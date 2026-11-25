"""Validation tests for the observability record contracts."""

from __future__ import annotations

import hashlib
import json
import secrets
import unittest
from copy import deepcopy
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate import SchemaError, Validator
from alerts import DEFAULTS_PATH, load_thresholds

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SCHEMAS = ROOT / "schemas"

EXAMPLES_AND_SCHEMAS = (
    ("lifecycle-bee-running.json", "lifecycle.schema.json"),
    ("lifecycle-fallback.json", "lifecycle.schema.json"),
    ("failure-rate-limit.json", "failure.schema.json"),
    ("failure-environmental.json", "failure.schema.json"),
    ("vcs-snapshot.json", "vcs-snapshot.schema.json"),
    ("board-snapshot.json", "board-snapshot.schema.json"),
    ("resource-snapshot.json", "resource-snapshot.schema.json"),
)

FORBIDDEN = (
    "ts.net",
    "tailscale",
    "BEGIN PRIVATE",
    "api_key=",
    "api-key=",
    ".env",
)


def _load_example(name: str) -> dict:
    with (EXAMPLES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


class ExamplesValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_every_example_matches_its_schema(self) -> None:
        for example, schema in EXAMPLES_AND_SCHEMAS:
            with self.subTest(example=example):
                self.validator.validate_file(_load_example(example), schema)

    def test_schema_files_are_json_objects(self) -> None:
        names = sorted(path.name for path in SCHEMAS.glob("*.schema.json"))
        self.assertEqual(
            names,
            [
                "alert-thresholds-override.schema.json",
                "alert-thresholds.schema.json",
                "board-snapshot.schema.json",
                "ci-run.schema.json",
                "common.schema.json",
                "failure.schema.json",
                "inference.schema.json",
                "lifecycle.schema.json",
                "owner-decision.schema.json",
                "resource-sample.schema.json",
                "resource-snapshot.schema.json",
                "snapshot.schema.json",
                "task-outcome.schema.json",
                "tool-call.schema.json",
                "vcs-snapshot.schema.json",
            ],
        )
        for name in names:
            with (SCHEMAS / name).open(encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertIsInstance(data, dict)
            self.assertTrue(data["$id"].startswith(
                "https://github.com/mojomast/workflow/observability/schemas/"
            ))

    def test_this_package_does_not_define_a_usage_schema(self) -> None:
        for path in SCHEMAS.glob("*.json"):
            self.assertNotIn("usage", path.name.lower())
            data = json.loads(path.read_text(encoding="utf-8"))
            rec = data.get("properties", {}).get("record_type", {})
            const = str(rec.get("const") or "")
            self.assertNotIn("usage", const.lower())
            for item in rec.get("enum") or []:
                self.assertNotIn("usage", str(item).lower())
            schema_ver = data.get("properties", {}).get("schema_version", {})
            self.assertNotEqual(schema_ver.get("const"), "bee.usage/v1")
            self.assertNotIn("bee.usage/v1", [schema_ver.get("const")] + list(schema_ver.get("enum") or []))


class JoinKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_lifecycle_accepts_the_five_join_keys(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        for key in ("attempt_id", "card_id", "run_id", "project", "role"):
            self.assertIn(key, doc)
            self.assertIsInstance(doc[key], str)
        self.assertEqual(doc["role"], "work")
        self.validator.validate_file(doc, "lifecycle.schema.json")

    def test_snapshots_may_leave_join_keys_null(self) -> None:
        doc = _load_example("vcs-snapshot.json")
        for key in ("attempt_id", "card_id", "run_id", "project", "role"):
            self.assertIsNone(doc[key])
        self.validator.validate_file(doc, "vcs-snapshot.schema.json")

    def test_unknown_role_is_rejected(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        doc["role"] = "worker"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "lifecycle.schema.json")


class FailureClassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_rate_limit_fallback_is_not_a_regression(self) -> None:
        doc = _load_example("failure-rate-limit.json")
        self.assertEqual(doc["class"], "rate-limit")
        self.assertEqual(doc["fallback_to"], "deepseek")
        self.assertTrue(doc["http_429"])
        self.validator.validate_file(doc, "failure.schema.json")

    def test_environmental_class_is_distinct_from_regression(self) -> None:
        doc = _load_example("failure-environmental.json")
        self.assertEqual(doc["class"], "environmental")
        self.assertNotEqual(doc["class"], "regression")
        self.validator.validate_file(doc, "failure.schema.json")

    def test_invented_failure_class_is_rejected(self) -> None:
        doc = _load_example("failure-environmental.json")
        doc["class"] = "timeout"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "failure.schema.json")


class ResourceUnknownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)
        self.doc = _load_example("resource-snapshot.json")

    def test_unavailable_row_uses_null_not_zero(self) -> None:
        go2 = next(row for row in self.doc["resources"] if row.get("resource_id") == "go-2")
        self.assertEqual(go2["status"], "unavailable")
        self.assertIsNone(go2["value"])
        self.assertIsNone(go2["remaining"])
        self.validator.validate_file(self.doc, "resource-snapshot.schema.json")

    def test_genuine_zero_is_allowed_when_status_is_ok(self) -> None:
        cloud = next(row for row in self.doc["resources"] if row["kind"] == "cursor_cloud_agents")
        self.assertEqual(cloud["status"], "ok")
        self.assertEqual(cloud["value"], 0)
        self.validator.validate_file(self.doc, "resource-snapshot.schema.json")

    def test_unavailable_with_zero_value_is_rejected(self) -> None:
        doc = deepcopy(self.doc)
        for row in doc["resources"]:
            if row.get("resource_id") == "go-2":
                row["value"] = 0
                row["remaining"] = 0
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "resource-snapshot.schema.json")

    def test_both_go_keys_are_distinct_labeled_rows(self) -> None:
        go_rows = [row for row in self.doc["resources"] if row["kind"] == "go_allowance"]
        self.assertEqual({row["resource_id"] for row in go_rows}, {"go-1", "go-2"})
        for row in go_rows:
            self.assertNotIn("sk-", str(row))
            self.assertNotIn("key", (row.get("resource_id") or ""))

    def test_shared_bee_cap_is_twelve_in_the_example(self) -> None:
        self.assertEqual(self.doc["bee_cap"], 12)
        bees = next(row for row in self.doc["resources"] if row["kind"] == "bees_in_flight")
        self.assertEqual(bees["cap"], 12)

    def test_unexpected_property_is_rejected(self) -> None:
        doc = deepcopy(self.doc)
        doc["token"] = "should-not-be-here"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "resource-snapshot.schema.json")


class HyvvHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_hyvv_is_an_accepted_lifecycle_source(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        self.assertEqual(doc["platform"], "hyvv")
        doc["source"] = "hyvv"
        self.validator.validate_file(doc, "lifecycle.schema.json")

    def test_launcher_remains_a_transitional_lifecycle_source(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        doc["source"] = "launcher"
        self.validator.validate_file(doc, "lifecycle.schema.json")

    def test_failure_example_is_sourced_from_hyvv(self) -> None:
        doc = _load_example("failure-rate-limit.json")
        self.assertEqual(doc["source"], "hyvv")
        self.validator.validate_file(doc, "failure.schema.json")


class LifecycleRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_go_and_deepseek_routes_are_accepted(self) -> None:
        running = _load_example("lifecycle-bee-running.json")
        fallback = _load_example("lifecycle-fallback.json")
        self.assertEqual(running["route"], "go")
        self.assertFalse(running["fallen_back"])
        self.assertEqual(fallback["route"], "deepseek")
        self.assertTrue(fallback["fallen_back"])
        self.validator.validate_file(running, "lifecycle.schema.json")
        self.validator.validate_file(fallback, "lifecycle.schema.json")

    # Review P1: routes and source kinds are open vocabularies. Known values
    # stay recognized, but another provider is a valid extension label.
    def test_extension_route_and_source_labels_are_accepted(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        doc["route"] = "openrouter"
        doc["source"] = "openrouter-agent"
        self.validator.validate_file(doc, "lifecycle.schema.json")

    def test_malformed_route_labels_are_rejected(self) -> None:
        for bad in ("OpenRouter", "https://openrouter.ai", "a/b", "", "x" * 65, "-go"):
            doc = _load_example("lifecycle-bee-running.json")
            doc["route"] = bad
            with self.subTest(route=bad), self.assertRaises(SchemaError):
                self.validator.validate_file(doc, "lifecycle.schema.json")

    def test_extension_fallback_and_resource_kind_are_accepted(self) -> None:
        failure = _load_example("failure-rate-limit.json")
        failure["fallback_to"] = "openrouter"
        self.validator.validate_file(failure, "failure.schema.json")
        snapshot = _load_example("resource-snapshot.json")
        snapshot["resources"][0]["kind"] = "openrouter_credit"
        self.validator.validate_file(snapshot, "resource-snapshot.schema.json")

    def test_stable_vocabularies_stay_closed(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        doc["state"] = "exploded"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "lifecycle.schema.json")
        failure = _load_example("failure-rate-limit.json")
        failure["class"] = "openrouter"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(failure, "failure.schema.json")


class PrivacyTests(unittest.TestCase):
    def test_examples_and_schemas_have_no_host_or_secret_markers(self) -> None:
        allowed_urls = (
            "https://json-schema.org",
            "https://github.com/mojomast/workflow/observability/schemas/",
        )
        paths = [DEFAULTS_PATH]
        for folder in (EXAMPLES, SCHEMAS):
            paths.extend(path for path in folder.glob("*") if path.is_file())
        for path in paths:
            raw = path.read_text(encoding="utf-8")
            lowered = raw.lower()
            for token in FORBIDDEN:
                self.assertNotIn(token.lower(), lowered, f"{path.name} contains {token!r}")
            remainder = raw
            for url in allowed_urls:
                remainder = remainder.replace(url, "")
            self.assertNotIn("://", remainder, f"{path.name} has an unexpected URL")
            self.assertNotRegex(raw, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


class BoardAndVcsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_board_without_blockers_uses_null_age(self) -> None:
        doc = _load_example("board-snapshot.json")
        doc["open_blocker_count"] = 0
        doc["oldest_blocker_age_s"] = None
        self.validator.validate_file(doc, "board-snapshot.schema.json")

    def test_vcs_rejects_a_clone_url(self) -> None:
        doc = _load_example("vcs-snapshot.json")
        doc["repos"][0]["repo"] = "https://github.com/mojomast/workflow"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "vcs-snapshot.schema.json")

    def test_missing_required_field_is_rejected(self) -> None:
        doc = _load_example("board-snapshot.json")
        del doc["group"]
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "board-snapshot.schema.json")


class AlertThresholdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_defaults_match_kyle_thresholds(self) -> None:
        doc = load_thresholds()
        self.validator.validate_file(doc, "alert-thresholds.schema.json")
        self.assertEqual(doc["schema"], "alert.thresholds/v1")
        self.assertEqual(doc["schema_version"], "v1")
        self.assertEqual(doc["destinations"], ["orbit_dashboard", "board_note"])
        self.assertEqual(doc["actions"]["at_bee_cap"], "warn")
        th = doc["thresholds"]
        self.assertEqual(th["deepseek_balance_below_usd"], 5)
        self.assertEqual(th["go_allowance_pct_used"], 80)
        self.assertEqual(th["go_429_streak"], 5)
        self.assertEqual(th["stuck_bee_no_progress_s"], 1800)
        self.assertEqual(th["blocker_age_s"], 14400)
        self.assertEqual(th["disk_free_pct"], 10)
        self.assertEqual(th["bees_in_flight_warn_at"], 12)
        self.assertEqual(th["daily_model_spend_above_usd"], 10)

    def test_override_merges_on_top_of_defaults(self) -> None:
        merged = load_thresholds(EXAMPLES / "alerts.override.json")
        self.validator.validate_file(merged, "alert-thresholds.schema.json")
        self.assertEqual(merged["schema"], "alert.thresholds/v1")
        self.assertEqual(merged["thresholds"]["daily_model_spend_above_usd"], 15)
        self.assertEqual(merged["thresholds"]["deepseek_balance_below_usd"], 5)
        self.assertEqual(merged["destinations"], ["orbit_dashboard", "board_note"])
        self.assertEqual(merged["actions"]["at_bee_cap"], "warn")

    def test_defaults_are_not_mutated_by_an_override(self) -> None:
        load_thresholds(EXAMPLES / "alerts.override.json")
        again = load_thresholds()
        self.assertEqual(again["thresholds"]["daily_model_spend_above_usd"], 10)

    def test_pause_at_bee_cap_is_rejected_in_v1(self) -> None:
        doc = load_thresholds()
        doc["actions"]["at_bee_cap"] = "pause"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "alert-thresholds.schema.json")

    def test_chat_destination_is_rejected(self) -> None:
        doc = load_thresholds()
        doc["destinations"] = ["orbit_dashboard", "chat"]
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "alert-thresholds.schema.json")

    def test_percent_above_100_is_rejected(self) -> None:
        doc = load_thresholds()
        doc["thresholds"]["disk_free_pct"] = 101
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "alert-thresholds.schema.json")

    def test_empty_override_is_rejected(self) -> None:
        with self.assertRaises(SchemaError):
            self.validator.validate_file(
                {"schema": "alert.thresholds.override/v1", "schema_version": "v1"},
                "alert-thresholds-override.schema.json",
            )

    def test_override_example_validates(self) -> None:
        self.validator.validate_file(
            _load_example("alerts.override.json"),
            "alert-thresholds-override.schema.json",
        )


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(body: dict) -> str:
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _unavailable_section(collected_at: str) -> dict:
    return {"status": "unavailable", "error": "source_missing", "collected_at": collected_at}


def _unavailable_snapshot(generated_at: str) -> dict:
    """The smallest snapshot a collector with no readable source may emit."""
    collected = generated_at
    return {
        "schema": "rizzstack.observability/snapshot/1",
        "generated_at": generated_at,
        "collector": {"name": "test-suite"},
        "degraded": [],
        "fleet": dict(
            _unavailable_section(collected),
            attempts=[],
            in_flight=None,
            bee_cap=None,
        ),
        "usage": dict(
            _unavailable_section(collected),
            source={
                "schema": "rizzstack.observability/snapshot/1",
                "generated_at": generated_at,
                "record_count": None,
                "parse_errors": None,
                "usage_status": "unavailable",
            },
            totals={
                "schema": "rizzstack.observability/snapshot/1",
                "generated_at": generated_at,
                "requests": None,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "cost_usd": None,
                "tokens_status": "unavailable",
                "cost_status": "unavailable",
                "unknown_cost_records": None,
                "http_429_count": None,
                "fallback_count": None,
            },
            by_model=[],
            by_repo=[],
        ),
        "pipeline": dict(
            _unavailable_section(collected),
            jobs=[],
            counts={},
            escalations=[],
            blockers=[],
        ),
        "backlog": dict(_unavailable_section(collected), features=[], counts={}),
        "ci": dict(_unavailable_section(collected), repos=[], prs=[]),
        "failures": dict(_unavailable_section(collected), failures=[], counts={}),
        "health": dict(
            _unavailable_section(collected),
            scheduler={
                "schema": "rizzstack.observability/snapshot/1",
                "generated_at": generated_at,
                "liveness": "unavailable",
                "alive": None,
                "last_event_at": None,
                "last_event_age_s": None,
                "source": "none",
            },
            quota=[],
            bees_in_flight=None,
            bee_cap=None,
        ),
        "alerts": dict(_unavailable_section(collected), active=[]),
    }


class OwnerDecisionRecordTests(unittest.TestCase):
    """The owner-decision queue record contract (rizzstack.owner-decision/1)."""

    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    @staticmethod
    def _nonce() -> str:
        return secrets.token_hex(16)

    def _request(self) -> dict:
        body = {
            "schema": "rizzstack.owner-decision/1",
            "record": "request",
            "request_id": "odq_release_gate_1",
            "kind": "gate",
            "subject": "release-gate",
            "question": "Resolve the release gate for job odj_release_1?",
            "evidence": [{"kind": "record", "reference": "jobs/odj_release_1.json"}],
            "raised_by": "decision_queue",
            "raised_at": "2026-11-16T09:00:00Z",
            "decision_nonce": self._nonce(),
        }
        body["request_digest"] = _digest(body)
        return body

    def _decision(self, request: dict, outcome: str = "approve") -> dict:
        body = {
            "schema": "rizzstack.owner-decision/1",
            "record": "decision",
            "request_id": request["request_id"],
            "request_digest": request["request_digest"],
            "decision_nonce": request["decision_nonce"],
            "decided_by": "owner",
            "decided_at": "2026-11-16T10:00:00Z",
            "outcome": outcome,
            "approval_receipt_ref": "approvals/odj_release_1.release-gate.json",
            "rationale": "The gate criteria are met and the evidence references check out.",
        }
        if outcome != "approve":
            body["approval_receipt_ref"] = None
        body["decision_digest"] = _digest(body)
        return body

    def test_request_document_validates(self) -> None:
        self.validator.validate_file(self._request(), "owner-decision.schema.json")

    def test_decision_document_validates(self) -> None:
        request = self._request()
        self.validator.validate_file(request, "owner-decision.schema.json")
        self.validator.validate_file(self._decision(request), "owner-decision.schema.json")

    def test_missing_required_field_is_rejected(self) -> None:
        body = self._request()
        del body["question"]
        with self.assertRaises(SchemaError):
            self.validator.validate_file(body, "owner-decision.schema.json")

    def test_unexpected_property_is_rejected(self) -> None:
        body = self._request()
        body["widen_budget"] = True
        with self.assertRaises(SchemaError):
            self.validator.validate_file(body, "owner-decision.schema.json")

    def test_unknown_kind_is_rejected(self) -> None:
        body = self._request()
        body["kind"] = "merge"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(body, "owner-decision.schema.json")

    def test_unknown_outcome_is_rejected(self) -> None:
        request = self._request()
        body = self._decision(request)
        body["outcome"] = "maybe"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(body, "owner-decision.schema.json")

    def test_deferral_may_omit_the_receipt(self) -> None:
        request = self._request()
        self.validator.validate_file(
            self._decision(request, outcome="defer"), "owner-decision.schema.json"
        )

    def test_malformed_discriminator_is_rejected(self) -> None:
        body = self._request()
        body["schema"] = "owner-decision/v1"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(body, "owner-decision.schema.json")


class SnapshotDecisionsExtensionTests(unittest.TestCase):
    """The optional decisions section is a backward-compatible extension."""

    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)
        self.schema = self.validator.load("snapshot.schema.json")

    @staticmethod
    def _row(request_id: str, state: str, kind: str = "gate") -> dict:
        return {
            "schema": "rizzstack.observability/snapshot/1",
            "generated_at": "2026-11-16T09:30:00Z",
            "request_id": request_id,
            "kind": kind,
            "subject": "release-gate",
            "state": state,
            "outcome": None,
            "question": "Resolve the release gate for job odj_release_1?",
            "raised_at": "2026-11-16T09:00:00Z",
            "decided_at": None,
            "applied_at": None,
        }

    def _section(self, rows: list) -> dict:
        return {
            "status": "live",
            "error": None,
            "collected_at": "2026-11-16T09:30:00Z",
            "requests": rows,
        }

    def test_section_is_optional_and_absent_by_default(self) -> None:
        self.assertIn("decisions", self.schema["properties"])
        self.assertNotIn("decisions", self.schema["required"])
        self.validator.validate_file(
            _unavailable_snapshot("2026-11-16T09:30:00Z"), "snapshot.schema.json"
        )

    def test_snapshot_with_decisions_section_validates(self) -> None:
        doc = _unavailable_snapshot("2026-11-16T09:30:00Z")
        doc["decisions"] = self._section(
            [
                self._row("odq_release_gate_1", "pending"),
                self._row("odq_budget_top_up_1", "applied"),
            ]
        )
        self.validator.validate_file(doc, "snapshot.schema.json")

    def test_extension_kind_label_is_accepted(self) -> None:
        doc = _unavailable_snapshot("2026-11-16T09:30:00Z")
        doc["decisions"] = self._section(
            [self._row("odq_vendor_signoff_1", "pending", kind="vendor_signoff")]
        )
        self.validator.validate_file(doc, "snapshot.schema.json")

    def test_unknown_row_property_is_rejected(self) -> None:
        doc = _unavailable_snapshot("2026-11-16T09:30:00Z")
        row = self._row("odq_release_gate_1", "pending")
        row["decided_by"] = "owner"
        doc["decisions"] = self._section([row])
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "snapshot.schema.json")

    def test_row_must_carry_the_snapshot_envelope(self) -> None:
        doc = _unavailable_snapshot("2026-11-16T09:30:00Z")
        row = self._row("odq_release_gate_1", "pending")
        row["schema"] = "rizzstack.owner-decision/1"
        doc["decisions"] = self._section([row])
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "snapshot.schema.json")

    def test_unknown_state_is_rejected(self) -> None:
        doc = _unavailable_snapshot("2026-11-16T09:30:00Z")
        doc["decisions"] = self._section([self._row("odq_release_gate_1", "approved")])
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "snapshot.schema.json")


if __name__ == "__main__":
    unittest.main()
