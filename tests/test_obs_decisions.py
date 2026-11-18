"""Tests for the observability snapshot's owner-decisions section.

The section is sourced from the existing durable queue
(bundlebees_plugin/decision_queue.py, rizzstack.owner-decision/1): the tests
raise real requests through that queue and read the collector's produced
snapshot. All digests and nonces are computed at runtime.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))

from validate import Validator  # noqa: E402

FIXED_NOW = datetime(2026, 11, 16, 9, 30, 0, tzinfo=timezone.utc)
FIXED_STRING = "2026-11-16T09:30:00Z"
SNAPSHOT_SCHEMA = "snapshot.schema.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_queue = load_module(
    "decision_queue_for_obs", ROOT / "bundlebees_plugin" / "decision_queue.py"
)
collector = load_module(
    "rizzstack_obs_collector_for_decisions",
    ROOT / "contrib" / "rizzstack-observability" / "collector.py",
)
VALIDATOR = Validator(ROOT / "observability" / "schemas")


def gate_request(
    *,
    request_id: str = "odq_gate_1",
    subject: str = "release-gate",
    raised_at: str = "2026-11-16T09:25:00Z",
    **overrides,
) -> dict:
    """One sealed gate request, built by the queue module itself."""
    body = {
        "schema": "rizzstack.owner-decision/1",
        "record": "request",
        "request_id": request_id,
        "kind": "gate",
        "subject": subject,
        "question": f"Resolve the release gate for {subject}?",
        "evidence": [{"kind": "record", "reference": "jobs/odj_1.json"}],
        "raised_by": "decision_queue",
        "raised_at": raised_at,
    }
    body.update(overrides)
    return decision_queue.seal_request(body)


def make_queue(state_dir: Path) -> decision_queue.DecisionQueue:
    return decision_queue.DecisionQueue(state_dir, now=lambda: FIXED_STRING)


def failing_runner(argv):
    return 1, "", ""


def make_collector(state_dir: Path | None, **overrides) -> object:
    options = dict(
        state_dir=state_dir,
        fleet_runner=failing_runner,
        gh_runner=failing_runner,
        now_fn=lambda: FIXED_NOW,
    )
    options.update(overrides)
    return collector.Collector(**options)


def validated(doc: dict) -> None:
    VALIDATOR.validate(doc, VALIDATOR.load(SNAPSHOT_SCHEMA))


class TestDecisionsSection:
    def test_absent_decisions_directory_is_a_live_zero(self, tmp_path: Path) -> None:
        snap = make_collector(tmp_path).build_snapshot()
        validated(snap)
        assert snap["decisions"] == {
            "schema": "rizzstack.observability/snapshot/1",
            "generated_at": FIXED_STRING,
            "status": "live",
            "error": None,
            "records": [],
        }
        assert "decisions" not in snap["degraded"]

    def test_queued_request_appears_with_its_queue_fields(self, tmp_path: Path) -> None:
        make_queue(tmp_path).raise_request(gate_request())
        section = make_collector(tmp_path).decisions_section()
        assert section["status"] == "live"
        assert section["error"] is None
        assert section["records"] == [
            {
                "request_id": "odq_gate_1",
                "kind": "gate",
                "status": "pending",
                "subject": "release-gate",
            }
        ]
        # Nothing beyond the fields the queue stores is invented.
        assert set(section["records"][0]) == {"request_id", "kind", "status", "subject"}

    def test_status_follows_the_queue_lifecycle(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.raise_request(gate_request(request_id="odq_pending", subject="release-gate"))
        queue.raise_request(gate_request(request_id="odq_decided", subject="merge-gate"))
        queue.raise_request(gate_request(request_id="odq_applied", subject="deploy-gate"))
        queue.raise_request(gate_request(request_id="odq_withdrawn", subject="scope-gate"))
        queue.record_decision(
            "odq_applied",
            outcome="approve",
            decided_by="owner",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.deploy-gate.json",
        )
        queue.apply_ready()
        queue.record_decision(
            "odq_decided",
            outcome="approve",
            decided_by="owner",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.merge-gate.json",
        )
        queue.withdraw("odq_withdrawn")

        section = make_collector(tmp_path).decisions_section()
        statuses = {row["request_id"]: row["status"] for row in section["records"]}
        assert statuses == {
            "odq_pending": "pending",
            "odq_decided": "decided",
            "odq_applied": "applied",
            "odq_withdrawn": "withdrawn",
        }
        assert section["status"] == "live"

    def test_malformed_record_is_skipped_and_degrades(self, tmp_path: Path) -> None:
        make_queue(tmp_path).raise_request(gate_request())
        (tmp_path / "decisions" / "odq_broken.json").write_text(
            "{not json", encoding="utf-8"
        )
        section = make_collector(tmp_path).decisions_section()
        assert section["status"] == "unavailable"
        assert section["error"] == "decision_record_malformed"
        assert [row["request_id"] for row in section["records"]] == ["odq_gate_1"]

    def test_record_with_foreign_shape_is_never_a_fake_request(self, tmp_path: Path) -> None:
        decisions = tmp_path / "decisions"
        decisions.mkdir()
        (decisions / "odq_unknown.json").write_text(
            json.dumps({"request_id": "odq_unknown", "kind": "gate"}),
            encoding="utf-8",
        )
        section = make_collector(tmp_path).decisions_section()
        assert section["status"] == "unavailable"
        assert section["error"] == "decision_record_malformed"
        assert section["records"] == []

    def test_unreadable_decisions_directory_degrades(self, tmp_path: Path) -> None:
        (tmp_path / "decisions").write_text("not a directory", encoding="utf-8")
        snap = make_collector(tmp_path).build_snapshot()
        validated(snap)
        assert snap["decisions"]["status"] == "unavailable"
        assert snap["decisions"]["error"] == "decisions_unreadable"
        assert snap["decisions"]["records"] == []
        assert "decisions" in snap["degraded"]

    def test_stale_when_the_newest_request_is_old(self, tmp_path: Path) -> None:
        make_queue(tmp_path).raise_request(
            gate_request(raised_at="2026-11-16T08:00:00Z")
        )
        snap = make_collector(tmp_path, stale_after_s=60).build_snapshot()
        validated(snap)
        assert snap["decisions"]["status"] == "stale"
        assert snap["decisions"]["error"] == "decisions_older_than_threshold"
        assert len(snap["decisions"]["records"]) == 1
        assert "decisions" in snap["degraded"]

    def test_no_state_directory_is_unavailable_not_a_fake_zero(self) -> None:
        section = collector.Collector(now_fn=lambda: FIXED_NOW).decisions_section()
        assert section["status"] == "unavailable"
        assert section["error"] == "source_missing"
        assert section["records"] == []

    @pytest.mark.parametrize(
        ("state_dir_kind", "expected_status"),
        [("absent", "live"), ("unreadable", "unavailable")],
    )
    def test_degraded_lists_decisions_exactly_when_not_live(
        self, tmp_path: Path, state_dir_kind: str, expected_status: str
    ) -> None:
        if state_dir_kind == "unreadable":
            (tmp_path / "decisions").write_text("not a directory", encoding="utf-8")
        snap = make_collector(tmp_path).build_snapshot()
        validated(snap)
        assert snap["decisions"]["status"] == expected_status
        assert ("decisions" in snap["degraded"]) == (
            snap["decisions"]["status"] != "live"
        )

    def test_produced_snapshot_validates_with_a_queued_request(
        self, tmp_path: Path
    ) -> None:
        make_queue(tmp_path).raise_request(gate_request())
        snap = make_collector(tmp_path).build_snapshot()
        validated(snap)
        assert snap["decisions"]["records"][0]["request_id"] == "odq_gate_1"
