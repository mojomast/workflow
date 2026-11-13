"""Offline acceptance tests for the bee-CI shadow-runner CLI.

The GitHub reader and the launcher are replaced with recording fakes, so
nothing here opens a socket, runs ``gh`` or contacts a real launcher. The
module is imported lazily so a missing implementation reports one RED failure
per test instead of a collection error.

Acceptance map:
* AC-001 dry-run prints the plan and never touches the launcher
* AC-002 live dispatches only bee-eligible legs, verifies, records, renders,
  and never posts a commit status
* AC-003 missing token, full capacity, timeout and unverifiable results are
  skipped/error, never success
"""

from __future__ import annotations

import importlib
import io
import json
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify_result  # noqa: E402

TOKEN = "fixture-token-not-a-secret"
KEY = "fixture-key-not-a-secret"
HEAD = "a" * 40
REPO = "mojomast/workflow"
ELIGIBLE = ["reference", "acceptance-light", "secret-scan"]
EXCLUDED = ["macos-docs", "arm64-smoke"]


def load_run_shadow():
    """Import run_shadow.py lazily so each RED test fails individually."""
    return importlib.import_module("run_shadow")


def job_name(item):
    job = item.get("job")
    if isinstance(job, Mapping):
        return job.get("name")
    return item.get("job_name") or str(job)


def signed_payload(job_id, head_sha=HEAD, exit_code=0):
    payload = {
        "job_id": job_id,
        "head_sha": head_sha,
        "steps": [{"name": "tests", "exit_code": exit_code}],
    }
    payload["signature"] = verify_result.sign_payload(payload, KEY)
    return payload


class FakeGitHub:
    def __init__(self, head_sha=HEAD, number=7, state="open", draft=False):
        self.head_sha = head_sha
        self.number = number
        self.state = state
        self.draft = draft
        self.calls = []

    def pr_head(self, repo, pr):
        self.calls.append(("pr_head", repo, pr))
        return {
            "number": pr,
            "head_sha": self.head_sha,
            "state": self.state,
            "draft": self.draft,
            "title": "shadow test",
            "url": "https://example.com/pull/7",
        }

    def actions_conclusions(self, repo, head_sha):
        self.calls.append(("actions", repo, head_sha))
        return [{"name": "CI", "conclusion": "success", "headSha": head_sha}]


class FakeLauncher:
    """A recording launcher with optional capacity and signed results."""

    def __init__(self, capacity=None, mode="signed", result=None, dispatch_error=None):
        self.capacity_info = {"active": 0, "max": 3} if capacity is None else capacity
        self.mode = mode
        self.result_override = result
        self.dispatch_error = dispatch_error
        self.results = {}
        self.calls = []

    def capacity(self):
        self.calls.append(("capacity",))
        if isinstance(self.capacity_info, BaseException):
            raise self.capacity_info
        return self.capacity_info

    def dispatch(self, item):
        name = job_name(item)
        self.calls.append(("dispatch", name))
        if self.dispatch_error is not None:
            raise self.dispatch_error
        task_id = f"task-{name}"
        if self.mode == "signed":
            self.results[task_id] = signed_payload(task_id)
        elif self.mode == "unsigned":
            self.results[task_id] = {
                "job_id": task_id,
                "head_sha": HEAD,
                "steps": [{"name": "tests", "exit_code": 0}],
            }
        return {"ok": True, "state": "success", "task_id": task_id}

    def result(self, task_id):
        self.calls.append(("result", task_id))
        if self.result_override is not None:
            return self.result_override
        return self.results.get(task_id)


def run_cli(module, argv, github, launcher, env, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = module.main(
        argv,
        github=github,
        launcher=launcher,
        out=out,
        err=err,
        env=env,
        **kwargs,
    )
    return code, out.getvalue(), err.getvalue()


def report_from(stdout):
    return json.loads(stdout)


def test_dry_run_prints_plan(tmp_path):
    module = load_run_shadow()
    github = FakeGitHub()
    launcher = FakeLauncher()

    code, stdout, stderr = run_cli(
        module,
        ["--repo", REPO, "--pr", "7"],
        github,
        launcher,
        env={},
    )

    assert code == 0, (stdout, stderr)
    report = report_from(stdout)
    assert report["dry_run"] is True
    assert report["live"] is False
    assert report["repo"] == REPO
    assert report["pr"] == 7
    assert report["head_sha"] == HEAD
    assert report["eligible"] == ELIGIBLE
    assert report["excluded"] == EXCLUDED
    assert report["posted_status"] is False

    rows = {row["job"]: row for row in report["jobs"]}
    for name in ELIGIBLE:
        assert rows[name]["eligible"] is True
    for name in EXCLUDED:
        assert rows[name]["eligible"] is False

    assert github.calls == [("pr_head", REPO, 7)]
    assert launcher.calls == []
    assert not (tmp_path / "index.json").exists()


def test_live_verifies_and_records_without_posting(tmp_path):
    module = load_run_shadow()
    github = FakeGitHub()
    launcher = FakeLauncher(capacity={"active": 0, "max": 3})
    index = tmp_path / "evidence" / "index.json"
    report_path = tmp_path / "evidence" / "report.html"

    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            REPO,
            "--pr",
            "7",
            "--live",
            "--index",
            str(index),
            "--report",
            str(report_path),
        ],
        github,
        launcher,
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
    )

    assert code == 0, (stdout, stderr)
    report = report_from(stdout)
    assert report["live"] is True
    assert report["dry_run"] is False
    assert report["posted_status"] is False
    assert report["status"] == "ok"
    states = {row["job"]: row["state"] for row in report["jobs"] if row["eligible"]}
    assert states == {name: "success" for name in ELIGIBLE}

    document = json.loads(index.read_text(encoding="utf-8"))
    bee_runs = [run for run in document["runs"] if run["source"] == "bee"]
    assert {run["job"] for run in bee_runs} == set(ELIGIBLE)
    assert all(run["state"] == "success" for run in bee_runs)
    assert all(run["repo"] == "workflow" for run in bee_runs)
    assert all(run["head_sha"] == HEAD for run in bee_runs)
    assert not any(run["source"] == "github" for run in document["runs"])

    assert report_path.is_file()
    page = report_path.read_text(encoding="utf-8")
    assert "reference" in page and "acceptance-light" in page

    dispatched = [call[1] for call in launcher.calls if call[0] == "dispatch"]
    assert dispatched == ELIGIBLE
    assert all(
        call[0] in {"capacity", "dispatch", "result"} for call in launcher.calls
    )
    assert ("actions", REPO, HEAD) in github.calls

    # Phase 1 must refuse any flag that would post a commit status.
    refused_code, refused_out, refused_err = run_cli(
        module,
        ["--repo", REPO, "--pr", "7", "--live", "--post-status"],
        FakeGitHub(),
        FakeLauncher(),
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
    )
    assert refused_code == 2
    assert "status" in refused_err.lower()
    assert refused_out == ""

    for text in (stdout, stderr, page, index.read_text(encoding="utf-8")):
        assert TOKEN not in text


def test_fail_closed_on_missing_token_and_capacity(tmp_path):
    module = load_run_shadow()

    # 1. Missing launcher token: skip everything and never contact the launcher.
    github = FakeGitHub()
    launcher = FakeLauncher()
    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            REPO,
            "--pr",
            "7",
            "--live",
            "--index",
            str(tmp_path / "a.json"),
            "--report",
            str(tmp_path / "a.html"),
        ],
        github,
        launcher,
        env={},
    )
    assert code != 0, (stdout, stderr)
    report = report_from(stdout)
    rows = [row for row in report["jobs"] if row["eligible"]]
    assert len(rows) == len(ELIGIBLE)
    assert all(row["state"] == "skipped" for row in rows)
    assert all(row["code"] == "missing_token" for row in rows)
    assert launcher.calls == []
    assert report["status"] == "skipped"

    # 2. Launcher over capacity: skip, never dispatch.
    launcher = FakeLauncher(capacity={"active": 2, "max": 2})
    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            REPO,
            "--pr",
            "7",
            "--live",
            "--index",
            str(tmp_path / "b.json"),
            "--report",
            str(tmp_path / "b.html"),
        ],
        FakeGitHub(),
        launcher,
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
    )
    assert code != 0, (stdout, stderr)
    report = report_from(stdout)
    rows = [row for row in report["jobs"] if row["eligible"]]
    assert all(row["state"] == "skipped" for row in rows)
    assert all(row["code"] == "capacity_full" for row in rows)
    assert launcher.calls == [("capacity",)]

    # 3. Unverifiable result: error, never success, and the index records error.
    index = tmp_path / "c.json"
    launcher = FakeLauncher(capacity={"active": 0, "max": 3}, mode="unsigned")
    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            REPO,
            "--pr",
            "7",
            "--live",
            "--index",
            str(index),
            "--report",
            str(tmp_path / "c.html"),
        ],
        FakeGitHub(),
        launcher,
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
    )
    assert code != 0, (stdout, stderr)
    report = report_from(stdout)
    rows = [row for row in report["jobs"] if row["eligible"]]
    assert all(row["state"] == "error" for row in rows)
    document = json.loads(index.read_text(encoding="utf-8"))
    assert document["runs"]
    assert all(run["state"] == "error" for run in document["runs"])
    assert not any(run["state"] == "success" for run in document["runs"])

    # 4. Poll timeout: error, never success or pending-as-success.
    index = tmp_path / "d.json"
    launcher = FakeLauncher(capacity={"active": 0, "max": 3}, mode="none")
    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            REPO,
            "--pr",
            "7",
            "--live",
            "--timeout",
            "0",
            "--index",
            str(index),
            "--report",
            str(tmp_path / "d.html"),
        ],
        FakeGitHub(),
        launcher,
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
    )
    assert code != 0, (stdout, stderr)
    report = report_from(stdout)
    rows = [row for row in report["jobs"] if row["eligible"]]
    assert all(row["state"] == "error" for row in rows)
    assert all(row["code"] == "timeout" for row in rows)
    document = json.loads(index.read_text(encoding="utf-8"))
    assert all(run["state"] == "error" for run in document["runs"])


class RecordingDispatchLauncher(FakeLauncher):
    """A fake launcher that keeps the whole dispatched work item."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.items = []

    def dispatch(self, item):
        self.items.append(dict(item))
        return super().dispatch(item)


def test_bee_brief_is_built_from_manifest_commands():
    module = load_run_shadow()
    job = {
        "name": "unit",
        "command": ["uv sync --frozen --no-dev", "uv run python -m unittest"],
        "workdir": ".",
        "requires": ["uv"],
        "timeout_s": 42,
    }

    brief = module.build_bee_brief(job, repo="hyvv")

    assert brief["commands"] == job["command"]
    assert brief["workdir"] == "."
    assert brief["requires"] == ["uv"]
    assert brief["timeout_s"] == 42
    assert brief["objective"]
    assert any("unit" in criterion for criterion in brief["acceptance_criteria"])


def test_dispatch_carries_the_bee_brief(tmp_path):
    module = load_run_shadow()
    launcher = RecordingDispatchLauncher(capacity={"active": 0, "max": 3})

    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            "mojomast/hyvv",
            "--pr",
            "7",
            "--live",
            "--index",
            str(tmp_path / "index.json"),
            "--report",
            str(tmp_path / "report.html"),
        ],
        FakeGitHub(),
        launcher,
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
        tool_checker=lambda tool: True,
    )

    assert code == 0, (stdout, stderr)
    by_job = {item["job"]["name"]: item for item in launcher.items}
    unit = by_job["unit"]
    assert unit["brief"]["commands"] == [
        "uv sync --frozen --no-dev || uv sync --no-dev",
        "uv run python -m unittest discover -s tests -v",
    ]
    assert unit["job"]["brief"] == unit["brief"]


def test_missing_required_tool_is_not_run(tmp_path):
    module = load_run_shadow()
    launcher = FakeLauncher(capacity={"active": 0, "max": 3})
    seen = []

    def tool_checker(tool):
        seen.append(tool)
        return tool != "gitleaks"

    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            "mojomast/hyvv",
            "--pr",
            "7",
            "--live",
            "--index",
            str(tmp_path / "index.json"),
            "--report",
            str(tmp_path / "report.html"),
        ],
        FakeGitHub(),
        launcher,
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
        tool_checker=tool_checker,
    )

    assert code != 0, (stdout, stderr)
    report = report_from(stdout)
    rows = {row["job"]: row for row in report["jobs"]}

    scan = rows["scan"]
    assert scan["state"] == "not_run"
    assert scan["code"] == "missing_required_tool"
    assert "gitleaks" in scan["detail"]
    assert scan["missing_tools"] == ["gitleaks"]

    dispatched = [call[1] for call in launcher.calls if call[0] == "dispatch"]
    assert "scan" not in dispatched
    assert "unit" in dispatched
    assert report["status"] != "ok"
