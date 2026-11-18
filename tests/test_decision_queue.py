"""Tests for the durable owner-decision queue (rizzstack.owner-decision/1).

The queue is exercised as a library, against the observability contracts, and
through its CLI. All digests and nonces are computed at runtime so no
credential-shaped literal ever appears in source, and no test performs the
human act the queue exists to record.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))

from validate import SchemaError, Validator  # noqa: E402

MODULE_PATH = ROOT / "bundlebees_plugin" / "decision_queue.py"
SNAPSHOT_SCHEMA = "snapshot.schema.json"
OWNER_SCHEMA = "owner-decision.schema.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_queue = load_module("decision_queue", MODULE_PATH)
collector = load_module("rizzstack_obs_collector", ROOT / "contrib" / "rizzstack-observability" / "collector.py")

VALIDATOR = Validator(ROOT / "observability" / "schemas")

FIXED_NOW = "2026-11-16T09:30:00Z"
FIXED_DT = datetime(2026, 11, 16, 9, 30, tzinfo=timezone.utc)


def oracle_digest(body: dict, dropped: str) -> str:
    stripped = {key: value for key, value in body.items() if key != dropped}
    canonical = json.dumps(stripped, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def gate_request(*, nonce: str | None = None, **overrides) -> dict:
    body = {
        "schema": "rizzstack.owner-decision/1",
        "record": "request",
        "request_id": "odq_gate_1",
        "kind": "gate",
        "subject": "release-gate",
        "question": "Resolve the release gate for job odj_1?",
        "evidence": [{"kind": "record", "reference": "jobs/odj_1.json"}],
        "raised_by": "decision_queue",
        "raised_at": "2026-11-16T09:00:00Z",
    }
    body.update(overrides)
    return decision_queue.seal_request(body, nonce=nonce)


@pytest.fixture()
def queue(tmp_path: Path) -> decision_queue.DecisionQueue:
    return decision_queue.DecisionQueue(tmp_path, now=lambda: FIXED_NOW)


# ------------------------------------------------------------------- digests


class TestDigests:
    def test_seal_stamps_a_fresh_nonce_and_digest(self) -> None:
        request = gate_request()
        assert decision_queue.NONCE_RE.match(request["decision_nonce"])
        assert request["request_digest"] == oracle_digest(request, "request_digest")

    def test_explicit_nonce_is_kept_and_a_bad_one_is_refused(self) -> None:
        nonce = os.urandom(16).hex()
        assert gate_request(nonce=nonce)["decision_nonce"] == nonce
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.seal_request({}, nonce="short")
        assert excinfo.value.code == "bad_nonce"

    def test_tampered_request_is_refused(self) -> None:
        request = gate_request()
        request["subject"] = "another-gate"
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "digest_mismatch"

    def test_digest_covers_the_nonce_too(self) -> None:
        request = gate_request()
        tampered = dict(request, decision_nonce=os.urandom(16).hex())
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(tampered)
        assert excinfo.value.code == "digest_mismatch"


# --------------------------------------------------------- request validation


class TestRequestValidation:
    @pytest.mark.parametrize(
        "mutation, code",
        [
            ({"record": "decision"}, "bad_record"),
            ({"schema": "rizzstack.owner-decision/2"}, "bad_version"),
            ({"kind": "merge"}, "bad_kind"),
            ({"subject": "not a slug/with slash"}, "bad_id"),
            ({"raised_at": "2026-11-16 09:00:00"}, "bad_timestamp"),
            ({"question": "short"}, "bad_question"),
            ({"evidence": []}, "bad_evidence"),
            ({"evidence": [{"kind": "hearsay", "reference": "x"}]}, "bad_evidence"),
            ({"evidence": [{"kind": "record", "reference": ""}]}, "bad_evidence"),
        ],
    )
    def test_refusals_name_the_rule(self, mutation: dict, code: str) -> None:
        request = gate_request(**mutation)
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == code

    def test_unknown_field_is_refused(self) -> None:
        request = gate_request(widen_budget=True)
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "unknown_field"

    def test_missing_field_is_refused(self) -> None:
        request = gate_request()
        del request["question"]
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "missing_field"

    def test_duplicate_evidence_is_refused(self) -> None:
        request = gate_request(
            evidence=[
                {"kind": "record", "reference": "jobs/odj_1.json"},
                {"kind": "record", "reference": "jobs/odj_1.json"},
            ]
        )
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "bad_evidence"

    def test_every_recognized_kind_builds_a_valid_request(self) -> None:
        payloads = [
            {},
            {"spend_ceiling_usd": 10, "requested_addition_usd": 5},
            {"proposed_paths": ["tools/recovery.py", "docs/27-recovery-protocol.md"]},
            {"grant_id": "grant_ops_1", "grant_action": "enroll"},
        ]
        for kind, payload in zip(decision_queue.KINDS, payloads):
            request = decision_queue.build_request(
                request_id=f"odq_{kind}_1",
                kind=kind,
                subject=f"{kind}-subject",
                question=f"Decide the {kind} question for the queue?",
                evidence=[{"kind": "record", "reference": "jobs/odj_1.json"}],
                raised_by="decision_queue",
                raised_at="2026-11-16T09:00:00Z",
                **payload,
            )
            assert decision_queue.validate_request(request)["kind"] == kind


# ---------------------------------------------------------- kind payload rules


class TestKindPayloads:
    def test_payload_on_the_wrong_kind_is_refused(self) -> None:
        request = gate_request(grant_id="grant_ops_1", grant_action="enroll")
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "payload_mismatch"

    def test_budget_requires_both_numbers(self) -> None:
        request = gate_request(
            kind="budget",
            subject="spend",
            spend_ceiling_usd=10,
        )
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "payload_mismatch"

    def test_a_zero_addition_is_not_a_widening(self) -> None:
        request = gate_request(
            kind="budget",
            subject="spend",
            spend_ceiling_usd=10,
            requested_addition_usd=0,
        )
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "bad_budget"

    def test_scope_paths_must_stay_inside_the_repository(self) -> None:
        for bad in (["/etc"], ["../outside"], ["a/../../b"], []):
            request = gate_request(kind="scope", subject="scope", proposed_paths=bad)
            with pytest.raises(decision_queue.QueueError) as excinfo:
                decision_queue.validate_request(request)
            assert excinfo.value.code in ("bad_scope", "payload_mismatch")

    def test_grant_action_is_closed(self) -> None:
        request = gate_request(kind="grant", subject="grant_ops_1", grant_id="grant_ops_1", grant_action="pause")
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_request(request)
        assert excinfo.value.code == "bad_grant"


# -------------------------------------------------------- decision validation


class TestDecisionValidation:
    @staticmethod
    def decision(request: dict, **overrides) -> dict:
        body = {
            "schema": "rizzstack.owner-decision/1",
            "record": "decision",
            "request_id": request["request_id"],
            "request_digest": request["request_digest"],
            "decision_nonce": request["decision_nonce"],
            "decided_by": "owner",
            "decided_at": "2026-11-16T10:00:00Z",
            "outcome": "approve",
            "approval_receipt_ref": "approvals/odj_1.release-gate.json",
            "rationale": "The gate criteria are met and the evidence references check out.",
        }
        body.update(overrides)
        if overrides.get("outcome", "approve") != "approve":
            body["approval_receipt_ref"] = None
        body["decision_digest"] = decision_queue.decision_digest(body)
        return body

    def test_an_approval_binds_request_digest_and_nonce(self) -> None:
        request = gate_request()
        checked = decision_queue.validate_decision(self.decision(request), request=request)
        assert checked["outcome"] == "approve"
        assert checked["decision_digest"] == oracle_digest(checked, "decision_digest")

    def test_an_approval_without_a_receipt_is_refused(self) -> None:
        request = gate_request()
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_decision(
                self.decision(request, approval_receipt_ref=None), request=request
            )
        assert excinfo.value.code == "missing_receipt"

    def test_only_an_approval_may_cite_a_receipt(self) -> None:
        for outcome in ("deny", "defer"):
            request = gate_request()
            body = self.decision(request, outcome=outcome)
            body["approval_receipt_ref"] = "approvals/odj_1.release-gate.json"
            body["decision_digest"] = decision_queue.decision_digest(body)
            with pytest.raises(decision_queue.QueueError) as excinfo:
                decision_queue.validate_decision(body, request=request)
            assert excinfo.value.code == "unexpected_receipt"

    def test_a_decision_cannot_be_replayed_against_another_request(self) -> None:
        request = gate_request()
        other = gate_request(request_id="odq_gate_2", subject="merge-gate")
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_decision(self.decision(other), request=request)
        assert excinfo.value.code in ("binding_mismatch", "nonce_mismatch", "request_mismatch")

    def test_a_tampered_decision_body_is_refused(self) -> None:
        request = gate_request()
        body = self.decision(request)
        body["rationale"] = "Rewritten after the fact by someone else entirely."
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_decision(body, request=request)
        assert excinfo.value.code == "digest_mismatch"

    def test_validate_decision_validates_the_request_too(self) -> None:
        request = gate_request()
        request["kind"] = "merge"
        with pytest.raises(decision_queue.QueueError) as excinfo:
            decision_queue.validate_decision(self.decision(request), request=request)
        assert excinfo.value.code == "bad_kind"


# ------------------------------------------------------------ queue lifecycle


class TestQueueLifecycle:
    def test_raise_decide_apply_is_exactly_once(self, queue: decision_queue.DecisionQueue) -> None:
        record = queue.raise_request(gate_request())
        assert queue.status(record) == "pending"
        record = queue.record_decision(
            "odq_gate_1",
            outcome="approve",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.release-gate.json",
        )
        assert queue.status(record) == "decided"
        assert queue.apply_ready() == ["odq_gate_1"]
        assert queue.status(queue.get("odq_gate_1")) == "applied"
        assert queue.apply_ready() == []
        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.record_decision(
                "odq_gate_1",
                outcome="deny",
                decided_by="owner",
                rationale="The request was already applied, so this must be refused.",
            )
        assert excinfo.value.code == "not_pending"

    def test_a_deferral_leaves_the_request_pending(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        record = queue.record_decision(
            "odq_gate_1",
            outcome="defer",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="Not while the current wave is still in flight.",
        )
        assert queue.status(record) == "pending"
        assert len(record["defers"]) == 1
        assert queue.apply_ready() == []
        record = queue.record_decision(
            "odq_gate_1",
            outcome="deny",
            decided_by="owner",
            decided_at="2026-11-16T11:00:00Z",
            rationale="The gate criteria are not met, so the answer is no.",
        )
        assert queue.status(record) == "decided"
        assert queue.apply_ready() == ["odq_gate_1"]
        assert queue.get("odq_gate_1")["decision"]["outcome"] == "deny"

    def test_one_open_request_per_kind_and_subject(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.raise_request(gate_request(request_id="odq_gate_2"))
        assert excinfo.value.code == "duplicate_open_request"
        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.raise_request(gate_request(request_id="odq_gate_1"))
        assert excinfo.value.code == "request_id_taken"

    def test_a_new_request_may_follow_an_applied_one(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        queue.record_decision(
            "odq_gate_1",
            outcome="deny",
            decided_by="owner",
            rationale="The gate criteria are not met, so the answer is no.",
        )
        queue.apply_ready()
        again = gate_request(request_id="odq_gate_2")
        assert queue.status(queue.raise_request(again)) == "pending"

    def test_withdrawn_requests_are_never_decided(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        record = queue.withdraw("odq_gate_1")
        assert queue.status(record) == "withdrawn"
        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.record_decision(
                "odq_gate_1",
                outcome="approve",
                decided_by="owner",
                rationale="The gate criteria are met and the evidence references check out.",
                approval_receipt_ref="approvals/odj_1.release-gate.json",
            )
        assert excinfo.value.code == "not_pending"
        assert queue.apply_ready() == []

    def test_withdraw_refuses_a_closed_request(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        queue.record_decision(
            "odq_gate_1",
            outcome="approve",
            decided_by="owner",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.release-gate.json",
        )
        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.withdraw("odq_gate_1")
        assert excinfo.value.code == "not_pending"

    def test_a_tampered_record_stops_the_pass(self, queue: decision_queue.DecisionQueue, tmp_path: Path) -> None:
        queue.raise_request(gate_request())
        queue.record_decision(
            "odq_gate_1",
            outcome="approve",
            decided_by="owner",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.release-gate.json",
        )
        path = tmp_path / "decisions" / "odq_gate_1.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["decision"]["outcome"] = "deny"
        path.write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.apply_ready()
        assert excinfo.value.code == "record_tampered"
        assert queue.status(queue._read("odq_gate_1")) == "decided"

    def test_get_refuses_a_tampered_request(self, queue: decision_queue.DecisionQueue, tmp_path: Path) -> None:
        queue.raise_request(gate_request())
        path = tmp_path / "decisions" / "odq_gate_1.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["request"]["question"] = "Rewritten after the fact by someone else?"
        path.write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(decision_queue.QueueError):
            queue.get("odq_gate_1")

    def test_unknown_request_ids_are_refused(self, queue: decision_queue.DecisionQueue) -> None:
        for call in (
            lambda: queue.get("odq_missing"),
            lambda: queue.withdraw("odq_missing"),
            lambda: queue.record_decision(
                "odq_missing",
                outcome="approve",
                decided_by="owner",
                rationale="The gate criteria are met and the evidence references check out.",
            ),
        ):
            with pytest.raises(decision_queue.QueueError) as excinfo:
                call()
            assert excinfo.value.code in ("no_such_request", "bad_id")

    def test_request_ids_may_not_escape_the_queue_directory(self, queue: decision_queue.DecisionQueue, tmp_path: Path) -> None:
        with pytest.raises(decision_queue.QueueError):
            queue.get("../escape")
        assert not (tmp_path.parent / "escape.json").exists()


# ----------------------------------------------------- observability wiring


class TestObservabilitySection:
    @staticmethod
    def base_snapshot() -> dict:
        return collector.Collector(now_fn=lambda: FIXED_DT).build_snapshot()

    def test_section_validates_inside_a_real_snapshot(
        self, queue: decision_queue.DecisionQueue
    ) -> None:
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
        snapshot = self.base_snapshot()
        snapshot["decisions"] = queue.snapshot_section(generated_at=FIXED_NOW)
        VALIDATOR.validate(snapshot, VALIDATOR.load(SNAPSHOT_SCHEMA))
        row = snapshot["decisions"]["requests"][0]
        assert row["state"] == "applied"
        assert row["outcome"] == "approve"
        assert row["applied_at"] == FIXED_NOW

    def test_an_empty_queue_emits_an_empty_live_section(
        self, queue: decision_queue.DecisionQueue
    ) -> None:
        snapshot = self.base_snapshot()
        snapshot["decisions"] = queue.snapshot_section(generated_at=FIXED_NOW)
        VALIDATOR.validate(snapshot, VALIDATOR.load(SNAPSHOT_SCHEMA))
        assert snapshot["decisions"] == {
            "status": "live",
            "error": None,
            "collected_at": FIXED_NOW,
            "requests": [],
        }

    def test_rows_reflect_every_state(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        queue.raise_request(
            gate_request(
                request_id="odq_gate_2",
                subject="merge-gate",
                question="Resolve the merge gate for job odj_1?",
            )
        )
        queue.withdraw("odq_gate_2")
        queue.record_decision(
            "odq_gate_1",
            outcome="approve",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.release-gate.json",
        )
        states = {row["request_id"]: row["state"] for row in queue.snapshot_rows(FIXED_NOW)}
        assert states == {"odq_gate_1": "decided", "odq_gate_2": "withdrawn"}
        for row in queue.snapshot_rows(FIXED_NOW):
            assert row["schema"] == "rizzstack.observability/snapshot/1"
            assert row["generated_at"] == FIXED_NOW


class TestSchemaAgreement:
    """Documents the queue produces must satisfy the observability contract."""

    def test_request_and_decision_documents_validate(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        record = queue.get("odq_gate_1")
        VALIDATOR.validate_file(record["request"], OWNER_SCHEMA)
        decision = queue.record_decision(
            "odq_gate_1",
            outcome="approve",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.release-gate.json",
        )["decision"]
        VALIDATOR.validate_file(decision, OWNER_SCHEMA)


class TestCollectorCompat:
    """The section is optional, so unchanged collector output still validates."""

    def test_all_unavailable_collector_snapshot_validates(self) -> None:
        snapshot = collector.Collector(now_fn=lambda: FIXED_DT).build_snapshot()
        VALIDATOR.validate(snapshot, VALIDATOR.load(SNAPSHOT_SCHEMA))
        # decisions is now a real collector section: with no state directory
        # it degrades unavailable rather than being absent from the document,
        # and the snapshot still validates against the same discriminator.
        assert "decisions" in collector.SECTION_NAMES
        assert snapshot["decisions"]["status"] == "unavailable"
        assert snapshot["decisions"]["error"]
        assert snapshot["decisions"]["requests"] == []


# ------------------------------------------------------------------------ CLI


class TestCli:
    @pytest.fixture()
    def state(self, tmp_path: Path) -> Path:
        state = tmp_path / "state"
        queue = decision_queue.DecisionQueue(state)
        queue.raise_request(gate_request())
        return state

    def run(self, state: Path, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), "--state-dir", str(state), *argv],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )

    def test_pending_lists_the_open_request(self, state: Path) -> None:
        proc = self.run(state, "pending")
        assert proc.returncode == 0, proc.stderr
        pending = json.loads(proc.stdout)
        assert [row["request_id"] for row in pending] == ["odq_gate_1"]

    def test_record_apply_and_pending_round_trip(self, state: Path, tmp_path: Path) -> None:
        request = decision_queue.validate_request(gate_request())
        decision = {
            "schema": request["schema"],
            "record": "decision",
            "request_id": request["request_id"],
            "request_digest": request["request_digest"],
            "decision_nonce": request["decision_nonce"],
            "decided_by": "owner",
            "decided_at": "2026-11-16T10:00:00Z",
            "outcome": "approve",
            "approval_receipt_ref": "approvals/odj_1.release-gate.json",
            "rationale": "The gate criteria are met and the evidence references check out.",
        }
        decision["decision_digest"] = decision_queue.decision_digest(decision)
        path = tmp_path / "decision.json"
        path.write_text(json.dumps(decision), encoding="utf-8")

        proc = self.run(state, "record", "--request-id", "odq_gate_1", "--file", str(path))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["decision"]["outcome"] == "approve"

        proc = self.run(state, "apply")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout) == {"applied": ["odq_gate_1"]}

        proc = self.run(state, "pending")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout) == []

    def test_refusals_exit_two_with_a_json_error(self, state: Path, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"outcome": "approve"}), encoding="utf-8")
        proc = self.run(state, "record", "--request-id", "odq_gate_1", "--file", str(path))
        assert proc.returncode == 2
        error = json.loads(proc.stderr)
        assert error["code"] in ("bad_id", "bad_outcome", "bad_rationale")
        proc = self.run(state, "show", "--request-id", "odq_missing")
        assert proc.returncode == 2
        assert json.loads(proc.stderr)["code"] == "no_such_request"


# ------------------------------------------------------- record identity


class TestRecordIdentityIsTheFileName:
    """A queue record's identity is its file name AND its body id, and they must agree.

    Regression for the r1 review's blocking finding: _read took the identity
    from the file stem while _write targeted the body's request_id, so a plain
    copy of a decided record under a new stem was re-applied on every pass -
    the digests stay valid across a rename, so only a stem-vs-body check can
    catch it. The queue refuses such a file with ``bad_record_file``.
    """

    def _decide(self, queue: decision_queue.DecisionQueue) -> None:
        queue.raise_request(gate_request())
        queue.record_decision(
            "odq_gate_1",
            outcome="approve",
            decided_by="owner",
            decided_at="2026-11-16T10:00:00Z",
            rationale="The gate criteria are met and the evidence references check out.",
            approval_receipt_ref="approvals/odj_1.release-gate.json",
        )

    def test_a_copied_decided_record_is_refused_and_never_applied(
        self, queue: decision_queue.DecisionQueue, tmp_path: Path
    ) -> None:
        self._decide(queue)
        source = tmp_path / "decisions" / "odq_gate_1.json"
        copy = tmp_path / "decisions" / "odq_copy_1.json"
        copy.write_bytes(source.read_bytes())

        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.apply_ready()
        assert excinfo.value.code == "bad_record_file"

        # The pass refused before applying anything: the original stays decided.
        original = queue.get("odq_gate_1")
        assert queue.status(original) == "decided"
        assert original["applied"] is None

        # With the impostor gone, the queue applies the real record exactly once.
        copy.unlink()
        assert queue.apply_ready() == ["odq_gate_1"]
        assert queue.apply_ready() == []

    def test_get_refuses_a_record_whose_body_id_differs_from_the_stem(
        self, queue: decision_queue.DecisionQueue, tmp_path: Path
    ) -> None:
        self._decide(queue)
        source = tmp_path / "decisions" / "odq_gate_1.json"
        (tmp_path / "decisions" / "odq_copy_1.json").write_bytes(source.read_bytes())
        with pytest.raises(decision_queue.QueueError) as excinfo:
            queue.get("odq_copy_1")
        assert excinfo.value.code == "bad_record_file"



if __name__ == "__main__":
    pytest.main([__file__])
