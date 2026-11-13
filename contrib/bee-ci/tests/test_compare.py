"""Hermetic tests for the bee-CI / GitHub Actions shadow comparison.

Every input is a hand-written fixture; nothing here touches the network,
git, GitHub, or a real bee run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BEE_CI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BEE_CI))

import compare  # noqa: E402

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
SHA_E = "e" * 40
SHA_F = "f" * 40
SHA_G = "0" * 40
SHA_H = "1" * 40
SHA_I = "2" * 40

BEE_FIXTURE = {
    "source": "bee-ci",
    "records": [
        {"sha": SHA_A, "job": "unit", "state": "passed", "exit_code": 0},
        {"sha": SHA_A, "job": "lint", "state": "failed", "exit_code": 1},
        # No matching GitHub Actions conclusion at all.
        {"sha": SHA_B, "job": "unit", "state": "passed", "exit_code": 0},
        # bee failed, Actions passed.
        {"sha": SHA_C, "job": "unit", "state": "failed", "exit_code": 2},
        # bee passed, Actions failed.
        {"sha": SHA_D, "job": "unit", "state": "passed", "exit_code": 0},
        {"sha": SHA_E, "job": "unit", "state": "passed", "exit_code": 0},
        # bee has no usable result, Actions passed: must not be a pass.
        {"sha": SHA_F, "job": "unit", "state": "unknown"},
        # State missing but a recorded exit code says the job passed.
        {"sha": SHA_G, "job": "unit", "exit_code": 0},
        # Contradictory bee record: state says passed, exit code says failed.
        {"sha": SHA_H, "job": "unit", "state": "passed", "exit_code": 1},
    ],
}

ACTIONS_FIXTURE = {
    "source": "github-actions",
    "records": [
        {"sha": SHA_A, "job": "unit", "conclusion": "success"},
        {"sha": SHA_A, "job": "lint", "conclusion": "failure"},
        {"sha": SHA_C, "job": "unit", "conclusion": "success"},
        {"sha": SHA_D, "job": "unit", "conclusion": "failure"},
        {"sha": SHA_F, "job": "unit", "conclusion": "success"},
        {"sha": SHA_G, "job": "unit", "conclusion": "success"},
        {"sha": SHA_H, "job": "unit", "conclusion": "success"},
        # No matching bee result at all.
        {"sha": SHA_I, "job": "unit", "conclusion": "success"},
        # A cancelled conclusion is not a pass.
        {"sha": SHA_A, "job": "docs", "conclusion": "cancelled"},
    ],
}


def _kinds(report):
    return {(row["sha"], row["job"]): row["kind"] for row in report["disagreements"]}


def test_disagreements():
    report = compare.compare(BEE_FIXTURE, ACTIONS_FIXTURE)
    kinds = _kinds(report)

    assert kinds[(SHA_C, "unit")] == "bee-failed-actions-passed"
    assert kinds[(SHA_D, "unit")] == "bee-passed-actions-failed"
    assert kinds[(SHA_B, "unit")] == "missing-actions"
    assert kinds[(SHA_E, "unit")] == "missing-actions"
    assert kinds[(SHA_I, "unit")] == "missing-bee"

    # Anything without a bee record is missing on that side, never a pass.
    assert kinds[(SHA_A, "docs")] == "missing-bee"

    assert report["summary"]["bee_failed_actions_passed"] == 1
    assert report["summary"]["bee_passed_actions_failed"] == 1
    assert report["summary"]["missing_actions"] == 2
    assert report["summary"]["missing_bee"] == 2
    assert report["summary"]["disagreements"] == 8
    assert report["summary"]["total"] == 11

    for row in report["disagreements"]:
        assert row["verdict"] == "disagree"


def test_agreements_and_inconclusive_are_not_passes():
    report = compare.compare(BEE_FIXTURE, ACTIONS_FIXTURE)
    kinds = _kinds(report)

    assert (SHA_A, "unit") not in kinds
    assert (SHA_A, "lint") not in kinds
    assert (SHA_G, "unit") not in kinds
    assert report["summary"]["agreements"] == 3

    # A missing/unknown bee state is inconclusive even when Actions passed.
    assert kinds[(SHA_F, "unit")] == "inconclusive"
    # A bee record that contradicts itself is inconclusive, not a pass.
    assert kinds[(SHA_H, "unit")] == "inconclusive"
    assert report["summary"]["inconclusive"] == 2

    for row in report["rows"]:
        if not row["bee"]["present"] or not row["actions"]["present"]:
            assert row["verdict"] != "agree"


def test_exact_sha_match_only():
    bee = {"records": [{"sha": "abc123", "job": "unit", "state": "passed", "exit_code": 0}]}
    actions = {"records": [{"sha": "abc1234", "job": "unit", "conclusion": "success"}]}
    report = compare.compare(bee, actions)

    assert report["summary"]["agreements"] == 0
    assert _kinds(report) == {
        ("abc123", "unit"): "missing-actions",
        ("abc1234", "unit"): "missing-bee",
    }


def test_deterministic_output():
    first = compare.compare(BEE_FIXTURE, ACTIONS_FIXTURE)
    second = compare.compare(BEE_FIXTURE, ACTIONS_FIXTURE)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert compare.render_markdown(first) == compare.render_markdown(second)

    keys = [(row["sha"], row["job"]) for row in first["rows"]]
    assert keys == sorted(keys)


def test_json_fixtures_via_load_and_cli(tmp_path):
    bee_path = tmp_path / "bee.json"
    actions_path = tmp_path / "actions.json"
    out_path = tmp_path / "report.json"
    bee_path.write_text(json.dumps(BEE_FIXTURE), encoding="utf-8")
    actions_path.write_text(json.dumps(ACTIONS_FIXTURE), encoding="utf-8")

    assert compare.load_json(bee_path) == BEE_FIXTURE
    assert compare.main(["--bee", str(bee_path), "--actions", str(actions_path), "--out", str(out_path)]) == 0

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["summary"]["disagreements"] == 8
    assert written["schema_version"] == 1


def test_markdown_report_names_every_disagreement():
    report = compare.compare(BEE_FIXTURE, ACTIONS_FIXTURE)
    text = compare.render_markdown(report)

    for sha, job in [
        (SHA_C, "unit"),
        (SHA_D, "unit"),
        (SHA_B, "unit"),
        (SHA_E, "unit"),
        (SHA_I, "unit"),
        (SHA_F, "unit"),
        (SHA_H, "unit"),
    ]:
        assert sha in text
        assert job in text
    assert "bee-failed-actions-passed" in text
    assert "bee-passed-actions-failed" in text
    assert "missing-actions" in text
    assert "missing-bee" in text


def test_invalid_payload_is_rejected():
    with pytest.raises(compare.CompareError):
        compare.compare({"source": "bee-ci", "records": [{"sha": SHA_A, "state": "passed"}]}, ACTIONS_FIXTURE)
    with pytest.raises(compare.CompareError):
        compare.compare(BEE_FIXTURE, {"records": [{"sha": SHA_A, "job": "unit", "conclusion": 3}]})
