"""Durable owner-decision queue (rizzstack.owner-decision/1).

Some decisions belong to the owner alone (docs/22-autonomy-architecture.md,
section 16): resolving a gate, spending beyond the authorized budget, widening
the file or test scope, enrolling or revoking a grant, and the merge, push,
release and deploy acts themselves. Silence is never consent and a relayed
answer is not approval. This module is the durable pointer layer between the
mechanical pipeline and that human authority:

* a **request** is written mechanically by the pipeline when work reaches such
  a point: what is being asked, for which subject, with at least one durable
  evidence reference, sealed by a digest and a fresh nonce;
* a **decision** is recorded by or for the owner: approve, deny, or defer. It
  binds the exact request bytes through ``request_digest`` and echoes the
  request's ``decision_nonce``, so it cannot be replayed against a different
  request; an approval must cite an approval receipt reference;
* the queue validates the pair mechanically, applies a final answer exactly
  once on the next ``apply_ready`` pass, and never performs the human act
  itself. Deferring records that the owner saw the question; the request stays
  pending. No timeout turns silence into approval.

Two documents per queue entry live in ``<state>/decisions/<request_id>.json``
as one atomic record holding the request, the final decision (if any),
recorded deferrals, the applied marker and the withdrawn marker. The queue
refuses a second open request for the same kind and subject, refuses duplicate
or conflicting decisions, refuses to decide a withdrawn request, and refuses
to apply anything it cannot re-validate from disk.

Schema: the owner-decision record contract under the observability
schemas directory (owner-decision.schema.json).
Snapshot wiring: observability/schemas/snapshot.schema.json (optional
``decisions`` section). Docs: docs/decision-queue.md.
Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SUPPORTED = ("rizzstack.owner-decision/1",)

KINDS = ("gate", "budget", "scope", "grant")
OUTCOMES = ("approve", "deny", "defer")
GRANT_ACTIONS = ("enroll", "revoke")
EVIDENCE_KINDS = ("record", "report", "metric")

# A request may carry only the payload its kind understands, and must carry
# the payload its kind requires. Everything else is refused by name so the
# refusal names the rule.
KIND_PAYLOAD_FIELDS = {
    "gate": (),
    "budget": ("spend_ceiling_usd", "requested_addition_usd"),
    "scope": ("proposed_paths",),
    "grant": ("grant_id", "grant_action"),
}

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
REL_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")

REQUEST_FIELDS = (
    "schema",
    "record",
    "request_id",
    "kind",
    "subject",
    "question",
    "evidence",
    "raised_by",
    "raised_at",
    "decision_nonce",
    "request_digest",
)
REQUEST_OPTIONAL_FIELDS = (
    "spend_ceiling_usd",
    "requested_addition_usd",
    "proposed_paths",
    "grant_id",
    "grant_action",
)
DECISION_FIELDS = (
    "schema",
    "record",
    "request_id",
    "request_digest",
    "decision_nonce",
    "decided_by",
    "decided_at",
    "outcome",
    "approval_receipt_ref",
    "rationale",
    "decision_digest",
)

RECEIPT_SCHEMA = "rizzstack.owner-decision-receipt/1"
RECEIPT_FIELDS = (
    "schema",
    "request_id",
    "request_digest",
    "decision_nonce",
    "outcome",
    "decided_by",
    "decided_at",
    "decision_digest",
    "signature",
)
RECEIPT_OUTCOMES = ("approve", "deny")

QUESTION_MIN = 8
QUESTION_MAX = 400
RATIONALE_MIN = 8
RATIONALE_MAX = 500
EVIDENCE_MAX = 8
PROPOSED_PATHS_MAX = 32


class QueueError(ValueError):
    """A document or queue operation failed mechanical validation."""

    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(f"{code}: {message}" + (f" ({fix})" if fix else ""))
        self.code = code
        self.message = message
        self.fix = fix

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "fix": self.fix}


def canonical_json(value: Any) -> str:
    """The one serialization digests are computed over."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest_without(body: Mapping[str, Any], field: str) -> str:
    stripped = {key: value for key, value in body.items() if key != field}
    return hashlib.sha256(canonical_json(stripped).encode("utf-8")).hexdigest()


def request_digest(request: Mapping[str, Any]) -> str:
    """sha256 over the canonical request without ``request_digest``."""
    return _digest_without(request, "request_digest")


def decision_digest(decision: Mapping[str, Any]) -> str:
    """sha256 over the canonical decision without ``decision_digest``."""
    return _digest_without(decision, "decision_digest")


def utc_now_iso() -> str:
    """Current UTC time in the RFC 3339 second-precision form the contracts use."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _need(condition: bool, code: str, message: str, fix: str = "") -> None:
    if not condition:
        raise QueueError(code, message, fix)


def _check_id(value: Any, field: str) -> None:
    _need(isinstance(value, str) and ID_RE.match(value), "bad_id", f"{field} must be a short opaque identifier", field)


def _check_timestamp(value: Any, field: str) -> None:
    _need(
        isinstance(value, str) and TIMESTAMP_RE.match(value) is not None,
        "bad_timestamp",
        f"{field} must be an RFC 3339 UTC timestamp with second precision",
        field,
    )


def _check_evidence(evidence: Any) -> None:
    _need(isinstance(evidence, list), "bad_evidence", "evidence must be an array")
    _need(1 <= len(evidence) <= EVIDENCE_MAX, "bad_evidence", f"evidence must carry 1 to {EVIDENCE_MAX} references")
    seen: list[dict[str, Any]] = []
    for index, entry in enumerate(evidence):
        field = f"evidence[{index}]"
        _need(isinstance(entry, dict), "bad_evidence", f"{field} must be an object")
        _need(
            set(entry) <= {"kind", "reference", "sha256"},
            "bad_evidence",
            f"{field} carries unknown fields",
        )
        _need(set(entry) >= {"kind", "reference"}, "bad_evidence", f"{field} needs kind and reference")
        _need(entry["kind"] in EVIDENCE_KINDS, "bad_evidence", f"{field}.kind must be one of {EVIDENCE_KINDS}")
        reference = entry["reference"]
        _need(
            isinstance(reference, str) and 1 <= len(reference) <= 200,
            "bad_evidence",
            f"{field}.reference must be 1 to 200 characters",
        )
        if "sha256" in entry:
            _need(
                isinstance(entry["sha256"], str) and SHA256_RE.match(entry["sha256"]) is not None,
                "bad_evidence",
                f"{field}.sha256 must be a hex sha256 digest",
            )
        _need(entry not in seen, "bad_evidence", f"{field} repeats an earlier reference")
        seen.append(entry)


def _check_kind_payload(request: Mapping[str, Any]) -> None:
    kind = request["kind"]
    allowed = set(KIND_PAYLOAD_FIELDS[kind])
    for name in REQUEST_OPTIONAL_FIELDS:
        present = name in request
        _need(
            present == (name in allowed),
            "payload_mismatch",
            f"a {kind} request must carry exactly its own payload fields",
            name if present else f"missing {name}",
        )
    if kind == "budget":
        ceiling = request["spend_ceiling_usd"]
        addition = request["requested_addition_usd"]
        _need(_is_number(ceiling) and ceiling >= 0, "bad_budget", "spend_ceiling_usd must be a number of at least 0")
        _need(
            _is_number(addition) and addition > 0,
            "bad_budget",
            "requested_addition_usd must be a number above 0",
        )
    elif kind == "scope":
        paths = request["proposed_paths"]
        _need(isinstance(paths, list), "bad_scope", "proposed_paths must be an array")
        _need(
            1 <= len(paths) <= PROPOSED_PATHS_MAX,
            "bad_scope",
            f"proposed_paths must carry 1 to {PROPOSED_PATHS_MAX} entries",
        )
        _need(len(set(paths)) == len(paths), "bad_scope", "proposed_paths must be unique")
        for index, path in enumerate(paths):
            _need(
                isinstance(path, str) and REL_PATH_RE.match(path) is not None,
                "bad_scope",
                f"proposed_paths[{index}] must be a repository-relative path",
            )
            _need(
                ".." not in path.split("/"),
                "bad_scope",
                f"proposed_paths[{index}] must not traverse upward",
            )
    elif kind == "grant":
        _check_id(request["grant_id"], "grant_id")
        _need(
            request["grant_action"] in GRANT_ACTIONS,
            "bad_grant",
            f"grant_action must be one of {GRANT_ACTIONS}",
        )


def seal_request(request: Mapping[str, Any], *, nonce: str | None = None) -> dict[str, Any]:
    """Return a copy of *request* with a fresh ``decision_nonce`` and ``request_digest``.

    An incoming ``decision_nonce`` is kept only when it is well formed; an
    incoming ``request_digest`` is never trusted: it is recomputed. Call
    :func:`validate_request` afterwards; sealing is not validation.
    """
    body = dict(request)
    if nonce is not None:
        _need(
            isinstance(nonce, str) and NONCE_RE.match(nonce) is not None,
            "bad_nonce",
            "an explicit decision_nonce must be 32 hex characters",
        )
        body["decision_nonce"] = nonce
    elif "decision_nonce" not in body or not NONCE_RE.match(str(body.get("decision_nonce", ""))):
        body["decision_nonce"] = os.urandom(16).hex()
    body["request_digest"] = request_digest(body)
    return body


def validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one request document mechanically and return a clean copy."""
    _need(isinstance(request, dict), "bad_document", "a request must be a JSON object")
    body = dict(request)
    _need(
        set(body) <= set(REQUEST_FIELDS) | set(REQUEST_OPTIONAL_FIELDS),
        "unknown_field",
        "the request carries fields outside the protocol",
        ", ".join(sorted(set(body) - set(REQUEST_FIELDS) - set(REQUEST_OPTIONAL_FIELDS))),
    )
    for name in REQUEST_FIELDS:
        _need(name in body, "missing_field", f"the request is missing {name}", name)
    _need(body["record"] == "request", "bad_record", "record must be the literal 'request'")
    _need(body["schema"] in SUPPORTED, "bad_version", f"unsupported protocol version, expected one of {SUPPORTED}")
    _check_id(body["request_id"], "request_id")
    _need(body["kind"] in KINDS, "bad_kind", f"kind must be one of {KINDS}")
    _check_id(body["subject"], "subject")
    question = body["question"]
    _need(
        isinstance(question, str) and QUESTION_MIN <= len(question) <= QUESTION_MAX,
        "bad_question",
        f"question must be {QUESTION_MIN} to {QUESTION_MAX} characters",
    )
    _check_evidence(body["evidence"])
    _check_id(body["raised_by"], "raised_by")
    _check_timestamp(body["raised_at"], "raised_at")
    _need(
        isinstance(body["decision_nonce"], str) and NONCE_RE.match(body["decision_nonce"]) is not None,
        "bad_nonce",
        "decision_nonce must be 32 hex characters",
    )
    _need(
        isinstance(body["request_digest"], str) and SHA256_RE.match(body["request_digest"]) is not None,
        "bad_digest",
        "request_digest must be a hex sha256 digest",
    )
    _check_kind_payload(body)
    _need(
        body["request_digest"] == request_digest(body),
        "digest_mismatch",
        "request_digest does not match the request body",
        "re-seal the request",
    )
    return body


def validate_decision(decision: Mapping[str, Any], *, request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one decision document against its request and return a clean copy."""
    _need(isinstance(decision, dict), "bad_document", "a decision must be a JSON object")
    checked_request = validate_request(request)
    body = dict(decision)
    _need(
        set(body) <= set(DECISION_FIELDS),
        "unknown_field",
        "the decision carries fields outside the protocol",
        ", ".join(sorted(set(body) - set(DECISION_FIELDS))),
    )
    for name in DECISION_FIELDS:
        _need(name in body, "missing_field", f"the decision is missing {name}", name)
    _need(body["record"] == "decision", "bad_record", "record must be the literal 'decision'")
    _need(body["schema"] in SUPPORTED, "bad_version", f"unsupported protocol version, expected one of {SUPPORTED}")
    _need(
        body["request_id"] == checked_request["request_id"],
        "request_mismatch",
        "the decision names a different request",
    )
    _need(
        body["request_digest"] == checked_request["request_digest"],
        "binding_mismatch",
        "the decision does not bind the request's digest",
        "a decision answers exactly one sealed request",
    )
    _need(
        body["decision_nonce"] == checked_request["decision_nonce"],
        "nonce_mismatch",
        "the decision does not echo the request's nonce",
        "replay refused",
    )
    _check_id(body["decided_by"], "decided_by")
    _check_timestamp(body["decided_at"], "decided_at")
    _need(body["outcome"] in OUTCOMES, "bad_outcome", f"outcome must be one of {OUTCOMES}")
    receipt = body["approval_receipt_ref"]
    if body["outcome"] == "approve":
        _need(
            isinstance(receipt, str) and 1 <= len(receipt) <= 200,
            "missing_receipt",
            "an approval must cite the receipt that proves the owner's act",
            "approval_receipt_ref",
        )
    else:
        _need(
            receipt is None,
            "unexpected_receipt",
            "only an approval may cite a receipt",
            "approval_receipt_ref",
        )
    rationale = body["rationale"]
    _need(
        isinstance(rationale, str) and RATIONALE_MIN <= len(rationale) <= RATIONALE_MAX,
        "bad_rationale",
        f"rationale must be {RATIONALE_MIN} to {RATIONALE_MAX} characters",
    )
    _need(
        isinstance(body["decision_digest"], str) and SHA256_RE.match(body["decision_digest"]) is not None,
        "bad_digest",
        "decision_digest must be a hex sha256 digest",
    )
    _need(
        body["decision_digest"] == decision_digest(body),
        "digest_mismatch",
        "decision_digest does not match the decision body",
    )
    return body


def canonical_receipt(receipt: Mapping[str, Any]) -> str:
    """The canonical signing domain: the receipt without its ``signature``."""
    return canonical_json({name: value for name, value in receipt.items() if name != "signature"})


def _receipt_key(key: bytes | str | None) -> bytes:
    if isinstance(key, str):
        material = key.encode("utf-8")
    elif isinstance(key, (bytes, bytearray)):
        material = bytes(key)
    else:
        material = b""
    _need(
        bool(material),
        "receipt_key_missing",
        "a receipt needs the owner-held signing key",
        "supply the key from its environment variable",
    )
    return material


def receipt_signature(receipt: Mapping[str, Any], key: bytes | str | None) -> str:
    """HMAC-SHA256 over :func:`canonical_receipt`, keyed with the owner's key."""
    material = _receipt_key(key)
    return hmac.new(material, canonical_receipt(receipt).encode("utf-8"), hashlib.sha256).hexdigest()


def sign_receipt(receipt: Mapping[str, Any], key: bytes | str | None) -> dict[str, Any]:
    """Return a copy of *receipt* carrying its HMAC-SHA256 signature."""
    body = {name: value for name, value in receipt.items() if name != "signature"}
    body["signature"] = receipt_signature(body, key)
    return body


def _receipt_body(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the frozen receipt shape and return it as a plain dict."""
    _need(isinstance(receipt, dict), "receipt_bad_version", "a receipt must be a JSON object")
    body = dict(receipt)
    unknown = sorted(set(body) - set(RECEIPT_FIELDS))
    _need(
        not unknown,
        "receipt_unknown_field",
        "the receipt carries fields outside the protocol",
        ", ".join(unknown),
    )
    for name in RECEIPT_FIELDS:
        _need(name in body, "receipt_missing_field", f"the receipt is missing {name}", name)
    _need(
        body["schema"] == RECEIPT_SCHEMA,
        "receipt_bad_version",
        f"receipt schema must be {RECEIPT_SCHEMA}",
    )
    _need(
        isinstance(body["request_id"], str) and ID_RE.match(body["request_id"]) is not None,
        "receipt_bad_id",
        "receipt request_id must be a short opaque identifier",
    )
    _need(
        isinstance(body["decision_nonce"], str) and NONCE_RE.match(body["decision_nonce"]) is not None,
        "receipt_bad_id",
        "receipt decision_nonce must be 32 hex characters",
    )
    _need(
        isinstance(body["request_digest"], str) and SHA256_RE.match(body["request_digest"]) is not None,
        "receipt_bad_digest",
        "receipt request_digest must be a hex sha256 digest",
    )
    _need(
        isinstance(body["decision_digest"], str) and SHA256_RE.match(body["decision_digest"]) is not None,
        "receipt_bad_digest",
        "receipt decision_digest must be a hex sha256 digest",
    )
    _need(
        isinstance(body["decided_at"], str) and TIMESTAMP_RE.match(body["decided_at"]) is not None,
        "receipt_bad_timestamp",
        "receipt decided_at must be an RFC 3339 UTC timestamp with second precision",
    )
    _need(
        body["outcome"] in RECEIPT_OUTCOMES,
        "receipt_bad_outcome",
        f"receipt outcome must be one of {RECEIPT_OUTCOMES}",
    )
    _need(
        body["decided_by"] == "owner",
        "receipt_not_owner",
        "a receipt must be signed for the literal owner",
    )
    _need(
        isinstance(body["signature"], str) and SHA256_RE.match(body["signature"]) is not None,
        "receipt_signature_invalid",
        "receipt signature must be 64 lowercase hex characters",
    )
    return body


def _verify_receipt_signature(body: Mapping[str, Any], key: bytes | str | None) -> None:
    expected = receipt_signature(body, _receipt_key(key))
    _need(
        hmac.compare_digest(expected, body["signature"]),
        "receipt_signature_invalid",
        "receipt signature does not verify",
    )


def _verify_receipt_bindings(
    body: Mapping[str, Any],
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> None:
    _need(
        isinstance(request, dict) and isinstance(decision, dict),
        "receipt_binding_mismatch",
        "a receipt must be verified against one request and one decision",
    )
    _need(
        body["request_id"] == request.get("request_id")
        and body["request_digest"] == request.get("request_digest")
        and body["decision_nonce"] == request.get("decision_nonce"),
        "receipt_binding_mismatch",
        "the receipt does not bind this request",
    )
    _need(
        body["decision_digest"] == decision.get("decision_digest")
        and body["outcome"] == decision.get("outcome")
        and body["decided_at"] == decision.get("decided_at"),
        "receipt_decision_mismatch",
        "the receipt does not answer this decision",
    )


def verify_receipt(
    receipt: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    key: bytes | str | None,
) -> dict[str, Any]:
    """Verify the frozen receipt shape, its signature and its bindings.

    The shape is checked first, then the signature with ``hmac.compare_digest``,
    then the request and decision bindings. The key is supplied by the caller;
    this module never reads or stores it.
    """
    body = _receipt_body(receipt)
    _verify_receipt_signature(body, key)
    _verify_receipt_bindings(body, request, decision)
    return body


def build_request(
    *,
    request_id: str,
    kind: str,
    subject: str,
    question: str,
    evidence: list[dict[str, Any]],
    raised_by: str,
    raised_at: str | None = None,
    spend_ceiling_usd: float | None = None,
    requested_addition_usd: float | None = None,
    proposed_paths: list[str] | None = None,
    grant_id: str | None = None,
    grant_action: str | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Build and seal one request document; see :func:`validate_request`."""
    body: dict[str, Any] = {
        "schema": SUPPORTED[0],
        "record": "request",
        "request_id": request_id,
        "kind": kind,
        "subject": subject,
        "question": question,
        "evidence": [dict(entry) for entry in evidence],
        "raised_by": raised_by,
        "raised_at": raised_at or utc_now_iso(),
    }
    if spend_ceiling_usd is not None:
        body["spend_ceiling_usd"] = spend_ceiling_usd
    if requested_addition_usd is not None:
        body["requested_addition_usd"] = requested_addition_usd
    if proposed_paths is not None:
        body["proposed_paths"] = list(proposed_paths)
    if grant_id is not None:
        body["grant_id"] = grant_id
    if grant_action is not None:
        body["grant_action"] = grant_action
    return seal_request(body, nonce=nonce)


class DecisionQueue:
    """The durable queue over ``<state_dir>/decisions/<request_id>.json``."""

    def __init__(self, state_dir: str | os.PathLike[str], *, now: Any = None) -> None:
        self.state_dir = Path(state_dir)
        self._now = now or utc_now_iso

    # ------------------------------------------------------------ storage

    def _path(self, request_id: str) -> Path:
        _check_id(request_id, "request_id")
        return self.state_dir / "decisions" / f"{request_id}.json"

    def _read(self, request_id: str) -> dict[str, Any]:
        path = self._path(request_id)
        _need(path.exists(), "no_such_request", f"no queue record named {request_id}", str(path))
        with path.open(encoding="utf-8") as handle:
            record = json.load(handle)
        _need(isinstance(record, dict), "bad_record_file", f"{request_id}.json is not a JSON object")
        _need(
            set(record) == {"request", "decision", "defers", "applied", "withdrawn"},
            "bad_record_file",
            f"{request_id}.json does not have the queue record shape",
        )
        _need(isinstance(record["request"], dict), "bad_record_file", f"{request_id}.json has no request")
        _need(
            record["request"].get("request_id") == request_id,
            "bad_record_file",
            f"{request_id}.json holds the record of another request",
        )
        return record

    def _write(self, record: Mapping[str, Any]) -> None:
        target = self._path(record["request"]["request_id"])
        directory = target.parent
        directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, prefix=".tmp-", suffix=".json", delete=False
        )
        tmp_name = handle.name
        try:
            with handle as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def request_ids(self) -> list[str]:
        directory = self.state_dir / "decisions"
        if not directory.is_dir():
            return []
        return sorted(path.stem for path in directory.glob("*.json") if not path.name.startswith("."))

    def get(self, request_id: str) -> dict[str, Any]:
        """Load and re-validate one queue record from disk."""
        record = self._read(request_id)
        validate_request(record["request"])
        if record["decision"] is not None:
            validate_decision(record["decision"], request=record["request"])
        for deferred in record["defers"]:
            validate_decision(deferred, request=record["request"])
        return record

    def status(self, record: Mapping[str, Any]) -> str:
        """Derive the queue state: pending, decided, applied or withdrawn."""
        if record["withdrawn"] is not None:
            return "withdrawn"
        if record["applied"] is not None:
            return "applied"
        if record["decision"] is not None:
            return "decided"
        return "pending"

    # ------------------------------------------------------------- raising

    def raise_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Validate, seal-check and persist one already built request document.

        Refuses an unknown request id, a second open request for the same kind
        and subject, and any document that fails :func:`validate_request`.
        """
        checked = validate_request(request)
        request_id = checked["request_id"]
        path = self._path(request_id)
        _need(not path.exists(), "request_id_taken", f"a queue record named {request_id} already exists")
        for existing_id in self.request_ids():
            existing = self._read(existing_id)
            if self.status(existing) in ("pending", "decided"):
                prior = existing["request"]
                if prior["kind"] == checked["kind"] and prior["subject"] == checked["subject"]:
                    raise QueueError(
                        "duplicate_open_request",
                        f"{existing_id} is already open for {checked['kind']} {checked['subject']}",
                        "resolve it first",
                    )
        record = {"request": checked, "decision": None, "defers": [], "applied": None, "withdrawn": None}
        self._write(record)
        return record

    # ------------------------------------------------------------ deciding

    def record_decision(
        self,
        request_id: str,
        *,
        outcome: str,
        decided_by: str,
        rationale: str,
        approval_receipt_ref: str | None = None,
        decided_at: str | None = None,
        receipt: Mapping[str, Any] | None = None,
        key: bytes | str | None = None,
    ) -> dict[str, Any]:
        """Record the owner's answer for one pending request.

        A final answer (approve or deny) closes the request until
        :meth:`apply_ready` consumes it. A deferral is recorded and the request
        stays pending. Refuses a decision on anything that is not pending.

        An optional owner-decision receipt is evidence only: it is verified
        against the checked decision and its request, before any write, and is
        never persisted by the queue.
        """
        record = self.get(request_id)
        current = self.status(record)
        _need(current == "pending", "not_pending", f"{request_id} is {current}, only a pending request may be decided")
        if receipt is not None:
            _receipt_key(key)
        decision = {
            "schema": SUPPORTED[0],
            "record": "decision",
            "request_id": request_id,
            "request_digest": record["request"]["request_digest"],
            "decision_nonce": record["request"]["decision_nonce"],
            "decided_by": decided_by,
            "decided_at": decided_at or self._now(),
            "outcome": outcome,
            "approval_receipt_ref": approval_receipt_ref,
            "rationale": rationale,
        }
        decision["decision_digest"] = decision_digest(decision)
        checked = validate_decision(decision, request=record["request"])
        if receipt is not None:
            verify_receipt(receipt, request=record["request"], decision=checked, key=key)
        if checked["outcome"] == "defer":
            record["defers"].append(checked)
        else:
            record["decision"] = checked
        self._write(record)
        return record

    def withdraw(self, request_id: str) -> dict[str, Any]:
        """Retract a pending request. A withdrawn request is never decided."""
        record = self.get(request_id)
        current = self.status(record)
        _need(current == "pending", "not_pending", f"{request_id} is {current}, only a pending request may be withdrawn")
        record["withdrawn"] = {"withdrawn_at": self._now()}
        self._write(record)
        return record

    # ------------------------------------------------------------- applying

    def apply_ready(self, *, applied_by: str = "decision_queue") -> list[str]:
        """Apply every decided request exactly once, in request-id order.

        Each record is re-validated from disk before its outcome is applied;
        a tampered record stops the pass with ``record_tampered`` and nothing
        after it is applied. The queue records the outcome; it never performs
        the human act itself.
        """
        applied: list[str] = []
        for request_id in self.request_ids():
            record = self._read(request_id)
            if self.status(record) != "decided":
                continue
            try:
                validate_decision(record["decision"], request=record["request"])
            except QueueError as exc:
                raise QueueError("record_tampered", f"{request_id} no longer validates: {exc.message}") from exc
            record["applied"] = {"applied_at": self._now(), "applied_by": applied_by}
            self._write(record)
            applied.append(request_id)
        return applied

    # ------------------------------------------------------- observability

    def snapshot_rows(self, generated_at: str) -> list[dict[str, Any]]:
        """One observability row per queue record, newest evidence preserved.

        Rows follow the optional ``decisions`` section of the snapshot schema:
        every row carries the snapshot envelope, the queue state, and the
        decision timestamps when they exist. The question is truncated and is
        scrubbed text by contract; the queue never copies evidence bodies.
        """
        rows: list[dict[str, Any]] = []
        for request_id in self.request_ids():
            record = self._read(request_id)
            request = record["request"]
            state = self.status(record)
            decision = record["decision"]
            row: dict[str, Any] = {
                "schema": "rizzstack.observability/snapshot/1",
                "generated_at": generated_at,
                "request_id": request_id,
                "kind": request["kind"],
                "subject": request["subject"],
                "state": state,
                "outcome": decision["outcome"] if decision else None,
                "question": request["question"][:QUESTION_MAX],
                "raised_at": request["raised_at"],
                "decided_at": decision["decided_at"] if decision else None,
                "applied_at": record["applied"]["applied_at"] if record["applied"] else None,
            }
            rows.append(row)
        return rows

    def snapshot_section(
        self,
        *,
        generated_at: str,
        collected_at: str | None = None,
        status: str = "live",
        error: str | None = None,
    ) -> dict[str, Any]:
        """The whole optional ``decisions`` section for a snapshot document."""
        return {
            "status": status,
            "error": error,
            "collected_at": collected_at or generated_at,
            "requests": self.snapshot_rows(generated_at),
        }


def _receipt_from_file(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise QueueError("receipt_bad_file", "cannot read the receipt document", path) from exc


def _key_from_env(name: str | None) -> bytes:
    _need(
        isinstance(name, str) and bool(name),
        "receipt_key_missing",
        "a receipt needs the name of the key environment variable",
        "--key-env",
    )
    value = os.environ.get(name, "")
    _need(
        bool(value),
        "receipt_key_missing",
        f"the key environment variable {name} is missing or empty",
        "--key-env",
    )
    return value.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    """Read-only verbs plus decide/apply for the queue, JSON in and out."""
    parser = argparse.ArgumentParser(
        prog="decision_queue",
        description="Durable owner-decision queue (rizzstack.owner-decision/1).",
    )
    parser.add_argument("--state-dir", required=True, help="plugin state directory holding decisions/")
    verb = parser.add_subparsers(dest="verb", required=True)
    verb.add_parser("pending", help="list pending requests")
    show = verb.add_parser("show", help="print one queue record")
    show.add_argument("--request-id", required=True)
    record = verb.add_parser("record", help="record a decision from a JSON file")
    record.add_argument("--request-id", required=True)
    record.add_argument("--file", required=True, help="path to the decision document")
    record.add_argument("--receipt", help="path to an owner-decision receipt document")
    record.add_argument("--key-env", help="environment variable holding the receipt signing key")
    verify = verb.add_parser("verify-receipt", help="verify a receipt against a stored decision")
    verify.add_argument("--request-id", required=True)
    verify.add_argument("--file", required=True, help="path to the receipt document")
    verify.add_argument("--key-env", required=True, help="environment variable holding the receipt signing key")
    verb.add_parser("apply", help="apply every decided request exactly once")
    args = parser.parse_args(argv)
    queue = DecisionQueue(args.state_dir)
    try:
        if args.verb == "pending":
            result = [
                {
                    "request_id": record["request"]["request_id"],
                    "kind": record["request"]["kind"],
                    "subject": record["request"]["subject"],
                    "question": record["request"]["question"],
                    "raised_at": record["request"]["raised_at"],
                    "deferrals": len(record["defers"]),
                }
                for record in (queue.get(name) for name in queue.request_ids())
                if queue.status(record) == "pending"
            ]
        elif args.verb == "show":
            result = queue.get(args.request_id)
        elif args.verb == "verify-receipt":
            stored = queue.get(args.request_id)
            _need(
                stored["decision"] is not None,
                "not_pending",
                f"{args.request_id} has no final decision to verify against",
            )
            receipt = _receipt_from_file(args.file)
            key = _key_from_env(args.key_env)
            checked = verify_receipt(
                receipt,
                request=stored["request"],
                decision=stored["decision"],
                key=key,
            )
            result = {
                "ok": True,
                "request_id": checked["request_id"],
                "outcome": checked["outcome"],
            }
        elif args.verb == "record":
            with open(args.file, encoding="utf-8") as handle:
                document = json.load(handle)
            receipt = None
            key = None
            if args.receipt is not None or args.key_env is not None:
                _need(
                    args.receipt is not None,
                    "receipt_bad_file",
                    "the receipt document is required with --key-env",
                    "--receipt",
                )
                _need(
                    args.key_env is not None,
                    "receipt_key_missing",
                    "the key environment variable is required with --receipt",
                    "--key-env",
                )
                receipt = _receipt_from_file(args.receipt)
                key = _key_from_env(args.key_env)
            result = queue.record_decision(
                args.request_id,
                outcome=document.get("outcome", ""),
                decided_by=document.get("decided_by", ""),
                rationale=document.get("rationale", ""),
                approval_receipt_ref=document.get("approval_receipt_ref"),
                decided_at=document.get("decided_at"),
                receipt=receipt,
                key=key,
            )
        else:
            result = {"applied": queue.apply_ready()}
    except QueueError as exc:
        print(json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
