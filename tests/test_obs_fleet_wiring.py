"""Fleet and health wiring tests for the real bundlebees CLI subcommands.

Packet 1 ships two read-only subcommands, ``<bin> bundlebees attempts`` and
``<bin> bundlebees status``. These tests pin the collector to that exact
invocation shape and to the documented degradation ladder: ``live`` with real
rows when the CLI works, ``unavailable`` with a precise generic error code
when it does not, ``stale`` when its newest output is older than the
freshness threshold, and ``null`` (never zero) for every count the CLI did
not report. The live fixtures mirror the real shipped CLI shapes verbatim
(flat ``status`` payload with no ``summary`` wrapper; attempts rows carrying
only the four real states dispatched/verified/failed/accepted); synthetic and
malformed payloads are kept solely as degradation coverage. The leak
stand-in constant is named so it can never be mistaken for a real credential.
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


# Real shipped CLI shapes, captured verbatim from the merged bundlebees CLI
# (main ced3ba8): ``status`` is a FLAT payload (no ``summary`` wrapper) and
# attempts rows carry exactly the fields below, with the four states
# dispatched/verified/failed/accepted; in-flight is {dispatched, verified}.
REAL_STATUS = {
    "bee_cap": 12,
    "health": {
        "adapter": "orbit-loopback",
        "credential_configured": False,
        "launcher_url_configured": False,
    },
    "in_flight": 1,
    "in_flight_attempts": ["att-disp"],
}
REAL_ATTEMPTS_ROWS = [
    {
        "attempt_id": "att-disp",
        "branch": "feat/att-disp",
        "created_at": "2026-11-16T09:00:00Z",
        "model": "go",
        "project": "proj-a",
        "state": "dispatched",
        "updated_at": "2026-11-16T09:00:00Z",
    },
    {
        "attempt_id": "att-verif",
        "branch": "feat/att-verif",
        "created_at": "2026-11-16T09:05:00Z",
        "model": "deepseek",
        "project": "proj-a",
        "state": "verified",
        "updated_at": "2026-11-16T09:20:00Z",
    },
    {
        "attempt_id": "att-fail",
        "branch": "feat/att-fail",
        "created_at": "2026-11-16T09:06:00Z",
        "model": None,
        "project": None,
        "state": "failed",
        "updated_at": "2026-11-16T09:21:00Z",
    },
    {
        "attempt_id": "att-accept",
        "branch": "feat/att-accept",
        "created_at": "2026-11-16T09:07:00Z",
        "model": None,
        "project": None,
        "state": "accepted",
        "updated_at": "2026-11-16T09:21:30Z",
    },
]
REAL_ATTEMPTS = attempts_payload(*REAL_ATTEMPTS_ROWS)

# Kept synthetic rows, used only for degradation coverage: a state label no
# shipped CLI emits, plus unmapped diagnostic fields that must never surface.
UNKNOWN_STATE_ROW = {
    "attempt_id": "att-future",
    "state": "warp-drive",
    "note": "diagnostic " + LEAK_MARK,
    "trace_url": LEAK_URL,
}


def cli_runner(attempts, status, *, attempts_code=0, status_code=0, state_dir=None):
    """Runner that only answers the two packet-1 subcommands, by exact argv.

    The invocation is pinned in both directions: the subcommand must be one
    of the two real read-only ones, and the state directory on the wire must
    be exactly the one the collector was given. A collector with no state
    directory must send the bare subcommand - a ``--state-dir`` there would
    be an invented one, and is refused; a collector with one must forward
    it, and a missing one is refused just the same.
    """

    def runner(argv):
        if len(argv) < 3 or argv[1] != "bundlebees" or argv[2] not in ("attempts", "status"):
            raise AssertionError(f"unexpected fleet invocation: {list(argv)}")
        if state_dir is None:
            assert "--state-dir" not in argv, f"invented state dir: {list(argv)}"
        else:
            assert argv[-2:] == ["--state-dir", str(state_dir)], list(argv)
        if argv[2] == "attempts":
            body = "" if attempts is None else json.dumps(attempts)
            return attempts_code, body, ""
        body = "" if status is None else json.dumps(status)
        return status_code, body, ""

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
            return cli_runner(REAL_ATTEMPTS, REAL_STATUS)(argv)

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
            fleet_runner=cli_runner(REAL_ATTEMPTS, REAL_STATUS),
        ).build_snapshot()
        validated(snap)
        return snap

    def test_fleet_is_live_with_real_rows(self, snapshot: dict) -> None:
        fleet = snapshot["fleet"]
        assert fleet["status"] == "live"
        assert fleet["error"] is None
        by_id = {row["attempt_id"]: row for row in fleet["attempts"]}
        assert sorted(by_id) == ["att-accept", "att-disp", "att-fail", "att-verif"]
        # All four real CLI states map onto the frozen snapshot vocabulary.
        # dispatched is in flight; verified is a recorded outcome awaiting
        # acceptance, so it is neither working nor in flight.
        assert by_id["att-disp"]["state"] == "starting"
        assert by_id["att-verif"]["state"] == "verified"
        assert by_id["att-fail"]["state"] == "failed"
        assert by_id["att-accept"]["state"] == "accepted"
        # Mapped passthrough fields survive the real row shape.
        assert by_id["att-verif"]["branch"] == "feat/att-verif"
        assert by_id["att-verif"]["updated_at"] == "2026-11-16T09:20:00Z"
        # Fields the real rows never carry stay null, never invented.
        assert by_id["att-verif"]["repo"] is None
        assert by_id["att-verif"]["route"] is None
        # The CLI's created_at is the dispatch (lease) time; with no explicit
        # start it is the attempt's start (owner decision t1685u).
        assert by_id["att-verif"]["started_at"] == "2026-11-16T09:05:00Z"
        assert by_id["att-verif"]["detail"] is None

    def test_counts_come_from_flat_status_payload(self, snapshot: dict) -> None:
        assert snapshot["fleet"]["in_flight"] == 1
        # The CLI status reported bee_cap 12, but launcher configuration is
        # not an observed fleet fact: the fleet section never surfaces it -
        # suppressed even when the status payload carries it. The health
        # and bottlenecks sections still derive from the value (asserted in
        # the health test below).
        assert snapshot["fleet"]["bee_cap"] is None

    def test_unmapped_cli_fields_never_enter_the_snapshot(self, snapshot: dict) -> None:
        dumped = json.dumps(snapshot)
        # Only mapped fields cross into records: the rows' model/project/
        # created_at and the flat status payload's health/in_flight_attempts
        # are never copied through.
        assert "proj-a" not in dumped
        assert '"model"' not in dumped
        assert "created_at" not in dumped
        assert "orbit-loopback" not in dumped
        assert "in_flight_attempts" not in dumped
        # ...while the fields that are mapped do land.
        assert "feat/att-verif" in dumped

    def test_health_derives_quota_and_liveness_from_real_state(self, tmp_path: Path) -> None:
        state = fresh_metrics_dir(tmp_path)
        snap = wiring_collector(
            state_dir=state,
            fleet_runner=cli_runner(REAL_ATTEMPTS, REAL_STATUS, state_dir=state),
        ).build_snapshot()
        validated(snap)
        health = snap["health"]
        assert health["status"] == "live"
        # Only the dispatched attempt is an active bee; the verified one has
        # already finished.
        assert health["bees_in_flight"] == 1
        assert health["bee_cap"] == 12
        scheduler = health["scheduler"]
        assert scheduler["liveness"] == "live"
        assert scheduler["alive"] is True
        assert scheduler["last_event_age_s"] == 120
        bees = next(row for row in health["quota"] if row["kind"] == "bees_in_flight")
        assert bees["value"] == 1.0
        assert bees["cap"] == 12
        assert bees["remaining"] == 11
        assert bees["unit"] == "count"
        assert bees["status"] == "ok"


# ------------------------------------------------------------- verified state


class TestOutcomeStates:
    """``verified`` and ``expired`` are recorded outcomes, not work in progress.

    The bundlebees CLI stopped counting ``verified`` as in flight (a verify
    result means the bee finished and the result awaits acceptance) and started
    reporting ``expired`` for dispatches with no outcome past its TTL. Both must
    survive normalization as themselves -- never ``working`` (which reports a
    finished bee as active) and never ``unknown`` (which hides a known state).
    """

    def test_dispatched_is_still_active(self) -> None:
        collector_under_test = wiring_collector()
        assert collector_under_test._normalize_fleet_state("dispatched") == "starting"

    def test_verified_is_not_working(self) -> None:
        collector_under_test = wiring_collector()
        assert collector_under_test._normalize_fleet_state("verified") == "verified"

    def test_expired_survives_normalization(self) -> None:
        collector_under_test = wiring_collector()
        assert collector_under_test._normalize_fleet_state("expired") == "expired"

    def test_only_the_dispatched_row_is_in_flight_in_the_status_failure_fallback(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(REAL_ATTEMPTS, None, status_code=1),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "live"
        # att-disp is in flight. att-verif has a recorded outcome, so the
        # fallback must not count it as an active bee.
        assert fleet["in_flight"] == 1


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
        stale_row = dict(REAL_ATTEMPTS_ROWS[0], updated_at="2026-11-16T07:00:00Z")
        snap = wiring_collector(
            fleet_runner=cli_runner(attempts_payload(stale_row), REAL_STATUS),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "stale"
        assert fleet["error"] == "fleet_state_older_than_threshold"
        assert [row["attempt_id"] for row in fleet["attempts"]] == ["att-disp"]
        # The stale-active row was demoted to unknown, so the collector's
        # own row-derived count is 0 - the CLI's tally of 2 still counts a
        # bee the collector cannot vouch for, and is never parroted over
        # rows that contradict it.
        assert fleet["attempts"][0]["state"] == "unknown"
        assert fleet["attempts"][0]["detail"] == "dispatched"
        assert fleet["in_flight"] == 0
        # And the fleet section never surfaces the launcher's bee_cap.
        assert fleet["bee_cap"] is None

    def test_unrecognized_label_degrades_to_unknown_without_leaking(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(attempts_payload(UNKNOWN_STATE_ROW), None, status_code=1),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "live"
        # An unrecognized CLI label stays unknown and keeps its raw label.
        assert fleet["attempts"][0]["state"] == "unknown"
        assert fleet["attempts"][0]["detail"] == "warp-drive"
        # Unmapped diagnostic fields on the row never surface either.
        dumped = json.dumps(snap)
        assert LEAK_MARK not in dumped
        assert "internal.example" not in dumped

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
        snap = wiring_collector(
            fleet_runner=cli_runner(REAL_ATTEMPTS, None, status_code=1),
        ).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "live"
        assert len(fleet["attempts"]) == 4
        # Derived from real rows: only the dispatched row is active. The
        # verified row has an outcome recorded, so counting it would report a
        # finished bee as in flight.
        assert fleet["in_flight"] == 1
        # Cap was never reported: it stays null, never zero.
        assert fleet["bee_cap"] is None
        bees = next(row for row in snap["health"]["quota"] if row["kind"] == "bees_in_flight")
        assert bees["value"] == 1.0
        assert bees["cap"] is None
        assert bees["remaining"] is None

    def test_summary_without_cap_falls_back_and_stays_null_where_unknown(self) -> None:
        snap = wiring_collector(
            fleet_runner=cli_runner(REAL_ATTEMPTS, {"summary": {"in_flight": 5}}),
        ).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "live"
        # The status summary tallied 5, but the collector counts the rows it
        # just read: only the dispatched row is active (verified has an
        # outcome), and the CLI tally is never parroted over rows that
        # contradict it.
        assert snap["fleet"]["in_flight"] == 1
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
            "'attempt_id': 'att_real_1', 'state': 'dispatched', "
            "'job_id': 'job_20261116_r', "
            "'internal_note': 'diag ' + mark, "
            "'trace_url': 'https://' + 'internal.example/' + mark}]}))\n"
            "elif args == ['bundlebees', 'status']:\n"
            "    sys.stderr.write('diag ' + mark + chr(10))\n"
            "    print(json.dumps({'bee_cap': 12, "
            "'health': {'adapter': 'orbit-loopback', "
            "'credential_configured': False, 'launcher_url_configured': False}, "
            "'in_flight': 1, 'in_flight_attempts': ['att_real_1']}))\n"
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
        # The real status payload reported bee_cap 12; launcher configuration
        # is never surfaced by the fleet section - suppressed even when the
        # CLI reports it, never fabricated where unknown.
        assert fleet["bee_cap"] is None
        # dispatched renders as the lifecycle-aligned starting state.
        assert fleet["attempts"][0]["state"] == "starting"
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
