#!/usr/bin/env python3
"""Phase 1 bee-CI shadow comparison.

Reads bee-CI results (one record per SHA and job, with a state and the
recorded exit code) and GitHub Actions conclusions for the same exact SHA,
then writes a deterministic local report of agreements and disagreements.

Nothing is posted to GitHub in phase 1. Missing data is reported as missing
and is never counted as a pass. The report is pure data (JSON by default,
Markdown optional) and contains no timestamps, so repeated runs over the
same inputs are byte-identical.

Expected bee-CI input::

    {"records": [
        {"sha": "<40 hex>", "job": "unit", "state": "passed", "exit_code": 0}
    ]}

Expected GitHub Actions input::

    {"records": [
        {"sha": "<40 hex>", "job": "unit", "conclusion": "success"}
    ]}

A bare JSON list of the same records is also accepted. SHA matching is exact:
short SHAs and abbreviations are never expanded or prefix-matched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

PASSED = "passed"
FAILED = "failed"
UNKNOWN = "unknown"

_PASS_STATES = frozenset({"passed", "pass", "success", "succeeded", "ok", "green"})
_FAIL_STATES = frozenset(
    {"failed", "fail", "failure", "error", "errored", "timed_out", "timedout", "red"}
)
AGREE_PASSED = "agree-passed"
AGREE_FAILED = "agree-failed"
BEE_PASSED_ACTIONS_FAILED = "bee-passed-actions-failed"
BEE_FAILED_ACTIONS_PASSED = "bee-failed-actions-passed"
MISSING_BEE = "missing-bee"
MISSING_ACTIONS = "missing-actions"
INCONCLUSIVE = "inconclusive"


class CompareError(ValueError):
    """Raised when an input payload cannot be compared safely."""


def load_json(source: str | Path | dict | list) -> Any:
    """Load a fixture or result file, or pass an already-decoded payload."""
    if isinstance(source, (dict, list)):
        return source
    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CompareError(f"cannot read input: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CompareError(f"invalid JSON input: {exc}") from exc


def _records(payload: Any, side: str) -> list[dict]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        if "records" in payload:
            records = payload["records"]
        elif "results" in payload:
            records = payload["results"]
        else:
            raise CompareError(f"{side} payload has no records list")
    else:
        raise CompareError(f"{side} payload must be an object or a list")
    if not isinstance(records, list):
        raise CompareError(f"{side} records must be a list")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise CompareError(f"{side} record {index} must be an object")
    return records


def _text(value: Any, field: str, side: str, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise CompareError(f"{side} record is missing {field}")
        return None
    if not isinstance(value, str) or not value.strip():
        raise CompareError(f"{side} {field} must be a non-empty string")
    return value.strip()


def _exit_code(value: Any, side: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise CompareError(f"{side} exit_code must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value.strip())
    raise CompareError(f"{side} exit_code must be an integer")


def _classify(value: str | None) -> str:
    if not value:
        return UNKNOWN
    token = value.strip().lower()
    if token in _PASS_STATES:
        return PASSED
    if token in _FAIL_STATES:
        return FAILED
    return UNKNOWN


def _bee_row(record: dict) -> dict:
    sha = _text(record.get("sha"), "sha", "bee-ci")
    job = _text(record.get("job"), "job", "bee-ci")
    raw_state = _text(record.get("state"), "state", "bee-ci", required=False)
    exit_code = _exit_code(record.get("exit_code"), "bee-ci")

    state_result = _classify(raw_state)
    exit_result = None
    if exit_code is not None:
        exit_result = PASSED if exit_code == 0 else FAILED

    contradictory = False
    if state_result == UNKNOWN and exit_result is not None:
        result = exit_result
    elif state_result == UNKNOWN:
        result = UNKNOWN
    elif exit_result is None or exit_result == state_result:
        result = state_result
    else:
        result = UNKNOWN
        contradictory = True

    return {
        "sha": sha,
        "job": job,
        "present": True,
        "state": raw_state,
        "exit_code": exit_code,
        "result": result,
        "contradictory": contradictory,
    }


def _actions_row(record: dict) -> dict:
    sha = _text(record.get("sha"), "sha", "github-actions")
    job = _text(record.get("job"), "job", "github-actions")
    raw_conclusion = record.get("conclusion")
    if raw_conclusion is not None and not isinstance(raw_conclusion, str):
        raise CompareError("github-actions conclusion must be a string")
    return {
        "sha": sha,
        "job": job,
        "present": True,
        "conclusion": raw_conclusion,
        "result": _classify(raw_conclusion),
    }


def _index(rows: list[dict], side: str) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["sha"].lower(), row["job"])
        if key in index:
            raise CompareError(
                f"{side} has duplicate records for sha {key[0]} job {key[1]}"
            )
        index[key] = row
    return index


def _row_sort_key(row: dict) -> tuple[str, str]:
    return (row["sha"], row["job"])


def _missing_bee(sha: str, job: str) -> dict:
    return {"sha": sha, "job": job, "present": False, "result": "missing"}


def _missing_actions(sha: str, job: str) -> dict:
    return {"sha": sha, "job": job, "present": False, "result": "missing"}


def compare(bee_payload: Any, actions_payload: Any) -> dict:
    """Compare bee-CI results with GitHub Actions conclusions for exact SHAs."""
    bee_records = _records(bee_payload, "bee-ci")
    actions_records = _records(actions_payload, "github-actions")

    bee_index = _index([_bee_row(record) for record in bee_records], "bee-ci")
    actions_index = _index(
        [_actions_row(record) for record in actions_records], "github-actions"
    )

    keys = sorted(set(bee_index) | set(actions_index))
    rows: list[dict] = []

    for sha, job in keys:
        bee = bee_index.get((sha, job))
        actions = actions_index.get((sha, job))

        if bee is None:
            rows.append(
                {
                    "sha": sha,
                    "job": job,
                    "verdict": "disagree",
                    "kind": MISSING_BEE,
                    "bee": _missing_bee(sha, job),
                    "actions": actions,
                }
            )
            continue
        if actions is None:
            rows.append(
                {
                    "sha": sha,
                    "job": job,
                    "verdict": "disagree",
                    "kind": MISSING_ACTIONS,
                    "bee": bee,
                    "actions": _missing_actions(sha, job),
                }
            )
            continue

        bee_result = bee["result"]
        actions_result = actions["result"]

        if bee_result == PASSED and actions_result == PASSED:
            verdict, kind = "agree", AGREE_PASSED
        elif bee_result == FAILED and actions_result == FAILED:
            verdict, kind = "agree", AGREE_FAILED
        elif bee_result == PASSED and actions_result == FAILED:
            verdict, kind = "disagree", BEE_PASSED_ACTIONS_FAILED
        elif bee_result == FAILED and actions_result == PASSED:
            verdict, kind = "disagree", BEE_FAILED_ACTIONS_PASSED
        else:
            # Unknown on either side (including contradictory bee records).
            # Never collapse this into a pass.
            verdict, kind = "disagree", INCONCLUSIVE

        rows.append(
            {
                "sha": sha,
                "job": job,
                "verdict": verdict,
                "kind": kind,
                "bee": bee,
                "actions": actions,
            }
        )

    rows.sort(key=_row_sort_key)

    agreements = [row for row in rows if row["verdict"] == "agree"]
    disagreements = [row for row in rows if row["verdict"] == "disagree"]
    inconclusive = [row for row in disagreements if row["kind"] == INCONCLUSIVE]

    def count(kind: str) -> int:
        return sum(1 for row in disagreements if row["kind"] == kind)

    summary = {
        "total": len(rows),
        "agreements": len(agreements),
        "disagreements": len(disagreements),
        "inconclusive": len(inconclusive),
        "agree_passed": sum(1 for row in agreements if row["kind"] == AGREE_PASSED),
        "agree_failed": sum(1 for row in agreements if row["kind"] == AGREE_FAILED),
        "bee_passed_actions_failed": count(BEE_PASSED_ACTIONS_FAILED),
        "bee_failed_actions_passed": count(BEE_FAILED_ACTIONS_PASSED),
        "missing_bee": count(MISSING_BEE),
        "missing_actions": count(MISSING_ACTIONS),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "bee-ci-shadow-compare",
        "sides": {"bee": "bee-ci", "actions": "github-actions"},
        "summary": summary,
        "rows": rows,
        "agreements": agreements,
        "disagreements": disagreements,
    }


def _cell(value: Any) -> str:
    text = "missing" if value is None else str(value)
    return text.replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def render_markdown(report: dict) -> str:
    """Render the report as stable Markdown (no timestamps, sorted rows)."""
    summary = report["summary"]
    lines = [
        "# bee-CI shadow comparison",
        "",
        "Phase 1: written locally only; nothing was posted to GitHub.",
        "",
        "Missing data is reported as missing and is never counted as a pass.",
        "",
        "## Summary",
        "",
        "| metric | count |",
        "| --- | ---: |",
    ]
    for key in (
        "total",
        "agreements",
        "agree_passed",
        "agree_failed",
        "disagreements",
        "inconclusive",
        "bee_passed_actions_failed",
        "bee_failed_actions_passed",
        "missing_bee",
        "missing_actions",
    ):
        lines.append(f"| {key} | {summary[key]} |")

    lines.extend(
        [
            "",
            "## Disagreements",
            "",
            "| sha | job | bee | actions | kind |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if report["disagreements"]:
        for row in report["disagreements"]:
            bee = row["bee"]
            actions = row["actions"]
            bee_cell = "missing" if not bee["present"] else _cell(bee["result"])
            actions_cell = (
                "missing" if not actions["present"] else _cell(actions["result"])
            )
            lines.append(
                f"| {_cell(row['sha'])} | {_cell(row['job'])} | "
                f"{bee_cell} | {actions_cell} | {_cell(row['kind'])} |"
            )
    else:
        lines.append("| none | | | | |")

    lines.extend(
        [
            "",
            "## Agreements",
            "",
            "| sha | job | result |",
            "| --- | --- | --- |",
        ]
    )
    if report["agreements"]:
        for row in report["agreements"]:
            lines.append(
                f"| {_cell(row['sha'])} | {_cell(row['job'])} | "
                f"{_cell(row['bee']['result'])} |"
            )
    else:
        lines.append("| none | | |")

    return "\n".join(lines) + "\n"


def _dump(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare bee-CI results with GitHub Actions conclusions (local only)."
    )
    parser.add_argument("--bee", required=True, help="bee-CI results JSON file")
    parser.add_argument(
        "--actions", required=True, help="GitHub Actions conclusions JSON file"
    )
    parser.add_argument("--out", help="write the JSON report here instead of stdout")
    parser.add_argument("--markdown", help="also write a Markdown report here")
    parser.add_argument(
        "--fail-on-disagreement",
        action="store_true",
        help="exit 1 when any disagreement, missing side, or inconclusive row exists",
    )
    args = parser.parse_args(argv)

    report = compare(load_json(args.bee), load_json(args.actions))
    data = _dump(report)

    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(report), encoding="utf-8")

    if args.fail_on_disagreement and report["summary"]["disagreements"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
