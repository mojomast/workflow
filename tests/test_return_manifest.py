"""Conformance tests for rizzstack.return/1 (schemas/return-manifest.schema.json)."""

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
import return_manifest  # noqa: E402
from workflow import acdd  # noqa: E402

EXAMPLES = ROOT / "schemas" / "examples"
SCHEMA = ROOT / "schemas" / "return-manifest.schema.json"
ACCEPTED = "c" * 40


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def sealed(manifest: dict) -> dict:
    return return_manifest.seal(manifest)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def strip_generated(value):
    """Independent oracle for the digest body: no generated_at anywhere."""
    if isinstance(value, dict):
        return {key: strip_generated(item) for key, item in value.items() if key != "generated_at"}
    if isinstance(value, list):
        return [strip_generated(item) for item in value]
    return value


def oracle_digest(manifest: dict) -> str:
    body = {key: value for key, value in manifest.items() if key != "evidence_digest"}
    return hashlib.sha256(canonical(strip_generated(body)).encode("utf-8")).hexdigest()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def resolution_record() -> dict:
    """The stage-2 record the dependent return example claims to answer."""
    packet = load("feature-descendant.json")
    template = copy.deepcopy(packet["contract_template"])
    template["source_rev"] = ACCEPTED
    frozen = acdd.freeze_contract(template, approved_by="policy-b", approved_at="2026-11-13T00:00:00Z")
    return {
        "resolution_version": "rizzstack.source-resolution/1",
        "packet_digest": feature_packet.packet_digest(packet),
        "policy_id": "policy-b",
        "policy_digest": "d" * 64,
        "dependency_job": "job_a",
        "dependency_feature": "feature-a",
        "accepted_commit": ACCEPTED,
        "derived_source_rev": ACCEPTED,
        "contract": frozen,
        "contract_sha256": acdd.check_frozen(frozen),
        "at": "2026-11-13T00:00:00Z",
    }


class ExampleTests(unittest.TestCase):
    def test_the_exact_example_validates_against_the_schema_and_semantics(self):
        manifest = return_manifest.validate(load("return-exact.json"))
        self.assertEqual(manifest["feature_id"], "feature-a")
        self.assertIsNone(manifest["descendant"])
        self.assertIsNone(manifest["transport"])

    def test_the_dependent_example_validates_against_the_schema_and_semantics(self):
        manifest = return_manifest.validate(load("return-dependent.json"))
        self.assertEqual(manifest["feature_id"], "feature-b")
        self.assertEqual(manifest["descendant"]["accepted_commit"], manifest["repository"]["source_rev"])
        self.assertEqual(manifest["authorization"]["authority"], "descendant-policy")

    def test_the_examples_bind_the_packet_examples(self):
        pairs = (
            ("return-exact.json", "feature-exact.json"),
            ("return-dependent.json", "feature-descendant.json"),
        )
        for return_name, packet_name in pairs:
            self.assertEqual(load(return_name)["packet_digest"], feature_packet.packet_digest(load(packet_name)),
                             f"{return_name} does not bind {packet_name}")

    def test_the_exact_example_carries_the_frozen_contract_hash(self):
        manifest = load("return-exact.json")
        packet = load("feature-exact.json")
        self.assertEqual(manifest["contract"]["id"], packet["contract"]["id"])
        self.assertEqual(manifest["contract"]["sha256"], packet["contract_sha256"])

    def test_the_dependent_example_carries_the_source_bound_contract_hash(self):
        manifest = load("return-dependent.json")
        record = resolution_record()
        self.assertEqual(manifest["contract"]["id"], record["contract"]["id"])
        self.assertEqual(manifest["contract"]["sha256"], record["contract_sha256"])

    def test_the_dependent_example_binds_a_real_source_resolution_record(self):
        manifest = load("return-dependent.json")
        record = resolution_record()
        feature_packet.validate_source_resolution(record, packet=load("feature-descendant.json"),
                                                  accepted_commit=ACCEPTED)
        self.assertEqual(manifest["descendant"]["source_resolution_digest"],
                         hashlib.sha256(canonical(record).encode("utf-8")).hexdigest())
        self.assertEqual(manifest["descendant"]["policy_id"], record["policy_id"])
        self.assertEqual(manifest["descendant"]["policy_digest"], record["policy_digest"])
        self.assertEqual(manifest["descendant"]["dependency_feature"], record["dependency_feature"])
        self.assertEqual(manifest["descendant"]["dependency_job"], record["dependency_job"])

    def test_the_examples_carry_no_volatile_timestamp(self):
        for name in ("return-exact.json", "return-dependent.json"):
            text = (EXAMPLES / name).read_text(encoding="utf-8")
            self.assertNotIn("generated_at", text, f"{name} embeds a volatile timestamp")
            manifest = load(name)
            self.assertEqual(manifest["evidence_digest"], oracle_digest(manifest), name)

    def test_the_examples_pin_one_schema_bearing_ancestor(self):
        exact = load("return-exact.json")
        dependent = load("return-dependent.json")
        pin = exact["workflow_ref"]
        self.assertEqual(dependent["workflow_ref"], pin)
        self.assertEqual(len(pin), 40)
        self.assertEqual(git("cat-file", "-e", f"{pin}^{{commit}}").returncode, 0, f"{pin} is not a commit here")
        self.assertEqual(git("merge-base", "--is-ancestor", pin, "HEAD").returncode, 0,
                         f"{pin} is not an ancestor of HEAD")
        pinned = git("show", f"{pin}:schemas/return-manifest.schema.json")
        self.assertEqual(pinned.returncode, 0, f"{pin} does not bear the return schema")
        self.assertEqual(pinned.stdout, SCHEMA.read_text(encoding="utf-8"),
                         f"the return schema at {pin} differs from the enforced schema; repin the examples")

    def test_the_validator_cli_accepts_both_examples(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "return_manifest.py"),
             str(EXAMPLES / "return-exact.json"), str(EXAMPLES / "return-dependent.json")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count(": ok "), 2, result.stdout)


class DigestTests(unittest.TestCase):
    def test_evidence_digest_matches_an_independent_oracle(self):
        for name in ("return-exact.json", "return-dependent.json"):
            manifest = load(name)
            self.assertEqual(return_manifest.evidence_digest(manifest), oracle_digest(manifest), name)

    def test_sealing_after_an_edit_recomputes_the_digest(self):
        manifest = load("return-exact.json")
        before = manifest["evidence_digest"]
        manifest["limitations"] = ["integration was not authorized"]
        changed = sealed(manifest)
        self.assertNotEqual(changed["evidence_digest"], before)
        return_manifest.validate(changed)

    def test_generated_at_stays_outside_the_digest(self):
        manifest = load("return-exact.json")
        before = manifest["evidence_digest"]
        manifest["generated_at"] = "2026-11-13T19:00:00Z"
        self.assertEqual(return_manifest.evidence_digest(manifest), before)
        return_manifest.validate(manifest)  # the old digest still covers the body

    def test_digest_body_drops_generated_at_at_any_depth(self):
        manifest = {
            "generated_at": "2026-11-13T19:00:00Z",
            "verification": {"generated_at": "2026-11-13T19:00:01Z", "commit": "a" * 40},
            "kept": [{"generated_at": "x", "value": 1}],
        }
        body = return_manifest.digest_body(manifest)
        self.assertNotIn("generated_at", body)
        self.assertNotIn("generated_at", body["verification"])
        self.assertNotIn("generated_at", body["kept"][0])
        self.assertEqual(body["verification"]["commit"], "a" * 40)
        self.assertEqual(body["kept"][0]["value"], 1)

    def test_pending_receiver_decision_is_the_only_generated_shape(self):
        decision = return_manifest.pending_receiver_decision()
        self.assertEqual(decision, {"status": "pending", "decided_by": None,
                                    "decided_at": None, "note": None})
        decision["status"] = "accepted"  # a caller mutating its copy cannot poison the module
        self.assertEqual(return_manifest.pending_receiver_decision()["status"], "pending")


class AcceptanceStatusTests(unittest.TestCase):
    def manifest_with(self, status: str, evidence: list[str]) -> dict:
        manifest = load("return-exact.json")
        manifest["acceptance"][0]["status"] = status
        manifest["acceptance"][0]["evidence"] = evidence
        return sealed(manifest)

    def test_a_pass_with_evidence_is_accepted(self):
        manifest = self.manifest_with("PASS", ["evidence/2026-11-13-feature-a/verify.log"])
        self.assertEqual(return_manifest.validate(manifest)["acceptance"][0]["status"], "PASS")

    def test_a_fail_with_evidence_is_accepted(self):
        return_manifest.validate(self.manifest_with("FAIL", ["evidence/2026-11-13-feature-a/fail.log"]))

    def test_a_not_run_criterion_is_accepted_with_empty_evidence(self):
        return_manifest.validate(self.manifest_with("NOT RUN", []))

    def test_a_blocked_criterion_is_accepted_with_empty_evidence(self):
        return_manifest.validate(self.manifest_with("BLOCKED", []))

    def test_an_unverified_criterion_is_accepted(self):
        return_manifest.validate(self.manifest_with("UNVERIFIED", ["evidence/2026-11-13-feature-a/claim.md"]))

    def test_red_green_test_first_with_a_red_record_is_accepted(self):
        manifest = load("return-exact.json")
        manifest["red_green"]["test_first"] = True
        manifest["red_green"]["red"] = {
            "record_path": "evidence/2026-11-13-feature-a/0001-red.json",
            "sha256": "1" * 64,
            "revision": "a" * 40,
            "phase": "red",
        }
        return_manifest.validate(sealed(manifest))

    def test_an_integrated_return_populates_the_whole_integration_block(self):
        manifest = load("return-dependent.json")
        integration = manifest["integration"]
        self.assertTrue(all(integration[field] is not None
                            for field in ("commit", "wave", "evidence", "accepted_wave_digest")))

    def test_transport_may_be_null_or_a_complete_receipt(self):
        self.assertIsNone(load("return-exact.json")["transport"])
        transport = load("return-dependent.json")["transport"]
        self.assertEqual(sorted(transport), ["mirror_ref", "receipt_path", "source_sha"])


class NegativeTests(unittest.TestCase):
    def assertRefused(self, manifest: dict, code: str, *, reseal: bool = True) -> return_manifest.ReturnError:
        if reseal:
            manifest = sealed(manifest)
        with self.assertRaises(return_manifest.ReturnError) as caught:
            return_manifest.validate(manifest)
        self.assertEqual(caught.exception.code, code, caught.exception.message)
        return caught.exception

    def test_an_unsupported_version_is_refused(self):
        manifest = load("return-exact.json")
        manifest["schema"] = "rizzstack.return/0"
        self.assertRefused(manifest, "return_version_unsupported")

    def test_a_pass_without_evidence_is_refused(self):
        manifest = load("return-exact.json")
        manifest["acceptance"][0]["evidence"] = []
        error = self.assertRefused(manifest, "pass_without_evidence")
        self.assertIn("AC-001", error.message)

    def test_a_filled_receiver_decision_is_refused(self):
        manifest = load("return-exact.json")
        manifest["receiver_decision"]["status"] = "accepted"
        error = self.assertRefused(manifest, "receiver_decision_not_pending")
        self.assertIn("pending", error.message)

    def test_a_named_receiver_is_refused(self):
        manifest = load("return-exact.json")
        manifest["receiver_decision"]["decided_by"] = "reviewer"
        self.assertRefused(manifest, "receiver_decision_not_pending")

    def test_a_receiver_note_is_refused(self):
        manifest = load("return-exact.json")
        manifest["receiver_decision"]["note"] = "looks good"
        self.assertRefused(manifest, "receiver_decision_not_pending")

    def test_a_digest_mismatch_is_refused(self):
        manifest = load("return-exact.json")
        manifest["limitations"] = ["edited after sealing"]
        self.assertRefused(manifest, "evidence_digest_mismatch", reseal=False)

    def test_a_missing_acceptance_block_is_refused(self):
        manifest = load("return-exact.json")
        del manifest["acceptance"]
        self.assertRefused(manifest, "return_schema")

    def test_an_empty_acceptance_block_is_refused(self):
        manifest = load("return-exact.json")
        manifest["acceptance"] = []
        self.assertRefused(manifest, "return_schema")

    def test_an_unknown_acceptance_status_is_refused(self):
        manifest = load("return-exact.json")
        manifest["acceptance"][0]["status"] = "PASSED"
        self.assertRefused(manifest, "return_schema")

    def test_a_lowercase_fail_status_is_refused(self):
        manifest = load("return-exact.json")
        manifest["acceptance"][0]["status"] = "failed"
        self.assertRefused(manifest, "return_schema")

    def test_duplicate_acceptance_ids_are_refused(self):
        manifest = load("return-exact.json")
        manifest["acceptance"].append(copy.deepcopy(manifest["acceptance"][0]))
        self.assertRefused(manifest, "acceptance_duplicate")

    def test_a_descendant_block_on_an_m1_authority_is_refused(self):
        manifest = load("return-dependent.json")
        manifest["authorization"]["authority"] = "m1-authorization"
        self.assertRefused(manifest, "descendant_authority_mismatch")

    def test_an_exact_return_with_a_descendant_authority_is_refused(self):
        manifest = load("return-exact.json")
        manifest["authorization"]["authority"] = "descendant-policy"
        self.assertRefused(manifest, "descendant_authority_mismatch")

    def test_a_descendant_commit_that_is_not_the_source_revision_is_refused(self):
        manifest = load("return-dependent.json")
        manifest["descendant"]["accepted_commit"] = "e" * 40
        self.assertRefused(manifest, "descendant_revision_mismatch")

    def test_an_incomplete_descendant_block_is_refused(self):
        manifest = load("return-dependent.json")
        del manifest["descendant"]["accepted_commit"]
        self.assertRefused(manifest, "return_schema")

    def test_an_incomplete_integration_block_is_refused(self):
        manifest = load("return-dependent.json")
        manifest["integration"]["wave"] = None
        self.assertRefused(manifest, "integration_incomplete")

    def test_a_partial_transport_block_is_refused(self):
        manifest = load("return-dependent.json")
        del manifest["transport"]["receipt_path"]
        self.assertRefused(manifest, "return_schema")

    def test_a_test_first_claim_without_a_red_record_is_refused(self):
        manifest = load("return-exact.json")
        manifest["red_green"]["test_first"] = True
        self.assertRefused(manifest, "red_green_inconsistent")

    def test_a_red_record_with_test_first_false_is_refused(self):
        manifest = load("return-exact.json")
        manifest["red_green"]["red"] = {
            "record_path": "evidence/2026-11-13-feature-a/0001-red.json",
            "sha256": "1" * 64,
            "revision": "a" * 40,
            "phase": "red",
        }
        self.assertRefused(manifest, "red_green_inconsistent")

    def test_a_bad_packet_digest_shape_is_refused(self):
        manifest = load("return-exact.json")
        manifest["packet_digest"] = "not-a-digest"
        self.assertRefused(manifest, "return_schema")

    def test_a_bad_workflow_ref_is_refused(self):
        manifest = load("return-exact.json")
        manifest["workflow_ref"] = "94257fc"
        self.assertRefused(manifest, "return_schema")

    def test_a_bad_contract_hash_is_refused(self):
        manifest = load("return-exact.json")
        manifest["contract"]["sha256"] = "f" * 63
        self.assertRefused(manifest, "return_schema")

    def test_an_unknown_authority_is_refused(self):
        manifest = load("return-exact.json")
        manifest["authorization"]["authority"] = "trust-me"
        self.assertRefused(manifest, "return_schema")

    def test_an_extra_top_level_field_is_refused(self):
        manifest = load("return-exact.json")
        manifest["outcome"] = "complete"
        self.assertRefused(manifest, "return_schema")

    def test_a_missing_receiver_decision_is_refused(self):
        manifest = load("return-exact.json")
        del manifest["receiver_decision"]
        self.assertRefused(manifest, "return_schema")

    def test_an_empty_limitation_is_refused(self):
        manifest = load("return-exact.json")
        manifest["limitations"] = [""]
        self.assertRefused(manifest, "return_schema")

    def test_an_attempt_with_an_invalid_revision_is_refused(self):
        manifest = load("return-exact.json")
        manifest["attempts"][0]["source_rev"] = "main"
        self.assertRefused(manifest, "return_schema")


if __name__ == "__main__":
    unittest.main()
