"""Revision-drift checks for ``tdd-evidence/1`` records.

A record may legitimately be produced on a newer revision (``revision``) while
its work still descends from the contract's pinned ``source_rev``.  The base
revision is therefore what must match the contract; the record revision is only
a fallback for old records that predate ``base_rev``.
"""

from __future__ import annotations

from typing import Any, Mapping

Problem = dict[str, str]


def _problem(code: str, where: str, message: str) -> Problem:
    return {"code": code, "where": where, "message": message}


def _base_revision(record: Mapping[str, Any]) -> str:
    base = record.get("base_rev")
    if isinstance(base, str) and base:
        return base
    revision = record.get("revision")
    if isinstance(revision, str) and revision:
        return revision
    return ""


def check_revision_drift(
    contract: Mapping[str, Any],
    records: list[tuple[str, Mapping[str, Any]]],
) -> list[Problem]:
    """Return a problem for each record whose base revision is not pinned."""
    if not isinstance(contract, Mapping):
        return []
    source_rev = contract.get("source_rev")
    if not isinstance(source_rev, str) or not source_rev:
        return []

    problems: list[Problem] = []
    for filename, record in records:
        if not isinstance(record, Mapping):
            continue
        base_rev = _base_revision(record)
        if not base_rev or base_rev == source_rev:
            continue
        problems.append(
            _problem(
                "evidence_revision_mismatch",
                filename,
                f"record base revision {base_rev[:12]!r} does not match contract source_rev {source_rev[:12]!r}; rebase onto the pinned revision",
            )
        )
    return problems
