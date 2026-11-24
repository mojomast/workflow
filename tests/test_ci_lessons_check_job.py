"""Approved tests (T1-LESSONS): lessons-check runs in CI as an ADVISORY job.

Advisory means: findings never fail the job (``--report-only``), but a broken
tool still does (exit 2 and failing unit tests are not swallowed). The job is
listed in ci-gate's needs like every other job (check_ci_gate.py), never uses
continue-on-error, pins actions by SHA, and writes its findings to the step
summary so the report is visible.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from check_ci_gate import gate_needs, job_blocks  # noqa: E402  (stdlib parser; no PyYAML on the runner)
CI = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "tools" / "lessons-check" / "README.md"


def blocks():
    return job_blocks(CI.read_text(encoding="utf-8").splitlines())


def job():
    return blocks().get("lessons-check")


def run_text(j) -> str:
    return "\n".join(j)


class TestLessonsCheckCiJob(unittest.TestCase):
    def test_job_exists_and_is_gated(self):
        jobs = blocks()
        self.assertIn("lessons-check", jobs)
        self.assertIn("lessons-check", gate_needs(jobs["ci-gate"]))
        proc = subprocess.run([sys.executable, str(ROOT / ".github" / "scripts" / "check_ci_gate.py"), str(CI)],
                              capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_findings_are_advisory_but_tool_failure_is_not(self):
        j = job()
        self.assertIsNotNone(j)
        text = run_text(j)
        self.assertRegex(text, r"python3 -m lessons_check check .*--report-only")
        self.assertIn("python3 -m unittest discover -s tests -t .", text)
        self.assertNotIn("continue-on-error", text)
        self.assertNotRegex(text, r"\|\|\s*true")
        self.assertNotRegex(text, r"set \+e")

    def test_report_goes_to_step_summary(self):
        self.assertIn("GITHUB_STEP_SUMMARY", run_text(job()))

    def test_job_is_hardened_like_the_others(self):
        j = job()
        self.assertIsNotNone(j)
        text = run_text(j)
        self.assertRegex(text, r"(?m)^    permissions:\s*\n      contents: read\s*$")
        minutes = re.search(r"(?m)^    timeout-minutes:\s*(\d+)\s*$", text)
        self.assertIsNotNone(minutes)
        self.assertLessEqual(int(minutes.group(1)), 15)
        uses = re.findall(r"uses:\s*(\S+)", text)
        self.assertTrue(uses)
        for ref in uses:
            self.assertRegex(ref, r"@[0-9a-f]{40}$", f"unpinned action {ref}")
        if any(u.startswith("actions/checkout@") for u in uses):
            self.assertIn("persist-credentials: false", text)

    def test_readme_no_longer_says_not_wired(self):
        text = README.read_text(encoding="utf-8")
        self.assertNotIn("It is not wired\ninto CI", text)
        self.assertNotIn("not wired into CI", re.sub(r"\s+", " ", text))
        self.assertIn("advisory", text.lower())
        self.assertIn("ci.yml", text)


if __name__ == "__main__":
    unittest.main()
