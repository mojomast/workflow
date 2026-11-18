"""Tests for the observability snapshot's owner-decisions section.

The section is sourced from the existing durable queue
(bundlebees_plugin/decision_queue.py, rizzstack.owner-decision/1): the tests
raise real requests through that queue and read the collector's produced
snapshot. The assertions name the exact fields and value vocabulary the Hive
app's consumer reads, so a records[]/requests[] regression cannot recur.
All digests and nonces are computed at runtime.
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

CONSUMER_STATES = {"pending", "approved", "denied", "applied", "unknown"}
CONSUMER_KINDS = {"gate", "budget", "scope", "grant", "unknown"}
REQUEST_FIELDS = {
    "request_id",
    "state",
    "kind",
    "subject",
    "question",
    "generated_at",
    "raised_at",
    "decided_at",
    "applied_at",
}


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
            "status": "live",
            "error": None,
            "collected_at": FIXED_STRING,
            "requests": [],
        }
        assert "records" not in snap["decisions"]
        assert "decisions" not in snap["degraded"]

    def test_queued_request_uses_the_exact_consumer_field_names(
        self, tmp_path: Path
    ) -> None:
        make_queue(tmp_path).raise_request(gate_request())
        section = make_collector(tmp_path).decisions_section()
        assert section["status"] == "live"
        assert section["error"] is None
        assert set(section) == {"status", "error", "collected_at", "requests"}
        assert "records" not in section
        assert section["requests"] == [
            {
                "request_id": "odq_gate_1",
                "state": "pending",
                "kind": "gate",
                "subject": "release-gate",
                "question": "Resolve the release gate for release-gate?",
                "generated_at": FIXED_STRING,
                "raised_at": "2026-11-16T09:25:00Z",
                "decided_at": None,
                "applied_at": None,
            }
        ]
        assert set(section["requests"][0]) == REQUEST_FIELDS

    def test_state_vocabulary_follows_the_queue_lifecycle(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.raise_request(gate_request(request_id="odq_pending", subject="release-gate"))
        queue.raise_request(gate_request(request_id="odq_applied", subject="deploy-gate"))
        queue.raise_request(gate_request(request_id="odq_approved", subject="merge-gate"))
        queue.raise_request(gate_request(request_id="odq_denied", subject="scope-gate"))
        queue.raise_request(gate_request(request_id="odq_withdrawn", subject="grant-gate"))

        queue.record_decision(
            "odq_applied",
            outcome="approve",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.deploy-gate.json",
        )
        # Consume it before the other final answers are recorded so they stay
        # in their decided states rather than all becoming applied.
        queue.apply_ready()
        queue.record_decision(
            "odq_approved",
            outcome="approve",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.merge-gate.json",
        )
        queue.record_decision(
            "odq_denied",
            outcome="deny",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are not met, so the answer is no.",
        )
        queue.withdraw("odq_withdrawn")

        section = make_collector(tmp_path).decisions_section()
        states = {row["request_id"]: row["state"] for row in section["requests"]}
        assert states == {
            "odq_pending": "pending",
            "odq_applied": "applied",
            "odq_approved": "approved",
            "odq_denied": "denied",
            "odq_withdrawn": "unknown",
        }
        assert set(states.values()) <= CONSUMER_STATES
        assert section["status"] == "live"

    def test_queue_timestamps_are_carried_when_present(self, tmp_path: Path) -> None:
        queue = make_queue(tmp_path)
        queue.raise_request(gate_request())
        queue.record_decision(
            "odq_gate_1",
            outcome="approve",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.release-gate.json",
        )
        queue.apply_ready()
        row = make_collector(tmp_path).decisions_section()["requests"][0]
        assert row["raised_at"] == "2026-11-16T09:25:00Z"
        assert row["decided_at"] == "2026-11-16T10:00:00Z"
        assert row["applied_at"] == FIXED_STRING

    def test_unknown_kind_is_reported_as_unknown_not_a_default(
        self, tmp_path: Path
    ) -> None:
        request = decision_queue.seal_request(
            {
                "schema": "rizzstack.owner-decision/1",
                "record": "request",
                "request_id": "odq_vendor_1",
                "kind": "vendor_signoff",
                "subject": "vendor-signoff",
                "question": "Approve the vendor signoff for this release?",
                "evidence": [{"kind": "record", "reference": "jobs/odj_1.json"}],
                "raised_by": "decision_queue",
                "raised_at": "2026-11-16T09:25:00Z",
            }
        )
        decisions = tmp_path / "decisions"
        decisions.mkdir()
        (decisions / "odq_vendor_1.json").write_text(
            json.dumps(
                {
                    "request": request,
                    "decision": None,
                    "defers": [],
                    "applied": None,
                    "withdrawn": None,
                }
            ),
            encoding="utf-8",
        )
        section = make_collector(tmp_path).decisions_section()
        assert section["status"] == "live"
        assert section["requests"][0]["kind"] == "unknown"
        assert section["requests"][0]["question"] == request["question"]
        assert set(row["kind"] for row in section["requests"]) <= CONSUMER_KINDS

    def test_malformed_record_is_skipped_and_degrades(self, tmp_path: Path) -> None:
        make_queue(tmp_path).raise_request(gate_request())
        (tmp_path / "decisions" / "odq_broken.json").write_text(
            "{not json", encoding="utf-8"
        )
        section = make_collector(tmp_path).decisions_section()
        assert section["status"] == "unavailable"
        assert section["error"] == "decision_record_malformed"
        assert [row["request_id"] for row in section["requests"]] == ["odq_gate_1"]

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
        assert section["requests"] == []

    def test_malformed_decision_is_skipped_and_degrades(self, tmp_path: Path) -> None:
        make_queue(tmp_path).raise_request(gate_request())
        path = tmp_path / "decisions" / "odq_gate_1.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["decision"] = {"outcome": "maybe", "decided_at": FIXED_STRING}
        path.write_text(json.dumps(record), encoding="utf-8")
        section = make_collector(tmp_path).decisions_section()
        assert section["status"] == "unavailable"
        assert section["error"] == "decision_record_malformed"
        assert section["requests"] == []

    def test_unreadable_decisions_directory_degrades(self, tmp_path: Path) -> None:
        (tmp_path / "decisions").write_text("not a directory", encoding="utf-8")
        snap = make_collector(tmp_path).build_snapshot()
        validated(snap)
        assert snap["decisions"]["status"] == "unavailable"
        assert snap["decisions"]["error"] == "decisions_unreadable"
        assert snap["decisions"]["requests"] == []
        assert "decisions" in snap["degraded"]

    def test_stale_when_the_newest_request_is_old(self, tmp_path: Path) -> None:
        make_queue(tmp_path).raise_request(
            gate_request(raised_at="2026-11-16T08:00:00Z")
        )
        snap = make_collector(tmp_path, stale_after_s=60).build_snapshot()
        validated(snap)
        assert snap["decisions"]["status"] == "stale"
        assert snap["decisions"]["error"] == "decisions_older_than_threshold"
        assert len(snap["decisions"]["requests"]) == 1
        assert "decisions" in snap["degraded"]

    def test_no_state_directory_is_unavailable_not_a_fake_zero(self) -> None:
        section = collector.Collector(now_fn=lambda: FIXED_NOW).decisions_section()
        assert section["status"] == "unavailable"
        assert section["error"] == "source_missing"
        assert section["requests"] == []

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
        assert snap["decisions"]["requests"][0]["request_id"] == "odq_gate_1"
        assert set(snap["decisions"]["requests"][0]) == REQUEST_FIELDS


class TestSchemaDocumentsTheConsumerContract:
    def test_section_and_request_shape_are_documented(self) -> None:
        schema = VALIDATOR.load(SNAPSHOT_SCHEMA)
        section = schema["$defs"]["decisions_requests_section"]
        assert section["required"] == ["status", "error", "collected_at", "requests"]
        row_ref = section["properties"]["requests"]["items"]["$ref"]
        assert row_ref == "#/$defs/decision_request_row"
        row = schema["$defs"]["decision_request_row"]
        assert row["additionalProperties"] is False
        assert set(row["required"]) == {
            "request_id",
            "state",
            "kind",
            "subject",
            "question",
            "generated_at",
            "raised_at",
        }
        assert set(schema["$defs"]["consumer_decision_state"]["enum"]) == CONSUMER_STATES
        assert set(schema["$defs"]["consumer_decision_kind"]["enum"]) == CONSUMER_KINDS
