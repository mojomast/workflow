"""Approved acceptance tests for the fork-safe PR summary comment workflows. Coordinator-written; do not edit."""
import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parents[3] / ".github" / "workflows"
A = WF / "pr-summary-build.yml"
B = WF / "pr-summary-comment.yml"


def text(p):
    assert p.is_file(), f"{p.name} missing"
    return p.read_text()


def perms(t):
    m = re.search(r"(?m)^permissions:\s*\n((?:[ \t]+.*\n)+)", t)
    assert m, "top-level permissions block required"
    return m.group(1)


class WorkflowA(unittest.TestCase):
    def test_a1_runs_on_pull_request_only_with_read_only_permissions(self):
        t = text(A)
        self.assertIn("pull_request:", t)
        self.assertNotIn("pull_request_target", t)
        self.assertNotIn("workflow_run", t)
        p = perms(t)
        self.assertIn("contents: read", p)
        self.assertNotIn("write", p)

    def test_a2_has_no_secrets_and_no_job_level_permission_elevation(self):
        t = text(A)
        self.assertNotIn("secrets.", t)
        self.assertNotRegex(t, r"(?m)^\s{4,}permissions:")

    def test_a3_every_action_is_pinned_to_a_full_sha(self):
        uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", text(A))
        self.assertTrue(uses)
        for u in uses:
            self.assertRegex(u, r"@[0-9a-f]{40}$", u)

    def test_a4_runs_the_pr_comment_script_and_uploads_a_named_artifact(self):
        t = text(A)
        self.assertIn("contrib/bee-ci/report/pr_comment.py", t)
        self.assertIn("--changed-files", t)
        self.assertIn("actions/upload-artifact@", t)
        self.assertRegex(t, r"name:\s*pr-summary\b")
        self.assertIn("if-no-files-found: ignore", t)

    def test_a5_is_bounded_and_does_not_interpolate_pr_text_into_shell(self):
        t = text(A)
        m = re.search(r"timeout-minutes:\s*(\d+)", t)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 10)
        for run in re.findall(r"(?ms)^\s*run:\s*[|>]?\s*(.*?)(?=^\s*-\s|\Z)", t):
            self.assertNotRegex(run, r"\$\{\{\s*github\.(head_ref|event\.pull_request\.(title|body|head))")

    def test_a6_workflow_name_is_the_one_workflow_b_listens_for(self):
        self.assertRegex(text(A), r"(?m)^name:\s*pr-summary-build\s*$")



if __name__ == "__main__":
    unittest.main()
