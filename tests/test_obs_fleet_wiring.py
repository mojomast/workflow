"""Fleet and health wiring tests for the real bundlebees CLI subcommands.

Packet 1 ships two read-only subcommands, ``<bin> bundlebees attempts`` and
``<bin> bundlebees status``. These tests pin the collector to that exact
invocation shape and to the documented degradation ladder: ``live`` with real
rows when the CLI works, ``unavailable`` with a precise generic error code
when it does not, ``stale`` when its newest output is older than the
freshness threshold, and ``null`` (never zero) for every count the CLI did
not report. All fixture output is synthetic; the leak stand-in constant is
named so it can never be mistaken for a real credential.
"""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))

from validate import SchemaError, Validator  # noqa: E402

FIXED_NOW = datetime(2026, 11, 16, 9, 30, 0, tzinfo=timezone.utc)

# Synthetic stand-in for credential-shaped material that must never reach a
# snapshot record, log line, or stderr echo. Deliberately not named after any
# credential word and deliberately not shaped like a provider literal.
LEAK_MARK = "leakmark-4f7a9c21-sentinel"
LEAK_URL = "https://" + "internal.example/" + LEAK_MARK

SCHEMA = "rizzstack.observability/snapshot/1"


def load_collector_module():
    spec = importlib.util.spec_from_file_location(
        "rizzstack_obs_collector_wiring",
        ROOT / "contrib" / "rizzstack-observability" / "collector.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_collector_module()
VALIDATOR = Validator(ROOT / "observability" / "schemas")


def validated(doc) -> None:
    VALIDATOR.validate(doc, VALIDATOR.load("snapshot.schema.json"))


def attempts_payload(*rows) -> dict:
    return {"attempts": list(rows)}


LIVE_ROW_FRESH = {
    "attempt_id": "att_live_1",
    "state": "running",
    "job_id": "job_20261116_a",
    "task_id": "T1",
    "repo": "mojomast/workflow",
    "branch": "feat/cli-attempts-status",
    "route": "go",
    "started_at": "2026-11-16T09:00:00Z",
    "updated_at": "2026-11-16T09:29:30Z",
    # Unmapped CLI fields must never be copied into a record.
    "note": "diagnostic " + LEAK_MARK,
}
LIVE_ROW_VERIFYING = {
    "attempt_id": "att_live_2",
    "state": "verifying",
    "job_id": "job_20261116_a",
    "task_id": "T2",
    "updated_at": "2026-11-16T09:28:00Z",
}
LIVE_ROW_UNKNOWN_STATE = {"attempt_id": "att_live_3", "state": "warp-drive"}
LIVE_ATTEMPTS = attempts_payload(LIVE_ROW_FRESH, LIVE_ROW_VERIFYING, LIVE_ROW_UNKNOWN_STATE)
LIVE_STATUS = {"summary": {"in_flight": 2, "bee_cap": 12}}


def cli_runner(attempts, status, *, attempts_code=0, status_code=0):
    """Runner that only answers the two packet-1 subcommands, by exact argv."""

    def runner(argv):
        if argv[1:] == ["bundlebees", "attempts"]:
            body = "" if attempts is None else json.dumps(attempts)
            return attempts_code, body, ""
        if argv[1:] == ["bundlebees", "status"]:
            body = "" if status is None else json.dumps(status)
            return status_code, body, ""
        raise AssertionError(f"unexpected fleet invocation: {list(argv)}")

    return runner


def wiring_collector(**overrides):
    defaults = dict(now_fn=lambda: FIXED_NOW, stale_after_s=1800)
    defaults.update(overrides)
    return collector.Collector(**defaults)


def fresh_metrics_dir(tmp_path: Path, *, age_s: int = 120) -> Path:
    state = tmp_path / "state"
    metrics = state / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    moment = FIXED_NOW.timestamp() - age_s
    stamp = datetime.fromtimestamp(moment, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (metrics / "run-1.jsonl").write_text(
        json.dumps({"seq": 1, "ts": stamp, "event": "dispatch"}) + "\n",
        encoding="utf-8",
    )
    return state


# ------------------------------------------------------------------- argv shape


class TestFleetArgvShape:
    def test_default_fleet_argv_uses_real_subcommands(self) -> None:
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

    def test_invocation_is_exactly_two_read_only_calls(self, tmp_path: Path) -> None:
        seen: list[list[str]] = []

        def runner(argv):
            seen.append(list(argv))
            return cli_runner(LIVE_ATTEMPTS, LIVE_STATUS)(argv)

        snap = wiring_collector(fleet_runner=runner).build_snapshot()
        validated(snap)
        assert seen == [
            ["hermes", "bundlebees", "attempts"],
            ["hermes", "bundlebees", "status"],
        ]


# ------------------------------------------------------------------- live CLI


class TestLiveCli:
    @pytest.fixture()
    def snapshot(self) -> dict:
        snap = wiring_collector(
            fleet_runner=cli_runner(LIVE_ATTEMPTS, LIVE_STATUS),
        ).build_snapshot()
        validated(snap)
        return snap

    def test_fleet_is_live_with_real_rows(self, snapshot: dict) -> None:
        fleet = snapshot["fleet"]
        assert fleet["status"] == "live"
        assert fleet["error"] is None
        by_id = {row["attempt_id"]: row for row in fleet["attempts"]}
        assert by_id["att_live_1"]["state"] == "running"
        assert by_id["att_live_1"]["repo"] == "mojomast/workflow"
        assert by_id["att_live_1"]["branch"] == "feat/cli-attempts-status"
        assert by_id["att_live_1"]["route"] == "go"
        assert by_id["att_live_1"]["started_at"] == "2026-11-16T09:00:00Z"
        assert by_id["att_live_1"]["updated_at"] == "2026-11-16T09:29:30Z"
        # verifying normalizes into the lifecycle-aligned working state
        assert by_id["att_live_2"]["state"] == "working"
        # An unrecognized CLI label stays unknown and keeps its raw label.
        assert by_id["att_live_3"]["state"] == "unknown"
        assert by_id["att_live_3"]["detail"] == "warp-drive"

    def test_counts_come_from_status_summary(self, snapshot: dict) -> None:
        assert snapshot["fleet"]["in_flight"] == 2
        assert snapshot["fleet"]["bee_cap"] == 12

    def test_unmapped_cli_fields_never_enter_the_snapshot(self, snapshot: dict) -> None:
        dumped = json.dumps(snapshot)
        assert LEAK_MARK not in dumped
        assert "internal.example" not in dumped

    def test_health_derives_quota_and_liveness_from_real_state(self, tmp_path: Path) -> None:
        state = fresh_metrics_dir(tmp_path)
        snap = wiring_collector(
            state_dir=state,
            fleet_runner=cli_runner(LIVE_ATTEMPTS, LIVE_STATUS),
        ).build_snapshot()
        validated(snap)
        health = snap["health"]
        assert health["status"] == "live"
        assert health["bees_in_flight"] == 2
        assert health["bee_cap"] == 12
        scheduler = health["scheduler"]
        assert scheduler["liveness"] == "live"
        assert scheduler["alive"] is True
        assert scheduler["last_event_age_s"] == 120
        bees = next(row for row in health["quota"] if row["kind"] == "bees_in_flight")
        assert bees["value"] == 2.0
        assert bees["cap"] == 12
        assert bees["remaining"] == 10
        assert bees["unit"] == "count"
        assert bees["status"] == "ok"


# --------------------------------------------------------------- degradation


class TestCliDegradation:
    def test_cli_missing_degrades_with_precise_error(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(None, None, attempts_code=127, status_code=127),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "unavailable"
        assert fleet["error"] == "fleet_cli_missing"
        assert fleet["attempts"] == []
        assert fleet["in_flight"] is None
        assert fleet["bee_cap"] is None
        # Unknown counts stay null downstream too: no row, no zero.
        assert snap["health"]["bees_in_flight"] is None
        assert snap["health"]["bee_cap"] is None
        assert all(row["kind"] != "bees_in_flight" for row in snap["health"]["quota"])

    def test_cli_missing_real_binary_degrades_with_precise_error(self, tmp_path: Path) -> None:
        state = fresh_metrics_dir(tmp_path)
        snap = wiring_collector(
            state_dir=state,
            bundlebees_bin=str(tmp_path / "no-such-hermes"),
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["error"] == "fleet_cli_missing"
        # Metrics are still readable, so health stays live without bee counts.
        assert snap["health"]["scheduler"]["liveness"] == "live"
        assert snap["health"]["bees_in_flight"] is None

    def test_cli_error_degrades_with_generic_error(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(None, None, attempts_code=1, status_code=1),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "unavailable"
        assert fleet["error"] == "fleet_command_failed"
        assert fleet["attempts"] == []
        assert fleet["in_flight"] is None
        assert fleet["bee_cap"] is None

    def test_cli_timeout_degrades_with_precise_error(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(None, None, attempts_code=124, status_code=124),
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["error"] == "fleet_cli_timeout"
        assert snap["fleet"]["in_flight"] is None

    def test_unparseable_output_degrades_with_precise_error(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner("fleet console is under maintenance", None),
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["error"] == "fleet_output_unparseable"
        assert snap["fleet"]["attempts"] == []
        assert snap["fleet"]["in_flight"] is None
        assert snap["fleet"]["bee_cap"] is None

    def test_stale_output_marks_stale_but_keeps_real_rows(self) -> None:
        stale_row = dict(LIVE_ROW_FRESH, updated_at="2026-11-16T07:00:00Z")
        snap = wiring_collector(
            fleet_runner=cli_runner(attempts_payload(stale_row), LIVE_STATUS),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "stale"
        assert fleet["error"] == "fleet_state_older_than_threshold"
        assert [row["attempt_id"] for row in fleet["attempts"]] == ["att_live_1"]
        # The reported counts are still the CLI's own numbers.
        assert fleet["in_flight"] == 2
        assert fleet["bee_cap"] == 12

    def test_missing_inputs_never_crash_and_never_fold_unknown_into_zero(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(None, None, attempts_code=127, status_code=127),
        ).build_snapshot()
        validated(snap)
        health = snap["health"]
        # No metrics and no quota inputs: the section degrades with a marker.
        assert health["status"] == "unavailable"
        assert health["error"] == "no_health_sources"
        assert health["scheduler"]["liveness"] == "unavailable"
        assert health["scheduler"]["alive"] is None
        assert health["bees_in_flight"] is None
        assert health["bee_cap"] is None


# --------------------------------------------------- partial CLI availability


class TestPartialCli:
    def test_status_subcommand_failure_keeps_rows_and_null_cap(self) -> None:
        done_row = {"attempt_id": "att_live_2", "state": "succeeded", "job_id": "job_20261116_a"}
        rows = attempts_payload(LIVE_ROW_FRESH, done_row)
        snap = wiring_collector(
            fleet_runner=cli_runner(rows, None, status_code=1),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "live"
        assert len(fleet["attempts"]) == 2
        # Derived from real rows: exactly one row is in an active state.
        assert fleet["in_flight"] == 1
        # Cap was never reported: it stays null, never zero.
        assert fleet["bee_cap"] is None
        bees = next(row for row in snap["health"]["quota"] if row["kind"] == "bees_in_flight")
        assert bees["value"] == 1.0
        assert bees["cap"] is None
        assert bees["remaining"] is None

    def test_summary_without_cap_falls_back_and_stays_null_where_unknown(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(LIVE_ATTEMPTS, {"summary": {"in_flight": 5}}),
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "live"
        assert snap["fleet"]["in_flight"] == 5
        assert snap["fleet"]["bee_cap"] is None

    def test_empty_attempts_is_genuine_zero_not_unknown(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(attempts_payload(), None, status_code=1),
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "live"
        assert snap["fleet"]["attempts"] == []
        assert snap["fleet"]["in_flight"] == 0
        assert snap["fleet"]["bee_cap"] is None

    def test_shape_mismatch_is_unavailable_not_zero(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner({"hello": "world"}, None),
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["error"] == "fleet_output_unparseable"
        assert snap["fleet"]["in_flight"] is None
        assert snap["fleet"]["bee_cap"] is None


# ------------------------------------------------------------- real subprocess


class TestRealSubprocess:
    def test_real_subprocess_uses_packet_one_subcommands(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        hermes = bin_dir / "hermes"
        script = (
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "mark = " + repr(LEAK_MARK) + "\n"
            "args = sys.argv[1:]\n"
            "if args == ['bundlebees', 'attempts']:\n"
            "    print(json.dumps({'attempts': [{"
            "'attempt_id': 'att_real_1', 'state': 'backoff', "
            "'job_id': 'job_20261116_r', "
            "'internal_note': 'diag ' + mark, "
            "'trace_url': 'https://' + 'internal.example/' + mark}]}))\n"
            "elif args == ['bundlebees', 'status']:\n"
            "    sys.stderr.write('diag ' + mark + chr(10))\n"
            "    print(json.dumps({'summary': {'in_flight': 1, 'bee_cap': 12}}))\n"
            "else:\n"
            "    sys.stderr.write('unknown invocation' + chr(10))\n"
            "    sys.exit(3)\n"
        )
        hermes.write_text(script, encoding="utf-8")
        hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        snap = wiring_collector(bundlebees_bin=str(hermes)).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "live"
        assert fleet["in_flight"] == 1
        assert fleet["bee_cap"] == 12
        assert fleet["attempts"][0]["state"] == "backoff"
        assert fleet["attempts"][0]["attempt_id"] == "att_real_1"
        dumped = json.dumps(snap)
        # Neither stderr from the CLI nor unmapped row fields may surface.
        assert LEAK_MARK not in dumped
        assert "internal.example" not in dumped

    def test_stderr_from_the_cli_is_never_copied(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        hermes = bin_dir / "hermes"
        hermes.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stderr.write(" + repr("traceback noise " + LEAK_MARK) + " + chr(10))\n"
            "sys.exit(4)\n",
            encoding="utf-8",
        )
        hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        snap = wiring_collector(bundlebees_bin=str(hermes)).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["error"] == "fleet_command_failed"
        dumped = json.dumps(snap)
        assert LEAK_MARK not in dumped
        assert "traceback noise" not in dumped
