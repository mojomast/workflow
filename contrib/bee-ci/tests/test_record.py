"""Tests for the bee-CI record layer.

``record.py`` is the bridge between a pipeline run result and the frozen
``bee-ci/evidence/v1`` evidence index.  It appends one entry per job through
``evidence.append`` and can render the index with ``report/render.py``.

The important property is honesty: a failed job stays failed, an unverified
job stays pending, and only a job with recorded passing evidence is stored as
success.  Missing values are stored as null, never invented.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence  # noqa: E402
import record  # noqa: E402

SHA = "a" * 40
SHA_B = "b" * 40
INDEX_REL = Path("evidence") / "index.json"


def verified_result(**overrides):
    data = {
        "repo": "workflow",
        "head_sha": SHA,
        "source": "bee",
        "started_at": "2026-11-13T00:00:00Z",
        "finished_at": "2026-11-13T00:01:00Z",
        "jobs": [
            {
                "job": "unit",
                "state": "success",
                "verified": True,
                "exit_codes": [{"step": "python -m pytest", "exit_code": 0}],
                "started_at": "2026-11-13T00:00:00Z",
                "finished_at": "2026-11-13T00:01:00Z",
                "result_path": f"evidence/workflow/{SHA}/unit-bee.json",
            }
        ],
    }
    data.update(overrides)
    return data


def test_appends_verified_run(tmp_path):
    index = tmp_path / INDEX_REL
    result = verified_result()

    assert record.record_result(result, index) == 1

    doc = evidence.load(index)
    assert doc["schema"] == "bee-ci/evidence/v1"
    assert len(doc["runs"]) == 1
    run = doc["runs"][0]
    assert run == {
        "repo": "workflow",
        "head_sha": SHA,
        "job": "unit",
        "source": "bee",
        "state": "success",
        "exit_codes": [{"step": "python -m pytest", "exit_code": 0}],
        "started_at": "2026-11-13T00:00:00Z",
        "finished_at": "2026-11-13T00:01:00Z",
        "result_path": f"evidence/workflow/{SHA}/unit-bee.json",
    }

    # The dedupe key is repo + head_sha + job + source; recording again is a
    # no-op and leaves the index byte-for-byte unchanged.
    original = index.read_bytes()
    assert record.record_result(result, index) == 0
    assert index.read_bytes() == original


def test_render_after_record(tmp_path):
    index = tmp_path / INDEX_REL

    record.record_result(verified_result(), index)
    record.record_result(
        verified_result(
            head_sha=SHA_B,
            source="github",
            jobs=[
                {
                    "job": "unit",
                    "state": "failure",
                    "exit_codes": [{"step": "python -m pytest", "exit_code": 1}],
                    "result_path": f"evidence/workflow/{SHA_B}/unit-github.json",
                }
            ],
        ),
        index,
    )
    record.record_result(
        verified_result(
            head_sha=SHA_B,
            source="bee",
            jobs=[
                {
                    "job": "unit",
                    "state": "success",
                    "verified": True,
                    "exit_codes": [{"step": "python -m pytest", "exit_code": 0}],
                }
            ],
        ),
        index,
    )
    record.record_result(
        verified_result(
            head_sha=SHA_B,
            source="bee",
            jobs=[
                {
                    "job": "lint",
                    "state": "success",
                    "verified": True,
                    "exit_codes": [{"step": "ruff check", "exit_code": 0}],
                }
            ],
        ),
        index,
    )

    html = record.render_report(index)

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "DISAGREEMENT" in html
    assert "workflow" in html and SHA[:12] in html and "unit" in html
    # The same run has conflicting bee/github evidence: it must be flagged.
    assert SHA_B[:12] in html
    assert 'data-kind="state-mismatch"' in html
    assert 'class="disagreement' in html
    assert "failure" in html and "success" in html
    # A bee-only job has no github side; the renderer must surface it as
    # missing instead of treating it as a pass.
    assert "lint" in html
    assert "missing" in html

    out = tmp_path / "report.html"
    written = record.write_report(index, out)
    assert written == out
    assert out.read_text(encoding="utf-8") == html


def test_failed_run_kept_honest(tmp_path):
    index = tmp_path / INDEX_REL
    result = {
        "repo": "workflow",
        "head_sha": SHA,
        "source": "bee",
        "jobs": [
            {
                "job": "failed-step",
                "state": "failure",
                "exit_codes": [{"step": "make test", "exit_code": 2}],
            },
            {
                "job": "errored",
                "state": "error",
                "exit_codes": None,
            },
            {
                "job": "unverified",
                "state": None,
                "exit_codes": None,
            },
            {
                # A claimed success with a recorded non-zero exit is a failure,
                # never an upgrade to success.
                "job": "lying",
                "state": "success",
                "exit_codes": [{"step": "make test", "exit_code": 7}],
            },
            {
                # Success without passing evidence is not proven; keep pending.
                "job": "unproven",
                "state": "success",
                "verified": False,
                "exit_codes": None,
            },
        ],
    }

    assert record.record_result(result, index) == 5

    doc = evidence.load(index)
    states = {run["job"]: run["state"] for run in doc["runs"]}
    assert states == {
        "failed-step": "failure",
        "errored": "error",
        "unverified": "pending",
        "lying": "failure",
        "unproven": "pending",
    }
    assert "success" not in states.values()

    html = record.render_report(index)
    assert "failure" in html and "error" in html and "pending" in html
    assert "unverified" in html

    # Recording the same failures again must not fabricate a success row.
    assert record.record_result(result, index) == 0
    assert json.loads(index.read_text(encoding="utf-8"))["schema"] == "bee-ci/evidence/v1"
