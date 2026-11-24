#!/usr/bin/env python3
"""Anchor the uirizz action audit chain (rizzstack.audit-anchor/1). Stdlib only.

Reads the uirizz audit log (``actions.jsonl``) and its one rotation backup
(``actions.jsonl.1``), verifies their hash chains, and appends an anchor
``{log_id, seq, head_hash, ts, reason}`` to its own anchor file for every 100th
entry of a segment and for the last entry of a rotated-out segment. It never
writes the audit log, and it refuses to anchor anything when a chain does not
verify, a line does not parse, or a rotation does not continue its backup.

    python3 audit_anchor.py --log <plugin data>/audit/actions.jsonl --anchors <rails evidence>/audit-anchors.jsonl

Exit 0 when the anchors are up to date, 1 on any refusal (nothing is written).
Contract: observability/schemas/audit-anchor.schema.json. Verifier: uirizz.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "rizzstack.audit-anchor/1"
ZERO = "0" * 64


class AnchorError(Exception):
    """A refusal: the chain cannot be anchored as it is."""


def digest(prev: str, body: dict) -> str:
    """The uirizz gate's chain digest: sha256(prev + canonical JSON of the entry without hash)."""
    blob = prev + json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def read_segment(path: Path) -> list[dict]:
    """The entries of one log file, oldest first; any unparseable line is a refusal."""
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise AnchorError(f"{path.name}: line {number} is not JSON") from exc
        if not isinstance(item, dict):
            raise AnchorError(f"{path.name}: line {number} is not an object")
        entries.append(item)
    return entries


def verify_segment(entries: list[dict], name: str) -> None:
    """Every entry hashes correctly, links to the previous one and counts up from seq 1."""
    prev = entries[0].get("prev") if entries else None
    for index, entry in enumerate(entries):
        body = {k: v for k, v in entry.items() if k != "hash"}
        if entry.get("seq") != index + 1 or entry.get("prev") != prev:
            raise AnchorError(f"{name}: chain breaks at entry {index + 1}")
        if digest(str(entry.get("prev", "")), body) != entry.get("hash"):
            raise AnchorError(f"{name}: hash mismatch at entry {index + 1}")
        prev = entry["hash"]


def wanted(entries: list[dict], every: int) -> list[tuple[str, int, str, str]]:
    """(log_id, seq, head_hash, reason) for every interval anchor this segment owes."""
    if not entries:
        return []
    log_id = entries[0]["hash"]
    return [(log_id, e["seq"], e["hash"], "interval") for e in entries if e["seq"] % every == 0]


def rotation(backup: list[dict], current: list[dict]) -> tuple[str, int, str, str] | None:
    """The rotation anchor for the backup segment, if the current log continues it."""
    if not backup or not current or current[0].get("type") != "rotated":
        return None
    last = backup[-1]
    if current[0].get("prev") != last["hash"] or current[0].get("from_seq") != last["seq"]:
        raise AnchorError("the current log's rotation does not continue actions.jsonl.1")
    return (backup[0]["hash"], last["seq"], last["hash"], "rotation")


def load_segments(log: Path) -> tuple[list[dict], list[dict]]:
    """(backup, current) entries, both verified. A missing current log is a refusal."""
    if not log.is_file():
        raise AnchorError("audit log not found")
    current = read_segment(log)
    verify_segment(current, log.name)
    backup_path = log.with_name(log.name + ".1")
    backup = read_segment(backup_path) if backup_path.is_file() else []
    verify_segment(backup, backup_path.name)
    return backup, current


def pending(log: Path, anchors: Path, every: int) -> list[tuple[str, int, str, str]]:
    """Anchors owed and not yet recorded, in a stable order."""
    backup, current = load_segments(log)
    owed = wanted(backup, every) + wanted(current, every)
    rot = rotation(backup, current)
    if rot:
        owed.append(rot)
    done = set()
    if anchors.is_file():
        for row in read_segment(anchors):
            done.add((row.get("log_id"), row.get("seq"), row.get("reason")))
    return [a for a in owed if (a[0], a[1], a[3]) not in done]


def append(anchors: Path, rows: list[tuple[str, int, str, str]], ts: str) -> None:
    anchors.parent.mkdir(parents=True, exist_ok=True)
    with anchors.open("a", encoding="utf-8") as fh:
        for log_id, seq, head, reason in rows:
            record = {"schema": SCHEMA, "log_id": log_id, "seq": seq, "head_hash": head, "ts": ts, "reason": reason}
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", required=True, type=Path, help="uirizz audit log (actions.jsonl)")
    parser.add_argument("--anchors", required=True, type=Path, help="append-only anchor file")
    parser.add_argument("--every", type=int, default=100)
    parser.add_argument("--now", help="UTC timestamp to record (tests); default: now")
    args = parser.parse_args(argv)
    ts = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = pending(args.log, args.anchors, max(1, args.every))
    except (AnchorError, OSError) as exc:
        reason = exc if isinstance(exc, AnchorError) else type(exc).__name__
        print(f"audit-anchor: refused, nothing written: {reason}", file=sys.stderr)
        return 1
    if rows:
        append(args.anchors, rows, ts)
    print(f"audit-anchor: {len(rows)} new anchor(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
