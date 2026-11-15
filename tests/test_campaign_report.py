import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import campaign_report  # noqa: E402

try:  # optional cross-check; the semantic validator is stdlib-only.
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

EXAMPLE = ROOT / "schemas" / "examples" / "campaign-report.example.json"
SCHEMA = ROOT / "schemas" / "campaign-report.schema.json"


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class ValidReportTests(unittest.TestCase):
    def test_the_example_validates(self):
        report = campaign_report.validate(example())
        self.assertEqual(report["campaign_id"], "jackpot-2026-11")
        self.assertEqual(report["receiver_decision"], "pending")
        self.assertEqual(report["task_graph"]["implemented"], 27)

    def test_validate_returns_a_detached_copy(self):
        original = example()
        validated = campaign_report.validate(original)
        validated["acceptance"][0]["status"] = "FAIL"
        self.assertEqual(original["acceptance"][0]["status"], "PASS")

    def test_the_schema_describes_the_same_root_shape(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema"]["const"], campaign_report.SCHEMA)
        self.assertEqual(
            set(schema["required"]),
            {
                "schema",
                "campaign_id",
                "repository",
                "branch",
                "base_rev",
                "head_rev",
                "generated_at",
                "delivery_state",
                "task_graph",
                "pull_requests",
                "acceptance",
                "test_runs",
                "not_run",
                "known_limits",
                "receiver_decision",
                "recommended_merge_order",
            },
        )

    @unittest.skipUnless(jsonschema is not None, "jsonschema is optional")
    def test_the_example_cross_checks_against_json_schema(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(example(), schema)


class RefusalTests(unittest.TestCase):
    def assert_refused(self, report, code):
        with self.assertRaises(campaign_report.CampaignReportError) as caught:
            campaign_report.validate(report)
        self.assertEqual(caught.exception.code, code)

    def test_pass_without_evidence_is_refused(self):
        report = example()
        report["acceptance"][0]["evidence"] = []
        self.assert_refused(report, "campaign_acceptance_pass_without_evidence")

    def test_a_passing_test_without_a_command_is_refused(self):
        report = example()
        del report["acceptance"][0]["command"]
        self.assert_refused(report, "campaign_acceptance_command")

    def test_a_not_run_criterion_needs_a_reason(self):
        report = example()
        del report["acceptance"][2]["reason"]
        self.assert_refused(report, "campaign_acceptance_reason")

    def test_an_agent_cannot_fill_the_receiver_decision(self):
        report = example()
        report["receiver_decision"] = "accepted"
        self.assert_refused(report, "campaign_receiver_decision")

    def test_ready_cannot_hide_a_failed_criterion(self):
        report = example()
        report["acceptance"][0]["status"] = "FAIL"
        self.assert_refused(report, "campaign_ready_with_blocker")

    def test_ready_cannot_hide_an_unverified_criterion(self):
        report = example()
        report["acceptance"][1]["status"] = "UNVERIFIED"
        report["acceptance"][1]["reason"] = "No browser was run."
        self.assert_refused(report, "campaign_ready_with_blocker")

    def test_ready_cannot_have_a_failed_test_run(self):
        report = example()
        report["test_runs"][0]["failed"] = 1
        self.assert_refused(report, "campaign_test_failed")

    def test_ready_needs_at_least_one_test_run(self):
        report = example()
        report["test_runs"] = []
        self.assert_refused(report, "campaign_test_runs")

    def test_unrun_checks_need_known_limits(self):
        report = example()
        report["known_limits"] = []
        self.assert_refused(report, "campaign_limits_required")

    def test_duplicate_acceptance_ids_are_refused(self):
        report = example()
        report["acceptance"][1]["id"] = "AC-001"
        self.assert_refused(report, "campaign_acceptance_duplicate")

    def test_duplicate_pull_requests_are_refused(self):
        report = example()
        report["pull_requests"].append(copy.deepcopy(report["pull_requests"][0]))
        self.assert_refused(report, "campaign_pr_duplicate")

    def test_merge_order_must_name_open_pull_requests(self):
        report = example()
        report["recommended_merge_order"] = [99]
        self.assert_refused(report, "campaign_merge_order")

    def test_task_counts_must_be_ordered(self):
        report = example()
        report["task_graph"]["integrated"] = 28
        self.assert_refused(report, "campaign_task_graph")

    def test_remaining_must_match_the_total(self):
        report = example()
        report["task_graph"]["remaining"] = 1
        self.assert_refused(report, "campaign_task_graph")

    def test_a_revision_must_be_full_length(self):
        report = example()
        report["head_rev"] = "794318a"
        self.assert_refused(report, "campaign_revision")

    def test_delivery_state_is_closed(self):
        report = example()
        report["delivery_state"] = "done"
        self.assert_refused(report, "campaign_delivery_state")

    def test_private_host_paths_are_refused(self):
        report = example()
        report["acceptance"][0]["evidence"] = ["/home/alice/artifacts/test.log"]
        self.assert_refused(report, "campaign_secret")

    def test_secret_values_are_refused(self):
        report = example()
        report["known_limits"].append("token ghp_abcdefghijklmnopqrstuvwxyz")
        self.assert_refused(report, "campaign_secret")

    def test_bad_json_is_refused_with_a_named_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(campaign_report.CampaignReportError) as caught:
                campaign_report.load(path)
        self.assertEqual(caught.exception.code, "campaign_invalid")


class CliTests(unittest.TestCase):
    def test_valid_cli_exits_zero(self):
        self.assertEqual(campaign_report.main(["validate", str(EXAMPLE)]), 0)

    def test_invalid_cli_exits_one(self):
        report = example()
        report["receiver_decision"] = "accepted"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(campaign_report.main(["validate", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
