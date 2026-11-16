#!/usr/bin/env python3
"""rizzstack-obs-collector: read-only observability snapshot aggregator.

Assembles one ``rizzstack.observability/snapshot/1`` document from:

- plugin local state (``jobs/*.json``, ``verify-results/*.json``,
  ``metrics/*.jsonl``, ``queue.json`` under ``--state-dir``),
- the Hermes bundlebees CLI (``<bin> bundlebees attempts`` and
  ``<bin> bundlebees status``, both read-only) for the live fleet,
- ``gh pr list`` / ``gh pr checks`` (read-only) for PR and CI state,
- a ``bee.usage/v1`` JSONL ledger given with ``--usage``.

Every section degrades independently: a missing or unreadable source yields
an empty section with a ``stale``/``unavailable`` status marker, never a
crash, and unknown numeric values are preserved as null rather than folded
into zero.

Serving: with ``--serve`` the current snapshot is served as JSON over
loopback HTTP and requires ``Authorization: Bearer <credential>`` on every
request. The credential comes from ``--bearer-token-file``, then
``--bearer-token``, then the ``RIZZSTACK_OBS_TOKEN`` environment variable;
serving without one refuses to start. The credential is never printed or
logged, request logging is disabled, and non-loopback bind addresses are
refused.

The collector only ever reads. It writes nothing to disk, does not follow
untrusted links, and never echoes stderr from the CLIs it invokes (error
reasons are reported as generic codes). Stdlib only.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA = "rizzstack.observability/snapshot/1"
COLLECTOR_NAME = "rizzstack-obs-collector"

SECTION_NAMES = (
    "fleet",
    "usage",
    "pipeline",
    "backlog",
    "ci",
    "failures",
    "health",
    "alerts",
)

ACTIVE_FLEET_STATES = frozenset(
    {"starting", "running", "working", "backoff", "dispatching", "verifying"}
)

FLEET_STATE_ALIASES = {
    "pending": "queued",
    "dispatching": "queued",
    "leased": "queued",
    "claimed": "queued",
    "dispatched": "starting",
    "accepted_by_worker": "starting",
    "verify": "working",
    "verifying": "working",
    "integrated": "accepted",
    "complete": "succeeded",
    "completed": "succeeded",
    "ok": "succeeded",
    "error": "failed",
    "canceled": "cancelled",
    "cancelled_by_operator": "cancelled",
}

FLEET_STATES = frozenset(
    {
        "queued",
        "starting",
        "running",
        "working",
        "backoff",
        "blocked",
        "succeeded",
        "failed",
        "cancelled",
        "accepted",
        "rejected",
        "not_started",
        "done",
        "unknown",
    }
)

TASK_STATES = frozenset(
    {
        "pending",
        "dispatching",
        "dispatched",
        "running",
        "verifying",
        "verified",
        "integrating",
        "accepted",
        "rejected",
        "failed",
        "superseded",
    }
)

QUEUE_STATUSES = frozenset(
    {
        "queued",
        "claimed",
        "running",
        "ready_for_review",
        "blocked",
        "failed",
        "needs_approval",
    }
)

FAILURE_CLASSES = frozenset(
    {
        "environmental",
        "regression",
        "rate-limit",
        "auth",
        "unavailable",
        "cancelled",
        "unknown",
    }
)

FAILURE_CLASS_HINTS = (
    ("429", "rate-limit"),
    ("rate_limit", "rate-limit"),
    ("rate-limit", "rate-limit"),
    ("auth", "auth"),
    ("unauthorized", "auth"),
    ("forbidden", "auth"),
    ("timeout", "unavailable"),
    ("connection", "unavailable"),
    ("unavailable", "unavailable"),
    ("cancel", "cancelled"),
    ("lease", "environmental"),
    ("checkout", "environmental"),
    ("provision", "environmental"),
)

REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
CHECK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,_()/-]{0,119}$")
HEX_REV_RE = re.compile(r"^[0-9a-f]{40,64}$")
ID_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PROVIDER_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")

DEFAULT_THRESHOLDS = {
    "deepseek_balance_below_usd": 5,
    "go_allowance_pct_used": 80,
    "go_429_streak": 5,
    "stuck_bee_no_progress_s": 1800,
    "blocker_age_s": 14400,
    "disk_free_pct": 10,
    "bees_in_flight_warn_at": 12,
    "daily_model_spend_above_usd": 10,
}


def utc_now_string(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scrub(value: Any, limit: int = 200) -> str | None:
    """Free text safe for a record: control characters dropped, URLs masked,
    length capped. Never raises."""
    if not isinstance(value, str):
        return None
    text = URL_RE.sub("[url]", value)
    text = CONTROL_RE.sub(" ", text).strip()
    if not text:
        return None
    return text[:limit]


def id_token(value: Any) -> str | None:
    """Keep only opaque identifier-shaped strings; anything else is None."""
    if isinstance(value, str) and ID_TOKEN_RE.match(value):
        return value
    return None


def repo_slug(value: Any) -> str | None:
    if isinstance(value, str) and REPO_SLUG_RE.match(value) and "://" not in value:
        return value
    return None


def branch_name(value: Any) -> str | None:
    if isinstance(value, str) and BRANCH_RE.match(value) and "://" not in value:
        return value
    return None


def check_name(value: Any) -> str | None:
    if isinstance(value, str) and CHECK_NAME_RE.match(value):
        return value
    return None


def provider_label(value: Any) -> str | None:
    if isinstance(value, str) and PROVIDER_LABEL_RE.match(value):
        return value
    return None


def parse_ts(value: Any) -> datetime | None:
    """Parse an RFC 3339 timestamp or epoch seconds; None when unknown."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def parse_iso_or_none(value: Any) -> str | None:
    moment = parse_ts(value)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def first_str(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def first_number(record: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


def first_bool(record: Mapping[str, Any], keys: Sequence[str]) -> bool | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, bool):
            return value
    return None


def read_jsonl(path: Path) -> tuple[list[Any], int]:
    """Read a JSONL file read-only; returns (records, parse_error_count)."""
    records: list[Any] = []
    errors = 0
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    errors += 1
    except OSError:
        return [], 0
    return records, errors


def read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def file_age_s(path: Path, now: datetime) -> int | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return max(0, int(now.timestamp() - mtime))


def newest_mtime(paths: Iterable[Path]) -> float | None:
    newest = None
    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def extract_json(text: str) -> Any:
    """Parse JSON from a tool's stdout, tolerating surrounding text."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    decoder = json.JSONDecoder()
    for start_char in ("{", "["):
        index = text.find(start_char)
        while index != -1:
            try:
                value, _ = decoder.raw_decode(text[index:])
                return value
            except (json.JSONDecodeError, ValueError):
                index = text.find(start_char, index + 1)
    return None


def as_list(value: Any, key: str | None = None) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if key and isinstance(value.get(key), list):
            return value[key]
    return []


def agg_status(known: int, total: int, any_source: bool) -> str:
    if total <= 0 or not any_source:
        return "unavailable" if not any_source else "unknown"
    if known >= total:
        return "known"
    if known <= 0:
        return "unknown"
    return "partial"


def section(
    now: datetime,
    status: str,
    error: str | None,
    **fields: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "error": error,
        "collected_at": utc_now_string(now),
    }
    out.update(fields)
    return out


def default_fleet_argv(bundlebees_bin: str, op: str) -> list[str]:
    """Read-only bundlebees subcommands: ``<bin> bundlebees attempts|status``."""
    return [bundlebees_bin, "bundlebees", op]


FLEET_ERROR_CLI_MISSING = "fleet_cli_missing"
FLEET_ERROR_CLI_TIMEOUT = "fleet_cli_timeout"
FLEET_ERROR_COMMAND_FAILED = "fleet_command_failed"
FLEET_ERROR_OUTPUT_UNPARSEABLE = "fleet_output_unparseable"


def fleet_exit_error(code: int) -> str:
    """Generic cause for a fleet CLI that did not answer; never a path or stderr."""
    if code == 127:
        return FLEET_ERROR_CLI_MISSING
    if code == 124:
        return FLEET_ERROR_CLI_TIMEOUT
    return FLEET_ERROR_COMMAND_FAILED


def subprocess_runner(argv: Sequence[str], timeout_s: float) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(  # noqa: S603 - argv is operator-configured, read-only CLIs
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return proc.returncode, proc.stdout or "", ""
    except subprocess.TimeoutExpired:
        return 124, "", ""
    except OSError:
        return 127, "", ""


Runner = Callable[[Sequence[str]], tuple[int, str, str]]


class Collector:
    """Read-only snapshot builder. Every read degrades independently."""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        usage_path: Path | None = None,
        repos: Sequence[str] = (),
        stale_after_s: int = 1800,
        bundlebees_bin: str = "hermes",
        gh_bin: str = "gh",
        cli_timeout_s: float = 10.0,
        fleet_runner: Runner | None = None,
        gh_runner: Runner | None = None,
        now_fn: Callable[[], datetime] | None = None,
        thresholds: Mapping[str, float] | None = None,
    ) -> None:
        self.state_dir = Path(state_dir) if state_dir else None
        self.usage_path = Path(usage_path) if usage_path else None
        self.extra_repos = [slug for slug in (repo_slug(r) for r in repos) if slug]
        self.stale_after_s = stale_after_s
        self.bundlebees_bin = bundlebees_bin
        self.gh_bin = gh_bin
        self.cli_timeout_s = cli_timeout_s
        self._fleet_runner = fleet_runner
        self._gh_runner = gh_runner
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.thresholds = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            for key, value in thresholds.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    self.thresholds[key] = value

    # ------------------------------------------------------------------ time
    def now(self) -> datetime:
        return self._now_fn()

    def _run(self, runner: Runner | None, argv: Sequence[str]) -> tuple[int, str, str]:
        active = runner or (lambda a: subprocess_runner(a, self.cli_timeout_s))
        return active(argv)

    # ----------------------------------------------------------------- fleet
    def fleet_section(self) -> tuple[dict[str, Any], int | None, int | None]:
        now = self.now()
        generated = utc_now_string(now)
        attempts: list[dict[str, Any]] = []
        in_flight: int | None = None
        bee_cap: int | None = None
        status = "live"
        error: str | None = None
        rows: list[Any] | None = None

        code, out, _ = self._run(
            self._fleet_runner,
            default_fleet_argv(self.bundlebees_bin, "attempts"),
        )
        payload = extract_json(out) if code == 0 else None
        if code != 0:
            status, error = "unavailable", fleet_exit_error(code)
        elif payload is None:
            status, error = "unavailable", FLEET_ERROR_OUTPUT_UNPARSEABLE
        else:
            rows = self._attempts_rows_of(payload)
            if rows is None:
                status, error = "unavailable", FLEET_ERROR_OUTPUT_UNPARSEABLE
            else:
                for raw in rows:
                    if not isinstance(raw, dict):
                        continue
                    attempts.append(self._fleet_row(raw, generated))
                code2, out2, _ = self._run(
                    self._fleet_runner,
                    default_fleet_argv(self.bundlebees_bin, "status"),
                )
                if code2 == 0:
                    summary = extract_json(out2)
                    if isinstance(summary, dict):
                        summary_body = summary.get("summary")
                        body = summary_body if isinstance(summary_body, dict) else summary
                        cap = first_number(body, ("bee_cap", "cap"))
                        if cap is not None and cap >= 1:
                            bee_cap = int(cap)
                        inflight = first_number(body, ("in_flight", "bees_in_flight"))
                        if inflight is not None and inflight >= 0:
                            in_flight = int(inflight)
                if in_flight is None:
                    # Derived from rows the CLI actually reported; when the
                    # attempts output never parsed, in_flight stays null.
                    in_flight = sum(
                        1 for row in attempts if row["state"] in ACTIVE_FLEET_STATES
                    )
                newest = max(
                    (parse_ts(row["updated_at"]) for row in attempts if row["updated_at"]),
                    default=None,
                )
                if attempts and newest and (now - newest) > timedelta(seconds=self.stale_after_s):
                    status, error = "stale", "fleet_state_older_than_threshold"
        return (
            section(
                now,
                status,
                error,
                attempts=attempts,
                in_flight=in_flight,
                bee_cap=bee_cap,
            ),
            in_flight,
            bee_cap,
        )

    def _attempts_rows_of(self, payload: Any) -> list[Any] | None:
        """The attempts list of the CLI output; None when the shape mismatches."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("attempts"), list):
                return payload["attempts"]
            for value in payload.values():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value
        return None

    def _fleet_row(self, raw: Mapping[str, Any], generated: str) -> dict[str, Any]:
        attempt_id = id_token(first_str(raw, ("attempt_id", "id", "attempt")))
        raw_state = first_str(raw, ("state", "status")) or "unknown"
        raw_state = scrub(raw_state, 40) or "unknown"
        state = self._normalize_fleet_state(raw_state)
        return {
            "schema": SCHEMA,
            "generated_at": generated,
            "attempt_id": attempt_id or "unknown",
            "state": state,
            "job_id": id_token(first_str(raw, ("job_id", "job"))),
            "task_id": id_token(first_str(raw, ("task_id", "task"))),
            "repo": repo_slug(first_str(raw, ("repo", "repository"))),
            "branch": branch_name(first_str(raw, ("branch", "head_branch"))),
            "route": self._route_of(raw),
            "started_at": parse_iso_or_none(first_str(raw, ("started_at", "started", "ts"))),
            "updated_at": parse_iso_or_none(first_str(raw, ("updated_at", "updated", "heartbeat_at"))),
            "detail": None if state != "unknown" else raw_state,
        }

    def _normalize_fleet_state(self, raw_state: str) -> str:
        lowered = raw_state.strip().lower().replace("-", "_").replace(" ", "_")
        if lowered in FLEET_STATES:
            return lowered
        alias = FLEET_STATE_ALIASES.get(lowered)
        if alias and alias in FLEET_STATES:
            return alias
        return "unknown"

    def _route_of(self, raw: Mapping[str, Any]) -> str | None:
        route = provider_label(first_str(raw, ("route", "provider")))
        if route in ("go", "deepseek") or (route and PROVIDER_LABEL_RE.match(route)):
            return route
        return None

    # ----------------------------------------------------------------- usage
    def usage_section(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (section, summary) where summary carries today's known cost
        sum and quota hints for health/alerts."""
        now = self.now()
        generated = utc_now_string(now)
        empty_totals = {
            "schema": SCHEMA,
            "generated_at": generated,
            "requests": 0,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "tokens_status": "unavailable",
            "cost_status": "unavailable",
            "unknown_cost_records": 0,
            "http_429_count": 0,
            "fallback_count": 0,
        }
        empty_source = {
            "schema": SCHEMA,
            "generated_at": generated,
            "record_count": 0,
            "parse_errors": 0,
            "usage_status": "unavailable",
        }
        summary: dict[str, Any] = {"today_cost_usd": 0.0, "today_known": 0, "quota_rows": []}
        if self.usage_path is None:
            body = section(
                now,
                "unavailable",
                "source_missing",
                source=empty_source,
                totals=empty_totals,
                by_model=[],
                by_repo=[],
            )
            return body, summary
        if not self.usage_path.is_file():
            body = section(
                now,
                "unavailable",
                "source_missing",
                source=empty_source,
                totals=empty_totals,
                by_model=[],
                by_repo=[],
            )
            return body, summary

        records, parse_errors = read_jsonl(self.usage_path)
        today_prefix = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
        totals = {"input": 0, "output": 0, "total": 0, "cost": 0.0}
        known = {"input": 0, "output": 0, "total": 0, "cost": 0}
        requests = 0
        unknown_cost = 0
        http_429_count = 0
        fallback_count = 0
        by_model: dict[tuple[str, str], dict[str, Any]] = {}
        by_repo: dict[str, dict[str, Any]] = {}
        seen_any = False

        for record in records:
            if not isinstance(record, dict):
                parse_errors += 1
                continue
            seen_any = True
            requests += 1
            usage_status = record.get("usage_status")
            model = scrub(first_str(record, ("served_model", "model", "requested_model")), 64) or "unknown"
            model = model if ID_TOKEN_RE.match(model) else "unknown"
            provider = provider_label(first_str(record, ("route", "provider"))) or "unknown"
            inp = _int_or_none(first_number(record, ("input_tokens", "prompt_tokens")))
            outp = _int_or_none(first_number(record, ("output_tokens", "completion_tokens")))
            total = _int_or_none(first_number(record, ("total_tokens", "tokens")))
            if total is None and inp is not None and outp is not None:
                total = inp + outp
            cost = first_number(record, ("cost_usd", "cost_usd_total", "cost"))
            cost_known = cost is not None
            record_unknown = usage_status == "unknown"
            if not cost_known:
                unknown_cost += 1
            if inp is not None:
                totals["input"] += inp
                known["input"] += 1
            if outp is not None:
                totals["output"] += outp
                known["output"] += 1
            if total is not None:
                totals["total"] += total
                known["total"] += 1
            if cost is not None:
                totals["cost"] += cost
                known["cost"] += 1

            http_429 = first_number(record, ("http_429", "http_429_count", "count_429"))
            if isinstance(record.get("http_429"), bool):
                http_429_count += 1 if record["http_429"] else 0
            elif http_429 is not None:
                http_429_count += int(http_429)
            if record.get("fallback") or record.get("fallen_back"):
                fallback_count += 1

            # Quota hints for the health section (never secret material).
            go_pct = first_number(record, ("go_allowance_used_pct", "go_allowance_pct_used"))
            if go_pct is not None:
                label = id_token(first_str(record, ("go_label", "go_key_label", "resource_id"))) or "go"
                summary["quota_rows"].append(
                    {
                        "kind": "go_allowance",
                        "resource_id": label,
                        "value": go_pct,
                        "unit": "percent",
                        "cap": 100.0,
                        "remaining": max(0.0, 100.0 - go_pct),
                        "status": "exhausted" if go_pct >= 100 else ("low" if go_pct >= self.thresholds["go_allowance_pct_used"] else "ok"),
                    }
                )
            balance = first_number(record, ("deepseek_balance_usd", "deepseek_credit_usd"))
            if balance is not None:
                summary["quota_rows"].append(
                    {
                        "kind": "deepseek_credit",
                        "resource_id": None,
                        "value": balance,
                        "unit": "usd",
                        "cap": None,
                        "remaining": balance,
                        "status": "ok" if balance >= self.thresholds["deepseek_balance_below_usd"] else "low",
                    }
                )

            ts = parse_ts(first_str(record, ("ts", "created_at", "time")))
            if ts and cost is not None and ts.astimezone(timezone.utc).strftime("%Y-%m-%d") == today_prefix:
                summary["today_cost_usd"] += cost
                summary["today_known"] += 1

            bucket = by_model.setdefault(
                (model, provider),
                self._usage_bucket(generated, model=model, provider=provider),
            )
            self._usage_accumulate(bucket, requests_delta=1, inp=inp, outp=outp, total=total, cost=cost, cost_known=cost_known, record_unknown=record_unknown)

            repo = repo_slug(first_str(record, ("repo", "repository")))
            if repo is None:
                repo = "unknown/unknown"  # sentinel for records without a slug
            rbucket = by_repo.setdefault(
                repo,
                self._usage_bucket(generated, model=None, provider=None, repo=repo),
            )
            self._usage_accumulate(rbucket, requests_delta=1, inp=inp, outp=outp, total=total, cost=cost, cost_known=cost_known, record_unknown=record_unknown)

        tokens_status = (
            "unavailable"
            if not seen_any
            else agg_status(min(known["input"], known["output"]), requests, seen_any)
        )
        cost_status = "unavailable" if not seen_any else agg_status(known["cost"], requests, seen_any)
        usage_status = "unavailable" if not seen_any else ("known" if parse_errors == 0 else "partial")
        totals_row = {
            "schema": SCHEMA,
            "generated_at": generated,
            "requests": requests,
            "input_tokens": totals["input"] if known["input"] else None,
            "output_tokens": totals["output"] if known["output"] else None,
            "total_tokens": totals["total"] if known["total"] else None,
            "cost_usd": round(totals["cost"], 6) if known["cost"] else None,
            "tokens_status": tokens_status,
            "cost_status": cost_status,
            "unknown_cost_records": unknown_cost,
            "http_429_count": http_429_count,
            "fallback_count": fallback_count,
        }
        model_rows = sorted(by_model.values(), key=lambda row: (row["provider"], row["model"]))
        repo_rows = sorted(by_repo.values(), key=lambda row: row["repo"])
        for row in model_rows + repo_rows:
            row.pop("_sums", None)
            row.pop("_known", None)
        status = "live"
        error: str | None = None
        if not seen_any:
            status, error = "unavailable", "no_records"
        else:
            age = file_age_s(self.usage_path, now)
            if age is not None and age > self.stale_after_s:
                status, error = "stale", "ledger_older_than_threshold"
        body = section(
            now,
            status,
            error,
            source={
                "schema": SCHEMA,
                "generated_at": generated,
                "record_count": requests,
                "parse_errors": parse_errors,
                "usage_status": usage_status,
            },
            totals=totals_row,
            by_model=model_rows,
            by_repo=repo_rows,
        )
        return body, summary

    def _usage_bucket(
        self,
        generated: str,
        *,
        model: str | None,
        provider: str | None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        bucket: dict[str, Any] = {
            "schema": SCHEMA,
            "generated_at": generated,
            "requests": 0,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "tokens_status": "unknown",
            "cost_status": "unknown",
        }
        if repo is not None:
            bucket["repo"] = repo
        else:
            bucket["model"] = model
            bucket["provider"] = provider
        bucket["_sums"] = {"input": 0, "output": 0, "total": 0, "cost": 0.0}
        bucket["_known"] = {"input": 0, "output": 0, "total": 0, "cost": 0}
        return bucket

    def _usage_accumulate(
        self,
        bucket: dict[str, Any],
        *,
        requests_delta: int,
        inp: int | None,
        outp: int | None,
        total: int | None,
        cost: float | None,
        cost_known: bool,
        record_unknown: bool,
    ) -> None:
        sums = bucket["_sums"]
        known = bucket["_known"]
        bucket["requests"] += requests_delta
        if inp is not None:
            sums["input"] += inp
            known["input"] += 1
        if outp is not None:
            sums["output"] += outp
            known["output"] += 1
        if total is not None:
            sums["total"] += total
            known["total"] += 1
        if cost is not None:
            sums["cost"] += cost
            known["cost"] += 1
        requests_now = bucket["requests"]
        bucket["input_tokens"] = sums["input"] if known["input"] else None
        bucket["output_tokens"] = sums["output"] if known["output"] else None
        bucket["total_tokens"] = sums["total"] if known["total"] else None
        bucket["cost_usd"] = round(sums["cost"], 6) if known["cost"] else None
        bucket["tokens_status"] = agg_status(
            min(known["input"], known["output"]), requests_now, True
        )
        bucket["cost_status"] = agg_status(known["cost"], requests_now, True)
        if record_unknown:
            # An explicitly unknown record keeps its buckets partial at best.
            if bucket["cost_status"] == "known" and known["cost"] < requests_now:
                bucket["cost_status"] = "partial"

    # -------------------------------------------------------------- pipeline
    def pipeline_section(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Returns (section, blocker_and_escalation_rows) — the age of those
        rows feeds the blocker-age alert."""
        now = self.now()
        generated = utc_now_string(now)
        jobs: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        escalations: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        seen_files = 0
        job_dir = self.state_dir / "jobs" if self.state_dir else None
        paths: list[Path] = []
        if job_dir is not None:
            try:
                paths = sorted(p for p in job_dir.glob("*.json") if p.is_file())
            except OSError:
                paths = []
        for path in paths:
            data = read_json_dict(path)
            if data is None:
                continue
            seen_files += 1
            job_id = id_token(data.get("job_id")) or id_token(path.stem) or "unknown"
            goal = data.get("goal") if isinstance(data.get("goal"), dict) else {}
            repo = repo_slug(goal.get("repo"))
            base_rev_raw = first_str(goal, ("base_rev", "base"))
            base_rev = (
                base_rev_raw.lower()
                if isinstance(base_rev_raw, str) and HEX_REV_RE.match(base_rev_raw.strip().lower())
                else None
            )
            tasks_raw = as_list(data.get("tasks"))
            task_rows: list[dict[str, Any]] = []
            job_escalations = as_list(data.get("escalations"))
            for index, task in enumerate(tasks_raw):
                if not isinstance(task, dict):
                    continue
                task_id = id_token(task.get("task_id")) or f"T{index + 1}"
                state = task.get("state")
                if not isinstance(state, str) or state not in TASK_STATES:
                    continue  # closed vocabulary; unrecognized states are skipped
                attempts = task.get("attempts")
                attempts_count = len(attempts) if isinstance(attempts, list) else (
                    attempts if isinstance(attempts, int) and attempts >= 0 else None
                )
                reason = self._task_reason(task, state)
                task_rows.append(
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "task_id": task_id,
                        "state": state,
                        "attempts_count": attempts_count,
                        "reason": reason,
                    }
                )
                counts[state] = counts.get(state, 0) + 1
                if state in ("rejected", "failed", "superseded"):
                    blockers.append(
                        {
                            "schema": SCHEMA,
                            "generated_at": generated,
                            "job_id": job_id,
                            "task_id": task_id,
                            "reason": id_token(reason) or "task_" + state,
                            "detail": reason,
                            "created_at": self._last_attempt_ts(task),
                        }
                    )
            approval_gate = data.get("approval_gate")
            gate_state = (
                approval_gate.get("state")
                if isinstance(approval_gate, dict) and isinstance(approval_gate.get("state"), str)
                else None
            )
            for index, esc in enumerate(job_escalations):
                if not isinstance(esc, dict):
                    continue
                reason_raw = first_str(esc, ("reason", "code", "kind")) or "escalation"
                escalations.append(
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "job_id": job_id,
                        "reason": _reason_token(reason_raw),
                        "detail": scrub(first_str(esc, ("detail", "message", "note"))),
                        "created_at": parse_iso_or_none(first_str(esc, ("ts", "created_at", "at"))),
                    }
                )
            if gate_state and gate_state not in ("waiting", "done", "satisfied"):
                escalations.append(
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "job_id": job_id,
                        "reason": "approval_required",
                        "detail": scrub(gate_state),
                        "created_at": None,
                    }
                )
            jobs.append(
                {
                    "schema": SCHEMA,
                    "generated_at": generated,
                    "job_id": job_id,
                    "repo": repo,
                    "base_rev": base_rev,
                    "task_count": len(task_rows),
                    "tasks": task_rows,
                    "escalation_count": sum(
                        1 for item in job_escalations if isinstance(item, dict)
                    ),
                }
            )
        status, error = "live", None
        if seen_files == 0:
            status, error = "unavailable", "source_missing"
        else:
            newest = newest_mtime(paths)
            if newest is not None:
                age = int(now.timestamp() - newest)
                if age > self.stale_after_s:
                    status, error = "stale", "job_state_older_than_threshold"
        body = section(
            now,
            status,
            error,
            jobs=jobs,
            counts=counts,
            escalations=escalations,
            blockers=blockers,
        )
        return body, blockers + escalations

    def _task_reason(self, task: Mapping[str, Any], state: str) -> str | None:
        reason = scrub(first_str(task, ("reason", "blocker_reason", "failure_reason")))
        if reason:
            return reason
        attempts = task.get("attempts")
        if isinstance(attempts, list) and attempts:
            last = attempts[-1]
            if isinstance(last, dict):
                reason = scrub(first_str(last, ("reason", "error", "outcome_reason", "detail")))
                if reason:
                    return reason
                outcome = first_str(last, ("outcome", "status", "state"))
                if isinstance(outcome, str) and outcome not in ("ok", "success", "proven"):
                    return scrub("attempt_" + outcome)
        if state in ("rejected", "failed", "superseded"):
            return "state_" + state
        return None

    def _last_attempt_ts(self, task: Mapping[str, Any]) -> str | None:
        attempts = task.get("attempts")
        if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict):
            return parse_iso_or_none(first_str(attempts[-1], ("ts", "created_at", "time")))
        return None

    # --------------------------------------------------------------- backlog
    def backlog_section(self) -> dict[str, Any]:
        now = self.now()
        generated = utc_now_string(now)
        features: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        status, error = "live", None
        queue_path = self.state_dir / "queue.json" if self.state_dir else None
        data = read_json_dict(queue_path) if queue_path else None
        if data is None:
            status, error = "unavailable", "source_missing"
        else:
            rows: list[tuple[str, Mapping[str, Any]]] = []
            if isinstance(data.get("features"), list):
                rows = [
                    (str(f.get("feature_id") or f"feature-{i}"), f)
                    for i, f in enumerate(data["features"])
                    if isinstance(f, dict)
                ]
            elif isinstance(data.get("features"), dict):
                rows = [(str(k), v) for k, v in data["features"].items() if isinstance(v, dict)]
            else:
                rows = [(str(k), v) for k, v in data.items() if isinstance(v, dict)]
            for feature_id, row in rows:
                fid = id_token(feature_id)
                if fid is None:
                    continue
                status_raw = row.get("status")
                if not isinstance(status_raw, str):
                    continue
                status_norm = status_raw.strip().lower().replace("-", "_").replace(" ", "_")
                if status_norm not in QUEUE_STATUSES:
                    continue
                depends = [
                    tok
                    for tok in (id_token(d) for d in as_list(row.get("depends_on")))
                    if tok
                ]
                features.append(
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "feature_id": fid,
                        "job_id": id_token(row.get("job_id")),
                        "status": status_norm,
                        "depends_on": depends,
                    }
                )
                counts[status_norm] = counts.get(status_norm, 0) + 1
            age = file_age_s(queue_path, now) if queue_path else None
            if age is not None and age > self.stale_after_s:
                status, error = "stale", "queue_older_than_threshold"
        return section(now, status, error, features=features, counts=counts)

    # -------------------------------------------------------------------- ci
    def ci_section(self, pipeline_jobs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        now = self.now()
        generated = utc_now_string(now)
        repos: list[str] = list(self.extra_repos)
        for job in pipeline_jobs:
            slug = job.get("repo")
            if isinstance(slug, str) and slug not in repos and REPO_SLUG_RE.match(slug):
                repos.append(slug)
        repo_rows: list[dict[str, Any]] = []
        pr_rows: list[dict[str, Any]] = []
        failures = 0
        successes = 0
        for slug in repos:
            code, out, _ = self._run(
                self._gh_runner,
                [
                    self.gh_bin,
                    "pr",
                    "list",
                    "--repo",
                    slug,
                    "--state",
                    "open",
                    "--limit",
                    "50",
                    "--json",
                    "number,headRefName,state,statusCheckRollup",
                ],
            )
            payload = extract_json(out) if code == 0 else None
            if payload is None:
                failures += 1
                repo_rows.append(
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "repo": slug,
                        "branch": None,
                        "open_prs": None,
                        "ci_state": "unavailable",
                        "failing_check_names": [],
                    }
                )
                continue
            successes += 1
            prs = as_list(payload)
            failing: set[str] = set()
            repo_state: set[str] = set()
            open_count = 0
            for pr in prs:
                if not isinstance(pr, dict):
                    continue
                open_count += 1
                number = pr.get("number")
                if not isinstance(number, int) or isinstance(number, bool):
                    continue
                checks, check_source = self._pr_checks(slug, number, pr.get("statusCheckRollup"))
                ci_state, failing_names = _ci_state_of(checks, check_source)
                repo_state.add(ci_state)
                failing.update(failing_names)
                pr_state = pr.get("state")
                pr_state = pr_state.lower() if isinstance(pr_state, str) else "unknown"
                if pr_state not in ("open", "merged", "closed", "draft"):
                    pr_state = "unknown"
                head = branch_name(pr.get("headRefName"))
                pr_rows.append(
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "repo": slug,
                        "number": number,
                        "state": pr_state,
                        "head_branch": head,
                        "ci_state": ci_state,
                        "failing_check_names": failing_names,
                    }
                )
            if open_count == 0:
                repo_ci = "unavailable"
            elif repo_state == {"passing"}:
                repo_ci = "passing"
            elif repo_state == {"failing"}:
                repo_ci = "failing"
            elif "pending" in repo_state and not ({"failing", "mixed"} & repo_state):
                repo_ci = "pending"
            else:
                repo_ci = "mixed"
            repo_rows.append(
                {
                    "schema": SCHEMA,
                    "generated_at": generated,
                    "repo": slug,
                    "branch": None,
                    "open_prs": open_count,
                    "ci_state": repo_ci,
                    "failing_check_names": sorted(failing),
                }
            )
        if not repos:
            status, error = "unavailable", "no_repos_configured"
        elif successes == 0:
            status, error = "unavailable", "ci_command_failed"
        else:
            status, error = "live", None
        pr_rows.sort(key=lambda row: (row["repo"], row["number"]))
        return section(now, status, error, repos=repo_rows, prs=pr_rows)

    def _pr_checks(
        self,
        slug: str,
        number: int,
        rollup: Any,
    ) -> tuple[list[tuple[str, str]], str]:
        checks: list[tuple[str, str]] = []
        source = "none"
        if isinstance(rollup, list) and rollup:
            source = "rollup"
            for entry in rollup:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("workflowName") or ""
                state = entry.get("state") or entry.get("conclusion") or entry.get("status") or ""
                checks.append((str(name), str(state)))
        elif isinstance(rollup, dict) and rollup:
            source = "rollup"
            name = rollup.get("name") or ""
            state = rollup.get("state") or rollup.get("conclusion") or ""
            checks.append((str(name), str(state)))
        if not checks:
            code, out, _ = self._run(
                self._gh_runner,
                [self.gh_bin, "pr", "checks", str(number), "--repo", slug, "--json", "name,state"],
            )
            payload = extract_json(out) if code == 0 else None
            if isinstance(payload, list):
                source = "checks"
                for entry in payload:
                    if isinstance(entry, dict):
                        checks.append((str(entry.get("name") or ""), str(entry.get("state") or "")))
        return checks, source

    # -------------------------------------------------------------- failures
    def failures_section(self) -> dict[str, Any]:
        now = self.now()
        generated = utc_now_string(now)
        failures: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        seen_files = 0
        vdir = self.state_dir / "verify-results" if self.state_dir else None
        paths: list[Path] = []
        if vdir is not None:
            try:
                paths = sorted(p for p in vdir.glob("*.json") if p.is_file())
            except OSError:
                paths = []
        for path in paths:
            data = read_json_dict(path)
            if data is None:
                continue
            seen_files += 1
            row = self._failure_row(data, path.stem, generated)
            if row is None:
                continue
            failures.append(row)
            counts[row["class"]] = counts.get(row["class"], 0) + 1
        status, error = "live", None
        if seen_files == 0:
            status, error = "unavailable", "source_missing"
        else:
            newest = newest_mtime(paths)
            if newest is not None:
                age = int(now.timestamp() - newest)
                if age > self.stale_after_s:
                    status, error = "stale", "verify_results_older_than_threshold"
        return section(now, status, error, failures=failures, counts=counts)

    def _failure_row(
        self,
        data: Mapping[str, Any],
        stem: str,
        generated: str,
    ) -> dict[str, Any] | None:
        outcome = first_str(data, ("outcome", "status", "result")) or ""
        outcome_norm = outcome.strip().lower()
        suite = data.get("suite") if isinstance(data.get("suite"), dict) else {}
        exit_code = suite.get("exit_code") if isinstance(suite, dict) else None
        ok_outcomes = {"ok", "success", "proven", "pass", "passed", "verified", "accepted"}
        suite_ok = isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code == 0
        if outcome_norm in ok_outcomes or (outcome_norm == "" and suite_ok):
            return None
        if outcome_norm in ("", "none", "null") and not suite_ok and exit_code is None:
            return None
        code = id_token(first_str(data, ("code", "failure_code", "error_code")))
        cls = data.get("class")
        cls = cls if isinstance(cls, str) and cls in FAILURE_CLASSES else None
        if cls is None:
            cls = _infer_failure_class(outcome_norm, code)
        note = scrub(first_str(data, ("reason", "note", "detail", "message")), 500)
        http_429 = first_bool(data, ("http_429",))
        if http_429 is None and code and "429" in code:
            http_429 = True
        fallback = data.get("fallback_to")
        fallback = provider_label(fallback) if isinstance(fallback, str) else None
        if fallback not in ("deepseek",) and fallback is not None and not PROVIDER_LABEL_RE.match(fallback):
            fallback = None
        ts = parse_iso_or_none(first_str(data, ("ts", "created_at", "finished_at", "time")))
        if ts is None:
            ts = utc_now_string(self.now())
        job_id = id_token(first_str(data, ("job_id",)))
        task_id = id_token(first_str(data, ("task_id",)))
        attempt_id = id_token(first_str(data, ("attempt_id",))) or id_token(stem)
        return {
            "schema": SCHEMA,
            "generated_at": generated,
            "ts": ts,
            "attempt_id": attempt_id,
            "job_id": job_id,
            "task_id": task_id,
            "class": cls,
            "code": code,
            "component": id_token(first_str(data, ("component",))),
            "retryable": first_bool(data, ("retryable",)),
            "http_429": http_429,
            "fallback_to": fallback,
            "note": note,
        }

    # ---------------------------------------------------------------- health
    def health_section(
        self,
        fleet_body: Mapping[str, Any],
        usage_summary: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """Returns (section, observations) — observations feed alerts."""
        now = self.now()
        generated = utc_now_string(now)
        metrics_paths: list[Path] = []
        if self.state_dir is not None:
            metrics_dir = self.state_dir / "metrics"
            try:
                metrics_paths = sorted(p for p in metrics_dir.glob("*.jsonl") if p.is_file())
            except OSError:
                metrics_paths = []
        last_event_at: str | None = None
        last_event_age_s: int | None = None
        liveness = "unavailable"
        for path in metrics_paths:
            records, _ = read_jsonl(path)
            for record in records:
                if not isinstance(record, dict):
                    continue
                ts = parse_ts(first_str(record, ("ts", "time", "timestamp", "created_at")))
                if ts is None:
                    continue
                if last_event_at is None or ts.strftime("%Y-%m-%dT%H:%M:%SZ") > last_event_at:
                    last_event_at = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        if last_event_at is not None:
            moment = parse_ts(last_event_at)
            assert moment is not None
            last_event_age_s = max(0, int((now - moment).total_seconds()))
            liveness = "live" if last_event_age_s <= self.stale_after_s else "stale"
        scheduler = {
            "schema": SCHEMA,
            "generated_at": generated,
            "liveness": liveness,
            "alive": True if liveness == "live" else (False if liveness == "stale" else None),
            "last_event_at": last_event_at,
            "last_event_age_s": last_event_age_s,
            "source": "metrics",
        }

        quota_rows: list[dict[str, Any]] = []
        for hint in as_list(usage_summary.get("quota_rows")):
            if not isinstance(hint, dict):
                continue
            quota_rows.append(
                {
                    "schema": SCHEMA,
                    "generated_at": generated,
                    "kind": hint.get("kind"),
                    "resource_id": hint.get("resource_id"),
                    "value": hint.get("value"),
                    "unit": hint.get("unit"),
                    "cap": hint.get("cap"),
                    "remaining": hint.get("remaining"),
                    "status": hint.get("status"),
                }
            )
        in_flight = fleet_body.get("in_flight")
        bee_cap = fleet_body.get("bee_cap")
        if isinstance(in_flight, int) and not isinstance(in_flight, bool):
            warn_at = self.thresholds["bees_in_flight_warn_at"]
            quota_rows.append(
                {
                    "schema": SCHEMA,
                    "generated_at": generated,
                    "kind": "bees_in_flight",
                    "resource_id": None,
                    "value": in_flight,
                    "unit": "count",
                    "cap": bee_cap if isinstance(bee_cap, int) else None,
                    "remaining": (
                        max(0, bee_cap - in_flight)
                        if isinstance(bee_cap, int)
                        else None
                    ),
                    "status": "low" if in_flight >= warn_at else "ok",
                }
            )
        if not quota_rows and liveness == "unavailable":
            status, error = "unavailable", "no_health_sources"
        elif liveness == "stale":
            status, error = "stale", "scheduler_older_than_threshold"
        else:
            status, error = "live", None
        body = section(
            now,
            status,
            error,
            scheduler=scheduler,
            quota=quota_rows,
            bees_in_flight=in_flight if isinstance(in_flight, int) and not isinstance(in_flight, bool) else None,
            bee_cap=bee_cap if isinstance(bee_cap, int) and bee_cap >= 1 else None,
        )
        observations = {
            "bees_in_flight": float(in_flight) if isinstance(in_flight, int) and not isinstance(in_flight, bool) else None,
            "bee_cap": float(bee_cap) if isinstance(bee_cap, int) else None,
            "last_event_age_s": float(last_event_age_s) if last_event_age_s is not None else None,
            "today_cost_usd": float(usage_summary.get("today_cost_usd") or 0.0)
            if isinstance(usage_summary.get("today_cost_usd"), (int, float))
            else None,
        }
        return body, observations

    # ---------------------------------------------------------------- alerts
    def alerts_section(
        self,
        *,
        observations: Mapping[str, Any],
        blockers: Sequence[Mapping[str, Any]],
        quota_rows: Sequence[Mapping[str, Any]],
        any_live_input: bool,
    ) -> dict[str, Any]:
        now = self.now()
        generated = utc_now_string(now)
        active: list[dict[str, Any]] = []
        emitted: set[tuple[str, str]] = set()

        def add(key: str, observed: float | None, threshold: float | None, message: str, label: str = "") -> None:
            dedupe = (key, label)
            if dedupe in emitted:
                return
            emitted.add(dedupe)
            active.append(
                {
                    "schema": SCHEMA,
                    "generated_at": generated,
                    "key": key,
                    "severity": "warn",
                    "message": scrub(message, 200) or key,
                    "observed": observed,
                    "threshold": threshold,
                    "ts": utc_now_string(now),
                }
            )

        bees = observations.get("bees_in_flight")
        warn_at = self.thresholds["bees_in_flight_warn_at"]
        if isinstance(bees, (int, float)) and bees >= warn_at:
            add(
                "bees_in_flight_warn_at",
                float(bees),
                float(warn_at),
                f"bees in flight at {int(bees)} reaches the warn cap of {int(warn_at)}",
            )
        age = observations.get("last_event_age_s")
        stuck = self.thresholds["stuck_bee_no_progress_s"]
        if isinstance(age, (int, float)) and age > stuck:
            add(
                "stuck_bee_no_progress_s",
                float(age),
                float(stuck),
                f"no scheduler progress event for {int(age)}s",
            )
        blocker_threshold = self.thresholds["blocker_age_s"]
        for blocker in blockers:
            created = parse_ts(blocker.get("created_at"))
            if created is None:
                continue
            age_s = int((now - created).total_seconds())
            if age_s >= blocker_threshold:
                add(
                    "blocker_age_s",
                    float(age_s),
                    float(blocker_threshold),
                    f"blocker {blocker.get('reason')} open for {age_s}s",
                )
                break
        go_threshold = self.thresholds["go_allowance_pct_used"]
        for row in quota_rows:
            if row.get("kind") == "go_allowance" and isinstance(row.get("value"), (int, float)):
                value = float(row["value"])
                if value >= go_threshold:
                    add(
                        "go_allowance_pct_used",
                        value,
                        float(go_threshold),
                        f"Go key {row.get('resource_id')} at {value:.0f}% of allowance",
                        label=str(row.get("resource_id") or ""),
                    )
            if row.get("kind") == "deepseek_credit" and isinstance(row.get("value"), (int, float)):
                balance = float(row["value"])
                floor = self.thresholds["deepseek_balance_below_usd"]
                if balance < floor:
                    add(
                        "deepseek_balance_below_usd",
                        balance,
                        float(floor),
                        f"DeepSeek credit at {balance:.2f} USD",
                        label="deepseek",
                    )
        today_cost = observations.get("today_cost_usd")
        spend_cap = self.thresholds["daily_model_spend_above_usd"]
        if isinstance(today_cost, (int, float)) and today_cost > spend_cap:
            add(
                "daily_model_spend_above_usd",
                float(today_cost),
                float(spend_cap),
                f"today's model spend is {today_cost:.2f} USD",
            )
        status = "live" if any_live_input else "unavailable"
        error = None if any_live_input else "no_live_inputs"
        return section(now, status, error, active=active)

    # -------------------------------------------------------------- assembly
    def build_snapshot(self) -> dict[str, Any]:
        now = self.now()
        generated = utc_now_string(now)
        fleet, in_flight, bee_cap = self.fleet_section()
        usage, usage_summary = self.usage_section()
        pipeline, blockers = self.pipeline_section()
        backlog = self.backlog_section()
        ci = self.ci_section(pipeline.get("jobs", []))
        failures = self.failures_section()
        health, observations = self.health_section(fleet, usage_summary)
        any_live = any(
            body.get("status") == "live"
            for body in (fleet, usage, pipeline, backlog, ci, failures, health)
        )
        alerts = self.alerts_section(
            observations=observations,
            blockers=blockers,
            quota_rows=health.get("quota", []),
            any_live_input=any_live,
        )
        sections = {
            "fleet": fleet,
            "usage": usage,
            "pipeline": pipeline,
            "backlog": backlog,
            "ci": ci,
            "failures": failures,
            "health": health,
            "alerts": alerts,
        }
        return {
            "schema": SCHEMA,
            "generated_at": generated,
            "collector": {"name": COLLECTOR_NAME},
            "degraded": [name for name in SECTION_NAMES if sections[name].get("status") != "live"],
            **sections,
        }


def _reason_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_")[:64]
    return token or "escalation"


def _infer_failure_class(outcome_norm: str, code: str | None) -> str:
    haystack = f"{outcome_norm} {code or ''}".lower()
    for needle, cls in FAILURE_CLASS_HINTS:
        if needle in haystack:
            return cls
    if "suite" in haystack or "test" in haystack or "verify" in haystack:
        return "regression"
    return "unknown"


def _int_or_none(value: float | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _check_state(state: str) -> str:
    normalized = state.strip().upper()
    if normalized in ("SUCCESS", "PASSED", "NEUTRAL", "SKIPPED"):
        return "pass"
    if normalized in ("FAILURE", "FAILED", "ERROR", "TIMED_OUT", "START_FAILURE"):
        return "fail"
    if normalized in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "RUNNING"):
        return "pending"
    return "pending"


def _ci_state_of(checks: Sequence[tuple[str, str]], source: str) -> tuple[str, list[str]]:
    failing: list[str] = []
    if source == "none" or not checks:
        return "unavailable" if source == "none" else "pending", failing
    states = set()
    for name, state in checks:
        mapped = _check_state(state)
        states.add(mapped)
        if mapped == "fail":
            clean = check_name(name)
            if clean:
                failing.append(clean)
    if states == {"pass"}:
        return "passing", failing
    if states == {"fail"} or (states <= {"fail", "pending"} and "fail" in states):
        return "failing", failing
    if "pending" in states and "fail" not in states:
        return "pending", failing
    return "mixed", failing


# --------------------------------------------------------------------- serving
def _load_thresholds_from_repo(repo_root: Path) -> dict[str, float]:
    path = repo_root / "observability" / "alerts.defaults.json"
    data = read_json_dict(path)
    if not data:
        return dict(DEFAULT_THRESHOLDS)
    thresholds = data.get("thresholds")
    merged = dict(DEFAULT_THRESHOLDS)
    if isinstance(thresholds, dict):
        for key, value in thresholds.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[key] = value
    return merged


def make_server(
    host: str,
    port: int,
    snapshot_provider: Callable[[], Mapping[str, Any]],
    credential: str,
) -> ThreadingHTTPServer:
    """Loopback-only HTTP server exposing the snapshot behind a bearer check."""
    if host == "localhost":
        host = "127.0.0.1"
    if host != "127.0.0.1" and host != "::1":
        raise ValueError("refusing to bind a non-loopback address")
    expected = credential.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _deny(self, code: int, body: str, headers: dict[str, str] | None = None) -> None:
            payload = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            auth = self.headers.get("Authorization") or ""
            parts = auth.split(" ", 1)
            provided = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""
            ok = bool(provided) and hmac.compare_digest(provided.encode("utf-8"), expected)
            if not ok:
                self._deny(401, "unauthorized", {"WWW-Authenticate": "Bearer"})
                return
            if self.path not in ("/", "/snapshot"):
                self._deny(404, "not found")
                return
            try:
                snapshot = snapshot_provider()
                payload = json.dumps(snapshot, indent=2, sort_keys=True).encode("utf-8")
            except Exception:
                self._deny(500, "snapshot unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib naming
            self._deny(405, "method not allowed")

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Never log requests: paths and headers could carry credential material.
            return

        def log_error(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    return ThreadingHTTPServer((host, port), Handler)


# ------------------------------------------------------------------------ main
def resolve_credential(args: argparse.Namespace) -> str | None:
    if getattr(args, "bearer_token_file", None):
        try:
            text = Path(args.bearer_token_file).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text or None
    if getattr(args, "bearer_token", None):
        return args.bearer_token
    value = os.environ.get("RIZZSTACK_OBS_TOKEN", "").strip()
    return value or None


class QuietArgumentParser(argparse.ArgumentParser):
    """argparse that never echoes argv in errors: a mistyped flag could
    otherwise carry a credential value into stderr."""

    def error(self, message: str) -> None:  # type: ignore[override]
        print("argument error; run with --help for usage", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = QuietArgumentParser(
        prog=COLLECTOR_NAME,
        description="Read-only rizzstack observability snapshot collector.",
        add_help=True,
    )
    parser.add_argument("--state-dir", type=Path, default=None, help="plugin local state directory")
    parser.add_argument("--usage", type=Path, default=None, dest="usage_path", help="bee.usage/v1 JSONL path")
    parser.add_argument("--repo", action="append", default=[], metavar="OWNER/NAME", help="repo for the ci section (repeatable)")
    parser.add_argument("--stale-after-s", type=int, default=1800, help="freshness threshold in seconds")
    parser.add_argument("--bundlebees-bin", default="hermes", help="Hermes CLI binary for the fleet section")
    parser.add_argument("--gh-bin", default="gh", help="GitHub CLI binary for the ci section")
    parser.add_argument("--cli-timeout-s", type=float, default=10.0, help="subprocess timeout in seconds")
    parser.add_argument("--print", action="store_true", dest="print_snapshot", help="print the snapshot to stdout (default)")
    parser.add_argument("--serve", action="store_true", help="serve the snapshot over loopback HTTP")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (loopback only)")
    parser.add_argument("--port", type=int, default=8787, help="bind port")
    parser.add_argument("--bearer-token", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--bearer-token-file", type=Path, default=None, help="file holding the serving credential (0600)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    thresholds = _load_thresholds_from_repo(repo_root)
    collector = Collector(
        state_dir=args.state_dir,
        usage_path=args.usage_path,
        repos=args.repo,
        stale_after_s=args.stale_after_s,
        bundlebees_bin=args.bundlebees_bin,
        gh_bin=args.gh_bin,
        cli_timeout_s=args.cli_timeout_s,
        thresholds=thresholds,
    )
    if args.serve:
        credential = resolve_credential(args)
        if not credential:
            print("serving requires a bearer credential; refusing to start", file=sys.stderr)
            return 2
        try:
            server = make_server(args.host, args.port, collector.build_snapshot, credential)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except OSError:
            print("could not bind the loopback socket", file=sys.stderr)
            return 2
        print(f"serving on {args.host}:{args.port}", file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    snapshot = collector.build_snapshot()
    json.dump(snapshot, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
