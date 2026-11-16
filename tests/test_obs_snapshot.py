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
        assert argv[1:] == ["bundlebees", "attempts"] or argv[1:] == [
            "bundlebees",
            "status",
        ], argv
        if "attempts" in argv[1:]:
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
        for section in (
            "fleet",
            "usage",
            "pipeline",
            "backlog",
            "ci",
            "failures",
            "health",
            "alerts",
        ):
            assert section in schema["properties"], section

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
        snap = collector.Collector(now_fn=lambda: FIXED_NOW).build_snapshot()
        validated(snap)
        assert snap["degraded"] == list(collector.SECTION_NAMES)
        for name in collector.SECTION_NAMES:
            body = snap[name]
            assert body["status"] == "unavailable"
            assert body["error"]

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
        assert snapshot["fleet"]["in_flight"] == 2
        assert snapshot["fleet"]["bee_cap"] == 12

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
        assert snapshot["health"]["bees_in_flight"] == 2
        assert snapshot["health"]["bee_cap"] == 12

    def test_usage_aggregates_and_preserves_unknowns(self, snapshot: dict) -> None:
        totals = snapshot["usage"]["totals"]
        assert totals["requests"] == 5
        assert totals["input_tokens"] == 1700
        assert totals["output_tokens"] == 850
        assert totals["total_tokens"] == 2550
        assert totals["cost_usd"] == 0.02
        assert totals["tokens_status"] == "partial"
        assert totals["cost_status"] == "partial"
        assert totals["unknown_cost_records"] == 4
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

    def test_alerts_fire_from_thresholds(self, snapshot: dict) -> None:
        keys = {row["key"] for row in snapshot["alerts"]["active"]}
        assert "go_allowance_pct_used" in keys
        assert "deepseek_balance_below_usd" in keys
        assert all(row["severity"] == "warn" for row in snapshot["alerts"]["active"])
        # One alert per threshold key and resource label, not one per record.
        deepseek_alerts = [r for r in snapshot["alerts"]["active"] if r["key"] == "deepseek_balance_below_usd"]
        assert len(deepseek_alerts) == 1
        go_alert = next(r for r in snapshot["alerts"]["active"] if r["key"] == "go_allowance_pct_used")
        assert go_alert["observed"] == 82.0
        assert go_alert["threshold"] == 80

    def test_snapshot_contains_no_credential_shaped_material(self, snapshot: dict) -> None:
        dumped = json.dumps(snapshot)
        for marker in ("ghp_", "sk-", "BEGIN PRIVATE", "bearer "):
            assert marker not in dumped


# ------------------------------------------------------------------ degradation


class TestDegradation:
    def test_missing_sources_degrade_with_stale_markers(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty-state"
        empty.mkdir()
        snap = collector.Collector(
            state_dir=empty,
            usage_path=tmp_path / "nope.jsonl",
            now_fn=lambda: FIXED_NOW,
        ).build_snapshot()
        validated(snap)
        assert set(snap["degraded"]) == set(collector.SECTION_NAMES)
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
        assert snap["fleet"]["bee_cap"] == 12
        # verifying normalizes into the lifecycle-aligned working state
        assert snap["fleet"]["attempts"][0]["state"] == "working"


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
