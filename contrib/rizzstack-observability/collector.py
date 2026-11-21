#!/usr/bin/env python3
"""rizzstack-obs-collector: read-only observability snapshot aggregator.

Assembles one ``rizzstack.observability/snapshot/1`` document from:

- plugin local state (``jobs/*.json``, ``verify-results/*.json``,
  ``metrics/*.jsonl``, ``queue.json``, the live claim records under
  ``queue/``, the recorded decision files under ``approvals/``, and the
  dispatch leases under ``leases/`` joined with the bee-landed events under
  ``events/outbox/`` (the legacy ``outbox/`` is still read) under
  ``--state-dir``,
- the Hermes bundlebees CLI (``<bin> bundlebees attempts --state-dir DIR``
  and ``<bin> bundlebees status --state-dir DIR``, both read-only) for the
  live fleet - when the CLI cannot answer, the fleet section falls back to
  the dispatch-lease store joined with the bee-landed outbox under
  ``events/outbox/`` and marks itself ``stale`` with ``source:
  dispatch_leases``,
- ``gh pr list`` / ``gh pr checks`` (read-only) for PR and CI state,
- a ``bee.usage/v1`` JSONL ledger given with ``--usage``.

The bottlenecks section is computed from the same records (job documents,
the feature queue, the claim store, recorded approval decisions, verify
results, scheduler metrics, the fleet, open pull requests): per stage queue
depth, oldest-item age, dwell-time median and p95, throughput, WIP versus
capacity, and the coordinator reconciler's own invariant of eligible work
waiting despite available scheduler capacity. Dwell targets per stage are
threshold configuration, not constants.

Fleet rows and pipeline rows are honest about what their source shows. A
fleet row whose active state is older than the staleness threshold is
demoted to ``unknown`` and is not counted in-flight, and the CLI status
``bee_cap`` is launcher configuration, not an observed fleet fact: it is
never surfaced in the fleet section, though the health quota row and the
bottlenecks verify stage still derive from it. The pipeline section carries
the job title and summary from the goal and each task's title from its
first acceptance-criterion statement, scrubbed like every other free-text
field.

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
import math
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA = "rizzstack.observability/snapshot/1"
COLLECTOR_NAME = "rizzstack-obs-collector"
OWNER_DECISION_SCHEMA = "rizzstack.owner-decision/1"
DECISION_KINDS = frozenset({"gate", "budget", "scope", "grant"})

SECTION_NAMES = (
    "fleet",
    "usage",
    "pipeline",
    "backlog",
    "ci",
    "failures",
    "health",
    "alerts",
    "bottlenecks",
    "decisions",
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
    # ``verified`` is a RECORDED OUTCOME, not work in progress: the bee
    # finished and its result awaits acceptance. It used to alias to
    # ``working``, which counted 104 finished attempts as active bees.
    "verified": "verified",
    "expired": "expired",
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
        "verified",
        "expired",
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

# Bottleneck stages. Each maps to the real record that shows work waiting
# there: verify counts job tasks in the verifying state, review counts
# features ready for review on the action queue, integrate counts verified
# and integrating tasks at the integration wave, and deploy counts open
# pull requests.
STAGE_NAMES = ("verify", "review", "integrate", "deploy")
VERIFY_ENTRY_STATES = frozenset({"verifying"})
VERIFY_MEMBER_STATES = frozenset({"verifying"})
VERIFY_ADVANCE_STATES = frozenset({"verified", "integrating", "accepted"})
INTEGRATE_ENTRY_STATES = frozenset({"verified"})
INTEGRATE_MEMBER_STATES = frozenset({"verified", "integrating"})
INTEGRATE_ADVANCE_STATES = frozenset({"accepted"})
INTEGRATE_QUEUE_STATES = frozenset({"verified", "integrating"})
NON_TERMINAL_TASK_STATES = frozenset(
    TASK_STATES - {"accepted", "rejected", "failed", "superseded"}
)
NON_TERMINAL_QUEUE_STATUSES = frozenset(QUEUE_STATUSES - {"failed"})
# The reconciler's automatic-progress destinations: a recorded job
# transition into one of these states is automatic progression, and a
# scheduler dispatch, verify or integrate event is its metrics counterpart.
# Human interventions and recovery decisions do not count.
AUTOMATIC_PROGRESS_STATES = frozenset(
    {"dispatching", "dispatched", "running", "verifying", "verified", "integrating", "accepted"}
)
METRIC_AUTO_EVENTS = frozenset({"dispatch", "verify", "integrate"})
WORKER_COMPLETED_SUFFIX = "->verifying"
# The work scheduler's active-slot budget (work_scheduler.MAX_ACTIVE). This,
# not the shared bee cap, is the capacity the reconciler's invariant uses.
SCHEDULER_MAX_ACTIVE = 4
# Claim records the queue store treats as in flight (QueueStore.active()).
ACTIVE_CLAIM_STATES = frozenset({"claimed", "running"})
#: Task states the coordinator reconciler counts as claimed work
#: (reconcile.py dispatching/dispatched); a running task is an active
#: worker, not a claim, and the queue claim record for the same unit is
#: reported separately, never added twice.
CLAIMED_TASK_STATES = frozenset({"dispatching", "dispatched"})
WORKING_FLEET_STATES = frozenset({"running", "working"})
# How many dispatch-lease records the fleet fallback reads at most (the
# newest ones by mtime), so one crowded store cannot balloon a snapshot.
FLEET_FALLBACK_LEASE_LIMIT = 24

DEFAULT_THRESHOLDS = {
    "deepseek_balance_below_usd": 5,
    "go_allowance_pct_used": 80,
    "go_429_streak": 5,
    "stuck_bee_no_progress_s": 1800,
    "blocker_age_s": 14400,
    "disk_free_pct": 10,
    "bees_in_flight_warn_at": 12,
    "daily_model_spend_above_usd": 10,
    # SLO-style dwell targets per bottleneck stage, in seconds. The dashboard
    # draws threshold lines from these; operators override them like any
    # other threshold key.
    "verify_dwell_target_s": 3600,
    "review_dwell_target_s": 14400,
    "integrate_dwell_target_s": 7200,
    "deploy_dwell_target_s": 86400,
}


def utc_now_string(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_utc_moment(value: Any) -> datetime:
    """Normalize an injected clock to an aware UTC datetime.

    The collector takes an injected clock so snapshots are deterministic in
    tests; a caller may hand it epoch seconds, a naive datetime or an aware
    one. A value that is not a clock at all (None, a string, a bool) falls
    back to the real UTC clock: a bad injection must degrade to ``now``,
    never crash the build - over HTTP that crash is a 500 where the contract
    says a snapshot, and staleness arithmetic would raise before the
    degradation ladder ever runs.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    return datetime.now(timezone.utc)


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
            try:
                number = float(value)
            except OverflowError:
                continue
            if math.isfinite(number):
                return number
    return None


def first_count(record: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    """Non-negative integer observation, without rounding large JSON integers."""
    for key in keys:
        value = record.get(key)
        if type(value) is int and value >= 0:
            return value
        if isinstance(value, float) and value >= 0 and value.is_integer():
            return int(value)
    return None


def first_bool(record: Mapping[str, Any], keys: Sequence[str]) -> bool | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, bool):
            return value
    return None


_BAD_JSON = object()


def jsonl_rows(path: Path) -> Iterable[Any]:
    """Yield one parsed record at a time, or a marker for a malformed line."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    yield _BAD_JSON


def read_jsonl(path: Path) -> tuple[list[Any], int]:
    """Read a JSONL file read-only; returns (records, parse_error_count)."""
    records: list[Any] = []
    errors = 0
    try:
        for row in jsonl_rows(path):
            if row is _BAD_JSON:
                errors += 1
            else:
                records.append(row)
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


def unwrap_job_envelope(data: dict[str, Any]) -> dict[str, Any] | None:
    """Unwrap the on-disk job envelope shape job.py _seal writes.

    Real job documents are stored as ``{"body": {...}, "mac": "..."}``
    (docs/22-autonomy-architecture.md: jobs/<job_id>.json, HMAC). This is a
    read-only, keyless collector: when the envelope shape is present the
    body is used as the document and the MAC is NOT verified here - the
    reconciler, which holds the state key, is the verifier of record. An
    envelope whose body is not an object yields None (the caller counts the
    file unreadable, an owner message, never a silent zero); a plain
    document with neither key passes through so legacy shapes and RETURN
    reports keep reading.
    """
    body = data.get("body")
    if isinstance(body, dict):
        return body
    if "body" in data or "mac" in data:
        return None
    return data


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


def token_status(known: Mapping[str, int], requests: int) -> str:
    if not requests:
        return "unavailable"
    if min(known["input"], known["output"]) == requests:
        return "known"
    return "partial" if known["input"] or known["output"] or known["total"] else "unknown"


def _median_of(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _p95_of(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return float(ordered[rank - 1])


def _age_s(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    return max(0, int((now - moment).total_seconds()))


def _window_rates(
    moments: Sequence[datetime], now: datetime
) -> tuple[float, float]:
    """Items advanced per hour over the last hour and the last day."""
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)
    recent = sum(1 for moment in moments if moment >= hour_ago)
    daily = sum(1 for moment in moments if moment >= day_ago)
    return round(float(recent), 6), round(daily / 24.0, 6)


def _stage_walk(
    transitions: Sequence[tuple[datetime, str]],
    entry_states: frozenset[str],
    member_states: frozenset[str],
    advance_states: frozenset[str],
) -> tuple[datetime | None, list[float], list[datetime]]:
    """Walk one task's recorded state transitions.

    Returns (open entry into the stage, completed dwell seconds, moments the
    task advanced past the stage). A stay opens on a transition into an
    entry state and closes on the next transition out of the stage's member
    states; a move deeper into the stage (for example verified into
    integrating) keeps the stay open. A recorded transition to a state past
    the stage counts as an advance even when the stage entry was never
    recorded, but only once per passage. Records that show no entry
    contribute no dwell: unknown stays unknown.
    """
    stays: list[float] = []
    advances: list[datetime] = []
    open_entry: datetime | None = None
    entered: datetime | None = None
    advanced = False
    for moment, to_state in transitions:
        if to_state in member_states:
            if entered is None and to_state in entry_states:
                entered = moment
                advanced = False
            continue
        if entered is not None:
            stays.append(max(0.0, (moment - entered).total_seconds()))
            entered = None
        if to_state in advance_states and not advanced:
            advances.append(moment)
            advanced = True
    if entered is not None:
        open_entry = entered
    return open_entry, stays, advances


def _stage_row(
    generated: str,
    stage: str,
    *,
    now: datetime,
    queue_depth: int | None,
    oldest_item_age_s: int | None,
    dwell_samples: Sequence[float],
    dwell_status: str,
    advanced: Sequence[datetime],
    throughput_status: str,
    wip: int | None,
    capacity: int | None,
    capacity_source: str | None,
    target: float | None,
) -> dict[str, Any]:
    median = _median_of(dwell_samples)
    p95 = _p95_of(dwell_samples)
    if throughput_status in ("known", "partial"):
        per_hour_1h, per_hour_24h = _window_rates(advanced, now)
    else:
        per_hour_1h = per_hour_24h = None
    if target is None or (median is None and p95 is None):
        state = "unknown"
    else:
        worst = max(value for value in (median, p95) if value is not None)
        state = "over" if worst > target else "ok"
    return {
        "schema": SCHEMA,
        "generated_at": generated,
        "stage": stage,
        "queue_depth": queue_depth,
        "oldest_item_age_s": oldest_item_age_s,
        "dwell_median_s": median,
        "dwell_p95_s": p95,
        "dwell_status": dwell_status,
        "throughput_per_hour_1h": per_hour_1h,
        "throughput_per_hour_24h": per_hour_24h,
        "throughput_status": throughput_status,
        "wip": wip,
        "capacity": capacity,
        "capacity_source": capacity_source,
        "state": state,
    }


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


def default_fleet_argv(
    bundlebees_bin: str,
    op: str,
    state_dir: Path | str | None = None,
) -> list[str]:
    """Read-only bundlebees subcommands, scoped to the plugin state directory.

    The real read-only subcommands are ``<bin> bundlebees attempts`` and
    ``<bin> bundlebees status``, each taking ``--state-dir DIR``; the
    ``bundlebees attempt op=...`` shape never existed. The collector forwards
    the state directory it was given so the fleet rows it reads describe the
    same jobs the pipeline section reads. Without a state directory the bare
    subcommand is sent and the CLI applies its own default.
    """
    argv = [bundlebees_bin, "bundlebees", op]
    if state_dir is not None:
        argv += ["--state-dir", str(state_dir)]
    return argv


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
        cli_workers: int = 8,
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
        # Independent read-only CLI reads (fleet attempts/status, one gh read per
        # repo) run concurrently, so a snapshot costs the slowest read rather than
        # their sum. 1 restores strictly sequential reads.
        self.cli_workers = max(1, int(cli_workers))
        self.thresholds = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            for key, value in thresholds.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    self.thresholds[key] = value

    # ------------------------------------------------------------------ time
    def now(self) -> datetime:
        """The collector's clock, normalized once: epoch seconds, naive and
        aware datetimes all become an aware UTC moment; a non-clock value
        falls back to the real UTC clock (see ``as_utc_moment``)."""
        return as_utc_moment(self._now_fn())

    def _run(self, runner: Runner | None, argv: Sequence[str]) -> tuple[int, str, str]:
        active = runner or (lambda a: subprocess_runner(a, self.cli_timeout_s))
        return active(argv)

    def _parallel(self, calls: Sequence[Callable[[], Any]]) -> list[Any]:
        """Run independent zero-argument reads, results in the given order.

        Sequential when ``cli_workers`` is 1 or there is a single call. An
        exception in one call propagates exactly as it would sequentially.
        """
        if self.cli_workers <= 1 or len(calls) <= 1:
            return [call() for call in calls]
        with ThreadPoolExecutor(
            max_workers=min(self.cli_workers, len(calls)),
            thread_name_prefix="obs-read",
        ) as pool:
            futures = [pool.submit(call) for call in calls]
            return [future.result() for future in futures]

    # ----------------------------------------------------------------- fleet
    def fleet_section(self) -> tuple[dict[str, Any], int | None, int | None]:
        """Returns (section, in_flight, bee_cap).

        The section body is what the snapshot surfaces: rows, the derived
        in-flight count and a ``source`` marker. The CLI status ``bee_cap``
        is deliberately NOT surfaced there - it is launcher configuration,
        not an observed fleet fact, so the body's ``bee_cap`` field stays
        null - but the value is still returned to the caller because the
        health quota row and the bottlenecks verify stage derive from it.
        When the CLI cannot answer, the rows are rebuilt from the
        dispatch-lease store joined with the bee-landed outbox (see
        ``_lease_fallback_rows``); that fallback view is marked ``stale``
        with ``source: dispatch_leases`` so no consumer mistakes it for a
        live CLI read.
        """
        now = self.now()
        generated = utc_now_string(now)
        attempts: list[dict[str, Any]] = []
        in_flight: int | None = None
        bee_cap: int | None = None
        status = "live"
        error: str | None = None
        source = "cli"
        rows: list[Any] | None = None

        # Both fleet CLI reads are read-only and independent, so they run
        # together; the status read is consulted only when the attempts read
        # produced rows, exactly as when it ran second.
        (code, out, _), (code2, out2, _) = self._parallel(
            [
                lambda: self._run(
                    self._fleet_runner,
                    default_fleet_argv(self.bundlebees_bin, "attempts", self.state_dir),
                ),
                lambda: self._run(
                    self._fleet_runner,
                    default_fleet_argv(self.bundlebees_bin, "status", self.state_dir),
                ),
            ]
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
        if rows is None:
            # The CLI could not answer: rebuild what the durable dispatch
            # records can show. With no lease rows the section stays
            # unavailable and empty, exactly as before.
            fallback = self._lease_fallback_rows(generated, now)
            if fallback:
                attempts = fallback
                source = "dispatch_leases"
                status = "stale"
                in_flight = sum(
                    1 for row in attempts if row["state"] in ACTIVE_FLEET_STATES
                )
        else:
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                attempts.append(self._fleet_row(raw, generated, now))
            if code2 == 0:
                summary = extract_json(out2)
                if isinstance(summary, dict):
                    summary_body = summary.get("summary")
                    body = summary_body if isinstance(summary_body, dict) else summary
                    cap = first_number(body, ("bee_cap", "cap"))
                    if cap is not None and cap >= 1:
                        bee_cap = int(cap)
            # The in-flight count is the collector's own count over the rows
            # it just read: stale-active rows were demoted to unknown by the
            # row builder and are therefore never counted, and the CLI
            # status tally is not parroted over rows that contradict it.
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
                source=source,
                attempts=attempts,
                in_flight=in_flight,
                # The CLI status bee_cap is launcher configuration, not an
                # observed fleet fact: the fleet section never surfaces it.
                # The value returned above still feeds the health quota row
                # and the bottlenecks verify stage.
                bee_cap=None,
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

    def _fleet_row(
        self, raw: Mapping[str, Any], generated: str, now: datetime
    ) -> dict[str, Any]:
        """One fleet row from a CLI attempts row or a dispatch-lease record.

        Branch is carried when the source names it and stays null otherwise.
        The model/title widening was reverted: they are not fleet-attempt
        fields and are never surfaced, whatever the source carries. Fleet
        honesty: an ACTIVE-state row whose heartbeat is older than the
        staleness threshold cannot be vouched for as active - it is demoted
        to ``unknown`` with the raw state label kept in ``detail``, which
        also removes it from the in-flight count. The clock is normalized
        once here so an injected non-datetime cannot reach the staleness
        arithmetic and crash the build.
        """
        now = as_utc_moment(now)
        attempt_id = id_token(first_str(raw, ("attempt_id", "id", "attempt")))
        raw_state = first_str(raw, ("state", "status")) or "unknown"
        raw_state = scrub(raw_state, 40) or "unknown"
        state = self._normalize_fleet_state(raw_state)
        detail = None if state != "unknown" else raw_state
        updated = parse_ts(first_str(raw, ("updated_at", "updated", "heartbeat_at")))
        if (
            state in ACTIVE_FLEET_STATES
            and updated is not None
            and (now - updated) > timedelta(seconds=self.stale_after_s)
        ):
            state = "unknown"
            detail = raw_state
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
            "detail": detail,
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

    # ------------------------------------------------- dispatch-lease fallback
    def _lease_fallback_rows(self, generated: str, now: datetime) -> list[dict[str, Any]]:
        """Fleet rows rebuilt from durable dispatch records when the CLI
        cannot answer.

        Reads the dispatch-lease store ``state_dir/leases/att_*.json`` (the
        newest 24 records by mtime; the collector only reads) and joins each
        lease with the newest ``rizzstack.bee.landed.v1`` event for its
        attempt under the live ``state_dir/events/outbox/`` (the legacy
        ``state_dir/outbox/`` is still read). A lease alone proves the attempt
        was dispatched, so it renders as the lifecycle-aligned ``starting``
        state dated by the lease itself; a landing event supplies the
        terminal state and the landing time. The row builder's staleness
        demotion applies to these rows exactly as to CLI rows, so an old
        lease without a landing cannot pass for an active bee. Unreadable
        records are skipped, never fatal.
        """
        if self.state_dir is None:
            return []
        leases_dir = self.state_dir / "leases"

        def mtime_of(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        try:
            candidates = [p for p in leases_dir.glob("att_*.json") if p.is_file()]
        except OSError:
            return []
        paths = sorted(candidates, key=mtime_of, reverse=True)[:FLEET_FALLBACK_LEASE_LIMIT]
        if not paths:
            return []
        landed = self._outbox_landed_states()
        rows: list[dict[str, Any]] = []
        for path in paths:
            record = read_json_dict(path)
            if record is None:
                continue
            raw = dict(record)
            attempt_id = id_token(first_str(raw, ("attempt_id", "id", "attempt"))) or id_token(
                path.stem
            )
            # The lease itself dates the dispatch, whatever the landing says.
            lease_ts = first_str(raw, ("created_at", "dispatched_at", "ts", "at"))
            if lease_ts is None:
                try:
                    lease_ts = utc_now_string(
                        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                    )
                except OSError:
                    lease_ts = None
            if lease_ts is not None:
                raw.setdefault("started_at", lease_ts)
            landing = landed.get(attempt_id) if attempt_id else None
            if landing is not None:
                raw.setdefault("state", landing["state"])
                if landing.get("time"):
                    raw.setdefault("updated_at", landing["time"])
            else:
                # No landing recorded: the lease write is the last fact, so
                # the staleness demotion ages the row from it.
                if lease_ts is not None:
                    raw.setdefault("updated_at", lease_ts)
                raw.setdefault("state", "dispatched")
            rows.append(self._fleet_row(raw, generated, now))
        return rows

    def _outbox_landed_states(self) -> dict[str, dict[str, Any]]:
        """Newest bee-landed event per attempt id, read-only.

        The live ``state_dir/events/outbox/`` holds the coordinator's durable
        ``rizzstack.bee.landed.v1`` CloudEvents, one JSON object per file or
        one per line in a ``.jsonl`` file; the legacy ``state_dir/outbox/``
        is still read. Files that are not landings or do not parse are
        skipped. Only the payload's ``attempt_id`` joins a landing to a
        lease; the envelope ``subject`` may name a task and is never used as
        a join key. The newest event per attempt (by its CloudEvents
        ``time``) wins across both directories, so redeliveries collapse.
        """
        if self.state_dir is None:
            return {}
        paths: list[Path] = []
        for outbox_dir in (
            self.state_dir / "events" / "outbox",
            self.state_dir / "outbox",
        ):
            try:
                paths.extend(
                    p for p in outbox_dir.iterdir()
                    if p.is_file() and p.suffix in (".json", ".jsonl")
                )
            except OSError:
                continue
        paths.sort()
        landed: dict[str, dict[str, Any]] = {}
        for path in paths:
            if path.suffix == ".jsonl":
                records, _ = read_jsonl(path)
            else:
                single = read_json_dict(path)
                records = [single] if single is not None else []
            for event in records:
                if not isinstance(event, dict):
                    continue
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                if event.get("type") != "rizzstack.bee.landed.v1" and data.get(
                    "schema"
                ) != "rizzstack.bee-landed/1":
                    continue
                attempt_id = id_token(first_str(data, ("attempt_id",)))
                state = first_str(data, ("state",))
                if attempt_id is None or not isinstance(state, str):
                    continue
                moment = parse_ts(first_str(event, ("time",))) or parse_ts(
                    first_str(data, ("ts", "at"))
                )
                known = landed.get(attempt_id)
                if known is None or (
                    moment is not None and (known["moment"] is None or moment > known["moment"])
                ):
                    landed[attempt_id] = {
                        "state": state,
                        "time": moment.strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None,
                        "moment": moment,
                    }
        return landed

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
        error = "source_missing"
        if self.usage_path is not None:
            try:
                return self._aggregate_usage(now, generated, jsonl_rows(self.usage_path))
            except FileNotFoundError:
                pass
            except OSError:
                # Discard even the subtotal if the ledger failed halfway through.
                error = "source_unreadable"
        return section(now, "unavailable", error, source=empty_source, totals=empty_totals,
                       by_model=[], by_repo=[]), summary

    def _aggregate_usage(self, now: datetime, generated: str, records: Iterable[Any]) -> tuple[dict, dict]:
        summary: dict[str, Any] = {"today_cost_usd": 0.0, "today_known": 0, "quota_rows": []}
        parse_errors = 0
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
        latest_quota: dict[tuple[str, str | None], tuple[datetime | None, dict[str, Any]]] = {}

        def remember_quota(ts: datetime | None, hint: dict[str, Any]) -> None:
            key = (hint["kind"], hint["resource_id"])
            previous = latest_quota.get(key)
            # Prefer event time over append order. If neither reading is dated,
            # or the timestamps tie, the last ledger entry wins.
            if previous is None or previous[0] is None or (ts is not None and ts >= previous[0]):
                latest_quota[key] = (ts, hint)

        for record in records:
            if not isinstance(record, dict):
                parse_errors += 1
                continue
            seen_any = True
            requests += 1
            model = scrub(first_str(record, ("served_model", "model", "requested_model")), 64) or "unknown"
            model = model if ID_TOKEN_RE.match(model) else "unknown"
            provider = provider_label(first_str(record, ("route", "provider"))) or "unknown"
            inp = first_count(record, ("input_tokens", "prompt_tokens"))
            outp = first_count(record, ("output_tokens", "completion_tokens"))
            total = first_count(record, ("total_tokens", "tokens"))
            # Orbit keeps the producer's total in usage_raw for extension-only
            # events. Cache/thinking semantics vary; prefer the reported total.
            if total is None and isinstance(record.get("usage_raw"), dict):
                total = first_count(record["usage_raw"], ("total",))
            if total is None and inp is not None and outp is not None:
                total = inp + outp
            cost = first_number(record, ("cost_usd_list", "cost_usd", "cost_usd_total", "cost"))
            if cost is not None and cost < 0:
                cost = None
            if cost is None:
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

            http_429 = first_count(record, ("http_429", "http_429_count", "count_429"))
            if isinstance(record.get("http_429"), bool):
                http_429_count += 1 if record["http_429"] else 0
            elif http_429 is not None:
                http_429_count += http_429
            if record.get("fallback") or record.get("fallen_back"):
                fallback_count += 1

            # Quota hints for the health section (never secret material).
            ts = parse_ts(first_str(record, ("ts", "ts_end", "ts_start", "created_at", "time")))
            go_pct = first_number(record, ("go_allowance_used_pct", "go_allowance_pct_used"))
            allowance = record.get("go_allowance")
            # Orbit also emits a per-request derived_list_price percentage;
            # only an observed account reading is a quota update.
            if go_pct is None and isinstance(allowance, dict) and allowance.get("pct_source") == "opencode.allowance":
                go_pct = first_number(allowance, ("pct_used",))
            if go_pct is not None:
                label = id_token(first_str(record, ("go_label", "go_key_label", "resource_id"))) or "go"
                remember_quota(
                    ts,
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
                remember_quota(
                    ts,
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

            if ts and cost is not None and ts.astimezone(timezone.utc).strftime("%Y-%m-%d") == today_prefix:
                summary["today_cost_usd"] += cost
                summary["today_known"] += 1

            key = (model, provider)
            if key not in by_model:
                by_model[key] = self._usage_bucket(generated, model=model, provider=provider)
            self._usage_accumulate(by_model[key], requests_delta=1, inp=inp, outp=outp, total=total, cost=cost)

            repo = repo_slug(first_str(record, ("repo", "repository", "project")))
            if repo is None:
                repo = "unknown/unknown"  # sentinel for records without a slug
            if repo not in by_repo:
                by_repo[repo] = self._usage_bucket(generated, model=None, provider=None, repo=repo)
            self._usage_accumulate(by_repo[repo], requests_delta=1, inp=inp, outp=outp, total=total, cost=cost)

        summary["quota_rows"] = [hint for _, hint in latest_quota.values()]
        tokens_status = token_status(known, requests)
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
        bucket["tokens_status"] = token_status(known, requests_now)
        bucket["cost_status"] = agg_status(known["cost"], requests_now, True)

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
            data = unwrap_job_envelope(data)
            if data is None:
                continue
            seen_files += 1
            job_id = id_token(data.get("job_id")) or id_token(path.stem) or "unknown"
            goal = data.get("goal") if isinstance(data.get("goal"), dict) else {}
            repo = repo_slug(goal.get("repo"))
            job_title = scrub(first_str(goal, ("title", "objective")))
            job_summary = scrub(first_str(goal, ("summary", "description")))
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
                        "title": self._task_title(task),
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
                    "title": job_title,
                    "summary": job_summary,
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

    def _task_title(self, task: Mapping[str, Any]) -> str | None:
        """The task's title: its first acceptance-criterion statement.

        The acdd/1 contract titles a task by its first criterion statement,
        so the pipeline row carries exactly that, scrubbed. A task without
        criteria has no title; the objective is never substituted, and a
        criterion without a usable statement is skipped.
        """
        for criterion in self._acceptance_criteria(task):
            statement = (
                criterion.get("statement") if isinstance(criterion, dict) else criterion
            )
            title = scrub(statement if isinstance(statement, str) else None)
            if title:
                return title
        return None

    @staticmethod
    def _acceptance_criteria(task: Mapping[str, Any]) -> list[Any]:
        for key in ("acceptance_criteria", "accepts"):
            value = task.get(key)
            if isinstance(value, list) and value:
                return value
        contract = task.get("contract")
        if isinstance(contract, dict):
            value = contract.get("acceptance_criteria")
            if isinstance(value, list) and value:
                return value
        return []

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
        def read_repo(slug: str) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
            """One repo's open PRs and CI rows; (repo_row, pr_rows, answered)."""
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
                    "number,headRefName,state,createdAt,statusCheckRollup",
                ],
            )
            payload = extract_json(out) if code == 0 else None
            if payload is None:
                return (
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "repo": slug,
                        "branch": None,
                        "open_prs": None,
                        "ci_state": "unavailable",
                        "failing_check_names": [],
                    },
                    [],
                    False,
                )
            prs = as_list(payload)
            rows: list[dict[str, Any]] = []
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
                rows.append(
                    {
                        "schema": SCHEMA,
                        "generated_at": generated,
                        "repo": slug,
                        "number": number,
                        "state": pr_state,
                        "head_branch": head,
                        "created_at": parse_iso_or_none(pr.get("createdAt")),
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
            return (
                {
                    "schema": SCHEMA,
                    "generated_at": generated,
                    "repo": slug,
                    "branch": None,
                    "open_prs": open_count,
                    "ci_state": repo_ci,
                    "failing_check_names": sorted(failing),
                },
                rows,
                True,
            )

        # One gh read per repo, concurrently; rows keep the configured repo order.
        repo_rows: list[dict[str, Any]] = []
        pr_rows: list[dict[str, Any]] = []
        successes = 0
        for repo_row, rows, answered in self._parallel(
            [lambda slug=slug: read_repo(slug) for slug in repos]
        ):
            repo_rows.append(repo_row)
            pr_rows.extend(rows)
            successes += 1 if answered else 0
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

    # ----------------------------------------------------------- bottlenecks
    def _read_job_documents(self) -> tuple[list[dict[str, Any]], int]:
        """Read-only pass over the job documents for the bottlenecks section.

        Reads the shapes the producers actually write: the on-disk HMAC
        envelope ({"body", "mac"}, job.py _seal) is unwrapped read-only and
        keylessly, task attempts are a list of attempt-id strings
        (reconcile.py appends ids), and the recorded events are documents
        with at/task_id/transition/actor/reason where transition is the
        ``from->to`` string (job.py transition). An event record that
        cannot yield a transition still counts as seen, so a half-readable
        history degrades to partial or unknown instead of passing as
        complete. An envelope whose body is not an object counts as an
        unreadable job.

        Returns (documents, unreadable_document_count).
        """
        docs: list[dict[str, Any]] = []
        unreadable = 0
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
                unreadable += 1
                continue
            data = unwrap_job_envelope(data)
            if data is None:
                unreadable += 1
                continue
            job_id = id_token(data.get("job_id")) or id_token(path.stem) or "unknown"
            tasks: list[dict[str, Any]] = []
            for index, task in enumerate(as_list(data.get("tasks"))):
                if not isinstance(task, dict):
                    continue
                task_id = id_token(task.get("task_id")) or f"T{index + 1}"
                state = task.get("state")
                state = state if isinstance(state, str) and state in TASK_STATES else None
                attempt_ids = [
                    tok
                    for tok in (id_token(attempt) for attempt in as_list(task.get("attempts")))
                    if tok
                ]
                blocker: str | None = None
                if state in ("rejected", "failed", "superseded"):
                    reason = scrub(first_str(task, ("reason", "blocker_reason", "failure_reason")), 80)
                    blocker = _reason_token(reason) if reason else "task_" + str(state)
                tasks.append(
                    {
                        "task_id": task_id,
                        "state": state,
                        "attempt_ids": attempt_ids,
                        "blocker": blocker,
                        "binding": task.get("binding") if isinstance(task.get("binding"), dict) else {},
                        "contract_sha256": first_str(task, ("contract_sha256",)),
                    }
                )
            events: list[tuple[datetime, str, str]] = []
            ordered: list[tuple[datetime, str]] = []
            raw_events = 0
            latency_gaps: list[float] = []
            for event in as_list(data.get("events")):
                raw_events += 1
                if not isinstance(event, dict):
                    continue
                task_id = id_token(event.get("task_id"))
                moment = parse_ts(first_str(event, ("at",)))
                transition = event.get("transition")
                if not (task_id and moment is not None and isinstance(transition, str) and "->" in transition):
                    continue
                to_state = transition.rsplit("->", 1)[-1]
                if not to_state:
                    continue
                events.append((moment, task_id, to_state))
                ordered.append((moment, transition))
            events.sort(key=lambda item: (item[0], item[1]))
            # The reconciler's own latency pair: a recorded worker-completion
            # transition and the next recorded event of the job, in document
            # order.
            for index, (moment, transition) in enumerate(ordered):
                if not transition.endswith(WORKER_COMPLETED_SUFFIX):
                    continue
                following = ordered[index + 1][0] if index + 1 < len(ordered) else None
                if following is not None:
                    latency_gaps.append(max(0.0, (following - moment).total_seconds()))
            gate = data.get("approval_gate")
            gate_names: list[str] = []
            if isinstance(gate, dict):
                gate_names = [
                    name.strip()
                    for name in (item for item in as_list(gate.get("gates")) if isinstance(item, str))
                    if name.strip()
                ]
            docs.append(
                {
                    "job_id": job_id,
                    "tasks": tasks,
                    "events": events,
                    "raw_events": raw_events,
                    "latency_gaps": latency_gaps,
                    "gate_names": gate_names,
                    "integration": data.get("integration") if isinstance(data.get("integration"), dict) else {},
                }
            )
        return docs, unreadable

    def _read_verify_reports(self) -> list[dict[str, Any]]:
        """Read-only pass over the verify results.

        The producers write attempt_id/ok/sha/branch/files/tests/at/evidence
        with no job or task reference (the cli.py verify writer; the
        commit-local writer adds base_rev, suite and gitleaks outcomes), so
        rows key on the attempt id alone. The job link comes from the
        task's attempt-id list.
        """
        rows: list[dict[str, Any]] = []
        report_dir = self.state_dir / "verify-results" if self.state_dir else None
        paths: list[Path] = []
        if report_dir is not None:
            try:
                paths = sorted(p for p in report_dir.glob("*.json") if p.is_file())
            except OSError:
                paths = []
        for path in paths:
            data = read_json_dict(path)
            if not isinstance(data, dict):
                continue
            suite = data.get("suite") if isinstance(data.get("suite"), dict) else {}
            gitleaks = data.get("gitleaks") if isinstance(data.get("gitleaks"), dict) else {}
            suite_exit = suite.get("exit_code")
            gitleaks_exit = gitleaks.get("exit_code")
            rows.append(
                {
                    "attempt_id": id_token(first_str(data, ("attempt_id",))) or id_token(path.stem),
                    "ok": data.get("ok") if isinstance(data.get("ok"), bool) else None,
                    "sha": first_str(data, ("sha",)),
                    "base_rev": first_str(data, ("base_rev",)),
                    "suite_exit": (
                        suite_exit
                        if isinstance(suite_exit, int) and not isinstance(suite_exit, bool)
                        else None
                    ),
                    "gitleaks_exit": (
                        gitleaks_exit
                        if isinstance(gitleaks_exit, int) and not isinstance(gitleaks_exit, bool)
                        else None
                    ),
                    "at": parse_ts(first_str(data, ("at",))),
                }
            )
        return rows

    def _read_metric_events(self) -> tuple[list[dict[str, Any]], bool]:
        """Read-only pass over the scheduler metrics logs. The producer
        writes seq/at/event/run_id plus event fields such as attempt_id
        (metrics.py append_event); records carry no job or task reference.
        Returns the parsed events (oldest first) and whether any metrics
        file was seen at all."""
        events: list[dict[str, Any]] = []
        seen = False
        metrics_dir = self.state_dir / "metrics" if self.state_dir else None
        paths: list[Path] = []
        if metrics_dir is not None:
            try:
                paths = sorted(p for p in metrics_dir.glob("*.jsonl") if p.is_file())
            except OSError:
                paths = []
        for path in paths:
            seen = True
            records, _ = read_jsonl(path)
            for record in records:
                if not isinstance(record, dict):
                    continue
                moment = parse_ts(first_str(record, ("at",)))
                if moment is None:
                    continue
                events.append(
                    {
                        "ts": moment,
                        "event": scrub(first_str(record, ("event",)), 40) or "",
                        "attempt_id": id_token(first_str(record, ("attempt_id",))),
                    }
                )
        events.sort(key=lambda item: item["ts"])
        return events, seen

    def _read_claim_store(self) -> tuple[int | None, int, bool]:
        """Live claim records, as QueueStore.active() counts them: readable
        records under queue/ whose state is claimed or running. QueueStore
        refuses the whole store when any record cannot be read (an
        unreadable record may be an active claim), so one unreadable record
        makes the active count unknown rather than smaller; the caller
        records the refusal as one owner message, the way the reconciler
        records one queue:claims refusal. The count is informational: the
        reconciler reports it as features.active_claims and never adds it
        to the in-flight task it is the claim of. Returns (active count or
        None, unreadable record count, whether the store was seen)."""
        claims_dir = self.state_dir / "queue" if self.state_dir else None
        if claims_dir is None or not claims_dir.is_dir():
            return 0, 0, False
        try:
            paths = sorted(p for p in claims_dir.glob("*.json") if p.is_file())
        except OSError:
            return None, 0, True
        active = 0
        unreadable = 0
        for path in paths:
            data = read_json_dict(path)
            if data is None:
                unreadable += 1
                continue
            if data.get("state") in ACTIVE_CLAIM_STATES:
                active += 1
        if unreadable:
            return None, unreadable, True
        return active, unreadable, True

    def _approval_state(self, docs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Declared approval gates without a recorded decision file, the
        reconciler's own pending-approval rule. A gate stays in the waiting
        state by design even after its decision is recorded, so the recorded
        file at approvals/<job>.<gate>.json is what counts, never the gate
        state. Returns the pending count, per-job missing gate slugs,
        whether every check could be performed, and whether the source
        contributed."""
        approvals_dir = self.state_dir / "approvals" if self.state_dir else None
        per_doc: dict[str, set[str]] = {}
        pending = 0
        known = True
        declared = False
        for doc in docs:
            missing: set[str] = set()
            for gate in doc["gate_names"]:
                declared = True
                if approvals_dir is None:
                    known = False
                    continue
                path = approvals_dir / f"{doc['job_id']}.{_gate_slug(gate)}.json"
                try:
                    recorded = path.exists()
                except OSError:
                    known = False
                    continue
                if not recorded:
                    missing.add(_gate_slug(gate))
            if missing:
                per_doc[doc["job_id"]] = missing
                pending += len(missing)
        source = False
        if approvals_dir is not None:
            try:
                source = approvals_dir.is_dir()
            except OSError:
                source = True
        source = source or declared
        return {"pending": pending, "per_doc": per_doc, "known": known, "source": source}

    # ------------------------------------------------------------- decisions
    @staticmethod
    def _decision_state(record: Mapping[str, Any]) -> str:
        """Map the queue's own state onto the consumer's fixed vocabulary.

        The consumer knows pending, approved, denied, applied and unknown. A
        final answer is approved or denied by its outcome, an applied request
        is applied, and a withdrawal has no consumer equivalent, so it stays
        unknown rather than being presented as an approval or a denial."""
        if record["withdrawn"] is not None:
            return "unknown"
        if record["applied"] is not None:
            return "applied"
        decision = record["decision"]
        if decision is not None:
            outcome = decision.get("outcome")
            if outcome == "approve":
                return "approved"
            if outcome == "deny":
                return "denied"
            return "unknown"
        return "pending"

    @staticmethod
    def _decision_kind(kind: Any) -> str:
        """Keep only the four recognized queue kinds; anything else is unknown."""
        return kind if kind in DECISION_KINDS else "unknown"

    def _read_decision_record(
        self, path: Path
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Read one ``<state>/decisions/<request_id>.json`` queue record.

        The on-disk shape is the one decision_queue.py writes: the sealed
        request, the final decision, the recorded deferrals, the applied
        marker and the withdrawn marker. A record that cannot be read or does
        not have that shape is refused with a precise code; the caller skips
        it and never turns it into a fabricated request."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None, "decision_record_unreadable"
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return None, "decision_record_malformed"
        if not isinstance(data, dict):
            return None, "decision_record_malformed"
        if set(data) != {"request", "decision", "defers", "applied", "withdrawn"}:
            return None, "decision_record_malformed"
        if not isinstance(data["defers"], list):
            return None, "decision_record_malformed"
        for marker in ("decision", "applied", "withdrawn"):
            if data[marker] is not None and not isinstance(data[marker], dict):
                return None, "decision_record_malformed"
        request = data["request"]
        if not isinstance(request, dict):
            return None, "decision_record_malformed"
        if request.get("schema") != OWNER_DECISION_SCHEMA:
            return None, "decision_record_malformed"
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or request_id != path.stem:
            return None, "decision_record_malformed"
        if ID_TOKEN_RE.match(request_id) is None:
            return None, "decision_record_malformed"
        kind = request.get("kind")
        if not isinstance(kind, str) or not kind:
            return None, "decision_record_malformed"
        subject = request.get("subject")
        if not isinstance(subject, str) or ID_TOKEN_RE.match(subject) is None:
            return None, "decision_record_malformed"
        question = request.get("question")
        if not isinstance(question, str) or not 1 <= len(question) <= 400:
            return None, "decision_record_malformed"
        if parse_ts(request.get("raised_at")) is None:
            return None, "decision_record_malformed"
        decision = data["decision"]
        if decision is not None:
            if decision.get("outcome") not in ("approve", "deny"):
                return None, "decision_record_malformed"
            if parse_ts(decision.get("decided_at")) is None:
                return None, "decision_record_malformed"
        applied = data["applied"]
        if applied is not None and parse_ts(applied.get("applied_at")) is None:
            return None, "decision_record_malformed"
        return data, None

    def decisions_section(self) -> dict[str, Any]:
        """The owner-decision queue (rizzstack.owner-decision/1) as a section.

        Requests are read from the queue's own durable files under
        ``<state-dir>/decisions`` and mapped onto the consumer's fixed
        vocabulary: ``requests`` (never ``records``), consumer state words,
        and the request id, kind, subject, question and queue timestamps the
        queue stores. An absent decisions directory is a genuine zero: no
        request has been raised, so the section is live with an empty
        requests array. An unreadable directory is unavailable; an unreadable
        or malformed record is skipped and degrades the section with a
        precise error code, never a fake request.
        """
        now = self.now()
        generated = utc_now_string(now)
        requests: list[dict[str, Any]] = []
        status, error = "live", None
        newest: datetime | None = None
        if self.state_dir is None:
            status, error = "unavailable", "source_missing"
        else:
            directory = self.state_dir / "decisions"
            if not directory.exists():
                # No request has been raised yet: a genuine zero, not unknown.
                pass
            elif not directory.is_dir():
                status, error = "unavailable", "decisions_unreadable"
            else:
                try:
                    paths = sorted(
                        p
                        for p in directory.glob("*.json")
                        if not p.name.startswith(".") and p.is_file()
                    )
                except OSError:
                    paths = []
                    status, error = "unavailable", "decisions_unreadable"
                malformed_error: str | None = None
                for path in paths:
                    record, code = self._read_decision_record(path)
                    if record is None:
                        malformed_error = malformed_error or code
                        continue
                    request = record["request"]
                    decision = record["decision"]
                    applied = record["applied"]
                    requests.append(
                        {
                            "request_id": request["request_id"],
                            "state": self._decision_state(record),
                            "kind": self._decision_kind(request["kind"]),
                            "subject": request["subject"],
                            "question": request["question"],
                            "generated_at": generated,
                            "raised_at": request["raised_at"],
                            "decided_at": decision["decided_at"] if decision else None,
                            "applied_at": applied["applied_at"] if applied else None,
                        }
                    )
                    raised = parse_ts(request["raised_at"])
                    if raised is not None and (newest is None or raised > newest):
                        newest = raised
                if malformed_error is not None:
                    status, error = "unavailable", malformed_error
                elif newest is not None:
                    age = int((now - newest).total_seconds())
                    if age > self.stale_after_s:
                        status, error = "stale", "decisions_older_than_threshold"
        return {
            "status": status,
            "error": error,
            "collected_at": generated,
            "requests": requests,
        }

    def bottlenecks_section(
        self,
        *,
        pipeline_body: Mapping[str, Any],
        backlog_body: Mapping[str, Any],
        ci_body: Mapping[str, Any],
        fleet_body: Mapping[str, Any],
        fleet_bee_cap: int | None = None,
    ) -> dict[str, Any]:
        """Compute the bottlenecks section read-only from records the other
        sections already read: job documents, the feature queue, the claim
        store, recorded approval decisions, review reports, scheduler
        metrics, the fleet, and open pull requests. Each contributing source
        degrades independently: a metric its source cannot show stays null
        with a status marker, never zero. The fleet section no longer
        surfaces the CLI status bee_cap (it is launcher configuration, not
        an observed fleet fact), so the caller passes it separately; the
        verify stage's WIP-versus-capacity row keeps deriving from it."""
        now = self.now()
        generated = utc_now_string(now)
        docs, unreadable_jobs = self._read_job_documents()
        reports = self._read_verify_reports()
        events, metrics_seen = self._read_metric_events()
        approval_state = self._approval_state(docs)

        pipeline_readable = pipeline_body.get("status") != "unavailable"
        queue_readable = backlog_body.get("status") != "unavailable"
        ci_readable = ci_body.get("status") != "unavailable"
        features = [f for f in as_list(backlog_body.get("features")) if isinstance(f, dict)]
        docs_by_id = {doc["job_id"]: doc for doc in docs}

        transitions: dict[tuple[str, str], list[tuple[datetime, str]]] = {}
        for doc in docs:
            for moment, task_id, to_state in doc["events"]:
                transitions.setdefault((doc["job_id"], task_id), []).append((moment, to_state))
        for rows in transitions.values():
            rows.sort(key=lambda item: item[0])

        # Verify records join to tasks through the task's attempt-id list;
        # the newest record per attempt wins, as the record file is rewritten
        # on a resumed verify.
        report_by_attempt: dict[str, dict[str, Any]] = {}
        for report in reports:
            attempt_id = report["attempt_id"]
            if not attempt_id:
                continue
            known = report_by_attempt.get(attempt_id)
            if known is None or (report["at"] is not None and (known["at"] is None or report["at"] > known["at"])):
                report_by_attempt[attempt_id] = report

        # Scheduler dispatch records date an attempt's start; the earliest
        # dispatch of an attempt is the one that started it.
        dispatch_by_attempt: dict[str, datetime] = {}
        for event in events:
            attempt_id = event["attempt_id"]
            if event["event"] != "dispatch" or not attempt_id:
                continue
            known = dispatch_by_attempt.get(attempt_id)
            if known is None or event["ts"] < known:
                dispatch_by_attempt[attempt_id] = event["ts"]

        targets: dict[str, float | None] = {}
        for stage in STAGE_NAMES:
            value = self.thresholds.get(stage + "_dwell_target_s")
            targets[stage] = (
                float(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else None
            )

        total_tasks = sum(len(doc["tasks"]) for doc in docs)
        raw_events = sum(doc["raw_events"] for doc in docs)
        parsed_events = sum(len(doc["events"]) for doc in docs)
        if not pipeline_readable:
            event_status = "unavailable"
        elif total_tasks > 0 and parsed_events == 0:
            event_status = "unknown"
        elif parsed_events < raw_events:
            event_status = "partial"
        else:
            event_status = "known"

        stages = [
            self._verify_stage_row(
                now, generated, docs, transitions, dispatch_by_attempt, fleet_body,
                targets["verify"], pipeline_readable, event_status, fleet_bee_cap,
            ),
            self._review_stage_row(
                now, generated, features, docs_by_id, report_by_attempt,
                queue_readable, targets["review"],
            ),
            self._integrate_stage_row(
                now, generated, docs, transitions, report_by_attempt,
                dispatch_by_attempt, pipeline_readable, targets["integrate"], event_status,
            ),
            self._deploy_stage_row(now, generated, ci_body, ci_readable, targets["deploy"]),
        ]
        invariant = self._bottleneck_invariant(
            now,
            generated,
            features=features,
            queue_readable=queue_readable,
            docs=docs,
            unreadable_jobs=unreadable_jobs,
            pipeline_readable=pipeline_readable,
            ci_body=ci_body,
            ci_readable=ci_readable,
            events=events,
            metrics_seen=metrics_seen,
            report_by_attempt=report_by_attempt,
            approval_state=approval_state,
        )

        readable = [
            pipeline_readable,
            queue_readable,
            ci_readable,
            fleet_body.get("status") != "unavailable",
            metrics_seen,
        ]
        if not any(readable):
            status, error = "unavailable", "no_bottleneck_sources"
        else:
            live_flags = [
                pipeline_body.get("status") == "live",
                backlog_body.get("status") == "live",
                ci_body.get("status") == "live",
                fleet_body.get("status") == "live",
            ]
            if events:
                newest = events[-1]["ts"]
                if (now - newest) <= timedelta(seconds=self.stale_after_s):
                    live_flags.append(True)
            if any(live_flags):
                status, error = "live", None
            else:
                status, error = "stale", "bottleneck_sources_older_than_threshold"
        return section(
            now,
            status,
            error,
            stages=stages,
            invariant=invariant,
            thresholds={stage: {"dwell_target_s": targets[stage]} for stage in STAGE_NAMES},
        )

    def _verify_stage_row(
        self,
        now: datetime,
        generated: str,
        docs: Sequence[Mapping[str, Any]],
        transitions: Mapping[tuple[str, str], Sequence[tuple[datetime, str]]],
        dispatch_by_attempt: Mapping[str, datetime],
        fleet_body: Mapping[str, Any],
        target: float | None,
        source_readable: bool,
        event_status: str,
        fleet_bee_cap: int | None = None,
    ) -> dict[str, Any]:
        open_count = 0
        entries: list[datetime] = []
        stays: list[float] = []
        advances: list[datetime] = []
        for doc in docs:
            for task in doc["tasks"]:
                rows = transitions.get((doc["job_id"], task["task_id"]), [])
                open_entry, task_stays, task_advances = _stage_walk(
                    rows, VERIFY_ENTRY_STATES, VERIFY_MEMBER_STATES, VERIFY_ADVANCE_STATES
                )
                stays.extend(task_stays)
                advances.extend(task_advances)
                if source_readable and task["state"] == "verifying":
                    open_count += 1
                    entry = open_entry
                    if entry is None:
                        # No recorded transition into verifying: the
                        # scheduler dispatch record of the task's newest
                        # attempt dates the entry. No record means unknown.
                        dispatched = [
                            dispatch_by_attempt[attempt_id]
                            for attempt_id in task["attempt_ids"]
                            if attempt_id in dispatch_by_attempt
                        ]
                        if dispatched:
                            entry = max(dispatched)
                    if entry is not None:
                        entries.append(entry)
        oldest = min(entries) if entries else None
        wip = None
        capacity = None
        capacity_source = None
        if fleet_body.get("status") != "unavailable":
            wip = sum(
                1
                for row in as_list(fleet_body.get("attempts"))
                if isinstance(row, dict) and row.get("state") in WORKING_FLEET_STATES
            )
            cap = fleet_body.get("bee_cap")
            if not (isinstance(cap, int) and not isinstance(cap, bool) and cap >= 1):
                # The fleet section no longer surfaces the CLI status bee_cap;
                # the caller passes it through separately instead.
                cap = fleet_bee_cap
            if isinstance(cap, int) and not isinstance(cap, bool) and cap >= 1:
                capacity = cap
                capacity_source = "bee_cap"
        return _stage_row(
            generated,
            "verify",
            now=now,
            queue_depth=open_count if source_readable else None,
            oldest_item_age_s=_age_s(oldest, now),
            dwell_samples=stays,
            dwell_status="known" if (stays and source_readable) else ("unknown" if source_readable else "unavailable"),
            advanced=advances,
            throughput_status=event_status,
            wip=wip,
            capacity=capacity,
            capacity_source=capacity_source,
            target=target,
        )

    def _review_stage_row(
        self,
        now: datetime,
        generated: str,
        features: Sequence[Mapping[str, Any]],
        docs_by_id: Mapping[str, Mapping[str, Any]],
        report_by_attempt: Mapping[str, Mapping[str, Any]],
        source_readable: bool,
        target: float | None,
    ) -> dict[str, Any]:
        if not source_readable:
            return _stage_row(
                generated,
                "review",
                now=now,
                queue_depth=None,
                oldest_item_age_s=None,
                dwell_samples=[],
                dwell_status="unavailable",
                advanced=[],
                throughput_status="unavailable",
                wip=None,
                capacity=None,
                capacity_source=None,
                target=target,
            )
        waiting = [f for f in features if f.get("status") == "ready_for_review"]
        ready_at: list[datetime] = []
        for feature in waiting:
            job_id = feature.get("job_id")
            doc = docs_by_id.get(job_id) if isinstance(job_id, str) else None
            if doc is None:
                continue
            candidates: list[datetime] = []
            for task in doc["tasks"]:
                for attempt_id in task["attempt_ids"]:
                    report = report_by_attempt.get(attempt_id)
                    # A passing verify record is when the work became
                    # reviewable; a failed one is not a completion.
                    if report is not None and report["ok"] is True and report["at"] is not None:
                        candidates.append(report["at"])
            if candidates:
                ready_at.append(max(candidates))
        oldest = min(ready_at) if ready_at else None
        # The queue snapshot carries no record of completed review stays or
        # of items leaving review, so dwell and throughput stay unknown.
        return _stage_row(
            generated,
            "review",
            now=now,
            queue_depth=len(waiting),
            oldest_item_age_s=_age_s(oldest, now),
            dwell_samples=[],
            dwell_status="unknown",
            advanced=[],
            throughput_status="unknown",
            wip=None,
            capacity=None,
            capacity_source=None,
            target=target,
        )

    def _integrate_stage_row(
        self,
        now: datetime,
        generated: str,
        docs: Sequence[Mapping[str, Any]],
        transitions: Mapping[tuple[str, str], Sequence[tuple[datetime, str]]],
        report_by_attempt: Mapping[str, Mapping[str, Any]],
        dispatch_by_attempt: Mapping[str, datetime],
        source_readable: bool,
        target: float | None,
        event_status: str,
    ) -> dict[str, Any]:
        open_count = 0
        entries: list[datetime] = []
        stays: list[float] = []
        advances: list[datetime] = []
        for doc in docs:
            for task in doc["tasks"]:
                rows = transitions.get((doc["job_id"], task["task_id"]), [])
                open_entry, task_stays, task_advances = _stage_walk(
                    rows, INTEGRATE_ENTRY_STATES, INTEGRATE_MEMBER_STATES, INTEGRATE_ADVANCE_STATES
                )
                stays.extend(task_stays)
                advances.extend(task_advances)
                if source_readable and task["state"] in INTEGRATE_QUEUE_STATES:
                    open_count += 1
                    entry = open_entry
                    if entry is None:
                        passed = [
                            report_by_attempt[attempt_id]["at"]
                            for attempt_id in task["attempt_ids"]
                            if attempt_id in report_by_attempt
                            and report_by_attempt[attempt_id]["ok"] is True
                            and report_by_attempt[attempt_id]["at"] is not None
                        ]
                        if passed:
                            entry = max(passed)
                    if entry is None:
                        dispatched = [
                            dispatch_by_attempt[attempt_id]
                            for attempt_id in task["attempt_ids"]
                            if attempt_id in dispatch_by_attempt
                        ]
                        if dispatched:
                            entry = max(dispatched)
                    if entry is not None:
                        entries.append(entry)
        oldest = min(entries) if entries else None
        return _stage_row(
            generated,
            "integrate",
            now=now,
            queue_depth=open_count if source_readable else None,
            oldest_item_age_s=_age_s(oldest, now),
            dwell_samples=stays,
            dwell_status="known" if (stays and source_readable) else ("unknown" if source_readable else "unavailable"),
            advanced=advances,
            throughput_status=event_status,
            wip=None,
            capacity=None,
            capacity_source=None,
            target=target,
        )

    def _deploy_stage_row(
        self,
        now: datetime,
        generated: str,
        ci_body: Mapping[str, Any],
        source_readable: bool,
        target: float | None,
    ) -> dict[str, Any]:
        rows = [pr for pr in as_list(ci_body.get("prs")) if isinstance(pr, dict)]
        if not source_readable:
            return _stage_row(
                generated,
                "deploy",
                now=now,
                queue_depth=None,
                oldest_item_age_s=None,
                dwell_samples=[],
                dwell_status="unavailable",
                advanced=[],
                throughput_status="unavailable",
                wip=None,
                capacity=None,
                capacity_source=None,
                target=target,
            )
        opened = [
            moment
            for moment in (parse_ts(pr.get("created_at")) for pr in rows)
            if moment is not None
        ]
        oldest = min(opened) if opened else None
        # Open pull requests carry no record here of completed stays or of
        # merges, so dwell and throughput stay unknown.
        return _stage_row(
            generated,
            "deploy",
            now=now,
            queue_depth=len(rows),
            oldest_item_age_s=_age_s(oldest, now),
            dwell_samples=[],
            dwell_status="unknown",
            advanced=[],
            throughput_status="unknown",
            wip=None,
            capacity=None,
            capacity_source=None,
            target=target,
        )

    def _done_features(
        self,
        features: Sequence[Mapping[str, Any]],
        docs_by_id: Mapping[str, Mapping[str, Any]],
        report_by_attempt: Mapping[str, Mapping[str, Any]],
    ) -> set[str]:
        """Features whose linked job is accepted, mirroring the queue's own
        acceptance check: every task accepted with a passing verify record
        for its last attempt, and an accepted integration wave naming an
        integrated commit. A job that fails the check is a computed no, not
        an unknown; a feature without a linked job is simply not done."""
        done: set[str] = set()
        for feature in features:
            job_id = feature.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                continue
            doc = docs_by_id.get(job_id)
            if doc is None:
                continue
            if self._job_acceptable(doc, report_by_attempt):
                feature_id = feature.get("feature_id")
                if isinstance(feature_id, str) and feature_id:
                    done.add(feature_id)
        return done

    def _job_acceptable(
        self,
        doc: Mapping[str, Any],
        report_by_attempt: Mapping[str, Mapping[str, Any]],
    ) -> bool:
        """The queue's job-acceptance check, read-only: all tasks accepted,
        each with a passing verify record for its last attempt (record ok,
        commit sha, scan and suite exits, and any recorded binding matches),
        and an accepted integration wave naming a commit."""
        tasks = doc["tasks"]
        if not tasks:
            return False
        for task in tasks:
            if task["state"] != "accepted":
                return False
            attempt_ids = task["attempt_ids"]
            if not attempt_ids:
                return False
            record = report_by_attempt.get(attempt_ids[-1])
            if record is None or record["ok"] is not True or not record["sha"]:
                return False
            binding = task["binding"]
            if binding.get("source_rev") and str(record["base_rev"]) != str(binding["source_rev"]):
                return False
            if binding.get("contract_sha256") and str(task["contract_sha256"] or "") != str(
                binding["contract_sha256"]
            ):
                return False
            if record["gitleaks_exit"] != 0:
                return False
            if record["suite_exit"] != 0:
                return False
        integration = doc["integration"]
        waves = [wave for wave in as_list(integration.get("accepted_waves")) if isinstance(wave, dict)]
        if not waves:
            return False
        last_commit = first_str(integration, ("last_commit",)) or first_str(waves[-1], ("commit",))
        if not last_commit:
            return False
        return True

    def _bottleneck_invariant(
        self,
        now: datetime,
        generated: str,
        *,
        features: Sequence[Mapping[str, Any]],
        queue_readable: bool,
        docs: Sequence[Mapping[str, Any]],
        unreadable_jobs: int,
        pipeline_readable: bool,
        ci_body: Mapping[str, Any],
        ci_readable: bool,
        events: Sequence[Mapping[str, Any]],
        metrics_seen: bool,
        report_by_attempt: Mapping[str, Mapping[str, Any]],
        approval_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """The coordinator reconciler's invariant (reconcile.py):
        in_use is claimed plus active workers plus tasks awaiting
        verification, available is the work scheduler's max-active minus
        in_use, owner messages are pending approvals plus blocked items,
        and advancement is expected when ready work, available capacity and
        zero owner messages coincide. claimed counts tasks in the
        dispatching/dispatched states exactly as the reconciler counts
        them; live claim records are reported separately as active_claims
        (the reconciler's features.active_claims), never added to the task
        they are the claim of. The blocked set covers what the reconciler
        blocks and this collector's own sources can show: terminal task
        states, integration-terminal and evidence-incomplete jobs, unknown
        task states, unreadable jobs, and the claim store refused whole.
        Two reconciler causes are out of this reader's scope and declared
        in the README: campaign-checkpoint blockers and an unreadable
        scheduler queue. Dependency-blocked queue features are not owner
        messages (they advance when their dependency completes). Every
        count comes from the real record of its kind; a record the
        collector cannot read leaves the headline unknown, never a guessed
        answer."""
        docs_by_id = {doc["job_id"]: doc for doc in docs}
        tasks = [task for doc in docs for task in doc["tasks"]]

        active_claims, claims_unreadable, claims_dir_seen = self._read_claim_store()
        claims_known = active_claims is not None
        done = self._done_features(features, docs_by_id, report_by_attempt) if queue_readable else set()

        ready = None
        total_outstanding = None
        awaiting_review = None
        blocked_reasons: dict[str, int] = {}

        def note_blocked(reason: str) -> None:
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1

        if claims_unreadable:
            # QueueStore.active() refuses the whole store when any record
            # cannot be read; one refusal, the reconciler's queue:claims
            # entry, not one message per unreadable record.
            note_blocked("queue_claims_unreadable")

        if queue_readable:
            ready = 0
            for feature in features:
                feature_id = feature.get("feature_id")
                if feature.get("status") != "queued" or not isinstance(feature_id, str) or not feature_id:
                    continue
                if feature_id in done:
                    continue
                deps = [dep for dep in as_list(feature.get("depends_on")) if isinstance(dep, str)]
                if all(dep in done for dep in deps):
                    ready += 1
            total_outstanding = sum(
                1 for f in features if f.get("status") in NON_TERMINAL_QUEUE_STATUSES
            )
            awaiting_review = sum(1 for f in features if f.get("status") == "ready_for_review")
            # A blocked queue feature is not an owner message: approval and
            # task causes are already counted at their source, and a
            # dependency-blocked feature advances when its dependency
            # completes, exactly as the reconciler treats it.
        elif pipeline_readable:
            total_outstanding = sum(
                1 for task in tasks if task["state"] in NON_TERMINAL_TASK_STATES
            )
        if pipeline_readable:
            for doc in docs:
                for task in doc["tasks"]:
                    if task["blocker"]:
                        note_blocked(task["blocker"])
                    elif task["state"] is None:
                        note_blocked("task_state_unknown")
                integration = doc["integration"]
                if integration.get("terminal"):
                    note_blocked("integration_terminal")
                elif doc["tasks"] and all(task["state"] == "accepted" for task in doc["tasks"]):
                    if not self._job_acceptable(doc, report_by_attempt):
                        note_blocked("job_evidence_incomplete")
        for _ in range(unreadable_jobs):
            note_blocked("job_unreadable")

        awaiting_verify = awaiting_integrate = None
        active_workers = None
        claimed = None
        if pipeline_readable:
            awaiting_verify = sum(1 for task in tasks if task["state"] == "verifying")
            awaiting_integrate = sum(
                1 for task in tasks if task["state"] in INTEGRATE_QUEUE_STATES
            )
            active_workers = sum(1 for task in tasks if task["state"] == "running")
            claimed = sum(1 for task in tasks if task["state"] in CLAIMED_TASK_STATES)

        awaiting_deploy = None
        if ci_readable:
            awaiting_deploy = sum(
                1 for pr in as_list(ci_body.get("prs")) if isinstance(pr, dict)
            )

        blocked_known = queue_readable and pipeline_readable
        # An unreadable claim store is itself a known one-message refusal,
        # so it does not make the owner-message count unknown.
        owner_messages_known = approval_state["known"] and blocked_known
        owner_messages = approval_state["pending"] + sum(blocked_reasons.values())

        in_use = None
        available = None
        waiting_despite = None
        waiting_count = None
        if ready is not None and pipeline_readable and owner_messages_known:
            in_use = (claimed or 0) + (active_workers or 0) + (awaiting_verify or 0)
            available = max(0, SCHEDULER_MAX_ACTIVE - in_use)
            advancement = ready > 0 and available > 0 and owner_messages == 0
            waiting_despite = advancement
            waiting_count = ready if advancement else 0

        last_auto_at = None
        for doc in docs:
            for moment, _task_id, to_state in doc["events"]:
                if to_state in AUTOMATIC_PROGRESS_STATES and (
                    last_auto_at is None or moment > last_auto_at
                ):
                    last_auto_at = moment
        for event in events:
            if event["event"] in METRIC_AUTO_EVENTS and (
                last_auto_at is None or event["ts"] > last_auto_at
            ):
                last_auto_at = event["ts"]

        gaps = [gap for doc in docs for gap in doc["latency_gaps"]]
        if not pipeline_readable:
            gap_status = "unavailable"
        elif gaps:
            gap_status = "known"
        else:
            gap_status = "unknown"

        sources = [
            queue_readable,
            pipeline_readable,
            ci_readable,
            metrics_seen,
            claims_dir_seen,
            approval_state["source"],
        ]
        if not any(sources):
            invariant_status = "unavailable"
        elif all(sources):
            invariant_status = "known"
        else:
            invariant_status = "partial"

        return {
            "schema": SCHEMA,
            "generated_at": generated,
            "status": invariant_status,
            "total_outstanding": total_outstanding,
            "ready": ready,
            "ready_waiting_despite_capacity": waiting_count,
            "waiting_despite_capacity": waiting_despite,
            "claimed": claimed,
            "active_claims": active_claims,
            "active_workers": active_workers,
            "awaiting_verify": awaiting_verify,
            "awaiting_review": awaiting_review,
            "awaiting_integrate": awaiting_integrate,
            "awaiting_deploy": awaiting_deploy,
            "capacity": {
                "max_active": SCHEDULER_MAX_ACTIVE,
                "in_use": in_use,
                "available": available,
            },
            "blocked_with_reason": sum(blocked_reasons.values()),
            "blocked_reasons": blocked_reasons,
            "human_approvals_required": approval_state["pending"],
            "last_auto_progress_at": (
                last_auto_at.strftime("%Y-%m-%dT%H:%M:%SZ") if last_auto_at else None
            ),
            "last_auto_progress_age_s": _age_s(last_auto_at, now),
            "completion_to_next_action_median_s": _median_of(gaps),
            "completion_to_next_action_p95_s": _p95_of(gaps),
            "completion_to_next_action_status": gap_status,
        }

    # ---------------------------------------------------------------- health
    def health_section(
        self,
        fleet_body: Mapping[str, Any],
        usage_summary: Mapping[str, Any],
        fleet_bee_cap: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """Returns (section, observations) — observations feed alerts.

        The fleet section no longer surfaces the CLI status bee_cap (it is
        launcher configuration, not an observed fleet fact), so the caller
        passes it separately: the bees_in_flight quota row still derives its
        cap and remaining headroom from it."""
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
        if not (isinstance(bee_cap, int) and not isinstance(bee_cap, bool) and bee_cap >= 1):
            # The fleet section no longer surfaces the CLI status bee_cap;
            # the caller passes it through separately instead.
            bee_cap = fleet_bee_cap
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
            "today_cost_usd": float(usage_summary["today_cost_usd"])
            if usage_summary.get("today_known") and isinstance(usage_summary.get("today_cost_usd"), (int, float))
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
                f"today's reported list-price subtotal is {today_cost:.2f} USD",
            )
        status = "live" if any_live_input else "unavailable"
        error = None if any_live_input else "no_live_inputs"
        return section(now, status, error, active=active)

    # -------------------------------------------------------------- assembly
    def build_snapshot(self) -> dict[str, Any]:
        now = self.now()
        generated = utc_now_string(now)

        def local_and_ci() -> tuple[Any, ...]:
            usage, usage_summary = self.usage_section()
            pipeline, blockers = self.pipeline_section()
            backlog = self.backlog_section()
            ci = self.ci_section(pipeline.get("jobs", []))
            failures = self.failures_section()
            decisions = self.decisions_section()
            return usage, usage_summary, pipeline, blockers, backlog, ci, failures, decisions

        # The fleet CLI reads dominate a cold snapshot; they run alongside the
        # file reads and the gh reads instead of before them.
        fleet_result, rest = self._parallel([self.fleet_section, local_and_ci])
        fleet, in_flight, bee_cap = fleet_result
        usage, usage_summary, pipeline, blockers, backlog, ci, failures, decisions = rest
        bottlenecks = self.bottlenecks_section(
            pipeline_body=pipeline,
            backlog_body=backlog,
            ci_body=ci,
            fleet_body=fleet,
            fleet_bee_cap=bee_cap,
        )
        health, observations = self.health_section(fleet, usage_summary, fleet_bee_cap=bee_cap)
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
            "bottlenecks": bottlenecks,
            "decisions": decisions,
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


def _gate_slug(value: str) -> str:
    """The decision-file name for a gate, as the job writer slugs it."""
    text = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)


def _infer_failure_class(outcome_norm: str, code: str | None) -> str:
    haystack = f"{outcome_norm} {code or ''}".lower()
    for needle, cls in FAILURE_CLASS_HINTS:
        if needle in haystack:
            return cls
    if "suite" in haystack or "test" in haystack or "verify" in haystack:
        return "regression"
    return "unknown"


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
            if self.path not in ("/", "/snapshot", "/obs-snapshot"):
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
    parser.add_argument("--cli-workers", type=int, default=8, help="concurrent read-only CLI reads (1 = sequential)")
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
        cli_workers=args.cli_workers,
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
