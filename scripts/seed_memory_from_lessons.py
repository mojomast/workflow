#!/usr/bin/env python3
"""Seed a ``rizzstack.memory/1`` vault from the agent lessons catalogue.

Every ``### L-NN · Title`` section in ``docs/28-agent-lessons.md`` becomes one
``learning`` memory with id ``lesson-l-nn``. The seeder writes through
:class:`rizstack_memory.DiskVault`, so it is subject to the same write gate as
any other producer: no authority grant means the files land in the seed
writer's quarantine subtree and stay there until a human promotes them.

Re-running is idempotent: an unchanged body and timestamp produce the same
digest and the file is left alone; a changed digest is written as an update
using the digest that was read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rizzstack_memory import (  # noqa: E402
    CONTRACT,
    TYPE_POLICY,
    ContractError,
    DiskVault,
    memory_sha,
    parse_memory,
    quarantine_prefix,
)

WRITER = "agent:lessons-seed"
LESSONS_PATH = "docs/28-agent-lessons.md"
LESSONS_FILE = REPO_ROOT / LESSONS_PATH
HEADING_RE = re.compile(r"^### (L-\d{2}) · (.+?)\s*$")
STOP_RE = re.compile(r"^(?:### |## )")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_lessons(text: str) -> list:
    """Return ``(id, title, body)`` for every lesson section, in file order."""
    lines = text.splitlines()
    lessons = []
    index = 0
    while index < len(lines):
        match = HEADING_RE.match(lines[index])
        if not match:
            index += 1
            continue
        code, title = match.group(1), match.group(2)
        end = index + 1
        while end < len(lines) and not STOP_RE.match(lines[end]):
            end += 1
        body_lines = ["# " + lines[index][4:]] + lines[index + 1 : end]
        body = "\n".join(body_lines).rstrip("\n") + "\n"
        lessons.append(("lesson-" + code.lower(), title, body))
        index = end
    return lessons


def build_record(memory_id: str, title: str, body: str, now: str, code: str) -> dict:
    record = {
        "schema": CONTRACT,
        "id": memory_id,
        "type": "learning",
        "created": now,
        "modified": now,
        "retention": {
            "policy": TYPE_POLICY["learning"],
            "expires": None,
            "superseded_by": None,
        },
        "sources": [
            {
                "kind": "file",
                "ref": LESSONS_PATH,
                "note": f"{code} {title}",
            }
        ],
        "sha": "",
    }
    record["sha"] = memory_sha(record, body)
    return record


def write_op(path: str, record: dict, body: str, expected_sha) -> dict:
    return {
        "op": "write",
        "writer": WRITER,
        "path": path,
        "memory": record,
        "body": body,
        "expected_sha": expected_sha,
        "authority": None,
    }


def existing_sha(root: Path, path: str):
    """Read an existing digest without bootstrapping the vault (for --dry-run)."""
    target = root / path
    if not target.is_file():
        return None
    record, _ = parse_memory(target.read_text(encoding="utf-8"))
    return record["sha"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, help="vault directory to seed")
    parser.add_argument("--now", default=utc_now(), help="RFC 3339 timestamp (default: now, UTC)")
    parser.add_argument("--dry-run", action="store_true", help="list what would be written and touch nothing")
    args = parser.parse_args(argv)

    try:
        lessons = parse_lessons(LESSONS_FILE.read_text(encoding="utf-8"))
        prefix = quarantine_prefix(WRITER)
        root = Path(args.vault)
        vault = None if args.dry_run else DiskVault(root)

        written = 0
        unchanged = 0
        for memory_id, title, body in lessons:
            code = memory_id[len("lesson-") :].upper()
            record = build_record(memory_id, title, body, args.now, code)
            path = prefix + memory_id + ".md"
            if args.dry_run:
                stored = existing_sha(root, path)
            else:
                try:
                    stored = vault.read(path)["current_sha"]
                except ContractError as err:
                    if err.code != "not_found":
                        raise
                    stored = None
            if stored == record["sha"]:
                unchanged += 1
                action = "unchanged"
            else:
                written += 1
                action = "would write" if args.dry_run else ("updated" if stored else "written")
                if not args.dry_run:
                    vault.write(write_op(path, record, body, stored))
            print(f"{memory_id} {action}")

        summary = {
            "writer": WRITER,
            "written": written,
            "unchanged": unchanged,
            "dry_run": bool(args.dry_run),
        }
        print(json.dumps(summary, sort_keys=True))
        return 0
    except ContractError as err:
        print(f"{err.code}: {err.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
