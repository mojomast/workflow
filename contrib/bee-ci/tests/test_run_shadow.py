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
import urllib.error
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
        self.capacity_info = (
            {"active": 0, "max_concurrent": 3} if capacity is None else capacity
        )
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
    launcher = FakeLauncher(capacity={"active": 0, "max_concurrent": 3})
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
    launcher = FakeLauncher(capacity={"active": 2, "max_concurrent": 2})
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
    launcher = FakeLauncher(
        capacity={"active": 0, "max_concurrent": 3}, mode="unsigned"
    )
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
    launcher = FakeLauncher(
        capacity={"active": 0, "max_concurrent": 3}, mode="none"
    )
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
    launcher = RecordingDispatchLauncher(capacity={"active": 0, "max_concurrent": 3})

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


def load_dispatch():
    return importlib.import_module("dispatch")


class RecordingPostTransport:
    """A fake launcher transport that records the parsed JSON body."""

    def __init__(self, response=None):
        self.response = (
            {"ok": True, "id": "attempt-1"} if response is None else response
        )
        self.calls = []

    def post(self, url, payload, *, headers, timeout):
        self.calls.append(
            {
                "url": url,
                "payload": json.loads(json.dumps(payload)),
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        return dict(self.response)


def test_dispatch_posts_a_launcher_brief():
    dispatch = load_dispatch()
    transport = RecordingPostTransport()
    job = {
        "name": "unit",
        "command": ["uv sync --frozen --no-dev", "uv run python -m unittest"],
        "workdir": ".",
        "timeout_s": 42,
        "leased_paths": ["src/app.py", "tests/test_app.py"],
    }

    result = dispatch.dispatch(
        dispatch.WorkItem(repo="mojomast/hyvv", head_sha=HEAD, job=job),
        transport=transport,
        env={"BEE_CI_LAUNCHER_TOKEN": TOKEN},
    )

    assert result["state"] == "success", result
    assert transport.calls, "the launcher must be called"
    call = transport.calls[0]
    assert call["url"].endswith("/v1/attempts"), call["url"]

    body = call["payload"]
    assert body["model"] == dispatch.DEFAULT_MODEL
    brief = body["brief"]
    assert brief["project"] == "hyvv"
    assert brief["source_rev"] == HEAD
    assert brief["commands"] == job["command"]
    assert brief["assigned_files"] == ["src/app.py", "tests/test_app.py"]
    assert brief["budget"] == {"timeout_s": 42}
    assert "unit" in brief["objective"]
    assert "exit code" in brief["objective"].lower()
    assert brief["acceptance"]
    assert TOKEN not in json.dumps(body, sort_keys=True)

    # Defaults: a bare manifest repo stays bare, no leased paths still yields
    # an assigned file, and a job without timeout_s uses the 900s budget.
    default = dispatch.build_payload(
        dispatch.WorkItem(repo="workflow", head_sha=HEAD, job={"name": "reference"}),
        "task-fixture",
    )["brief"]
    assert default["project"] == "workflow"
    assert default["assigned_files"]
    assert default["budget"] == {"timeout_s": 900}
    assert default["commands"] == []


def test_launcher_error_text_is_surfaced(tmp_path):
    dispatch = load_dispatch()
    item = dispatch.WorkItem(repo="workflow", head_sha=HEAD, job={"name": "unit"})

    class StatusTransport:
        def __init__(self, status_code, error):
            self.status_code = status_code
            self.error = error

        def post(self, url, payload, *, headers, timeout):
            return {"status_code": self.status_code, "error": self.error}

    for status_code, message in (
        (400, "brief.objective is required"),
        (403, "project 'workflow' is not in the allow-list"),
    ):
        result = dispatch.dispatch(
            item,
            transport=StatusTransport(status_code, message),
            env={"BEE_CI_LAUNCHER_TOKEN": TOKEN},
        )
        assert result["state"] == "error"
        assert message in (result["error"] or ""), result

    class RejectingLauncher(FakeLauncher):
        def __init__(self, error):
            super().__init__(capacity={"active": 0, "max_concurrent": 3})
            self.error = error

        def dispatch(self, item):
            self.calls.append(("dispatch", job_name(item)))
            return {
                "ok": False,
                "state": "error",
                "code": "launcher_error",
                "error": self.error,
            }

    module = load_run_shadow()
    report = module.run(
        {
            "repo": REPO,
            "pr": 7,
            "live": True,
            "github": FakeGitHub(),
            "launcher": RejectingLauncher("brief.objective is required"),
            "env": {module.TOKEN_ENV: TOKEN, module.KEY_ENV: KEY},
            "evidence_index": str(tmp_path / "index.json"),
            "report_path": str(tmp_path / "report.html"),
        }
    )
    rows = [row for row in report["jobs"] if row["eligible"]]
    assert rows and all(row["state"] == "error" for row in rows)
    assert all("brief.objective is required" in row["detail"] for row in rows)
    assert all("did not accept" not in row["detail"] for row in rows)


def test_missing_required_tool_is_not_run(tmp_path, monkeypatch):
    module = load_run_shadow()
    launcher = FakeLauncher(capacity={"active": 0, "max_concurrent": 3})
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

    # The default checker must ask the real PATH, not assume every tool exists.
    # ``which`` is patched only to keep this test hermetic while still running
    # the uninjected default code path.
    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name: None if name == "gitleaks" else "/usr/bin/" + name,
    )
    seen.clear()
    code, stdout, stderr = run_cli(
        module,
        ["--repo", "mojomast/hyvv", "--pr", "7"],
        FakeGitHub(),
        FakeLauncher(),
        env={},
    )

    assert code == 0, (stdout, stderr)
    report = report_from(stdout)
    rows = {row["job"]: row for row in report["jobs"]}
    scan = rows["scan"]
    assert scan["state"] == "not_run"
    assert scan["code"] == "missing_required_tool"
    assert scan["missing_tools"] == ["gitleaks"]
    assert "gitleaks" in scan["detail"]
    assert module._tool_checker({})("gitleaks") is False
class FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(url, code):
    return urllib.error.HTTPError(url, code, "fixture error", {}, io.BytesIO(b""))


class RecordingOpener:
    """Records every request URL and delegates to a responder."""

    def __init__(self, responder):
        self.responder = responder
        self.urls = []
        self.requests = []

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        self.requests.append({"url": request.full_url, "data": request.data})
        outcome = self.responder(request.full_url)
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(outcome)


def test_capacity_uses_health(tmp_path):
    module = load_run_shadow()
    opener = RecordingOpener(
        lambda url: {
            "ok": True,
            "version": "1",
            "max_concurrent": 3,
            "active": 2,
            "queued": 0,
            "model": "fixture",
            "models": ["fixture"],
            "uptime_s": 1,
            "loop_lag_ms": 0,
        }
    )
    client = module.LauncherClient(
        "https://launcher.invalid:9", TOKEN, opener=opener
    )

    info = client.capacity()

    assert opener.urls == ["https://launcher.invalid:9/v1/health"]
    assert info["active"] == 2
    assert info["max_concurrent"] == 3
    assert module._capacity_state(info) == (True, None)
    assert module._capacity_state({"active": 3, "max_concurrent": 3}) == (
        False,
        "capacity_full",
    )
    assert module._capacity_state({"active": 0}) == (False, "capacity_unknown")
    assert module._capacity_state([]) == (False, "capacity_unknown")

    # The gate passes only while active < max_concurrent.
    index = tmp_path / "e.json"
    report_path = tmp_path / "e.html"
    report = module.run(
        {
            "repo": REPO,
            "pr": 7,
            "live": True,
            "github": FakeGitHub(),
            "launcher": FakeLauncher(capacity={"active": 2, "max_concurrent": 3}),
            "env": {module.TOKEN_ENV: TOKEN, module.KEY_ENV: KEY},
            "evidence_index": str(index),
            "report_path": str(report_path),
        }
    )
    assert report["status"] == "ok"
    assert all(
        row["state"] == "success"
        for row in report["jobs"]
        if row["eligible"]
    )

    # A 404 and an unparseable body are named failures, never exceptions.
    for opener, expected in (
        (
            RecordingOpener(
                lambda url: http_error(url, 404)
            ),
            "capacity_check_failed",
        ),
        (RecordingOpener(lambda url: b"{not json"), "capacity_check_failed"),
        (RecordingOpener(lambda url: []), "capacity_unknown"),
    ):
        client = module.LauncherClient(
            "https://launcher.invalid:9", TOKEN, opener=opener
        )
        report = module.run(
            {
                "repo": REPO,
                "pr": 7,
                "live": True,
                "github": FakeGitHub(),
                "launcher": client,
                "env": {module.TOKEN_ENV: TOKEN, module.KEY_ENV: KEY},
            }
        )
        assert report["status"] == "skipped"
        rows = [row for row in report["jobs"] if row["eligible"]]
        assert rows and all(row["code"] == expected for row in rows)


def test_result_uses_attempts_route():
    module = load_run_shadow()
    calls = {"result": 0}
    result_body = {"job_id": "attempt-1", "steps": [{"name": "tests", "exit_code": 0}]}

    def respond(url):
        if url.endswith("/result"):
            calls["result"] += 1
            if calls["result"] == 1:
                return http_error(url, 409)
            return result_body
        return {"id": "attempt-1", "state": "running"}

    opener = RecordingOpener(respond)
    client = module.LauncherClient(
        "https://launcher.invalid:9", TOKEN, opener=opener
    )

    payload = module._poll_result(
        client,
        "attempt-1",
        timeout=5.0,
        interval=0.0,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
    )
    assert payload == result_body
    assert opener.urls == [
        "https://launcher.invalid:9/v1/attempts/attempt-1/result",
        "https://launcher.invalid:9/v1/attempts/attempt-1",
        "https://launcher.invalid:9/v1/attempts/attempt-1/result",
    ]
    assert not any("/v1/results/" in url for url in opener.urls)

    # A persistent 409 keeps polling until the timeout, then reports no result.
    always_409 = RecordingOpener(
        lambda url: http_error(url, 409)
        if url.endswith("/result")
        else {"id": "attempt-2", "state": "running"}
    )
    client = module.LauncherClient(
        "https://launcher.invalid:9", TOKEN, opener=always_409
    )
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds

    payload = module._poll_result(
        client,
        "attempt-2",
        timeout=3.0,
        interval=1.0,
        clock=clock,
        sleep=sleep,
    )
    assert payload is None
    result_calls = [url for url in always_409.urls if url.endswith("/result")]
    assert len(result_calls) >= 2
    assert all(
        url.startswith("https://launcher.invalid:9/v1/attempts/attempt-2")
        for url in always_409.urls
    )

    # Any other status is a launcher failure, not a silent "no result".
    failing = module.LauncherClient(
        "https://launcher.invalid:9",
        TOKEN,
        opener=RecordingOpener(lambda url: http_error(url, 404)),
    )
    try:
        failing.result("attempt-3")
    except module.ShadowError:
        pass
    else:
        raise AssertionError("404 must not be treated as no-result-yet")


def test_live_http_end_to_end_uses_the_brief(tmp_path):
    module = load_run_shadow()
    dispatch = load_dispatch()
    polled = {"result": 0}

    def respond(url):
        if url.endswith("/v1/health"):
            return {"ok": True, "max_concurrent": 2, "active": 0}
        if url.endswith("/v1/attempts"):
            return {"id": "attempt-live-1", "state": "queued"}
        if url.endswith("/result"):
            polled["result"] += 1
            if polled["result"] == 1:
                return http_error(url, 409)
            payload = {
                "job_id": "attempt-live-1",
                "head_sha": HEAD,
                "steps": [{"name": "tests", "exit_code": 0}],
            }
            payload["signature"] = verify_result.sign_payload(payload, KEY)
            return payload
        return {"id": "attempt-live-1", "state": "running"}

    opener = RecordingOpener(respond)
    code, stdout, stderr = run_cli(
        module,
        [
            "--repo",
            REPO,
            "--pr",
            "7",
            "--live",
            "--launcher-url",
            "https://launcher.invalid:9",
            "--timeout",
            "5",
            "--poll-interval",
            "0",
            "--index",
            str(tmp_path / "index.json"),
            "--report",
            str(tmp_path / "report.html"),
        ],
        FakeGitHub(),
        None,
        env={"BUNDLEBEES_LAUNCHER_TOKEN": TOKEN, "BEE_CI_RESULT_KEY": KEY},
        opener=opener,
        tool_checker=lambda tool: True,
    )

    assert code == 0, (stdout, stderr)
    report = report_from(stdout)
    assert report["status"] == "ok"
    states = {row["job"]: row["state"] for row in report["jobs"] if row["eligible"]}
    assert states == {name: "success" for name in ELIGIBLE}

    posts = [entry for entry in opener.requests if entry["url"].endswith("/v1/attempts")]
    assert len(posts) == len(ELIGIBLE)
    for entry in posts:
        body = json.loads(entry["data"].decode("utf-8"))
        assert body["brief"]["project"] == "workflow"
        assert body["brief"]["source_rev"] == HEAD
        assert body["brief"]["budget"] == {"timeout_s": 900}
        assert body["brief"]["assigned_files"] == ["."]
        assert body["model"] == dispatch.DEFAULT_MODEL
        assert TOKEN not in entry["data"].decode("utf-8")

    # Polling uses the launcher's attempt id, never the locally minted task id.
    result_urls = [url for url in opener.urls if url.endswith("/result")]
    assert result_urls
    assert all("/v1/attempts/attempt-live-1/result" in url for url in result_urls)


def test_repo_manifest_and_url_fallback():
    module = load_run_shadow()

    # A bare manifest name from contrib/bee-ci/jobs/*.yaml is accepted.
    github = FakeGitHub()
    code, stdout, stderr = run_cli(
        module, ["--repo", "workflow", "--pr", "7"], github, FakeLauncher(), env={}
    )
    assert code == 0, (stdout, stderr)
    report = report_from(stdout)
    assert report["manifest"] == "workflow"
    assert report["repo"] == "workflow"
    assert report["eligible"] == ELIGIBLE

    # owner/name is still accepted and resolves to the same manifest.
    code, stdout, stderr = run_cli(
        module, ["--repo", REPO, "--pr", "7"], FakeGitHub(), FakeLauncher(), env={}
    )
    assert code == 0, (stdout, stderr)
    assert report_from(stdout)["manifest"] == "workflow"

    # Unknown or malformed names fail closed before any external call.
    for bad in ("nope", "a/b/c"):
        github = FakeGitHub()
        code, stdout, stderr = run_cli(
            module, ["--repo", bad, "--pr", "7"], github, FakeLauncher(), env={}
        )
        assert code == 2, (stdout, stderr)
        assert github.calls == []

    # With no --launcher-url and no env URL, hermes supplies the launcher URL.
    hermes_calls = []
    opener = RecordingOpener(
        lambda url: {"ok": True, "max_concurrent": 1, "active": 1}
    )

    def hermes(args, **kwargs):
        hermes_calls.append(list(args))
        return '  "https://launcher.invalid:9/"  \n'

    report = module.run(
        {
            "repo": REPO,
            "pr": 7,
            "live": True,
            "github": FakeGitHub(),
            "env": {module.TOKEN_ENV: TOKEN, module.KEY_ENV: KEY},
            "hermes": hermes,
            "opener": opener,
        }
    )
    assert hermes_calls == [
        ["config", "get", "plugins.entries.bundlebees.settings.launcher_url"]
    ]
    assert opener.urls == ["https://launcher.invalid:9/v1/health"]
    assert report["status"] == "skipped"
    rows = [row for row in report["jobs"] if row["eligible"]]
    assert all(row["code"] == "capacity_full" for row in rows)

    # An env URL wins over hermes.
    env_opener = RecordingOpener(
        lambda url: {"ok": True, "max_concurrent": 1, "active": 1}
    )
    report = module.run(
        {
            "repo": REPO,
            "pr": 7,
            "live": True,
            "github": FakeGitHub(),
            "env": {
                module.TOKEN_ENV: TOKEN,
                module.KEY_ENV: KEY,
                module.URL_ENV: "https://env.invalid:8",
            },
            "hermes": lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("hermes must not run when the env URL is set")
            ),
            "opener": env_opener,
        }
    )
    assert env_opener.urls == ["https://env.invalid:8/v1/health"]
    assert report["status"] == "skipped"

    # A failed hermes call is a named skip, never a crash.
    report = module.run(
        {
            "repo": REPO,
            "pr": 7,
            "live": True,
            "github": FakeGitHub(),
            "env": {module.TOKEN_ENV: TOKEN, module.KEY_ENV: KEY},
            "hermes": lambda *a, **k: (_ for _ in ()).throw(OSError("missing")),
        }
    )
    assert report["status"] == "skipped"
    rows = [row for row in report["jobs"] if row["eligible"]]
    assert all(row["code"] == "no_launcher_endpoint" for row in rows)
