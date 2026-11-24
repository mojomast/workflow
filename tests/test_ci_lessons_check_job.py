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

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "tools" / "lessons-check" / "README.md"


def load():
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def job():
    return load()["jobs"].get("lessons-check")


def run_text(j) -> str:
    return "\n".join(str(s.get("run", "")) for s in j.get("steps", []))


class TestLessonsCheckCiJob(unittest.TestCase):
    def test_job_exists_and_is_gated(self):
        jobs = load()["jobs"]
        self.assertIn("lessons-check", jobs)
        self.assertIn("lessons-check", jobs["ci-gate"]["needs"])
        proc = subprocess.run([sys.executable, str(ROOT / ".github" / "scripts" / "check_ci_gate.py"), str(CI)],
                              capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_findings_are_advisory_but_tool_failure_is_not(self):
        j = job()
        self.assertIsNotNone(j)
        text = run_text(j)
        self.assertRegex(text, r"python3 -m lessons_check check .*--report-only")
        self.assertIn("python3 -m unittest discover -s tests -t .", text)
        self.assertNotIn("continue-on-error", yaml.safe_dump(j))
        self.assertNotRegex(text, r"\|\|\s*true")
        self.assertNotRegex(text, r"set \+e")

    def test_report_goes_to_step_summary(self):
        self.assertIn("GITHUB_STEP_SUMMARY", run_text(job()))

    def test_job_is_hardened_like_the_others(self):
        j = job()
        self.assertEqual(j.get("permissions"), {"contents": "read"})
        self.assertIsInstance(j.get("timeout-minutes"), int)
        self.assertLessEqual(j["timeout-minutes"], 15)
        for step in j["steps"]:
            uses = step.get("uses")
            if uses:
                self.assertRegex(uses, r"@[0-9a-f]{40}$", f"unpinned action {uses}")
            if uses and uses.startswith("actions/checkout@"):
                self.assertIs(step.get("with", {}).get("persist-credentials"), False)

    def test_readme_no_longer_says_not_wired(self):
        text = README.read_text(encoding="utf-8")
        self.assertNotIn("It is not wired\ninto CI", text)
        self.assertNotIn("not wired into CI", re.sub(r"\s+", " ", text))
        self.assertIn("advisory", text.lower())
        self.assertIn("ci.yml", text)


if __name__ == "__main__":
    unittest.main()
