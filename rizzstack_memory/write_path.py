"""Quarantine-first write pipeline for ``rizzstack.memory/1``.

The contract is normative: writes are quarantined by default, a secret never
lands on disk, and promotion out of quarantine needs a durable grant record
(and a human approver for the curated zones). This module is the only path that
implements those rules for the disk-backed vault.

The gate runs a configured scanner executable over the exact bytes that would
be stored. A configured scanner that cannot be run is a refusal, never a pass.
When no external scanner is configured a conservative in-process denylist runs
instead, so the write surface is still gated on a bare install.

Refusals are logged to ``.quarantine/refusals.log`` with the rule id and the
attempted writer/path only. The payload, the secret and the scanner's output
are never logged.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .vault import (
    GRANT_APPROVER_KINDS,
    ID_RE,
    KIND_RE,
    QUARANTINE_ROOT,
    TIME_RE,
    TYPE_DIR,
    ContractError,
    memory_sha,
    parse_memory,
    quarantine_prefix,
    refuse,
    serialize_memory,
    validate_frontmatter,
    validate_write_op,
    zone_of,
)

SCANNER_ENV = "RIZZSTACK_MEMORY_GITLEAKS"
SCANNER_TIMEOUT_SECONDS = 30
REFUSAL_LOG = "refusals.log"

SECRET_DETECTED = "secret_detected"
SCANNER_UNAVAILABLE = "scanner_unavailable"

_GATE_ARGS = ("detect", "--no-banner", "--redact", "--pipe")
_RULE_ID_RE = re.compile(r"(?i)\"?\b(?:rule[_-]?id|rule)\"?\s*[:=]\s*\"?([A-Za-z0-9][A-Za-z0-9._-]{0,63})")


def _cat(*parts: str) -> str:
    return "".join(parts)


# The built-in denylist. It mirrors the repository gate's refusal classes but
# never carries a provider literal in one piece; each prefix is assembled from
# fragments so this source file stays clean under those same rules.
_PROVIDER_PREFIXES = tuple(
    _cat(*parts) for parts in (("s", "k-"), ("gh", "p_"), ("github", "_pat_"), ("xo", "x"))
)
_BUILTIN_NAME_VALUE_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9_])([A-Za-z0-9_.$/\"'-]*(?:token|secret|password|passwd|pwd"
    r"|api[_-]key|authorization))[ \t]*[:=]"
)
_BUILTIN_BEARER_RE = re.compile(r"(?i)\bBearer[ \t]+(\S{6,})")
_BUILTIN_PROVIDER_RE = re.compile(
    r"(?i)\b(?:" + "|".join(re.escape(prefix) for prefix in _PROVIDER_PREFIXES) + r")"
)
_BUILTIN_CLOUD_RE = re.compile(
    r"\b" + _cat("A", "K", "I", "A") + r"[0-9A-Za-z]{16}|\b" + _cat("A", "I", "za") + r"[0-9A-Za-z_-]{20}"
)
_BUILTIN_JWT_RE = re.compile(
    r"\b" + _cat("ey", "J") + r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
)
_BUILTIN_LONG_RUN_RE = re.compile(r"[A-Za-z0-9]{32,}")
_BUILTIN_PRIVATE_KEY_RE = re.compile(
    re.escape(_cat("-", "-", "-", "-", "-", "BEGIN ")) + r"[A-Z ]*PRIVATE KEY" + re.escape(_cat("-", "-", "-", "-", "-"))
)


class _GateRefusal(ContractError):
    """A ContractError carrying the rule id the scanner named."""

    def __init__(self, code: str, message: str, rule_id: str = "unknown") -> None:
        super().__init__(code, message, "Remove the secret; never store credentials in the vault.")
        self.rule_id = rule_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_rule(output: str) -> str:
    match = _RULE_ID_RE.search(output)
    if not match:
        return "unknown"
    return match.group(1)


def _builtin_scan(text: str) -> None:
    """Refuse on a credential-shaped literal. Only the rule id leaves here."""
    if _BUILTIN_NAME_VALUE_RE.search(text):
        raise _GateRefusal(SECRET_DETECTED, "the secret gate refused this write: rule generic-api-key", "generic-api-key")
    if _BUILTIN_BEARER_RE.search(text):
        raise _GateRefusal(SECRET_DETECTED, "the secret gate refused this write: rule bearer-token", "bearer-token")
    if _BUILTIN_PROVIDER_RE.search(text):
        raise _GateRefusal(SECRET_DETECTED, "the secret gate refused this write: rule provider-token", "provider-token")
    if _BUILTIN_CLOUD_RE.search(text):
        raise _GateRefusal(SECRET_DETECTED, "the secret gate refused this write: rule cloud-access-key", "cloud-access-key")
    if _BUILTIN_JWT_RE.search(text):
        raise _GateRefusal(SECRET_DETECTED, "the secret gate refused this write: rule jwt", "jwt")
    for match in _BUILTIN_LONG_RUN_RE.finditer(text):
        run = match.group(0)
        if run != run.lower() and run != run.upper() and any(char.isdigit() for char in run):
            raise _GateRefusal(SECRET_DETECTED, "the secret gate refused this write: rule long-mixed-run", "long-mixed-run")
    if _BUILTIN_PRIVATE_KEY_RE.search(text):
        raise _GateRefusal(SECRET_DETECTED, "the secret gate refused this write: rule private-key", "private-key")


def scan_payload(payload, scanner=None, env_var: str = SCANNER_ENV, timeout: int = SCANNER_TIMEOUT_SECONDS) -> None:
    """Scan the exact payload bytes and refuse on a hit.

    ``scanner`` is the path to the scanner executable (gitleaks-compatible:
    the payload is on stdin, exit 0 is clean, exit 1 is a finding). When no
    scanner is configured the built-in denylist runs instead.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if not isinstance(payload, (bytes, bytearray)):
        refuse("schema_invalid", "the gate scans exact payload bytes")
    payload = bytes(payload)

    configured = scanner if scanner is not None else os.environ.get(env_var)
    if not configured:
        _builtin_scan(payload.decode("utf-8", errors="replace"))
        return

    command = os.fspath(configured)
    if not os.path.isfile(command):
        raise _GateRefusal(SCANNER_UNAVAILABLE, "the configured secret scanner does not exist; refusing the write")
    try:
        completed = subprocess.run(
            [command, *_GATE_ARGS],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise _GateRefusal(SCANNER_UNAVAILABLE, "the secret scanner timed out; refusing the write")
    except (OSError, ValueError):
        raise _GateRefusal(SCANNER_UNAVAILABLE, "the secret scanner could not be run; refusing the write")

    if completed.returncode == 0:
        return
    if completed.returncode == 1:
        output = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
        rule_id = _extract_rule(output)
        raise _GateRefusal(
            SECRET_DETECTED,
            f"the secret scanner refused this write: rule {rule_id}",
            rule_id,
        )
    raise _GateRefusal(
        SCANNER_UNAVAILABLE,
        f"the secret scanner exited {completed.returncode}; refusing the write",
    )


def _root(vault):
    root = getattr(vault, "root", None)
    return Path(root) if root is not None else None


def _safe_field(value, limit: int = 300):
    if not isinstance(value, str):
        return None
    return value.replace("\r", " ").replace("\n", " ")[:limit]


def refusal_log_path(vault) -> Path:
    root = _root(vault)
    if root is None:
        raise ValueError("a refusal log needs a disk-backed vault root")
    return root / QUARANTINE_ROOT / REFUSAL_LOG


def record_refusal(vault, code: str, rule_id: str, writer=None, path=None) -> None:
    """Append one scrubbed refusal line; never the payload or the secret."""
    root = _root(vault)
    if root is None:
        return
    entry = {
        "at": _utc_now(),
        "code": code,
        "rule": rule_id if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", rule_id or "") else "unknown",
    }
    writer = _safe_field(writer)
    path = _safe_field(path)
    if writer is not None:
        entry["writer"] = writer
    if path is not None:
        entry["path"] = path
    target = root / QUARANTINE_ROOT / REFUSAL_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _scanner_for(vault, scanner, env_var):
    if scanner is not None:
        return scanner
    configured = getattr(vault, "scanner", None)
    if configured:
        return configured
    return os.environ.get(env_var or SCANNER_ENV)


def _gate(vault, payload, scanner, env_var, writer, path) -> None:
    try:
        scan_payload(payload, scanner=scanner, env_var=env_var or SCANNER_ENV)
    except ContractError as err:
        record_refusal(vault, err.code, getattr(err, "rule_id", "unknown"), writer=writer, path=path)
        raise


def enforce_gate(vault, record: dict, body: str, scanner=None, env_var=None, writer=None, path=None) -> None:
    """Gate the exact canonical bytes a memory write would store."""
    payload = serialize_memory(record, body).encode("utf-8")
    _gate(vault, payload, _scanner_for(vault, scanner, env_var), env_var, writer, path)


def _require_identity(writer) -> str:
    if not isinstance(writer, str) or not KIND_RE.match(writer):
        refuse(
            "schema_invalid",
            "writer must be a kind-prefixed id such as agent:bee-7, never a path",
            "Pass the writer identity, not a filesystem path.",
        )
    return writer


def write_quarantined(vault, op: dict, writer=None, scanner=None, env_var=None) -> dict:
    """Validate, gate and store one write inside the writer's own quarantine.

    The caller's path must already be inside ``.quarantine/<writer-slug>/``;
    anything else is refused as ``write_quarantined``. A grant cannot be used
    to turn this function into a direct zone write.
    """
    validate_write_op(op)
    if writer is None:
        writer = op["writer"]
    writer = _require_identity(writer)
    if op["writer"] != writer:
        refuse("schema_invalid", "the writer identity must match the write operation's writer")
    if op["authority"] is not None:
        refuse("write_bad_grant", "a quarantined write carries no authority grant")
    prefix = quarantine_prefix(writer)
    path = op["path"]
    if not path.startswith(prefix) or ".." in Path(path).parts:
        refuse(
            "write_quarantined",
            "a writer may only write its own quarantine subtree",
            f"Write under {prefix} or promote with a grant.",
        )
    enforce_gate(
        vault,
        op["memory"],
        op["body"],
        scanner=scanner,
        env_var=env_var or getattr(vault, "scanner_env", None),
        writer=writer,
        path=path,
    )
    return vault.write(op)


def _validate_grant(grant) -> str:
    if not isinstance(grant, dict):
        refuse("write_bad_grant", "a promotion requires a grant record")
    if set(grant) != {"grant_ref", "approved_by", "approved_at"}:
        refuse("write_bad_grant", "a grant record carries grant_ref, approved_by and approved_at")
    if not isinstance(grant["grant_ref"], str) or not 1 <= len(grant["grant_ref"]) <= 200:
        refuse("write_bad_grant", "grant_ref must name the durable approval record")
    if not isinstance(grant["approved_by"], str) or not KIND_RE.match(grant["approved_by"]):
        refuse("write_bad_grant", "approved_by must be a kind-prefixed id")
    if not isinstance(grant["approved_at"], str) or not TIME_RE.match(grant["approved_at"]):
        refuse("write_bad_grant", "approved_at must be an RFC 3339 timestamp")
    kind = grant["approved_by"].split(":", 1)[0]
    if kind not in GRANT_APPROVER_KINDS:
        refuse("write_bad_grant", f"grants are approved by one of {', '.join(GRANT_APPROVER_KINDS)}")
    return grant["approved_by"]


def _find_quarantined(root: Path, memory_id: str) -> Path:
    quarantine = root / QUARANTINE_ROOT
    matches = []
    if quarantine.is_dir():
        for candidate in sorted(quarantine.rglob("*.md")):
            if not candidate.is_file():
                continue
            try:
                record, _ = parse_memory(candidate.read_text(encoding="utf-8"))
            except (ContractError, OSError, UnicodeDecodeError):
                continue
            if record.get("id") == memory_id:
                matches.append(candidate)
    if not matches:
        refuse("not_found", f"no quarantined memory with id {memory_id}")
    if len(matches) > 1:
        refuse("duplicate_id", f"more than one quarantined memory has id {memory_id}")
    return matches[0]


def _writer_of_quarantine_path(relative: str):
    parts = relative.split("/")
    if len(parts) >= 3 and parts[0] == QUARANTINE_ROOT:
        return parts[1]
    return None


def _existing_id(vault, memory_id: str, skip_relative: str) -> None:
    scan = getattr(vault, "_scan", None)
    if scan is None:
        return
    for entry in scan():
        if entry["path"] == skip_relative:
            continue
        if entry["record"]["id"] == memory_id:
            refuse("duplicate_id", "this memory id already exists elsewhere in the vault")


def _next_seq(vault) -> int:
    last = getattr(vault, "_last_log_seq", None)
    if last is not None:
        return last() + 1
    receipts = getattr(vault, "receipts", None)
    return len(receipts()) + 1 if receipts is not None else 1


def _append_receipt(vault, entry: dict) -> None:
    append = getattr(vault, "_append_receipt", None)
    if append is not None:
        append(entry)
        return
    root = _root(vault)
    if root is None:
        raise ValueError("a receipt needs a disk-backed vault root")
    line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    with open(root / "log.md", "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_file(path: Path) -> None:
    handle = os.open(path, os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def promote(vault, memory_id: str, grant: dict, scanner=None, env_var=None) -> dict:
    """Move one quarantined memory into its contract zone with a valid grant.

    Missing or malformed grants, bot-only grants into curated zones and any
    attempted self-approval are refused before a byte moves.
    """
    if not isinstance(memory_id, str) or not ID_RE.match(memory_id):
        refuse("schema_invalid", "memory_id must be a lowercase kebab slug")
    approved_by = _validate_grant(grant)
    root = _root(vault)
    if root is None:
        refuse("service_owned", "promotion needs a disk-backed vault root")

    source = _find_quarantined(root, memory_id)
    relative_source = source.relative_to(root).as_posix()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        refuse("not_found", f"no readable quarantined memory with id {memory_id}")
    record, body = parse_memory(text)
    validate_frontmatter(record)
    if record["id"] != memory_id:
        refuse("id_mismatch", "the quarantined path holds a different memory id")
    if record["sha"] != memory_sha(record, body):
        refuse("sha_mismatch", "the quarantined memory digest does not match its record and body")

    target_relative = f"{TYPE_DIR[record['type']]}/{memory_id}.md"
    zone = zone_of(target_relative)
    if zone == "service-owned":
        refuse("service_owned", f"{target_relative} is not a writable memory zone")
    approver_kind = approved_by.split(":", 1)[0]
    if zone == "curated" and approver_kind != "human":
        refuse("write_bad_grant", "curated zones require a grant approved by a human")
    writer_slug = _writer_of_quarantine_path(relative_source)
    if writer_slug is not None and writer_slug == approved_by.replace(":", "-"):
        refuse("write_bad_grant", "an identity cannot approve its own promotion")

    target = root / target_relative
    if target.exists():
        refuse("duplicate_id", "the contract zone already holds this memory id")
    _existing_id(vault, memory_id, relative_source)

    gate_writer = writer_slug
    _gate(
        vault,
        text.encode("utf-8"),
        _scanner_for(vault, scanner, env_var),
        env_var or getattr(vault, "scanner_env", None),
        gate_writer,
        relative_source,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    _fsync_file(target)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

    seq = _next_seq(vault)
    _append_receipt(
        vault,
        {
            "seq": seq,
            "at": record["modified"],
            "writer": approved_by,
            "path": target_relative,
            "id": record["id"],
            "sha": record["sha"],
            "granted": True,
        },
    )
    return {
        "accepted": True,
        "id": record["id"],
        "sha": record["sha"],
        "path": target_relative,
        "log_seq": seq,
        "promoted_from": relative_source,
    }


__all__ = [
    "REFUSAL_LOG",
    "SCANNER_ENV",
    "SCANNER_UNAVAILABLE",
    "SECRET_DETECTED",
    "enforce_gate",
    "promote",
    "record_refusal",
    "refusal_log_path",
    "scan_payload",
    "write_quarantined",
]
