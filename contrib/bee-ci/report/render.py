"""Render a bee-CI evidence index as one static, dark-mode HTML page.

Consumes the frozen ``bee-ci/evidence/v1`` document and writes plain HTML with
no JavaScript, no network access and no server.  A missing bee or github side
is shown as ``missing``; it is never treated as a pass.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path

SCHEMA = "bee-ci/evidence/v1"
SOURCES = ("bee", "github")
STATE_CLASSES = {
    "success": "success",
    "failure": "failure",
    "error": "error",
    "pending": "pending",
}
SHORT_SHA_LENGTH = 12

_REDACTIONS = (
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "[redacted-token]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[redacted-token]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), "[redacted-token]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[redacted-token]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[redacted-token]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[redacted-token]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{8,}=*"), "[redacted-token]"),
    (re.compile(r"(?i)\b(?:token|secret|password|passwd|api[_-]?key)\s*[=:]\s*\S+"), "[redacted-secret]"),
    (re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>]+"), "[redacted-url]"),
    (re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b", re.IGNORECASE), "[redacted-host]"),
    (re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:tailnet|internal|local|lan|home\.arpa)\b", re.IGNORECASE), "[redacted-host]"),
    (re.compile(r"\blocalhost\b", re.IGNORECASE), "[redacted-host]"),
    (re.compile(r"(?<![\w:])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"), "[redacted-ip]"),
    (re.compile(r"\[[0-9a-fA-F:]{2,}\](?::\d+)?"), "[redacted-ip]"),
    (re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{1,4}:){1,7}:[0-9a-fA-F]{0,4}(?![\w:])"), "[redacted-ip]"),
)


class EvidenceError(ValueError):
    """Raised when an index document does not match the frozen contract."""


def _redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _safe(value: object) -> str:
    return html.escape(_redact("" if value is None else str(value)), quote=True)


def _load(index_doc: object) -> list:
    if isinstance(index_doc, dict):
        document = index_doc
    elif isinstance(index_doc, (str, bytes, os.PathLike)):
        raw = Path(index_doc).read_text(encoding="utf-8")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EvidenceError("evidence index is not valid JSON") from exc
    else:
        raise TypeError("render() expects an evidence document or a path to one")

    if not isinstance(document, dict):
        raise EvidenceError("evidence index must be a JSON object")
    schema = document.get("schema")
    if schema is not None and schema != SCHEMA:
        raise EvidenceError(f"unsupported evidence schema: {schema!r}")
    runs = document.get("runs")
    if not isinstance(runs, list):
        raise EvidenceError("evidence index must contain a runs list")
    return runs


def _normalise(runs: list) -> list[dict]:
    normalised = []
    for position, item in enumerate(runs):
        if not isinstance(item, dict):
            raise EvidenceError(f"run at position {position} must be an object")
        record = {}
        for field in ("repo", "head_sha", "job", "source", "state"):
            value = item.get(field)
            if not isinstance(value, str) or not value:
                raise EvidenceError(f"run at position {position} has no {field}")
            record[field] = value
        result_path = item.get("result_path")
        record["result_path"] = result_path if isinstance(result_path, str) else ""
        record["_order"] = position
        normalised.append(record)
    normalised.sort(
        key=lambda record: (
            record["repo"],
            record["head_sha"],
            record["job"],
            record["source"],
            record["_order"],
        )
    )
    return normalised


def _state_class(state: str) -> str:
    return STATE_CLASSES.get(state, "unknown")


def _state_html(state: str) -> str:
    css = _state_class(state)
    return f'<span class="state state-{css}">{_safe(state)}</span>'


def _missing_html() -> str:
    return '<span class="state state-missing">missing</span>'


def _run_row(record: dict, disagreeing: set) -> str:
    key = (record["repo"], record["head_sha"], record["job"])
    disagree = " disagree" if key in disagreeing else ""
    css = _state_class(record["state"])
    source_css = record["source"] if record["source"] in SOURCES else "other"
    return (
        f'<tr class="run state-{css}{disagree}" data-result-path="{_safe(record["result_path"])}">'
        f'<td class="repo"><code>{_safe(record["repo"])}</code></td>'
        f'<td class="sha" data-abbrev="{_safe(record["head_sha"][:7])}"><code>{_safe(record["head_sha"][:SHORT_SHA_LENGTH])}</code></td>'
        f'<td class="job">{_safe(record["job"])}</td>'
        f'<td class="source"><span class="source source-{source_css}">{_safe(record["source"])}</span></td>'
        f'<td class="state-cell">{_state_html(record["state"])}</td>'
        "</tr>"
    )


def _group(records: list[dict]) -> dict:
    groups: dict[tuple, dict[str, list[dict]]] = {}
    for record in records:
        key = (record["repo"], record["head_sha"], record["job"])
        groups.setdefault(key, {}).setdefault(record["source"], []).append(record)
    return groups


def _disagreements(groups: dict) -> list[dict]:
    issues = []
    for key in sorted(groups):
        by_source = groups[key]
        states = {
            source: [record["state"] for record in by_source.get(source, [])]
            for source in SOURCES
        }
        missing = [source for source in SOURCES if not states[source]]
        unique = {
            source: sorted(set(states[source]))
            for source in SOURCES
        }
        conflict = False
        reason = ""
        kind = ""
        if missing:
            conflict = True
            kind = "missing-side"
            reason = "missing " + " and ".join(f"{source} evidence" for source in missing)
        elif any(len(unique[source]) > 1 for source in SOURCES):
            conflict = True
            kind = "conflicting-evidence"
            reason = "conflicting evidence for one source"
        elif unique["bee"] != unique["github"]:
            conflict = True
            kind = "state-mismatch"
            reason = "state mismatch"
        if not conflict:
            continue
        issues.append(
            {
                "key": key,
                "missing": missing,
                "unique": unique,
                "states": states,
                "kind": kind,
                "reason": reason,
            }
        )
    return issues


def _side_html(source: str, issue: dict) -> str:
    if source in issue["missing"]:
        state_markup = _missing_html()
    else:
        values = issue["unique"][source]
        state_markup = " / ".join(_state_html(state) for state in values)
    return (
        f'<span class="side side-{source}">'
        f'<span class="side-label">{_safe(source)}</span> {state_markup}'
        "</span>"
    )


def _issue_html(issue: dict) -> str:
    repo, head_sha, job = issue["key"]
    return (
        f'<li class="disagreement" data-kind="{issue["kind"]}" '
        f'data-repo="{_safe(repo)}" data-head-sha="{_safe(head_sha)}" data-job="{_safe(job)}">'
        '<div class="disagreement-head">'
        f'<code class="repo">{_safe(repo)}</code> '
        f'<code class="sha" data-abbrev="{_safe(head_sha[:7])}">{_safe(head_sha[:SHORT_SHA_LENGTH])}</code> '
        f'<code class="job">{_safe(job)}</code>'
        "</div>"
        '<div class="disagreement-body">'
        f'{_side_html("bee", issue)}'
        f'{_side_html("github", issue)}'
        f'<span class="reason">{_safe(issue["reason"])}</span>'
        "</div>"
        "</li>"
    )


def _template(template_path: object | None) -> str:
    path = Path(template_path) if template_path is not None else Path(__file__).with_name("template.html")
    return path.read_text(encoding="utf-8")


def _summary(records: list[dict], issues: list[dict]) -> str:
    missing_sides = sum(len(issue["missing"]) for issue in issues)
    return (
        '<p class="summary">'
        f"Runs: <strong>{len(records)}</strong>"
        '<span class="sep">|</span>'
        f"Disagreements: <strong>{len(issues)}</strong>"
        '<span class="sep">|</span>'
        f"Missing sides: <strong>{missing_sides}</strong>"
        "</p>"
    )


def render(index_doc: object, template_path: object | None = None) -> str:
    records = _normalise(_load(index_doc))
    groups = _group(records)
    issues = _disagreements(groups)
    disagreeing = {issue["key"] for issue in issues}

    if records:
        rows = "\n".join(_run_row(record, disagreeing) for record in records)
    else:
        rows = '<tr class="empty"><td colspan="5">No runs in the evidence index.</td></tr>'

    if issues:
        disagreements = "\n".join(_issue_html(issue) for issue in issues)
    else:
        disagreements = (
            '<p class="empty">No disagreements. A missing side is reported as missing, '
            "never as a pass.</p>"
        )

    page = _template(template_path)
    replacements = {
        "{{SUMMARY}}": _summary(records, issues),
        "{{RUN_ROWS}}": rows,
        "{{DISAGREEMENTS}}": disagreements,
    }
    for marker, value in replacements.items():
        page = page.replace(marker, value)
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", help="path to evidence/index.json")
    parser.add_argument("--out", help="write the page here instead of stdout")
    parser.add_argument("--template", help="override the bundled template")
    args = parser.parse_args(argv)

    page = render(args.index, template_path=args.template)
    if args.out:
        Path(args.out).write_text(page, encoding="utf-8")
        print(args.out)
    else:
        print(page, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
