"""Semantic validation for rizzstack.feature-packet/1.

JSON Schema covers shape. This module adds the checks that make a packet
executable evidence rather than a claim:

* the packet version is one this validator implements;
* ``workflow_ref`` is a real commit in the pinned workflow checkout, and the
  schema at that commit is byte-identical to the one being enforced here;
* the ACDD contract is frozen and its hash matches ``contract_sha256``;
* acceptance IDs and tests agree with the contract;
* lease scope agrees with the contract's assigned files;
* a descendant policy names exactly one dependency and a policy id;
* authorization provenance and human gates are present.

The packet is not authorization. This validator never grants anything; it only
refuses packets that are self-inconsistent or bound to an unknown protocol.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "feature-packet.schema.json"
SUPPORTED = ("rizzstack.feature-packet/1",)


class PacketError(Exception):
    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message, "fix": self.fix}


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _is_sha(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 40 and all(ch in "0123456789abcdef" for ch in text)


def validate(packet: Mapping[str, Any], *, workflow_repo: Path | None = None,
             check_protocol_commit: bool = True) -> dict[str, Any]:
    """Validate a packet; returns it on success, raises PacketError otherwise."""

    schema = _load_schema()
    try:
        jsonschema.validate(packet, schema)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        raise PacketError("packet_schema", f"{path or '<root>'}: {exc.message}", "Fix the packet shape; do not relax the schema.") from exc

    if packet.get("packet_version") not in SUPPORTED:
        raise PacketError("packet_version_unsupported", f"{packet.get('packet_version')!r} is not implemented", "Use a supported version or upgrade the validator.")

    workflow_ref = str(packet.get("workflow_ref") or "")
    if not _is_sha(workflow_ref):
        raise PacketError("workflow_ref_invalid", "workflow_ref must be a full lowercase commit SHA", "Pin the exact protocol commit.")

    if check_protocol_commit and workflow_repo is not None:
        repo = Path(workflow_repo)
        exists = _git(["cat-file", "-e", f"{workflow_ref}^{{commit}}"], repo)
        if exists.returncode != 0:
            raise PacketError("workflow_ref_unknown", f"{workflow_ref} is not a commit in the pinned workflow checkout", "Fetch the pinned protocol revision.")
        pinned = _git(["show", f"{workflow_ref}:schemas/feature-packet.schema.json"], repo)
        if pinned.returncode != 0:
            raise PacketError("workflow_ref_unsupported", f"{workflow_ref} predates the feature-packet schema", "Pin a revision that defines the protocol.")
        if pinned.stdout.strip() != SCHEMA_PATH.read_text(encoding="utf-8").strip():
            raise PacketError("validator_mismatch", "the schema at workflow_ref differs from the enforced schema", "Refuse: the validator does not correspond to the pinned protocol.")

    contract = packet.get("contract")
    if not isinstance(contract, Mapping):
        raise PacketError("contract_missing", "the packet carries no ACDD contract", "Attach the frozen acdd/1 contract.")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))
        from workflow import acdd  # type: ignore

        digest = acdd.check_frozen(contract)
    except Exception as exc:  # noqa: BLE001 - any refusal is a refusal
        if getattr(exc, "code", "") in ("contract_changed", "contract_hash_mismatch"):
            raise PacketError("contract_hash_mismatch", f"the frozen contract no longer matches its review block: {exc}",
                              "Refuse: the contract changed after approval.") from exc
        raise PacketError("contract_not_frozen", f"the contract is not validly frozen: {exc}", "Freeze the contract with a review block first.") from exc
    if digest != packet.get("contract_sha256"):
        raise PacketError("contract_hash_mismatch", "contract_sha256 does not match the frozen contract", "Refuse: the contract changed after approval.")

    criteria = [c for c in contract.get("acceptance_criteria") or [] if isinstance(c, Mapping)]
    expected_ids = sorted(str(c.get("id")) for c in criteria)
    if sorted(str(i) for i in packet.get("acceptance_ids") or []) != expected_ids:
        raise PacketError("acceptance_mismatch", "acceptance_ids do not match the contract", "List exactly the contract's criteria.")
    contract_tests = sorted({str(t) for c in criteria for t in c.get("tests") or []})
    missing = [t for t in contract_tests if t not in (packet.get("tests") or [])]
    if missing:
        raise PacketError("tests_mismatch", f"approved tests missing from the packet: {', '.join(missing)}", "Carry every approved test.")

    lease = sorted(str(p) for p in (packet.get("scope") or {}).get("lease") or [])
    assigned = sorted(str(p) for p in (contract.get("scope") or {}).get("assigned_files") or [])
    if lease != assigned:
        raise PacketError("scope_mismatch", "lease scope differs from the contract's assigned files", "Keep write scope identical to the approved contract.")

    policy = packet.get("source_policy") or {}
    if policy.get("kind") == "exact":
        if policy.get("revision") != contract.get("source_rev"):
            raise PacketError("source_policy_mismatch", "the exact revision differs from the contract's source_rev", "Pin the same revision in both places.")
    elif policy.get("kind") == "descendant":
        if len(policy.get("dependencies") or []) != 1:
            raise PacketError("dependency_unsupported", "this coordinator supports exactly one dependency per descendant packet", "Split the feature or wait for multi-dependency support.")
        if not policy.get("policy_id"):
            raise PacketError("policy_missing", "a descendant packet must name the enrolled policy", "Reference the exact policy id.")
    else:
        raise PacketError("source_policy_invalid", "unknown source policy", "Use exact or descendant.")

    auth = packet.get("authorization") or {}
    if not str(auth.get("reference") or "").strip() or not str(auth.get("approved_by") or "").strip():
        raise PacketError("authorization_missing", "the packet has no authorization provenance", "Reference the sealed approval.")
    if not packet.get("human_gates"):
        raise PacketError("gates_missing", "human gates were dropped", "Keep merge/release/deploy/publish gates.")
    return dict(packet)
