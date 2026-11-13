"""Feature-packet schema and semantic validation tests."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
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


class PositiveTests(unittest.TestCase):
    def test_the_exact_revision_example_validates_without_a_checkout(self):
        packet = feature_packet.validate(load("feature-exact.json"), check_protocol_commit=False)
        self.assertEqual(packet["packet_version"], "rizzstack.feature-packet/1")

    def test_the_dependent_example_validates(self):
        packet = feature_packet.validate(load("feature-descendant.json"), check_protocol_commit=False)
        self.assertEqual(packet["source_policy"]["kind"], "descendant")

    def test_a_pinned_commit_with_the_same_schema_validates(self):
        repo = ROOT
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if not head:
            self.skipTest("not a git checkout")
        # The schema must already be committed at that revision for this to be a
        # protocol revision; otherwise the validator must refuse it.
        committed = subprocess.run(["git", "-C", str(repo), "show", f"{head}:schemas/feature-packet.schema.json"],
                                   capture_output=True, text=True)
        packet = load("feature-exact.json")
        packet["workflow_ref"] = head
        if committed.returncode != 0:
            with self.assertRaises(feature_packet.PacketError) as caught:
                feature_packet.validate(packet, workflow_repo=repo)
            self.assertEqual(caught.exception.code, "workflow_ref_unsupported")
        else:
            feature_packet.validate(packet, workflow_repo=repo)


class NegativeTests(unittest.TestCase):
    def assertRefused(self, packet, code, **kwargs):
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate(packet, check_protocol_commit=False, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_an_unsupported_packet_version_is_refused(self):
        packet = load("feature-exact.json")
        packet["packet_version"] = "rizzstack.feature-packet/0"
        self.assertRefused(packet, "packet_schema")  # schema const rejects it first

    def test_an_invalid_workflow_revision_is_refused(self):
        packet = load("feature-exact.json")
        packet["workflow_ref"] = "main"
        self.assertRefused(packet, "packet_schema")

    def test_a_mutated_contract_is_refused(self):
        packet = load("feature-exact.json")
        packet["contract"]["outcome"]["summary"] = "something else entirely"
        self.assertRefused(packet, "contract_hash_mismatch")

    def test_a_mutated_contract_hash_is_refused(self):
        packet = load("feature-exact.json")
        packet["contract_sha256"] = "0" * 64
        self.assertRefused(packet, "contract_hash_mismatch")

    def test_changed_acceptance_ids_are_refused(self):
        packet = load("feature-exact.json")
        packet["acceptance_ids"] = ["AC-999"]
        self.assertRefused(packet, "acceptance_mismatch")

    def test_a_dropped_approved_test_is_refused(self):
        packet = load("feature-exact.json")
        packet["tests"] = ["tests/other.py::test_other"]
        self.assertRefused(packet, "tests_mismatch")

    def test_a_wider_write_scope_is_refused(self):
        packet = load("feature-exact.json")
        packet["scope"]["lease"] = ["smoke/answer.py", "src/secret.py"]
        self.assertRefused(packet, "scope_mismatch")

    def test_an_exact_packet_with_a_different_revision_is_refused(self):
        packet = load("feature-exact.json")
        packet["source_policy"]["revision"] = "f" * 40
        self.assertRefused(packet, "source_policy_mismatch")

    def test_a_descendant_packet_without_a_policy_id_is_refused(self):
        packet = load("feature-descendant.json")
        del packet["source_policy"]["policy_id"]
        self.assertRefused(packet, "packet_schema")

    def test_two_dependencies_are_refused_rather_than_partially_supported(self):
        packet = load("feature-descendant.json")
        packet["source_policy"]["dependencies"] = ["feature-a", "feature-c"]
        self.assertRefused(packet, "packet_schema")

    def test_missing_authorization_provenance_is_refused(self):
        packet = load("feature-exact.json")
        packet["authorization"]["reference"] = ""
        self.assertRefused(packet, "packet_schema")

    def test_dropped_human_gates_are_refused(self):
        packet = load("feature-exact.json")
        packet["human_gates"] = []
        self.assertRefused(packet, "packet_schema")

    def test_a_different_validator_at_the_pinned_ref_is_refused(self):
        repo = ROOT
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if not head:
            self.skipTest("not a git checkout")
        committed = subprocess.run(["git", "-C", str(repo), "show", f"{head}:schemas/feature-packet.schema.json"],
                                   capture_output=True, text=True)
        if committed.returncode != 0:
            self.skipTest("schema not committed at HEAD yet")
        # Simulate drift: a packet pinned to this commit validates only while the
        # working schema equals the committed one.
        packet = load("feature-exact.json")
        packet["workflow_ref"] = head
        feature_packet.validate(packet, workflow_repo=repo)  # baseline is consistent
        original = feature_packet.SCHEMA_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                drifted = Path(tmp) / "feature-packet.schema.json"
                drifted.write_text(json.loads(original.read_text()) and original.read_text().replace('"minItems": 1', '"minItems": 1 '))
                feature_packet.SCHEMA_PATH = drifted
                with self.assertRaises(feature_packet.PacketError) as caught:
                    feature_packet.validate(packet, workflow_repo=repo)
                self.assertEqual(caught.exception.code, "validator_mismatch")
        finally:
            feature_packet.SCHEMA_PATH = original


if __name__ == "__main__":
    unittest.main()
