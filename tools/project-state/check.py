#!/usr/bin/env python3
"""Reference checker for workflow.project-state/v1 (docs/18).

A protocol aid, not a service: it reads a repository, decides whether new
work may start, and explains why not. Standard library only. Exit codes:
0 = dispatch allowed, 3 = refused (parked/archived/invalid), 2 = usage.

    python3 tools/project-state/check.py REPO_ROOT [--expect-generation N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

STATE_REL = ".workflow/project-state.json"
SCHEMA = "workflow.project-state/v1"
STATES = ("active", "parked", "archived")
BLOCKED = ("parked", "archived")
TRANSITIONS = {
    ("active", "parked"), ("active", "archived"), ("parked", "active"),
    ("parked", "archived"), ("archived", "active"),
}
TS = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$")
ACTOR = re.compile(r"^(human|agent|bot|orbit|hyvv|bundlebees):[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# Same text rule as the schema's snapshot_path pattern.
SAFE_PATH = re.compile(r"^(?!/)(?!.*(?:^|/)[.]{1,2}(?:/|$))(?!.*//)(?!.*/$)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
MAX_STATE_BYTES = 256 * 1024
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def is_link_like(path: Path, st: os.stat_result) -> bool:
    """Symlink, Windows junction, or any other reparse point (mount point, app link...).

    os.path.islink / S_ISLNK miss directory junctions on Windows, so a junction
    could otherwise carry snapshot_path outside the repository.
    """
    if stat.S_ISLNK(st.st_mode):
        return True
    if getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
    try:
        return bool(isjunction and isjunction(path))
    except OSError:
        return True


class StateError(Exception):
    """A state file that must be treated as invalid (fail closed)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def safe_snapshot(repo_root: Path, rel: str) -> Path:
    """Resolve rel inside repo_root. Refuse traversal, symlinks, non-files."""
    if not isinstance(rel, str) or len(rel) > 244 or not SAFE_PATH.match(rel):
        raise StateError("snapshot_path_invalid", "snapshot_path is not a safe repo-relative path")
    root = Path(os.path.realpath(repo_root))
    cur = root
    for part in rel.split("/"):
        cur = cur / part
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            raise StateError("snapshot_missing", "snapshot_path does not exist") from None
        if is_link_like(cur, st):
            raise StateError("snapshot_path_symlink", "snapshot_path has a symlink, junction or reparse-point component")
    if not stat.S_ISREG(os.lstat(cur).st_mode):
        raise StateError("snapshot_path_invalid", "snapshot_path is not a regular file")
    real = Path(os.path.realpath(cur))
    if root != real and root not in real.parents:
        raise StateError("snapshot_path_escape", "snapshot_path resolves outside the repository")
    return real


def validate(doc: object, repo_root: Path | None = None) -> dict:
    if not isinstance(doc, dict):
        raise StateError("invalid_project_state", "state file is not an object")
    allowed = {"schema", "schema_version", "project", "display_name", "state", "at", "by",
               "reason", "generation", "snapshot_path", "primary_repo", "history"}
    extra = set(doc) - allowed
    if extra:
        raise StateError("invalid_project_state", "unknown fields: " + ", ".join(sorted(extra)))
    if doc.get("schema") != SCHEMA or doc.get("schema_version") != "v1":
        raise StateError("invalid_project_state", "not workflow.project-state/v1")
    if not isinstance(doc.get("project"), str) or not PROJECT.match(doc["project"]):
        raise StateError("invalid_project_state", "project id is invalid")

    def entry_ok(e: object, where: str) -> None:
        if not isinstance(e, dict) or e.get("state") not in STATES:
            raise StateError("invalid_project_state", f"{where}: state is invalid")
        if not isinstance(e.get("at"), str) or not TS.match(e["at"]):
            raise StateError("invalid_project_state", f"{where}: at is invalid")
        if not isinstance(e.get("by"), str) or not ACTOR.match(e["by"]):
            raise StateError("invalid_project_state", f"{where}: by is invalid")
        r = e.get("reason")
        if not isinstance(r, str) or not r.strip() or len(r) > 500:
            raise StateError("invalid_project_state", f"{where}: reason is invalid")

    entry_ok(doc, "state")
    hist = doc.get("history")
    if not isinstance(hist, list) or not hist:
        raise StateError("invalid_project_state", "history is missing or empty")
    for i, e in enumerate(hist):
        entry_ok(e, f"history[{i}]")
        if set(e) - {"state", "at", "by", "reason"}:
            raise StateError("invalid_project_state", f"history[{i}] has unknown fields")
    for i, (a, b) in enumerate(zip(hist, hist[1:]), start=1):
        if (a["state"], b["state"]) not in TRANSITIONS:
            raise StateError("invalid_project_state", f"history[{i}]: {a['state']} -> {b['state']} is not allowed")
        if b["at"] < a["at"] and b["at"].endswith("Z") and a["at"].endswith("Z"):
            raise StateError("invalid_project_state", f"history[{i}] is older than the entry before it")
        if b["state"] == "active" and not b["by"].startswith("human:"):
            raise StateError("invalid_project_state", f"history[{i}]: resume must be by a human")
    last = hist[-1]
    if any(last[k] != doc[k] for k in ("state", "at", "by", "reason")):
        raise StateError("invalid_project_state", "last history entry does not match the current state")
    gen = doc.get("generation")
    if not isinstance(gen, int) or isinstance(gen, bool) or gen != len(hist):
        raise StateError("invalid_project_state", "generation must equal the number of history entries")
    if doc["state"] in BLOCKED:
        if "snapshot_path" not in doc:
            raise StateError("invalid_project_state", "snapshot_path is required when parked or archived")
        if repo_root is not None:
            safe_snapshot(repo_root, doc["snapshot_path"])
        elif not SAFE_PATH.match(str(doc["snapshot_path"])):
            raise StateError("snapshot_path_invalid", "snapshot_path is not a safe repo-relative path")
    elif doc.get("snapshot_path") is not None and not SAFE_PATH.match(str(doc["snapshot_path"])):
        raise StateError("snapshot_path_invalid", "snapshot_path is not a safe repo-relative path")
    return doc


def gate(repo_root: Path, expect_generation: int | None = None) -> dict:
    """Decide whether new work may start. Never cancels anything."""
    root = Path(repo_root)
    sdir = root / ".workflow"
    path = sdir / "project-state.json"
    try:
        for p in (sdir, path):
            if os.path.lexists(p) and is_link_like(p, os.lstat(p)):
                raise StateError("invalid_project_state", "state file path is a symlink, junction or reparse point")
        if not os.path.lexists(path):
            if expect_generation is not None:
                raise StateError("project_state_changed", "state file disappeared since the gate was read")
            return {"allow": True, "state": "active", "defaulted": True, "generation": 0}
        if not stat.S_ISREG(os.lstat(path).st_mode) or os.path.getsize(path) > MAX_STATE_BYTES:
            raise StateError("invalid_project_state", "state file is not a small regular file")
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise StateError("invalid_project_state", "state file is unreadable") from None
        validate(doc, root)
    except StateError as e:
        return {"allow": False, "code": e.code, "message": str(e)}
    if expect_generation is not None and doc["generation"] != expect_generation:
        return {"allow": False, "code": "project_state_changed", "state": doc["state"],
                "generation": doc["generation"], "message": "project state changed since the gate was read"}
    if doc["state"] in BLOCKED:
        return {"allow": False, "code": "project_parked", "state": doc["state"],
                "generation": doc["generation"], "at": doc["at"], "by": doc["by"], "reason": doc["reason"]}
    return {"allow": True, "state": "active", "defaulted": False, "generation": doc["generation"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo_root")
    ap.add_argument("--expect-generation", type=int)
    a = ap.parse_args(argv)
    out = gate(Path(a.repo_root), a.expect_generation)
    print(json.dumps(out, sort_keys=True))
    return 0 if out["allow"] else 3


if __name__ == "__main__":
    sys.exit(main())
