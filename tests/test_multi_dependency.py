"""Multi-dependency feature packets (rizzstack.feature-packet/2, packet F4).

rizzstack.feature-packet/1 allows exactly one dependency per descendant packet.
/2 lifts that ceiling: one or more declared dependencies, no self-dependency,
no duplicates, and admission only once every declared dependency is admitted
and merged. The single-dependency /1 shape is unchanged.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "reference"))

import feature_packet  # noqa: E402
from workflow import acdd  # noqa: E402

EXAMPLES = ROOT / "schemas" / "examples"
V1 = "rizzstack.feature-packet/1"
V2 = "rizzstack.feature-packet/2"
ACCEPTED = "c" * 40


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def descendant_packet(*dependencies: str, version: str = V2, feature_id: str = "feature-c") -> dict:
    """A valid intent packet declaring the given dependencies."""
    packet = load("feature-descendant.json")
    packet["packet_version"] = version
    packet["feature_id"] = feature_id
    packet["job_id"] = f"job-{feature_id.removeprefix('feature-')}"
    packet["request"] = {"summary": "triple_answer() returns 126", "provenance": f"kanban:{feature_id}"}
    packet["authorization"]["reference"] = packet["job_id"].replace("job-", "auth:job_")
    packet["source_policy"] = {
        "kind": "descendant",
        "root_revision": packet["source_policy"]["root_revision"],
        "dependencies": list(dependencies),
        "policy_id": "policy-c",
    }
    return packet


def resolution_record(packet: dict, dependency: str, *, accepted: str = ACCEPTED) -> dict:
    """A stage-2 record binding the packet to one declared dependency's commit."""
    template = copy.deepcopy(packet["contract_template"])
    template["source_rev"] = accepted
    frozen = acdd.freeze_contract(template, approved_by="policy-c", approved_at="2026-11-16T00:00:00Z")
    return {
        "resolution_version": "rizzstack.source-resolution/1",
        "packet_digest": feature_packet.packet_digest(packet),
        "policy_id": packet["source_policy"]["policy_id"],
        "policy_digest": "d" * 64,
        "dependency_job": f"job-{dependency.removeprefix('feature-')}",
        "dependency_feature": dependency,
        "accepted_commit": accepted,
        "derived_source_rev": accepted,
        "contract": frozen,
        "contract_sha256": acdd.check_frozen(frozen),
        "at": "2026-11-16T00:00:00Z",
    }


class VersionTwoIntentTests(unittest.TestCase):
    """rizzstack.feature-packet/2 declares one or more dependencies; /1 stays exactly one."""

    def validate(self, packet):
        return feature_packet.validate(packet, check_protocol_commit=False)

    def test_a_two_dependency_intent_packet_validates(self):
        packet = self.validate(descendant_packet("feature-a", "feature-b"))
        self.assertEqual(packet["packet_version"], V2)
        self.assertEqual(packet["source_policy"]["dependencies"], ["feature-a", "feature-b"])

    def test_a_three_dependency_intent_packet_validates(self):
        packet = self.validate(descendant_packet("feature-a", "feature-b", "feature-c", feature_id="feature-d"))
        self.assertEqual(packet["source_policy"]["dependencies"], ["feature-a", "feature-b", "feature-c"])

    def test_the_single_dependency_example_is_still_version_one(self):
        packet = self.validate(load("feature-descendant.json"))
        self.assertEqual(packet["packet_version"], V1)

    def test_an_exact_packet_may_also_carry_version_two(self):
        packet = load("feature-exact.json")
        packet["packet_version"] = V2
        exact = self.validate(packet)
        self.assertEqual(exact["source_policy"]["kind"], "exact")

    def test_a_version_one_packet_with_two_dependencies_names_the_upgrade(self):
        packet = descendant_packet("feature-a", "feature-b", version=V1)
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.validate(packet)
        self.assertEqual(caught.exception.code, "packet_schema")
        self.assertIn(V2, caught.exception.message)
        self.assertIn(V2, caught.exception.fix)

    def test_a_version_two_packet_still_refuses_a_frozen_contract(self):
        packet = descendant_packet("feature-a", "feature-b")
        packet["contract"] = copy.deepcopy(packet["contract_template"])
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.validate(packet)
        self.assertEqual(caught.exception.code, "packet_schema")
        self.assertIn("contract", caught.exception.message)

    def test_a_version_two_packet_still_needs_its_policy_id(self):
        packet = descendant_packet("feature-a", "feature-b")
        del packet["source_policy"]["policy_id"]
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.validate(packet)
        self.assertEqual(caught.exception.code, "packet_schema")


class DependencySemanticsTests(unittest.TestCase):
    """No self-dependency and no duplicates, on either packet version."""

    def validate(self, packet):
        return feature_packet.validate(packet, check_protocol_commit=False)

    def test_a_packet_cannot_depend_on_itself(self):
        packet = descendant_packet("feature-a", "feature-c")
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.validate(packet)
        self.assertEqual(caught.exception.code, "dependency_self")
        self.assertIn("feature-c", caught.exception.message)

    def test_a_single_dependency_may_not_be_the_packet_itself(self):
        packet = descendant_packet("feature-c")
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.validate(packet)
        self.assertEqual(caught.exception.code, "dependency_self")

    def test_duplicate_dependencies_are_refused(self):
        packet = descendant_packet("feature-a", "feature-a", "feature-b")
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.validate(packet)
        self.assertEqual(caught.exception.code, "dependency_duplicate")
        self.assertIn("feature-a", caught.exception.message)


class AdmissionTests(unittest.TestCase):
    """Every declared dependency must be admitted and merged before the dependent is."""

    def admit(self, packet, accepted=None):
        return feature_packet.admit(packet, accepted=accepted, check_protocol_commit=False)

    def test_admission_refuses_until_every_dependency_is_merged(self):
        packet = descendant_packet("feature-a", "feature-b")
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.admit(packet)
        self.assertEqual(caught.exception.code, "dependency_not_accepted")
        self.assertIn("feature-a", caught.exception.message)
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.admit(packet, accepted={"feature-a": ACCEPTED})
        self.assertEqual(caught.exception.code, "dependency_not_accepted")
        self.assertIn("feature-b", caught.exception.message)
        self.assertNotIn("feature-a", caught.exception.message)

    def test_admission_succeeds_once_every_dependency_is_merged(self):
        packet = descendant_packet("feature-a", "feature-b")
        out = self.admit(packet, accepted={"feature-a": ACCEPTED, "feature-b": "d" * 40})
        self.assertEqual(out["feature_id"], "feature-c")

    def test_three_dependencies_are_admitted_in_declared_order(self):
        packet = descendant_packet("feature-a", "feature-b", "feature-c", feature_id="feature-d")
        merged: dict[str, str] = {}
        for feature in ("feature-a", "feature-b", "feature-c"):
            with self.assertRaises(feature_packet.PacketError) as caught:
                self.admit(packet, accepted=dict(merged))
            self.assertEqual(caught.exception.code, "dependency_not_accepted")
            self.assertIn(feature, caught.exception.message)
            merged[feature] = ACCEPTED
        out = self.admit(packet, accepted=dict(merged))
        self.assertEqual(out["source_policy"]["dependencies"], ["feature-a", "feature-b", "feature-c"])

    def test_an_exact_packet_needs_no_dependencies_to_be_admitted(self):
        out = self.admit(load("feature-exact.json"))
        self.assertEqual(out["source_policy"]["kind"], "exact")

    def test_admission_validates_the_packet_before_the_dependencies(self):
        packet = descendant_packet("feature-a", "feature-b")
        packet["tests"] = ["tests/test_other.py"]
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.admit(packet, accepted={"feature-a": ACCEPTED, "feature-b": ACCEPTED})
        self.assertEqual(caught.exception.code, "tests_mismatch")

    def test_a_single_dependency_packet_is_admitted_like_version_one(self):
        packet = descendant_packet("feature-a", version=V1)
        with self.assertRaises(feature_packet.PacketError) as caught:
            self.admit(packet)
        self.assertEqual(caught.exception.code, "dependency_not_accepted")
        out = self.admit(packet, accepted={"feature-a": ACCEPTED})
        self.assertEqual(out["packet_version"], V1)


class ResolutionTests(unittest.TestCase):
    """Stage 2 binds one declared dependency of a multi-dependency intent."""

    def test_a_resolution_may_bind_a_declared_dependency(self):
        packet = descendant_packet("feature-a", "feature-b")
        record = resolution_record(packet, "feature-b")
        out = feature_packet.validate_source_resolution(record, packet=packet, accepted_commit=ACCEPTED)
        self.assertEqual(out["dependency_feature"], "feature-b")

    def test_a_resolution_naming_an_undeclared_dependency_is_refused(self):
        packet = descendant_packet("feature-a", "feature-b")
        record = resolution_record(packet, "feature-z")
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate_source_resolution(record, packet=packet, accepted_commit=ACCEPTED)
        self.assertEqual(caught.exception.code, "resolution_dependency_mismatch")


if __name__ == "__main__":
    unittest.main()
