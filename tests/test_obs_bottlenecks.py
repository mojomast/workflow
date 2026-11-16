"""Tests for the bottlenecks section of the rizzstack observability snapshot.

The bottlenecks section answers one question for the dashboard: where is
work piling up? Per pipeline stage (verify, review, integrate, deploy) it
carries queue depth, oldest-item age, dwell-time median and p95, throughput
over the last hour and last day, and WIP versus capacity where a cap exists.
It also carries the reconciliation headline: the coordinator reconciler's
invariant of eligible work waiting despite available scheduler capacity.

Everything is computed read-only from records whose shapes are the ones the
producers actually write. Fixtures below copy those shapes from the
bundlebees writers: job events are documents with at/task_id/transition/
actor/reason where transition is the from->to string (job.py transition),
task attempts are lists of attempt-id strings (reconcile.py), verify
results carry attempt_id/ok/sha/branch/files/tests/at/evidence with no job
or task reference (cli.py verify writer, plus the commit-local record shape
from verify_local), metrics records carry seq/at/event/run_id plus event
fields with a chained prev_sha256 (metrics.py append_event), the feature
queue file is one flat object keyed by feature id (queue.py FileQueue), the
claim store is one record per feature under queue/ (QueueStore.claim), and
approval decisions live at approvals/<job>.<gate>.json (job.py
record_approval). A missing source degrades to null with a status marker,
never to zero. Dwell targets are configuration, not constants.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))

from validate import SchemaError, Validator  # noqa: E402

SNAPSHOT_SCHEMA = "snapshot.schema.json"

FIXED_NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
FIXED_EPOCH = FIXED_NOW.timestamp()

HEX_A = "5f4e3d2c1b0a9f8e7d6c5b4a39281706f5e4d3c2"
HEX_B = "0a1b2c3d4e5f60718a9b0cad1e2f3a4b5c6d7e8f"
HEX_C = "1a2b3c4d5e6f70819a2b3c4d5e6f70819a2b3c4d"
DIGEST_A = "ab" * 32
ZERO_DIGEST = "0" * 64

STAGE_NAMES = ("verify", "review", "integrate", "deploy")

DEFAULT_TARGETS = {"verify": 3600, "review": 14400, "integrate": 7200, "deploy": 86400}


def load_collector_module():
    spec = importlib.util.spec_from_file_location(
        "rizzstack_obs_collector_bottlenecks",
        ROOT / "contrib" / "rizzstack-observability" / "collector.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_collector_module()
VALIDATOR = Validator(ROOT / "observability" / "schemas")


def validated(doc) -> None:
    VALIDATOR.validate(doc, VALIDATOR.load(SNAPSHOT_SCHEMA))


def at(minute: int, second: int = 0) -> str:
    """Timestamp on the fixture day, 10:00 + offset minutes."""
    moment = FIXED_NOW.replace(hour=10, minute=0, second=0) + timedelta(minutes=minute, seconds=second)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------- real-shaped fixtures


def event_row(task_id: str, transition: str, moment: str) -> dict:
    """Job event in the shape bundlebees job.py transition() appends."""
    return {
        "at": moment,
        "task_id": task_id,
        "transition": transition,
        "actor": "reconciler",
        "reason": "",
    }


def task_row(task_id: str, state: str, attempts: tuple[str, ...] = (), depends: tuple[str, ...] = ()) -> dict:
    """Task in the shape the job writer stores: attempts are attempt-id
    strings, as reconcile.py appends them."""
    return {
        "task_id": task_id,
        "state": state,
        "attempts": list(attempts),
        "depends_on": list(depends),
        "intent": None,
    }


def job_document(
    job_id: str,
    repo: str,
    tasks: list[dict],
    events: list[dict],
    gates: tuple[str, ...] = ("merge",),
    integration: dict | None = None,
) -> dict:
    """Job document in the shape the bundlebees job writer saves: the
    approval gate declares its gate names and starts in the waiting state."""
    return {
        "job_id": job_id,
        "goal": {"repo": repo, "base_rev": HEX_A},
        "tasks": tasks,
        "integration": integration or {"wave": "w1", "state": "pending", "evidence": None},
        "approval_gate": {"required": True, "gates": list(gates), "state": "waiting"},
        "escalations": [],
        "events": events,
    }


def write_job_document(state: Path, doc: dict) -> None:
    (state / "jobs" / f"{doc['job_id']}.json").write_text(json.dumps(doc), encoding="utf-8")


def verify_record_slim(attempt_id: str, moment: str, ok: bool = True) -> dict:
    """Verify result in the shape the bundlebees cli.py verify writer writes:
    attempt_id/ok/sha/branch/files/tests/at/evidence and no job or task
    reference."""
    return {
        "attempt_id": attempt_id,
        "ok": ok,
        "sha": HEX_B if ok else None,
        "branch": "bb-verify/" + attempt_id,
        "files": ["contrib/rizzstack-observability/collector.py"],
        "tests": ["tests/test_obs_bottlenecks.py"],
        "at": moment,
        "evidence": {"source_rev": HEX_A},
    }


def verify_record_commit_local(attempt_id: str, moment: str) -> dict:
    """Verify result in the shape the bundlebees verify_local commit-local
    writer records, with the suite and scan outcomes the queue's acceptance
    check reads."""
    return {
        "attempt_id": attempt_id,
        "ok": True,
        "sha": HEX_C,
        "branch": "bb-verify/" + attempt_id,
        "base_rev": HEX_A,
        "files": ["contrib/rizzstack-observability/collector.py"],
        "tests": ["tests/test_obs_bottlenecks.py"],
        "red": {"exit_code": 1, "timed_out": False},
        "suite": {"exit_code": 0, "timed_out": False},
        "gitleaks": {"exit_code": 0},
        "mode": "commit-local",
        "patch_sha256": DIGEST_A,
        "execution_identity": None,
        "resumed": False,
        "test_cache": {"executions": 1, "hits": 0, "misses": 1},
        "at": moment,
    }


def write_verify_record(state: Path, record: dict) -> None:
    (state / "verify-results" / f"{record['attempt_id']}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


def write_metrics(state: Path, entries: list[tuple[str, str, dict]], run: str = "run-1") -> None:
    """Metrics log in the shape metrics.py append_event writes: seq, at,
    event, run_id, allowed event fields, and prev_sha256 chaining the
    sha256 of the previous line (the first line chains the zero digest)."""
    lines: list[str] = []
    previous = ZERO_DIGEST
    for index, (event, moment, fields) in enumerate(entries, start=1):
        record = {"seq": index, "at": moment, "event": event, "run_id": run}
        record.update(fields)
        record["prev_sha256"] = previous
        line = json.dumps(record, sort_keys=True, separators=(",", ":"))
        lines.append(line)
        previous = hashlib.sha256(line.encode("utf-8")).hexdigest()
    (state / "metrics" / f"{run}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_queue(state: Path, features: dict) -> None:
    """Feature queue file in the shape the file-backed queue writes: one
    flat object keyed by feature id."""
    (state / "queue.json").write_text(json.dumps(features), encoding="utf-8")


def write_claim(state: Path, feature_id: str, job_id: str, moment: str) -> None:
    """Claim record in the shape QueueStore.claim writes under queue/."""
    record = {
        "feature_id": feature_id,
        "state": "claimed",
        "job_id": job_id,
        "claimed_at": moment,
        "pid": 4242,
    }
    (state / "queue" / f"{feature_id}.json").write_text(json.dumps(record), encoding="utf-8")


def write_grant(state: Path, job_id: str, gate: str, moment: str) -> None:
    """Decision file in the shape job.py record_approval writes: one
    create-only file per job and gate."""
    body = {
        "schema_version": 1,
        "kind": "approval",
        "job_id": job_id,
        "gate": gate,
        "decision": "granted",
        "statement": "recorded decision",
        "by": "operator",
        "at": moment,
    }
    (state / "approvals" / f"{job_id}.{gate}.json").write_text(json.dumps(body), encoding="utf-8")


# --------------------------------------------------------- main fixture state


def write_job_r1(state: Path) -> None:
    """One job with all stage traffic: a verifying task dated by its
    transition, a verified task awaiting the wave, an integrating task, and
    a task that travelled the whole path leaving dwell samples behind."""
    doc = job_document(
        "job_r1",
        "mojomast/workflow",
        tasks=[
            task_row("T1", "verifying", attempts=("a1",)),
            task_row("T2", "verified", attempts=("a2",)),
            task_row("T3", "accepted", attempts=("a3",)),
            task_row("T4", "integrating", attempts=("a4",)),
        ],
        events=[
            event_row("T3", "running->verifying", at(5)),
            event_row("T3", "verifying->verified", at(20)),
            event_row("T3", "verified->accepted", at(45)),
            event_row("T2", "verifying->verified", at(50)),
            event_row("T4", "running->verifying", at(60)),
            event_row("T4", "verifying->verified", at(80)),
            event_row("T4", "verified->integrating", at(100)),
            event_row("T1", "running->verifying", at(110)),
        ],
    )
    write_job_document(state, doc)


def write_job_r2(state: Path) -> None:
    """A second job with a running task and a gate whose decision has not
    been recorded: its approval stays pending until a grant file exists."""
    doc = job_document(
        "job_r2",
        "mojomast/bundlebees",
        tasks=[task_row("T1", "running", attempts=("b1",))],
        events=[],
    )
    write_job_document(state, doc)


MAIN_QUEUE = {
    "feat_alpha": {
        "repo": "mojomast/workflow",
        "job_id": "job_r1",
        "title": "alpha",
        "depends_on": [],
        "status": "ready_for_review",
    },
    "feat_beta": {
        "repo": "mojomast/workflow",
        "job_id": "",
        "title": "beta",
        "depends_on": [],
        "status": "queued",
    },
    "feat_gamma": {
        "repo": "mojomast/bundlebees",
        "job_id": "job_r2",
        "title": "gamma",
        "depends_on": [],
        "status": "claimed",
    },
    "feat_delta": {
        "repo": "mojomast/workflow",
        "job_id": "job_r1",
        "title": "delta",
        "depends_on": ["feat_alpha"],
        "status": "blocked",
    },
}


def write_main_verify_records(state: Path) -> None:
    write_verify_record(state, verify_record_slim("a2", at(50)))
    write_verify_record(state, verify_record_commit_local("a3", at(45)))
    write_verify_record(state, verify_record_slim("a4", at(80)))


def write_main_metrics(state: Path) -> None:
    write_metrics(
        state,
        [
            ("dispatch", at(0), {"attempt_id": "a3"}),
            ("verify", at(18), {"attempt_id": "a3", "ok": True}),
            ("dispatch", at(40), {"attempt_id": "a2"}),
            ("dispatch", at(95), {"attempt_id": "a1"}),
        ],
    )


def fleet_runner(argv):
    attempts = {
        "attempts": [
            {
                "attempt_id": "w1",
                "state": "working",
                "job_id": "job_r1",
                "task_id": "T1",
                "repo": "mojomast/workflow",
                "started_at": at(100),
                "updated_at": at(119),
            }
        ]
    }
    # argv-flip companion (bb CLI subcommands; wf#41): the fleet
    # attempts call now invokes the bare subcommand instead of op=attempts.
    if "attempts" in argv:
        return 0, json.dumps(attempts), ""
    return 0, json.dumps({"in_flight": 2, "bee_cap": 12}), ""


def gh_runner(argv):
    if "checks" in argv:
        return 0, json.dumps([]), ""
    repo = argv[argv.index("--repo") + 1]
    prs = []
    if repo == "mojomast/workflow":
        prs = [
            {
                "number": 21,
                "headRefName": "feat/alpha",
                "state": "OPEN",
                "createdAt": at(30),
                "statusCheckRollup": [{"name": "unit tests", "state": "SUCCESS"}],
            }
        ]
    return 0, json.dumps(prs), ""


def make_state(tmp_path: Path, *, with_queue: bool = True) -> Path:
    state = tmp_path / "state"
    for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
        (state / subdir).mkdir(parents=True, exist_ok=True)
    write_job_r1(state)
    write_job_r2(state)
    if with_queue:
        write_queue(state, MAIN_QUEUE)
        write_claim(state, "feat_gamma", "job_r2", at(0))
    write_main_verify_records(state)
    write_main_metrics(state)
    # job_r1's gate decision is recorded; job_r2's is not.
    write_grant(state, "job_r1", "merge", at(2))
    return state


def pin_mtimes(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (FIXED_EPOCH - 60, FIXED_EPOCH - 60))


def bottleneck_collector(tmp_path: Path, *, with_queue: bool = True, **overrides):
    state = make_state(tmp_path, with_queue=with_queue)
    pin_mtimes(tmp_path)
    defaults = dict(
        state_dir=state,
        fleet_runner=fleet_runner,
        gh_runner=gh_runner,
        now_fn=lambda: FIXED_NOW,
        stale_after_s=1800,
    )
    defaults.update(overrides)
    return collector.Collector(**defaults)


def bottlenecks_of(snapshot: dict) -> dict:
    return snapshot["bottlenecks"]


def stage_of(section: dict, stage: str) -> dict:
    rows = {row["stage"]: row for row in section["stages"]}
    assert set(rows) == set(STAGE_NAMES), rows
    return rows[stage]


# --------------------------------------------------------------------- schema


class TestBottlenecksSchema:
    def test_bottlenecks_is_optional_but_always_emitted(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        # Optional under the existing discriminator: documents emitted before
        # this section existed must keep validating. The collector still
        # always emits it.
        assert "bottlenecks" not in schema["required"]
        assert "bottlenecks" in schema["properties"]
        assert "bottlenecks" in schema["properties"]["degraded"]["items"]["enum"]
        snap = collector.Collector(now_fn=lambda: FIXED_NOW).build_snapshot()
        assert "bottlenecks" in snap

    def test_ci_pr_created_at_is_optional(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        required = schema["$defs"]["ci_pr"]["required"]
        assert "created_at" not in required
        assert "created_at" in schema["$defs"]["ci_pr"]["properties"]

    def test_base_snapshot_still_validates_against_head_schema(self, tmp_path: Path) -> None:
        # The review probe: a document emitted before this change (no
        # bottlenecks section, no ci created_at) must validate against the
        # head schema under the unchanged discriminator.
        snap = bottleneck_collector(tmp_path).build_snapshot()
        del snap["bottlenecks"]
        for pr in snap["ci"]["prs"]:
            pr.pop("created_at", None)
        validated(snap)

    def test_stage_vocabulary_is_the_four_pipeline_stages(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        stages = schema["$defs"]["bottleneck_stage"]["properties"]["stage"]["enum"]
        assert tuple(stages) == STAGE_NAMES

    def test_stage_rows_carry_every_headline_metric(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        required = schema["$defs"]["bottleneck_stage"]["required"]
        for field in (
            "queue_depth",
            "oldest_item_age_s",
            "dwell_median_s",
            "dwell_p95_s",
            "dwell_status",
            "throughput_per_hour_1h",
            "throughput_per_hour_24h",
            "throughput_status",
            "wip",
            "capacity",
            "capacity_source",
            "state",
        ):
            assert field in required, field

    def test_invariant_carries_the_reconciliation_metric_set(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        required = schema["$defs"]["bottleneck_invariant"]["required"]
        for field in (
            "total_outstanding",
            "ready",
            "ready_waiting_despite_capacity",
            "waiting_despite_capacity",
            "claimed",
            "active_workers",
            "awaiting_verify",
            "awaiting_review",
            "awaiting_integrate",
            "awaiting_deploy",
            "blocked_with_reason",
            "blocked_reasons",
            "human_approvals_required",
            "last_auto_progress_at",
            "last_auto_progress_age_s",
            "completion_to_next_action_median_s",
            "completion_to_next_action_p95_s",
        ):
            assert field in required, field

    def test_invariant_capacity_is_optional_but_declared(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        invariant = schema["$defs"]["bottleneck_invariant"]
        assert "capacity" not in invariant["required"]
        capacity = invariant["properties"]["capacity"]
        assert set(capacity["required"]) == {"max_active", "in_use", "available"}

    def test_dwell_targets_are_declared_per_stage_in_the_schema(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        thresholds = schema["$defs"]["bottlenecks_section"]["properties"]["thresholds"]
        assert set(thresholds["properties"]) == set(STAGE_NAMES)
        for node in thresholds["properties"].values():
            resolved = VALIDATOR.load(SNAPSHOT_SCHEMA)
            ref = node["$ref"].split("/")[-1]
            assert "dwell_target_s" in resolved["$defs"][ref]["properties"]

    def test_unavailable_snapshot_still_validates_with_bottlenecks(self, tmp_path: Path) -> None:
        # Degradation must come from the sources, not from ambient CLI
        # failures on the test host: both runners are injected as failing.
        def failing(argv):
            return 1, "", ""

        snap = collector.Collector(
            fleet_runner=failing,
            gh_runner=failing,
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        assert "bottlenecks" in snap["degraded"]
        body = bottlenecks_of(snap)
        assert body["status"] == "unavailable"
        assert body["error"]
        row = stage_of(body, "verify")
        assert row["queue_depth"] is None
        assert row["dwell_status"] == "unavailable"
        assert row["throughput_status"] == "unavailable"
        assert row["state"] == "unknown"
        assert body["invariant"]["ready_waiting_despite_capacity"] is None
        assert body["invariant"]["waiting_despite_capacity"] is None


# ------------------------------------------------------------ fixture section


class TestBottlenecksComputed:
    @pytest.fixture()
    def section(self, tmp_path: Path) -> dict:
        snap = bottleneck_collector(tmp_path).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live", body.get("error")
        return body

    def test_every_record_carries_schema_and_generated_at(self, section: dict) -> None:
        generated = section["collected_at"]
        for row in section["stages"]:
            assert row["schema"] == "rizzstack.observability/snapshot/1"
            assert row["generated_at"] == generated
        invariant = section["invariant"]
        assert invariant["schema"] == "rizzstack.observability/snapshot/1"
        assert invariant["generated_at"] == generated

    def test_thresholds_echo_configuration_not_magic(self, section: dict) -> None:
        assert section["thresholds"] == {
            stage: {"dwell_target_s": DEFAULT_TARGETS[stage]} for stage in STAGE_NAMES
        }

    def test_verify_stage_metrics(self, section: dict) -> None:
        row = stage_of(section, "verify")
        assert row["queue_depth"] == 1
        assert row["oldest_item_age_s"] == 600
        assert row["dwell_median_s"] == 1050.0
        assert row["dwell_p95_s"] == 1200.0
        assert row["dwell_status"] == "known"
        assert row["throughput_per_hour_1h"] == 1.0
        assert abs(row["throughput_per_hour_24h"] - 3 / 24) < 1e-6
        assert row["throughput_status"] == "known"
        assert row["wip"] == 1
        assert row["capacity"] == 12
        assert row["capacity_source"] == "bee_cap"
        assert row["state"] == "ok"

    def test_review_stage_metrics(self, section: dict) -> None:
        row = stage_of(section, "review")
        assert row["queue_depth"] == 1
        assert row["oldest_item_age_s"] == 2400
        # No record of completed review stays exists, so dwell and
        # throughput stay unknown instead of being folded into zero.
        assert row["dwell_median_s"] is None
        assert row["dwell_p95_s"] is None
        assert row["dwell_status"] == "unknown"
        assert row["throughput_per_hour_1h"] is None
        assert row["throughput_status"] == "unknown"
        assert row["wip"] is None
        assert row["capacity"] is None
        assert row["capacity_source"] is None
        assert row["state"] == "unknown"

    def test_integrate_stage_metrics(self, section: dict) -> None:
        row = stage_of(section, "integrate")
        assert row["queue_depth"] == 2
        assert row["oldest_item_age_s"] == 4200
        assert row["dwell_median_s"] == 1500.0
        assert row["dwell_p95_s"] == 1500.0
        assert row["dwell_status"] == "known"
        assert row["throughput_per_hour_1h"] == 0.0
        assert abs(row["throughput_per_hour_24h"] - 1 / 24) < 1e-6
        assert row["wip"] is None
        assert row["capacity"] is None
        assert row["state"] == "ok"

    def test_deploy_stage_metrics_from_open_pull_requests(self, section: dict) -> None:
        row = stage_of(section, "deploy")
        assert row["queue_depth"] == 1
        assert row["oldest_item_age_s"] == 5400
        assert row["dwell_status"] == "unknown"
        assert row["throughput_status"] == "unknown"
        assert row["capacity_source"] is None

    def test_invariant_pins_the_reconciler_formula_on_the_fixture(self, section: dict) -> None:
        # The reconciler's arithmetic on this fixture (reconcile.py):
        # claimed counts tasks in the dispatching/dispatched states, so the
        # running claim record for feat_gamma is NOT a claimed task - the
        # running task itself is the active worker and the claim record is
        # reported separately as active_claims. A dependency-blocked queue
        # feature is not an owner message (it advances when its dependency
        # completes), so the only owner message is job_r2's unrecorded
        # merge-gate decision. The earlier expectation here (in_use 3,
        # blocked dependency 1) enshrined the double count the r2 review
        # rejected.
        invariant = section["invariant"]
        assert invariant["status"] == "known"
        assert invariant["total_outstanding"] == 4
        assert invariant["ready"] == 1
        assert invariant["claimed"] == 0
        assert invariant["active_workers"] == 1
        assert invariant["awaiting_verify"] == 1
        assert invariant["awaiting_review"] == 1
        assert invariant["awaiting_integrate"] == 2
        assert invariant["awaiting_deploy"] == 1
        assert invariant["active_claims"] == 1
        assert invariant["capacity"] == {"max_active": 4, "in_use": 2, "available": 2}
        assert invariant["waiting_despite_capacity"] is False
        assert invariant["ready_waiting_despite_capacity"] == 0
        assert invariant["blocked_with_reason"] == 0
        assert invariant["blocked_reasons"] == {}
        assert invariant["human_approvals_required"] == 1

    def test_invariant_progression_and_handoff_latency(self, section: dict) -> None:
        invariant = section["invariant"]
        assert invariant["last_auto_progress_at"] == at(110)
        assert invariant["last_auto_progress_age_s"] == 600
        # Worker-completion to next-event gaps in document order: T3 at 5
        # minutes to its next event at 20, T4 at 60 to its next at 80.
        assert invariant["completion_to_next_action_median_s"] == 1050.0
        assert invariant["completion_to_next_action_p95_s"] == 1200.0
        assert invariant["completion_to_next_action_status"] == "known"


# ------------------------------------------------------- real-shaped probing


class TestBottlenecksRealShapes:
    """The review's probe scenario: a verifying task, a verified task, a
    verify event, and a dispatch. Every number below comes from a record the
    producers actually write."""

    @pytest.fixture()
    def section(self, tmp_path: Path) -> dict:
        state = tmp_path / "state"
        for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
            (state / subdir).mkdir(parents=True, exist_ok=True)
        write_job_document(
            state,
            job_document(
                "job_p",
                "mojomast/workflow",
                tasks=[
                    task_row("T1", "verifying", attempts=("a1",)),
                    task_row("T2", "verified", attempts=("a2",)),
                ],
                events=[event_row("T2", "verifying->verified", at(60))],
            ),
        )
        write_grant(state, "job_p", "merge", at(50))
        write_queue(
            state,
            {"feat_p": {"repo": "mojomast/workflow", "job_id": "", "title": "p", "depends_on": [], "status": "queued"}},
        )
        write_metrics(
            state,
            [
                ("dispatch", at(30), {"attempt_id": "a2"}),
                ("dispatch", at(90), {"attempt_id": "a1"}),
            ],
        )
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
            stale_after_s=1800,
        ).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live", body.get("error")
        return body

    def test_verify_row_numbers_become_real(self, section: dict) -> None:
        row = stage_of(section, "verify")
        assert row["queue_depth"] == 1
        # The verifying task has no recorded transition into verifying; its
        # dispatch record dates the entry, so the age is real, not null and
        # not a fabricated zero.
        assert row["oldest_item_age_s"] == 1800
        assert row["dwell_status"] == "unknown"
        assert row["dwell_median_s"] is None
        # The recorded verify event (verifying to verified) is an advance
        # past the stage even though the stage entry was never recorded.
        assert row["throughput_per_hour_1h"] == 1.0
        assert abs(row["throughput_per_hour_24h"] - 1 / 24) < 1e-6
        assert row["throughput_status"] == "known"

    def test_integrate_row_numbers_become_real(self, section: dict) -> None:
        row = stage_of(section, "integrate")
        assert row["queue_depth"] == 1
        # The verified task's entry is dated by the recorded transition into
        # verified.
        assert row["oldest_item_age_s"] == 3600
        assert row["dwell_status"] == "unknown"
        assert row["throughput_status"] == "known"

    def test_invariant_becomes_real(self, section: dict) -> None:
        invariant = section["invariant"]
        assert invariant["ready"] == 1
        assert invariant["claimed"] == 0
        assert invariant["active_workers"] == 0
        assert invariant["awaiting_verify"] == 1
        assert invariant["capacity"] == {"max_active": 4, "in_use": 1, "available": 3}
        assert invariant["human_approvals_required"] == 0
        assert invariant["waiting_despite_capacity"] is True
        assert invariant["ready_waiting_despite_capacity"] == 1

    def test_tasks_with_zero_parsed_transitions_report_unknown_throughput(self, tmp_path: Path) -> None:
        # A job whose tasks exist but whose event list records no transition
        # yet: throughput must read unknown, never 0.0 with a known marker.
        state = tmp_path / "state"
        for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
            (state / subdir).mkdir(parents=True, exist_ok=True)
        write_job_document(
            state,
            job_document(
                "job_z",
                "mojomast/workflow",
                tasks=[task_row("T1", "verifying", attempts=("a1",))],
                events=[],
            ),
        )
        write_grant(state, "job_z", "merge", at(5))
        write_queue(
            state,
            {"feat_z": {"repo": "mojomast/workflow", "job_id": "", "title": "z", "depends_on": [], "status": "queued"}},
        )
        write_metrics(state, [("dispatch", at(90), {"attempt_id": "a1"})])
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        row = stage_of(bottlenecks_of(snap), "verify")
        assert row["queue_depth"] == 1
        assert row["oldest_item_age_s"] == 1800
        assert row["dwell_status"] == "unknown"
        assert row["throughput_status"] == "unknown"
        assert row["throughput_per_hour_1h"] is None
        assert row["throughput_per_hour_24h"] is None

    def test_recorded_grant_file_clears_the_pending_approval(self, tmp_path: Path) -> None:
        # RED-first review finding: a gate stays in the waiting state by
        # design even after its decision is recorded, so the recorded
        # decision file is what counts. A job with a recorded grant counts
        # zero pending approvals, and a blocked feature reports its actual
        # blocker, never a stale approval_required.
        state = tmp_path / "state"
        for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
            (state / subdir).mkdir(parents=True, exist_ok=True)
        doc = job_document(
            "job_g",
            "mojomast/workflow",
            tasks=[task_row("T1", "failed", attempts=("a9",))],
            events=[event_row("T1", "verifying->failed", at(60))],
        )
        doc["approval_gate"]["state"] = "awaiting_approval"
        write_job_document(state, doc)
        write_grant(state, "job_g", "merge", at(50))
        write_queue(
            state,
            {"feat_g": {"repo": "mojomast/workflow", "job_id": "job_g", "title": "g", "depends_on": [], "status": "blocked"}},
        )
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        invariant = bottlenecks_of(snap)["invariant"]
        assert invariant["human_approvals_required"] == 0
        assert invariant["blocked_reasons"] == {"task_failed": 1}
        assert "approval_required" not in invariant["blocked_reasons"]
        assert invariant["ready"] == 0
        assert invariant["waiting_despite_capacity"] is False
        assert invariant["ready_waiting_despite_capacity"] == 0

    def test_ready_counts_only_eligible_queue_items(self, tmp_path: Path) -> None:
        # The queue's eligibility rule: a queued item counts as ready only
        # when the item itself is not done and every recorded dependency is
        # done. A dependency is done when its linked job is accepted, which
        # the queue checks against the verify records and the accepted
        # integration wave, not against status strings.
        state = tmp_path / "state"
        for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
            (state / subdir).mkdir(parents=True, exist_ok=True)
        done_job = job_document(
            "job_done",
            "mojomast/workflow",
            tasks=[task_row("T1", "accepted", attempts=("a10",))],
            events=[
                event_row("T1", "running->verifying", at(0)),
                event_row("T1", "verifying->verified", at(5)),
                event_row("T1", "verified->integrating", at(8)),
                event_row("T1", "integrating->accepted", at(10)),
            ],
            integration={
                "wave": "w1",
                "state": "accepted",
                "accepted_waves": [{"wave": "w1", "commit": HEX_C}],
                "last_commit": HEX_C,
            },
        )
        write_job_document(state, done_job)
        write_grant(state, "job_done", "merge", at(11))
        write_verify_record(state, verify_record_commit_local("a10", at(5)))
        write_queue(
            state,
            {
                "feat_dep": {"repo": "mojomast/workflow", "job_id": "job_done", "title": "dep", "depends_on": [], "status": "ready_for_review"},
                "feat_next": {"repo": "mojomast/workflow", "job_id": "", "title": "next", "depends_on": ["feat_dep"], "status": "queued"},
                "feat_solo": {"repo": "mojomast/workflow", "job_id": "", "title": "solo", "depends_on": [], "status": "queued"},
                "feat_stuck": {"repo": "mojomast/workflow", "job_id": "", "title": "stuck", "depends_on": ["feat_missing"], "status": "queued"},
            },
        )
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        invariant = bottlenecks_of(snap)["invariant"]
        # feat_next (dependency done) and feat_solo (no dependencies) are
        # eligible; feat_stuck's dependency was never done and must not be
        # counted, and neither may it be folded into a blocked item it is not.
        assert invariant["ready"] == 2
        assert invariant["claimed"] == 0
        assert invariant["active_workers"] == 0
        assert invariant["awaiting_verify"] == 0
        assert invariant["capacity"] == {"max_active": 4, "in_use": 0, "available": 4}
        assert invariant["human_approvals_required"] == 0
        assert invariant["blocked_with_reason"] == 0
        assert invariant["waiting_despite_capacity"] is True
        assert invariant["ready_waiting_despite_capacity"] == 2


# ------------------------------------------------------------------ thresholds


class TestBottlenecksThresholdsAreConfig:
    def test_target_override_flips_stage_state_to_over(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(
            tmp_path, thresholds={"verify_dwell_target_s": 100}
        ).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["thresholds"]["verify"]["dwell_target_s"] == 100
        assert stage_of(body, "verify")["state"] == "over"
        # Other stages keep their configured defaults.
        assert body["thresholds"]["review"]["dwell_target_s"] == DEFAULT_TARGETS["review"]


# ---------------------------------------------------------------- degradation


class TestBottlenecksDegradation:
    def test_no_sources_degrades_to_unavailable_with_markers(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty-state"
        empty.mkdir()
        snap = collector.Collector(
            state_dir=empty,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "unavailable"
        assert body["error"] == "no_bottleneck_sources"
        for stage in STAGE_NAMES:
            row = stage_of(body, stage)
            assert row["queue_depth"] is None
            assert row["oldest_item_age_s"] is None
            assert row["dwell_status"] == "unavailable"
            assert row["throughput_status"] == "unavailable"
        invariant = body["invariant"]
        assert invariant["status"] == "unavailable"
        assert invariant["total_outstanding"] is None
        assert invariant["ready"] is None
        assert invariant["waiting_despite_capacity"] is None
        assert invariant["ready_waiting_despite_capacity"] is None
        assert invariant["blocked_reasons"] == {}

    def test_missing_queue_degrades_review_and_headline_only(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(tmp_path, with_queue=False).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live"
        assert stage_of(body, "review")["queue_depth"] is None
        invariant = body["invariant"]
        # Capacity is computable from the records that exist, but the ready
        # count is not: the headline must be unknown, never a confident false.
        assert invariant["ready"] is None
        assert invariant["waiting_despite_capacity"] is None
        assert invariant["ready_waiting_despite_capacity"] is None
        # Outstanding falls back to the job tasks when the queue is unreadable.
        assert invariant["total_outstanding"] == 4
        assert invariant["status"] == "partial"

    def test_missing_fleet_keeps_stage_rows_alive_and_invariant_decided(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(
            tmp_path, fleet_runner=lambda argv: (1, "", "")
        ).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live"
        verify_row = stage_of(body, "verify")
        assert verify_row["wip"] is None
        assert verify_row["capacity"] is None
        assert verify_row["capacity_source"] is None
        assert verify_row["queue_depth"] == 1
        invariant = body["invariant"]
        # The invariant no longer reads the fleet: active workers come from
        # the job documents, so the headline stays decided.
        assert invariant["active_workers"] == 1
        assert invariant["ready"] == 1
        assert invariant["waiting_despite_capacity"] is False

    def test_missing_ci_degrades_deploy_only(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(tmp_path, gh_runner=lambda argv: (1, "", "")).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live"
        deploy_row = stage_of(body, "deploy")
        assert deploy_row["queue_depth"] is None
        assert deploy_row["dwell_status"] == "unavailable"
        invariant = body["invariant"]
        assert invariant["awaiting_deploy"] is None
        assert invariant["awaiting_verify"] == 1
        assert invariant["status"] == "partial"

    def test_all_sources_stale_marks_the_section_stale(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(
            tmp_path,
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW + timedelta(hours=4),
        ).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "stale"
        assert body["error"] == "bottleneck_sources_older_than_threshold"

    def test_unreadable_claim_record_blocks_without_silence(self, tmp_path: Path) -> None:
        state = make_state(tmp_path)
        (state / "queue" / "feat_broken.json").write_text("{not json", encoding="utf-8")
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        invariant = bottlenecks_of(snap)["invariant"]
        # A claim record that cannot be read may be an active claim, so it is
        # an owner message, never a silently dropped item.
        assert invariant["blocked_reasons"]["queue_claims_unreadable"] == 1
        assert invariant["waiting_despite_capacity"] is False


# --------------------------------------------------- sealed-envelope fixtures


def seal_document(doc: dict) -> dict:
    """The on-disk job envelope shape job.py _seal writes: {"body", "mac"}.

    The mac here is a synthetic digest, not a verified HMAC: the collector
    is a read-only, keyless reader and does not verify seals (the
    reconciler, which holds the state key, is the verifier). The shape is
    what the fixture pins.
    """
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return {"body": doc, "mac": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def write_sealed_job_document(state: Path, doc: dict) -> None:
    (state / "jobs" / f"{doc['job_id']}.json").write_text(
        json.dumps(seal_document(doc)), encoding="utf-8"
    )


class TestBottlenecksSealedEnvelope:
    """Real bundlebees job documents are written as HMAC envelopes
    ({"body": {...}, "mac": ...}, job.py _seal, docs/22-autonomy-architecture.md
    "Job (tasks, gates, events) | jobs/<job_id>.json | HMAC"). A collector
    that asks the envelope itself for tasks/events reads confident zeros on
    every real job; the suite must fail on that shape, never pass on it."""

    def test_sealed_job_document_is_unwrapped_for_bottlenecks(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
            (state / subdir).mkdir(parents=True, exist_ok=True)
        write_sealed_job_document(
            state,
            job_document(
                "job_sealed",
                "mojomast/workflow",
                tasks=[task_row("T1", "running", attempts=("a1",))],
                events=[event_row("T1", "dispatching->running", at(30))],
            ),
        )
        write_queue(
            state,
            {"feat_s": {"repo": "mojomast/workflow", "job_id": "", "title": "s", "depends_on": [], "status": "queued"}},
        )
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
            stale_after_s=1800,
        ).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live", body.get("error")
        invariant = body["invariant"]
        # The sealed body is parsed: one active worker, one recorded
        # automatic progression - not a confident zero.
        assert invariant["active_workers"] == 1
        assert invariant["total_outstanding"] == 1
        assert invariant["last_auto_progress_at"] == at(30)

    def test_sealed_job_document_is_unwrapped_for_the_pipeline_section(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        (state / "jobs").mkdir(parents=True)
        write_sealed_job_document(
            state,
            job_document(
                "job_sealed_p",
                "mojomast/workflow",
                tasks=[task_row("T1", "running", attempts=("a1",))],
                events=[],
            ),
        )
        pin_mtimes(tmp_path)
        body, _rows = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).pipeline_section()
        # The pre-existing pipeline reader sees through the same envelope.
        assert body["status"] == "live", body.get("error")
        assert body["counts"] == {"running": 1}
        assert body["jobs"][0]["task_count"] == 1

    def test_envelope_with_an_unusable_body_is_an_unreadable_job(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
            (state / subdir).mkdir(parents=True, exist_ok=True)
        broken = {"body": ["not", "an", "object"], "mac": "ab" * 32}
        (state / "jobs" / "job_broken.json").write_text(json.dumps(broken), encoding="utf-8")
        write_queue(
            state,
            {"feat_b": {"repo": "mojomast/workflow", "job_id": "", "title": "b", "depends_on": [], "status": "queued"}},
        )
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        invariant = bottlenecks_of(snap)["invariant"]
        # An envelope whose body cannot be a job document is an unreadable
        # job: an owner message, never a silent confident zero.
        assert invariant["blocked_reasons"]["job_unreadable"] == 1


# --------------------------------------------------- reconciler alignment


class TestBottlenecksReconcilerAlignment:
    """The invariant's inputs are the coordinator reconciler's
    (bundlebees_plugin/reconcile.py): claimed counts tasks in the
    dispatching/dispatched states (reconcile.py:1739-1740), active_workers
    counts running tasks (:1742), awaiting verification counts verifying
    tasks (:1746), and live claim records are reported separately as
    features.active_claims (:1849-1860) - never added to the task they are
    the claim of. The blocked set counts what requires the owner: approval
    gates without a recorded decision, terminal task states,
    integration-terminal and evidence-incomplete jobs, unknown task states,
    and unreadable job or claim records (the claim store is refused whole,
    one message, as QueueStore.active() refuses it)."""

    @staticmethod
    def _bare_state(tmp_path: Path) -> Path:
        state = tmp_path / "state"
        for subdir in ("jobs", "metrics", "verify-results", "queue", "approvals"):
            (state / subdir).mkdir(parents=True, exist_ok=True)
        return state

    @staticmethod
    def _snapshot(state: Path, tmp_path: Path) -> dict:
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
            stale_after_s=1800,
        ).build_snapshot()
        validated(snap)
        return bottlenecks_of(snap)["invariant"]

    def test_a_running_claim_and_its_running_task_count_once(self, tmp_path: Path) -> None:
        # The reviewer's probe: one task running under a running claim is
        # ONE unit of work, so in_use is 1, not 2.
        state = self._bare_state(tmp_path)
        write_job_document(
            state,
            job_document(
                "job_run",
                "mojomast/workflow",
                tasks=[task_row("T1", "running", attempts=("a1",))],
                events=[],
            ),
        )
        write_queue(
            state,
            {"feat_r": {"repo": "mojomast/workflow", "job_id": "job_run", "title": "r", "depends_on": [], "status": "claimed"}},
        )
        write_claim(state, "feat_r", "job_run", at(0))
        invariant = self._snapshot(state, tmp_path)
        assert invariant["claimed"] == 0
        assert invariant["active_workers"] == 1
        assert invariant["active_claims"] == 1
        assert invariant["capacity"] == {"max_active": 4, "in_use": 1, "available": 3}

    def test_a_dispatched_task_with_no_claim_counts_as_claimed(self, tmp_path: Path) -> None:
        # The reviewer's probe: the job-CLI path dispatches a task without a
        # queue claim; the reconciler counts it (dispatching/dispatched), so
        # in_use is 1, not 0.
        state = self._bare_state(tmp_path)
        write_job_document(
            state,
            job_document(
                "job_disp",
                "mojomast/workflow",
                tasks=[task_row("T1", "dispatched", attempts=("a1",))],
                events=[],
            ),
        )
        write_queue(
            state,
            {"feat_d": {"repo": "mojomast/workflow", "job_id": "", "title": "d", "depends_on": [], "status": "queued"}},
        )
        invariant = self._snapshot(state, tmp_path)
        assert invariant["claimed"] == 1
        assert invariant["active_workers"] == 0
        assert invariant["active_claims"] == 0
        assert invariant["capacity"] == {"max_active": 4, "in_use": 1, "available": 3}

    def test_stale_running_claims_do_not_pin_capacity(self, tmp_path: Path) -> None:
        # The reviewer's deployed-state evidence: claim records left in
        # state running by finished work must not pin available to 0. Claim
        # records are reported as active_claims; only in-flight task states
        # consume scheduler slots.
        state = make_state(tmp_path)
        for index in range(12):
            record = {
                "feature_id": f"stale_{index}",
                "state": "running",
                "job_id": "",
                "claimed_at": at(0),
                "pid": 1111,
            }
            (state / "queue" / f"stale_{index}.json").write_text(json.dumps(record), encoding="utf-8")
        invariant = self._snapshot(state, tmp_path)
        assert invariant["active_claims"] == 13
        assert invariant["claimed"] == 0
        assert invariant["capacity"] == {"max_active": 4, "in_use": 2, "available": 2}

    def test_integration_terminal_job_is_an_owner_message(self, tmp_path: Path) -> None:
        state = self._bare_state(tmp_path)
        write_job_document(
            state,
            job_document(
                "job_term",
                "mojomast/workflow",
                tasks=[task_row("T1", "accepted", attempts=("a1",))],
                events=[event_row("T1", "integrating->accepted", at(10))],
                integration={
                    "wave": "w1",
                    "state": "stopped",
                    "terminal": True,
                    "evidence": "conflict unresolved",
                    "last_commit": HEX_C,
                },
            ),
        )
        write_verify_record(state, verify_record_commit_local("a1", at(5)))
        write_queue(
            state,
            {"feat_t": {"repo": "mojomast/workflow", "job_id": "job_term", "title": "t", "depends_on": [], "status": "ready_for_review"}},
        )
        invariant = self._snapshot(state, tmp_path)
        assert invariant["blocked_reasons"]["integration_terminal"] == 1
        assert invariant["waiting_despite_capacity"] is False

    def test_evidence_incomplete_job_is_an_owner_message(self, tmp_path: Path) -> None:
        state = self._bare_state(tmp_path)
        # Every task accepted, a passing verify record for the last attempt,
        # but no accepted integration wave: the queue's own acceptance check
        # refuses it, so the job cannot be treated as finished silently.
        write_job_document(
            state,
            job_document(
                "job_ev",
                "mojomast/workflow",
                tasks=[task_row("T1", "accepted", attempts=("a1",))],
                events=[event_row("T1", "integrating->accepted", at(10))],
            ),
        )
        write_verify_record(state, verify_record_commit_local("a1", at(5)))
        write_grant(state, "job_ev", "merge", at(11))
        write_queue(
            state,
            {"feat_e": {"repo": "mojomast/workflow", "job_id": "job_ev", "title": "e", "depends_on": [], "status": "ready_for_review"}},
        )
        invariant = self._snapshot(state, tmp_path)
        assert invariant["blocked_reasons"]["job_evidence_incomplete"] == 1

    def test_unknown_task_state_is_an_owner_message(self, tmp_path: Path) -> None:
        state = self._bare_state(tmp_path)
        write_job_document(
            state,
            job_document(
                "job_odd",
                "mojomast/workflow",
                tasks=[task_row("T1", "teleported", attempts=("a1",))],
                events=[],
            ),
        )
        write_queue(
            state,
            {"feat_o": {"repo": "mojomast/workflow", "job_id": "", "title": "o", "depends_on": [], "status": "queued"}},
        )
        invariant = self._snapshot(state, tmp_path)
        assert invariant["blocked_reasons"]["task_state_unknown"] == 1

    def test_unreadable_claim_store_is_one_owner_message(self, tmp_path: Path) -> None:
        # QueueStore.active() refuses the whole store when any record cannot
        # be read; the reconciler records one queue:claims refusal. The
        # collector must not turn two unreadable records into two messages,
        # and the active-claim count is unknown, not zero.
        state = make_state(tmp_path)
        (state / "queue" / "broken_a.json").write_text("{not json", encoding="utf-8")
        (state / "queue" / "broken_b.json").write_text("{also not", encoding="utf-8")
        invariant = self._snapshot(state, tmp_path)
        assert invariant["blocked_reasons"]["queue_claims_unreadable"] == 1
        assert invariant["active_claims"] is None
        assert invariant["waiting_despite_capacity"] is False

    def test_invariant_agrees_with_the_reconcilers_own_report(self, tmp_path: Path) -> None:
        source = os.environ.get("BUNDLEBEES_PLUGIN_SRC")
        if not source:
            pytest.skip(
                "bundlebees_plugin source not provided (BUNDLEBEES_PLUGIN_SRC unset); "
                "CI pins the formula above and the coordinator runs this live "
                "cross-check at verify time"
            )
        if source not in sys.path:
            sys.path.insert(0, source)
        from bundlebees_plugin import job as bb_jobs  # reconcile.py imports it as jobs
        from bundlebees_plugin import reconcile as bb_reconcile
        from bundlebees_plugin.leases import _ensure_key

        state = tmp_path / "xstate"
        for subdir in ("jobs", "queue", "approvals"):
            (state / subdir).mkdir(parents=True)
        key = _ensure_key(state)
        body = job_document(
            "job_x",
            "mojomast/workflow",
            tasks=[
                task_row("T1", "running", attempts=("a1",)),
                task_row("T2", "verifying", attempts=("a2",)),
            ],
            events=[],
        )
        envelope = {"body": body, "mac": bb_jobs._sign(body, key)}
        (state / "jobs" / "job_x.json").write_text(json.dumps(envelope), encoding="utf-8")
        write_queue(
            state,
            {"feat_x": {"repo": "mojomast/workflow", "job_id": "", "title": "x", "depends_on": [], "status": "queued"}},
        )
        write_claim(state, "feat_x", "job_x", at(0))
        for index in range(2):
            record = {
                "feature_id": f"stale_{index}",
                "state": "running",
                "job_id": "",
                "claimed_at": at(0),
                "pid": 2222,
            }
            (state / "queue" / f"stale_{index}.json").write_text(json.dumps(record), encoding="utf-8")
        pin_mtimes(tmp_path)
        snap = collector.Collector(
            state_dir=state,
            fleet_runner=lambda argv: (1, "", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
            stale_after_s=1800,
        ).build_snapshot()
        validated(snap)
        invariant = bottlenecks_of(snap)["invariant"]
        report = bb_reconcile.reconciliation_report(state, now=FIXED_EPOCH)  # the reconciler's clock is epoch/ISO/callable
        # Same logical state, two readers - the sealed fixture proves the
        # collector's numbers come from the same sources as the reconciler's
        # report, including the stale claims that must not count twice.
        assert report["capacity"]["in_use"] == invariant["capacity"]["in_use"] == 2
        assert report["outstanding"]["claimed"] == invariant["claimed"] == 0
        assert report["outstanding"]["active_workers"] == invariant["active_workers"] == 1
        assert report["awaiting"]["verification"] == invariant["awaiting_verify"] == 1
        assert report["features"]["active_claims"] == invariant["active_claims"] == 3
        assert report["invariant"]["owner_messages_required"] == (
            invariant["human_approvals_required"] + invariant["blocked_with_reason"]
        ) == 1


# ------------------------------------------------------------------ read-only


class TestBottlenecksReadOnly:
    def test_bottlenecks_collection_writes_nothing(self, tmp_path: Path) -> None:
        def inventory(root: Path) -> dict:
            out = {}
            for path in sorted(root.rglob("*")):
                st = path.stat()
                out[str(path.relative_to(root))] = (st.st_mtime_ns, st.st_size, st.st_mode)
            return out

        state = make_state(tmp_path)
        pin_mtimes(tmp_path)
        before = inventory(tmp_path)
        c = collector.Collector(
            state_dir=state,
            fleet_runner=fleet_runner,
            gh_runner=gh_runner,
            now_fn=lambda: FIXED_NOW,
        )
        c.build_snapshot()
        c.build_snapshot()
        assert inventory(tmp_path) == before


# ------------------------------------------------------------------ envelope


class TestBottlenecksEnvelope:
    # Marker strings are assembled at runtime by concatenation so no
    # credential-shaped literal ever appears in source, as in the wider
    # snapshot suite.
    MARKERS = tuple(
        "".join(parts)
        for parts in (("gh", "p_"), ("s", "k-"), ("github_", "pat_"), ("AK", "IA"), ("AI", "za"))
    )

    def test_snapshot_carries_no_credential_shaped_material(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(tmp_path).build_snapshot()
        dumped = json.dumps(snap)
        for marker in self.MARKERS:
            assert marker not in dumped


if __name__ == "__main__":
    unittest.main()
