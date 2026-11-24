"""Narrow diagnosis test for the CS-apply-tax cold-start acceptance failure.

At ``source_rev`` the approved tests must be collectable even though
``apply_tax`` does not exist yet. When the import sits at module scope, pytest
reports one collection error for the file, so bundlebees' ``tdd red`` cannot
match the contract's per-test ids, writes no evidence record, and the report
shows zero signed records. This module reproduces that condition and checks
that the harness input is collectable, red, and then green after the
implementation lands. It also keeps the review criterion intact.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acceptance import harness  # noqa: E402


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _toy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "shop"
    _write(repo, "shop/__init__.py", "")
    _write(repo, "shop/pricing.py", harness.PRICING)
    _write(repo, "tests/__init__.py", "")
    _write(repo, "tests/test_tax.py", harness.ACDD_TEST)
    return repo


def _pytest(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )


def _collected_ids(stdout: str) -> list[str]:
    return sorted(
        line.strip()
        for line in stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    )


def _contract_test_ids() -> list[str]:
    contract = harness._acdd_contract("a" * 40)
    return sorted(
        test
        for criterion in contract["acceptance_criteria"]
        for test in criterion.get("tests") or []
    )


def test_approved_tests_collect_at_red_and_match_the_contract_ids(tmp_path):
    repo = _toy_repo(tmp_path)

    collected = _pytest(repo, "--collect-only", "tests/test_tax.py")
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert _collected_ids(collected.stdout) == _contract_test_ids()


def test_approved_tests_fail_at_red_and_pass_with_the_implementation(tmp_path):
    repo = _toy_repo(tmp_path)

    red = _pytest(repo, "tests/test_tax.py")
    assert red.returncode != 0
    assert "2 failed" in red.stdout

    _write(repo, "shop/pricing.py", harness.ACDD_IMPL)
    green = _pytest(repo, "tests/test_tax.py")
    assert green.returncode == 0, green.stdout + green.stderr
    assert "2 passed" in green.stdout


def test_contract_keeps_the_review_criterion():
    contract = harness._acdd_contract("a" * 40)
    criteria = {criterion["id"]: criterion for criterion in contract["acceptance_criteria"]}
    assert criteria["AC-004"]["verification"] == "review"
    assert "review" in contract["evidence_required"]
