"""Offline contract tests for the bee-run CI dispatcher.

The launcher is replaced by a recording transport, so nothing here opens a
socket or reads a real launcher token. Each test imports ``dispatch`` lazily
so a missing implementation reports a RED per test instead of a collection
error.

Acceptance map:
* AC-001 parallel jobs get distinct, non-empty task ids -> test_unique_task_ids
* AC-002 the launcher token never reaches a result, repr or log -> test_token_redacted
* AC-003 timeout / launcher failure is an error, never success -> test_timeout_is_error
"""

from __future__ import annotations

import importlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOKEN = "launcher-token-do-not-print-4f8c2e"
HEAD = "a" * 40


def load_dispatch():
    """Import dispatch.py lazily so each RED test fails individually."""
    return importlib.import_module("dispatch")


def job_spec(name="unit"):
    return {
        "name": name,
        "os": "ubuntu-24.04",
        "image": "bee-ci/ubuntu",
        "arch": "x64",
        "python": "3.12",
        "node": None,
        "browser": "none",
        "runner": "bee",
    }


def work_item(dispatch, name="unit", repo="workflow", head_sha=HEAD):
    return dispatch.WorkItem(repo=repo, head_sha=head_sha, job=job_spec(name))


class RecordingTransport:
    """A thread-safe fake launcher that records requests."""

    def __init__(self, response=None):
        self.response = {"ok": True, "attempt_id": "attempt-1"} if response is None else response
        self.calls = []
        self.lock = threading.Lock()

    def post(self, url, payload, *, headers, timeout):
        with self.lock:
            self.calls.append(
                {
                    "url": url,
                    "payload": dict(payload),
                    "headers": dict(headers),
                    "timeout": timeout,
                }
            )
        return dict(self.response)


class LeakyTransport:
    """Raises an error that deliberately contains the token and a host."""

    def post(self, url, payload, *, headers, timeout):
        raise RuntimeError(
            f"launcher rejected bearer {TOKEN} via http://private-host.ts.net/v1"
        )


class EchoTransport:
    """Returns the token echoed back from an untrusted launcher."""

    def post(self, url, payload, *, headers, timeout):
        return {"ok": True, "attempt_id": "attempt-echo", "echo": TOKEN}


class TimeoutTransport:
    def post(self, url, payload, *, headers, timeout):
        raise TimeoutError(f"timed out talking to {url}")


class ErrorTransport:
    def post(self, url, payload, *, headers, timeout):
        raise RuntimeError(f"launcher 500 for bearer {TOKEN}")


def test_unique_task_ids():
    dispatch = load_dispatch()
    transport = RecordingTransport()
    items = [work_item(dispatch) for _ in range(12)]

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda item: dispatch.dispatch(
                    item, transport=transport, env={"BEE_CI_LAUNCHER_TOKEN": TOKEN}
                ),
                items,
            )
        )

    task_ids = [result["task_id"] for result in results]
    assert all(isinstance(task_id, str) and task_id.strip() for task_id in task_ids)
    assert len(set(task_ids)) == len(items), "every ticket must get its own task_id"
    assert all(result["state"] == "success" for result in results)

    payload_ids = [call["payload"]["task_id"] for call in transport.calls]
    assert len(payload_ids) == len(items)
    assert set(payload_ids) == set(task_ids)
    assert len(set(payload_ids)) == len(payload_ids)

    # A second identical batch must not reuse an earlier id either.
    again = dispatch.dispatch_all(
        items, transport=transport, env={"BEE_CI_LAUNCHER_TOKEN": TOKEN}
    )
    again_ids = [result["task_id"] for result in again]
    assert set(again_ids).isdisjoint(task_ids)


def test_token_redacted(caplog):
    dispatch = load_dispatch()
    item = work_item(dispatch)

    failed = dispatch.dispatch(
        item,
        transport=LeakyTransport(),
        env={"BEE_CI_LAUNCHER_TOKEN": TOKEN},
    )
    assert failed["state"] == "error"
    rendered = "\n".join(
        [
            json.dumps(failed.to_dict(), sort_keys=True),
            str(failed),
            repr(failed),
            caplog.text,
        ]
    )
    assert TOKEN not in rendered
    assert "ts.net" not in rendered

    echoed = dispatch.dispatch(
        item,
        transport=EchoTransport(),
        env={"BEE_CI_LAUNCHER_TOKEN": TOKEN},
    )
    assert echoed["state"] == "success"
    rendered = "\n".join(
        [
            json.dumps(echoed.to_dict(), sort_keys=True),
            str(echoed),
            repr(echoed),
        ]
    )
    assert TOKEN not in rendered

    # The token is read from the environment and sent only as a header.
    transport = RecordingTransport()
    dispatch.dispatch(
        item,
        transport=transport,
        env={"BEE_CI_LAUNCHER_TOKEN": TOKEN},
    )
    assert transport.calls[0]["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in json.dumps(transport.calls[0]["payload"], sort_keys=True)


def test_timeout_is_error():
    dispatch = load_dispatch()
    result = dispatch.dispatch(
        work_item(dispatch),
        transport=TimeoutTransport(),
        env={"BEE_CI_LAUNCHER_TOKEN": TOKEN},
    )

    assert result["state"] == "error"
    assert result["ok"] is False
    assert result["state"] != "success"
    assert result["code"] in {"timeout", "transport_error"}


def test_launcher_error_is_error():
    dispatch = load_dispatch()
    result = dispatch.dispatch(
        work_item(dispatch),
        transport=ErrorTransport(),
        env={"BEE_CI_LAUNCHER_TOKEN": TOKEN},
    )

    assert result["state"] == "error"
    assert result["ok"] is False
    assert TOKEN not in json.dumps(result.to_dict(), sort_keys=True)
    assert TOKEN not in repr(result)


def test_missing_token_fails_closed():
    dispatch = load_dispatch()
    transport = RecordingTransport()
    result = dispatch.dispatch(work_item(dispatch), transport=transport, env={})

    assert result["state"] == "error"
    assert result["ok"] is False
    assert result["code"] == "missing_token"
    assert transport.calls == []
