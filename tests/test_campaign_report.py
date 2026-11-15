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


def pull_request(number, *, state="open", merge_order=None, head_sha=None):
    entry = {
        "number": number,
        "url": f"https://github.com/example/repo/pull/{number}",
        "draft": True,
        "state": state,
        "base": "main",
        "head_sha": head_sha or "b" * 40,
    }
    if merge_order is not None:
        entry["merge_order"] = merge_order
    return entry


def audit(*, status="findings", head_sha: str | None = "b" * 40, findings=None, reason=None):
    entry = {
        "source": "Independent read-only review",
        "status": status,
        "findings": [] if findings is None else findings,
    }
    if head_sha is not None:
        entry["head_sha"] = head_sha
    if reason is not None:
        entry["reason"] = reason
    return entry


def fixed_finding(finding_id="AF-001"):
    return {
        "id": finding_id,
        "summary": "A real defect was found and repaired.",
        "disposition": "fixed",
        "evidence": "evidence/audit-001.md",
    }


class RefusalMixin(unittest.TestCase):
    def assert_refused(self, report, code):
        with self.assertRaises(campaign_report.CampaignReportError) as caught:
            campaign_report.validate(report)
        self.assertEqual(caught.exception.code, code)
        return caught.exception



class ValidReportTests(unittest.TestCase):
    def test_the_example_validates(self):
        report = campaign_report.validate(example())
        self.assertEqual(report["campaign_id"], "example-campaign")
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


class RefusalTests(RefusalMixin):
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

    def test_passing_evidence_must_be_a_reference(self):
        report = example()
        report["acceptance"][0]["evidence"] = ["TODO"]
        self.assert_refused(report, "campaign_evidence")

    def test_passing_evidence_cannot_be_an_empty_label(self):
        report = example()
        report["acceptance"][0]["evidence"] = ["see the report"]
        self.assert_refused(report, "campaign_evidence")

    def test_a_passing_criterion_must_name_the_final_head(self):
        report = example()
        del report["acceptance"][0]["head_sha"]
        self.assert_refused(report, "campaign_acceptance_head")

    def test_a_passing_criterion_cannot_use_an_older_head(self):
        report = example()
        report["acceptance"][0]["head_sha"] = "c" * 40
        self.assert_refused(report, "campaign_acceptance_revision")

    def test_ready_campaign_test_runs_must_be_at_the_final_head(self):
        report = example()
        report["test_runs"][0]["head_sha"] = "c" * 40
        self.assert_refused(report, "campaign_test_head")

    def test_each_audit_finding_needs_one_disposition(self):
        report = example()
        del report["audits"][0]["findings"][0]["disposition"]
        self.assert_refused(report, "campaign_audit_disposition")

    def test_rejected_and_deferred_findings_need_a_reason(self):
        report = example()
        del report["audits"][0]["findings"][1]["reason"]
        self.assert_refused(report, "campaign_audit_reason")

    def test_audit_finding_ids_must_be_unique(self):
        report = example()
        report["audits"][0]["findings"][1]["id"] = "AF-001"
        self.assert_refused(report, "campaign_audit_duplicate")

    def test_audit_finding_ids_must_be_stable_looking(self):
        report = example()
        report["audits"][0]["findings"][0]["id"] = "finding-one"
        self.assert_refused(report, "campaign_audit_id")

    def test_legacy_disposition_arrays_are_refused(self):
        report = example()
        report["audits"][0]["fixed"] = ["a free-text disposition"]
        self.assert_refused(report, "campaign_audit_legacy")

    def test_audit_finding_evidence_is_a_reference(self):
        report = example()
        report["audits"][0]["findings"][0]["evidence"] = "see the notes"
        self.assert_refused(report, "campaign_evidence")

    def test_a_ready_audit_must_be_at_the_final_head(self):
        report = example()
        report["audits"][0]["head_sha"] = "c" * 40
        self.assert_refused(report, "campaign_audit_head")

    def test_a_ready_audit_must_name_a_head(self):
        report = example()
        del report["audits"][0]["head_sha"]
        self.assert_refused(report, "campaign_audit_head")

    def test_a_zero_count_test_run_is_not_a_run(self):
        report = example()
        report["test_runs"][0].update(passed=0, failed=0, skipped=0)
        self.assert_refused(report, "campaign_test_runs")

    def test_placeholder_path_segments_are_refused(self):
        report = example()
        report["acceptance"][0]["evidence"] = ["evidence/TODO"]
        self.assert_refused(report, "campaign_evidence")

    def test_evidence_cannot_escape_the_repository(self):
        report = example()
        report["acceptance"][0]["evidence"] = ["../../secrets/vault.txt"]
        self.assert_refused(report, "campaign_evidence")

    def test_credentialed_evidence_urls_are_refused(self):
        report = example()
        report["acceptance"][0]["evidence"] = ["https://user:pass@example.com/run.log"]
        self.assert_refused(report, "campaign_secret")

    def test_artifacts_use_the_same_evidence_contract(self):
        report = example()
        report["artifacts"]["screenshots"] = ["TODO"]
        self.assert_refused(report, "campaign_evidence")

    def test_a_position_must_match_the_recommended_order(self):
        report = example()
        report["pull_requests"][0]["merge_order"] = 2
        self.assert_refused(report, "campaign_merge_order_position")

    def test_timestamps_must_parse(self):
        report = example()
        report["generated_at"] = "2026-99-99T99:99:99Z"
        self.assert_refused(report, "campaign_invalid")

    def test_a_secret_in_an_unknown_key_is_still_refused(self):
        report = example()
        report["api_token"] = "sk-" + "a" * 24
        self.assert_refused(report, "campaign_secret")

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
        report["acceptance"][0]["reason"] = "/home/alice/artifacts/test.log"
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


    def test_ready_needs_at_least_one_pass(self):
        report = example()
        for criterion in report["acceptance"]:
            criterion["status"] = "NOT RUN"
            criterion["reason"] = "not run"
        report["not_run"] = [
            {"check": f"{criterion['id']}: {criterion['statement']}", "reason": "not run"}
            for criterion in report["acceptance"]
        ]
        self.assert_refused(report, "campaign_ready_without_pass")

    def test_visual_pass_needs_an_image_or_recording(self):
        report = example()
        report["acceptance"][1]["evidence"] = ["docs/30-campaign-closeout.md"]
        self.assert_refused(report, "campaign_evidence_kind")


class MergeOrderTests(RefusalMixin):
    """`merge_order` is a 1..N position; `recommended_merge_order` lists PR numbers."""

    def test_a_low_pr_number_can_merge_first(self):
        # THE DEFECT: PR #2 in position 1 is normal work, not a contradiction.
        report = example()
        report["pull_requests"] = [pull_request(2, merge_order=1)]
        report["recommended_merge_order"] = [2]
        validated = campaign_report.validate(report)
        self.assertEqual(validated["recommended_merge_order"], [2])
        self.assertEqual(validated["pull_requests"][0]["merge_order"], 1)

    def test_nonconsecutive_pr_numbers_are_allowed(self):
        report = example()
        report["pull_requests"] = [
            pull_request(7, merge_order=1),
            pull_request(2, merge_order=2),
        ]
        report["recommended_merge_order"] = [7, 2]
        self.assertEqual(campaign_report.validate(report)["recommended_merge_order"], [7, 2])

    def test_a_contradictory_order_is_refused(self):
        # THE OTHER DEFECT: positions say #1 first, the list says #2 first.
        report = example()
        report["pull_requests"] = [
            pull_request(1, merge_order=1),
            pull_request(2, merge_order=2),
        ]
        report["recommended_merge_order"] = [2, 1]
        self.assert_refused(report, "campaign_merge_order")

    def test_duplicate_positions_are_refused(self):
        report = example()
        report["pull_requests"] = [
            pull_request(1, merge_order=1),
            pull_request(2, merge_order=2),
            pull_request(3, merge_order=2),
        ]
        report["recommended_merge_order"] = [1, 2, 3]
        self.assert_refused(report, "campaign_merge_order_duplicate")

    def test_position_gaps_are_refused(self):
        report = example()
        report["pull_requests"] = [
            pull_request(1, merge_order=1),
            pull_request(2, merge_order=3),
        ]
        report["recommended_merge_order"] = [1, 2]
        self.assert_refused(report, "campaign_merge_order_position")

    def test_an_open_pr_without_a_position_is_refused(self):
        report = example()
        report["pull_requests"] = [pull_request(1, merge_order=1), pull_request(2)]
        report["recommended_merge_order"] = [1, 2]
        self.assert_refused(report, "campaign_merge_order_missing")

    def test_a_closed_pr_cannot_carry_a_position(self):
        report = example()
        report["pull_requests"] = [
            pull_request(1, merge_order=1),
            pull_request(2, state="merged", merge_order=2),
        ]
        report["recommended_merge_order"] = [1]
        self.assert_refused(report, "campaign_merge_order_state")

    def test_a_closed_pr_cannot_carry_an_explicit_null_position(self):
        report = example()
        report["pull_requests"] = [
            pull_request(1, merge_order=1),
            pull_request(2, state="closed"),
        ]
        report["pull_requests"][1]["merge_order"] = None
        report["recommended_merge_order"] = [1]
        self.assert_refused(report, "campaign_merge_order_state")

    def test_a_closed_pr_cannot_appear_in_the_recommended_order(self):
        report = example()
        report["pull_requests"] = [pull_request(1, merge_order=1), pull_request(2, state="closed")]
        report["recommended_merge_order"] = [1, 2]
        self.assert_refused(report, "campaign_merge_order")

    def test_an_all_merged_report_has_an_empty_recommended_order(self):
        report = example()
        report["pull_requests"] = [
            pull_request(1, state="merged"),
            pull_request(4, state="closed"),
        ]
        report["recommended_merge_order"] = []
        self.assertEqual(campaign_report.validate(report)["recommended_merge_order"], [])

    def test_an_empty_recommended_order_cannot_hide_an_open_pr(self):
        report = example()
        report["pull_requests"] = [pull_request(3, merge_order=1)]
        report["recommended_merge_order"] = []
        self.assert_refused(report, "campaign_merge_order")

    def test_recommended_order_must_name_positive_pr_numbers(self):
        report = example()
        report["recommended_merge_order"] = [0]
        self.assert_refused(report, "campaign_merge_order")

    def test_recommended_order_cannot_repeat_a_pr_number(self):
        report = example()
        report["recommended_merge_order"] = [1, 1]
        self.assert_refused(report, "campaign_merge_order_duplicate")


class AuditStatusTests(RefusalMixin):
    """A completed audit with zero findings is `clean`, not an invented finding."""

    def test_a_clean_audit_with_no_findings_passes(self):
        report = example()
        report["audits"] = [audit(status="clean")]
        validated = campaign_report.validate(report)
        self.assertEqual(validated["audits"][0]["status"], "clean")
        self.assertEqual(validated["audits"][0]["findings"], [])
        self.assertEqual(validated["audits"][0]["head_sha"], "b" * 40)

    def test_a_findings_audit_keeps_its_findings_and_dispositions(self):
        report = example()
        report["audits"] = [audit(status="findings", findings=[fixed_finding()])]
        validated = campaign_report.validate(report)
        self.assertEqual(validated["audits"][0]["findings"][0]["disposition"], "fixed")

    def test_a_not_run_audit_is_recorded_as_not_run(self):
        report = example()
        report["audits"] = [
            audit(status="findings", findings=[fixed_finding()]),
            audit(status="not_run", head_sha=None, reason="The coverage audit needs a tool the host lacks."),
        ]
        validated = campaign_report.validate(report)
        self.assertEqual([item["status"] for item in validated["audits"]], ["findings", "not_run"])

    def test_an_audit_needs_a_status(self):
        report = example()
        del report["audits"][0]["status"]
        self.assert_refused(report, "campaign_audit_status")

    def test_an_unknown_audit_status_is_refused(self):
        report = example()
        report["audits"][0]["status"] = "done"
        self.assert_refused(report, "campaign_audit_status")

    def test_a_clean_audit_cannot_carry_findings(self):
        report = example()
        report["audits"][0]["status"] = "clean"
        self.assert_refused(report, "campaign_audit_clean")

    def test_a_clean_audit_needs_a_head(self):
        report = example()
        report["audits"] = [audit(status="clean", head_sha=None)]
        self.assert_refused(report, "campaign_audit_head")

    def test_a_clean_audit_at_a_stale_head_is_refused(self):
        report = example()
        report["audits"] = [audit(status="clean", head_sha="c" * 40)]
        self.assert_refused(report, "campaign_audit_head")

    def test_a_findings_audit_needs_findings(self):
        report = example()
        report["audits"] = [audit(status="findings")]
        self.assert_refused(report, "campaign_audit_findings")

    def test_a_not_run_audit_needs_a_reason(self):
        report = example()
        report["audits"] = [audit(status="not_run", head_sha=None)]
        self.assert_refused(report, "campaign_audit_reason")

    def test_a_not_run_audit_cannot_carry_findings(self):
        report = example()
        report["audits"][0]["status"] = "not_run"
        report["audits"][0]["reason"] = "Not run on this host."
        self.assert_refused(report, "campaign_audit_not_run")

    def test_a_ready_campaign_needs_an_audit_that_ran(self):
        report = example()
        report["audits"] = [audit(status="not_run", head_sha=None, reason="No audit was run.")]
        self.assert_refused(report, "campaign_audit_missing")

    def test_a_ready_campaign_needs_a_recorded_audit(self):
        report = example()
        report["audits"] = []
        self.assert_refused(report, "campaign_audit_missing")

    def test_a_not_run_audit_must_be_disclosed_in_known_limits(self):
        report = example()
        report["audits"] = [
            audit(status="findings", findings=[fixed_finding()]),
            audit(status="not_run", head_sha=None, reason="The coverage audit needs an unavailable tool."),
        ]
        report["known_limits"] = []
        self.assert_refused(report, "campaign_limits_required")


class NotRunDisclosureTests(RefusalMixin):
    def test_a_not_run_criterion_must_be_named_in_not_run(self):
        report = example()
        report["not_run"] = [
            entry for entry in report["not_run"] if "AC-003" not in entry["check"]
        ]
        self.assert_refused(report, "campaign_not_run_consistency")

    def test_a_free_text_not_run_entry_is_still_allowed(self):
        report = example()
        report["not_run"].append({"check": "Full WebKit journey suite", "reason": "No runnable WebKit."})
        campaign_report.validate(report)


class MetricTests(RefusalMixin):
    def test_a_nan_metric_value_is_refused(self):
        report = example()
        report["artifacts"]["performance"][0]["value"] = float("nan")
        self.assert_refused(report, "campaign_metric")

    def test_an_infinite_budget_is_refused(self):
        report = example()
        report["artifacts"]["performance"][0]["budget"] = float("inf")
        self.assert_refused(report, "campaign_metric")

    def test_a_bool_metric_value_is_refused(self):
        report = example()
        report["artifacts"]["performance"][0]["value"] = True
        self.assert_refused(report, "campaign_metric")

    def test_a_nan_in_the_source_json_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(
                json.dumps(example()).replace('"value": 1.9', '"value": NaN'),
                encoding="utf-8",
            )
            with self.assertRaises(campaign_report.CampaignReportError) as caught:
                campaign_report.load(path)
        self.assertEqual(caught.exception.code, "campaign_invalid")

    def test_a_budget_has_no_enforced_direction(self):
        # A budget may be a ceiling (latency) or a floor (throughput); the unit
        # and the contract define the direction, so the validator records it.
        report = example()
        report["artifacts"]["performance"][0].update(value=4.0, budget=3.0)
        validated = campaign_report.validate(report)
        self.assertEqual(validated["artifacts"]["performance"][0]["budget"], 3.0)


class UnknownFieldTests(RefusalMixin):
    def test_an_unknown_root_field_is_refused(self):
        report = example()
        report["extra_notes"] = "not in the schema"
        self.assert_refused(report, "campaign_invalid")

    def test_an_unknown_pull_request_field_is_refused(self):
        report = example()
        report["pull_requests"][0]["label"] = "merge-queue"
        self.assert_refused(report, "campaign_invalid")

    def test_an_unknown_acceptance_field_is_refused(self):
        report = example()
        report["acceptance"][0]["owner"] = "nobody"
        self.assert_refused(report, "campaign_invalid")


class AcceptanceTestRunTests(RefusalMixin):
    def test_a_pass_cannot_contradict_a_failed_run_of_the_same_command(self):
        report = example()
        report["delivery_state"] = "incomplete"
        report["test_runs"][0]["failed"] = 1
        self.assert_refused(report, "campaign_acceptance_test_run")

    def test_a_pass_may_name_a_command_that_was_not_the_full_run(self):
        report = example()
        report["acceptance"][0]["command"] = "pnpm test --filter acceptance"
        campaign_report.validate(report)

    def test_a_later_green_rerun_supersedes_an_earlier_red_run(self):
        # An incomplete report may honestly record a failed attempt and a green
        # rerun of the same command. The latest run is the current result.
        report = example()
        report["delivery_state"] = "incomplete"
        report["test_runs"][0]["failed"] = 1
        report["test_runs"].append({
            **report["test_runs"][0],
            "failed": 0,
            "passed": report["test_runs"][0]["passed"] + 1,
            "ran_at": "2026-11-15T09:30:00Z",
        })
        campaign_report.validate(report)


@unittest.skipUnless(jsonschema is not None, "jsonschema is optional")
class SchemaParityTests(unittest.TestCase):
    """The JSON Schema and the semantic validator must agree on shape."""

    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def assert_schema_refuses(self, report):
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(report, self.schema)

    def test_a_free_text_ran_at_is_refused(self):
        report = example()
        report["test_runs"][0]["ran_at"] = "yesterday"
        self.assert_schema_refuses(report)

    def test_a_placeholder_screenshot_is_refused(self):
        report = example()
        report["artifacts"]["screenshots"] = ["TODO"]
        self.assert_schema_refuses(report)

    def test_an_empty_reason_is_refused(self):
        report = example()
        report["acceptance"][0]["reason"] = ""
        self.assert_schema_refuses(report)

    def test_an_audit_needs_a_status(self):
        report = example()
        del report["audits"][0]["status"]
        self.assert_schema_refuses(report)

    def test_a_clean_audit_cannot_carry_findings(self):
        report = example()
        report["audits"][0]["status"] = "clean"
        self.assert_schema_refuses(report)

    def test_a_clean_audit_needs_a_head(self):
        report = example()
        report["audits"] = [audit(status="clean", head_sha=None)]
        self.assert_schema_refuses(report)

    def test_a_not_run_audit_needs_a_reason(self):
        report = example()
        report["audits"] = [audit(status="not_run", head_sha=None)]
        self.assert_schema_refuses(report)

    def test_a_closed_pr_cannot_carry_a_position(self):
        report = example()
        report["pull_requests"] = [pull_request(1, state="closed", merge_order=1)]
        self.assert_schema_refuses(report)

    def test_an_open_pr_needs_a_position(self):
        report = example()
        report["pull_requests"] = [pull_request(1)]
        self.assert_schema_refuses(report)

    def test_a_clean_audit_is_accepted_by_the_schema(self):
        report = example()
        report["audits"] = [audit(status="clean")]
        jsonschema.validate(report, self.schema)

    def test_the_validator_normal_form_validates_against_the_schema(self):
        # The normal form omits absent optional keys rather than emitting nulls;
        # otherwise a report accepted by validate() would fail its own schema.
        jsonschema.validate(campaign_report.validate(example()), self.schema)

    def test_a_placeholder_performance_evidence_is_refused_by_the_schema(self):
        report = example()
        report["artifacts"]["performance"][0]["evidence"] = "TODO"
        self.assert_schema_refuses(report)


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
