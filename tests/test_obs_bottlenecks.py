"""Tests for the bottlenecks section of the rizzstack observability snapshot.

The bottlenecks section answers one question for the dashboard: where is
work piling up? Per pipeline stage (verify, review, integrate, deploy) it
carries queue depth, oldest-item age, dwell-time median and p95, throughput
over the last hour and last day, and WIP versus capacity where a cap exists.
It also carries the reconciliation headline: authorized and eligible work
waiting despite available capacity.

Everything is computed read-only from real records (job documents, the
feature queue, review reports, scheduler metrics, CI pull requests). A
missing source degrades to null with a status marker, never to zero. Dwell
targets are configuration, not constants. Fixture state below is synthetic
and written per test into tmp_path.
"""

from __future__ import annotations

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


def write_job_b1(state: Path) -> None:
    """One job with all stage traffic: an open verify item, an open
    integrate item, and a task that travelled the whole verify-then-integrate
    path leaving dwell samples behind."""
    doc = {
        "job_id": "job_b1",
        "goal": {"repo": "mojomast/workflow", "base_rev": HEX_A},
        "tasks": [
            {
                "task_id": "T1",
                "state": "verifying",
                "attempts": [{"attempt_id": "a1", "state": "verifying", "ts": at(105)}],
            },
            {
                "task_id": "T2",
                "state": "verified",
                "attempts": [{"attempt_id": "a2", "state": "succeeded", "ts": at(50)}],
            },
            {
                "task_id": "T3",
                "state": "accepted",
                "attempts": [{"attempt_id": "a3", "state": "succeeded", "ts": at(0)}],
            },
        ],
        "events": [
            {"kind": "task_state", "task_id": "T3", "from": "running", "to": "verifying", "ts": at(5)},
            {"kind": "task_state", "task_id": "T3", "from": "verifying", "to": "verified", "ts": at(20)},
            {"kind": "task_state", "task_id": "T3", "from": "verified", "to": "accepted", "ts": at(45)},
            {"kind": "task_state", "task_id": "T2", "from": "verifying", "to": "verified", "ts": at(50)},
            {"kind": "task_state", "task_id": "T2", "from": "verified", "to": "integrating", "ts": at(100)},
            {"kind": "task_state", "task_id": "T1", "from": "running", "to": "verifying", "ts": at(110)},
        ],
        "approval_gate": {"required": True, "for": "merge", "state": "awaiting_approval"},
        "integration": {"wave": "w1", "state": "pending"},
        "escalations": [],
    }
    (state / "jobs" / "job_b1.json").write_text(json.dumps(doc), encoding="utf-8")


def write_job_b2(state: Path) -> None:
    doc = {
        "job_id": "job_b2",
        "goal": {"repo": "mojomast/bundlebees", "base_rev": HEX_B},
        "tasks": [{"task_id": "T1", "state": "running", "attempts": []}],
        "events": [],
        "approval_gate": {"required": True, "for": "merge", "state": "waiting"},
        "integration": {"wave": "w1", "state": "pending"},
        "escalations": [],
    }
    (state / "jobs" / "job_b2.json").write_text(json.dumps(doc), encoding="utf-8")


def write_queue(state: Path) -> None:
    doc = {
        "features": [
            {"feature_id": "feat_alpha", "job_id": "job_b1", "status": "ready_for_review", "depends_on": []},
            {"feature_id": "feat_beta", "job_id": None, "status": "queued", "depends_on": []},
            {"feature_id": "feat_gamma", "job_id": "job_b2", "status": "claimed", "depends_on": []},
            {"feature_id": "feat_delta", "job_id": "job_b1", "status": "blocked", "depends_on": ["feat_alpha"]},
        ]
    }
    (state / "queue.json").write_text(json.dumps(doc), encoding="utf-8")


def write_metrics(state: Path) -> None:
    events = [
        {"seq": 1, "ts": at(80), "event": "dispatch", "job_id": "job_b1", "task_id": "T4", "attempt_id": "a4"},
        {"seq": 2, "ts": at(105), "event": "verify", "job_id": "job_b1", "task_id": "T4", "attempt_id": "a4", "outcome": "failure"},
        {"seq": 3, "ts": at(107), "event": "recovery", "job_id": "job_b1", "task_id": "T4", "reason": "needs_agent"},
        {"seq": 4, "ts": at(110), "event": "dispatch", "job_id": "job_b1", "task_id": "T5", "attempt_id": "a5"},
        {"seq": 5, "ts": at(115), "event": "verify", "job_id": "job_b1", "task_id": "T5", "attempt_id": "a5", "outcome": "ok"},
        {"seq": 6, "ts": at(120), "event": "dispatch", "job_id": "job_b1", "task_id": "T5", "attempt_id": "a6"},
    ]
    lines = "\n".join(json.dumps(event) for event in events) + "\n"
    (state / "metrics" / "run-1.jsonl").write_text(lines, encoding="utf-8")


def write_review_report(state: Path) -> None:
    report = {
        "attempt_id": "a2",
        "job_id": "job_b1",
        "task_id": "T2",
        "ts": at(50),
        "outcome": "ok",
        "suite": {"exit_code": 0, "passed": 3, "failed": 0},
    }
    (state / "verify-results" / "a2.json").write_text(json.dumps(report), encoding="utf-8")


def fleet_runner(argv):
    attempts = {
        "attempts": [
            {
                "attempt_id": "w1",
                "state": "working",
                "job_id": "job_b1",
                "task_id": "T1",
                "repo": "mojomast/workflow",
                "started_at": at(100),
                "updated_at": at(119),
            }
        ]
    }
    if any("op=attempts" in part for part in argv):
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
    for subdir in ("jobs", "metrics", "verify-results"):
        (state / subdir).mkdir(parents=True, exist_ok=True)
    write_job_b1(state)
    write_job_b2(state)
    if with_queue:
        write_queue(state)
    write_metrics(state)
    write_review_report(state)
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
    def test_bottlenecks_is_a_required_versioned_section(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        assert "bottlenecks" in schema["required"]
        assert "bottlenecks" in schema["properties"]
        assert "bottlenecks" in schema["properties"]["degraded"]["items"]["enum"]

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

    def test_dwell_targets_are_declared_per_stage_in_the_schema(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        thresholds = schema["$defs"]["bottlenecks_section"]["properties"]["thresholds"]
        assert set(thresholds["properties"]) == set(STAGE_NAMES)
        for node in thresholds["properties"].values():
            resolved = VALIDATOR.load(SNAPSHOT_SCHEMA)
            ref = node["$ref"].split("/")[-1]
            assert "dwell_target_s" in resolved["$defs"][ref]["properties"]

    def test_unavailable_snapshot_still_validates_with_bottlenecks(self, tmp_path: Path) -> None:
        snap = collector.Collector(now_fn=lambda: FIXED_NOW).build_snapshot()
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
        assert row["dwell_median_s"] == 900.0
        assert row["dwell_p95_s"] == 900.0
        assert row["dwell_status"] == "known"
        assert row["throughput_per_hour_1h"] == 0.0
        # Only transitions recorded as leaving verifying count: T3 left at
        # 10:20; T2's report exists but its entry into verifying was never
        # recorded, so unknown stays unknown instead of being inferred.
        assert abs(row["throughput_per_hour_24h"] - 1 / 24) < 1e-6
        assert row["throughput_status"] == "known"
        assert row["wip"] == 1
        assert row["capacity"] == 12
        assert row["capacity_source"] == "bee_cap"
        assert row["state"] == "ok"

    def test_review_stage_metrics(self, section: dict) -> None:
        row = stage_of(section, "review")
        assert row["queue_depth"] == 1
        assert row["oldest_item_age_s"] == 900
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
        assert row["queue_depth"] == 1
        assert row["oldest_item_age_s"] == 4200
        assert row["dwell_median_s"] == 2250.0
        assert row["dwell_p95_s"] == 3000.0
        assert row["dwell_status"] == "known"
        assert row["throughput_per_hour_1h"] == 1.0
        assert abs(row["throughput_per_hour_24h"] - 2 / 24) < 1e-6
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

    def test_invariant_headline_waiting_despite_capacity(self, section: dict) -> None:
        invariant = section["invariant"]
        assert invariant["status"] == "known"
        assert invariant["total_outstanding"] == 4
        assert invariant["ready"] == 1
        assert invariant["claimed"] == 1
        assert invariant["waiting_despite_capacity"] is True
        assert invariant["ready_waiting_despite_capacity"] == 1
        assert invariant["active_workers"] == 2
        assert invariant["awaiting_verify"] == 1
        assert invariant["awaiting_review"] == 1
        assert invariant["awaiting_integrate"] == 1
        assert invariant["awaiting_deploy"] == 1
        assert invariant["blocked_with_reason"] == 1
        assert invariant["blocked_reasons"] == {"approval_required": 1}
        assert invariant["human_approvals_required"] == 2

    def test_invariant_progression_and_handoff_latency(self, section: dict) -> None:
        invariant = section["invariant"]
        assert invariant["last_auto_progress_at"] == at(120)
        assert invariant["last_auto_progress_age_s"] == 0
        assert invariant["completion_to_next_action_median_s"] == 210.0
        assert invariant["completion_to_next_action_p95_s"] == 300.0
        assert invariant["completion_to_next_action_status"] == "known"


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
        assert invariant["blocked_reasons"] == {}

    def test_missing_queue_degrades_review_and_headline_only(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(tmp_path, with_queue=False).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live"
        assert stage_of(body, "review")["queue_depth"] is None
        invariant = body["invariant"]
        # Capacity is known but the ready count is not: the headline must be
        # unknown, never a confident false.
        assert invariant["ready"] is None
        assert invariant["waiting_despite_capacity"] is None
        assert invariant["ready_waiting_despite_capacity"] is None
        # Outstanding falls back to the job tasks when the queue is unreadable.
        assert invariant["total_outstanding"] == 3
        assert invariant["status"] == "partial"

    def test_missing_fleet_keeps_stage_rows_alive_without_capacity(self, tmp_path: Path) -> None:
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
        assert invariant["active_workers"] is None
        assert invariant["waiting_despite_capacity"] is None
        assert invariant["ready"] == 1

    def test_missing_ci_degrades_deploy_only(self, tmp_path: Path) -> None:
        snap = bottleneck_collector(tmp_path, gh_runner=lambda argv: (1, "", "")).build_snapshot()
        validated(snap)
        body = bottlenecks_of(snap)
        assert body["status"] == "live"
        deploy_row = stage_of(body, "deploy")
        assert deploy_row["queue_depth"] is None
        assert deploy_row["dwell_status"] == "unavailable"
        assert body["invariant"]["awaiting_deploy"] is None
        assert body["invariant"]["awaiting_verify"] == 1

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
