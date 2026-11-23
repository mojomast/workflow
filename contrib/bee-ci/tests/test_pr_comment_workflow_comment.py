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


class WorkflowB(unittest.TestCase):
    def test_b1_triggers_on_workflow_run_of_workflow_a_completed(self):
        t = text(B)
        self.assertIn("workflow_run:", t)
        self.assertRegex(t, r"workflows:\s*\[\s*[\"']?pr-summary-build[\"']?\s*\]")
        self.assertIn("completed", t)
        self.assertNotIn("pull_request_target", t)

    def test_b2_gated_on_pull_request_event_and_success(self):
        t = text(B)
        self.assertIn("github.event.workflow_run.event == 'pull_request'", t)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", t)

    def test_b3_least_privilege_permissions(self):
        p = perms(text(B))
        self.assertIn("pull-requests: write", p)
        self.assertIn("contents: read", p)
        self.assertIn("actions: read", p)
        self.assertNotRegex(p, r"(contents|actions|issues|packages|id-token): write")

    def test_b4_never_checks_out_code(self):
        t = text(B)
        self.assertNotIn("actions/checkout", t)
        self.assertNotIn("git clone", t)

    def test_b5_artifact_goes_to_runner_temp_and_not_github_env(self):
        t = text(B)
        self.assertIn("RUNNER_TEMP", t)
        self.assertNotIn("GITHUB_ENV", t)

    def test_b6_pr_number_is_validated_numeric_and_against_commit_associated_prs(self):
        t = text(B)
        self.assertRegex(t, r"\^\[0-9\]\{1,9\}\$")
        self.assertIn("head_sha", t)
        self.assertRegex(t, r"commits/.*pulls|listPullRequestsAssociatedWithCommit")

    def test_b7_comment_is_capped_at_60000_bytes_and_must_start_with_the_marker(self):
        t = text(B)
        self.assertIn("60000", t)
        self.assertIn("<!-- workflow-pr-summary:v1 -->", t)

    def test_b8_sticky_upsert_via_gh_api_without_third_party_actions(self):
        t = text(B)
        self.assertIn("gh api", t)
        self.assertRegex(t, r"issues/.*comments")
        self.assertRegex(t, r"-X PATCH|--method PATCH")
        self.assertNotRegex(t, r"(?m)^\s*-?\s*uses:\s*(?!actions/)")

    def test_b9_untrusted_values_reach_shell_only_through_env_not_expression_interpolation(self):
        t = text(B)
        for run in re.findall(r"(?ms)^\s*run:\s*[|>]?\s*(.*?)(?=^\s*-\s|\Z)", t):
            self.assertNotRegex(run, r"\$\{\{")

    def test_b10_every_action_is_pinned_and_job_is_bounded(self):
        t = text(B)
        for u in re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", t):
            self.assertRegex(u, r"@[0-9a-f]{40}$", u)
        m = re.search(r"timeout-minutes:\s*(\d+)", t)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 10)



if __name__ == "__main__":
    unittest.main()
