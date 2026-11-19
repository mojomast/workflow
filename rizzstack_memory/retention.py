"""Retention runner for the ``rizzstack.memory/1`` vault.

One idempotent pass over the vault:

* classify each memory as active, deadline-passed or superseded;
* refuse a record whose type and retention policy are paired illegally
  (a decision or learning carrying a deadline, a reference without one);
* append exactly one ``log.md`` receipt for each expiry or supersession that
  has not been receipted before.

The runner never rewrites memory frontmatter. Default queries already hide
expired records through :func:`rizzstack_memory.vault.is_expired`; this pass is
the auditable decision + receipt step, not an opaque rewriter.

Invocation::

    python -m rizzstack_memory.retention --vault <path> --now <rfc3339> [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json

from .vault import (
    CONTRACT,
    MEMORY_TYPES,
    TIME_RE,
    TYPE_POLICY,
    ContractError,
    DiskVault,
    parse_memory,
    parse_time,
    refuse,
    zone_of,
)

EVENT_EXPIRY = "expiry"
EVENT_SUPERSESSION = "supersession"
RECEIPT_KIND = "retention"


def _fingerprint(memory_id: str, memory_type: str, policy: str, expires, superseded_by, reason: str) -> str:
    """Stable identity of one retention state, used for idempotent receipts."""
    payload = json.dumps(
        {
            "id": memory_id,
            "type": memory_type,
            "policy": policy,
            "expires": expires,
            "superseded_by": superseded_by,
            "reason": reason,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _judge(record: dict, now: str):
    """Return ``(code, reason, message)`` for one parsed memory record.

    ``code`` is a typed refusal code, ``reason`` is ``expiry`` or
    ``supersession`` when the record is stale, and both are ``None`` for an
    active record.
    """
    memory_id = record.get("id")
    memory_type = record.get("type")
    retention = record.get("retention")
    if not isinstance(memory_id, str) or memory_type not in MEMORY_TYPES or not isinstance(retention, dict):
        return None, None, None
    policy = retention.get("policy")
    expires = retention.get("expires")
    superseded_by = retention.get("superseded_by")
    expected = TYPE_POLICY.get(memory_type)
    if policy != expected:
        return (
            "policy_mismatch",
            None,
            f"{memory_id}: type {memory_type} requires policy {expected}, not {policy}",
        )
    if memory_type in ("decision", "learning") and expires is not None:
        return (
            "policy_mismatch",
            None,
            f"{memory_id}: type {memory_type} policy {policy} never carries expires",
        )
    if memory_type == "reference" and expires is None:
        return (
            "policy_mismatch",
            None,
            f"{memory_id}: type reference policy {policy} requires a re-verify deadline",
        )
    if superseded_by:
        return None, EVENT_SUPERSESSION, None
    if expires is not None:
        try:
            passed = parse_time(expires) <= parse_time(now)
        except (TypeError, ValueError):
            return "schema_invalid", None, f"{memory_id}: retention.expires is not an RFC 3339 timestamp"
        if passed:
            return None, EVENT_EXPIRY, None
    return None, None, None


def _scan(vault: DiskVault):
    """Yield ``(path, record, body)`` for every parseable memory document."""
    for target in vault._candidate_paths():
        rel = target.relative_to(vault.root).as_posix()
        if zone_of(rel) == "service-owned":
            continue
        try:
            record, body = parse_memory(target.read_text(encoding="utf-8"))
        except (ContractError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict) or record.get("schema") != CONTRACT:
            continue
        if not isinstance(record.get("id"), str) or record.get("type") not in MEMORY_TYPES:
            continue
        if not isinstance(record.get("retention"), dict):
            continue
        yield rel, record, body


def _receipted_fingerprints(vault: DiskVault) -> set:
    fingerprints = set()
    for entry in vault.receipts():
        if entry.get("kind") == RECEIPT_KIND and isinstance(entry.get("fingerprint"), str):
            fingerprints.add(entry["fingerprint"])
    return fingerprints


def run(vault: DiskVault, now: str, dry_run: bool = False) -> list:
    """Run one retention pass and return the per-record decision list.

    With ``dry_run=True`` the decisions are returned and nothing is written.
    A record whose retention state was already receipted is reported as
    ``unchanged`` and does not produce a second receipt.
    """
    if not isinstance(now, str) or not TIME_RE.match(now):
        refuse("schema_invalid", "now must be an RFC 3339 timestamp")

    decisions = []
    seen = _receipted_fingerprints(vault)
    seq = vault._last_log_seq()

    for path, record, _body in _scan(vault):
        memory_id = record.get("id")
        memory_type = record.get("type")
        retention = record["retention"]
        policy = retention.get("policy")
        expires = retention.get("expires")
        superseded_by = retention.get("superseded_by")
        decision = {
            "id": memory_id,
            "path": path,
            "type": memory_type,
            "policy": policy,
            "retention": {
                "policy": policy,
                "expires": expires,
                "superseded_by": superseded_by,
            },
            "expired": None,
            "reason": None,
            "action": "active",
            "code": None,
            "message": None,
            "fingerprint": None,
            "seq": None,
        }

        code, reason, message = _judge(record, now)
        if code is not None:
            decision.update(action="refused", code=code, message=message)
            decisions.append(decision)
            continue

        if reason is None:
            decision["expired"] = False
            decisions.append(decision)
            continue

        fingerprint = _fingerprint(memory_id, memory_type, policy, expires, superseded_by, reason)
        decision.update(expired=True, reason=reason, fingerprint=fingerprint)
        if fingerprint in seen:
            decision["action"] = "unchanged"
        elif dry_run:
            decision["action"] = "would_log"
        else:
            seq += 1
            vault._append_receipt(
                {
                    "seq": seq,
                    "at": now,
                    "kind": RECEIPT_KIND,
                    "event": reason,
                    "id": memory_id,
                    "path": path,
                    "type": memory_type,
                    "policy": policy,
                    "reason": reason,
                    "fingerprint": fingerprint,
                    "retention": {
                        "policy": policy,
                        "expires": expires,
                        "superseded_by": superseded_by,
                    },
                }
            )
            seen.add(fingerprint)
            decision.update(action="logged", seq=seq)
        decisions.append(decision)

    return decisions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one rizzstack.memory/1 retention pass.")
    parser.add_argument("--vault", required=True, help="vault root directory")
    parser.add_argument("--now", required=True, help="RFC 3339 instant used for expiry decisions")
    parser.add_argument("--dry-run", action="store_true", help="report decisions without writing receipts")
    options = parser.parse_args(argv)
    vault = DiskVault(options.vault)
    decisions = run(vault, options.now, dry_run=options.dry_run)
    print(
        json.dumps(
            {
                "vault": str(vault.root),
                "now": options.now,
                "dry_run": options.dry_run,
                "decisions": decisions,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EVENT_EXPIRY", "EVENT_SUPERSESSION", "RECEIPT_KIND", "main", "run"]
