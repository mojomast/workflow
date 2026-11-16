#!/usr/bin/env python3
"""rizzstack decision-queue notifier.

A durable, stdlib-only notifier over the written in-repo decision-queue
contract:

- ``docs/22-autonomy-architecture.md`` section 5 (the feature queue): the
  closed queue status vocabulary and the two owner-needed pending kinds —
  ``needs_approval`` waits on a decision, ``blocked`` waits on a blocker.
- ``observability/schemas/snapshot.schema.json``: the backlog section and row
  shapes (this module pins the required fields and the status enum and treats
  any mismatch as drift).
- ``contrib/rizzstack-observability/collector.py``: the ``queue.json``
  normalization the collector's backlog section applies, and the snapshot
  document the collector emits. The notifier reads either a ``queue.json``
  directly (same normalization, unknown statuses reported as drift) or an
  already-assembled snapshot document.

Severity design (anti-fatigue): owner-needed items are severity-high and get
chat delivery plus a desktop notification. Every routine status is
dashboard-only: it lands in the status document's dashboard block and nothing
is pushed. ``failed`` is excluded from notification: per the contract it is a
verify outcome, not an owner request.

Durability: one status document (``status.json``) is the persisted delivery
marker. Items are deduped by item id (``feature_id/kind``): a pending item is
notified once, then only re-notified when it has been pending for at least
``escalate_after_s`` (aging escalation, config data) or when its last delivery
attempt failed (degrade-to-marker). A failed chat delivery never loses an
item: the item stays in the marker with a generic error code and is retried on
every later pass until it is delivered. Delivery is at-least-once: a crash
between delivery and the marker write may re-notify, it can never silently
drop. The status document, stderr and chat errors never carry the chat
endpoint or any credential material — only generic codes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

NOTIFIER_NAME = "rizzstack-decision-notifier"
STATUS_SCHEMA = "rizzstack.notifier/status/1"
SNAPSHOT_SCHEMA = "rizzstack.observability/snapshot/1"

# docs/22-autonomy-architecture.md section 5: "Statuses: queued, claimed,
# running, ready_for_review, blocked, failed, needs_approval." The
# snapshot.schema.json $defs.queue_status enum pins the same vocabulary; the
# vocabulary is closed and this notifier never invents a status.
QUEUE_STATUSES = frozenset(
    {
        "queued",
        "claimed",
        "running",
        "ready_for_review",
        "blocked",
        "failed",
        "needs_approval",
    }
)
SECTION_STATUSES = frozenset({"live", "stale", "unavailable"})

# The owner-needed pending kinds, per the contract reading of docs/22
# section 5: needs_approval waits on a decision, blocked waits on a blocker.
# failed is deliberately excluded. This is one line on purpose: if the
# wf#43/#44 review says otherwise, the set changes here (or through the
# pending_kinds config key, which reports its divergence as drift).
PENDING_KINDS = {"needs_approval": "decision", "blocked": "blocker"}

# snapshot.schema.json $defs.backlog_feature.required and
# $defs.backlog_section.required, pinned as module data.
BACKLOG_ROW_REQUIRED = ("schema", "generated_at", "feature_id", "job_id", "status", "depends_on")
BACKLOG_SECTION_REQUIRED = ("status", "error", "collected_at", "features", "counts")

KIND_LABELS = {"decision": "decision needed", "blocker": "unblock needed"}
APP_NAME = "rizzstack"
CHAT_WEBHOOK_ENV = "RIZZSTACK_NOTIFIER_CHAT_WEBHOOK"
DESKTOP_TIMEOUT_S = 10.0

DEFAULT_CONFIG: dict[str, Any] = {
    "escalate_after_s": 14400,
    "stale_after_s": 1800,
    "chat_timeout_s": 10,
    "chat_message_max_chars": 200,
    "resolved_retention_s": 604800,
}
CONFIG_KEYS = frozenset(DEFAULT_CONFIG) | {"pending_kinds"}
INT_CONFIG_KEYS = frozenset(
    {"escalate_after_s", "stale_after_s", "chat_message_max_chars", "resolved_retention_s"}
)
POSITIVE_ZERO_KEYS = frozenset({"stale_after_s", "resolved_retention_s"})

ID_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")

Drift = list[dict[str, Any]]
Deliverer = Callable[..., tuple[bool, str | None]]

MAX_DRIFT_ROWS = 50


# ------------------------------------------------------------------ helpers
def utc_now_string(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def id_token(value: Any) -> str | None:
    if isinstance(value, str) and ID_TOKEN_RE.match(value):
        return value
    return None


def scrub(value: Any, limit: int = 200) -> str | None:
    """Mask URLs, drop control characters, bound the length.

    Mirrors the collector's scrub(): free text that reaches a record must
    carry no link and no control character, and it must stay short.
    """
    if value is None:
        return None
    text = URL_RE.sub("[link]", str(value))
    text = CONTROL_RE.sub(" ", text).strip()
    if not text:
        return None
    return text[:limit]


def drift_entry(code: str, detail: Any) -> dict[str, Any]:
    return {"code": code, "detail": scrub(detail, 200) or code}


def file_age_s(path: Path, now: datetime) -> int | None:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    return max(0, int(now.timestamp() - stamp))


def read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ------------------------------------------------------------------- config
def load_config(path: str | Path | None) -> tuple[dict[str, Any], Drift, str | None]:
    """Load notifier config data. Returns (config, drift, error).

    ``error`` is a generic refusal code; the caller exits 2. Unknown keys are
    reported as drift and ignored. A ``pending_kinds`` override that diverges
    from the written contract is honored and reported as contract divergence.
    """
    config: dict[str, Any] = dict(DEFAULT_CONFIG)
    config["pending_kinds"] = dict(PENDING_KINDS)
    drift: Drift = []
    if path is None:
        return config, drift, None
    try:
        with Path(path).open(encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return config, drift, "config_unreadable"
    if not isinstance(raw, dict):
        return config, drift, "config_not_a_dict"
    for key, value in raw.items():
        if key == "pending_kinds":
            if not isinstance(value, dict) or not all(
                isinstance(k, str) and k and isinstance(v, str) and v for k, v in value.items()
            ):
                return config, drift, "config_bad_value"
            config["pending_kinds"] = dict(value)
        elif key in INT_CONFIG_KEYS:
            if isinstance(value, bool) or not isinstance(value, int):
                return config, drift, "config_bad_value"
            floor = 0 if key in POSITIVE_ZERO_KEYS else 1
            if value < floor:
                return config, drift, "config_bad_value"
            config[key] = value
        elif key == "chat_timeout_s":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                return config, drift, "config_bad_value"
            config[key] = float(value)
        else:
            drift.append(drift_entry("config_unknown_key", f"unknown config key {key}"))
    return config, drift, None


# ------------------------------------------------------------------- source
def _queue_rows(data: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    features = data.get("features")
    rows: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(features, list):
        rows = [
            (str(f.get("feature_id") or f"feature-{index}"), f)
            for index, f in enumerate(features)
            if isinstance(f, dict)
        ]
    elif isinstance(features, dict):
        rows = [(str(key), value) for key, value in features.items() if isinstance(value, dict)]
    else:
        rows = [(str(key), value) for key, value in data.items() if isinstance(value, dict)]
    return rows


def _normalize_queue_row(
    key: str, row: Mapping[str, Any], generated: str
) -> tuple[dict[str, Any] | None, Drift]:
    drift: Drift = []
    fid = id_token(key)
    if fid is None:
        drift.append(drift_entry("backlog_row_shape", f"backlog feature id {key!r} is not an id token"))
        return None, drift
    status_raw = row.get("status")
    if not isinstance(status_raw, str):
        drift.append(drift_entry("backlog_row_shape", f"backlog row {fid} carries no status"))
        return None, drift
    status_norm = status_raw.strip().lower().replace("-", "_").replace(" ", "_")
    if status_norm not in QUEUE_STATUSES:
        drift.append(
            drift_entry(
                "status_outside_vocabulary",
                f"queue status {status_raw!r} is outside the docs/22 section 5 vocabulary",
            )
        )
        return None, drift
    job = id_token(row.get("job_id"))
    if row.get("job_id") is not None and job is None:
        drift.append(drift_entry("backlog_row_shape", f"backlog row {fid} carries a malformed job id"))
    depends: list[str] = []
    for token in row.get("depends_on") or []:
        clean = id_token(token)
        if clean:
            depends.append(clean)
    return (
        {
            "schema": SNAPSHOT_SCHEMA,
            "generated_at": generated,
            "feature_id": fid,
            "job_id": job,
            "status": status_norm,
            "depends_on": depends,
        },
        drift,
    )


def _snapshot_rows(backlog: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], Drift]:
    drift: Drift = []
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    raw_counts = backlog.get("counts")
    if isinstance(raw_counts, dict):
        counts = {str(k): v for k, v in raw_counts.items() if isinstance(v, int) and v >= 0}
    elif raw_counts is not None:
        drift.append(drift_entry("backlog_section_shape", "backlog counts are not a count map"))
    raw_rows = backlog.get("features")
    if not isinstance(raw_rows, list):
        drift.append(drift_entry("backlog_section_shape", "backlog features are not a list"))
        return rows, counts, drift
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            drift.append(drift_entry("backlog_row_shape", f"backlog row {index} is not an object"))
            continue
        if any(key not in raw for key in BACKLOG_ROW_REQUIRED):
            drift.append(drift_entry("backlog_row_shape", f"backlog row {index} misses required fields"))
            continue
        fid = id_token(raw.get("feature_id"))
        generated = raw.get("generated_at")
        status = raw.get("status")
        depends_raw = raw.get("depends_on")
        if (
            raw.get("schema") != SNAPSHOT_SCHEMA
            or fid is None
            or parse_ts(generated) is None
            or not isinstance(status, str)
            or status not in QUEUE_STATUSES
            or not isinstance(depends_raw, list)
            or (raw.get("job_id") is not None and id_token(raw.get("job_id")) is None)
        ):
            code = (
                "status_outside_vocabulary"
                if isinstance(status, str) and status not in QUEUE_STATUSES
                else "backlog_row_shape"
            )
            drift.append(drift_entry(code, f"backlog row {fid or index} violates the snapshot backlog shape"))
            continue
        depends = [tok for tok in (id_token(d) for d in depends_raw) if tok]
        rows.append(
            {
                "schema": SNAPSHOT_SCHEMA,
                "generated_at": str(generated),
                "feature_id": fid,
                "job_id": id_token(raw.get("job_id")),
                "status": status,
                "depends_on": depends,
            }
        )
    return rows, counts, drift


def read_backlog(
    path: Path, now: datetime, config: Mapping[str, Any]
) -> tuple[dict[str, Any], Drift, str]:
    """Read the decision-queue source and return (section, drift, kind).

    ``kind`` is ``queue`` for a queue.json read with the collector's
    normalization, ``snapshot`` for an assembled rizzstack.observability
    snapshot document, and ``none`` when nothing readable was found. Any
    divergence from the written contract is reported as drift instead of
    being silently folded in.
    """
    generated = utc_now_string(now)
    drift: Drift = []
    data = read_json_dict(path)
    if data is None:
        if path.exists():
            drift.append(drift_entry("source_unreadable", "the source file is not a JSON object"))
            kind = "none"
        else:
            kind = "none"
        return (
            {"status": "unavailable", "error": "source_missing" if kind == "none" else "source_unreadable",
             "collected_at": generated, "features": [], "counts": {}},
            drift,
            "none",
        )
    if data.get("schema") == SNAPSHOT_SCHEMA:
        return _snapshot_section(data, generated, drift)
    if "schema" in data:
        drift.append(
            drift_entry(
                "snapshot_schema_mismatch",
                f"the source document names schema {data.get('schema')!r}, not {SNAPSHOT_SCHEMA}",
            )
        )
        return _unavailable(generated, "snapshot_schema_mismatch"), drift, "none"
    return _queue_section(path, data, now, generated, config, drift)


def _unavailable(generated: str, error: str) -> dict[str, Any]:
    return {"status": "unavailable", "error": error, "collected_at": generated, "features": [], "counts": {}}


def _snapshot_section(data: Mapping[str, Any], generated: str, drift: Drift) -> tuple[dict[str, Any], Drift, str]:
    backlog = data.get("backlog")
    if not isinstance(backlog, Mapping) or any(key not in backlog for key in BACKLOG_SECTION_REQUIRED):
        drift.append(drift_entry("backlog_section_shape", "the snapshot backlog section misses required fields"))
        return _unavailable(generated, "backlog_section_invalid"), drift, "snapshot"
    status = backlog.get("status")
    if status not in SECTION_STATUSES:
        drift.append(drift_entry("unknown_section_status", f"backlog section status {status!r} is not a section status"))
        return _unavailable(generated, "backlog_section_invalid"), drift, "snapshot"
    rows, counts, row_drift = _snapshot_rows(backlog)
    drift.extend(row_drift)
    error = backlog.get("error")
    return (
        {
            "status": status,
            "error": scrub(error, 200) if isinstance(error, str) else None,
            "collected_at": generated,
            "features": rows,
            "counts": counts,
        },
        drift,
        "snapshot",
    )


def _queue_section(
    path: Path,
    data: Mapping[str, Any],
    now: datetime,
    generated: str,
    config: Mapping[str, Any],
    drift: Drift,
) -> tuple[dict[str, Any], Drift, str]:
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for key, raw in _queue_rows(data):
        row, row_drift = _normalize_queue_row(key, raw, generated)
        drift.extend(row_drift)
        if row is None:
            continue
        rows.append(row)
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    status, error = "live", None
    age = file_age_s(path, now)
    stale_after = int(config.get("stale_after_s") or 0)
    if age is not None and age > stale_after:
        status, error = "stale", "queue_older_than_threshold"
    return (
        {"status": status, "error": error, "collected_at": generated, "features": rows, "counts": counts},
        drift,
        "queue",
    )


# ------------------------------------------------------------------- marker
def load_marker(path: Path) -> dict[str, Any]:
    """Load the persisted delivery marker; a damaged marker starts fresh.

    A fresh marker re-notifies pending items (at-least-once), it never
    silently drops them.
    """
    data = read_json_dict(path)
    if data is not None and data.get("schema") == STATUS_SCHEMA and isinstance(data.get("items"), dict):
        return data
    return {"schema": STATUS_SCHEMA, "items": {}}


def save_marker(path: Path, doc: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------- delivery
def deliver_chat(webhook: str, message: str, timeout_s: float) -> tuple[bool, str | None]:
    """POST one chat message. Every failure is one generic code: the chat
    endpoint, its response body and any exception text are never surfaced."""
    payload = json.dumps({"text": message}).encode("utf-8")
    request = urllib.request.Request(
        webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - operator-configured endpoint
            response.read()
    except Exception:  # noqa: BLE001 - the failure reason itself must not leak
        return False, "chat_delivery_failed"
    return True, None


def deliver_desktop(cmd: str, summary: str, body: str) -> tuple[bool, str | None]:
    """One freedesktop notification via a fixed argv; never a shell."""
    argv = [cmd, "--app-name", APP_NAME, summary, body]
    try:
        proc = subprocess.run(  # noqa: S603 - argv is fixed, no user input
            argv, capture_output=True, timeout=DESKTOP_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False, "desktop_unavailable"
    if proc.returncode != 0:
        return False, "desktop_unavailable"
    return True, None


def build_chat_deliverer(webhook: str | None, timeout_s: float) -> Deliverer | None:
    if not webhook:
        return None

    def deliver(message: str) -> tuple[bool, str | None]:
        return deliver_chat(webhook, message, timeout_s)

    return deliver


def build_desktop_deliverer(cmd: str | None) -> Deliverer | None:
    if not cmd:
        return None

    def deliver(summary: str, body: str) -> tuple[bool, str | None]:
        return deliver_desktop(cmd, summary, body)

    return deliver


# ----------------------------------------------------------------- messages
def chat_message(item: Mapping[str, Any], limit: int, escalated: bool) -> str:
    label = KIND_LABELS.get(str(item.get("kind")), str(item.get("kind")))
    text = f"{NOTIFIER_NAME}: {label} - {item.get('feature_id')} ({item.get('queue_status')})"
    if escalated:
        text = f"{text}, escalation {int(item.get('escalations', 0)) + 1} since {item.get('first_seen_at')}"
    return scrub(text, limit) or NOTIFIER_NAME


def desktop_summary(item: Mapping[str, Any]) -> str:
    return f"{APP_NAME}: {item.get('kind')}"


# ------------------------------------------------------------------ the pass
def _notify(
    item: dict[str, Any],
    *,
    config: Mapping[str, Any],
    chat: Deliverer | None,
    desktop: Deliverer | None,
    stamp: str,
    escalated: bool,
    retry_only: bool,
) -> str | None:
    """Deliver one item. Returns the generic failure code, or None."""
    message = chat_message(item, int(config["chat_message_max_chars"]), escalated)
    if chat is None:
        ok, code = False, "chat_not_configured"
    else:
        ok, code = chat(message)
    if ok:
        item["deliveries"] = int(item.get("deliveries") or 0) + 1
        item["last_notified_at"] = stamp
        item["last_error"] = None
        item["state"] = "delivered"
    else:
        item["last_error"] = code
        item["state"] = "degraded"
    if escalated:
        item["escalations"] = int(item.get("escalations") or 0) + 1
    if not retry_only:
        if desktop is not None:
            desktop_ok, desktop_code = desktop(desktop_summary(item), message)
            item["last_desktop_at"] = stamp
            if desktop_ok:
                item.pop("last_desktop_error", None)
            else:
                item["last_desktop_error"] = desktop_code
        else:
            item.pop("last_desktop_error", None)
            item.pop("last_desktop_at", None)
    return None if ok else code


def run_pass(
    section: Mapping[str, Any],
    drift: Drift,
    source_kind: str,
    source_path: str | None,
    marker: dict[str, Any],
    config: Mapping[str, Any],
    chat: Deliverer | None,
    desktop: Deliverer | None,
    now: datetime,
) -> tuple[dict[str, Any], int]:
    """One notifier pass. Returns (status document, exit code).

    Exit 0 is a clean pass; exit 1 is a degraded pass (source unavailable, a
    chat failure this pass, or items still degraded). The status document is
    the delivery marker: the caller persists it after the pass.
    """
    stamp = utc_now_string(now)
    entries: Drift = [dict(entry) for entry in drift]
    items: dict[str, dict[str, Any]] = {}
    if isinstance(marker, dict) and marker.get("schema") == STATUS_SCHEMA and isinstance(marker.get("items"), dict):
        items = marker["items"]
    else:
        entries.append(drift_entry("status_marker_schema", "the delivery marker was not readable; starting fresh"))
        marker = {"schema": STATUS_SCHEMA, "items": items}

    pending_kinds: Mapping[str, str] = config.get("pending_kinds") or PENDING_KINDS
    if dict(pending_kinds) != dict(PENDING_KINDS):
        added = sorted(set(pending_kinds) - set(PENDING_KINDS))
        removed = sorted(set(PENDING_KINDS) - set(pending_kinds))
        detail = "pending-kind set diverges from docs/22 section 5"
        if added:
            detail += f"; added: {', '.join(added)}"
        if removed:
            detail += f"; removed: {', '.join(removed)}"
        entries.append(drift_entry("contract_divergence", detail))

    source_ok = section.get("status") in ("live", "stale")
    rows: list[Mapping[str, Any]] = list(section.get("features") or []) if source_ok else []

    seen_kinds: dict[str, str] = {}
    chat_error: str | None = None

    if source_ok:
        for row in rows:
            status = str(row.get("status"))
            kind = pending_kinds.get(status)
            if kind is None:
                continue
            fid = str(row.get("feature_id"))
            seen_kinds[fid] = kind
            item_id = f"{fid}/{kind}"
            item = items.get(item_id)
            if item is None or item.get("state") == "resolved":
                if item is None:
                    item = {
                        "feature_id": fid,
                        "job_id": row.get("job_id"),
                        "kind": kind,
                        "queue_status": status,
                        "first_seen_at": stamp,
                        "last_seen_at": stamp,
                        "state": "",
                        "last_notified_at": None,
                        "last_desktop_at": None,
                        "deliveries": 0,
                        "escalations": 0,
                        "last_error": None,
                    }
                    items[item_id] = item
                else:
                    item.update(
                        first_seen_at=stamp,
                        last_seen_at=stamp,
                        queue_status=status,
                        job_id=row.get("job_id"),
                        last_notified_at=None,
                        last_desktop_at=None,
                        deliveries=0,
                        escalations=0,
                        last_error=None,
                        state="",
                    )
                    item.pop("resolved_at", None)
                    item.pop("resolved_reason", None)
                code = _notify(item, config=config, chat=chat, desktop=desktop, stamp=stamp, escalated=False, retry_only=False)
                if code:
                    chat_error = chat_error or code
                continue
            item["last_seen_at"] = stamp
            item["queue_status"] = status
            item["job_id"] = row.get("job_id")
            if item.get("state") == "degraded":
                code = _notify(item, config=config, chat=chat, desktop=desktop, stamp=stamp, escalated=False, retry_only=True)
                if code:
                    chat_error = chat_error or code
                continue
            last = parse_ts(item.get("last_notified_at"))
            age = (now - last).total_seconds() if last is not None else None
            if age is None or age >= float(config["escalate_after_s"]):
                code = _notify(item, config=config, chat=chat, desktop=desktop, stamp=stamp, escalated=True, retry_only=False)
                if code:
                    chat_error = chat_error or code

        for item_id, item in items.items():
            if item.get("state") == "resolved":
                continue
            fid = str(item.get("feature_id"))
            if fid in seen_kinds:
                if seen_kinds[fid] != item.get("kind"):
                    item["state"] = "resolved"
                    item["resolved_at"] = stamp
                    item["resolved_reason"] = "kind_changed"
                continue
            item["state"] = "resolved"
            item["resolved_at"] = stamp
            item["resolved_reason"] = "left_pending_set"

    retention = float(config["resolved_retention_s"])
    for item_id in list(items):
        item = items[item_id]
        if item.get("state") == "resolved":
            resolved = parse_ts(item.get("resolved_at"))
            if resolved is not None and (now - resolved).total_seconds() > retention:
                del items[item_id]

    routine = [
        {"feature_id": str(row.get("feature_id")), "status": str(row.get("status"))}
        for row in rows
        if str(row.get("status")) not in pending_kinds
    ]
    routine.sort(key=lambda entry: entry["feature_id"])
    owner_needed = sum(1 for row in rows if str(row.get("status")) in pending_kinds)
    degraded_items = [item for item in items.values() if item.get("state") == "degraded"]
    source_unavailable = section.get("status") == "unavailable"
    pass_result = "ok" if not (source_unavailable or chat_error or degraded_items) else "degraded"

    if len(entries) > MAX_DRIFT_ROWS:
        entries = entries[:MAX_DRIFT_ROWS]
        entries.append(drift_entry("drift_truncated", f"drift capped at {MAX_DRIFT_ROWS} rows this pass"))

    doc: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "notifier": NOTIFIER_NAME,
        "generated_at": stamp,
        "source": {
            "kind": source_kind,
            "path": scrub(source_path, 200) if source_path else None,
            "status": section.get("status"),
            "error": section.get("error"),
        },
        "run": {
            "pass_result": pass_result,
            "chat_configured": chat is not None,
            "chat_error": chat_error,
            "exit": 0 if pass_result == "ok" else 1,
        },
        "dashboard": {
            "counts": dict(section.get("counts") or {}),
            "owner_needed": owner_needed,
            "routine": routine,
        },
        "items": items,
        "drift": entries,
    }
    marker["schema"] = STATUS_SCHEMA
    marker["items"] = items
    return doc, 0 if pass_result == "ok" else 1


# ---------------------------------------------------------------------- CLI
def resolve_chat_webhook(args: argparse.Namespace) -> str | None:
    """The chat endpoint is read at runtime from a file or the environment.

    It is never inlined, never printed, never logged and never copied into a
    record.
    """
    file_path = getattr(args, "chat_webhook_file", None)
    if file_path:
        try:
            text = Path(file_path).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text or None
    value = os.environ.get(CHAT_WEBHOOK_ENV, "").strip()
    return value or None


class QuietArgumentParser(argparse.ArgumentParser):
    """argparse that never echoes argv in errors."""

    def error(self, message: str) -> None:  # type: ignore[override]
        print("argument error; run with --help for usage", file=sys.stderr)
        raise SystemExit(2)


def default_status_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_home) / NOTIFIER_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = QuietArgumentParser(
        prog=NOTIFIER_NAME,
        description="Durable rizzstack decision-queue notifier.",
        add_help=True,
    )
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".hermes" / "plugin-state", help="directory holding queue.json")
    parser.add_argument("--snapshot", type=Path, default=None, help="read an assembled rizzstack.observability snapshot document instead of queue.json")
    parser.add_argument("--status-dir", type=Path, default=default_status_dir(), help="directory for the status.json delivery marker")
    parser.add_argument("--config", type=Path, default=None, help="JSON config overrides")
    parser.add_argument("--chat-webhook-file", default=None, help="file holding the chat webhook (0600); falls back to the chat webhook environment variable")
    parser.add_argument("--chat-timeout-s", type=float, default=None, help="chat delivery timeout in seconds")
    parser.add_argument("--desktop-cmd", default="notify-send", help="desktop notification command")
    parser.add_argument("--no-desktop", action="store_true", help="disable desktop notifications")
    parser.add_argument("--loop", action="store_true", help="run one pass every --interval-s instead of one pass")
    parser.add_argument("--interval-s", type=int, default=300, help="seconds between passes in loop mode")
    parser.add_argument("--print", action="store_true", dest="print_status", help="print the status document to stdout")
    return parser


def _one_pass(
    args: argparse.Namespace,
    config: dict[str, Any],
    chat: Deliverer | None,
    desktop: Deliverer | None,
    config_drift: Drift,
) -> tuple[dict[str, Any], int]:
    if args.chat_timeout_s is not None:
        if args.chat_timeout_s <= 0:
            print("chat timeout must be positive", file=sys.stderr)
            raise SystemExit(2)
        config["chat_timeout_s"] = float(args.chat_timeout_s)
    source_path = Path(args.snapshot) if args.snapshot else (args.state_dir / "queue.json")
    status_file = Path(args.status_dir) / "status.json"
    now = datetime.now(timezone.utc)
    section, drift, kind = read_backlog(source_path, now, config)
    marker = load_marker(status_file)
    doc, code = run_pass(section, drift + config_drift, kind, str(source_path), marker, config, chat, desktop, now)
    save_marker(status_file, doc)
    return doc, code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config, config_drift, error = load_config(args.config)
    if error:
        print(f"{error}; refusing to start", file=sys.stderr)
        return 2
    webhook = resolve_chat_webhook(args)
    chat = build_chat_deliverer(webhook, config["chat_timeout_s"])
    desktop = None if args.no_desktop else build_desktop_deliverer(args.desktop_cmd)
    try:
        while True:
            doc, code = _one_pass(args, config, chat, desktop, config_drift)
            if args.print_status:
                print(json.dumps(doc, indent=2, sort_keys=True))
            if not args.loop:
                return code
            time.sleep(args.interval_s)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
