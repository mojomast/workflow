"""Semantic validation for rizzstack.campaign-report/1.

A campaign report is the closeout record for one automated-development
campaign. It exists because a finished task graph is not product acceptance:
the report keeps task implementation, integrated behavior and independent
acceptance separate, and it refuses a receiver decision written by an agent.

The JSON Schema lives at schemas/campaign-report.schema.json. This module adds
the checks a schema cannot express safely: task arithmetic, final-head test
results, PASS-with-evidence, reasons for unrun checks, merge-order references,
traceable audit-finding dispositions and the always-pending receiver decision.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE / "schemas" / "campaign-report.schema.json"

SCHEMA = "rizzstack.campaign-report/1"
DELIVERY_STATES = {"ready_for_review", "incomplete", "blocked"}
ACCEPTANCE_KINDS = {"test", "integration", "visual", "performance", "asset", "manual"}
ACCEPTANCE_STATUSES = {"PASS", "FAIL", "NOT RUN", "BLOCKED", "UNVERIFIED"}
PR_STATES = {"open", "merged", "closed"}
REVISION_BOUND_KINDS = {"test", "integration", "visual", "performance", "asset"}
AUDIT_DISPOSITIONS = {"fixed", "rejected", "deferred"}
AUDIT_LEGACY_FIELDS = ("fixed", "rejected", "deferred")

REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
AUDIT_ID_RE = re.compile(r"^AF-[0-9]{1,}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
AC_RE = re.compile(r"^AC-[0-9]{1,}$")
TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
EVIDENCE_URL_RE = re.compile(r"^https://\S+$")
EVIDENCE_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+$")
EVIDENCE_PLACEHOLDER_RE = re.compile(
    r"^(?:todo|tbd|n/?a|unknown|pending|see(?:\s+.*)?|placeholder)$",
    re.IGNORECASE,
)

# Values that must never be copied into a public campaign report. Evidence
# references should be repository-relative paths, public URLs or redacted
# identifiers, never credential material or a private host layout.
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}\b"),
    re.compile(r"(?:^|[\s\"'=(])/(?:home|Users)/[^/\s]+"),
    re.compile(r"(?:^|[\s\"'=(])/(?:root|tmp|var|etc|opt|mnt|srv|usr|private|workspace)/[^/\s]+"),
    re.compile(r"(?:^|[\s\"'=(])[A-Za-z]:\\Users\\[^\\\s]+"),
    re.compile(r"(?:^|[\s/])(?:\.ssh|\.aws|\.gnupg)(?:/|\b)"),
)


class CampaignReportError(Exception):
    """A campaign report refused by one named rule."""

    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix

    def as_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message, "fix": self.fix}


def _fail(code: str, message: str, fix: str = "") -> "None":
    raise CampaignReportError(code, message, fix)


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("campaign_invalid", f"{field} must be an object")
    return value


def _list(value: Any, field: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        _fail("campaign_invalid", f"{field} must be a list")
    if nonempty and not value:
        _fail("campaign_invalid", f"{field} must not be empty")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("campaign_invalid", f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("campaign_invalid", f"{field} must be a non-negative integer")
    return value


def _revision(value: Any, field: str) -> str:
    text = _text(value, field).lower()
    if not REVISION_RE.fullmatch(text):
        _fail("campaign_revision", f"{field} must be a full 40-hex commit or 64-hex sha256")
    return text


def _time(value: Any, field: str) -> str:
    text = _text(value, field)
    if not TIME_RE.fullmatch(text):
        _fail("campaign_invalid", f"{field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail("campaign_invalid", f"{field} must be a real RFC 3339 timestamp")
        return text
    if parsed.tzinfo is None:
        _fail("campaign_invalid", f"{field} must include a timezone")
    return text


def _evidence_ref(value: Any, field: str) -> str:
    text = _text(value, field)
    if EVIDENCE_PLACEHOLDER_RE.fullmatch(text):
        _fail(
            "campaign_evidence",
            f"{field} is a placeholder, not evidence",
            "Name a repository-relative artifact path or a public https URL.",
        )
    if EVIDENCE_URL_RE.fullmatch(text):
        parsed = urlsplit(text)
        if parsed.username is not None or parsed.password is not None:
            _fail(
                "campaign_secret",
                f"{field} embeds credentials in the URL",
                "Use a public URL without userinfo, or a repository-relative path.",
            )
        return text
    if not EVIDENCE_PATH_RE.fullmatch(text):
        _fail(
            "campaign_evidence",
            f"{field} must be a repository-relative path or a public https URL",
            "Use evidence/<file> or https://... rather than a bare label.",
        )
    parts = [part for part in text.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        _fail(
            "campaign_evidence",
            f"{field} must not escape the repository",
            "Use a repository-relative path without . or .. segments.",
        )
    if any(EVIDENCE_PLACEHOLDER_RE.fullmatch(part) for part in parts):
        _fail(
            "campaign_evidence",
            f"{field} contains a placeholder path segment",
            "Name the actual evidence artifact.",
        )
    return text


def _secret_check(value: Any, path: str = "report") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _secret_check(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _secret_check(item, f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            _fail(
                "campaign_secret",
                f"{path} contains credential material or a private host path",
                "Use [REDACTED], a repository-relative path or a public URL.",
            )


def _acceptance(
    entry: Any,
    index: int,
    *,
    delivery_state: str,
    head_rev: str,
) -> dict[str, Any]:
    item = _object(entry, f"acceptance[{index}]")
    criterion_id = _text(item.get("id"), f"acceptance[{index}].id")
    if not AC_RE.fullmatch(criterion_id):
        _fail("campaign_acceptance_id", f"acceptance[{index}].id must look like AC-001")
    statement = _text(item.get("statement"), f"acceptance[{index}].statement")
    kind = _text(item.get("kind"), f"acceptance[{index}].kind")
    if kind not in ACCEPTANCE_KINDS:
        _fail("campaign_acceptance_kind", f"acceptance[{index}].kind is not a supported kind")
    status = _text(item.get("status"), f"acceptance[{index}].status")
    if status not in ACCEPTANCE_STATUSES:
        _fail("campaign_acceptance_status", f"acceptance[{index}].status is not supported")
    evidence = _list(item.get("evidence"), f"acceptance[{index}].evidence")
    evidence = [
        _evidence_ref(value, f"acceptance[{index}].evidence[{position}]")
        for position, value in enumerate(evidence)
    ]
    reason = _optional_text(item.get("reason"), f"acceptance[{index}].reason")
    command = _optional_text(item.get("command"), f"acceptance[{index}].command")
    head_sha = item.get("head_sha")
    if head_sha is not None:
        head_sha = _revision(head_sha, f"acceptance[{index}].head_sha")

    if status == "PASS" and kind == "visual":
        if not any(
            re.search(r"\.(?:png|jpe?g|webp|gif|mp4|webm)(?:[?#].*)?$", ref, re.IGNORECASE)
            for ref in evidence
        ):
            _fail(
                "campaign_evidence_kind",
                f"{criterion_id} is a visual PASS but cites no image or recording",
                "Attach a screenshot or recording path/URL, with viewport and head in the report.",
            )
    if status == "PASS" and not evidence:
        _fail(
            "campaign_acceptance_pass_without_evidence",
            f"{criterion_id} is PASS but has no evidence",
            "Attach the command output, screenshot, test id or other observable result.",
        )
    if status in {"NOT RUN", "BLOCKED", "UNVERIFIED"} and not reason:
        _fail(
            "campaign_acceptance_reason",
            f"{criterion_id} is {status} but has no reason",
            "State why the check did not run or could not be verified.",
        )
    if kind == "test" and status == "PASS" and not command:
        _fail(
            "campaign_acceptance_command",
            f"{criterion_id} is a passing test but names no command",
            "Record the exact command that produced the result.",
        )
    if delivery_state == "ready_for_review" and status == "PASS" and kind in REVISION_BOUND_KINDS:
        if not head_sha:
            _fail(
                "campaign_acceptance_head",
                f"{criterion_id} is a passing {kind} criterion but names no head",
                "Record the exact final head the evidence was observed at.",
            )
        if head_sha != head_rev:
            _fail(
                "campaign_acceptance_revision",
                f"{criterion_id} was observed at {head_sha}, not the reported final head {head_rev}",
                "Re-run the check on the final head or report the campaign as incomplete.",
            )
    if delivery_state == "ready_for_review" and status in {"FAIL", "BLOCKED", "UNVERIFIED"}:
        _fail(
            "campaign_ready_with_blocker",
            f"{criterion_id} is {status}; the campaign cannot be ready_for_review",
            "Resolve the criterion or change delivery_state to incomplete/blocked.",
        )

    return {
        "id": criterion_id,
        "statement": statement,
        "kind": kind,
        "status": status,
        "evidence": evidence,
        "reason": reason,
        "command": command,
        "head_sha": head_sha,
    }


def _pull_request(entry: Any, index: int) -> dict[str, Any]:
    item = _object(entry, f"pull_requests[{index}]")
    number = _integer(item.get("number"), f"pull_requests[{index}].number")
    if number < 1:
        _fail("campaign_pr_number", f"pull_requests[{index}].number must be positive")
    url = _text(item.get("url"), f"pull_requests[{index}].url")
    if not url.startswith("https://"):
        _fail("campaign_pr_url", f"pull_requests[{index}].url must be https")
    draft = item.get("draft")
    if not isinstance(draft, bool):
        _fail("campaign_pr_draft", f"pull_requests[{index}].draft must be boolean")
    state = _text(item.get("state"), f"pull_requests[{index}].state")
    if state not in PR_STATES:
        _fail("campaign_pr_state", f"pull_requests[{index}].state is not supported")
    base = _text(item.get("base"), f"pull_requests[{index}].base")
    head_sha = _revision(item.get("head_sha"), f"pull_requests[{index}].head_sha")
    merge_order = item.get("merge_order")
    if merge_order is not None:
        merge_order = _integer(merge_order, f"pull_requests[{index}].merge_order")
        if merge_order < 1:
            _fail("campaign_pr_merge_order", f"pull_requests[{index}].merge_order must be positive")
    return {
        "number": number,
        "url": url,
        "draft": draft,
        "state": state,
        "base": base,
        "head_sha": head_sha,
        "merge_order": merge_order,
    }


def _test_run(entry: Any, index: int) -> dict[str, Any]:
    item = _object(entry, f"test_runs[{index}]")
    command = _text(item.get("command"), f"test_runs[{index}].command")
    head_sha = _revision(item.get("head_sha"), f"test_runs[{index}].head_sha")
    passed = _integer(item.get("passed"), f"test_runs[{index}].passed")
    failed = _integer(item.get("failed"), f"test_runs[{index}].failed")
    skipped = _integer(item.get("skipped"), f"test_runs[{index}].skipped")
    if passed + failed + skipped == 0:
        _fail(
            "campaign_test_runs",
            f"test_runs[{index}] recorded zero tests",
            "Record a run that actually executed the suite, or mark it NOT RUN with a reason.",
        )
    ran_at = _time(item.get("ran_at"), f"test_runs[{index}].ran_at")
    note = _optional_text(item.get("note"), f"test_runs[{index}].note")
    return {
        "command": command,
        "head_sha": head_sha,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "ran_at": ran_at,
        "note": note,
    }


def _audit_finding(entry: Any, index: int, audit_index: int) -> dict[str, Any]:
    field = f"audits[{audit_index}].findings[{index}]"
    item = _object(entry, field)
    raw_id = str(item.get("id") or "").strip()
    if not raw_id:
        _fail(
            "campaign_audit_id",
            f"{field}.id must look like AF-001",
            "Give each audit finding a stable id that does not change between reports.",
        )
    finding_id = raw_id
    if not AUDIT_ID_RE.fullmatch(finding_id):
        _fail(
            "campaign_audit_id",
            f"{field}.id must look like AF-001",
            "Give each audit finding a stable id that does not change between reports.",
        )
    summary = _text(item.get("summary"), f"{field}.summary")
    disposition = str(item.get("disposition") or "").strip()
    if disposition not in AUDIT_DISPOSITIONS:
        _fail(
            "campaign_audit_disposition",
            f"{field}.disposition must be fixed, rejected or deferred",
            "Use one disposition per finding; do not put the same finding in multiple buckets.",
        )
    reason = _optional_text(item.get("reason"), f"{field}.reason")
    if disposition in {"rejected", "deferred"} and not reason:
        _fail(
            "campaign_audit_reason",
            f"{field} is {disposition} but has no reason",
            "Explain why the finding was rejected or deferred.",
        )
    evidence = item.get("evidence")
    if evidence is not None:
        evidence = _evidence_ref(evidence, f"{field}.evidence")
    result = {
        "id": finding_id,
        "summary": summary,
        "disposition": disposition,
    }
    if reason:
        result["reason"] = reason
    if evidence is not None:
        result["evidence"] = evidence
    return result


def _audit(entry: Any, index: int) -> dict[str, Any]:
    item = _object(entry, f"audits[{index}]")
    legacy = [field for field in AUDIT_LEGACY_FIELDS if field in item]
    if legacy:
        _fail(
            "campaign_audit_legacy",
            f"audits[{index}] uses untraceable disposition array(s): {', '.join(legacy)}",
            "Replace fixed/rejected/deferred arrays with findings[] objects, each with an id, one disposition and a reason where required.",
        )
    source = _text(item.get("source"), f"audits[{index}].source")
    head_sha = item.get("head_sha")
    if head_sha is not None:
        head_sha = _revision(head_sha, f"audits[{index}].head_sha")
    raw_findings = _list(item.get("findings"), f"audits[{index}].findings", nonempty=True)
    findings = [
        _audit_finding(finding, position, index)
        for position, finding in enumerate(raw_findings)
    ]
    return {"source": source, "head_sha": head_sha, "findings": findings}


def validate(report: Any) -> dict[str, Any]:
    """Validate one campaign report and return a detached normal form."""

    root = _object(report, "report")
    _secret_check(root)
    if root.get("schema") != SCHEMA:
        _fail("campaign_schema", f"schema must be {SCHEMA}")

    campaign_id = _text(root.get("campaign_id"), "campaign_id")
    if not ID_RE.fullmatch(campaign_id):
        _fail("campaign_id", "campaign_id must be a safe identifier")
    repository = _text(root.get("repository"), "repository")
    if not REPO_RE.fullmatch(repository):
        _fail("campaign_repository", "repository must be owner/name")
    branch = _text(root.get("branch"), "branch")
    base_rev = _revision(root.get("base_rev"), "base_rev")
    head_rev = _revision(root.get("head_rev"), "head_rev")
    generated_at = _time(root.get("generated_at"), "generated_at")
    delivery_state = _text(root.get("delivery_state"), "delivery_state")
    if delivery_state not in DELIVERY_STATES:
        _fail("campaign_delivery_state", "delivery_state is not supported")
    if delivery_state == "ready_for_review" and base_rev == head_rev:
        _fail(
            "campaign_revision",
            "base_rev and head_rev are identical; a ready campaign must name a changed head",
            "Record the actual reviewed head.",
        )
    receiver_decision = root.get("receiver_decision")
    if receiver_decision is None:
        _fail(
            "campaign_receiver_decision",
            "receiver_decision is missing; the receiver decision must remain pending",
        )
    if receiver_decision != "pending":
        _fail(
            "campaign_receiver_decision",
            "receiver_decision must remain pending; an agent cannot accept its own campaign",
        )

    graph = _object(root.get("task_graph"), "task_graph")
    total = _integer(graph.get("total"), "task_graph.total")
    implemented = _integer(graph.get("implemented"), "task_graph.implemented")
    integrated = _integer(graph.get("integrated"), "task_graph.integrated")
    accepted = _integer(graph.get("accepted"), "task_graph.accepted")
    remaining = _integer(graph.get("remaining"), "task_graph.remaining")
    if implemented > total or integrated > implemented or accepted > integrated:
        _fail(
            "campaign_task_graph",
            "task_graph counts must satisfy total >= implemented >= integrated >= accepted",
        )
    if remaining != total - implemented:
        _fail(
            "campaign_task_graph",
            "task_graph.remaining must equal total minus implemented",
        )
    graph_note = _optional_text(graph.get("note"), "task_graph.note")

    pull_requests = [_pull_request(entry, index) for index, entry in enumerate(
        _list(root.get("pull_requests"), "pull_requests")
    )]
    numbers = [item["number"] for item in pull_requests]
    if len(set(numbers)) != len(numbers):
        _fail("campaign_pr_duplicate", "pull_requests contains a duplicate PR number")
    urls = [item["url"] for item in pull_requests]
    if len(set(urls)) != len(urls):
        _fail("campaign_pr_duplicate", "pull_requests contains a duplicate PR URL")

    acceptance_raw = _list(root.get("acceptance"), "acceptance", nonempty=True)
    acceptance = [
        _acceptance(entry, index, delivery_state=delivery_state, head_rev=head_rev)
        for index, entry in enumerate(acceptance_raw)
    ]
    ids = [item["id"] for item in acceptance]
    if len(set(ids)) != len(ids):
        _fail("campaign_acceptance_duplicate", "acceptance contains a duplicate criterion id")
    if delivery_state == "ready_for_review" and not any(
        item["status"] == "PASS" for item in acceptance
    ):
        _fail(
            "campaign_ready_without_pass",
            "a ready campaign has no passing acceptance criterion",
            "Record at least one verified product criterion, or report the campaign as incomplete.",
        )

    test_runs = [_test_run(entry, index) for index, entry in enumerate(
        _list(root.get("test_runs"), "test_runs")
    )]
    if delivery_state == "ready_for_review":
        if not test_runs:
            _fail("campaign_test_runs", "a ready campaign needs at least one recorded test run")
        if any(run["failed"] for run in test_runs):
            _fail("campaign_test_failed", "a ready campaign cannot have a failed test run")
        stale = [run["head_sha"] for run in test_runs if run["head_sha"] != head_rev]
        if stale:
            _fail(
                "campaign_test_head",
                f"test run(s) were recorded at {', '.join(sorted(set(stale)))}, not the final head {head_rev}",
                "Re-run the final checks on the reported head or report the campaign as incomplete.",
            )

    raw_audits = root.get("audits")
    audits = [] if raw_audits is None else [_audit(entry, index) for index, entry in enumerate(
        _list(raw_audits, "audits")
    )]
    audit_ids = [finding["id"] for audit in audits for finding in audit["findings"]]
    if len(set(audit_ids)) != len(audit_ids):
        _fail(
            "campaign_audit_duplicate",
            "audit finding ids must be unique across the report",
            "Give every finding a stable id and keep its one disposition in one place.",
        )
    if delivery_state == "ready_for_review":
        for index, audit in enumerate(audits):
            if not audit["head_sha"]:
                _fail(
                    "campaign_audit_head",
                    f"audits[{index}] has no head_sha",
                    "Record the exact head the audit reviewed, or mark the campaign incomplete.",
                )
            if audit["head_sha"] != head_rev:
                _fail(
                    "campaign_audit_head",
                    f"audits[{index}] reviewed {audit['head_sha']}, not the final head {head_rev}",
                    "Re-run the audit on the final head or report the campaign as incomplete.",
                )

    not_run = []
    for index, entry in enumerate(_list(root.get("not_run"), "not_run")):
        item = _object(entry, f"not_run[{index}]")
        not_run.append({
            "check": _text(item.get("check"), f"not_run[{index}].check"),
            "reason": _text(item.get("reason"), f"not_run[{index}].reason"),
        })

    known_limits = [
        _text(value, "known_limits")
        for value in _list(root.get("known_limits"), "known_limits")
    ]
    if delivery_state == "ready_for_review" and (not_run or any(
        item["status"] == "NOT RUN" for item in acceptance
    )) and not known_limits:
        _fail(
            "campaign_limits_required",
            "a ready campaign with unrun checks must record known_limits",
        )

    merge_order = [
        _integer(value, "recommended_merge_order")
        for value in _list(root.get("recommended_merge_order"), "recommended_merge_order")
    ]
    if len(set(merge_order)) != len(merge_order):
        _fail("campaign_merge_order_duplicate", "recommended_merge_order repeats a number")
    pr_orders = [item["merge_order"] for item in pull_requests if item["merge_order"] is not None]
    if len(set(pr_orders)) != len(pr_orders):
        _fail("campaign_merge_order_duplicate", "pull_requests repeats a merge_order")
    if pr_orders and set(pr_orders) != set(merge_order):
        _fail(
            "campaign_merge_order",
            "pull_requests[].merge_order and recommended_merge_order disagree",
            "Use one merge-order source and make every open PR appear exactly once.",
        )
    open_numbers = {item["number"] for item in pull_requests if item["state"] == "open"}
    unknown = [number for number in merge_order if number not in open_numbers]
    if unknown:
        _fail(
            "campaign_merge_order",
            f"recommended_merge_order names PRs that are not open: {unknown}",
        )

    artifacts = root.get("artifacts")
    if artifacts is not None:
        artifacts = dict(_object(artifacts, "artifacts"))
        for field in ("screenshots", "assets"):
            if field in artifacts:
                artifacts[field] = [
                    _evidence_ref(value, f"artifacts.{field}")
                    for value in _list(artifacts[field], f"artifacts.{field}")
                ]
        if "performance" in artifacts:
            rows = []
            for index, entry in enumerate(_list(artifacts["performance"], "artifacts.performance")):
                item = _object(entry, f"artifacts.performance[{index}]")
                row = {
                    "metric": _text(item.get("metric"), f"artifacts.performance[{index}].metric"),
                    "value": item.get("value"),
                    "unit": _text(item.get("unit"), f"artifacts.performance[{index}].unit"),
                }
                if not isinstance(row["value"], (int, float)) or isinstance(row["value"], bool):
                    _fail("campaign_metric", f"artifacts.performance[{index}].value must be numeric")
                if item.get("budget") is not None:
                    budget = item["budget"]
                    if not isinstance(budget, (int, float)) or isinstance(budget, bool):
                        _fail("campaign_metric", f"artifacts.performance[{index}].budget must be numeric")
                    row["budget"] = budget
                if item.get("evidence") is not None:
                    row["evidence"] = _evidence_ref(
                        item["evidence"], f"artifacts.performance[{index}].evidence"
                    )
                rows.append(row)
            artifacts["performance"] = rows

    normal = {
        "schema": SCHEMA,
        "campaign_id": campaign_id,
        "repository": repository,
        "branch": branch,
        "base_rev": base_rev,
        "head_rev": head_rev,
        "generated_at": generated_at,
        "delivery_state": delivery_state,
        "task_graph": {
            "total": total,
            "implemented": implemented,
            "integrated": integrated,
            "accepted": accepted,
            "remaining": remaining,
            "note": graph_note,
        },
        "pull_requests": pull_requests,
        "acceptance": acceptance,
        "test_runs": test_runs,
        "audits": audits,
        "not_run": not_run,
        "known_limits": known_limits,
        "receiver_decision": "pending",
        "recommended_merge_order": merge_order,
    }
    if artifacts is not None:
        normal["artifacts"] = artifacts

    _secret_check(normal)
    return normal


def load(path: Path | str) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CampaignReportError("campaign_unreadable", f"cannot read report: {exc}") from exc
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise CampaignReportError("campaign_invalid", f"report is not valid JSON: {exc}") from exc
    return validate(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a rizzstack campaign report.")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate", help="validate one campaign report")
    check.add_argument("path")
    check.add_argument("--json", action="store_true", help="print a machine-readable result")
    args = parser.parse_args(argv)

    try:
        report = load(args.path)
    except CampaignReportError as exc:
        if args.json:
            print(json.dumps({"ok": False, "errors": [exc.as_dict()]}, sort_keys=True))
        else:
            print(f"campaign report: INVALID\n  {exc.code}: {exc.message}")
            if exc.fix:
                print(f"  fix: {exc.fix}")
        return 1
    if args.json:
        print(json.dumps({"ok": True, "campaign_id": report["campaign_id"]}, sort_keys=True))
    else:
        print(f"campaign report: VALID ({report['campaign_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
