"""Consistency checks between an ``acdd/1`` contract and an acceptance report.

A report that matches its contract is a *document* property only: nothing here
asserts authenticated human approval, nor permission to merge, deploy or take
any other gated action.

The functions here work on plain mappings and never raise on malformed input:
a missing report, unexpected value types or unknown status shapes simply yield
no problems.  Problem dictionaries have the same shape as ``contracts.Problem``.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import Problem, contract_sha256


def _problem(where: str, message: str) -> Problem:
    return {"code": "report_mismatch", "where": where, "message": message}


def _contract_ids(contract: Mapping[str, Any]) -> list[str]:
    criteria = contract.get("acceptance_criteria")
    if not isinstance(criteria, list):
        return []
    ids: list[str] = []
    for criterion in criteria:
        if isinstance(criterion, Mapping):
            ac_id = criterion.get("id")
            if isinstance(ac_id, str):
                ids.append(ac_id)
    return ids


def _frozen_sha(contract: Mapping[str, Any]) -> str | None:
    review = contract.get("review")
    if not isinstance(review, Mapping):
        return None
    stored = review.get("contract_sha256")
    if not isinstance(stored, str) or not stored:
        return None
    return contract_sha256(contract)


def check_report_totals(contract: Mapping[str, Any], report: Mapping[str, Any]) -> list[Problem]:
    """Return ``report_mismatch`` problems for one contract/report pair (never raises)."""
    if not isinstance(contract, Mapping) or not isinstance(report, Mapping):
        return []
    criteria = report.get("criteria")
    if not isinstance(criteria, Mapping):
        return []

    problems: list[Problem] = []
    contract_ids = _contract_ids(contract)
    known = set(contract_ids)
    report_ids = [ac_id for ac_id in criteria if isinstance(ac_id, str)]

    for ac_id in contract_ids:
        if ac_id not in criteria:
            problems.append(
                _problem(
                    f"criteria.{ac_id}",
                    f"contract criterion {ac_id!r} is missing from the acceptance report",
                )
            )
    for ac_id in report_ids:
        if ac_id not in known:
            problems.append(
                _problem(
                    f"criteria.{ac_id}",
                    f"acceptance report names criterion {ac_id!r}, which the contract does not define",
                )
            )

    shape_ok = _report_shape_ok(report, criteria)
    frozen = _frozen_sha(contract)
    reported_sha = report.get("contract_sha256")
    # Attribution is only meaningful for a document shaped like a report; a broken
    # object that makes no claim is noise, and the acceptance rule below reports it
    # when it does claim something.
    if frozen is not None and shape_ok:
        if reported_sha is None:
            problems.append(
                _problem(
                    "contract_sha256",
                    "report omits contract_sha256 while the contract is frozen; "
                    "the report cannot be attributed to this contract",
                )
            )
        elif not isinstance(reported_sha, str):
            problems.append(
                _problem(
                    "contract_sha256",
                    "report.contract_sha256 is not a string; the report cannot be attributed",
                )
            )
        elif reported_sha != frozen:
            problems.append(
                _problem(
                    "contract_sha256",
                    "report.contract_sha256 does not match the frozen contract hash",
                )
            )

    if report.get("accepted") is True:
        if shape_ok:
            problems.extend(_acceptance_problems(contract, report, criteria))
        else:
            # An acceptance claim the linter cannot read is not a pass. Say so
            # rather than staying silent: this tool applies no schema to reports.
            problems.append(
                _problem(
                    "accepted",
                    "report claims accepted while its phases or criteria are malformed; "
                    "the linter cannot verify the claim and refuses to treat it as accepted",
                )
            )

    return problems


def _report_shape_ok(report: Mapping[str, Any], criteria: Mapping[str, Any]) -> bool:
    """True when the report is shaped like a report.

    Structurally broken input (non-string statuses, criteria entries that are
    not mappings) is not a document that claims acceptance; it is noise, and the
    tool stays silent on it rather than inventing a verdict.
    """
    phases = report.get("phases")
    if phases is not None:
        if not isinstance(phases, Mapping):
            return False
        if any(not isinstance(name, str) or not isinstance(status, str) for name, status in phases.items()):
            return False
    for ac_id, entry in criteria.items():
        if not isinstance(ac_id, str) or not isinstance(entry, Mapping):
            return False
    return True


def _declared_verification(contract: Mapping[str, Any]) -> dict[str, str | None]:
    """Map each contract criterion id to its declared verification type."""
    declared: dict[str, str | None] = {}
    criteria = contract.get("acceptance_criteria")
    if not isinstance(criteria, list):
        return declared
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            continue
        ac_id = criterion.get("id")
        if isinstance(ac_id, str):
            kind = criterion.get("verification")
            declared[ac_id] = kind if isinstance(kind, str) else None
    return declared


def _acceptance_problems(
    contract: Mapping[str, Any],
    report: Mapping[str, Any],
    criteria: Mapping[str, Any],
) -> list[Problem]:
    """Problems with an ``accepted: true`` verdict.

    A criterion is satisfied when it is ``passed``, or when it is
    ``review_required`` and the review phase is valid and the contract declares
    that criterion's verification as ``review``. That mirrors the versioned
    reference report: review-gated acceptance is a recorded document property,
    never a claim of authenticated human approval or permission to act.
    """
    problems: list[Problem] = []
    phases = report.get("phases") if isinstance(report.get("phases"), Mapping) else {}
    review_valid = phases.get("review") == "valid"
    required = contract.get("evidence_required")
    required_phases = [name for name in required if isinstance(name, str)] if isinstance(required, list) else []
    declared = _declared_verification(contract)

    for name, status in phases.items():
        if isinstance(name, str) and isinstance(status, str) and status != "valid":
            problems.append(
                _problem(
                    f"phases.{name}",
                    f"report is accepted while phase {name!r} is {status!r}, not 'valid'",
                )
            )
    for name in required_phases:
        if name not in phases:
            problems.append(
                _problem(
                    f"phases.{name}",
                    f"report is accepted while the contract's required phase {name!r} is absent",
                )
            )

    for ac_id, entry in criteria.items():
        if not isinstance(ac_id, str) or not isinstance(entry, Mapping):
            continue
        status = entry.get("status")
        if status == "passed":
            continue
        if status == "review_required":
            if not review_valid:
                problems.append(
                    _problem(
                        f"criteria.{ac_id}.status",
                        f"criterion {ac_id!r} is 'review_required' but the review phase is not valid",
                    )
                )
                continue
            if declared.get(ac_id) != "review":
                problems.append(
                    _problem(
                        f"criteria.{ac_id}.status",
                        f"criterion {ac_id!r} is 'review_required' while the contract declares "
                        f"verification {declared.get(ac_id)!r}, not 'review'",
                    )
                )
                continue
            continue
        problems.append(
            _problem(
                f"criteria.{ac_id}.status",
                f"report is accepted while criterion {ac_id!r} is {status!r}, "
                "which does not support acceptance",
            )
        )

    return problems
