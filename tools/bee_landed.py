"""Semantic validation for rizzstack.bee-landed/1 CloudEvents.

A Bee Landed event announces one terminal worker transition: succeeded, failed
or cancelled. It is delivery evidence. It is never a verification result and
never an acceptance decision; those belong to the receiver.

The schema lives in schemas/bee-landed.schema.json. This module implements the
rules a JSON Schema cannot express alone: terminal sink comparison, dedupe,
redaction (secrets, private paths, full patches), payload size and the refusal
of client-side verified/accepted claims.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

BASE = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE / "schemas" / "bee-landed.schema.json"

EVENT_TYPE = "rizzstack.bee.landed.v1"
PAYLOAD_SCHEMA = "rizzstack.bee-landed/1"
STATES = ("succeeded", "failed", "cancelled")
MAX_EVENT_BYTES = 64 * 1024

EVENT_ID_RE = re.compile(
    r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|urn:[A-Za-z0-9][A-Za-z0-9-]{0,31}:\S+)$"
)
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RELATIVE_PATH_RE = re.compile(r"^(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+$")
SOURCE_RE = re.compile(r"^\S+$")

SENSITIVE_KEY_RE = re.compile(
    r"(?:secret|token|password|passwd|api[_-]?key|private[_-]?key|access[_-]?key"
    r"|authorization|credential|cookie|client[_-]?secret)",
    re.IGNORECASE,
)
CLAIM_KEYS = {"verified", "accepted", "verification", "acceptance", "approved", "approved_by", "decision"}

SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
)

PRIVATE_PATH_PATTERNS = (
    re.compile(r"(?:^|[\s\"'=(])/(?:home|Users)/[^/\s]+"),
    re.compile(r"(?:^|[\s\"'=(])/root(?:/|\b)"),
    re.compile(r"(?:^|[\s\"'=(])/private/(?:var|tmp|etc|home|Users)(?:/|\b)"),
    re.compile(r"(?:^|[\s\"'=(])/var/folders(?:/|\b)"),
    re.compile(r"(?:^|[\s\"'=(])[A-Za-z]:\\Users\\[^\\\s]+"),
    re.compile(r"(?:^|[\s/])(?:\.ssh|\.aws|\.gnupg)(?:/|\b)"),
    re.compile(r"(?:^|[\s/])(?:id_rsa|id_ed25519)(?:\b|$)"),
    re.compile(r"^file://"),
)

PATCH_MARKERS = (
    "diff --git ",
    "*** Begin Patch",
    "\n@@ -",
    "Index: ",
    "--- a/",
    "+++ b/",
)
PATCH_KEYS = {"patch", "diff", "full_patch", "patch_text", "raw_diff"}


class BeeLandedError(Exception):
    """A Bee Landed event refused by one named rule."""

    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message, "fix": self.fix}


def _fail(code: str, message: str, fix: str = "") -> "None":
    raise BeeLandedError(code, message, fix)


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, compact separators, ASCII."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _is_text(value: Any, *, maximum: int | None = None) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return maximum is None or len(value) <= maximum


def _require(mapping: Mapping[str, Any], field: str, where: str) -> Any:
    if field not in mapping:
        _fail("bee_required", f"{where}.{field} is required", f"Add {where}.{field}.")
    return mapping[field]


def _valid_time(value: str) -> bool:
    if not TIME_RE.match(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _walk(value: Any, path: str = "$") -> list[tuple[str, Any, Any]]:
    """Yield (path, key, value) for every mapping entry, at any depth."""
    found: list[tuple[str, Any, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.append((path, key, item))
            found.extend(_walk(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_walk(item, f"{path}[{index}]"))
    return found


def _truthy_claim(value: Any) -> bool:
    return isinstance(value, (bool, int, float, str, list, dict)) and bool(value)


def _refuse_embedded_data(event: Mapping[str, Any]) -> None:
    """Reject secrets, private paths, full patches and client-side claims."""
    for path, key, value in _walk(event):
        where = f"{path}.{key}"
        if isinstance(key, str):
            if SENSITIVE_KEY_RE.search(key) and value not in (None, "", False):
                _fail("bee_secret", f"{where} carries a credential-like field",
                      "Send ids and references, never credentials.")
            if key.lower() in PATCH_KEYS and value not in (None, "", False):
                _fail("bee_patch", f"{where} embeds a full patch",
                      "Carry an artifact digest and reference, never the patch body.")
            if key.lower() in CLAIM_KEYS and _truthy_claim(value):
                _fail("bee_client_claim", f"{where} claims a receiver-side outcome",
                      "A landing is evidence; remove verified/accepted/approved claims.")

        if isinstance(value, str):
            for pattern in SECRET_VALUE_PATTERNS:
                if pattern.search(value):
                    _fail("bee_secret", f"{where} looks like a secret value",
                          "Redact the credential before emitting the event.")
            for pattern in PRIVATE_PATH_PATTERNS:
                if pattern.search(value):
                    _fail("bee_private_path", f"{where} names a private filesystem path",
                          "Use a repository-relative path or a portable reference.")
            if any(marker in value for marker in PATCH_MARKERS):
                _fail("bee_patch", f"{where} contains a unified diff",
                      "Carry an artifact digest and reference, never a full patch.")


def _validate_envelope(event: Mapping[str, Any]) -> None:
    if not isinstance(event, Mapping):
        _fail("bee_invalid", "an event must be a JSON object", "Emit a CloudEvents 1.0 object.")

    for field in ("specversion", "id", "source", "type", "time", "subject", "data"):
        _require(event, field, "event")

    if event["specversion"] != "1.0":
        _fail("bee_cloud_events_version", f"specversion {event['specversion']!r} is not 1.0",
              "Emit CloudEvents specversion 1.0.")

    event_id = event["id"]
    if not isinstance(event_id, str) or not EVENT_ID_RE.match(event_id):
        _fail("bee_event_id", f"id {event_id!r} is neither a UUID nor a URN",
              "Use a canonical UUID text form or a URN.")

    source = event["source"]
    if not _is_text(source, maximum=2048) or not SOURCE_RE.match(source):
        _fail("bee_source", "source must be a non-empty URI-reference without whitespace",
              "Name the emitting coordinator with a stable URI or URN.")

    if event["type"] != EVENT_TYPE:
        _fail("bee_type", f"type {event['type']!r} is not {EVENT_TYPE!r}",
              f"Emit type {EVENT_TYPE}.")

    if not isinstance(event["time"], str) or not _valid_time(event["time"]):
        _fail("bee_time", f"time {event['time']!r} is not an RFC 3339 timestamp",
              "Emit an RFC 3339 date-time.")

    if not _is_text(event["subject"], maximum=512):
        _fail("bee_subject", "subject must be a non-empty string of at most 512 characters",
              "Name the worker task or attempt.")

    if "datacontenttype" in event and event["datacontenttype"] != "application/json":
        _fail("bee_invalid", "datacontenttype must be application/json when present",
              "Use application/json or omit the attribute.")
    if "dataschema" in event and not _is_text(event["dataschema"], maximum=2048):
        _fail("bee_invalid", "dataschema must be a non-empty string when present",
              "Use a schema URI or omit the attribute.")


def _validate_data(data: Any) -> None:
    if not isinstance(data, Mapping):
        _fail("bee_required", "data must be an object", "Emit the Bee Landed payload.")

    required = ("schema", "feature_id", "job_id", "task_id", "attempt_id",
                "coordinator", "backend", "state", "source_rev", "lease", "result")
    for field in required:
        _require(data, field, "data")

    allowed = set(required) | {"terminal_transition_id", "correlation_id", "causation_id"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail("bee_data_unknown", f"data carries unknown field(s): {', '.join(unknown)}",
              "Move extensions to the CloudEvents envelope root.")

    if data["schema"] != PAYLOAD_SCHEMA:
        _fail("bee_data_schema", f"data.schema {data['schema']!r} is not {PAYLOAD_SCHEMA!r}",
              f"Emit data.schema {PAYLOAD_SCHEMA}.")

    for field in ("feature_id", "job_id", "task_id", "attempt_id"):
        value = data[field]
        if not isinstance(value, str) or not ID_RE.match(value):
            _fail("bee_invalid", f"data.{field} must match {ID_RE.pattern}",
                  f"Use a stable id for {field}.")

    terminal = data.get("terminal_transition_id")
    if terminal is not None and not _is_text(terminal, maximum=256):
        _fail("bee_terminal_transition", "terminal_transition_id must be a non-empty string",
              "Record the durable transition id or omit it.")

    coordinator = data["coordinator"]
    if not isinstance(coordinator, Mapping):
        _fail("bee_coordinator", "data.coordinator must be an object", "Emit coordinator.identity.")
    if not _is_text(_require(coordinator, "identity", "data.coordinator"), maximum=256):
        _fail("bee_coordinator", "data.coordinator.identity must be a non-empty string",
              "Name the observing coordinator.")
    unknown = sorted(set(coordinator) - {"identity", "session"})
    if unknown:
        _fail("bee_coordinator", f"data.coordinator carries unknown field(s): {', '.join(unknown)}",
              "Only identity and optional session are allowed.")
    if "session" in coordinator and not _is_text(coordinator["session"], maximum=256):
        _fail("bee_coordinator", "data.coordinator.session must be a non-empty string",
              "Use a session id or omit it.")

    backend = data["backend"]
    if not isinstance(backend, Mapping):
        _fail("bee_backend", "data.backend must be an object", "Emit backend.harness.")
    if not _is_text(_require(backend, "harness", "data.backend"), maximum=128):
        _fail("bee_backend", "data.backend.harness must be a non-empty string",
              "Name the agent harness.")
    unknown = sorted(set(backend) - {"harness", "model"})
    if unknown:
        _fail("bee_backend", f"data.backend carries unknown field(s): {', '.join(unknown)}",
              "Only harness and optional model are allowed.")
    if "model" in backend and not _is_text(backend["model"], maximum=128):
        _fail("bee_backend", "data.backend.model must be a non-empty string",
              "Use a model id or omit it.")

    if data["state"] not in STATES:
        _fail("bee_state", f"state {data['state']!r} is not one of {', '.join(STATES)}",
              "A landing is terminal: succeeded, failed or cancelled.")

    revision = data["source_rev"]
    if not isinstance(revision, str) or not REVISION_RE.match(revision):
        _fail("bee_source_rev", f"source_rev {revision!r} is not lowercase 40 or 64 hex",
              "Use the exact lowercase revision the attempt ran against.")

    lease = data["lease"]
    if not isinstance(lease, Mapping):
        _fail("bee_lease", "data.lease must be an object", "Emit lease.sha256 and assigned_files.")
    lease_sha = _require(lease, "sha256", "data.lease")
    if not isinstance(lease_sha, str) or not SHA256_RE.match(lease_sha):
        _fail("bee_lease", "data.lease.sha256 must be lowercase 64 hex",
              "Use the digest of the granted lease.")
    files = _require(lease, "assigned_files", "data.lease")
    if not isinstance(files, list):
        _fail("bee_lease", "data.lease.assigned_files must be an array",
              "List repository-relative paths.")
    if len(files) > 1000:
        _fail("bee_oversized", "data.lease.assigned_files is too large",
              "A lease carries a bounded file list.")
    seen: set[str] = set()
    for index, path in enumerate(files):
        where = f"data.lease.assigned_files[{index}]"
        if not isinstance(path, str) or len(path) > 512 or not RELATIVE_PATH_RE.match(path):
            _fail("bee_lease", f"{where} is not a repository-relative path",
                  "Use a path like src/module.py without leading slash or backslash.")
        components = path.split("/")
        if any(part in ("", ".", "..") for part in components):
            _fail("bee_private_path", f"{where} contains traversal or an empty component",
                  "Use a normalized repository-relative path.")
        if path in seen:
            _fail("bee_lease", f"{where} duplicates an assigned file", "List each file once.")
        seen.add(path)
    unknown = sorted(set(lease) - {"sha256", "assigned_files"})
    if unknown:
        _fail("bee_lease", f"data.lease carries unknown field(s): {', '.join(unknown)}",
              "Only sha256 and assigned_files are allowed.")

    result = data["result"]
    if not isinstance(result, Mapping):
        _fail("bee_result", "data.result must be an object", "Emit result.available.")
    available = _require(result, "available", "data.result")
    if not isinstance(available, bool):
        _fail("bee_result", "data.result.available must be a boolean",
              "Say whether a result artifact exists.")
    digest = result.get("artifact_sha256")
    if digest is not None and (not isinstance(digest, str) or not SHA256_RE.match(digest)):
        _fail("bee_result", "data.result.artifact_sha256 must be lowercase 64 hex",
              "Use the artifact digest.")
    reference = result.get("reference")
    if reference is not None and not _is_text(reference, maximum=2048):
        _fail("bee_result", "data.result.reference must be a non-empty string",
              "Use a portable pointer to the artifact.")
    unknown = sorted(set(result) - {"available", "artifact_sha256", "reference"})
    if unknown:
        _fail("bee_result", f"data.result carries unknown field(s): {', '.join(unknown)}",
              "Only available, artifact_sha256 and reference are allowed.")
    if available and digest is None and reference is None:
        _fail("bee_result", "result.available is true but names no artifact",
              "Add artifact_sha256 or reference, or report available false.")

    for field in ("correlation_id", "causation_id"):
        if field in data and not _is_text(data[field], maximum=256):
            _fail("bee_invalid", f"data.{field} must be a non-empty string",
                  f"Use an id or omit {field}.")


def validate(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one Bee Landed event and return a detached copy."""
    if not isinstance(event, Mapping):
        _fail("bee_invalid", "an event must be a JSON object", "Emit a CloudEvents 1.0 object.")

    # Size first: an enormous event is refused before any claim is interpreted.
    try:
        size = len(canonical_json(event).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        _fail("bee_invalid", f"event is not JSON-serializable: {exc}", "Emit plain JSON values.")
    if size > MAX_EVENT_BYTES:
        _fail("bee_oversized", f"event is {size} bytes, above the {MAX_EVENT_BYTES}-byte limit",
              "Send ids and references; fetch the artifact separately.")

    _validate_envelope(event)
    _validate_data(event["data"])
    _refuse_embedded_data(event)
    return copy.deepcopy(dict(event))


def dedupe_key(event: Mapping[str, Any], terminal_transition_id: str | None = None) -> str:
    """sha256(attempt_id + ":" + state + ":" + terminal_transition_id).

    terminal_transition_id defaults to data.terminal_transition_id, then to the
    CloudEvents id. The same attempt landing twice with the same terminal state
    and transition therefore collapses to one key.
    """
    if not isinstance(event, Mapping):
        _fail("bee_dedupe", "an event must be a JSON object to compute a dedupe key",
              "Pass the whole CloudEvents envelope.")
    payload = event.get("data")
    data = payload if isinstance(payload, Mapping) else event
    if not isinstance(data, Mapping):
        _fail("bee_dedupe", "event.data is missing; no dedupe key can be computed",
              "Emit data.attempt_id and data.state.")
    attempt_id = data.get("attempt_id")
    state = data.get("state")
    transition = terminal_transition_id or data.get("terminal_transition_id") or event.get("id")
    if not all(isinstance(part, str) and part for part in (attempt_id, state, transition)):
        _fail("bee_dedupe", "attempt_id, state and terminal_transition_id are required for dedupe",
              "Emit all three, or rely on the CloudEvents id.")
    material = f"{attempt_id}:{state}:{transition}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate rizzstack.bee-landed/1 CloudEvents.")
    parser.add_argument("files", nargs="+", help="Bee Landed event JSON files")
    parser.add_argument("--dedupe", action="store_true", help="print the dedupe key after validation")
    args = parser.parse_args(argv)
    status = 0
    for name in args.files:
        try:
            event = json.loads(Path(name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{name}: error: {exc}", file=sys.stderr)
            status = 1
            continue
        try:
            validate(event)
        except BeeLandedError as exc:
            print(f"{name}: {exc.code}: {exc.message}", file=sys.stderr)
            status = 1
        else:
            if args.dedupe:
                print(dedupe_key(event))
            else:
                print(f"{name}: ok {dedupe_key(event)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
