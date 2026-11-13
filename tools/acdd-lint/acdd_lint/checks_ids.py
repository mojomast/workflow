"""Standalone checks for duplicate acceptance-criteria ids in acdd/1 contracts.

The helpers here work on plain mappings and never import the CLI, so the
coordinator can wire them into the linter later.  Malformed input is silent:
a missing, empty, or non-list ``acceptance_criteria`` yields no problems.
"""

from __future__ import annotations

from typing import Any, Mapping

Problem = dict[str, str]


def _problem(code: str, where: str, message: str) -> Problem:
    return {"code": code, "where": where, "message": message}


def check_duplicate_ac_ids(contract: Mapping[str, Any]) -> list[Problem]:
    """Return one problem for every acceptance-criteria id used more than once."""
    if not isinstance(contract, Mapping):
        return []
    criteria = contract.get("acceptance_criteria")
    if not isinstance(criteria, list):
        return []

    contract_id = contract.get("id")
    where = contract_id if isinstance(contract_id, str) and contract_id else "acceptance_criteria"

    counts: dict[str, int] = {}
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            continue
        ac_id = criterion.get("id")
        if not isinstance(ac_id, str):
            continue
        counts[ac_id] = counts.get(ac_id, 0) + 1

    problems: list[Problem] = []
    for ac_id, count in counts.items():
        if count > 1:
            problems.append(
                _problem(
                    "contract_duplicate_ac",
                    where,
                    f"acceptance criteria id {ac_id!r} appears {count} times; give every criterion a unique id",
                )
            )
    return problems
