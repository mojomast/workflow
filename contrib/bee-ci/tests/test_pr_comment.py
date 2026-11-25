"""Approved acceptance tests for contrib/bee-ci/report/pr_comment.py (builds the fork-safe PR summary comment body).
Coordinator-written; do not edit."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parents[1] / "report"
sys.path.insert(0, str(REPORT_DIR))

import pr_comment  # noqa: E402

SHA = "a" * 40


def contract(cid="W1-x"):
    return {"contract_version": "acdd/1", "id": cid, "title": "Add the thing",
            "outcome": {"summary": "s", "observable_behavior": ["x"]},
            "acceptance_criteria": [{"id": "AC-001", "statement": "works", "verification": "test", "tests": ["t.py::T::a"]}]}


def evidence(phase):
    return {"evidence_version": "tdd-evidence/1", "contract_id": "W1-x", "phase": phase, "revision": SHA,
            "classification": "passed", "result": {"exit_code": 0, "tests": 1, "failures": 0, "errors": 0, "skipped": 0, "timed_out": False}}


def put(root, rel, obj):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))
    return rel


def test_ac001_pr_with_contract_and_evidence_gets_a_comment_starting_with_the_marker(tmp_path):
    files = [put(tmp_path, "ev/W1-x.contract.json", contract()), put(tmp_path, "ev/W1-x.red.json", evidence("red")),
             put(tmp_path, "ev/W1-x.green.json", evidence("green"))]
    body = pr_comment.build_comment(files, tmp_path)
    assert body is not None
    assert body.startswith(pr_comment.MARKER + "\n")
    assert "Add the thing" in body and "| red |" in body and "| green |" in body


def test_ac002_pr_without_both_contract_and_evidence_gets_no_comment(tmp_path):
    only_contract = [put(tmp_path, "ev/W1-x.contract.json", contract())]
    assert pr_comment.build_comment(only_contract, tmp_path) is None
    only_ev = [put(tmp_path, "ev/W1-x.red.json", evidence("red"))]
    assert pr_comment.build_comment(only_ev, tmp_path) is None
    assert pr_comment.build_comment(["README.md", "src/a.py"], tmp_path) is None
    assert pr_comment.build_comment([], tmp_path) is None


def test_ac003_contract_and_evidence_in_different_directories_do_not_qualify(tmp_path):
    files = [put(tmp_path, "a/W1-x.contract.json", contract()), put(tmp_path, "b/W1-x.red.json", evidence("red"))]
    assert pr_comment.build_comment(files, tmp_path) is None


def test_ac004_unsafe_paths_are_ignored(tmp_path):
    put(tmp_path, "ev/W1-x.contract.json", contract())
    put(tmp_path, "ev/W1-x.red.json", evidence("red"))
    unsafe = ["../ev/W1-x.contract.json", "/etc/ev/W1-x.contract.json", "ev/../ev/W1-x.red.json", "ev\\W1-x.red.json"]
    assert pr_comment.build_comment(unsafe, tmp_path) is None


def test_ac005_symlinked_inputs_are_ignored(tmp_path):
    put(tmp_path, "real/W1-x.contract.json", contract())
    put(tmp_path, "real/W1-x.red.json", evidence("red"))
    (tmp_path / "ev").mkdir()
    for n in ("W1-x.contract.json", "W1-x.red.json"):
        (tmp_path / "ev" / n).symlink_to(tmp_path / "real" / n)
    assert pr_comment.build_comment(["ev/W1-x.contract.json", "ev/W1-x.red.json"], tmp_path) is None


def test_ac006_body_is_capped_at_60000_bytes_and_keeps_the_marker(tmp_path):
    files = []
    for i in range(5):
        c = contract(f"W1-{i}")
        c["acceptance_criteria"] = [{"id": f"AC-{n:03d}", "statement": "x" * 280, "verification": "test", "tests": ["t.py::T::a"]} for n in range(1, 300)]
        files.append(put(tmp_path, f"d{i}/W1-{i}.contract.json", c))
        files.append(put(tmp_path, f"d{i}/W1-{i}.red.json", evidence("red")))
    body = pr_comment.build_comment(files, tmp_path)
    assert body is not None
    assert len(body.encode("utf-8")) <= 60000
    assert body.startswith(pr_comment.MARKER + "\n")
    assert "truncated" in body


def test_ac007_at_most_five_directories_are_summarised(tmp_path):
    files = []
    for i in range(8):
        files += [put(tmp_path, f"d{i}/W1-x.contract.json", contract()), put(tmp_path, f"d{i}/W1-x.red.json", evidence("red"))]
    body = pr_comment.build_comment(files, tmp_path)
    assert body.count("# Add the thing") <= 5


def run_cli(tmp_path, changed, pr, out):
    cf = tmp_path / "changed.txt"
    cf.write_text("\n".join(changed) + "\n")
    return subprocess.run([sys.executable, str(REPORT_DIR / "pr_comment.py"), "--root", str(tmp_path), "--changed-files", str(cf),
                           "--pr", pr, "--out", str(out)], capture_output=True, text=True, timeout=60)


def test_ac008_cli_writes_comment_and_pr_number_artifacts(tmp_path):
    files = [put(tmp_path, "ev/W1-x.contract.json", contract()), put(tmp_path, "ev/W1-x.red.json", evidence("red"))]
    out = tmp_path / "out"
    p = run_cli(tmp_path, files, "123", out)
    assert p.returncode == 0, p.stderr
    assert (out / "comment.md").read_text().startswith(pr_comment.MARKER)
    assert (out / "pr-number.txt").read_text().strip() == "123"


def test_ac009_cli_writes_nothing_when_no_contract_and_evidence(tmp_path):
    out = tmp_path / "out"
    p = run_cli(tmp_path, ["README.md"], "123", out)
    assert p.returncode == 0
    assert not (out / "comment.md").exists() and not (out / "pr-number.txt").exists()


def test_ac010_cli_rejects_a_non_numeric_pr_number_with_exit_2(tmp_path):
    out = tmp_path / "out"
    for bad in ("abc", "12;rm", "-1", "", "1" * 12):
        p = run_cli(tmp_path, ["README.md"], bad, out)
        assert p.returncode == 2, bad
        assert not out.exists() or not any(out.iterdir())
