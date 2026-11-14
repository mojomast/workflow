"""Conformance tests for rizzstack.bee-landed/1 (schemas/bee-landed.schema.json)."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bee_landed  # noqa: E402

try:  # jsonschema is optional; the semantic validator never depends on it.
    import jsonschema
except ImportError:  # pragma: no cover - exercised on minimal installs
    jsonschema = None

SCHEMA_PATH = ROOT / "schemas" / "bee-landed.schema.json"


def base_event() -> dict:
    return {
        "specversion": "1.0",
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "source": "urn:rizzstack:coordinator:test",
        "type": "rizzstack.bee.landed.v1",
        "time": "2026-11-14T12:00:00Z",
        "subject": "job_a/attempt_a",
        "data": {
            "schema": "rizzstack.bee-landed/1",
            "feature_id": "feature-a",
            "job_id": "job_a",
            "task_id": "task_a",
            "attempt_id": "attempt_a",
            "coordinator": {"identity": "coordinator-a", "session": "session-1"},
            "backend": {"harness": "claude-code", "model": "claude-sonnet"},
            "state": "succeeded",
            "source_rev": "a" * 40,
            "lease": {
                "sha256": "b" * 64,
                "assigned_files": ["src/feature.py", "docs/feature.md"],
            },
            "result": {
                "available": True,
                "artifact_sha256": "c" * 64,
                "reference": "artifacts/attempt_a.json",
            },
            "terminal_transition_id": "transition-1",
            "correlation_id": "correlation-1",
            "causation_id": "command-1",
        },
    }


def failed_event() -> dict:
    event = base_event()
    event["data"]["state"] = "failed"
    event["data"]["result"] = {"available": False}
    return event


def cancelled_event() -> dict:
    event = base_event()
    event["data"]["state"] = "cancelled"
    event["data"]["result"] = {"available": False}
    event["data"]["lease"]["assigned_files"] = []
    event["data"]["terminal_transition_id"] = "transition-cancelled"
    return event


class PositiveTests(unittest.TestCase):
    def test_the_exact_landing_validates(self):
        event = bee_landed.validate(base_event())
        self.assertEqual(event["data"]["state"], "succeeded")
        self.assertEqual(event["type"], "rizzstack.bee.landed.v1")

    def test_a_failed_landing_validates(self):
        event = bee_landed.validate(failed_event())
        self.assertEqual(event["data"]["state"], "failed")
        self.assertFalse(event["data"]["result"]["available"])

    def test_a_cancelled_landing_validates_without_work_artifacts(self):
        event = bee_landed.validate(cancelled_event())
        self.assertEqual(event["data"]["state"], "cancelled")
        self.assertEqual(event["data"]["lease"]["assigned_files"], [])

    def test_validate_returns_a_detached_copy(self):
        original = base_event()
        validated = bee_landed.validate(original)
        validated["data"]["state"] = "failed"
        self.assertEqual(original["data"]["state"], "succeeded")

    def test_the_schema_declares_the_canonical_shape(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["type"]["const"], "rizzstack.bee.landed.v1")
        self.assertEqual(set(schema["required"]),
                         {"specversion", "id", "source", "type", "time", "subject", "data"})
        data = schema["properties"]["data"]
        self.assertEqual(data["properties"]["schema"]["const"], "rizzstack.bee-landed/1")
        self.assertEqual(data["properties"]["state"]["enum"], ["succeeded", "failed", "cancelled"])
        self.assertTrue({"schema", "feature_id", "job_id", "task_id", "attempt_id",
                         "coordinator", "backend", "state", "source_rev", "lease", "result"}
                        <= set(data["required"]))

    @unittest.skipUnless(jsonschema is not None, "jsonschema is not installed")
    def test_positive_events_validate_against_the_schema_when_jsonschema_is_available(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        for event in (base_event(), failed_event(), cancelled_event()):
            errors = sorted(validator.iter_errors(event), key=lambda error: error.path)
            self.assertEqual(errors, [], [error.message for error in errors])


class DedupeTests(unittest.TestCase):
    def test_the_dedupe_key_is_sha256_of_attempt_state_and_transition(self):
        event = base_event()
        expected = hashlib.sha256(b"attempt_a:succeeded:transition-1").hexdigest()
        self.assertEqual(bee_landed.dedupe_key(event), expected)

    def test_the_cloud_events_id_is_the_transition_fallback(self):
        event = base_event()
        del event["data"]["terminal_transition_id"]
        expected = hashlib.sha256(
            f"attempt_a:succeeded:{event['id']}".encode("utf-8")
        ).hexdigest()
        self.assertEqual(bee_landed.dedupe_key(event), expected)

    def test_the_same_terminal_landing_dedupes_to_one_key(self):
        first = base_event()
        second = copy.deepcopy(first)
        second["time"] = "2026-11-14T12:00:01Z"
        second["id"] = "223e4567-e89b-12d3-a456-426614174000"
        self.assertEqual(bee_landed.dedupe_key(first), bee_landed.dedupe_key(second))

    def test_a_different_terminal_state_gets_a_different_key(self):
        self.assertNotEqual(bee_landed.dedupe_key(base_event()), bee_landed.dedupe_key(failed_event()))

    def test_a_dedupe_request_without_data_is_refused(self):
        with self.assertRaises(bee_landed.BeeLandedError) as caught:
            bee_landed.dedupe_key({"id": "123e4567-e89b-12d3-a456-426614174000"})
        self.assertEqual(caught.exception.code, "bee_dedupe")


class NegativeTests(unittest.TestCase):
    def assertRefused(self, event: dict, code: str) -> bee_landed.BeeLandedError:
        with self.assertRaises(bee_landed.BeeLandedError) as caught:
            bee_landed.validate(event)
        self.assertEqual(caught.exception.code, code, caught.exception.message)
        return caught.exception

    def test_a_wrong_cloud_events_version_is_refused(self):
        event = base_event()
        event["specversion"] = "0.3"
        self.assertRefused(event, "bee_cloud_events_version")

    def test_an_event_id_that_is_neither_uuid_nor_urn_is_refused(self):
        event = base_event()
        event["id"] = "attempt_a"
        self.assertRefused(event, "bee_event_id")

    def test_a_urn_event_id_is_accepted(self):
        event = base_event()
        event["id"] = "urn:rizzstack:event:123e4567"
        bee_landed.validate(event)

    def test_a_source_with_whitespace_is_refused(self):
        event = base_event()
        event["source"] = "urn:rizzstack:bad source"
        self.assertRefused(event, "bee_source")

    def test_a_wrong_event_type_is_refused(self):
        event = base_event()
        event["type"] = "rizzstack.bee.verified.v1"
        self.assertRefused(event, "bee_type")

    def test_a_malformed_time_is_refused(self):
        event = base_event()
        event["time"] = "2026-13-40T99:99:99Z"
        self.assertRefused(event, "bee_time")

    def test_a_missing_subject_is_refused(self):
        event = base_event()
        del event["subject"]
        self.assertRefused(event, "bee_required")

    def test_a_wrong_payload_schema_is_refused(self):
        event = base_event()
        event["data"]["schema"] = "rizzstack.bee-landed/0"
        self.assertRefused(event, "bee_data_schema")

    def test_a_missing_attempt_id_is_refused(self):
        event = base_event()
        del event["data"]["attempt_id"]
        self.assertRefused(event, "bee_required")

    def test_an_unknown_payload_field_is_refused(self):
        event = base_event()
        event["data"]["outcome"] = "done"
        self.assertRefused(event, "bee_data_unknown")

    def test_a_receiver_side_state_is_refused(self):
        event = base_event()
        event["data"]["state"] = "verified"
        self.assertRefused(event, "bee_state")

    def test_an_uppercase_source_revision_is_refused(self):
        event = base_event()
        event["data"]["source_rev"] = "A" * 40
        self.assertRefused(event, "bee_source_rev")

    def test_a_short_source_revision_is_refused(self):
        event = base_event()
        event["data"]["source_rev"] = "a" * 39
        self.assertRefused(event, "bee_source_rev")

    def test_a_sixty_four_hex_source_revision_is_accepted(self):
        event = base_event()
        event["data"]["source_rev"] = "a" * 64
        bee_landed.validate(event)

    def test_a_coordinator_without_identity_is_refused(self):
        event = base_event()
        event["data"]["coordinator"] = {}
        self.assertRefused(event, "bee_required")

    def test_an_empty_coordinator_identity_is_refused(self):
        event = base_event()
        event["data"]["coordinator"]["identity"] = ""
        self.assertRefused(event, "bee_coordinator")

    def test_a_backend_without_harness_is_refused(self):
        event = base_event()
        event["data"]["backend"] = {"model": "some-model"}
        self.assertRefused(event, "bee_required")

    def test_an_uppercase_lease_digest_is_refused(self):
        event = base_event()
        event["data"]["lease"]["sha256"] = "B" * 64
        self.assertRefused(event, "bee_lease")

    def test_an_absolute_assigned_file_is_refused(self):
        event = base_event()
        event["data"]["lease"]["assigned_files"] = ["/etc/passwd"]
        self.assertRefused(event, "bee_lease")

    def test_an_assigned_file_with_traversal_is_refused(self):
        event = base_event()
        event["data"]["lease"]["assigned_files"] = ["src/../secret.txt"]
        self.assertRefused(event, "bee_private_path")

    def test_a_duplicate_assigned_file_is_refused(self):
        event = base_event()
        event["data"]["lease"]["assigned_files"] = ["src/feature.py", "src/feature.py"]
        self.assertRefused(event, "bee_lease")

    def test_an_available_result_without_an_artifact_is_refused(self):
        event = base_event()
        event["data"]["result"] = {"available": True}
        self.assertRefused(event, "bee_result")

    def test_a_non_boolean_available_flag_is_refused(self):
        event = base_event()
        event["data"]["result"]["available"] = "yes"
        self.assertRefused(event, "bee_result")

    def test_an_uppercase_artifact_digest_is_refused(self):
        event = base_event()
        event["data"]["result"]["artifact_sha256"] = "C" * 64
        self.assertRefused(event, "bee_result")

    def test_a_credential_named_field_is_refused(self):
        event = base_event()
        event["api_key"] = "not-a-real-key"
        self.assertRefused(event, "bee_secret")

    def test_a_credential_shaped_value_is_refused(self):
        event = base_event()
        event["data"]["coordinator"]["session"] = "ghp_" + "a" * 24
        self.assertRefused(event, "bee_secret")

    def test_a_private_home_path_is_refused(self):
        event = base_event()
        event["data"]["result"]["reference"] = "/home/alice/artifacts/attempt.json"
        self.assertRefused(event, "bee_private_path")

    def test_a_private_key_path_is_refused(self):
        event = base_event()
        event["data"]["result"]["reference"] = "artifacts/.ssh/id_rsa"
        self.assertRefused(event, "bee_private_path")

    def test_a_full_patch_in_a_reference_is_refused(self):
        event = base_event()
        event["data"]["result"]["reference"] = "diff --git a/x b/x\n@@ -1 +1 @@"
        self.assertRefused(event, "bee_patch")

    def test_a_full_patch_field_is_refused(self):
        event = base_event()
        event["patch"] = "--- a/x\n+++ b/x\n"
        self.assertRefused(event, "bee_patch")

    def test_an_oversized_event_is_refused(self):
        event = base_event()
        event["extension_blob"] = "a" * (bee_landed.MAX_EVENT_BYTES + 1)
        self.assertRefused(event, "bee_oversized")

    def test_a_client_verified_claim_is_refused(self):
        event = base_event()
        event["verified"] = True
        self.assertRefused(event, "bee_client_claim")

    def test_a_client_accepted_claim_is_refused(self):
        event = base_event()
        event["accepted"] = "yes"
        self.assertRefused(event, "bee_client_claim")

    def test_a_client_verification_block_is_refused(self):
        event = base_event()
        event["verification"] = {"result": "PASS"}
        self.assertRefused(event, "bee_client_claim")


if __name__ == "__main__":
    unittest.main()
