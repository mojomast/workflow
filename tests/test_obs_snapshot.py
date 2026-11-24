"""Tests for the rizzstack observability snapshot contract and collector.

The collector is exercised three ways: with injected CLI runners (deterministic
sections), through its real subprocess path against tiny fake ``hermes``/``gh``
executables, and over its loopback HTTP surface with a bearer credential. All
fixture data is synthetic; credentials in this file are assembled at runtime by
concatenation so no credential-shaped literal ever appears in source.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))

from validate import SchemaError, Validator  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "observability-state"
SNAPSHOT_SCHEMA = "snapshot.schema.json"

FIXED_NOW = datetime(2026, 11, 16, 9, 30, 0, tzinfo=timezone.utc)
FIXED_EPOCH = FIXED_NOW.timestamp()


def load_collector_module():
    spec = importlib.util.spec_from_file_location(
        "rizzstack_obs_collector",
        ROOT / "contrib" / "rizzstack-observability" / "collector.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_collector_module()
VALIDATOR = Validator(ROOT / "observability" / "schemas")


def freeze_state(tmp_path: Path) -> Path:
    """Copy the synthetic fixture state into tmp and pin mtimes so freshness
    checks are deterministic no matter when the suite runs. Idempotent."""
    target = tmp_path / "observability-state"
    if not target.exists():
        shutil.copytree(FIXTURES, target)
    for path in target.rglob("*"):
        if path.is_file():
            os.utime(path, (FIXED_EPOCH - 60, FIXED_EPOCH - 60))
    return target


def fixture_collector(tmp_path: Path, **overrides):
    state_root = freeze_state(tmp_path)
    state = state_root / "state"
    fleet_payload = {
        "attempts": [
            {
                "attempt_id": "att_1",
                "state": "running",
                "job_id": "job_20261113_a",
                "task_id": "T1",
                "repo": "mojomast/workflow",
                "branch": "feat/obs-snapshot-collector",
                "route": "go",
                "started_at": "2026-11-16T08:05:00Z",
                "updated_at": "2026-11-16T09:29:00Z",
            },
            {
                "attempt_id": "att_9",
                "state": "warp-drive",
                "job_id": "job_20261113_b",
                "task_id": "T1",
            },
        ]
    }
    status_payload = {"in_flight": 2, "bee_cap": 12}

    def fleet_runner(argv):
        # The collector's ported CLI contract: the two read-only packet-1
        # subcommands, each scoped by exactly the state directory the
        # collector was given. A runner that would see a subcommand other
        # than these - or a state directory the collector was never handed -
        # must refuse, so a wrong invocation shape still fails the suite.
        assert argv[1] == "bundlebees" and argv[2] in ("attempts", "status"), argv
        assert argv[-2:] == ["--state-dir", str(state)], argv
        if argv[2] == "attempts":
            return 0, json.dumps(fleet_payload), ""
        return 0, json.dumps(status_payload), ""

    gh_script = {
        "list": {
            "mojomast/workflow": [
                {
                    "number": 7,
                    "headRefName": "contrib/hermes-bees",
                    "state": "OPEN",
                    "statusCheckRollup": [
                        {"name": "unit tests", "state": "SUCCESS"},
                        {"name": "lint", "state": "FAILURE"},
                    ],
                }
            ],
            "mojomast/bundlebees": [
                {
                    "number": 12,
                    "headRefName": "feat/metrics",
                    "state": "OPEN",
                    "statusCheckRollup": [{"name": "suite", "state": "SUCCESS"}],
                }
            ],
        },
        "checks": {},
    }

    def gh_runner(argv):
        if "checks" in argv:
            number = argv[argv.index("checks") + 1]
            return 0, json.dumps(gh_script["checks"].get(number, [])), ""
        repo = argv[argv.index("--repo") + 1]
        return 0, json.dumps(gh_script["list"].get(repo, [])), ""

    defaults = dict(
        state_dir=state,
        usage_path=state_root / "usage" / "usage.jsonl",
        fleet_runner=fleet_runner,
        gh_runner=gh_runner,
        now_fn=lambda: FIXED_NOW,
        stale_after_s=1800,
    )
    defaults.update(overrides)
    return collector.Collector(**defaults)


def validated(doc) -> None:
    VALIDATOR.validate(doc, VALIDATOR.load(SNAPSHOT_SCHEMA))


# --------------------------------------------------------------------- schema


class TestSnapshotSchema:
    def test_schema_contract_loads_and_ids_correctly(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        assert schema["properties"]["schema"]["const"] == "rizzstack.observability/snapshot/1"
        # The live contract is the collector's own section list: ten
        # sections, read dynamically so a section added to the collector
        # must reach the schema (and this test) in the same change - a
        # hardcoded tuple drifted the moment bottlenecks shipped.
        assert len(collector.SECTION_NAMES) == 10
        for name in collector.SECTION_NAMES:
            assert name in schema["properties"], name
        # The schema requires exactly the live ten minus bottlenecks and
        # decisions: both are always emitted by this collector but stay
        # optional in the schema for documents emitted before they existed.
        required = set(schema["required"]) - {"schema", "generated_at", "collector", "degraded"}
        assert required <= set(collector.SECTION_NAMES), required - set(collector.SECTION_NAMES)
        optional = set(collector.SECTION_NAMES) - required
        assert optional == {"bottlenecks", "decisions"}, optional
        assert all(name in schema["properties"] for name in optional)

    def test_every_record_carries_schema_and_generated_at(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)

        def assert_envelope(node: dict) -> None:
            if "properties" in node and "schema" in node.get("properties", {}):
                props = node["properties"]
                if "generated_at" in props:
                    assert props["schema"].get("const") == "rizzstack.observability/snapshot/1"
                    assert "common.schema.json" in json.dumps(props["generated_at"])
            for value in node.values():
                if isinstance(value, dict):
                    assert_envelope(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            assert_envelope(item)

        assert_envelope(schema)

    def test_all_unavailable_snapshot_validates(self, tmp_path: Path) -> None:
        snap = collector.Collector(
            fleet_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        assert snap["degraded"] == list(collector.SECTION_NAMES)
        emitted = set(snap) - {"schema", "generated_at", "collector", "degraded"}
        assert emitted == set(collector.SECTION_NAMES)
        for name in collector.SECTION_NAMES:
            body = snap[name]
            # The strict never-live-with-empty invariant: a section with no
            # source is unavailable with a non-empty error - never live,
            # never silently empty.
            assert body["status"] == "unavailable", (name, body)
            assert body["error"], (name, body)
        assert all(snap[name]["status"] != "live" for name in collector.SECTION_NAMES)

    def test_unrecognized_section_or_row_is_rejected(self) -> None:
        base = collector.Collector(now_fn=lambda: FIXED_NOW).build_snapshot()
        bad = copy.deepcopy(base)
        bad["teleport"] = {}
        with pytest.raises(SchemaError):
            validated(bad)
        bad = copy.deepcopy(base)
        bad["fleet"]["attempts"].append({"schema": "rizzstack.observability/snapshot/1"})
        with pytest.raises(SchemaError):
            validated(bad)


# ------------------------------------------------------------ fixture sections


class TestFixtureSnapshot:
    @pytest.fixture()
    def snapshot(self, tmp_path: Path) -> dict:
        snap = fixture_collector(tmp_path).build_snapshot()
        validated(snap)
        return snap

    def test_all_sections_live(self, snapshot: dict) -> None:
        assert snapshot["degraded"] == []
        for name in collector.SECTION_NAMES:
            assert snapshot[name]["status"] == "live", (name, snapshot[name].get("error"))

    def test_fleet_reflects_cli_states(self, snapshot: dict) -> None:
        attempts = snapshot["fleet"]["attempts"]
        by_id = {row["attempt_id"]: row for row in attempts}
        assert by_id["att_1"]["state"] == "running"
        assert by_id["att_1"]["repo"] == "mojomast/workflow"
        assert by_id["att_1"]["route"] == "go"
        # An unrecognized CLI label normalizes to unknown and keeps its label.
        assert by_id["att_9"]["state"] == "unknown"
        assert by_id["att_9"]["detail"] == "warp-drive"
        # In-flight is the collector's own count over the rows it read:
        # att_1 is the only active row (att_9 is unknown), so the CLI
        # status tally of 2 is never parroted over rows that contradict it.
        assert snapshot["fleet"]["in_flight"] == 1
        # The CLI status bee_cap is launcher configuration, not an observed
        # fleet fact: the fleet section never surfaces it, even though the
        # status payload reported 12 this run.
        assert snapshot["fleet"]["bee_cap"] is None

    def test_pipeline_reflects_task_states_and_reasons(self, snapshot: dict) -> None:
        counts = snapshot["pipeline"]["counts"]
        assert counts["accepted"] == 1
        assert counts["failed"] == 1
        assert counts["rejected"] == 1
        assert counts["running"] == 1
        jobs = {job["job_id"]: job for job in snapshot["pipeline"]["jobs"]}
        failed = next(t for t in jobs["job_20261113_a"]["tasks"] if t["task_id"] == "T2")
        assert failed["state"] == "failed"
        assert "verify suite exited 1" in failed["reason"]
        reasons = {row["reason"] for row in snapshot["pipeline"]["escalations"]}
        assert "needs_agent" in reasons
        assert "approval_required" in reasons
        assert {row["task_id"] for row in snapshot["pipeline"]["blockers"]} == {"T2"}
        assert all(
            row["job_id"] in ("job_20261113_a", "job_20261113_b")
            for row in snapshot["pipeline"]["blockers"]
        )

    def test_backlog_reflects_queue(self, snapshot: dict) -> None:
        counts = snapshot["backlog"]["counts"]
        assert counts == {"running": 1, "blocked": 1, "queued": 1}
        features = {f["feature_id"]: f for f in snapshot["backlog"]["features"]}
        assert features["feat_obs_dashboards"]["status"] == "blocked"
        assert features["feat_obs_dashboards"]["depends_on"] == ["feat_obs_snapshot"]

    def test_failures_from_verify_results(self, snapshot: dict) -> None:
        rows = snapshot["failures"]["failures"]
        assert len(rows) == 1
        row = rows[0]
        assert row["attempt_id"] == "att_2"
        assert row["class"] == "regression"
        assert row["code"] == "verify_suite_failed"
        assert row["retryable"] is True
        assert snapshot["failures"]["counts"] == {"regression": 1}
        # att_1 succeeded: it must not appear as a failure.
        assert all(r["attempt_id"] != "att_1" for r in rows)

    def test_health_quota_and_scheduler_liveness(self, snapshot: dict) -> None:
        scheduler = snapshot["health"]["scheduler"]
        assert scheduler["liveness"] == "live"
        assert scheduler["alive"] is True
        assert scheduler["last_event_age_s"] == 120
        kinds = {row["kind"] for row in snapshot["health"]["quota"]}
        assert {"go_allowance", "deepseek_credit", "bees_in_flight"} <= kinds
        go = next(r for r in snapshot["health"]["quota"] if r["kind"] == "go_allowance")
        assert go["value"] == 82.0
        assert go["status"] == "low"
        # Health keeps deriving from the row-derived fleet count and from
        # the CLI status bee_cap the fleet section itself never surfaces.
        assert snapshot["health"]["bees_in_flight"] == 1
        assert snapshot["health"]["bee_cap"] == 12

    def test_usage_aggregates_and_preserves_unknowns(self, snapshot: dict) -> None:
        totals = snapshot["usage"]["totals"]
        # Five parsed records, but att_2 has every token field null: it is a
        # record, not a usage-bearing request.
        assert totals["requests"] == 4
        assert snapshot["usage"]["source"]["record_count"] == 5
        assert totals["input_tokens"] == 1700
        assert totals["output_tokens"] == 850
        assert totals["total_tokens"] == 2550
        assert totals["cost_usd"] == 0.02
        assert totals["tokens_status"] == "known"
        assert totals["cost_status"] == "partial"
        # Three usage-bearing rows carry no cost; att_2 is zero-token and null-cost.
        assert totals["unknown_cost_records"] == 3
        assert totals["http_429_count"] == 2
        assert totals["fallback_count"] == 1
        assert snapshot["usage"]["source"]["parse_errors"] == 1
        by_model = {(row["model"], row["provider"]): row for row in snapshot["usage"]["by_model"]}
        assert set(by_model) == {
            ("deepseek-v4.1-flash", "deepseek"),
            ("go-worker-large", "go"),
        }
        go_row = by_model[("go-worker-large", "go")]
        assert go_row["input_tokens"] is None
        assert go_row["cost_usd"] is None
        assert go_row["cost_status"] == "unknown"
        by_repo = {row["repo"]: row for row in snapshot["usage"]["by_repo"]}
        assert by_repo["mojomast/workflow"]["requests"] == 3
        # Records without a repository slug are preserved under one sentinel.
        assert by_repo["unknown/unknown"]["requests"] == 1

    def test_totals_requests_counts_only_usage_bearing_rows(self, tmp_path: Path) -> None:
        ledger = tmp_path / "usage.jsonl"
        records = [
            {"ts": "2026-11-16T09:00:00Z", "role": "coordinator",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": None, "output_tokens": None, "total_tokens": None,
             "cost_usd": None},
            {"ts": "2026-11-16T09:01:00Z", "role": "coordinator",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
             "cost_usd": None},
            {"ts": "2026-11-16T09:02:00Z", "role": "coordinator",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": None, "output_tokens": 0, "total_tokens": None,
             "cost_usd": None},
            {"ts": "2026-11-16T09:03:00Z", "role": "work",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "cost_usd": 0.01, "repo": "mojomast/workflow"},
        ]
        ledger.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        body, _ = collector.Collector(usage_path=ledger).usage_section()
        totals = body["totals"]
        assert body["status"] == "live"
        assert totals["requests"] == 1
        assert body["source"]["record_count"] == 4
        # Zero-token rows are records, not unpriced requests.
        assert totals["unknown_cost_records"] == 0
        # The one usage-bearing row's totals are unchanged.
        assert (totals["input_tokens"], totals["output_tokens"], totals["total_tokens"],
                totals["cost_usd"]) == (10, 5, 15, 0.01)

    def test_totals_requests_zero_for_an_all_zero_token_ledger(self, tmp_path: Path) -> None:
        ledger = tmp_path / "usage.jsonl"
        records = [
            {"ts": f"2026-11-16T09:0{i}:00Z", "role": "coordinator",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": None, "output_tokens": None, "total_tokens": None,
             "cost_usd": None}
            for i in range(5)
        ]
        ledger.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        body, _ = collector.Collector(usage_path=ledger).usage_section()
        totals = body["totals"]
        assert body["status"] == "live"
        assert totals["requests"] == 0
        assert body["source"]["record_count"] == 5
        assert (totals["input_tokens"], totals["output_tokens"], totals["total_tokens"],
                totals["cost_usd"]) == (None, None, None, None)
        assert totals["unknown_cost_records"] == 0

    def test_tokens_status_scopes_numerator_to_usage_bearing_rows(self, tmp_path: Path) -> None:
        ledger = tmp_path / "usage.jsonl"
        records = [
            {"ts": "2026-11-16T09:00:00Z", "role": "work",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "cost_usd": None},
            # An explicit 0/0/0 row is a record, not a request; its zeros must
            # not inflate the token numerator past the usage-bearing requests.
            {"ts": "2026-11-16T09:01:00Z", "role": "coordinator",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
             "cost_usd": None},
        ]
        ledger.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        body, _ = collector.Collector(usage_path=ledger).usage_section()
        totals = body["totals"]
        assert totals["requests"] == 1
        assert body["source"]["record_count"] == 2
        assert totals["tokens_status"] == "known"

    def test_cost_status_scopes_priced_numerator_to_usage_bearing_rows(self, tmp_path: Path) -> None:
        ledger = tmp_path / "usage.jsonl"
        records = [
            # Priced usage-bearing request.
            {"ts": "2026-11-16T09:00:00Z", "role": "work",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "cost_usd": 0.01},
            # Unpriced usage-bearing request.
            {"ts": "2026-11-16T09:01:00Z", "role": "verify",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
             "cost_usd": None},
            # Zero-token row carrying a numeric cost: it contributes money to
            # the total but must not make the priced counter claim coverage.
            {"ts": "2026-11-16T09:02:00Z", "role": "coordinator",
             "served_model": "deepseek-v4.1-flash", "route": "deepseek",
             "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
             "cost_usd": 0.02},
        ]
        ledger.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        body, _ = collector.Collector(usage_path=ledger).usage_section()
        totals = body["totals"]
        assert totals["requests"] == 2
        assert body["source"]["record_count"] == 3
        assert totals["unknown_cost_records"] == 1
        assert totals["cost_status"] == "partial"
        assert totals["cost_usd"] == 0.03

    def test_bucket_requests_still_count_records_seen(self, snapshot: dict) -> None:
        usage = snapshot["usage"]
        totals = usage["totals"]
        source = usage["source"]
        by_model = {(row["model"], row["provider"]): row for row in usage["by_model"]}
        go_row = by_model[("go-worker-large", "go")]
        # att_2 is zero-token and null-cost, yet its bucket still counts the record.
        assert go_row["requests"] == 1
        assert go_row["total_tokens"] is None
        # Totals exclude it: the disclosed divergence is deliberate.
        assert totals["requests"] == 4
        assert sum(row["requests"] for row in usage["by_model"]) == source["record_count"] == 5
        assert sum(row["requests"] for row in usage["by_repo"]) == source["record_count"] == 5

    def test_alerts_fire_from_thresholds(self, snapshot: dict) -> None:
        keys = {row["key"] for row in snapshot["alerts"]["active"]}
        assert "go_allowance_pct_used" in keys
        assert "deepseek_balance_below_usd" in keys
        assert all(row["severity"] == "warn" for row in snapshot["alerts"]["active"])
        # One alert per threshold key and resource label, not one per record.
        deepseek_alerts = [r for r in snapshot["alerts"]["active"] if r["key"] == "deepseek_balance_below_usd"]
        assert len(deepseek_alerts) == 1
        assert deepseek_alerts[0]["observed"] == 3.4  # latest of two balance readings
        go_alert = next(r for r in snapshot["alerts"]["active"] if r["key"] == "go_allowance_pct_used")
        assert go_alert["observed"] == 82.0
        assert go_alert["threshold"] == 80

    def test_quota_recovery_clears_only_the_recovered_resource(self, tmp_path: Path) -> None:
        ledger = tmp_path / "usage.jsonl"
        records = [
            {"ts": "2026-11-16T09:00:00Z", "go_label": "go-1", "go_allowance_used_pct": 90,
             "deepseek_balance_usd": 2},
            {"ts": "2026-11-16T09:20:00Z", "go_label": "go-1", "go_allowance_used_pct": 89},
            {"ts": "2026-11-16T09:20:00Z", "go_label": "go-1", "go_allowance_used_pct": 5,
             "deepseek_balance_usd": 12},
            # Late arrival and undated hint must not replace a newer dated observation.
            {"ts": "2026-11-16T09:10:00Z", "go_label": "go-1", "go_allowance_used_pct": 85},
            {"deepseek_balance_usd": 1},
            # Without timestamps, use the last reading for this label.
            {"go_label": "go-2", "go_allowance_used_pct": 10},
            {"go_label": "go-2", "go_allowance_used_pct": 95},
        ]
        ledger.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        snap = fixture_collector(tmp_path, usage_path=ledger).build_snapshot()
        validated(snap)

        hints = [
            (r["kind"], r["resource_id"], r["value"]) for r in snap["health"]["quota"]
            if r["kind"] != "bees_in_flight"
        ]
        assert sorted(hints) == [
            ("deepseek_credit", None, 12), ("go_allowance", "go-1", 5), ("go_allowance", "go-2", 95)
        ]
        quota_alerts = [
            (r["key"], r["observed"]) for r in snap["alerts"]["active"]
            if r["key"] in ("deepseek_balance_below_usd", "go_allowance_pct_used")
        ]
        assert quota_alerts == [("go_allowance_pct_used", 95)]
        # Quota hints carry no token counts, so none of these rows is a request.
        assert snap["usage"]["totals"]["requests"] == 0
        assert snap["usage"]["source"]["record_count"] == len(records)

    def test_orbit_ledger_cost_and_observed_total(self, tmp_path: Path) -> None:
        ledger = tmp_path / "usage.jsonl"
        records = [
            {"schema_version": "bee.usage/v1", "cost_usd_list": 0.125, "cost_status": "estimated",
             "usage_status": "known", "ts_end": "2026-11-16T09:00:00Z", "usage_raw": {"total": 20},
             "go_allowance": {"pct_used": 87.5, "pct_source": "opencode.allowance"},
             "input_tokens": 10, "output_tokens": 5, "project": "mojomast/workflow"},
            {"schema_version": "bee.usage/v1", "cost_usd_list": None, "cost_status": "unknown",
             "input_tokens": None, "output_tokens": None, "usage_status": "partial", "usage_raw": {"total": 0},
             "ts_end": "2026-11-16T09:30:00Z", "go_allowance": {"pct_used": 0.05, "pct_source": "derived_list_price"},
             "project": "another-feature"},
        ]
        ledger.write_text("\n".join(map(json.dumps, records)))
        source = fixture_collector(tmp_path, usage_path=ledger)
        body, summary = source.usage_section()
        assert body["totals"]["cost_usd"] == summary["today_cost_usd"] == 0.125
        # The null-cost row resolves total_tokens 0, so it is not usage-bearing.
        assert body["totals"]["unknown_cost_records"] == 0
        assert [q["value"] for q in summary["quota_rows"]] == [87.5]
        assert body["totals"]["total_tokens"] == 20
        unassigned = next(row for row in body["by_repo"] if row["repo"] == "unknown/unknown")
        assert (unassigned["total_tokens"], unassigned["tokens_status"]) == (0, "partial")
        assert unassigned["input_tokens"] is None and unassigned["cost_usd"] is None

    def test_snapshot_contains_no_credential_shaped_material(self, snapshot: dict) -> None:
        dumped = json.dumps(snapshot)
        for marker in ("ghp_", "sk-", "BEGIN PRIVATE", "bearer "):
            assert marker not in dumped


# ------------------------------------------------------------------ degradation


class TestDegradation:
    def test_invalid_usage_number_does_not_discard_other_observations(self, tmp_path: Path) -> None:
        ledger = tmp_path / "usage.jsonl"
        # A JSON exponent outside the float range, a fractional count, and
        # a large but valid integer must not break or round the snapshot.
        ledger.write_text('{"cost_usd_list":1e999,"http_429_count":1e999,"input_tokens":-1,"output_tokens":0.5}\n'
                          '{"cost_usd_list":0,"input_tokens":9007199254740993,"output_tokens":0}\n')
        body, _ = collector.Collector(usage_path=ledger).usage_section()
        totals = body["totals"]
        assert totals["requests"] == 1
        assert (totals["input_tokens"], totals["output_tokens"], totals["tokens_status"]) == (9007199254740993, 0, "known")
        assert (totals["cost_usd"], totals["cost_status"], totals["http_429_count"]) == (0.0, "known", 0)

    def test_ledger_read_error_does_not_publish_partial_aggregates(self, tmp_path, monkeypatch) -> None:
        def interrupted(_path):
            yield {"cost_usd_list": 1, "go_allowance_used_pct": 95}
            raise OSError("fixture stream interrupted")

        monkeypatch.setattr(collector, "jsonl_rows", interrupted)
        body, summary = collector.Collector(usage_path=tmp_path / "usage.jsonl").usage_section()
        assert (body["status"], body["error"]) == ("unavailable", "source_unreadable")
        assert body["totals"]["cost_usd"] is None and not summary["quota_rows"]

    def test_missing_sources_degrade_with_stale_markers(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty-state"
        empty.mkdir()
        snap = collector.Collector(
            state_dir=empty,
            usage_path=tmp_path / "nope.jsonl",
            fleet_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        # Every source is missing so every source-backed section degrades.
        # decisions is the deliberate exception: an absent decisions
        # directory is a genuine zero (no request raised), so it stays live
        # with an empty requests list instead of pretending to be unknown.
        assert set(snap["degraded"]) == set(collector.SECTION_NAMES) - {"decisions"}
        assert (snap["decisions"]["status"], snap["decisions"]["requests"]) == ("live", [])
        assert snap["pipeline"]["error"] == "source_missing"
        assert snap["pipeline"]["jobs"] == []
        assert snap["failures"]["error"] == "source_missing"
        assert snap["health"]["scheduler"]["liveness"] == "unavailable"

    def test_stale_marker_when_data_is_old(self, tmp_path: Path) -> None:
        state_root = freeze_state(tmp_path)
        state = state_root / "state"
        later = FIXED_NOW + timedelta(hours=3)
        snap = collector.Collector(
            state_dir=state,
            usage_path=state_root / "usage" / "usage.jsonl",
            fleet_runner=lambda argv: (0, json.dumps({"attempts": []}), ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: later,
        ).build_snapshot()
        validated(snap)
        assert snap["usage"]["status"] == "stale"
        assert snap["pipeline"]["status"] == "stale"
        assert snap["health"]["scheduler"]["liveness"] == "stale"
        assert snap["health"]["status"] == "stale"
        assert snap["health"]["scheduler"]["alive"] is False

    def test_partial_sources_never_crash(self, tmp_path: Path) -> None:
        state_root = freeze_state(tmp_path)
        state = state_root / "state"
        (state / "jobs" / "broken.json").write_text("{not json", encoding="utf-8")
        (state / "verify-results" / "broken.json").write_text("[]", encoding="utf-8")
        (state_root / "usage" / "partial.jsonl").write_text(
            '{"schema_version": "bee.usage/v1", "served_model": "deepseek-v4.1-flash", "route": "deepseek", "input_tokens": 5, "cost_usd": null, "usage_status": "unknown"}\n'
            "garbage line\n",
            encoding="utf-8",
        )
        snap = collector.Collector(
            state_dir=state,
            usage_path=state_root / "usage" / "partial.jsonl",
            fleet_runner=lambda argv: (0, "this is not json at all", ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["attempts"] == []
        assert snap["usage"]["source"]["parse_errors"] == 1
        assert snap["usage"]["totals"]["requests"] == 1
        assert snap["usage"]["totals"]["cost_usd"] is None
        assert snap["usage"]["totals"]["cost_status"] == "unknown"
        # The readable job documents still contribute.
        assert snap["pipeline"]["counts"].get("accepted") == 1


# ------------------------------------------------------------------- fleet CLI


class TestFleetCli:
    def test_default_fleet_argv_shape(self) -> None:
        assert collector.default_fleet_argv("hermes", "attempts") == [
            "hermes",
            "bundlebees",
            "attempts",
        ]
        assert collector.default_fleet_argv("hermes", "status") == [
            "hermes",
            "bundlebees",
            "status",
        ]

    def test_fleet_unavailable_when_cli_refuses(self, tmp_path: Path) -> None:
        snap = fixture_collector(
            tmp_path,
            fleet_runner=lambda argv: (1, "", ""),
        ).build_snapshot()
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["error"] == "fleet_command_failed"
        assert snap["fleet"]["attempts"] == []
        assert snap["fleet"]["in_flight"] is None

    def test_real_subprocess_shell_out(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        hermes = bin_dir / "hermes"
        hermes.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            'args = sys.argv[1:]\n'
            'if "attempts" in args:\n'
            '    print(json.dumps({"attempts": [{"attempt_id": "att_1", "state": "verifying", "job_id": "job_20261113_a"}]}))\n'
            'elif "status" in args:\n'
            '    print(json.dumps({"in_flight": 1, "bee_cap": 12}))\n',
            encoding="utf-8",
        )
        hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        state_root = freeze_state(tmp_path)
        state = state_root / "state"
        c = collector.Collector(
            state_dir=state,
            usage_path=state_root / "usage" / "usage.jsonl",
            bundlebees_bin=str(hermes),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW,
        )
        snap = c.build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "live"
        assert snap["fleet"]["in_flight"] == 1
        # The real status payload reported bee_cap 12; the fleet section
        # never surfaces launcher configuration. The value still feeds the
        # health quota row (asserted in the fixture-snapshot tests).
        assert snap["fleet"]["bee_cap"] is None
        # verifying normalizes into the lifecycle-aligned working state
        assert snap["fleet"]["attempts"][0]["state"] == "working"


# ------------------------------------------------------------- injected clocks


class TestInjectedClock:
    """A non-datetime injected clock must never crash the build.

    The HTTP surface answers 500 when ``build_snapshot`` raises, and the
    pre-fix failure was real: an int epoch hit ``utc_now_string``'s
    ``astimezone`` as an ``AttributeError`` and the int-datetime mismatch
    raised ``TypeError`` at the ``_fleet_row`` staleness arithmetic. The
    collector normalizes the clock once instead (``as_utc_moment``): epoch
    seconds, naive and aware datetimes all become an aware UTC moment, and a
    value that is not a clock at all falls back to the real UTC clock.
    """

    @staticmethod
    def row_payload() -> dict:
        return {
            "attempts": [
                {
                    "attempt_id": "att_clock",
                    "state": "running",
                    "updated_at": "2026-11-16T09:00:00Z",
                }
            ]
        }

    def test_epoch_seconds_clock_builds_a_validating_snapshot(self, tmp_path: Path) -> None:
        state_root = freeze_state(tmp_path)
        snap = collector.Collector(
            state_dir=state_root / "state",
            usage_path=state_root / "usage" / "usage.jsonl",
            fleet_runner=lambda argv: (0, json.dumps(self.row_payload()), ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_EPOCH,
        ).build_snapshot()
        validated(snap)
        assert snap["generated_at"] == "2026-11-16T09:30:00Z"
        # Staleness ran against the normalized clock: the 30-minute-old row
        # is exactly at the threshold, so it stays running and live.
        assert snap["fleet"]["status"] == "live"
        assert snap["fleet"]["attempts"][0]["state"] == "running"

    def test_naive_datetime_clock_is_read_as_utc(self, tmp_path: Path) -> None:
        state_root = freeze_state(tmp_path)
        snap = collector.Collector(
            state_dir=state_root / "state",
            usage_path=state_root / "usage" / "usage.jsonl",
            fleet_runner=lambda argv: (0, json.dumps(self.row_payload()), ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: FIXED_NOW.replace(tzinfo=None),
        ).build_snapshot()
        validated(snap)
        assert snap["generated_at"] == "2026-11-16T09:30:00Z"
        assert snap["fleet"]["status"] == "live"

    def test_aware_non_utc_clock_is_normalized_to_utc(self, tmp_path: Path) -> None:
        state_root = freeze_state(tmp_path)
        shifted = FIXED_NOW.astimezone(timezone(timedelta(hours=2)))
        assert shifted.utcoffset() == timedelta(hours=2)
        snap = collector.Collector(
            state_dir=state_root / "state",
            usage_path=state_root / "usage" / "usage.jsonl",
            fleet_runner=lambda argv: (0, json.dumps(self.row_payload()), ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: shifted,
        ).build_snapshot()
        validated(snap)
        assert snap["generated_at"] == "2026-11-16T09:30:00Z"

    def test_non_clock_value_falls_back_to_the_real_utc_clock(self, tmp_path: Path) -> None:
        state_root = freeze_state(tmp_path)
        before = datetime.now(timezone.utc)
        snap = collector.Collector(
            state_dir=state_root / "state",
            usage_path=state_root / "usage" / "usage.jsonl",
            fleet_runner=lambda argv: (0, json.dumps(self.row_payload()), ""),
            gh_runner=lambda argv: (1, "", ""),
            now_fn=lambda: "not-a-clock",
        ).build_snapshot()
        after = datetime.now(timezone.utc)
        validated(snap)
        generated = collector.parse_ts(snap["generated_at"])
        assert generated is not None
        assert before - timedelta(seconds=1) <= generated <= after + timedelta(seconds=1)

    def test_fleet_row_boundary_normalizes_the_clock(self) -> None:
        c = collector.Collector(now_fn=lambda: FIXED_NOW)
        raw = {
            "attempt_id": "att_clock",
            "state": "running",
            "updated_at": "2026-11-16T07:00:00Z",
        }
        # Epoch seconds and a naive datetime each reach the staleness
        # arithmetic through the boundary normalization: both demote the
        # 2.5-hour-old active row exactly as the aware clock does, instead
        # of raising TypeError on the subtraction.
        for moment in (FIXED_EPOCH, FIXED_NOW.replace(tzinfo=None)):
            row = c._fleet_row(raw, "2026-11-16T09:30:00Z", moment)
            assert row["state"] == "unknown", moment
            assert row["detail"] == "running", moment
        fresh = c._fleet_row(
            dict(raw, updated_at="2026-11-16T09:29:00Z"), "2026-11-16T09:30:00Z", FIXED_EPOCH
        )
        assert fresh["state"] == "running"
        assert fresh["detail"] is None


# ---------------------------------------------------------------------- ci/gh


class TestCiSection:
    @staticmethod
    def gh_runner(script: dict) -> collector.Runner:
        def runner(argv):
            joined = " ".join(argv)
            if " pr checks " in f" {joined} " or ("checks" in argv):
                number = argv[argv.index("checks") + 1]
                out = script["checks"].get(number, [])
                return 0, json.dumps(out), ""
            if "list" in argv:
                repo = argv[argv.index("--repo") + 1]
                return 0, json.dumps(script["list"].get(repo, [])), ""
            return 1, "", ""

        return runner

    def test_ci_states_from_gh(self, tmp_path: Path) -> None:
        script = {
            "list": {
                "mojomast/workflow": [
                    {
                        "number": 7,
                        "headRefName": "contrib/hermes-bees",
                        "state": "OPEN",
                        "statusCheckRollup": [
                            {"name": "unit tests", "state": "SUCCESS"},
                            {"name": "lint", "state": "FAILURE"},
                        ],
                    },
                    {
                        "number": 9,
                        "headRefName": "feat/x",
                        "state": "OPEN",
                        "statusCheckRollup": [],
                    },
                ],
                "mojomast/bundlebees": [
                    {
                        "number": 12,
                        "headRefName": "feat/metrics",
                        "state": "OPEN",
                        "statusCheckRollup": [{"name": "suite", "state": "SUCCESS"}],
                    }
                ],
            },
            "checks": {"9": [{"name": "browser checks", "state": "PENDING"}]},
        }
        state_root = freeze_state(tmp_path)
        state = state_root / "state"
        snap = collector.Collector(
            state_dir=state,
            usage_path=state_root / "usage" / "usage.jsonl",
            fleet_runner=lambda argv: (0, json.dumps({"attempts": []}), ""),
            gh_runner=self.gh_runner(script),
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        assert snap["ci"]["status"] == "live"
        repos = {row["repo"]: row for row in snap["ci"]["repos"]}
        assert repos["mojomast/workflow"]["ci_state"] == "mixed"
        assert repos["mojomast/workflow"]["open_prs"] == 2
        assert repos["mojomast/workflow"]["failing_check_names"] == ["lint"]
        assert repos["mojomast/bundlebees"]["ci_state"] == "passing"
        prs = {(row["repo"], row["number"]): row for row in snap["ci"]["prs"]}
        assert prs[("mojomast/workflow", 7)]["ci_state"] == "mixed"
        assert prs[("mojomast/workflow", 7)]["failing_check_names"] == ["lint"]
        assert prs[("mojomast/workflow", 9)]["ci_state"] == "pending"
        assert prs[("mojomast/workflow", 9)]["failing_check_names"] == []
        assert prs[("mojomast/workflow", 7)]["head_branch"] == "contrib/hermes-bees"

    def test_ci_unavailable_when_gh_fails(self, tmp_path: Path) -> None:
        snap = fixture_collector(
            tmp_path,
            gh_runner=lambda argv: (1, "", ""),
        ).build_snapshot()
        assert snap["ci"]["status"] == "unavailable"
        assert snap["ci"]["error"] == "ci_command_failed"

    def test_repos_come_from_jobs_and_flags(self, tmp_path: Path) -> None:
        seen: list[list[str]] = []

        def runner(argv):
            seen.append(list(argv))
            return 1, "", ""

        state_root = freeze_state(tmp_path)
        state = state_root / "state"
        collector.Collector(
            state_dir=state,
            usage_path=state_root / "usage" / "usage.jsonl",
            repos=["mojomast/orbitdesktop"],
            fleet_runner=lambda argv: (0, json.dumps({"attempts": []}), ""),
            gh_runner=runner,
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        requested = [argv[argv.index("--repo") + 1] for argv in seen if "--repo" in argv]
        assert set(requested) == {
            "mojomast/workflow",
            "mojomast/bundlebees",
            "mojomast/orbitdesktop",
        }


# ------------------------------------------------------------------- read-only


class TestReadOnly:
    def test_collector_writes_nothing(self, tmp_path: Path) -> None:
        def inventory(root: Path) -> dict:
            out = {}
            for path in sorted(root.rglob("*")):
                st = path.stat()
                out[str(path.relative_to(root))] = (st.st_mtime_ns, st.st_size, st.st_mode)
            return out

        state_root = freeze_state(tmp_path)
        before = inventory(state_root)
        c = fixture_collector(tmp_path)
        c.build_snapshot()
        c.build_snapshot()
        assert inventory(state_root) == before


# ------------------------------------------------------------------- serving


class TestHttpServing:
    CREDENTIAL_PARTS = ("rizz", "stack", "-obs-", "cred", "1")

    @property
    def credential(self) -> str:
        return "".join(self.CREDENTIAL_PARTS)

    def bearer(self, value: str) -> str:
        return "Bearer " + value

    @pytest.fixture()
    def server(self, tmp_path: Path):
        snap_collector = fixture_collector(tmp_path)
        srv = collector.make_server(
            "127.0.0.1",
            0,
            snap_collector.build_snapshot,
            self.credential,
        )
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        yield srv
        srv.shutdown()
        srv.server_close()

    def url(self, srv, path: str = "/") -> str:
        host, port = srv.server_address[:2]
        return f"http://{host}:{port}{path}"

    def test_requires_bearer(self, server) -> None:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(self.url(server), timeout=5)
        assert excinfo.value.code == 401
        assert excinfo.value.read() == b"unauthorized"

    def test_wrong_credential_is_refused_without_echo(self, server) -> None:
        request = urllib.request.Request(
            self.url(server),
            headers={"Authorization": self.bearer(self.credential + "x")},
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(request, timeout=5)
        assert excinfo.value.code == 401
        body = excinfo.value.read().decode()
        assert self.credential not in body

    def test_serves_validating_snapshot(self, server) -> None:
        request = urllib.request.Request(
            self.url(server),
            headers={"Authorization": self.bearer(self.credential)},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("application/json")
            doc = json.load(response)
        validated(doc)
        assert doc["schema"] == "rizzstack.observability/snapshot/1"

    def test_unknown_path_is_404(self, server) -> None:
        request = urllib.request.Request(
            self.url(server, "/elsewhere"),
            headers={"Authorization": self.bearer(self.credential)},
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(request, timeout=5)
        assert excinfo.value.code == 404

    def test_requests_are_not_logged(self, server, capsys) -> None:
        for headers in ({}, {"Authorization": self.bearer(self.credential)}):
            request = urllib.request.Request(self.url(server), headers=headers)
            try:
                urllib.request.urlopen(request, timeout=5)
            except urllib.error.HTTPError:
                pass
        captured = capsys.readouterr()
        assert self.credential not in (captured.out + captured.err)
        assert (captured.out + captured.err).strip() == ""

    def test_refuses_non_loopback_bind(self) -> None:
        with pytest.raises(ValueError):
            collector.make_server("0.0.0.0", 0, lambda: {}, self.credential)


class TestCredentialResolution:
    def test_credential_file_wins_and_env_is_used(self, tmp_path: Path, monkeypatch) -> None:
        args = collector.build_parser().parse_args([])
        monkeypatch.delenv("RIZZSTACK_OBS_TOKEN", raising=False)
        assert collector.resolve_credential(args) is None
        monkeypatch.setenv("RIZZSTACK_OBS_TOKEN", "".join(("env", "-", "cred")))
        assert collector.resolve_credential(args) == "env-cred"
        cred_path = tmp_path / "serving.cred"
        cred_path.write_text("".join(("file", "-", "cred")), encoding="utf-8")
        args = collector.build_parser().parse_args(["--bearer-token-file", str(cred_path)])
        assert collector.resolve_credential(args) == "file-cred"


# ----------------------------------------------------------------------- CLI


class TestCli:
    def test_print_mode_emits_validating_snapshot(self, tmp_path: Path) -> None:
        state_root = freeze_state(tmp_path)
        state = state_root / "state"
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "contrib" / "rizzstack-observability" / "collector.py"),
                "--state-dir",
                str(state),
                "--usage",
                str(state_root / "usage" / "usage.jsonl"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        validated(doc)
        assert doc["collector"]["name"] == "rizzstack-obs-collector"

    def test_serve_without_credential_refuses_to_start(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("RIZZSTACK_OBS_TOKEN", raising=False)
        env = {k: v for k, v in os.environ.items() if k != "RIZZSTACK_OBS_TOKEN"}
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "contrib" / "rizzstack-observability" / "collector.py"),
                "--serve",
                "--port",
                "0",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
            env=env,
        )
        assert proc.returncode == 2
        assert "refusing" in proc.stderr

    def test_existing_observability_suite_still_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "observability/tests"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(ROOT),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


if __name__ == "__main__":
    unittest.main()
