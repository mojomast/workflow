"""Semantic validation for the bounded recovery protocol (rizzstack.recovery/1).

Two durable documents answer one classified failure:

* a **request**, written by the orchestrator from recorded evidence: which job,
  feature, task and attempt failed, in which of the five failure classes, against
  which frozen contract, and what the approved envelope allows;
* a **decision**, written by an agent adapter: retry, supersede the contract once,
  or escalate. The adapter is named but not trusted: bundlebees validates the
  decision mechanically against the request before anything is dispatched.

Neither document is authority. The envelope restates an authorization that
already exists, a decision may only use what the envelope allows, and a decision
has no field with which to widen scope, budget or acceptance semantics.

The rules this module enforces are listed in docs/27-recovery-protocol.md.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import jsonschema

BASE = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE / "schemas" / "recovery.schema.json"
SUPPORTED = ("rizzstack.recovery/1",)

FAILURE_CLASSES = (
    "implementation",
    "specification",
    "environment",
    "infrastructure",
    "integration",
)

# A code belongs to exactly one class. The specification codes are the three
# ways an acceptance selection can be unusable; nothing else may be called a
# specification failure, and a specification failure may carry nothing else.
FAILURE_CODES: dict[str, tuple[str, ...]] = {
    "implementation": ("test_failed", "suite_failed", "lease_violation", "gitleaks_failed"),
    "specification": ("acceptance_uncovered", "test_not_found", "missing_test"),
    "environment": ("toolchain_missing", "dependency_unavailable", "network_blocked"),
    "infrastructure": ("launcher_unavailable", "scheduler_stalled", "storage_full"),
    "integration": ("merge_conflict", "combined_suite_failed", "wave_rejected"),
}

EVIDENCE_KINDS = ("test", "command", "log", "conflict", "environment", "infrastructure")

# At least one entry of one of these kinds must be present for the class.
REQUIRED_EVIDENCE: dict[str, tuple[str, ...]] = {
    "implementation": ("test", "command"),
    "specification": ("test", "log"),
    "environment": ("environment",),
    "infrastructure": ("infrastructure",),
    "integration": ("conflict",),
}

# Kinds that would relabel the failure as a different class.
FORBIDDEN_EVIDENCE: dict[str, tuple[str, ...]] = {
    "implementation": ("conflict",),
    "specification": ("conflict",),
    "environment": ("conflict",),
    "infrastructure": ("conflict",),
    "integration": ("environment", "infrastructure"),
}

DECISIONS = ("retry", "supersede", "escalate")

# A retry re-dispatches a worker, so it is legal only where another patch could
# plausibly change the outcome.
RETRY_CLASSES = ("implementation", "integration")
# No dispatch can fix these; only escalation is legal.
NO_DISPATCH_CLASSES = ("environment", "infrastructure")
# Only an unusable acceptance selection may be corrected.
SUPERSEDE_CLASSES = ("specification",)

# The mechanical components validate; they do not reason. A decision naming one
# of them is refused so the orchestrator cannot approve its own recovery.
RESERVED_ADAPTERS = frozenset({"bundlebees", "reconciler", "validator"})


class RecoveryError(Exception):
    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message, "fix": self.fix}


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _branch_schema(branch: str) -> dict[str, Any]:
    """A standalone schema for one document kind.

    The shared $defs travel with the $ref, so the subschema can be validated on
    its own and a refusal names the real path instead of "not valid under any of
    the given schemas".
    """
    root = _schema()
    if branch not in ("request", "decision"):
        raise ValueError(f"unknown document kind {branch!r}")
    return {"$schema": root["$schema"], "$defs": root["$defs"], "$ref": f"#/$defs/{branch}"}


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, compact separators, ASCII."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def request_digest(request: Mapping[str, Any]) -> str:
    """sha256 of the canonical request body; the value request_digest must equal."""
    body = {key: value for key, value in request.items() if key != "request_digest"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def decision_digest(decision: Mapping[str, Any]) -> str:
    """sha256 of the whole canonical decision.

    A decision carries no digest field: it binds the request through
    request_digest. This helper exists so a coordinator can journal the decision
    it stored, not so the document can prove anything about itself.
    """
    return hashlib.sha256(canonical_json(dict(decision)).encode("utf-8")).hexdigest()


def seal_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with request_digest recomputed. It does not validate."""
    sealed = copy.deepcopy(dict(request))
    sealed.pop("request_digest", None)
    sealed["request_digest"] = request_digest(sealed)
    return sealed


def document_kind(document: Mapping[str, Any]) -> str:
    """Name the document kind from its own fields, or refuse an ambiguous one."""
    looks_request = "failure" in document
    looks_decision = "decision" in document or "adapter" in document
    if looks_request and not looks_decision:
        return "request"
    if looks_decision and not looks_request:
        return "decision"
    if looks_request and looks_decision:
        raise RecoveryError("recovery_ambiguous", "the document carries both request and decision fields",
                            "Emit one document per failure: a request then a decision.")
    raise RecoveryError("recovery_schema", "the document is neither a recovery request nor a decision",
                        "Emit rizzstack.recovery/1 request or decision shape.")


def _shape(document: Mapping[str, Any], branch: str) -> None:
    try:
        jsonschema.validate(dict(document), _branch_schema(branch))
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        raise RecoveryError("recovery_schema", f"{path or '<root>'}: {exc.message}",
                            "Fix the document shape; see docs/27-recovery-protocol.md.") from exc


def _version(document: Mapping[str, Any]) -> None:
    if document.get("schema") not in SUPPORTED:
        raise RecoveryError("recovery_version_unsupported", f"{document.get('schema')!r} is not implemented",
                            "Upgrade the validator or emit rizzstack.recovery/1.")


def _count(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecoveryError("recovery_argument", f"{name} must be a non-negative integer, not {value!r}",
                            "Pass the durable ledger count, not a guess.")
    return value


def _check_failure(failure: Mapping[str, Any]) -> str:
    """Validate the class/code/evidence triple and return the class."""
    failure_class = str(failure.get("class"))
    code = str(failure.get("code"))
    if failure_class not in FAILURE_CLASSES:
        raise RecoveryError("failure_class_unknown", f"{failure_class!r} is not a failure class",
                            "Use one of: " + ", ".join(FAILURE_CLASSES) + ".")
    if code not in FAILURE_CODES[failure_class]:
        raise RecoveryError(
            "failure_code_mismatch",
            f"{code!r} is not a {failure_class} code; {failure_class} codes are "
            + ", ".join(FAILURE_CODES[failure_class]),
            "Classify the failure from the evidence, not from what would be convenient to retry.",
        )

    evidence = list(failure.get("evidence") or [])
    kinds = [str(entry.get("kind")) for entry in evidence]
    if not any(kind in REQUIRED_EVIDENCE[failure_class] for kind in kinds):
        raise RecoveryError(
            "evidence_missing",
            f"a {failure_class} failure needs at least one of these evidence kinds: "
            + ", ".join(REQUIRED_EVIDENCE[failure_class]),
            "Record the artefact before requesting recovery.",
        )
    for kind in kinds:
        if kind in FORBIDDEN_EVIDENCE[failure_class]:
            raise RecoveryError(
                "evidence_forbidden",
                f"a {kind!r} record does not belong to a {failure_class} failure",
                "A conflict record is integration evidence; an environment record is environment evidence.",
            )
    for entry in evidence:
        if entry.get("kind") != "conflict" and entry.get("paths"):
            raise RecoveryError("evidence_forbidden",
                                f"only a conflict record carries paths, not a {entry.get('kind')!r} record",
                                "Record conflicted paths on the conflict entry.")
    if failure_class == "integration":
        conflicts = [entry for entry in evidence if entry.get("kind") == "conflict"]
        if not conflicts or any(not entry.get("paths") for entry in conflicts):
            raise RecoveryError(
                "conflict_evidence_incomplete",
                "an integration failure needs a conflict record naming the conflicted paths",
                "Record the integration log with its conflicting paths; a bare reference is not distinct repair evidence.",
            )
    return failure_class


def _check_envelope(request: Mapping[str, Any], failure_class: str) -> None:
    envelope = request.get("envelope") or {}
    permitted = bool(request.get("supersession_permitted"))
    corrections = int(envelope.get("contract_corrections_allowed") or 0)
    allowed_tests = list(envelope.get("corrected_tests_allowed") or [])

    if permitted and failure_class != "specification":
        raise RecoveryError(
            "supersession_not_permitted",
            f"supersession_permitted is true for a {failure_class} failure",
            "Only an unusable acceptance selection may be corrected.",
        )
    if permitted and corrections < 1:
        raise RecoveryError("envelope_widened", "supersession is permitted but no contract correction is budgeted",
                            "Grant both or neither; a permission without a budget is incoherent.")
    if not permitted and corrections:
        raise RecoveryError("envelope_widened", "the envelope grants contract corrections that are not permitted",
                            "A retry may not rewrite the contract.")
    if allowed_tests:
        # Two classes may name pre-authorized tests: a specification correction
        # (replacement selection) and an integration repair (an added
        # regression test). Nothing else may change acceptance.
        if failure_class == "specification" and not permitted:
            raise RecoveryError("envelope_widened",
                                "the envelope names corrected tests but does not permit a correction",
                                "Grant the correction or drop the test list.")
        if failure_class not in ("specification", "integration"):
            raise RecoveryError("envelope_widened",
                                f"a {failure_class} failure may not name corrected tests",
                                "Only a specification correction or an integration repair changes tests.")


def validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one rizzstack.recovery/1 request: shape, digest, class, evidence, envelope."""
    _shape(request, "request")
    _version(request)
    failure_class = _check_failure(request.get("failure") or {})
    _check_envelope(request, failure_class)

    expected = request_digest(request)
    if request.get("request_digest") != expected:
        raise RecoveryError(
            "request_digest_mismatch",
            f"request_digest is {request.get('request_digest')!r}, the canonical body hashes to {expected}",
            "Recompute it with tools/recovery.py seal, or refuse the request.",
        )
    return dict(request)


def validate_decision(decision: Mapping[str, Any], *, request: Mapping[str, Any],
                      attempts_used: int, corrections_used: int = 0) -> dict[str, Any]:
    """Validate a decision against the exact request it answers.

    ``attempts_used`` is the durable ledger: attempts already consumed for this
    task, including the failed attempt the request names. ``corrections_used``
    counts contract corrections already consumed for it. The request is
    validated first, so a decision cannot be admitted on an inadmissible request.
    """
    validate_request(request)
    _shape(decision, "decision")
    _version(decision)

    attempts = _count("attempts_used", attempts_used)
    corrections = _count("corrections_used", corrections_used)

    request_id = str(request.get("request_id"))
    if decision.get("request_id") != request_id:
        raise RecoveryError("decision_binding_mismatch",
                            f"the decision answers {decision.get('request_id')!r}, the request is {request_id!r}",
                            "A decision answers exactly one request.")
    expected = request_digest(request)
    if request.get("request_digest") != expected:
        raise RecoveryError("request_digest_mismatch", "the request body no longer hashes to its request_digest",
                            "Refuse: the request was edited after it was sealed.")
    if decision.get("request_digest") != expected:
        raise RecoveryError(
            "decision_binding_mismatch",
            f"request_digest is {decision.get('request_digest')!r}, the request hashes to {expected}",
            "Replay the decision against the request it names; a decision cannot be moved to another failure.",
        )

    adapter = str(decision.get("adapter") or "")
    if adapter.lower() in RESERVED_ADAPTERS:
        raise RecoveryError("adapter_reserved", f"{adapter!r} is a mechanical component, not an adapter",
                            "The validator never decides; a named agent adapter must.")

    failure_class = str((request.get("failure") or {}).get("class"))
    envelope = request.get("envelope") or {}
    max_attempts = int(envelope.get("max_attempts_per_task") or 0)
    corrections_allowed = int(envelope.get("contract_corrections_allowed") or 0)
    allowed_tests = list(envelope.get("corrected_tests_allowed") or [])
    remaining = max_attempts - attempts
    chosen = str(decision.get("decision"))
    supersedes = decision.get("supersedes")
    corrected_tests = list(decision.get("corrected_tests") or [])

    if chosen not in DECISIONS:
        raise RecoveryError("recovery_schema", f"{chosen!r} is not a decision", "Use retry, supersede or escalate.")

    if chosen == "escalate":
        # Escalation is always legal and is the only decision that changes nothing.
        if supersedes is not None:
            raise RecoveryError("supersedes_unexpected", "an escalation cannot supersede a contract",
                                "Escalate without a correction; a human decides the next contract.")
        if corrected_tests:
            raise RecoveryError("corrected_tests_unexpected", "an escalation cannot carry corrected tests",
                                "Propose the correction in the escalation text, not in this field.")
        return dict(decision)

    if chosen == "retry":
        if failure_class in NO_DISPATCH_CLASSES:
            raise RecoveryError(
                "failure_class_no_dispatch",
                f"a {failure_class} failure may not retry: no worker dispatch can fix it",
                "Escalate to the human who owns the host or the launcher.",
            )
        if failure_class not in RETRY_CLASSES:
            raise RecoveryError(
                "decision_class_mismatch",
                f"a {failure_class} failure may not be retried",
                "A specification failure supersedes the contract; it does not retry it.",
            )
        if remaining < 1:
            raise RecoveryError(
                "budget_exhausted",
                f"retry needs a remaining attempt; {attempts} of {max_attempts} are used",
                "Escalate: the approved attempt budget is exhausted.",
            )
        if supersedes is not None:
            raise RecoveryError("supersedes_unexpected", "a retry cannot supersede the contract",
                                "Only a specification failure supersedes; and only with an explicit correction.")
        if failure_class == "implementation" and corrected_tests:
            raise RecoveryError("corrected_tests_unexpected", "an implementation retry may not change acceptance",
                                "Retry the same contract; corrected tests belong to a supersession.")
        if failure_class == "integration":
            outside = [test for test in corrected_tests if test not in allowed_tests]
            if outside:
                raise RecoveryError(
                    "corrected_tests_not_allowed",
                    f"the integration repair names tests the envelope does not allow: {', '.join(outside)}",
                    "Repair inside corrected_tests_allowed, or escalate.",
                )
        return dict(decision)

    # chosen == "supersede"
    if failure_class in NO_DISPATCH_CLASSES:
        raise RecoveryError(
            "failure_class_no_dispatch",
            f"a {failure_class} failure may not supersede: a contract correction does not fix it",
            "Escalate to the human who owns the host or the launcher.",
        )
    if failure_class not in SUPERSEDE_CLASSES:
        raise RecoveryError("decision_class_mismatch",
                            f"a {failure_class} failure may not supersede the contract",
                            "Only an unusable acceptance selection is a specification failure.")
    if not request.get("supersession_permitted"):
        raise RecoveryError("supersession_not_permitted",
                            "the request does not permit a contract correction",
                            "Escalate; a contract change needs a prior authorization.")
    if corrections >= corrections_allowed:
        raise RecoveryError(
            "budget_exhausted",
            f"supersede needs a remaining correction; {corrections} of {corrections_allowed} are used",
            "Escalate: v1 allows one specification supersession.",
        )
    if remaining < 1:
        raise RecoveryError(
            "budget_exhausted",
            f"supersede re-dispatches a worker and needs a remaining attempt; {attempts} of {max_attempts} are used",
            "Escalate: the attempt budget is exhausted.",
        )
    if supersedes is None:
        raise RecoveryError("supersedes_required", "a supersede decision must name the contract pair it replaces",
                            "Emit supersedes with the old and new contract id and hash.")
    old = request.get("contract") or {}
    if (supersedes.get("contract_id") != old.get("id")
            or supersedes.get("contract_sha256") != old.get("sha256")):
        raise RecoveryError("supersedes_mismatch",
                            "supersedes does not name the request's contract id and hash",
                            "Replace exactly the contract that failed.")
    if supersedes.get("new_contract_id") != supersedes.get("contract_id"):
        raise RecoveryError("decision_scope_widened",
                            "a supersession may not change the contract id",
                            "A correction revises the same contract; a different id is a new feature.")
    if supersedes.get("new_contract_sha256") == supersedes.get("contract_sha256"):
        raise RecoveryError("supersedes_mismatch", "the corrected contract has the same hash as the failed one",
                            "A supersession must change the contract.")
    if not corrected_tests:
        raise RecoveryError("corrected_tests_required", "a supersession must name the corrected acceptance tests",
                            "List the replacement tests; the contract they select is the point of the correction.")
    outside = [test for test in corrected_tests if test not in allowed_tests]
    if outside:
        raise RecoveryError("corrected_tests_not_allowed",
                            f"the correction names tests the envelope does not allow: {', '.join(outside)}",
                            "A decision cannot widen the pre-authorized test list.")
    return dict(decision)


def validate_pair(request: Mapping[str, Any], decision: Mapping[str, Any], *,
                  attempts_used: int, corrections_used: int = 0) -> dict[str, Any]:
    """Validate a request and its decision as one unit."""
    admitted = validate_request(request)
    validated = validate_decision(decision, request=admitted, attempts_used=attempts_used,
                                  corrections_used=corrections_used)
    return {"request": admitted, "decision": validated}


def recovery_entry(request: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    """The RETURN-manifest recovery entry for one validated pair.

    Field names differ on purpose: in the manifest the supersession records the
    old contract as ``contract_id``/``contract_sha256`` and the replacement as
    ``supersedes``/``supersedes_sha256`` (the B3b naming).
    """
    supersedes = decision.get("supersedes")
    supersession = None
    if supersedes is not None:
        supersession = {
            "contract_id": supersedes["contract_id"],
            "contract_sha256": supersedes["contract_sha256"],
            "supersedes": supersedes["new_contract_id"],
            "supersedes_sha256": supersedes["new_contract_sha256"],
        }
    return {
        "request_id": request["request_id"],
        "request_digest": request["request_digest"],
        "failure_class": request["failure"]["class"],
        "decision": decision["decision"],
        "adapter": decision["adapter"],
        "supersession": supersession,
    }


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate rizzstack.recovery/1 requests and decisions.")
    commands = parser.add_subparsers(dest="command", required=True)

    request_parser = commands.add_parser("request", help="validate one request")
    request_parser.add_argument("file")

    decision_parser = commands.add_parser("decision", help="validate one decision against its request")
    decision_parser.add_argument("file")
    decision_parser.add_argument("--request", required=True)
    decision_parser.add_argument("--attempts-used", type=int, required=True)
    decision_parser.add_argument("--corrections-used", type=int, default=0)

    seal_parser = commands.add_parser("seal", help="print a request with a recomputed request_digest")
    seal_parser.add_argument("file")

    entry_parser = commands.add_parser("entry", help="print the RETURN recovery entry for a pair")
    entry_parser.add_argument("--request", required=True)
    entry_parser.add_argument("--decision", required=True)
    entry_parser.add_argument("--attempts-used", type=int, default=0)
    entry_parser.add_argument("--corrections-used", type=int, default=0)

    args = parser.parse_args(argv)
    try:
        if args.command == "seal":
            print(json.dumps(seal_request(_load(args.file)), indent=2, sort_keys=True))
            return 0
        if args.command == "request":
            document = validate_request(_load(args.file))
            print(f"{args.file}: ok {document['request_digest']}")
        elif args.command == "decision":
            decision = validate_decision(_load(args.file), request=_load(args.request),
                                         attempts_used=args.attempts_used,
                                         corrections_used=args.corrections_used)
            print(f"{args.file}: ok {decision['request_id']}")
        else:
            request = validate_request(_load(args.request))
            decision = validate_decision(_load(args.decision), request=request,
                                         attempts_used=args.attempts_used,
                                         corrections_used=args.corrections_used)
            print(json.dumps(recovery_entry(request, decision), indent=2, sort_keys=True))
    except RecoveryError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        if exc.fix:
            print(f"fix: {exc.fix}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
