"""Approved acceptance tests for contrib/bee-ci/report/pr_summary.py. Coordinator-written; do not edit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPORT_DIR = Path(__file__).resolve().parents[1] / "report"
sys.path.insert(0, str(REPORT_DIR))

from pr_summary import render_pr_summary  # noqa: E402

SHA = "a" * 40


def contract(**over):
    c = {
        "contract_version": "acdd/1", "id": "W1-x", "title": "Add the thing",
        "outcome": {"summary": "Callers can use the thing", "observable_behavior": ["x"]},
        "acceptance_criteria": [
            {"id": "AC-001", "statement": "thing works", "verification": "test", "tests": ["t.py::T::a"]},
            {"id": "AC-002", "given": "g", "when": "w", "then": "t", "verification": "test", "tests": ["t.py::T::b"]},
        ],
    }
    c.update(over)
    return c


def record(phase, result="passed", cls="passed", **over):
    r = {"evidence_version": "tdd-evidence/1", "contract_id": "W1-x", "phase": phase, "revision": SHA,
         "result": result, "classification": cls, "at": "2026-11-23T10:00:00Z", "notes": ""}
    r.update(over)
    return r


def make(tmp_path, c=None, records=()):
    (tmp_path / "W1-x.contract.json").write_text(json.dumps(c or contract()))
    for rec in records:
        (tmp_path / f"W1-x.{rec['phase']}.json").write_text(json.dumps(rec))
    return tmp_path


def test_ac001_lists_title_and_every_acceptance_criterion(tmp_path):
    md = render_pr_summary(make(tmp_path, records=[record("red", "failed", "behavioral_failure"), record("green")]))
    assert "Add the thing" in md
    assert "AC-001" in md and "AC-002" in md
    assert "thing works" in md


def test_ac002_evidence_table_shows_phase_classification_and_short_sha(tmp_path):
    md = render_pr_summary(make(tmp_path, records=[record("red", "failed", "behavioral_failure"), record("green")]))
    assert "behavioral_failure" in md and "green" in md
    assert SHA[:10] in md and SHA not in md


def test_ac003_missing_green_evidence_is_an_explicit_gap(tmp_path):
    md = render_pr_summary(make(tmp_path, records=[record("red", "failed", "behavioral_failure")]))
    assert "GAP" in md and "green" in md.lower()


def test_ac003_no_evidence_at_all_is_a_gap_not_success(tmp_path):
    md = render_pr_summary(make(tmp_path))
    assert "GAP" in md


def test_ac004_markup_in_untrusted_text_is_escaped(tmp_path):
    c = contract(title="<script>alert(1)</script> | x")
    md = render_pr_summary(make(tmp_path, c, [record("green", notes="<img src=x onerror=1>\nline2")]))
    assert "<script>" not in md and "<img" not in md
    assert "&lt;script&gt;" in md


def test_ac004_pipes_do_not_break_table_rows(tmp_path):
    c = contract(title="a | b")
    md = render_pr_summary(make(tmp_path, c, [record("green")]))
    assert "a \\| b" in md


@pytest.mark.parametrize("secret", [
    "ghp_" + "A" * 36,
    "sk-" + "b" * 40,
    "Bearer abcdef0123456789abcdef",
    "host.tailnet1234" + ".ts" + ".net",  # built at runtime so the repo-wide private-host grep stays clean
    "10.20.30.40",
    "192.168.1.5",
])
def test_ac005_secret_and_private_host_shapes_are_redacted(tmp_path, secret):
    md = render_pr_summary(make(tmp_path, records=[record("green", notes=f"see {secret} here")]))
    assert secret not in md
    assert "[redacted]" in md


def test_ac006_optional_sections_render_only_when_given(tmp_path):
    d = make(tmp_path, records=[record("green")])
    plain = render_pr_summary(d)
    assert "Risk" not in plain
    rich = render_pr_summary(d, risk={"tier": "high", "reasons": ["touches sandbox.py"]},
                             slop={"new": 0, "fixed": 2}, metrics={"retries": 1, "review_findings": 3})
    assert "high" in rich and "touches sandbox.py" in rich
    assert "retries" in rich.lower()


def test_ac007_output_is_deterministic(tmp_path):
    d = make(tmp_path, records=[record("red", "failed", "behavioral_failure"), record("green")])
    assert render_pr_summary(d) == render_pr_summary(d)


def test_ac008_malformed_json_is_a_gap_not_a_crash(tmp_path):
    d = make(tmp_path, records=[record("green")])
    (d / "W1-x.red.json").write_text("{broken")
    md = render_pr_summary(d)
    assert "GAP" in md and "red" in md.lower()
