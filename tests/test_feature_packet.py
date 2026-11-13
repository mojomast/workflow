"""Feature-packet and source-resolution validation tests."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
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
SCHEMAS = ROOT / "schemas"
ACCEPTED = "c" * 40


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def packet_digest(packet: dict) -> str:
    """Independent oracle for the canonical digest the resolution record binds."""
    return hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


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


class PinnedProtocolTests(unittest.TestCase):
    """The examples must exercise the pinned protocol, not fall back to an unchecked path."""

    def test_the_examples_pin_one_real_schema_bearing_ancestor(self):
        exact = load("feature-exact.json")
        descendant = load("feature-descendant.json")
        self.assertEqual(exact["workflow_ref"], descendant["workflow_ref"])
        pin = exact["workflow_ref"]
        self.assertEqual(len(pin), 40)
        self.assertEqual(git("cat-file", "-e", f"{pin}^{{commit}}").returncode, 0, f"{pin} is not a commit here")
        self.assertEqual(git("merge-base", "--is-ancestor", pin, "HEAD").returncode, 0,
                         f"{pin} is not an ancestor of the examples")
        for name in ("feature-packet.schema.json", "source-resolution.schema.json"):
            pinned = git("show", f"{pin}:schemas/{name}")
            self.assertEqual(pinned.returncode, 0, f"{pin} does not bear {name}")
            self.assertEqual(pinned.stdout, (SCHEMAS / name).read_text(encoding="utf-8"),
                             f"{name} at {pin} differs from the enforced schema; repin the examples")

    def test_the_exact_example_validates_against_the_pinned_protocol(self):
        packet = feature_packet.validate(load("feature-exact.json"), workflow_repo=ROOT, check_protocol_commit=True)
        self.assertEqual(packet["source_policy"]["kind"], "exact")

    def test_the_dependent_intent_example_validates_against_the_pinned_protocol(self):
        packet = feature_packet.validate(load("feature-descendant.json"), workflow_repo=ROOT, check_protocol_commit=True)
        self.assertEqual(packet["source_policy"]["kind"], "descendant")
        self.assertNotIn("contract", packet)  # intent carries a template, not a fabricated frozen contract
        self.assertNotIn("contract_sha256", packet)


class PositiveTests(unittest.TestCase):
    def test_a_source_resolution_binds_the_intent_to_the_accepted_commit(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, ACCEPTED)
        out = feature_packet.validate_source_resolution(record, packet=packet, accepted_commit=ACCEPTED)
        self.assertEqual(out["derived_source_rev"], ACCEPTED)
        self.assertEqual(record["contract"]["source_rev"], ACCEPTED)
        self.assertEqual(record["contract"]["scope"], packet["contract_template"]["scope"])
        self.assertEqual(record["contract"]["acceptance_criteria"], packet["contract_template"]["acceptance_criteria"])

    def test_the_validator_digest_equals_the_independent_oracle(self):
        for name in ("feature-exact.json", "feature-descendant.json"):
            packet = load(name)
            self.assertEqual(feature_packet.packet_digest(packet), packet_digest(packet), name)

    def test_partial_authorization_limits_constrain_only_the_stated_dimension(self):
        packet = load("feature-exact.json")
        packet["authorization"]["limits"] = {"bees": 1}
        packet["budget"] = {"bees": 1, "wall_clock_s": 999999}
        feature_packet.validate(packet, check_protocol_commit=False)

    def test_an_exact_packet_may_pin_the_contracts_content_revision(self):
        packet = load("feature-exact.json")
        content_rev = "b" * 64
        contract = copy.deepcopy(packet["contract"])
        contract["source_rev"] = content_rev
        frozen = acdd.freeze_contract(contract, approved_by="reviewer", approved_at="2026-11-13T00:00:00Z")
        packet["contract"] = frozen
        packet["contract_sha256"] = acdd.check_frozen(frozen)
        packet["source_policy"]["revision"] = content_rev
        feature_packet.validate(packet, check_protocol_commit=False)


class ProtocolRefTests(unittest.TestCase):
    def validate(self, packet, **kwargs):
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate(packet, workflow_repo=ROOT, **kwargs)
        return caught.exception

    def test_an_unknown_commit_is_refused(self):
        packet = load("feature-exact.json")
        unknown = "f" * 40
        self.assertNotEqual(git("cat-file", "-e", f"{unknown}^{{commit}}").returncode, 0)
        packet["workflow_ref"] = unknown
        self.assertEqual(self.validate(packet).code, "workflow_ref_unknown")

    def test_a_commit_that_predates_the_schema_is_refused(self):
        adding = git("log", "--format=%H", "--diff-filter=A", "--", "schemas/feature-packet.schema.json").stdout.split()
        self.assertTrue(adding, "the schema has no adding commit")
        before = git("rev-parse", f"{adding[-1]}^").stdout.strip()
        self.assertTrue(before, "the schema-adding commit has no parent to test")
        self.assertNotEqual(git("cat-file", "-e", f"{before}:schemas/feature-packet.schema.json").returncode, 0,
                            f"{before} already bears the schema; pick an older fixture")
        packet = load("feature-exact.json")
        packet["workflow_ref"] = before
        self.assertEqual(self.validate(packet).code, "workflow_ref_unsupported")

    def test_schema_drift_at_the_pinned_commit_is_refused(self):
        packet = load("feature-exact.json")
        text = feature_packet.SCHEMA_PATH.read_text(encoding="utf-8")
        drifted = text.replace('"title": "Rizzstack feature packet', '"title": "Drifted feature packet', 1)
        self.assertNotEqual(text, drifted)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feature-packet.schema.json"
            path.write_text(drifted, encoding="utf-8")
            original = feature_packet.SCHEMA_PATH
            feature_packet.SCHEMA_PATH = path
            try:
                self.assertEqual(self.validate(packet).code, "validator_mismatch")
            finally:
                feature_packet.SCHEMA_PATH = original


class TwoStagePinTests(unittest.TestCase):
    """A dependent feature is interpreted under both stages, so its pin must bear both schemas."""

    def make_repo(self, tmp: str, *, with_resolution: bool) -> tuple[Path, str]:
        repo = Path(tmp) / "protocol"
        (repo / "schemas").mkdir(parents=True)
        for name in ("feature-packet.schema.json", "source-resolution.schema.json"):
            if name == "source-resolution.schema.json" and not with_resolution:
                continue
            shutil.copyfile(SCHEMAS / name, repo / "schemas" / name)
        for args in (("init", "-q"), ("config", "user.email", "test@example.com"), ("config", "user.name", "test"), ("add", "-A"), ("commit", "-qm", "one")):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        return repo, sha

    def commit_drift(self, repo: Path, name: str) -> str:
        path = repo / "schemas" / name
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace('"title": "Rizzstack', '"title": "Drifted', 1), encoding="utf-8")
        for args in (("add", "-A"), ("commit", "-qm", "drift")):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_a_dependent_pin_must_bear_the_resolution_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sha = self.make_repo(tmp, with_resolution=False)
            packet = load("feature-descendant.json")
            packet["workflow_ref"] = sha
            with self.assertRaises(feature_packet.PacketError) as caught:
                feature_packet.validate(packet, workflow_repo=repo)
            self.assertEqual(caught.exception.code, "workflow_ref_unsupported")

    def test_resolution_schema_drift_at_the_pin_is_refused_for_a_dependent_packet_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, first = self.make_repo(tmp, with_resolution=True)
            packet = load("feature-descendant.json")
            packet["workflow_ref"] = first
            feature_packet.validate(packet, workflow_repo=repo)  # both schemas identical at the pin
            second = self.commit_drift(repo, "source-resolution.schema.json")
            packet["workflow_ref"] = second
            with self.assertRaises(feature_packet.PacketError) as caught:
                feature_packet.validate(packet, workflow_repo=repo)
            self.assertEqual(caught.exception.code, "validator_mismatch")
            exact = load("feature-exact.json")
            exact["workflow_ref"] = second  # an exact feature does not read the second stage
            feature_packet.validate(exact, workflow_repo=repo)


class NegativeTests(unittest.TestCase):
    def assertRefused(self, packet, code, **kwargs):
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate(packet, check_protocol_commit=False, **kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception.message)

    def assertResolutionRefused(self, record, packet, code):
        with self.assertRaises(feature_packet.PacketError) as caught:
            feature_packet.validate_source_resolution(record, packet=packet, accepted_commit=ACCEPTED)
        self.assertEqual(caught.exception.code, code, caught.exception.message)

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

    def test_a_budget_wider_in_one_stated_dimension_is_refused(self):
        packet = load("feature-exact.json")
        packet["authorization"]["limits"] = {"wall_clock_s": 60}
        self.assertRefused(packet, "budget_exceeded")

    def test_an_exact_packet_with_a_different_revision_is_refused(self):
        packet = load("feature-exact.json")
        packet["source_policy"]["revision"] = "f" * 40
        self.assertRefused(packet, "source_policy_mismatch")

    def test_an_exact_packet_cannot_carry_a_template(self):
        packet = load("feature-exact.json")
        packet["contract_template"] = copy.deepcopy(load("feature-descendant.json")["contract_template"])
        self.assertRefused(packet, "packet_schema")

    def test_an_intent_packet_cannot_carry_a_frozen_contract_claim(self):
        packet = load("feature-descendant.json")
        packet["contract"] = packet["contract_template"]
        packet["contract_sha256"] = "0" * 64
        self.assertRefused(packet, "packet_schema")

    def test_an_intent_packet_cannot_carry_a_lone_contract_hash(self):
        packet = load("feature-descendant.json")
        packet["contract_sha256"] = "0" * 64
        self.assertRefused(packet, "packet_schema")

    def test_an_intent_packet_cannot_pre_claim_a_resolution(self):
        packet = load("feature-descendant.json")
        packet["source_resolution_ref"] = "resolution.json"
        self.assertRefused(packet, "packet_schema")

    def test_two_dependencies_are_refused(self):
        packet = load("feature-descendant.json")
        packet["source_policy"]["dependencies"] = ["feature-a", "feature-c"]
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
        record = resolution_for(packet, ACCEPTED)
        record["derived_source_rev"] = "e" * 40
        self.assertResolutionRefused(record, packet, "resolution_revision_mismatch")

    def test_a_resolution_that_changes_scope_is_refused(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, ACCEPTED,
                                mutate=lambda c: c["scope"].__setitem__("assigned_files", ["src/other.py"]))
        self.assertResolutionRefused(record, packet, "resolution_scope_changed")

    def test_a_resolution_that_changes_another_contract_field_is_refused(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, ACCEPTED, mutate=lambda c: c.__setitem__("title", "widened"))
        self.assertResolutionRefused(record, packet, "resolution_contract_changed")

    def test_a_resolution_that_binds_another_packet_is_refused(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, ACCEPTED)
        record["packet_digest"] = "d" * 64
        self.assertResolutionRefused(record, packet, "resolution_packet_digest")

    def test_a_resolution_against_an_exact_packet_is_refused(self):
        record = resolution_for(load("feature-descendant.json"), ACCEPTED)
        self.assertResolutionRefused(record, load("feature-exact.json"), "resolution_not_applicable")

    def test_an_unfrozen_source_bound_contract_is_refused(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, ACCEPTED)
        del record["contract"]["review"]
        self.assertResolutionRefused(record, packet, "resolution_contract_not_frozen")

    def test_a_malformed_resolution_record_is_refused(self):
        packet = load("feature-descendant.json")
        record = resolution_for(packet, ACCEPTED)
        del record["at"]
        self.assertResolutionRefused(record, packet, "resolution_schema")


if __name__ == "__main__":
    unittest.main()
