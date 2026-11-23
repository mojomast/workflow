"""Filesystem walk and deterministic rules for recurring review lessons."""

from __future__ import annotations

import json
import os
import re
from collections import namedtuple
from pathlib import Path
from typing import Iterable

Finding = namedtuple("Finding", "path rule message")

SKIP_DIRS = frozenset({"node_modules", "__pycache__", "venv", ".venv"})
JSON_SUFFIX = ".json"
CONTRACT_SUFFIX = ".contract.json"
EVIDENCE_DIR = "evidence"
BRIEFS_DIR = "briefs"

HOME_MARKER = "/" + "home" + "/"
WORKSPACE_MARKER = "/" + "workspace" + "/"
DRIVE_PATH = re.compile(r"[A-Za-z]:\\")


def check(paths: Iterable) -> list[Finding]:
    """Walk *paths* and return findings for every supported JSON record.

    Directories are walked without following symlinks and with dot
    directories, ``node_modules``, ``__pycache__`` and virtualenvs skipped.
    Files that cannot be read or parsed as JSON are ignored, never fatal.
    """
    findings: list[Finding] = []
    for path in _collect(paths):
        data = _load_json(path)
        if data is _UNREADABLE:
            continue
        shown = _relative(path)
        findings.extend(_contract_findings(shown, path, data))
        findings.extend(_evidence_findings(shown, path, data))
        findings.extend(_brief_findings(shown, path, data))
    findings.sort(key=lambda finding: (finding.path, finding.rule, finding.message))
    return findings


def _walk(root: Path):
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".")
            and name not in SKIP_DIRS
            and not os.path.islink(os.path.join(directory, name))
        )
        for name in sorted(filenames):
            if name.endswith(JSON_SUFFIX):
                yield Path(directory) / name


def _collect(paths: Iterable) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for item in paths:
        root = Path(item)
        if root.is_dir():
            candidates = _walk(root)
        elif root.is_file():
            candidates = [root]
        else:
            continue
        for candidate in candidates:
            if not candidate.is_file():
                continue
            key = os.path.normcase(os.path.abspath(os.fspath(candidate)))
            if key in seen:
                continue
            seen.add(key)
            found.append(candidate)
    found.sort(key=_relative)
    return found


def _relative(path: Path) -> str:
    try:
        text = os.path.relpath(os.fspath(path), os.fspath(Path.cwd()))
    except ValueError:
        text = os.fspath(path)
    return text.replace(os.sep, "/")


class _Unreadable:
    """Sentinel for a file that is missing, unreadable or not JSON."""


_UNREADABLE = _Unreadable()


def _load_json(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _UNREADABLE
    try:
        return json.loads(text)
    except ValueError:
        return _UNREADABLE


def _under(path: Path, name: str) -> bool:
    return name in path.parts[:-1]


def _has_contract_suffix(path: Path) -> bool:
    return path.name.endswith(CONTRACT_SUFFIX)


def _contract_findings(shown: str, path: Path, data) -> list[Finding]:
    if not _has_contract_suffix(path) or not isinstance(data, dict):
        return []
    criteria = data.get("acceptance_criteria")
    if not isinstance(criteria, list):
        return []
    findings: list[Finding] = []
    for entry in criteria:
        if not isinstance(entry, dict):
            continue
        tests = entry.get("tests")
        if not isinstance(tests, list):
            continue
        for reference in tests:
            if not isinstance(reference, str) or "::" in reference:
                continue
            findings.append(
                Finding(
                    shown,
                    "contract-test-ref",
                    f"test reference {reference} is not a class-qualified file::Class::test id",
                )
            )
    return findings


def _evidence_findings(shown: str, path: Path, data) -> list[Finding]:
    if not _under(path, EVIDENCE_DIR) or not _contains_absolute_path(data):
        return []
    return [
        Finding(
            shown,
            "evidence-absolute-path",
            "evidence record contains an absolute local path; scrub it before signing",
        )
    ]


def _brief_findings(shown: str, path: Path, data) -> list[Finding]:
    if not _under(path, BRIEFS_DIR) or not isinstance(data, dict):
        return []
    objective = data.get("objective")
    if not isinstance(objective, str) or "may create" not in objective.lower():
        return []
    return [
        Finding(
            shown,
            "brief-may-create",
            "brief tells the bee it may create a file outside its assigned scope",
        )
    ]


def _contains_absolute_path(value) -> bool:
    if isinstance(value, str):
        return (
            HOME_MARKER in value
            or WORKSPACE_MARKER in value
            or DRIVE_PATH.search(value) is not None
        )
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    return False
