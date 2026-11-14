"""Conformance tests for rizzstack.recovery/1 and the RETURN manifest's recovery array."""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "reference"))

import recovery  # noqa: E402
import return_manifest  # noqa: E402
from workflow import acdd  # noqa: E402

EXAMPLES = ROOT / "schemas" / "examples"
SCHEMA = ROOT / "schemas" / "recovery.schema.json"


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def oracle_digest(request: dict) -> str:
    body = {key: value for key, value in request.items() if key != "request_digest"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


@functools.lru_cache(maxsize=1)
def contracts() -> tuple[dict, dict]:
    """The two real frozen acdd/1 contracts the examples name.

    The failed contract selects a node id that does not exist; the corrected one
    selects the file that contains the behaviour. Built from the existing
    feature-exact example so the recovery fixtures stay ordinary contracts.
    """
    base = json.loads((EXAMPLES / "feature-exact.json").read_text(encoding="utf-8"))["contract"]

    def build(tests: list[str], approved_at: str) -> dict:
        body = copy.deepcopy(base)
        body["id"] = "SMOKE-R"
        body["title"] = "answer() returns 42 under the recovery example"
        body["outcome"]["summary"] = body["title"]
        body["acceptance_criteria"][0]["tests"] = list(tests)
        return acdd.freeze_contract(body, approved_by="reviewer", approved_at=approved_at)

    failed = build(["tests/test_smoke.py::AnswerTests::test_answer_is_42"], "2026-11-13T18:00:00Z")
    corrected = build(["tests/test_smoke.py"], "2026-11-13T19:35:00Z")
    return failed, corrected


EVIDENCE = {
    "implementation": [{"kind": "test", "reference": "evidence/verify-att-0007.log"}],
    "specification": [{"kind": "log", "reference": "evidence/verify-att-0007.log"}],
    "environment": [{"kind": "environment", "reference": "evidence/host-probe.log"}],
    "infrastructure": [{"kind": "infrastructure", "reference": "evidence/launcher.log"}],
    "integration": [{"kind": "conflict", "reference": "evidence/integrate-wave.log",
                     "paths": ["smoke/answer.py"]}],
}

CODES = {
    "implementation": "test_failed",
    "specification": "test_not_found",
    "environment": "toolchain_missing",
    "infrastructure": "launcher_unavailable",
    "integration": "merge_conflict",
}


def make_request(failure_class: str = "implementation", *, code: str | None = None,
                 evidence: list[dict] | None = None, permitted: bool = False,
                 corrections: int = 0, allowed: list[str] | None = None,
                 max_attempts: int = 2) -> dict:
    request = copy.deepcopy(load("recovery-request.json"))
    request["failure"] = {
        "class": failure_class,
        "code": code or CODES[failure_class],
        "evidence": copy.deepcopy(EVIDENCE[failure_class] if evidence is None else evidence),
        "rationale": "The recorded evidence supports this class and this code.",
    }
    request["supersession_permitted"] = permitted
    request["envelope"] = {
        "max_attempts_per_task": max_attempts,
        "contract_corrections_allowed": corrections,
        "corrected_tests_allowed": list(allowed or []),
    }
    return recovery.seal_request(request)


def make_decision(request: dict, *, decision: str = "retry", adapter: str = "codex-cli",
                  corrected_tests: list[str] | None = None, supersedes: dict | None = None) -> dict:
    if corrected_tests is None:
        corrected_tests = list(request["envelope"]["corrected_tests_allowed"]) if decision == "supersede" else []
    if supersedes is None and decision == "supersede":
        _, corrected = contracts()
        supersedes = {
            "contract_id": request["contract"]["id"],
            "contract_sha256": request["contract"]["sha256"],
            "new_contract_id": request["contract"]["id"],
            "new_contract_sha256": acdd.check_frozen(corrected),
        }
    return {
        "schema": "rizzstack.recovery/1",
        "request_id": request["request_id"],
        "request_digest": request["request_digest"],
        "adapter": adapter,
        "decision": decision,
        "corrected_tests": list(corrected_tests),
        "supersedes": copy.deepcopy(supersedes),
        "rationale": "The decision answers the outstanding question inside the envelope.",
        "decided_at": "2026-11-13T19:40:00Z",
    }


class RefusalMixin(unittest.TestCase):
    def assertRefused(self, operation, code: str) -> recovery.RecoveryError:
        with self.assertRaises(recovery.RecoveryError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code, caught.exception.message)
        return caught.exception


class ExampleTests(RefusalMixin):
    def test_the_request_example_validates(self):
        request = recovery.validate_request(load("recovery-request.json"))
        self.assertEqual(request["failure"]["class"], "specification")
        self.assertEqual(request["failure"]["code"], "test_not_found")
        self.assertTrue(request["supersession_permitted"])

    def test_the_decision_example_validates_against_its_request(self):
        request = load("recovery-request.json")
        decision = recovery.validate_decision(load("recovery-decision.json"), request=request,
                                              attempts_used=1, corrections_used=0)
        self.assertEqual(decision["decision"], "supersede")
        self.assertEqual(decision["adapter"], "codex-cli")

    def test_the_pair_validates_as_a_unit(self):
        pair = recovery.validate_pair(load("recovery-request.json"), load("recovery-decision.json"),
                                      attempts_used=1)
        self.assertEqual(pair["request"]["request_id"], pair["decision"]["request_id"])

    def test_the_request_example_is_sealed(self):
        request = load("recovery-request.json")
        self.assertEqual(request["request_digest"], oracle_digest(request))
        self.assertEqual(request["request_digest"], recovery.request_digest(request))

    def test_the_decision_example_binds_the_request_digest(self):
        request = load("recovery-request.json")
        decision = load("recovery-decision.json")
        self.assertEqual(decision["request_digest"], request["request_digest"])
        self.assertEqual(decision["request_id"], request["request_id"])

    def test_the_request_example_carries_no_volatile_timestamp(self):
        text = (EXAMPLES / "recovery-request.json").read_text(encoding="utf-8")
        for volatile in ("generated_at", "decided_at"):
            self.assertNotIn(volatile, text)
        self.assertEqual(recovery.seal_request(load("recovery-request.json")),
                         load("recovery-request.json"))

    def test_the_example_contracts_are_real_frozen_acdd_contracts(self):
        failed, corrected = contracts()
        request = load("recovery-request.json")
        decision = load("recovery-decision.json")
        self.assertEqual(request["contract"]["sha256"], acdd.check_frozen(failed))
        self.assertEqual(decision["supersedes"]["contract_sha256"], acdd.check_frozen(failed))
        self.assertEqual(decision["supersedes"]["new_contract_sha256"], acdd.check_frozen(corrected))
        self.assertEqual(decision["supersedes"]["contract_id"], failed["id"])
        self.assertEqual(decision["supersedes"]["new_contract_id"], corrected["id"])

    def test_the_corrected_contract_accepts_the_test_the_decision_names(self):
        _, corrected = contracts()
        decision = load("recovery-decision.json")
        selected = [test for criterion in corrected["acceptance_criteria"] for test in criterion["tests"]]
        self.assertEqual(selected, decision["corrected_tests"])
        self.assertEqual(decision["corrected_tests"], load("recovery-request.json")["envelope"]["corrected_tests_allowed"])

    def test_the_cli_validates_the_example_pair(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "recovery.py"), "request",
             str(EXAMPLES / "recovery-request.json")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(": ok ", result.stdout)
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "recovery.py"), "decision",
             str(EXAMPLES / "recovery-decision.json"),
             "--request", str(EXAMPLES / "recovery-request.json"), "--attempts-used", "1"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok recovery-feature-a-t1-0001", result.stdout)

    def test_the_cli_refuses_a_supersede_with_no_attempt_left(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "recovery.py"), "decision",
             str(EXAMPLES / "recovery-decision.json"),
             "--request", str(EXAMPLES / "recovery-request.json"), "--attempts-used", "2"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("budget_exhausted", result.stderr)

    def test_the_cli_seals_and_the_result_validates(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "recovery.py"), "seal",
             str(EXAMPLES / "recovery-request.json")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        seeded = json.loads(result.stdout)
        self.assertEqual(seeded, load("recovery-request.json"))
        recovery.validate_request(seeded)

    def test_the_cli_prints_the_return_entry(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "recovery.py"), "entry",
             "--request", str(EXAMPLES / "recovery-request.json"),
             "--decision", str(EXAMPLES / "recovery-decision.json"), "--attempts-used", "1"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)
        self.assertEqual(sorted(entry), ["adapter", "decision", "failure_class", "request_digest",
                                         "request_id", "supersession"])
        self.assertEqual(entry["supersession"]["supersedes"], "SMOKE-R")


class ShapeAndDigestTests(RefusalMixin):
    def test_the_schema_declares_both_documents(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("oneOf", schema)
        for name in ("request", "decision", "failure", "evidence", "envelope", "supersedes"):
            self.assertIn(name, schema["$defs"])

    def test_an_unsupported_request_version_is_refused(self):
        request = load("recovery-request.json")
        request["schema"] = "rizzstack.recovery/2"
        self.assertRefused(lambda: recovery.validate_request(request), "recovery_version_unsupported")

    def test_an_unsupported_decision_version_is_refused(self):
        request = load("recovery-request.json")
        decision = load("recovery-decision.json")
        decision["schema"] = "rizzstack.recovery/2"
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "recovery_version_unsupported")

    def test_a_request_edited_after_sealing_is_refused(self):
        request = load("recovery-request.json")
        request["envelope"]["max_attempts_per_task"] = 5
        self.assertRefused(lambda: recovery.validate_request(request), "request_digest_mismatch")

    def test_a_resealed_request_validates(self):
        request = load("recovery-request.json")
        request["envelope"]["max_attempts_per_task"] = 3
        request = recovery.seal_request(request)
        self.assertNotEqual(request["request_digest"], load("recovery-request.json")["request_digest"])
        recovery.validate_request(request)

    def test_the_request_digest_ignores_only_its_own_field(self):
        request = load("recovery-request.json")
        body = {key: value for key, value in request.items() if key != "request_digest"}
        self.assertEqual(recovery.request_digest(body), request["request_digest"])
        body["request_digest"] = "0" * 64
        self.assertEqual(recovery.request_digest(body), request["request_digest"])

    def test_the_decision_digest_is_over_the_whole_document(self):
        decision = load("recovery-decision.json")
        before = recovery.decision_digest(decision)
        decision["decision"] = "escalate"
        self.assertNotEqual(recovery.decision_digest(decision), before)

    def test_a_document_with_both_kinds_is_refused(self):
        document = load("recovery-decision.json")
        document["failure"] = copy.deepcopy(load("recovery-request.json")["failure"])
        self.assertRefused(lambda: recovery.document_kind(document), "recovery_ambiguous")

    def test_a_document_with_neither_kind_is_refused(self):
        self.assertRefused(lambda: recovery.document_kind({"schema": "rizzstack.recovery/1"}),
                           "recovery_schema")

    def test_an_unknown_request_field_is_refused(self):
        request = load("recovery-request.json")
        request["scope"] = ["smoke/answer.py"]
        self.assertRefused(lambda: recovery.validate_request(recovery.seal_request(request)),
                           "recovery_schema")

    def test_a_decision_cannot_carry_an_envelope(self):
        request = load("recovery-request.json")
        decision = load("recovery-decision.json")
        decision["envelope"] = {"max_attempts_per_task": 9, "contract_corrections_allowed": 9,
                                "corrected_tests_allowed": ["tests/test_smoke.py"]}
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "recovery_schema")

    def test_a_missing_outstanding_question_is_refused(self):
        request = load("recovery-request.json")
        del request["outstanding_question"]
        self.assertRefused(lambda: recovery.validate_request(recovery.seal_request(request)),
                           "recovery_schema")


class RequestSemanticTests(RefusalMixin):
    def test_an_unknown_failure_class_is_refused(self):
        request = make_request("implementation")
        request["failure"]["class"] = "flaky"
        self.assertRefused(lambda: recovery.validate_request(recovery.seal_request(request)),
                           "recovery_schema")

    def test_an_implementation_failure_cannot_use_a_specification_code(self):
        self.assertRefused(lambda: recovery.validate_request(
            make_request("implementation", code="test_not_found")), "failure_code_mismatch")

    def test_a_specification_failure_cannot_use_an_implementation_code(self):
        request = make_request("specification", permitted=True, corrections=1,
                              allowed=["tests/test_smoke.py"], code="test_failed")
        self.assertRefused(lambda: recovery.validate_request(request), "failure_code_mismatch")

    def test_specification_accepts_each_unusable_acceptance_code(self):
        for code in ("acceptance_uncovered", "test_not_found", "missing_test"):
            request = make_request("specification", code=code, permitted=True, corrections=1,
                                   allowed=["tests/test_smoke.py"])
            self.assertEqual(recovery.validate_request(request)["failure"]["code"], code)

    def test_an_implementation_failure_needs_a_test_or_command_record(self):
        request = make_request("implementation", evidence=[{"kind": "log", "reference": "evidence/verify.log"}])
        self.assertRefused(lambda: recovery.validate_request(request), "evidence_missing")

    def test_an_environment_failure_needs_an_environment_record(self):
        request = make_request("environment", evidence=[{"kind": "test", "reference": "evidence/verify.log"}])
        self.assertRefused(lambda: recovery.validate_request(request), "evidence_missing")

    def test_an_infrastructure_failure_needs_an_infrastructure_record(self):
        request = make_request("infrastructure", evidence=[{"kind": "log", "reference": "evidence/launcher.log"}])
        self.assertRefused(lambda: recovery.validate_request(request), "evidence_missing")

    def test_an_integration_failure_needs_conflict_paths(self):
        request = make_request("integration", evidence=[{"kind": "conflict", "reference": "evidence/integrate.log"}])
        self.assertRefused(lambda: recovery.validate_request(request), "conflict_evidence_incomplete")

    def test_an_integration_failure_accepts_a_conflict_record_with_paths(self):
        request = make_request("integration")
        self.assertEqual(recovery.validate_request(request)["failure"]["code"], "merge_conflict")

    def test_a_conflict_record_on_an_implementation_failure_is_refused(self):
        request = make_request("implementation", evidence=[
            {"kind": "test", "reference": "evidence/verify.log"},
            {"kind": "conflict", "reference": "evidence/integrate.log", "paths": ["smoke/answer.py"]},
        ])
        self.assertRefused(lambda: recovery.validate_request(request), "evidence_forbidden")

    def test_paths_on_a_non_conflict_record_are_refused(self):
        request = make_request("implementation", evidence=[
            {"kind": "test", "reference": "evidence/verify.log", "paths": ["smoke/answer.py"]},
        ])
        self.assertRefused(lambda: recovery.validate_request(request), "evidence_forbidden")

    def test_an_environment_record_on_an_integration_failure_is_refused(self):
        request = make_request("integration", evidence=[
            {"kind": "conflict", "reference": "evidence/integrate.log", "paths": ["smoke/answer.py"]},
            {"kind": "environment", "reference": "evidence/host.log"},
        ])
        self.assertRefused(lambda: recovery.validate_request(request), "evidence_forbidden")

    def test_an_empty_evidence_array_is_refused(self):
        request = make_request("implementation", evidence=[])
        self.assertRefused(lambda: recovery.validate_request(request), "recovery_schema")

    def test_supersession_permitted_on_a_non_specification_failure_is_refused(self):
        request = make_request("implementation", permitted=True, corrections=1, allowed=["tests/test_smoke.py"])
        self.assertRefused(lambda: recovery.validate_request(request), "supersession_not_permitted")

    def test_a_permission_without_a_correction_budget_is_refused(self):
        request = make_request("specification", permitted=True, corrections=0,
                               allowed=["tests/test_smoke.py"])
        self.assertRefused(lambda: recovery.validate_request(request), "envelope_widened")

    def test_a_correction_budget_without_a_permission_is_refused(self):
        request = make_request("specification", permitted=False, corrections=1)
        self.assertRefused(lambda: recovery.validate_request(request), "envelope_widened")

    def test_corrected_tests_without_a_budget_are_refused(self):
        request = make_request("specification", permitted=False, corrections=0,
                               allowed=["tests/test_smoke.py"])
        self.assertRefused(lambda: recovery.validate_request(request), "envelope_widened")

    def test_corrected_tests_allowed_only_outside_the_acceptance_pattern_are_refused(self):
        request = make_request("specification", permitted=True, corrections=1, allowed=["not a test id"])
        self.assertRefused(lambda: recovery.validate_request(request), "recovery_schema")

    def test_the_evidence_rationale_must_be_substantive(self):
        request = make_request("implementation")
        request["failure"]["rationale"] = "bad"
        self.assertRefused(lambda: recovery.validate_request(recovery.seal_request(request)),
                           "recovery_schema")


class DecisionSemanticTests(RefusalMixin):
    def test_an_implementation_retry_within_budget_is_accepted(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        self.assertEqual(recovery.validate_decision(decision, request=request, attempts_used=1)["decision"], "retry")

    def test_a_retry_at_the_attempt_limit_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=2),
                           "budget_exhausted")

    def test_escalation_is_legal_at_any_attempt_count(self):
        request = make_request("implementation")
        for used in (0, 1, 2):
            decision = make_decision(request, decision="escalate")
            self.assertEqual(recovery.validate_decision(decision, request=request,
                                                        attempts_used=used)["decision"], "escalate")

    def test_a_specification_retry_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="retry")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "decision_class_mismatch")

    def test_an_environment_retry_is_refused(self):
        request = make_request("environment")
        decision = make_decision(request, decision="retry")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=0),
                           "failure_class_no_dispatch")

    def test_an_infrastructure_retry_is_refused(self):
        request = make_request("infrastructure")
        decision = make_decision(request, decision="retry")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=0),
                           "failure_class_no_dispatch")

    def test_an_environment_supersede_is_refused(self):
        request = make_request("environment")
        decision = make_decision(request, decision="supersede", corrected_tests=["tests/test_smoke.py"])
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=0),
                           "failure_class_no_dispatch")

    def test_an_environment_escalation_is_the_only_legal_decision(self):
        request = make_request("environment")
        decision = make_decision(request, decision="escalate")
        recovery.validate_decision(decision, request=request, attempts_used=0)

    def test_a_valid_supersede_is_accepted(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede")
        validated = recovery.validate_decision(decision, request=request, attempts_used=1)
        self.assertEqual(validated["supersedes"]["contract_id"], request["contract"]["id"])

    def test_a_supersede_for_an_implementation_failure_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="supersede", corrected_tests=["tests/test_smoke.py"])
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "decision_class_mismatch")

    def test_a_supersede_without_permission_is_refused(self):
        request = make_request("specification")
        decision = make_decision(request, decision="supersede", corrected_tests=["tests/test_smoke.py"],
                                 supersedes={"contract_id": request["contract"]["id"],
                                             "contract_sha256": request["contract"]["sha256"],
                                             "new_contract_id": request["contract"]["id"],
                                             "new_contract_sha256": "e" * 64})
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "supersession_not_permitted")

    def test_a_supersede_with_no_correction_left_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request,
                                                              attempts_used=1, corrections_used=1),
                           "budget_exhausted")

    def test_a_supersede_at_the_attempt_limit_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=2),
                           "budget_exhausted")

    def test_a_supersede_naming_another_contract_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede")
        decision["supersedes"]["contract_sha256"] = "a" * 64
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "supersedes_mismatch")

    def test_a_supersede_with_an_unchanged_hash_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede")
        decision["supersedes"]["new_contract_sha256"] = decision["supersedes"]["contract_sha256"]
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "supersedes_mismatch")

    def test_a_supersede_changing_the_contract_id_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede")
        decision["supersedes"]["new_contract_id"] = "SMOKE-OTHER"
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "decision_scope_widened")

    def test_a_supersede_without_corrected_tests_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede", corrected_tests=[])
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "corrected_tests_required")

    def test_a_supersede_with_an_unapproved_test_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede",
                                 corrected_tests=["tests/test_smoke.py", "tests/test_other.py"])
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "corrected_tests_not_allowed")

    def test_a_supersede_without_the_supersedes_block_is_refused(self):
        request = make_request("specification", permitted=True, corrections=1,
                               allowed=["tests/test_smoke.py"])
        decision = make_decision(request, decision="supersede", supersedes=None)
        decision["supersedes"] = None
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "supersedes_required")

    def test_a_retry_with_a_supersession_block_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        decision["supersedes"] = {"contract_id": request["contract"]["id"],
                                  "contract_sha256": request["contract"]["sha256"],
                                  "new_contract_id": request["contract"]["id"],
                                  "new_contract_sha256": "e" * 64}
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "supersedes_unexpected")

    def test_an_implementation_retry_cannot_carry_corrected_tests(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry", corrected_tests=["tests/test_smoke.py"])
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "corrected_tests_unexpected")

    def test_an_escalation_cannot_carry_corrected_tests(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="escalate", corrected_tests=["tests/test_smoke.py"])
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "corrected_tests_unexpected")

    def test_an_integration_repair_within_the_allowed_list_is_accepted(self):
        request = make_request("integration", allowed=["tests/test_smoke.py::test_answer_is_42"])
        decision = make_decision(request, decision="retry",
                                 corrected_tests=["tests/test_smoke.py::test_answer_is_42"])
        validated = recovery.validate_decision(decision, request=request, attempts_used=1)
        self.assertEqual(validated["corrected_tests"], ["tests/test_smoke.py::test_answer_is_42"])

    def test_an_integration_repair_with_an_unapproved_test_is_refused(self):
        request = make_request("integration", allowed=["tests/test_smoke.py::test_answer_is_42"])
        decision = make_decision(request, decision="retry", corrected_tests=["tests/test_other.py"])
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "corrected_tests_not_allowed")

    def test_a_mechanical_adapter_cannot_decide(self):
        request = make_request("implementation")
        for adapter in ("bundlebees", "reconciler", "validator"):
            decision = make_decision(request, decision="retry", adapter=adapter)
            self.assertRefused(lambda: recovery.validate_decision(decision, request=request,
                                                                  attempts_used=1), "adapter_reserved")

    def test_a_decision_for_another_request_id_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        decision["request_id"] = "recovery-other-0001"
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "decision_binding_mismatch")

    def test_a_decision_with_another_digest_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        decision["request_digest"] = "f" * 64
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "decision_binding_mismatch")

    def test_a_decision_on_a_tampered_request_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        request["envelope"]["max_attempts_per_task"] = 5
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "request_digest_mismatch")

    def test_a_decision_cannot_be_replayed_on_a_similar_request(self):
        first = make_request("implementation")
        second = copy.deepcopy(first)
        second["task_id"] = "T2"
        second = recovery.seal_request(second)
        decision = make_decision(first, decision="retry")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=second, attempts_used=1),
                           "decision_binding_mismatch")

    def test_attempts_used_must_be_a_real_count(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=True),
                           "recovery_argument")
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=-1),
                           "recovery_argument")

    def test_a_decision_without_a_decided_at_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        del decision["decided_at"]
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "recovery_schema")

    def test_a_decision_with_a_short_rationale_is_refused(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        decision["rationale"] = "ok"
        self.assertRefused(lambda: recovery.validate_decision(decision, request=request, attempts_used=1),
                           "recovery_schema")


class ReturnManifestRecoveryTests(unittest.TestCase):
    def assertReturnRefused(self, operation, code: str) -> return_manifest.ReturnError:
        with self.assertRaises(return_manifest.ReturnError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code, caught.exception.message)
        return caught.exception

    def manifest_with(self, entries: list[dict]) -> dict:
        manifest = load("return-exact.json")
        manifest["recovery"] = entries
        return return_manifest.seal(manifest)

    def entry(self) -> dict:
        request = load("recovery-request.json")
        decision = load("recovery-decision.json")
        return recovery.recovery_entry(request, decision)

    def test_a_manifest_without_recovery_stays_valid(self):
        manifest = return_manifest.validate(load("return-exact.json"))
        self.assertNotIn("recovery", manifest)

    def test_an_empty_recovery_array_stays_valid(self):
        return_manifest.validate(self.manifest_with([]))

    def test_a_manifest_with_a_recovery_entry_validates(self):
        manifest = return_manifest.validate(self.manifest_with([self.entry()]))
        self.assertEqual(manifest["recovery"][0]["decision"], "supersede")

    def test_the_entry_helper_matches_the_documents(self):
        entry = self.entry()
        request = load("recovery-request.json")
        decision = load("recovery-decision.json")
        self.assertEqual(entry["request_id"], request["request_id"])
        self.assertEqual(entry["request_digest"], request["request_digest"])
        self.assertEqual(entry["failure_class"], request["failure"]["class"])
        self.assertEqual(entry["decision"], decision["decision"])
        self.assertEqual(entry["adapter"], decision["adapter"])
        self.assertEqual(entry["supersession"], {
            "contract_id": decision["supersedes"]["contract_id"],
            "contract_sha256": decision["supersedes"]["contract_sha256"],
            "supersedes": decision["supersedes"]["new_contract_id"],
            "supersedes_sha256": decision["supersedes"]["new_contract_sha256"],
        })

    def test_the_entry_has_no_supersession_for_a_retry(self):
        request = make_request("implementation")
        decision = make_decision(request, decision="retry")
        self.assertIsNone(recovery.recovery_entry(request, decision)["supersession"])

    def test_a_specification_retry_entry_is_refused(self):
        entry = self.entry()
        entry["failure_class"] = "specification"
        entry["decision"] = "retry"
        entry["supersession"] = None
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])),
                           "recovery_decision_class_mismatch")

    def test_an_environment_retry_entry_is_refused(self):
        entry = self.entry()
        entry["failure_class"] = "environment"
        entry["decision"] = "retry"
        entry["supersession"] = None
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])),
                           "recovery_decision_class_mismatch")

    def test_an_infrastructure_supersede_entry_is_refused(self):
        entry = self.entry()
        entry["failure_class"] = "infrastructure"
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])),
                           "recovery_decision_class_mismatch")

    def test_a_supersede_entry_without_supersession_is_refused(self):
        entry = self.entry()
        entry["supersession"] = None
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])),
                           "recovery_supersession_mismatch")

    def test_a_supersession_on_a_retry_entry_is_refused(self):
        entry = self.entry()
        entry["decision"] = "retry"
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])),
                           "recovery_supersession_mismatch")

    def test_a_supersession_with_an_unchanged_hash_is_refused(self):
        entry = self.entry()
        entry["supersession"]["supersedes_sha256"] = entry["supersession"]["contract_sha256"]
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])),
                           "recovery_supersession_mismatch")

    def test_a_duplicate_recovery_request_id_is_refused(self):
        entry = self.entry()
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry, copy.deepcopy(entry)])),
                           "recovery_entry_invalid")

    def test_a_recovery_entry_with_an_unknown_field_is_refused(self):
        entry = self.entry()
        entry["attempts_used"] = 1
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])), "return_schema")

    def test_a_recovery_entry_with_an_unknown_class_is_refused(self):
        entry = self.entry()
        entry["failure_class"] = "flaky"
        self.assertReturnRefused(lambda: return_manifest.validate(self.manifest_with([entry])), "return_schema")

    def test_the_return_schema_keeps_recovery_optional(self):
        schema = json.loads((ROOT / "schemas" / "return-manifest.schema.json").read_text(encoding="utf-8"))
        self.assertIn("recovery", schema["properties"])
        self.assertNotIn("recovery", schema["required"])


if __name__ == "__main__":
    unittest.main()
