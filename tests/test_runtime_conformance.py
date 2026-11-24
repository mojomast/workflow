"""Conformance tests for the pre-conformance bundlebees runtime records (M4.1).

bundlebees 191dc85 recorded one real recovery pair during the M4 dogfood
(2026-11-14, job ``job_m4_dogfood``, task ``T2``, attempt ``att_m4_2``). The
run worked, but the documents it wrote do not match ``rizzstack.recovery/1``:
they carry orchestration bookkeeping in the request, a boolean correction
budget, a free-text evidence string, a private failure code, a decision digest
of their own, and a revisioned contract id in ``supersedes``.

The records are kept byte-for-byte under ``tests/fixtures/runtime/`` as
evidence of what the runtime did. This module has two jobs and keeps them
apart:

1. **Refusal.** Every one of those shapes is refused by the pinned schema and
   validator, one divergence at a time, so the refusal names the exact rule.
   The schema and the validator are not changed to fit the runtime.
2. **Migration.** A canonical pair is derived from the same evidence with an
   explicit, reviewable transformation. The derived pair is checked in next to
   the captures, and the tests prove it is (a) exactly what the migration
   produces, (b) valid against the schema and ``validate_pair``, (c) different
   from the capture in the documented paths and nowhere else.

The captures are never edited. Editing them would erase the defect the runtime
has to fix, and would make these tests assert nothing.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "reference"))

import recovery  # noqa: E402
from workflow import acdd  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "runtime"
SCHEMA = ROOT / "schemas" / "recovery.schema.json"

CAPTURED_REQUEST = "captured-request.json"
CAPTURED_DECISION = "captured-decision.json"
CAPTURED_CONTRACT = "captured-corrected-contract.json"
CANONICAL_REQUEST = "canonical-request.json"
CANONICAL_DECISION = "canonical-decision.json"
CANONICAL_CONTRACT = "canonical-corrected-contract.json"

# sha256 of the bytes bundlebees 191dc85 wrote. Pinned so a fixture can never be
# "fixed" in place: the test fails instead.
CAPTURED_SHA256 = {
    CAPTURED_REQUEST: "da6f6300812052314fa959a101de2b6e02b2a3c06e41d4ee31f7346dfbf2cd72",
    CAPTURED_DECISION: "bc95fe8c76fec2406a1379006e3060fd84c4603a97f940bb0f4182de450b216f",
    CAPTURED_CONTRACT: "f528c32436e9fb181adb7a6d57714c7b82e3839e43261289f06fbb1a72c01692",
}

# The request's own bookkeeping fields. The canonical request has none of them:
# the attempt ledger and the wall clock are facts of the job, not of the
# document, and a volatile timestamp would break the seal.
UNEXPECTED_REQUEST_FIELDS = ("number", "attempts_used", "created_at")

# The two selectors the canonical envelope authorises: the test file the review
# approved, and the one replacement the corrected contract names. The capture
# allowed the file and the selector that does not exist.
CANONICAL_ALLOWED_TESTS = (
    "tools/acdd-lint/tests/test_check_reachability.py",
    "tools/acdd-lint/tests/test_check_reachability.py::Reachability::test_reachable_commit_is_silent",
)

# The evidence reference: the archived pre-conformance request is the durable
# record of the verifier's observation ("no test was collected for ..."), and
# it is byte-pinned in this repository. The run directory it came from is not.
EVIDENCE_REFERENCE = "tests/fixtures/runtime/captured-request.json"

CANONICAL_RATIONALE = (
    "evidence code 'test_not_found' is recorded as a specification failure: no test was "
    "collected for tools/acdd-lint/tests/test_check_reachability.py::Reachability::"
    "test_ancestor_ok; the verify run reported 'no tests ran in 0.01s'."
)

# Exactly these paths change between the capture and the canonical pair; the
# tests assert the sets, so an undocumented edit fails.
EXPECTED_REQUEST_EDITS = {
    "number",
    "attempts_used",
    "created_at",
    "envelope.contract_corrections_allowed",
    "envelope.corrected_tests_allowed.1",
    "failure.code",
    "failure.evidence",
    "failure.rationale",
    "outstanding_question",
    "request_digest",
}

EXPECTED_DECISION_EDITS = {
    "decision_digest",
    "request_digest",
    "supersedes.new_contract_id",
    "supersedes.new_contract_sha256",
}


def path(name: str) -> Path:
    return FIXTURES / name


def load(name: str) -> dict:
    return json.loads(path(name).read_text(encoding="utf-8"))


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def oracle_request_digest(request: dict) -> str:
    body = {key: value for key, value in request.items() if key != "request_digest"}
    return digest(canonical_json(body).encode("utf-8"))


def branch_schema(branch: str) -> dict:
    """The standalone schema for one document kind, built from the pinned file.

    Built here rather than borrowed from ``recovery._branch_schema`` so the
    shape refusals are proved against ``schemas/recovery.schema.json`` itself.
    """
    root = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return {"$schema": root["$schema"], "$defs": root["$defs"], "$ref": f"#/$defs/{branch}"}


def root_schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def changed_paths(before, after, prefix: str = "") -> set[str]:
    """Every JSON path that differs between two documents.

    Lists are compared element-wise when the lengths match and as one path
    otherwise, so replacing a string with an array reports the array's path.
    """
    if isinstance(before, dict) and isinstance(after, dict):
        out: set[str] = set()
        for key in set(before) | set(after):
            child = f"{prefix}.{key}" if prefix else key
            if key not in before or key not in after:
                out.add(child)
            else:
                out |= changed_paths(before[key], after[key], child)
        return out
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        out = set()
        for index, (left, right) in enumerate(zip(before, after)):
            out |= changed_paths(left, right, f"{prefix}.{index}")
        return out
    # `True == 1` (and `False == 0`) in Python: compare the type too, because
    # a boolean where the schema requires an integer is exactly the divergence
    # this fixture records.
    same = before == after and type(before) is type(after)
    return set() if same else {prefix}


# --------------------------------------------------------------------------
# The migration: one explicit step per mismatch, nothing else.
# --------------------------------------------------------------------------


def migrate_request(captured: dict) -> dict:
    """The canonical ``rizzstack.recovery/1`` request for the same failure.

    Removes the three orchestration fields, states the correction budget as the
    integer ``0..1`` the schema defines, classifies the observation with the
    canonical code (``test_not_found``: a named selector that no test satisfies
    at the pinned revision), replaces the free-text evidence with one evidence
    record, restates the rationale in terms of that code, and re-seals the body.
    The envelope's allowed tests are the review's: the test file, plus the one
    replacement the corrected contract names.
    """
    request = copy.deepcopy(captured)
    for field in UNEXPECTED_REQUEST_FIELDS:
        request.pop(field)
    request["envelope"]["contract_corrections_allowed"] = 1
    request["envelope"]["corrected_tests_allowed"] = list(CANONICAL_ALLOWED_TESTS)
    request["failure"]["code"] = "test_not_found"
    request["failure"]["evidence"] = [
        {
            "kind": "test",
            "reference": EVIDENCE_REFERENCE,
            "sha256": CAPTURED_SHA256[CAPTURED_REQUEST],
        }
    ]
    request["failure"]["rationale"] = CANONICAL_RATIONALE
    request["outstanding_question"] = captured["outstanding_question"].replace(
        "test_unresolved", "test_not_found"
    )
    return recovery.seal_request(request)


def migrate_decision(captured: dict, request: dict, contract: dict) -> dict:
    """The canonical decision that answers ``request`` with the same reasoning.

    Drops the decision's private digest (v1 has no such field: the decision
    binds the request through ``request_digest``), rebinds it to the canonical
    request digest, and names the corrected contract as a revision of the same
    contract id, using the corrected contract's own frozen hash.
    """
    decision = copy.deepcopy(captured)
    decision.pop("decision_digest")
    decision["request_digest"] = request["request_digest"]
    decision["supersedes"]["new_contract_id"] = request["contract"]["id"]
    decision["supersedes"]["new_contract_sha256"] = acdd.check_frozen(contract)
    return decision


def migrate_contract(captured: dict) -> dict:
    """The corrected contract re-frozen under the canonical (unchanged) id.

    A v1 supersession revises the same contract, so ``new_contract_id`` is the
    failed contract's id. ``contract_sha256`` covers the id, so the captured
    ``-r1`` contract cannot be cited: the same body re-approved under the same
    id is the corrected contract, and its hash is the one the decision names.
    """
    body = copy.deepcopy(captured)
    body["id"] = "T2-REACHABILITY"
    return acdd.freeze_contract(
        body,
        approved_by=captured["review"]["approved_by"],
        approved_at=captured["review"]["approved_at"],
    )


@functools.lru_cache(maxsize=1)
def canonical_contract() -> dict:
    return migrate_contract(load(CAPTURED_CONTRACT))


@functools.lru_cache(maxsize=1)
def canonical_request() -> dict:
    return migrate_request(load(CAPTURED_REQUEST))


@functools.lru_cache(maxsize=1)
def canonical_decision() -> dict:
    return migrate_decision(load(CAPTURED_DECISION), canonical_request(), canonical_contract())


class RefusalMixin(unittest.TestCase):
    def assertRefused(self, operation, code: str, *, at: str | None = None,
                      says: str | None = None) -> recovery.RecoveryError:
        with self.assertRaises(recovery.RecoveryError) as caught:
            operation()
        error = caught.exception
        self.assertEqual(error.code, code, error.message)
        if at is not None:
            self.assertTrue(error.message.startswith(f"{at}: "), error.message)
        if says is not None:
            self.assertIn(says, error.message)
        return error


class CapturedRecordTests(unittest.TestCase):
    """The captures are evidence: bytes pinned, and never edited."""

    def test_the_captured_records_are_byte_identical_to_what_the_runtime_wrote(self):
        for name, expected in CAPTURED_SHA256.items():
            self.assertEqual(digest(path(name).read_bytes()), expected, name)

    def test_the_captures_are_not_canonicalised_in_place(self):
        request = load(CAPTURED_REQUEST)
        decision = load(CAPTURED_DECISION)
        for field in UNEXPECTED_REQUEST_FIELDS:
            self.assertIn(field, request)
        self.assertIs(request["envelope"]["contract_corrections_allowed"], True)
        self.assertIsInstance(request["failure"]["evidence"], str)
        self.assertEqual(request["failure"]["code"], "test_unresolved")
        self.assertIn("decision_digest", decision)
        self.assertEqual(decision["supersedes"]["new_contract_id"], "T2-REACHABILITY-r1")

    def test_the_captured_request_sealed_a_body_the_schema_cannot_express(self):
        # The runtime hashed what it wrote, so its digest is correct for a body
        # v1 cannot hold: the canonical request cannot reuse it.
        request = load(CAPTURED_REQUEST)
        self.assertEqual(request["request_digest"], oracle_request_digest(request))
        self.assertEqual(request["request_digest"], recovery.request_digest(request))
        self.assertNotEqual(canonical_request()["request_digest"], request["request_digest"])

    def test_the_pinned_schema_was_not_relaxed_for_the_runtime(self):
        # The migration is a document change. Nothing in the schema may have
        # moved to accommodate a shape the runtime wrote.
        schema = root_schema()
        for name in ("request", "failure", "evidence", "contract", "envelope",
                     "supersedes", "decision"):
            self.assertIs(schema["$defs"][name]["additionalProperties"], False, name)
        self.assertEqual(schema["$defs"]["failure"]["properties"]["evidence"]["type"], "array")
        budget = schema["$defs"]["envelope"]["properties"]["contract_corrections_allowed"]
        self.assertEqual((budget["type"], budget["minimum"], budget["maximum"]),
                         ("integer", 0, 1))
        self.assertNotIn("decision_digest", schema["$defs"]["decision"]["properties"])
        self.assertEqual(schema["$defs"]["decision"]["properties"]["schema"]["pattern"],
                         r"^rizzstack\.recovery/[0-9]+$")


class RefusedRequestTests(RefusalMixin):
    """Each runtime divergence in the request is refused, on its own."""

    def assertShapeRefused(self, request: dict, *, at: str, says: str) -> None:
        self.assertRefused(lambda: recovery.validate_request(request), "recovery_schema",
                           at=at, says=says)

    def test_the_captured_request_is_refused_and_every_extra_field_is_named(self):
        error = self.assertRefused(lambda: recovery.validate_request(load(CAPTURED_REQUEST)),
                                   "recovery_schema", at="<root>")
        for field in UNEXPECTED_REQUEST_FIELDS:
            self.assertIn(field, error.message)
        self.assertIn("Additional properties are not allowed", error.message)

    def test_each_unexpected_request_property_is_refused_alone(self):
        values = {"number": 1, "attempts_used": 1, "created_at": "2026-11-14T01:49:12Z"}
        for field in UNEXPECTED_REQUEST_FIELDS:
            with self.subTest(field=field):
                request = copy.deepcopy(canonical_request())
                request[field] = values[field]
                self.assertShapeRefused(request, at="<root>",
                                        says=f"'{field}' was unexpected")

    def test_a_boolean_correction_budget_is_refused(self):
        request = copy.deepcopy(canonical_request())
        request["envelope"]["contract_corrections_allowed"] = True
        # `True` is not an integer in JSON Schema, and the schema's bound is a
        # count: one correction, not "corrections on". The validator's int()
        # cast would have accepted the bool, so the shape gate has to refuse it.
        self.assertShapeRefused(request, at="envelope.contract_corrections_allowed",
                                says="is not of type 'integer'")

    def test_a_free_text_evidence_string_is_refused(self):
        request = copy.deepcopy(canonical_request())
        request["failure"]["evidence"] = ("test_unresolved: no test was collected for "
                                          "tools/acdd-lint/tests/test_check_reachability.py::"
                                          "Reachability::test_ancestor_ok")
        self.assertShapeRefused(request, at="failure.evidence", says="is not of type 'array'")

    def test_the_runtime_failure_code_is_not_in_the_canonical_enum(self):
        codes = root_schema()["$defs"]["failure_code"]["enum"]
        self.assertNotIn("test_unresolved", codes)
        self.assertIn("test_not_found", codes)
        request = copy.deepcopy(canonical_request())
        request["failure"]["code"] = "test_unresolved"
        self.assertShapeRefused(request, at="failure.code", says="is not one of")

    def test_the_canonical_request_for_the_same_evidence_is_accepted(self):
        request = recovery.validate_request(canonical_request())
        self.assertEqual(request["failure"]["class"], "specification")
        self.assertEqual(request["failure"]["code"], "test_not_found")
        self.assertEqual(request["request_digest"], oracle_request_digest(request))


class RefusedDecisionTests(RefusalMixin):
    """Each runtime divergence in the decision is refused, on its own."""

    def test_the_captured_decision_is_refused_against_the_canonical_request(self):
        self.assertRefused(lambda: recovery.validate_decision(
            load(CAPTURED_DECISION), request=canonical_request(), attempts_used=1),
            "recovery_schema", at="<root>", says="'decision_digest' was unexpected")

    def test_a_decision_digest_of_its_own_is_refused_alone(self):
        decision = copy.deepcopy(canonical_decision())
        decision["decision_digest"] = load(CAPTURED_DECISION)["decision_digest"]
        self.assertRefused(lambda: recovery.validate_decision(
            decision, request=canonical_request(), attempts_used=1),
            "recovery_schema", at="<root>", says="'decision_digest' was unexpected")

    def test_a_revisioned_contract_id_in_supersedes_is_refused(self):
        decision = copy.deepcopy(canonical_decision())
        decision["supersedes"]["new_contract_id"] = "T2-REACHABILITY-r1"
        # The shape is legal (an id is an id); the refusal is the semantic rule
        # the schema states in prose and tools/recovery.py enforces.
        jsonschema.validate(decision, branch_schema("decision"))
        self.assertRefused(lambda: recovery.validate_decision(
            decision, request=canonical_request(), attempts_used=1),
            "decision_scope_widened", says="may not change the contract id")

    def test_the_runtime_envelope_did_not_authorise_the_runtime_decision(self):
        # Discovered by the migration: even after the six shape/field fixes the
        # captured envelope allows the file and the selector that does not
        # exist, but not the replacement the decision names.
        request = copy.deepcopy(canonical_request())
        request["envelope"]["corrected_tests_allowed"] = list(
            load(CAPTURED_REQUEST)["envelope"]["corrected_tests_allowed"])
        request = recovery.seal_request(request)
        decision = copy.deepcopy(canonical_decision())
        decision["request_digest"] = request["request_digest"]
        self.assertRefused(lambda: recovery.validate_decision(
            decision, request=request, attempts_used=1),
            "corrected_tests_not_allowed", says="test_reachable_commit_is_silent")

    def test_the_canonical_decision_for_the_same_reasoning_is_accepted(self):
        decision = recovery.validate_decision(canonical_decision(),
                                              request=canonical_request(), attempts_used=1)
        self.assertEqual(decision["decision"], "supersede")
        self.assertEqual(decision["adapter"], "deterministic-agent")
        self.assertEqual(decision["supersedes"]["new_contract_id"],
                         canonical_request()["contract"]["id"])


class CanonicalPairTests(RefusalMixin):
    """The derived pair is the checked-in one and it validates as a unit."""

    def test_the_canonical_fixtures_are_exactly_what_the_migration_produces(self):
        self.assertEqual(load(CANONICAL_REQUEST), canonical_request())
        self.assertEqual(load(CANONICAL_DECISION), canonical_decision())
        self.assertEqual(load(CANONICAL_CONTRACT), canonical_contract())

    def test_the_canonical_request_changes_only_the_documented_paths(self):
        self.assertEqual(changed_paths(load(CAPTURED_REQUEST), canonical_request()),
                         EXPECTED_REQUEST_EDITS)

    def test_the_canonical_decision_changes_only_the_documented_paths(self):
        self.assertEqual(changed_paths(load(CAPTURED_DECISION), canonical_decision()),
                         EXPECTED_DECISION_EDITS)

    def test_the_migration_does_not_mutate_the_captures(self):
        captured_request = load(CAPTURED_REQUEST)
        captured_decision = load(CAPTURED_DECISION)
        captured_contract = load(CAPTURED_CONTRACT)
        before = [copy.deepcopy(captured_request), copy.deepcopy(captured_decision),
                  copy.deepcopy(captured_contract)]
        migrate_request(captured_request)
        migrate_decision(captured_decision, canonical_request(), canonical_contract())
        migrate_contract(captured_contract)
        self.assertEqual([captured_request, captured_decision, captured_contract], before)

    def test_the_canonical_pair_passes_every_schema_branch(self):
        jsonschema.validate(canonical_request(), root_schema())
        jsonschema.validate(canonical_decision(), root_schema())
        jsonschema.validate(canonical_request(), branch_schema("request"))
        jsonschema.validate(canonical_decision(), branch_schema("decision"))

    def test_the_canonical_pair_validates_with_validate_pair(self):
        pair = recovery.validate_pair(canonical_request(), canonical_decision(),
                                      attempts_used=1, corrections_used=0)
        self.assertEqual(pair["request"]["request_id"], "job_m4_dogfood.T2.1")
        self.assertEqual(pair["decision"]["request_digest"], pair["request"]["request_digest"])
        self.assertEqual(pair["decision"]["decision"], "supersede")

    def test_the_canonical_pair_keeps_the_evidence_it_was_derived_from(self):
        request = canonical_request()
        captured = load(CAPTURED_REQUEST)
        for field in ("request_id", "job_id", "feature_id", "task_id", "attempt_id"):
            self.assertEqual(request[field], captured[field], field)
        self.assertEqual(request["contract"], captured["contract"])
        self.assertEqual(request["failure"]["class"], captured["failure"]["class"])
        evidence = request["failure"]["evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["kind"], "test")
        self.assertEqual(evidence[0]["sha256"], CAPTURED_SHA256[CAPTURED_REQUEST])
        self.assertEqual(request["envelope"]["max_attempts_per_task"],
                         captured["envelope"]["max_attempts_per_task"])
        self.assertIs(request["supersession_permitted"], True)
        decision = canonical_decision()
        captured_decision = load(CAPTURED_DECISION)
        for field in ("adapter", "decision", "corrected_tests", "rationale", "decided_at"):
            self.assertEqual(decision[field], captured_decision[field], field)
        self.assertEqual(decision["supersedes"]["contract_id"],
                         captured_decision["supersedes"]["contract_id"])
        self.assertEqual(decision["supersedes"]["contract_sha256"],
                         captured_decision["supersedes"]["contract_sha256"])

    def test_the_canonicalisation_does_not_loosen_a_budget(self):
        self.assertRefused(lambda: recovery.validate_pair(
            canonical_request(), canonical_decision(), attempts_used=2),
            "budget_exhausted", says="supersede re-dispatches a worker")
        self.assertRefused(lambda: recovery.validate_pair(
            canonical_request(), canonical_decision(), attempts_used=1, corrections_used=1),
            "budget_exhausted", says="supersede needs a remaining correction")

    def test_the_corrected_contract_is_the_same_contract_re_approved(self):
        request = canonical_request()
        decision = canonical_decision()
        contract = canonical_contract()
        self.assertEqual(contract["id"], request["contract"]["id"])
        self.assertEqual(contract["id"], decision["supersedes"]["new_contract_id"])
        self.assertEqual(acdd.check_frozen(contract),
                         decision["supersedes"]["new_contract_sha256"])
        self.assertNotEqual(decision["supersedes"]["new_contract_sha256"],
                            decision["supersedes"]["contract_sha256"])
        selected = [test for criterion in contract["acceptance_criteria"]
                    for test in criterion["tests"]]
        self.assertEqual(selected, decision["corrected_tests"])

    def test_the_captured_corrected_contract_cannot_be_cited(self):
        # The reason the corrected contract is re-frozen: contract_sha256 covers
        # the id, so the captured "T2-REACHABILITY-r1" revision has a hash that
        # cannot belong to a contract with the canonical id.
        captured = load(CAPTURED_CONTRACT)
        self.assertEqual(captured["id"], "T2-REACHABILITY-r1")
        self.assertEqual(acdd.check_frozen(captured),
                         load(CAPTURED_DECISION)["supersedes"]["new_contract_sha256"])
        self.assertNotEqual(acdd.check_frozen(captured),
                            canonical_decision()["supersedes"]["new_contract_sha256"])
        self.assertEqual(set(changed_paths(captured, canonical_contract())),
                         {"id", "review.contract_sha256"})

    def test_the_cli_validates_the_canonical_pair(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "recovery.py"), "decision",
             str(path(CANONICAL_DECISION)), "--request", str(path(CANONICAL_REQUEST)),
             "--attempts-used", "1", "--corrections-used", "0"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok job_m4_dogfood.T2.1", result.stdout)


if __name__ == "__main__":
    unittest.main()
