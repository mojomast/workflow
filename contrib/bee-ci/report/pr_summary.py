"""Render one compact, deterministic Markdown summary for a pull request.

Evidence text is untrusted: every interpolated string is redacted and escaped
before it reaches the page, and missing or unreadable records are reported as
an explicit ``GAP`` instead of being silently treated as a pass.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

PHASES = ("red", "green", "refactor", "integration", "review")
REQUIRED_PHASES = ("red", "green")
SHORT_REVISION_LENGTH = 10
MAX_TEXT_LENGTH = 300

_EVIDENCE_TABLE = (
    "| Phase | Result / classification | Revision | Note |\n"
    "| --- | --- | --- | --- |"
)

_REDACTIONS = (
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}"), "[redacted]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "[redacted]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "[redacted]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*"), "[redacted]"),
    (re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b", re.IGNORECASE), "[redacted]"),
    (
        re.compile(
            r"(?<![\w.])("
            r"10\.(?:\d{1,3}\.){2}\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3}"
            r"|192\.168\.(?:\d{1,3}\.)\d{1,3}"
            r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.(?:\d{1,3}\.)\d{1,3}"
            r")(?![\w.])"
        ),
        "[redacted]",
    ),
)


def _redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _safe(value: object) -> str:
    """Redact then escape one untrusted value for a Markdown table."""
    text = "" if value is None else str(value)
    text = _redact(text)
    text = re.sub(r"\s*[\r\n]+\s*", " ", text)
    text = text[:MAX_TEXT_LENGTH]
    return html.escape(text, quote=False).replace("|", r"\|")


def _read_json(path: Path) -> dict | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def _contract_path(evidence_dir: Path) -> Path | None:
    try:
        candidates = sorted(evidence_dir.glob("*.contract.json"))
    except OSError:
        return None
    return candidates[0] if candidates else None


def _contract_id(contract: dict, path: Path) -> str:
    value = contract.get("id")
    if isinstance(value, str) and value and Path(value).name == value and value not in (".", ".."):
        return value
    return path.name[: -len(".contract.json")]


def _criterion_text(criterion: dict) -> str:
    statement = criterion.get("statement")
    if isinstance(statement, str) and statement:
        return _safe(statement)
    parts = []
    for label, key in (("Given", "given"), ("when", "when"), ("then", "then")):
        value = criterion.get(key)
        if isinstance(value, str) and value:
            parts.append(f"{label} {_safe(value)}")
    return ", ".join(parts) if parts else ""


def _result_cell(record: dict) -> str:
    parts = []
    classification = record.get("classification")
    if isinstance(classification, str) and classification:
        parts.append(_safe(classification))
    result = record.get("result")
    if isinstance(result, str) and result:
        if _safe(result) not in parts:
            parts.append(_safe(result))
    elif isinstance(result, dict):
        exit_code = result.get("exit_code")
        if not parts and isinstance(exit_code, int) and not isinstance(exit_code, bool):
            parts.append(_safe(f"exit {exit_code}"))
    return " / ".join(parts) if parts else "unknown"


def _short_revision(record: dict) -> str:
    revision = record.get("revision")
    if not isinstance(revision, str):
        return _safe(revision)
    return _safe(revision[:SHORT_REVISION_LENGTH])


def _evidence_rows(
    evidence_dir: Path, contract_id: str
) -> tuple[list[str], list[str]]:
    rows: list[str] = []
    gaps: list[str] = []
    any_present = False
    for phase in PHASES:
        path = evidence_dir / f"{contract_id}.{phase}.json"
        if not path.exists():
            if phase in REQUIRED_PHASES:
                gaps.append(f"GAP: no readable {phase} evidence.")
            continue
        any_present = True
        record = _read_json(path)
        if record is None:
            gaps.append(f"GAP: {phase} evidence is unreadable.")
            continue
        note = record.get("notes")
        rows.append(
            f"| {phase} | {_result_cell(record)} | {_short_revision(record)} | "
            f"{_safe(note)} |"
        )
    if not any_present:
        gaps.append("GAP: no evidence records found.")
    return rows, gaps


def _criteria_section(contract: dict | None) -> list[str]:
    lines = ["## Acceptance criteria", "", "| ID | Criterion |", "| --- | --- |"]
    criteria = contract.get("acceptance_criteria") if contract else None
    if isinstance(criteria, list):
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            lines.append(
                f"| {_safe(criterion.get('id'))} | {_criterion_text(criterion)} |"
            )
    return lines


def _risk_section(risk: object) -> list[str]:
    lines = ["## Risk", ""]
    if not isinstance(risk, dict):
        lines.append(f"- {_safe(risk)}")
        return lines
    if "tier" in risk:
        lines.append(f"- Tier: {_safe(risk.get('tier'))}")
    reasons = risk.get("reasons")
    if isinstance(reasons, list) and reasons:
        lines.append("- Reasons:")
        for reason in reasons:
            lines.append(f"  - {_safe(reason)}")
    return lines


def _slop_section(slop: object) -> list[str]:
    lines = ["## Slop", ""]
    if not isinstance(slop, dict):
        lines.append(f"- {_safe(slop)}")
        return lines
    if "new" in slop:
        lines.append(f"- New: {_safe(slop.get('new'))}")
    if "fixed" in slop:
        lines.append(f"- Fixed: {_safe(slop.get('fixed'))}")
    return lines


def _metrics_section(metrics: object) -> list[str]:
    lines = ["## Rework metrics", ""]
    if not isinstance(metrics, dict):
        lines.append(f"- {_safe(metrics)}")
        return lines
    for key in sorted(metrics, key=lambda item: str(item)):
        lines.append(f"- {_safe(key)}: {_safe(metrics[key])}")
    return lines


def render_pr_summary(
    evidence_dir: object,
    *,
    risk: object = None,
    slop: object = None,
    metrics: object = None,
) -> str:
    """Render a compact Markdown PR summary for one evidence directory."""
    directory = Path(evidence_dir)
    contract: dict | None = None
    contract_id = ""
    path = _contract_path(directory)
    if path is not None:
        contract = _read_json(path)
        if contract is not None:
            contract_id = _contract_id(contract, path)

    title = contract.get("title") if contract else None
    lines = [f"# {_safe(title)}" if title else "# PR summary", ""]

    lines.extend(_criteria_section(contract))
    lines.append("")

    if contract is None:
        rows, gaps = [], ["GAP: no readable contract found."]
    else:
        rows, gaps = _evidence_rows(directory, contract_id)
    lines.extend(["## Evidence", "", _EVIDENCE_TABLE])
    lines.extend(rows)
    lines.append("")
    for gap in gaps:
        lines.append(gap)
    if gaps:
        lines.append("")

    if risk is not None:
        lines.extend(_risk_section(risk))
        lines.append("")
    if slop is not None:
        lines.extend(_slop_section(slop))
        lines.append("")
    if metrics is not None:
        lines.extend(_metrics_section(metrics))
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"
