"""Observability fleet/pipeline delta tests (rizzstack.observability/snapshot/1).

Four behaviors, each pinned RED-first against the collector:

1. the fleet section invokes the REAL read-only bundlebees subcommands,
   ``<bin> bundlebees attempts --state-dir DIR`` and
   ``<bin> bundlebees status --state-dir DIR``, scoped to the plugin state
   directory it was given; the ``bundlebees attempt op=...`` shape never
   existed and must never come back;
2. fleet rows carry ``branch`` (the model/title widening was reverted: a
   fleet attempt carries neither field, and the absence is pinned - not a
   null), and when the CLI cannot answer the fleet section falls back to
   the dispatch-lease store (``state_dir/leases/att_*.json``, newest 24)
   joined with the bee-landed states in the live
   ``state_dir/events/outbox/`` (the legacy ``state_dir/outbox/`` is still
   read);
3. fleet honesty: an ACTIVE-state row whose heartbeat is older than the
   staleness threshold is demoted to ``unknown`` and is not counted
   in-flight, and the CLI status ``bee_cap`` is not surfaced in the fleet
   section (the health and bottlenecks sections keep deriving from it);
4. the pipeline section emits the job ``title`` and ``summary`` from the
   goal and the task ``title`` from the first acceptance-criterion
   statement, scrubbed like every other free-text field.

Envelope unwrapping and the bottlenecks section (#42) are preserved: the
delta tests read job documents through the same envelope the reconciler
seals, and one assertion pins that the bottlenecks verify stage keeps its
capacity row.

All fixture data is synthetic; URLs in fixtures stand in for private
material and must never survive ``scrub()``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))

from validate import Validator  # noqa: E402

FIXED_NOW = datetime(2026, 11, 17, 9, 0, 0, tzinfo=timezone.utc)
FIXED_EPOCH = FIXED_NOW.timestamp()
STALE_AFTER_S = 1800


def load_collector_module():
    spec = importlib.util.spec_from_file_location(
        "rizzstack_obs_collector_delta",
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


def iso(seconds_before_now: float) -> str:
    moment = FIXED_NOW - timedelta(seconds=seconds_before_now)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp_mtime(path: Path, seconds_before_now: float) -> None:
    os.utime(path, (FIXED_EPOCH - seconds_before_now, FIXED_EPOCH - seconds_before_now))


def delta_collector(**overrides):
    defaults = dict(now_fn=lambda: FIXED_NOW, stale_after_s=STALE_AFTER_S)
    defaults.update(overrides)
    return collector.Collector(**defaults)


# ---------------------------------------------------------------- 1. real argv


class TestRealFleetSubcommands:
    def test_default_fleet_argv_scopes_the_real_subcommands_to_the_state_dir(self) -> None:
        state = Path("/tmp/opencode/example-plugin-state")
        assert collector.default_fleet_argv("hermes", "attempts", state) == [
            "hermes",
            "bundlebees",
            "attempts",
            "--state-dir",
            str(state),
        ]
        assert collector.default_fleet_argv("hermes", "status", state) == [
            "hermes",
            "bundlebees",
            "status",
            "--state-dir",
            str(state),
        ]

    def test_fleet_argv_never_uses_the_op_equals_shape(self) -> None:
        state = Path("/tmp/opencode/example-plugin-state")
        for op in ("attempts", "status"):
            argv = collector.default_fleet_argv("hermes", op, state)
            assert argv[1:3] == ["bundlebees", op]
            assert not any("op=" in part for part in argv)

    def test_fleet_section_invokes_both_real_subcommands_with_the_state_dir(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "plugin-state"
        state.mkdir()
        seen: list[list[str]] = []

        def runner(argv):
            seen.append(list(argv))
            if argv[-2:] == ["--state-dir", str(state)] and "attempts" in argv:
                return 0, json.dumps({"attempts": []}), ""
            if argv[-2:] == ["--state-dir", str(state)] and "status" in argv:
                return 0, json.dumps({"in_flight": 0}), ""
            raise AssertionError(f"unexpected fleet invocation: {list(argv)}")

        snap = delta_collector(state_dir=state, fleet_runner=runner).build_snapshot()
        validated(snap)
        assert seen == [
            ["hermes", "bundlebees", "attempts", "--state-dir", str(state)],
            ["hermes", "bundlebees", "status", "--state-dir", str(state)],
        ]
        assert snap["fleet"]["status"] == "live"


# --------------------------------------------------- 2. row fields + fallback


class TestFleetRowFields:
    def test_rows_carry_branch_and_never_model_or_title(self) -> None:
        row = collector.Collector()._fleet_row(
            {
                "attempt_id": "att_row",
                "state": "running",
                "branch": "feat/fleet-fallback",
                "model": "go",
                "title": "Add the dispatch-lease fallback",
                "job_id": "job_d1",
                "task_id": "T1",
                "updated_at": iso(60),
            },
            iso(0),
            FIXED_NOW,
        )
        assert row["branch"] == "feat/fleet-fallback"
        # The widened contract was reverted: model and title are not fleet
        # attempt fields at all. The source named both here and the row must
        # still drop them - absence, never a null placeholder.
        assert "model" not in row
        assert "title" not in row

    def test_row_free_text_from_the_source_never_surfaces(self, tmp_path: Path) -> None:
        def runner(argv):
            if "attempts" in argv:
                payload = {
                    "attempts": [
                        {
                            "attempt_id": "att_row",
                            "state": "running",
                            "branch": "feat/fleet-fallback",
                            "model": "go-worker-large",
                            "title": "see https://internal.example/one and \x07 bell",
                            "updated_at": iso(60),
                        }
                    ]
                }
                return 0, json.dumps(payload), ""
            return 0, json.dumps({"in_flight": 1}), ""

        snap = delta_collector(fleet_runner=runner).build_snapshot()
        validated(snap)
        row = snap["fleet"]["attempts"][0]
        assert "model" not in row
        assert "title" not in row
        dumped = json.dumps(snap)
        # Neither the dropped fields' free text nor its URL may leak through
        # any other carried field.
        assert "internal.example" not in dumped
        assert "\\u0007" not in dumped

    def test_fields_the_cli_does_not_report_stay_absent(self) -> None:
        row = collector.Collector()._fleet_row(
            {"attempt_id": "att_row", "state": "running", "updated_at": iso(60)},
            iso(0),
            FIXED_NOW,
        )
        assert row["branch"] is None
        assert "model" not in row
        assert "title" not in row


def write_lease(
    leases_dir: Path,
    attempt_id: str,
    *,
    title: str = "Wire the outbox join",
    branch: str = "feat/outbox-join",
    model: str | None = "deepseek",
    job_id: str = "job_d2",
    task_id: str = "T1",
    created_at: str | None = None,
    age_s: float = 60,
) -> Path:
    leases_dir.mkdir(parents=True, exist_ok=True)
    path = leases_dir / f"{attempt_id}.json"
    path.write_text(
        json.dumps(
            {
                "attempt_id": attempt_id,
                "job_id": job_id,
                "task_id": task_id,
                "title": title,
                "branch": branch,
                "model": model,
                "created_at": created_at or iso(age_s),
                "assigned_files": ["contrib/rizzstack-observability/collector.py"],
                "mac": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    stamp_mtime(path, age_s)
    return path


def write_landed_event(
    outbox_dir: Path,
    attempt_id: str,
    state: str,
    *,
    time: str | None = None,
    age_s: float = 30,
    job_id: str = "job_d2",
) -> Path:
    outbox_dir.mkdir(parents=True, exist_ok=True)
    path = outbox_dir / f"landed-{attempt_id}-{state}.json"
    path.write_text(
        json.dumps(
            {
                "specversion": "1.0",
                "id": "11111111-1111-4111-8111-%012d"
                % zlib.crc32((attempt_id + ":" + state).encode("utf-8")),
                "type": "rizzstack.bee.landed.v1",
                "source": "bundlebees-coordinator",
                "time": time or iso(age_s),
                "subject": attempt_id,
                "data": {
                    "schema": "rizzstack.bee-landed/1",
                    "feature_id": "feat_fleet_fallback",
                    "job_id": job_id,
                    "task_id": "T1",
                    "attempt_id": attempt_id,
                    "coordinator": {"identity": "test-coordinator"},
                    "backend": {"harness": "test-harness"},
                    "state": state,
                    "source_rev": "a" * 40,
                    "lease": {
                        "sha256": "b" * 64,
                        "assigned_files": ["contrib/rizzstack-observability/collector.py"],
                    },
                    "result": {"available": False},
                },
            }
        ),
        encoding="utf-8",
    )
    stamp_mtime(path, age_s)
    return path


def failing_cli(code: int = 1):
    def runner(argv):
        return code, "", ""

    return runner


class TestDispatchLeaseFallback:
    @pytest.fixture()
    def fallback_snapshot(self, tmp_path: Path) -> dict:
        state = tmp_path / "plugin-state"
        leases = state / "leases"
        outbox = state / "outbox"
        write_lease(leases, "att_fb1", title="Wire the outbox join", age_s=60)
        write_lease(leases, "att_fb2", title="Land the verify wave", age_s=120)
        write_lease(
            leases,
            "att_fb3",
            title="Dispatched without a landing",
            age_s=4 * STALE_AFTER_S,
        )
        write_lease(leases, "att_fb4", title="Fresh dispatch", age_s=90)
        write_landed_event(outbox, "att_fb1", "succeeded", age_s=30)
        write_landed_event(outbox, "att_fb2", "failed", age_s=45)
        (outbox / "garbage.json").write_text("{not json", encoding="utf-8")
        (leases / "att_broken.json").write_text("{not json", encoding="utf-8")
        snap = delta_collector(state_dir=state, fleet_runner=failing_cli()).build_snapshot()
        validated(snap)
        return snap

    def test_fleet_falls_back_to_lease_rows_when_the_cli_fails(
        self, fallback_snapshot: dict
    ) -> None:
        fleet = fallback_snapshot["fleet"]
        by_id = {row["attempt_id"]: row for row in fleet["attempts"]}
        assert set(by_id) == {"att_fb1", "att_fb2", "att_fb3", "att_fb4"}
        # A landing event supplies the terminal state for its attempt.
        assert by_id["att_fb1"]["state"] == "succeeded"
        assert by_id["att_fb2"]["state"] == "failed"
        # A lease alone proves dispatch: the lifecycle-aligned starting state.
        assert by_id["att_fb3"]["state"] == "unknown"
        assert by_id["att_fb3"]["detail"] == "dispatched"  # stale-active demotion
        assert by_id["att_fb4"]["state"] == "starting"
        # Lease context joins onto every row.
        assert by_id["att_fb1"]["branch"] == "feat/outbox-join"
        assert by_id["att_fb1"]["job_id"] == "job_d2"
        assert by_id["att_fb1"]["task_id"] == "T1"
        assert by_id["att_fb1"]["started_at"] == iso(60)
        # The lease record names a model and a title; the reverted contract
        # surfaces neither on a fleet attempt.
        assert "model" not in by_id["att_fb1"]
        assert "title" not in by_id["att_fb1"]

    def test_fallback_joins_landings_from_the_events_outbox(self, tmp_path: Path) -> None:
        state = tmp_path / "plugin-state"
        leases = state / "leases"
        write_lease(leases, "att_ev1", title="Join the live outbox", age_s=60)
        write_lease(leases, "att_ev2", title="Land a failed attempt", age_s=60)
        write_landed_event(state / "events" / "outbox", "att_ev1", "succeeded", age_s=30)
        write_landed_event(state / "events" / "outbox", "att_ev2", "failed", age_s=30)
        snap = delta_collector(state_dir=state, fleet_runner=failing_cli()).build_snapshot()
        validated(snap)
        by_id = {row["attempt_id"]: row for row in snap["fleet"]["attempts"]}
        assert by_id["att_ev1"]["state"] == "succeeded"
        assert by_id["att_ev2"]["state"] == "failed"
        assert snap["fleet"]["in_flight"] == 0

    def test_fallback_marks_the_section_stale_and_names_the_source(
        self, fallback_snapshot: dict
    ) -> None:
        fleet = fallback_snapshot["fleet"]
        assert fleet["status"] == "stale"
        assert fleet["error"] == "fleet_command_failed"
        assert fleet["source"] == "dispatch_leases"
        # Only the fresh lease row (att_fb4) is in flight: the two landed
        # rows are terminal and att_fb3 was demoted by the staleness rule.
        assert fleet["in_flight"] == 1
        assert "fleet" in fallback_snapshot["degraded"]

    def test_newest_twenty_four_leases_bound_the_fallback(self, tmp_path: Path) -> None:
        state = tmp_path / "plugin-state"
        leases = state / "leases"
        for index in range(26):
            write_lease(leases, f"att_fb{index:02d}", title=f"Lease {index}", age_s=index * 10)
        snap = delta_collector(state_dir=state, fleet_runner=failing_cli()).build_snapshot()
        validated(snap)
        ids = {row["attempt_id"] for row in snap["fleet"]["attempts"]}
        assert len(ids) == 24
        assert "att_fb00" in ids  # newest lease
        assert "att_fb24" not in ids  # oldest leases beyond the bound
        assert "att_fb25" not in ids

    def test_unreadable_lease_records_are_skipped_not_fatal(self, tmp_path: Path) -> None:
        state = tmp_path / "plugin-state"
        leases = state / "leases"
        write_lease(leases, "att_ok1", age_s=30)
        (leases / "att_broken.json").write_text("{not json", encoding="utf-8")
        snap = delta_collector(state_dir=state, fleet_runner=failing_cli()).build_snapshot()
        validated(snap)
        assert [row["attempt_id"] for row in snap["fleet"]["attempts"]] == ["att_ok1"]

    def test_cli_rows_win_over_the_fallback_when_the_cli_answers(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "plugin-state"
        write_lease(state / "leases", "att_fb1", age_s=30)
        write_landed_event(state / "outbox", "att_fb1", "succeeded", age_s=30)

        def runner(argv):
            if "attempts" in argv:
                return 0, json.dumps({"attempts": [
                    {"attempt_id": "att_cli", "state": "running", "updated_at": iso(30)}
                ]}), ""
            return 0, json.dumps({"in_flight": 1}), ""

        snap = delta_collector(state_dir=state, fleet_runner=runner).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["source"] == "cli"
        assert fleet["status"] == "live"
        assert [row["attempt_id"] for row in fleet["attempts"]] == ["att_cli"]

    def test_no_state_dir_and_no_cli_stays_unavailable_with_empty_rows(self) -> None:
        snap = delta_collector(fleet_runner=failing_cli()).build_snapshot()
        validated(snap)
        fleet = snap["fleet"]
        assert fleet["status"] == "unavailable"
        assert fleet["error"] == "fleet_command_failed"
        assert fleet["attempts"] == []
        assert fleet["in_flight"] is None
        assert fleet["source"] == "cli"

    def test_state_dir_without_leases_and_no_cli_stays_unavailable(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "plugin-state"
        state.mkdir()
        snap = delta_collector(state_dir=state, fleet_runner=failing_cli()).build_snapshot()
        validated(snap)
        assert snap["fleet"]["status"] == "unavailable"
        assert snap["fleet"]["attempts"] == []


# ------------------------------------------------------------ 3. fleet honesty


class TestFleetHonesty:
    @pytest.fixture()
    def honest_snapshot(self, tmp_path: Path) -> dict:
        def runner(argv):
            if "attempts" in argv:
                return 0, json.dumps({"attempts": [
                    {
                        "attempt_id": "att_fresh",
                        "state": "working",
                        "updated_at": iso(60),
                    },
                    {
                        "attempt_id": "att_stale",
                        "state": "running",
                        "updated_at": iso(2 * STALE_AFTER_S),
                    },
                ]}), ""
            # The launcher's own tally still counts the stale bee.
            return 0, json.dumps({"in_flight": 2, "bee_cap": 12}), ""

        snap = delta_collector(fleet_runner=runner).build_snapshot()
        validated(snap)
        return snap

    def test_stale_active_row_demotes_to_unknown_and_leaves_the_count(
        self, honest_snapshot: dict
    ) -> None:
        fleet = honest_snapshot["fleet"]
        by_id = {row["attempt_id"]: row for row in fleet["attempts"]}
        assert by_id["att_stale"]["state"] == "unknown"
        assert by_id["att_stale"]["detail"] == "running"
        # The fresh row stays exactly as the CLI reported it.
        assert by_id["att_fresh"]["state"] == "working"
        assert by_id["att_fresh"]["detail"] is None
        # The demoted row is not counted in-flight, and the collector's own
        # row-derived count stands even though the CLI tallied two.
        assert fleet["in_flight"] == 1

    def test_row_honesty_boundary_is_strictly_older_than_the_threshold(self) -> None:
        at_threshold = collector.Collector()._fleet_row(
            {"attempt_id": "att_edge", "state": "running", "updated_at": iso(STALE_AFTER_S)},
            iso(0),
            FIXED_NOW,
        )
        assert at_threshold["state"] == "running"
        past_threshold = collector.Collector()._fleet_row(
            {
                "attempt_id": "att_edge",
                "state": "running",
                "updated_at": iso(STALE_AFTER_S + 1),
            },
            iso(0),
            FIXED_NOW,
        )
        assert past_threshold["state"] == "unknown"
        assert past_threshold["detail"] == "running"

    def test_terminal_rows_are_never_demoted(self) -> None:
        row = collector.Collector()._fleet_row(
            {
                "attempt_id": "att_done",
                "state": "succeeded",
                "updated_at": iso(30 * 24 * 3600),
            },
            iso(0),
            FIXED_NOW,
        )
        assert row["state"] == "succeeded"
        assert row["detail"] is None

    def test_cli_status_bee_cap_is_not_surfaced_in_the_fleet_section(
        self, honest_snapshot: dict
    ) -> None:
        # The launcher reported bee_cap 12; the fleet section never surfaces
        # it (the field stays null). The health and bottlenecks sections
        # still derive from the value - see the preserve test below.
        assert honest_snapshot["fleet"]["bee_cap"] is None

    def test_health_and_bottlenecks_still_derive_from_the_cap(self, tmp_path: Path) -> None:
        def runner(argv):
            if "attempts" in argv:
                return 0, json.dumps({"attempts": [
                    {"attempt_id": "att_fresh", "state": "working", "updated_at": iso(60)}
                ]}), ""
            return 0, json.dumps({"in_flight": 1, "bee_cap": 12}), ""

        state = tmp_path / "plugin-state"
        metrics = state / "metrics"
        metrics.mkdir(parents=True)
        (metrics / "run-1.jsonl").write_text(
            json.dumps({"seq": 1, "ts": iso(60), "event": "dispatch"}) + "\n",
            encoding="utf-8",
        )
        snap = delta_collector(state_dir=state, fleet_runner=runner).build_snapshot()
        validated(snap)
        assert snap["health"]["bee_cap"] == 12
        bees = next(row for row in snap["health"]["quota"] if row["kind"] == "bees_in_flight")
        assert bees["cap"] == 12
        assert bees["remaining"] == 11
        verify = next(
            row for row in snap["bottlenecks"]["stages"] if row["stage"] == "verify"
        )
        assert verify["capacity"] == 12
        assert verify["capacity_source"] == "bee_cap"


# --------------------------------------------------------- 4. pipeline titles


HEX_REV = "5f4e3d2c1b0a9f8e7d6c5b4a39281706f5e4d3c2"


def title_job_body() -> dict:
    return {
        "job_id": "job_p1",
        "goal": {
            "title": "Fleet fallback view https://internal.example/one \x07tail",
            "summary": "Show the fleet from dispatch leases when the CLI is down",
            "repo": "mojomast/workflow",
            "base_rev": HEX_REV,
        },
        "tasks": [
            {
                "task_id": "T1",
                "state": "running",
                "objective": "the objective is not the title",
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "statement": "the fleet section falls back to dispatch leases "
                        "https://internal.example/two with \x07 noise " + "x" * 250,
                        "tests": ["tests/test_observability_snapshot.py"],
                    },
                    {
                        "id": "AC-2",
                        "statement": "second criterion never becomes the title",
                        "tests": [],
                    },
                ],
            },
            {
                "task_id": "T2",
                "state": "pending",
            },
        ],
    }


class TestPipelineTitles:
    @pytest.fixture()
    def titled_jobs(self, tmp_path: Path) -> dict:
        state = tmp_path / "plugin-state"
        jobs = state / "jobs"
        jobs.mkdir(parents=True)
        sealed = title_job_body()
        (jobs / "job_p1.json").write_text(
            json.dumps({"body": sealed, "mac": "0" * 64}), encoding="utf-8"
        )
        plain = title_job_body()
        plain["job_id"] = "job_p2"
        (jobs / "job_p2.json").write_text(json.dumps(plain), encoding="utf-8")

        def runner(argv):
            return 1, "", ""

        snap = delta_collector(state_dir=state, fleet_runner=runner).build_snapshot()
        validated(snap)
        return {job["job_id"]: job for job in snap["pipeline"]["jobs"]}

    def test_job_title_and_summary_come_from_the_goal(self, titled_jobs: dict) -> None:
        for job_id in ("job_p1", "job_p2"):
            job = titled_jobs[job_id]
            assert job["title"] == collector.scrub(
                "Fleet fallback view https://internal.example/one \x07tail"
            )
            assert job["summary"] == (
                "Show the fleet from dispatch leases when the CLI is down"
            )

    def test_task_title_is_the_first_acceptance_criterion_statement(
        self, titled_jobs: dict
    ) -> None:
        for job_id in ("job_p1", "job_p2"):
            tasks = {task["task_id"]: task for task in titled_jobs[job_id]["tasks"]}
            expected = collector.scrub(
                title_job_body()["tasks"][0]["acceptance_criteria"][0]["statement"]
            )
            assert tasks["T1"]["title"] == expected
            assert len(tasks["T1"]["title"]) <= 200
            assert "second criterion" not in (tasks["T1"]["title"] or "")
            # A task without criteria has no title; the objective is not used.
            assert tasks["T2"]["title"] is None

    def test_titles_are_scrubbed(self, titled_jobs: dict) -> None:
        dumped = json.dumps(titled_jobs)
        assert "internal.example" not in dumped
        assert "\\u0007" not in dumped

    def test_missing_goal_and_criteria_yield_null_titles(self, tmp_path: Path) -> None:
        state = tmp_path / "plugin-state"
        jobs = state / "jobs"
        jobs.mkdir(parents=True)
        (jobs / "job_bare.json").write_text(
            json.dumps({"job_id": "job_bare", "tasks": [{"task_id": "T1", "state": "pending"}]}),
            encoding="utf-8",
        )

        def runner(argv):
            return 1, "", ""

        snap = delta_collector(state_dir=state, fleet_runner=runner).build_snapshot()
        validated(snap)
        job = snap["pipeline"]["jobs"][0]
        assert job["title"] is None
        assert job["summary"] is None
        assert job["tasks"][0]["title"] is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


class TestModuleHeaderTruth:
    def test_module_header_names_the_live_events_outbox(self) -> None:
        """Pin review-wf-pr109 F1: the header must point at the live path.

        B111 corrected the three method docstrings; the module summary still
        sent a reader to the legacy ``outbox/`` as the landing directory.
        """

        header = " ".join((collector.__doc__ or "").split())
        assert "bee-landed events under ``events/outbox/``" in header
        assert "bee-landed events under ``outbox/``" not in header
        assert "(the legacy ``outbox/`` is still read)" in header

    def test_module_header_fallback_names_the_live_events_outbox(self) -> None:
        """Pin review-wf-pr110 F1: the fallback clause needs its own pin.

        The first header test's positive assertion matches the plugin-state
        bullet alone, so reverting only B113's fleet-fallback clause still
        passed. This test names that clause verbatim.
        """

        header = " ".join((collector.__doc__ or "").split())
        assert (
            "the fleet section falls back to the dispatch-lease store joined "
            "with the bee-landed outbox under ``events/outbox/`` and marks "
            "itself ``stale`` with ``source: dispatch_leases``"
        ) in header
        assert "joined with the bee-landed outbox and marks itself" not in header
