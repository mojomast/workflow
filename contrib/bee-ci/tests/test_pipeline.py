"""Offline acceptance tests for the bee-CI pipeline.

Every stage is injected: the GitHub reader, the launcher status adapter, the
dispatch transport, the signed result provider and the GitHub Actions
conclusions. Nothing here opens a socket, touches git, or contacts a real
launcher. The pipeline is imported lazily so a RED run reports one failure per
test instead of a collection error.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify_result  # noqa: E402

SHA = "a" * 40
KEY = "offline-test-key-4f8c2e"
REPO = "mojomast/workflow"

JOB = {
    "name": "reference",
    "os": "ubuntu-24.04",
    "image": "cua-bee-linux-x64",
    "arch": "x64",
    "python": "3.12",
    "node": None,
    "browser": "none",
    "runner": "bee",
}


def load_pipeline():
    """Import pipeline.py lazily so each RED test fails individually."""
    return importlib.import_module("pipeline")


def pr(number=1, sha=SHA):
    return {
        "number": number,
        "head_sha": sha,
        "state": "open",
        "draft": False,
        "title": "Pipeline test",
        "url": "https://example.com/pull/1",
    }


class FakeGitHub:
    def __init__(self, calls, prs=None):
        self.calls = calls
        self.prs = [pr()] if prs is None else prs

    def list_open_prs(self, repo):
        self.calls.append(("poll", repo))
        return [dict(item) for item in self.prs]


class FakeLauncher:
    def __init__(self, calls):
        self.calls = calls

    def status(self):
        self.calls.append(("launcher-status",))
        return {"active": 0, "max": 1}

    def capacity(self):
        return 1

    def bee_count(self):
        return 0

    def dispatch(self, item):
        self.calls.append(("poll-dispatch", item.get("head_sha")))
        return {"ok": True}


class RecordingTransport:
    def __init__(self, calls, response=None):
        self.calls = calls
        self.response = (
            {"ok": True, "attempt_id": "attempt-1"} if response is None else response
        )

    def post(self, url, payload, *, headers, timeout):
        self.calls.append(("dispatch", payload["job_name"], payload["task_id"]))
        return dict(self.response)


class ForbiddenStatusTransport:
    """A status transport that fails the test if the pipeline ever calls it."""

    def __init__(self):
        self.calls = []

    def __call__(self, record, token):
        self.calls.append(record)
        raise AssertionError("dry-run must not post a GitHub status")


def signed_result(sha, job_id, exit_code=0):
    payload = {
        "head_sha": sha,
        "job_id": job_id,
        "steps": [{"name": "run", "exit_code": exit_code}],
    }
    payload["signature"] = verify_result.sign_payload(payload, KEY)
    return payload


def result_provider(calls, *, unsigned=False):
    def provider(*, repo, head_sha, job, task_id):
        calls.append(("verify", job, task_id))
        if unsigned:
            return {
                "head_sha": head_sha,
                "job_id": task_id,
                "steps": [{"name": "run", "exit_code": 0}],
            }
        return signed_result(head_sha, task_id)

    return provider


def actions_provider(calls):
    def provider(*, repo, records):
        calls.append(("compare", repo))
        return {
            "records": [
                {"sha": row["sha"], "job": row["job"], "conclusion": "success"}
                for row in records
            ]
        }

    return provider


def one_job_manifest(name):
    assert name == "workflow"
    return {"repo": "workflow", "jobs": [dict(JOB)]}


def test_stage_order(tmp_path):
    pipeline = load_pipeline()
    calls = []

    report = pipeline.run(
        {
            "repos": [REPO],
            "github": FakeGitHub(calls),
            "launcher": FakeLauncher(calls),
            "transport": RecordingTransport(calls),
            "state_path": tmp_path / "state.json",
            "results": result_provider(calls),
            "actions": actions_provider(calls),
            "key": KEY,
        }
    )

    assert report["dry_run"] is True
    stages = [entry[0] for entry in calls]
    first_poll = stages.index("poll")
    dispatch_positions = [i for i, name in enumerate(stages) if name == "dispatch"]
    verify_positions = [i for i, name in enumerate(stages) if name == "verify"]
    compare_positions = [i for i, name in enumerate(stages) if name == "compare"]

    assert dispatch_positions and verify_positions and compare_positions
    assert first_poll < dispatch_positions[0]
    assert max(dispatch_positions) < min(verify_positions)
    assert max(verify_positions) < min(compare_positions)

    jobs = report["jobs"]
    assert jobs
    assert {job["repo"] for job in jobs} == {REPO}
    assert {job["sha"] for job in jobs} == {SHA}
    assert all(job["status"] == "success" for job in jobs)
    assert all(job["stage"] == "compare" for job in jobs)

    task_ids = [job["task_id"] for job in jobs]
    assert len(task_ids) == len(set(task_ids)), "each job must get a unique task id"
    assert all(isinstance(task_id, str) and task_id for task_id in task_ids)

    assert all(job["verification"]["status"] == "success" for job in jobs)
    assert all(job["comparison"]["verdict"] == "agree" for job in jobs)
    assert report["summary"]["success"] == len(jobs)
    assert report["summary"]["error"] == 0


def test_dry_run_default_never_posts(tmp_path, monkeypatch):
    pipeline = load_pipeline()
    import dispatch as dispatch_module
    import poll as poll_module

    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run must not create a live client or launcher")

    monkeypatch.setattr(dispatch_module, "HttpTransport", forbidden)
    monkeypatch.setattr(poll_module, "default_launcher", forbidden)
    monkeypatch.setattr(poll_module, "HttpLauncher", forbidden)
    monkeypatch.setattr(poll_module, "CommandLauncher", forbidden)
    monkeypatch.setattr(poll_module, "GitHubClient", forbidden)

    calls = []
    status_transport = ForbiddenStatusTransport()
    report = pipeline.run(
        {
            "repos": [REPO],
            "github": FakeGitHub(calls),
            "launcher": FakeLauncher(calls),
            "state_path": tmp_path / "state.json",
            "results": result_provider(calls),
            "actions": actions_provider(calls),
            "key": KEY,
            "status_transport": status_transport,
            # A caller cannot opt out of dry-run by setting only dry_run=False;
            # the explicit live flag is required.
            "dry_run": False,
        }
    )

    assert report["dry_run"] is True
    assert report["live"] is False
    assert status_transport.calls == []
    assert report["jobs"]
    assert all(job["status"] == "success" for job in report["jobs"])
    assert all(job["dispatch"]["state"] == "success" for job in report["jobs"])
    assert all(job["github_status"]["posted"] is False for job in report["jobs"])
    assert all(job["github_status"]["dry_run"] is True for job in report["jobs"])


def test_stage_failure_is_error(tmp_path):
    pipeline = load_pipeline()
    calls = []

    report = pipeline.run(
        {
            "repos": [REPO],
            "github": FakeGitHub(calls),
            "launcher": FakeLauncher(calls),
            "transport": RecordingTransport(calls),
            "state_path": tmp_path / "state.json",
            "manifest_loader": one_job_manifest,
            "results": result_provider(calls, unsigned=True),
            "actions": actions_provider(calls),
            "key": KEY,
        }
    )

    assert len(report["jobs"]) == 1
    job = report["jobs"][0]
    assert job["status"] == "error"
    assert job["stage"] == "verify"
    assert job["dispatch"]["state"] == "success"
    assert job["verification"]["status"] == "error"
    assert job["verification"]["code"] == "unsigned"
    assert job["error"]["code"] == "unsigned"
    assert job["comparison"] is None
    assert not [entry for entry in calls if entry[0] == "compare"]
    assert report["summary"]["error"] == 1
    assert report["summary"]["success"] == 0
    assert report["status"] == "error"


def test_dispatch_failure_stops_job(tmp_path):
    pipeline = load_pipeline()
    calls = []

    report = pipeline.run(
        {
            "repos": [REPO],
            "github": FakeGitHub(calls),
            "launcher": FakeLauncher(calls),
            "transport": RecordingTransport(
                calls, response={"ok": False, "error": "launcher rejected"}
            ),
            "state_path": tmp_path / "state.json",
            "manifest_loader": one_job_manifest,
            "results": result_provider(calls),
            "actions": actions_provider(calls),
            "key": KEY,
        }
    )

    job = report["jobs"][0]
    assert job["status"] == "error"
    assert job["stage"] == "dispatch"
    assert job["dispatch"]["state"] == "error"
    assert job["verification"] is None
    assert job["comparison"] is None
    assert not [entry for entry in calls if entry[0] == "verify"]
    assert not [entry for entry in calls if entry[0] == "compare"]
    assert report["summary"]["error"] == 1
