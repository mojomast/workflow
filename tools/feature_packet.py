"""Semantic validation for feature packets and dependent source resolution.

Exact features carry a frozen contract. Dependent features carry an immutable
*intent* packet with an unfrozen contract template, the authorized root, one
dependency and the enrolled policy id. After the dependency is accepted, a
separate immutable source-resolution record binds the intent's digest to the
exact derived revision and the source-bound frozen contract. It grants no new
authority.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import jsonschema

BASE = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE / "schemas" / "feature-packet.schema.json"
SR_SCHEMA_PATH = BASE / "schemas" / "source-resolution.schema.json"
SUPPORTED = ("rizzstack.feature-packet/1",)
RESOLUTION_SUPPORTED = ("rizzstack.source-resolution/1",)


class PacketError(Exception):
    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message, "fix": self.fix}


def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _is_sha(value: Any, length: int = 40) -> bool:
    text = str(value or "")
    return len(text) == length and all(ch in "0123456789abcdef" for ch in text)


def _acdd():
    sys.path.insert(0, str(BASE / "reference"))
    from workflow import acdd  # type: ignore

    return acdd


def _contract_checks(contract: Mapping[str, Any], packet: Mapping[str, Any], *, frozen: bool) -> None:
    if frozen:
        try:
            digest = _acdd().check_frozen(contract)
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "code", "") in ("contract_changed", "contract_hash_mismatch"):
                raise PacketError("contract_hash_mismatch", f"the frozen contract changed: {exc}",
                                  "Refuse: the contract changed after approval.") from exc
            raise PacketError("contract_not_frozen", f"the contract is not frozen: {exc}",
                              "Freeze the contract with a review block first.") from exc
        if digest != packet.get("contract_sha256"):
            raise PacketError("contract_hash_mismatch", "contract_sha256 does not match the frozen contract", "Refuse.")
    else:
        try:
            jsonschema.validate(contract, _schema(BASE / "schemas" / "acdd-contract.schema.json"))
        except jsonschema.ValidationError as exc:
            raise PacketError("contract_template_invalid", f"the contract template is not valid acdd/1: {exc.message}",
                              "Fix the template before approval.") from exc

    criteria = [c for c in contract.get("acceptance_criteria") or [] if isinstance(c, Mapping)]
    if sorted(str(i) for i in packet.get("acceptance_ids") or []) != sorted(str(c.get("id")) for c in criteria):
        raise PacketError("acceptance_mismatch", "acceptance_ids do not match the contract", "List exactly the criteria.")
    contract_tests = sorted({str(t) for c in criteria for t in c.get("tests") or []})
    if sorted(str(t) for t in packet.get("tests") or []) != contract_tests:
        raise PacketError("tests_mismatch", "packet tests must equal the approved tests", "No substitutes or omissions.")
    lease = sorted(str(p) for p in (packet.get("scope") or {}).get("lease") or [])
    assigned = sorted(str(p) for p in (contract.get("scope") or {}).get("assigned_files") or [])
    if lease != assigned:
        raise PacketError("scope_mismatch", "lease scope differs from the contract's assigned files", "Keep them identical.")
    read_only = [str(p) for p in (packet.get("scope") or {}).get("read_only") or []]
    unprotected = [t for t in contract_tests
                   if t not in read_only and not any(t == r.rstrip("*") or t.startswith(r.rstrip("*")) for r in read_only)]
    if unprotected:
        raise PacketError("tests_unprotected", f"approved tests are not read-only: {', '.join(unprotected)}",
                          "Protect every approved test path.")
    contract_gates = sorted(str(g) for g in (contract.get("authorization") or {}).get("human_gates") or [])
    if sorted(str(g) for g in packet.get("human_gates") or []) != contract_gates:
        raise PacketError("gates_mismatch", "packet human gates differ from the contract", "Keep the approved gates.")
    limits = (packet.get("authorization") or {}).get("limits") or {}
    budget = packet.get("budget") or {}
    if limits:
        if int(budget.get("bees") or 0) > int(limits.get("bees") or 0):
            raise PacketError("budget_exceeded", "packet bees exceed the authorization", "Stay inside the approved budget.")
        if int(budget.get("wall_clock_s") or 0) > int(limits.get("wall_clock_s") or 0):
            raise PacketError("budget_exceeded", "packet wall clock exceeds the authorization", "Stay inside the approved budget.")


def validate(packet: Mapping[str, Any], *, workflow_repo: Path | None = None,
             check_protocol_commit: bool = True) -> dict[str, Any]:
    try:
        jsonschema.validate(packet, _schema(SCHEMA_PATH))
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        raise PacketError("packet_schema", f"{path or '<root>'}: {exc.message}", "Fix the packet shape.") from exc
    if packet.get("packet_version") not in SUPPORTED:
        raise PacketError("packet_version_unsupported", f"{packet.get('packet_version')!r} is not implemented", "Upgrade the validator.")

    workflow_ref = str(packet.get("workflow_ref") or "")
    if not _is_sha(workflow_ref):
        raise PacketError("workflow_ref_invalid", "workflow_ref must be a full commit SHA", "Pin the protocol commit.")
    if check_protocol_commit:
        if workflow_repo is None:
            raise PacketError("workflow_unavailable", "protocol-commit checking requires the pinned checkout", "Set WORKFLOW_SRC.")
        repo = Path(workflow_repo)
        if _git(["cat-file", "-e", f"{workflow_ref}^{{commit}}"], repo).returncode != 0:
            raise PacketError("workflow_ref_unknown", f"{workflow_ref} is not a commit in the pinned checkout", "Fetch it.")
        pinned = _git(["show", f"{workflow_ref}:schemas/feature-packet.schema.json"], repo)
        if pinned.returncode != 0:
            raise PacketError("workflow_ref_unsupported", f"{workflow_ref} predates the schema", "Pin a protocol revision.")
        if pinned.stdout.strip() != SCHEMA_PATH.read_text(encoding="utf-8").strip():
            raise PacketError("validator_mismatch", "the schema at workflow_ref differs from the enforced schema", "Refuse drift.")

    policy = packet.get("source_policy") or {}
    kind = policy.get("kind")
    if kind == "exact":
        contract = packet.get("contract")
        if not isinstance(contract, Mapping):
            raise PacketError("contract_missing", "an exact packet needs its frozen contract", "Attach it.")
        _contract_checks(contract, packet, frozen=True)
        if policy.get("revision") != contract.get("source_rev"):
            raise PacketError("source_policy_mismatch", "exact revision differs from contract.source_rev", "Pin the same revision.")
    elif kind == "descendant":
        if len(policy.get("dependencies") or []) != 1:
            raise PacketError("dependency_unsupported", "exactly one dependency is supported", "Split the feature.")
        if not policy.get("policy_id"):
            raise PacketError("policy_missing", "a descendant packet must name the enrolled policy id", "Reference it exactly.")
        template = packet.get("contract_template")
        if not isinstance(template, Mapping):
            raise PacketError("contract_missing", "an intent packet needs its contract template", "Attach the approved template.")
        _contract_checks(template, packet, frozen=False)
        if template.get("source_rev") != policy.get("root_revision"):
            raise PacketError("source_policy_mismatch", "template source_rev must equal the authorized root", "Fix the intent.")
        if packet.get("source_resolution_ref"):
            raise PacketError("source_resolution_premature", "an intent packet must not pre-claim a source resolution", "Resolve after integration.")
    else:
        raise PacketError("source_policy_invalid", "unknown source policy", "Use exact or descendant.")

    auth = packet.get("authorization") or {}
    if not str(auth.get("reference") or "").strip() or not str(auth.get("approved_by") or "").strip():
        raise PacketError("authorization_missing", "no authorization provenance", "Reference the approval.")
    if not packet.get("human_gates"):
        raise PacketError("gates_missing", "human gates were dropped", "Keep them.")
    return dict(packet)


def validate_source_resolution(record: Mapping[str, Any], *, packet: Mapping[str, Any],
                               accepted_commit: str) -> dict[str, Any]:
    try:
        jsonschema.validate(record, _schema(SR_SCHEMA_PATH))
    except jsonschema.ValidationError as exc:
        raise PacketError("resolution_schema", str(exc.message), "Fix the resolution record.") from exc
    if record.get("resolution_version") not in RESOLUTION_SUPPORTED:
        raise PacketError("resolution_version_unsupported", "unsupported resolution version", "Upgrade the validator.")
    policy = packet.get("source_policy") or {}
    if record.get("policy_id") != policy.get("policy_id"):
        raise PacketError("resolution_policy_mismatch", "the resolution names another policy", "Refuse.")
    if record.get("dependency_feature") not in (policy.get("dependencies") or []):
        raise PacketError("resolution_dependency_mismatch", "the resolution names another dependency", "Refuse.")
    if not _is_sha(record.get("packet_digest"), 64):
        raise PacketError("resolution_packet_invalid", "the resolution does not bind the packet digest", "Refuse.")
    accepted = str(accepted_commit)
    if record.get("accepted_commit") != accepted or record.get("derived_source_rev") != accepted:
        raise PacketError("resolution_revision_mismatch", "the derived revision is not the accepted commit", "Refuse.")
    contract = record.get("contract") or {}
    try:
        digest = _acdd().check_frozen(contract)
    except Exception as exc:  # noqa: BLE001
        raise PacketError("resolution_contract_not_frozen", f"the source-bound contract is not frozen: {exc}", "Freeze it.") from exc
    if digest != record.get("contract_sha256"):
        raise PacketError("resolution_contract_hash", "the source-bound contract hash does not match", "Refuse.")
    if contract.get("source_rev") != accepted:
        raise PacketError("resolution_contract_revision", "the contract is not frozen against the derived revision", "Refuse.")
    template = packet.get("contract_template") or {}
    for field in ("scope", "acceptance_criteria"):
        if contract.get(field) != template.get(field):
            raise PacketError("resolution_scope_changed", f"{field} changed during source resolution", "Only the revision may be substituted.")
    return dict(record)
