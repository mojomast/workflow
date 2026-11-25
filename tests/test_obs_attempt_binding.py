"""Hive "Unknown" fixes: kanban backlog, lease-bound task ids, wave pipeline (RED-first).

Contracts pinned here (all read-only):

* Fleet rows: ``started_at`` falls back to the CLI ``created_at``; ``repo``
  falls back to the ``project`` label only when it names exactly one
  configured ``--repo`` slug; ``task_id`` comes from the CLI row, else the
  signed dispatch lease (``task_id``, else brief ``task_id``/``label``); a null
  ``route`` is filled from the coordinator's launcher-reported route record
  (``attempt-routes/<id>.json``) only when its route equals the explicit
  provider prefix of its model.
* Backlog: with ``--kanban-board`` configured, the board is read through the
  public ``hermes kanban --board SLUG list --json`` CLI. Open cards become
  features (ready -> queued, running -> running, review -> ready_for_review,
  blocked/todo/scheduled -> blocked, triage -> needs_approval); done and
  archived cards are not backlog. A stale queue file no longer makes the
  section stale when every board answered; a board that cannot be read
  never yields a live section.
* Pipeline: fresh lease-bound attempts are grouped into one observed job per
  (wave, project), one task per task id (latest attempt wins), so current
  wave work keeps the section live. Derived tasks add no blockers.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))

from validate import Validator  # noqa: E402

NOW = datetime(2026, 11, 24, 20, 0, 0, tzinfo=timezone.utc)


def _load():
    spec = importlib.util.spec_from_file_location(
        "rizzstack_obs_collector_binding", ROOT / "contrib" / "rizzstack-observability" / "collector.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = _load()
VALIDATOR = Validator(ROOT / "observability" / "schemas")


def stamp(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def sealed_job(body: dict) -> dict:
    mac = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"body": body, "mac": mac}


def make_state(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    (state / "leases").mkdir(parents=True)
    os.chmod(state, 0o700)
    return state


def lease(state: Path, attempt_id: str, **brief) -> None:
    record = {"version": 1, "attempt_id": attempt_id, "created_at": stamp(30), "brief": brief, "mac": "x"}
    if "task_id_top" in brief:
        record["task_id"] = brief.pop("task_id_top")
    (state / "leases" / f"{attempt_id}.json").write_text(json.dumps(record), encoding="utf-8")


def route_record(state: Path, attempt_id: str, route, model) -> None:
    root = state / "attempt-routes"
    root.mkdir(exist_ok=True, mode=0o700)
    (root / f"{attempt_id}.json").write_text(json.dumps({
        "schema": "bundlebees.attempt-route/1", "attempt_id": attempt_id, "route": route,
        "model": model, "observed_at": stamp(1), "source": "launcher"}), encoding="utf-8")


def runner_for(rows, *, boards=None, board_code=0):
    boards = boards or {}

    def runner(argv):
        argv = list(argv)
        if argv[1:3] == ["bundlebees", "attempts"]:
            return 0, json.dumps({"attempts": rows}), ""
        if argv[1:3] == ["bundlebees", "status"]:
            return 0, json.dumps({"bee_cap": 12, "in_flight": 1, "in_flight_attempts": []}), ""
        if argv[1] == "kanban":
            assert argv[2] == "--board" and argv[4:] == ["list", "--json"], argv
            if board_code:
                return board_code, "", "boom"
            return 0, json.dumps(boards.get(argv[3], [])), ""
        raise AssertionError(argv)

    return runner


def build(tmp_path, rows, *, state=None, boards=None, board_code=0, kanban_boards=(), repos=()):
    run = runner_for(rows, boards=boards, board_code=board_code)
    col = collector.Collector(
        state_dir=state, now_fn=lambda: NOW, stale_after_s=43200, fleet_runner=run,
        kanban_runner=run, kanban_boards=kanban_boards, repos=repos, cli_workers=1,
    )
    snap = col.build_snapshot()
    VALIDATOR.validate(snap, VALIDATOR.load("snapshot.schema.json"))
    return snap


def row(attempt_id, state="dispatched", **extra):
    base = {"attempt_id": attempt_id, "branch": "feat/x", "created_at": stamp(30), "job_id": None,
            "model": None, "project": None, "repo": None, "route": None, "state": state,
            "updated_at": stamp(30), "attributed_model": None}
    base.update(extra)
    return base


# ----------------------------------------------------------------- fleet rows


def test_started_at_falls_back_to_created_at(tmp_path):
    snap = build(tmp_path, [row("att_a1")])
    assert snap["fleet"]["attempts"][0]["started_at"] == stamp(30)


def test_project_maps_to_a_single_configured_repo_only(tmp_path):
    snap = build(tmp_path, [row("att_a1", project="bundlebees"), row("att_a2", project="uirizz")],
                 repos=["mojomast/bundlebees", "mojomast/hyvv"])
    by_id = {r["attempt_id"]: r for r in snap["fleet"]["attempts"]}
    assert by_id["att_a1"]["repo"] == "mojomast/bundlebees"
    assert by_id["att_a2"]["repo"] is None


def test_task_id_comes_from_the_lease_label_when_the_cli_has_none(tmp_path):
    state = make_state(tmp_path)
    lease(state, "att_b1", label="wa-a1b", wave="A", project="bundlebees")
    lease(state, "att_b2", label="wa-a1b", task_id="t_1234abcd")
    lease(state, "att_b3", label="x", task_id_top="t_top")
    lease(state, "att_b4", label="../../etc")
    snap = build(tmp_path, [row("att_b1"), row("att_b2"), row("att_b3"), row("att_b4"),
                            row("att_b5", task_id="cli-task")], state=state)
    by_id = {r["attempt_id"]: r for r in snap["fleet"]["attempts"]}
    assert by_id["att_b1"]["task_id"] == "wa-a1b"
    assert by_id["att_b2"]["task_id"] == "t_1234abcd"
    assert by_id["att_b3"]["task_id"] == "t_top"
    assert by_id["att_b4"]["task_id"] is None
    assert by_id["att_b5"]["task_id"] == "cli-task"


def test_a_symlinked_lease_is_never_read(tmp_path):
    state = make_state(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"attempt_id": "att_c1", "brief": {"label": "leak"}}))
    (state / "leases" / "att_c1.json").symlink_to(outside)
    snap = build(tmp_path, [row("att_c1")], state=state)
    assert snap["fleet"]["attempts"][0]["task_id"] is None


def test_reported_route_fills_a_null_route_only_when_consistent(tmp_path):
    state = make_state(tmp_path)
    route_record(state, "att_d1", "nous", "nous:hy4-flash")
    route_record(state, "att_d2", "go", "nous:hy4-flash")  # inconsistent: refused
    route_record(state, "att_d3", "nous", "nous:hy4-flash")
    snap = build(tmp_path, [row("att_d1"), row("att_d2"), row("att_d3", route="zoo")], state=state)
    by_id = {r["attempt_id"]: r for r in snap["fleet"]["attempts"]}
    assert by_id["att_d1"]["route"] == "nous"
    assert by_id["att_d2"]["route"] is None
    assert by_id["att_d3"]["route"] == "zoo"  # the CLI's own route wins


# -------------------------------------------------------------------- backlog


BOARD = [
    {"id": "t_ready001", "status": "ready", "title": "a"},
    {"id": "t_run00001", "status": "running", "title": "b"},
    {"id": "t_review01", "status": "review", "title": "c"},
    {"id": "t_todo0001", "status": "todo", "title": "d"},
    {"id": "t_triage01", "status": "triage", "title": "e"},
    {"id": "t_done0001", "status": "done", "title": "f"},
    {"id": "t_arch0001", "status": "archived", "title": "g"},
    {"id": "../bad", "status": "ready", "title": "h"},
]


def test_kanban_board_feeds_a_live_backlog_even_with_a_stale_queue_file(tmp_path):
    state = make_state(tmp_path)
    queue = state / "queue.json"
    queue.write_text(json.dumps({"features": [{"feature_id": "old", "status": "blocked"}]}))
    old = (NOW - timedelta(days=6)).timestamp()
    os.utime(queue, (old, old))
    snap = build(tmp_path, [], state=state, boards={"rizzstack-t1634": BOARD},
                 kanban_boards=["rizzstack-t1634"])
    backlog = snap["backlog"]
    assert backlog["status"] == "live" and backlog["error"] is None
    status = {f["feature_id"]: f["status"] for f in backlog["features"]}
    assert status == {"t_ready001": "queued", "t_run00001": "running", "t_review01": "ready_for_review",
                      "t_todo0001": "blocked", "t_triage01": "needs_approval"}
    assert backlog["counts"] == {"queued": 1, "running": 1, "ready_for_review": 1, "blocked": 1,
                                 "needs_approval": 1}
    assert "backlog" not in snap["degraded"]
    # The board's ready card is eligible work for the reconciler invariant.
    assert snap["bottlenecks"]["invariant"]["ready"] == 1


def test_an_unreadable_board_never_yields_a_live_backlog(tmp_path):
    state = make_state(tmp_path)
    snap = build(tmp_path, [], state=state, board_code=1, kanban_boards=["rizzstack-t1634"])
    assert snap["backlog"]["status"] != "live"
    assert snap["backlog"]["error"] == "kanban_unavailable"


def test_without_a_board_the_queue_file_logic_is_unchanged(tmp_path):
    state = make_state(tmp_path)
    queue = state / "queue.json"
    queue.write_text(json.dumps({"features": [{"feature_id": "f1", "status": "queued"}]}))
    old = (NOW - timedelta(days=6)).timestamp()
    os.utime(queue, (old, old))
    snap = build(tmp_path, [], state=state)
    assert snap["backlog"]["status"] == "stale"
    assert snap["backlog"]["error"] == "queue_older_than_threshold"


# ------------------------------------------------------------------- pipeline


def test_fresh_wave_attempts_keep_the_pipeline_live(tmp_path):
    state = make_state(tmp_path)
    (state / "jobs").mkdir()
    job = state / "jobs" / "old-job.json"
    job.write_text(json.dumps(sealed_job({"job_id": "old-job", "goal": {}, "tasks": [{"task_id": "T1", "state": "accepted"}]})))
    old = (NOW - timedelta(days=6)).timestamp()
    os.utime(job, (old, old))
    lease(state, "att_e1", label="wa-a1", wave="A", project="bundlebees")
    lease(state, "att_e2", label="wa-a1", wave="A", project="bundlebees")
    lease(state, "att_e3", label="wa-hy-1", wave="A", project="hyvv")
    lease(state, "att_e4", label="wa-old", wave="A", project="hyvv")
    rows = [
        row("att_e1", "failed", updated_at=stamp(50)),
        row("att_e2", "dispatched", updated_at=stamp(5)),
        row("att_e3", "verified", updated_at=stamp(10)),
        row("att_e4", "verified", updated_at=stamp(60 * 24 * 3)),  # outside the window
    ]
    snap = build(tmp_path, rows, state=state, repos=["mojomast/bundlebees", "mojomast/hyvv"])
    pipeline = snap["pipeline"]
    assert pipeline["status"] == "live" and pipeline["error"] is None
    jobs = {j["job_id"]: j for j in pipeline["jobs"]}
    assert set(jobs) == {"old-job", "wave-A-bundlebees", "wave-A-hyvv"}
    bb = jobs["wave-A-bundlebees"]
    assert bb["repo"] == "mojomast/bundlebees"
    assert [(t["task_id"], t["state"], t["attempts_count"]) for t in bb["tasks"]] == [("wa-a1", "dispatched", 2)]
    assert [(t["task_id"], t["state"]) for t in jobs["wave-A-hyvv"]["tasks"]] == [("wa-hy-1", "verified")]
    # Derived observations are not job-document blockers.
    assert all(b["job_id"] == "old-job" for b in pipeline["blockers"])


def test_without_fresh_attempts_the_stale_job_store_stays_stale(tmp_path):
    state = make_state(tmp_path)
    (state / "jobs").mkdir()
    job = state / "jobs" / "old-job.json"
    job.write_text(json.dumps(sealed_job({"job_id": "old-job", "goal": {}, "tasks": [{"task_id": "T1", "state": "accepted"}]})))
    old = (NOW - timedelta(days=6)).timestamp()
    os.utime(job, (old, old))
    snap = build(tmp_path, [], state=state)
    assert snap["pipeline"]["status"] == "stale"
