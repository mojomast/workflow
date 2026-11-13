"""Feature-packet and source-resolution validation tests."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "reference"))

import feature_packet  # noqa: E402
from workflow import acdd  # noqa: E402

EXAMPLES = ROOT / "schemas" / "examples"


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def packet_digest(packet: dict) -> str:
    return hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def resolution_for(packet: dict, accepted: str, *, mutate=None) -> dict:
    contract = copy.deepcopy(packet["contract_template"])
    contract["source_rev"] = accepted
    if mutate:
        mutate(contract)
    frozen = acdd.freeze_contract(contract, approved_by="policy-b", approved_at="2026-11-13T00:00:00Z")
    return {
        "resolution_version": "rizzstack.source-resolution/1",
        "packet_digest": packet_digest(packet),
        "policy_id": packet["source_policy"]["policy_id"],
        "policy_digest": "d" * 64,
        "dependency_job": "job_a",
        "dependency_feature": packet["source_policy"]["dependencies"][0],
        "accepted_commit": accepted,
        "derived_source_rev": accepted,
        "contract": frozen,
        "contract_sha256": acdd.check_frozen(frozen),
        "at": "2026-11-13T00:00:00Z",
    }


class PositiveTests(unittest.TestCase):
    def test_the_exact_example_validates_against_the_pinned_protocol(self):
        packet = feature_packet.validate(load("feature-exact.json"), workflow_repo=ROOT)
        self.assertEqual(packet["source_policy"]["kind"], "exact")

    def test_the_dependent_intent_example_validates_against_the_pinned_protocol(self):
        packet = feature_packet.validate(load("feature-descendant.json"), workflow_repo=ROOT)
        self.assertEqual(packet["source_policy"]["kind"], "descendant")
        self.assertNotIn("contract", packet)  # intent carries a template, not a fabricated frozen contract

    def test_a_source_resolution_binds_the_intent_to_the_accepted_commit(self):
        packet = load("feature-descendant.json")
        accepted = "c" * 40
        record = resolution_for(packet, accepted)
        out = feature_packet.validate_source_resolution(record, packet=packet, accepted_commit=accepted)
        self.assertEqual(out["derived_source_rev"], accepted)
        self.assertEqual(record["contract"]["source_rev"], accepted)


class NegativeTests(unittest.TestCase):
    def assertRefused(self, packet, code, **kwargs):
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate(packet, check_protocol_commit=False, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_an_unsupported_version_is_refused(self):
        packet = load("feature-exact.json")
        packet["packet_version"] = "rizzstack.feature-packet/0"
        self.assertRefused(packet, "packet_schema")

    def test_a_mutated_frozen_contract_is_refused(self):
        packet = load("feature-exact.json")
        packet["contract"]["outcome"]["summary"] = "mutated"
        self.assertRefused(packet, "contract_hash_mismatch")

    def test_substituted_tests_are_refused_even_when_originals_remain(self):
        packet = load("feature-exact.json")
        packet["tests"] = packet["tests"] + ["tests/extra.py::test_extra"]
        self.assertRefused(packet, "tests_mismatch")

    def test_unprotected_approved_tests_are_refused(self):
        packet = load("feature-exact.json")
        packet["scope"]["read_only"] = []
        self.assertRefused(packet, "tests_unprotected")

    def test_changed_human_gates_are_refused(self):
        packet = load("feature-exact.json")
        packet["human_gates"] = ["merge"]
        self.assertRefused(packet, "gates_mismatch")

    def test_a_wider_lease_is_refused(self):
        packet = load("feature-exact.json")
        packet["scope"]["lease"] = packet["scope"]["lease"] + ["src/secret.py"]
        self.assertRefused(packet, "scope_mismatch")

    def test_a_budget_wider_than_the_authorization_is_refused(self):
        packet = load("feature-exact.json")
        packet["authorization"]["limits"] = {"bees": 1, "wall_clock_s": 60}
        self.assertRefused(packet, "budget_exceeded")

    def test_an_exact_packet_with_a_different_revision_is_refused(self):
        packet = load("feature-exact.json")
        packet["source_policy"]["revision"] = "f" * 40
        self.assertRefused(packet, "source_policy_mismatch")

    def test_an_intent_packet_cannot_pre_claim_a_resolution(self):
        packet = load("feature-descendant.json")
        packet["source_resolution_ref"] = "resolution.json"
        self.assertRefused(packet, "source_resolution_premature")

    def test_two_dependencies_are_refused(self):
        packet = load("feature-descendant.json")
        packet["source_policy"]["dependencies"] = ["feature-a", "feature-c"]
        self.assertRefused(packet, "packet_schema")

    def test_an_intent_packet_cannot_carry_a_frozen_contract_claim(self):
        packet = load("feature-descendant.json")
        packet["contract"] = packet["contract_template"]
        packet["contract_sha256"] = "0" * 64
        self.assertRefused(packet, "packet_schema")

    def test_a_dropped_approved_test_is_refused(self):
        packet = load("feature-exact.json")
        packet["tests"] = ["tests/other.py::test_other"]
        self.assertRefused(packet, "tests_mismatch")

    def test_missing_authorization_provenance_is_refused(self):
        packet = load("feature-exact.json")
        packet["authorization"]["reference"] = ""
        self.assertRefused(packet, "packet_schema")

    def test_dropped_human_gates_are_refused(self):
        packet = load("feature-exact.json")
        packet["human_gates"] = []
        self.assertRefused(packet, "packet_schema")

    def test_a_resolution_with_another_revision_is_refused(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, "c" * 40)
        record["derived_source_rev"] = "e" * 40
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate_source_resolution(record, packet=packet, accepted_commit="c" * 40)
        self.assertEqual(caught.exception.code, "resolution_revision_mismatch")

    def test_a_resolution_that_changes_scope_is_refused(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, "c" * 40,
                                mutate=lambda c: c["scope"].__setitem__("assigned_files", ["src/other.py"]))
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate_source_resolution(record, packet=packet, accepted_commit="c" * 40)
        self.assertEqual(caught.exception.code, "resolution_scope_changed")

    def test_validator_drift_at_the_pinned_commit_is_refused(self):
        packet = load("feature-exact.json")
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        packet["workflow_ref"] = head
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"{head}:schemas/feature-packet.schema.json"],
                                   capture_output=True, text=True)
        if committed.returncode != 0:
            with self.assertRaises(feature_packet.PacketError) as caught:
                feature_packet.validate(packet, workflow_repo=ROOT)
            self.assertEqual(caught.exception.code, "workflow_ref_unsupported")
            return
        feature_packet.validate(packet, workflow_repo=ROOT)


if __name__ == "__main__":
    unittest.main()
