"""Offline tests for the bee-run CI poller.

The tests inject a fake GitHub reader and a fake launcher, so nothing here
touches GitHub, the launcher or any host outside the temporary directory.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_poll():
    """Import poll.py lazily so a red run reports each test, not a collection error."""
    return importlib.import_module("poll")


def pr(number, sha, *, state="open", draft=False, merged=False, title=None):
    record = {
        "number": number,
        "head_sha": sha,
        "state": state,
        "draft": draft,
        "title": title or f"PR {number}",
        "url": f"https://example.invalid/pull/{number}",
    }
    if merged:
        record["merged_at"] = "2026-11-12T00:00:00Z"
        record["state"] = "closed"
    return record


class FakeGitHub:
    def __init__(self, prs_by_repo):
        self.prs_by_repo = prs_by_repo
        self.calls = []

    def list_open_prs(self, repo):
        self.calls.append(repo)
        return [dict(item) for item in self.prs_by_repo.get(repo, [])]


class FakeLauncher:
    def __init__(self, active=0, cap=3):
        self.active = active
        self.cap = cap
        self.dispatch_calls = []

    def bee_count(self):
        return self.active

    def capacity(self):
        return self.cap

    def dispatch(self, item):
        self.dispatch_calls.append(dict(item))
        self.active += 1
        return {"ok": True, "head_sha": item["head_sha"]}


def make_poller(poll, tmp_path, github, launcher, repos=("o/r",), cap=None):
    return poll.Poller(
        repos=list(repos),
        state_path=tmp_path / "state.json",
        github=github,
        launcher=launcher,
        cap=cap,
    )


def read_state(tmp_path):
    return json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))


def test_dedupes_heads(tmp_path):
    poll = load_poll()
    sha_a = "a" * 40
    sha_b = "b" * 40
    github = FakeGitHub({"o/r": [pr(1, sha_a)]})
    launcher = FakeLauncher(active=0, cap=3)

    first = make_poller(poll, tmp_path, github, launcher).poll()
    assert [item["head_sha"] for item in first["new"]] == [sha_a]
    assert [item["head_sha"] for item in first["dispatched"]] == [sha_a]
    assert len(launcher.dispatch_calls) == 1

    # A second run sees the same head. It must not queue or dispatch it again.
    second = make_poller(poll, tmp_path, github, launcher).poll()
    assert second["new"] == []
    assert second["dispatched"] == []
    assert len(launcher.dispatch_calls) == 1
    assert sha_a in read_state(tmp_path)["queued"]

    # A genuinely new head is still picked up exactly once.
    github.prs_by_repo["o/r"].append(pr(2, sha_b))
    third = make_poller(poll, tmp_path, github, launcher).poll()
    assert [item["head_sha"] for item in third["new"]] == [sha_b]
    assert len(launcher.dispatch_calls) == 2

    fourth = make_poller(poll, tmp_path, github, launcher).poll()
    assert fourth["new"] == []
    assert len(launcher.dispatch_calls) == 2


def test_skips_closed(tmp_path):
    poll = load_poll()
    open_sha = "1" * 40
    closed_sha = "2" * 40
    merged_sha = "3" * 40
    draft_sha = "4" * 40
    github = FakeGitHub({
        "o/r": [
            pr(10, open_sha, state="open"),
            pr(11, closed_sha, state="closed"),
            pr(12, merged_sha, merged=True),
            pr(13, draft_sha, state="open", draft=True),
        ]
    })
    launcher = FakeLauncher(active=0, cap=3)

    result = make_poller(poll, tmp_path, github, launcher).poll()

    assert [item["head_sha"] for item in result["new"]] == [open_sha]
    assert [item["head_sha"] for item in result["dispatched"]] == [open_sha]
    assert [item["head_sha"] for item in launcher.dispatch_calls] == [open_sha]
    state = read_state(tmp_path)
    assert set(state["queued"]) == {open_sha}


def test_respects_cap(tmp_path):
    poll = load_poll()
    sha = "c" * 40
    github = FakeGitHub({"o/r": [pr(20, sha)]})
    launcher = FakeLauncher(active=1, cap=1)

    # The shared launcher is full: the head is queued, never dispatched.
    first = make_poller(poll, tmp_path, github, launcher).poll()
    assert [item["head_sha"] for item in first["new"]] == [sha]
    assert [item["head_sha"] for item in first["queued"]] == [sha]
    assert first["dispatched"] == []
    assert launcher.dispatch_calls == []
    assert read_state(tmp_path)["queued"][sha]["status"] == "queued"

    # Re-running while still full must not re-emit or dispatch the queued head.
    still_full = make_poller(poll, tmp_path, github, launcher).poll()
    assert still_full["new"] == []
    assert still_full["dispatched"] == []
    assert launcher.dispatch_calls == []

    # Capacity opens up: the already-queued head is dispatched exactly once.
    launcher.active = 0
    drained = make_poller(poll, tmp_path, github, launcher).poll()
    assert drained["new"] == []
    assert [item["head_sha"] for item in drained["dispatched"]] == [sha]
    assert len(launcher.dispatch_calls) == 1
    assert read_state(tmp_path)["queued"][sha]["status"] == "dispatched"


def test_queued_head_is_not_dispatched_after_pr_closes(tmp_path):
    poll = load_poll()
    sha = "d" * 40
    github = FakeGitHub({"o/r": [pr(30, sha)]})
    launcher = FakeLauncher(active=1, cap=1)

    first = make_poller(poll, tmp_path, github, launcher).poll()
    assert [item["head_sha"] for item in first["queued"]] == [sha]
    assert launcher.dispatch_calls == []

    # The PR closes while the head waits in the queue; capacity is now free.
    github.prs_by_repo["o/r"] = [pr(30, sha, state="closed")]
    launcher.active = 0
    second = make_poller(poll, tmp_path, github, launcher).poll()

    assert second["dispatched"] == []
    assert launcher.dispatch_calls == []
    assert read_state(tmp_path)["queued"][sha]["status"] == "closed"
