"""Brief schema, immutable lease records, and validation.

TEACHING ONLY. ``lease_sha256`` is a plain, unkeyed SHA-256 of the lease body,
stored in the same file as the lease. It catches accidental edits and makes the
idea of an immutable coordinator record visible, but anyone who can edit the
store can change a lease and recompute the hash. Do not copy this into a real
system. For real use, bundlebees' coordinator leases are HMAC-SHA256 signed
with a separate ``0600`` key and written read-only with ``O_EXCL``; see
https://github.com/mojomast/bundlebees and ``docs/13-bundlebees-hardening.md``.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

REQUIRED_BRIEF_FIELDS = ("title", "source_rev", "assigned_files", "acceptance")

LEASE_REQUIRED = ("task_id", "source_rev", "assigned_files")


class ContractError(ValueError):
    """A brief or lease failed validation."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def validate_brief(brief: dict) -> dict:
    missing = [k for k in REQUIRED_BRIEF_FIELDS if k not in brief]
    if missing:
        raise ContractError(f"brief missing required fields: {missing}")
    if not isinstance(brief["source_rev"], str) or len(brief["source_rev"]) != 40:
        raise ContractError("source_rev must be a full 40-character commit SHA")
    files = brief["assigned_files"]
    if not isinstance(files, list) or not files or not all(isinstance(x, str) and x for x in files):
        raise ContractError("assigned_files must be a non-empty list of paths")
    if len(set(files)) != len(files):
        raise ContractError("assigned_files must not contain duplicates")
    acc = brief["acceptance"]
    if not isinstance(acc, list) or not acc or not all(isinstance(x, str) and x for x in acc):
        raise ContractError("acceptance must be a non-empty list of checks")
    return brief


def lease_fingerprint(record: dict) -> str:
    """Unkeyed SHA-256 of the lease body. Teaching only: recomputable by anyone
    who can edit the store. Production leases need a keyed signature (HMAC)."""
    body = {k: record[k] for k in ("task_id", "source_rev", "assigned_files")}
    return _sha256_bytes(canonical_json(body))


def lease_record(task_id: str, source_rev: str, assigned_files: list[str]) -> dict:
    record = {
        "task_id": task_id,
        "source_rev": source_rev,
        "assigned_files": list(assigned_files),
    }
    record["lease_sha256"] = lease_fingerprint(record)
    return record


class LeaseStore:
    """Coordinator-owned leases. Once written, the API refuses to mutate them.

    Teaching only: the JSON file itself is writable, and the SHA-256
    fingerprints can be recomputed, so this is not tamper-proof. bundlebees
    uses HMAC-signed, read-only lease files for real enforcement.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}\n", encoding="utf-8")

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def put(self, record: dict) -> dict:
        for key in LEASE_REQUIRED:
            if key not in record:
                raise ContractError(f"lease missing {key}")
        expected = lease_fingerprint(record)
        if record.get("lease_sha256") != expected:
            raise ContractError("lease_sha256 does not match the lease body")
        data = self._load()
        task_id = record["task_id"]
        if task_id in data:
            raise ContractError(f"lease {task_id} is immutable and already recorded")
        data[task_id] = deepcopy(record)
        self._save(data)
        return deepcopy(record)

    def get(self, task_id: str) -> dict:
        data = self._load()
        if task_id not in data:
            raise KeyError(task_id)
        record = deepcopy(data[task_id])
        if lease_fingerprint(record) != record.get("lease_sha256"):
            raise ContractError(f"lease {task_id} was tampered with")
        return record

    def try_replace(self, task_id: str, new_record: dict) -> None:
        """Always rejected. Exposed so tests can prove immutability."""
        raise ContractError(f"lease {task_id} cannot be replaced")
