"""Tests for the rizzstack decision-queue notifier.

The notifier consumes the written in-repo contract:

- ``docs/22-autonomy-architecture.md`` section 5 (the feature queue): the
  closed queue status vocabulary, and the owner-needed pending kinds —
  ``needs_approval`` waits on a decision, ``blocked`` waits on a blocker.
- ``observability/schemas/snapshot.schema.json``: the backlog section and row
  shapes the collector emits.
- ``contrib/rizzstack-observability/collector.py``: the ``queue.json``
  normalization the collector's backlog section is built from.

Severity design (anti-fatigue): owner-needed items are severity-high and get
chat delivery plus a desktop notification; every routine status stays
dashboard-only. ``failed`` is excluded from notification.

Delivery evidence here is real: the smoke tests post real HTTP requests to a
loopback server, prove silence when nothing is owner-needed, degrade-to-marker
when delivery fails, catch-up after recovery, and that no chat endpoint ever
leaks into status.json or stderr. Endpoints in this file are assembled at
runtime by concatenation so no credential-shaped literal appears in source.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTIFIER_PATH = ROOT / "contrib" / "rizzstack-observability" / "decision_notifier.py"
SERVICE_PATH = ROOT / "contrib" / "rizzstack-observability" / "rizzstack-decision-notifier.service"
README_PATH = ROOT / "contrib" / "rizzstack-observability" / "README.md"
SNAPSHOT_SCHEMA_PATH = ROOT / "observability" / "schemas" / "snapshot.schema.json"

# docs/22-autonomy-architecture.md, section 5 (the feature queue), verbatim:
# "Statuses: queued, claimed, running, ready_for_review, blocked, failed,
# needs_approval." observability/schemas/snapshot.schema.json pins the same
# enum as $defs.queue_status.
CONTRACT_QUEUE_STATUSES = frozenset(
    {
        "queued",
        "claimed",
        "running",
        "ready_for_review",
        "blocked",
        "failed",
        "needs_approval",
    }
)
# The owner-needed pending kinds per the contract reading. failed is
# deliberately excluded: it is a verify outcome, not an owner request.
CONTRACT_PENDING_KINDS = {"needs_approval": "decision", "blocked": "blocker"}

FIXED_NOW = datetime(2026, 11, 16, 9, 30, 0, tzinfo=timezone.utc)
NOTIFIER_NAME = "rizzstack-decision-notifier"
STATUS_SCHEMA = "rizzstack.notifier/status/1"
SNAPSHOT_SCHEMA = "rizzstack.observability/snapshot/1"

_NOTIFIER = None


def notifier():
    global _NOTIFIER
    if _NOTIFIER is None:
        spec = importlib.util.spec_from_file_location("rizzstack_decision_notifier", NOTIFIER_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _NOTIFIER = module
    return _NOTIFIER


class ChatSpy:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[str] = []

    def __call__(self, message: str):
        self.calls.append(message)
        if self.ok:
            return True, None
        return False, "chat_delivery_failed"


class DesktopSpy:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple[str, str]] = []

    def __call__(self, summary: str, body: str):
        self.calls.append((summary, body))
        if self.ok:
            return True, None
        return False, "desktop_unavailable"


def write_queue(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({"features": rows}), encoding="utf-8")


def row(fid: str, status: str, job_id: str | None = None, depends: list[str] | None = None) -> dict:
    return {"feature_id": fid, "status": status, "job_id": job_id, "depends_on": list(depends or [])}


def all_status_rows() -> list[dict]:
    return [
        row("feat-queued", "queued"),
        row("feat-claimed", "claimed"),
        row("feat-running", "running"),
        row("feat-review", "ready_for_review"),
        row("feat-decision", "needs_approval", "job-1"),
        row("feat-blocked", "blocked", "job-2"),
        row("feat-failed", "failed"),
    ]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.nt = notifier()
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def pass_over(
        self,
        rows: list[dict],
        *,
        chat=None,
        desktop=None,
        now=FIXED_NOW,
        config=None,
        marker=None,
        raw=None,
    ):
        """One pass over a queue.json fixture; returns (doc, exit_code)."""
        cfg = dict(self.nt.DEFAULT_CONFIG)
        if config:
            cfg.update(config)
        source = self.tmp / "queue.json"
        if raw is None:
            write_queue(source, rows)
        else:
            source.write_text(raw, encoding="utf-8")
        section, drift, kind = self.nt.read_backlog(source, now, cfg)
        if marker is None:
            marker = {"schema": STATUS_SCHEMA, "items": {}}
        doc, code = self.nt.run_pass(section, drift, kind, str(source), marker, cfg, chat, desktop, now)
        return doc, code


class TestContractReading(Base):
    def test_queue_vocabulary_matches_the_written_schema(self) -> None:
        schema = json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
        enum = set(schema["$defs"]["queue_status"]["enum"])
        self.assertEqual(enum, set(CONTRACT_QUEUE_STATUSES))
        self.assertEqual(set(self.nt.QUEUE_STATUSES), enum)

    def test_pending_kinds_are_the_contract_reading(self) -> None:
        self.assertEqual(self.nt.PENDING_KINDS, dict(CONTRACT_PENDING_KINDS))
        self.assertNotIn("failed", self.nt.PENDING_KINDS)

    def test_backlog_shape_matches_the_written_schema(self) -> None:
        schema = json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
        row_required = schema["$defs"]["backlog_feature"]["required"]
        section_required = schema["$defs"]["backlog_section"]["required"]
        self.assertEqual(tuple(row_required), tuple(self.nt.BACKLOG_ROW_REQUIRED))
        self.assertEqual(tuple(section_required), tuple(self.nt.BACKLOG_SECTION_REQUIRED))

    def test_pending_kinds_is_one_line(self) -> None:
        text = NOTIFIER_PATH.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if re.match(r"^PENDING_KINDS\s*=", line)]
        self.assertEqual(len(lines), 1)
        self.assertIn("needs_approval", lines[0])
        self.assertIn("blocked", lines[0])

    def test_config_divergence_from_the_contract_is_drift(self) -> None:
        doc, _ = self.pass_over(all_status_rows(), config={"pending_kinds": {"failed": "decision", "needs_approval": "decision"}})
        codes = {entry["code"] for entry in doc["drift"]}
        self.assertIn("contract_divergence", codes)

    def test_unknown_status_is_drift_and_never_notified(self) -> None:
        doc, code = self.pass_over(
            [row("feat-odd", "in_review"), row("feat-decision", "needs_approval")],
            chat=ChatSpy(),
            desktop=DesktopSpy(),
        )
        codes = {entry["code"] for entry in doc["drift"]}
        self.assertIn("status_outside_vocabulary", codes)
        self.assertNotIn("feat-odd", json.dumps(doc["items"]))
        self.assertEqual(len(doc["dashboard"]["routine"]), 0)


class TestOwnerNeededOnly(Base):
    def test_only_owner_needed_items_notify(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        doc, code = self.pass_over(all_status_rows(), chat=chat, desktop=desktop)
        self.assertEqual(code, 0)
        self.assertEqual(len(chat.calls), 2)
        self.assertEqual(len(desktop.calls), 2)
        joined = " ".join(chat.calls)
        self.assertIn("feat-decision", joined)
        self.assertIn("feat-blocked", joined)
        self.assertIn("decision needed", joined)
        self.assertIn("unblock needed", joined)
        self.assertNotIn("feat-failed", joined)
        self.assertEqual(set(doc["items"]), {"feat-decision/decision", "feat-blocked/blocker"})
        self.assertEqual(doc["dashboard"]["owner_needed"], 2)
        routine = {entry["feature_id"] for entry in doc["dashboard"]["routine"]}
        self.assertEqual(
            routine,
            {"feat-queued", "feat-claimed", "feat-running", "feat-review", "feat-failed"},
        )

    def test_silence_when_nothing_is_owner_needed(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        doc, code = self.pass_over(
            [row("feat-queued", "queued"), row("feat-running", "running")],
            chat=chat,
            desktop=desktop,
        )
        self.assertEqual(chat.calls, [])
        self.assertEqual(desktop.calls, [])
        self.assertEqual(code, 0)
        self.assertEqual(doc["items"], {})
        self.assertEqual(doc["run"]["pass_result"], "ok")


class TestDedupeAndCatchUp(Base):
    def test_dedupe_by_item_id_across_passes(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        self.assertEqual(len(chat.calls), 1)
        doc, _ = self.pass_over(
            [row("feat-a", "needs_approval")],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=60),
            marker=marker,
        )
        self.assertEqual(len(chat.calls), 1)
        item = doc["items"]["feat-a/decision"]
        self.assertEqual(item["state"], "delivered")
        self.assertEqual(item["deliveries"], 1)

    def test_resolved_then_reappearing_notifies_again(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        doc, _ = self.pass_over(
            [row("feat-a", "running")],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=60),
            marker=marker,
        )
        self.assertEqual(doc["items"]["feat-a/decision"]["state"], "resolved")
        self.assertEqual(len(chat.calls), 1)
        doc, _ = self.pass_over(
            [row("feat-a", "needs_approval")],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=120),
            marker=marker,
        )
        self.assertEqual(len(chat.calls), 2)
        self.assertEqual(doc["items"]["feat-a/decision"]["state"], "delivered")

    def test_kind_change_moves_to_a_new_item_id(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        doc, _ = self.pass_over(
            [row("feat-a", "blocked")],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=60),
            marker=marker,
        )
        self.assertEqual(doc["items"]["feat-a/decision"]["state"], "resolved")
        self.assertEqual(doc["items"]["feat-a/decision"]["resolved_reason"], "kind_changed")
        self.assertEqual(len(chat.calls), 2)
        self.assertIn("feat-a", chat.calls[1])
        self.assertIn("unblock needed", chat.calls[1])


class TestEscalationAging(Base):
    def test_escalation_fires_only_after_the_configured_age(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        config = {"escalate_after_s": 100}
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, config=config, marker=marker)
        doc, _ = self.pass_over(
            [row("feat-a", "needs_approval")],
            chat=chat,
            desktop=desktop,
            config=config,
            now=FIXED_NOW + timedelta(seconds=99),
            marker=marker,
        )
        self.assertEqual(len(chat.calls), 1)
        self.assertEqual(doc["items"]["feat-a/decision"]["escalations"], 0)
        doc, _ = self.pass_over(
            [row("feat-a", "needs_approval")],
            chat=chat,
            desktop=desktop,
            config=config,
            now=FIXED_NOW + timedelta(seconds=101),
            marker=marker,
        )
        self.assertEqual(len(chat.calls), 2)
        self.assertIn("escalation", chat.calls[1])
        self.assertEqual(doc["items"]["feat-a/decision"]["escalations"], 1)
        self.assertEqual(doc["items"]["feat-a/decision"]["deliveries"], 2)

    def test_escalation_uses_config_data_not_a_literal(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        config = {"escalate_after_s": 30}
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "blocked")], chat=chat, desktop=desktop, config=config, marker=marker)
        doc, _ = self.pass_over(
            [row("feat-a", "blocked")],
            chat=chat,
            desktop=desktop,
            config=config,
            now=FIXED_NOW + timedelta(seconds=31),
            marker=marker,
        )
        self.assertEqual(doc["items"]["feat-a/blocker"]["escalations"], 1)


class TestDegradeToMarker(Base):
    def test_failed_chat_degrades_to_marker_and_is_never_lost(self) -> None:
        chat, desktop = ChatSpy(ok=False), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        doc, code = self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        self.assertEqual(code, 1)
        item = doc["items"]["feat-a/decision"]
        self.assertEqual(item["state"], "degraded")
        self.assertEqual(item["last_error"], "chat_delivery_failed")
        self.assertEqual(item["deliveries"], 0)
        self.assertEqual(doc["run"]["chat_error"], "chat_delivery_failed")
        self.assertEqual(len(desktop.calls), 1)

    def test_degraded_item_catches_up_on_the_next_good_pass(self) -> None:
        chat, desktop = ChatSpy(ok=False), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        chat.ok = True
        doc, code = self.pass_over(
            [row("feat-a", "needs_approval")],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=60),
            marker=marker,
        )
        self.assertEqual(code, 0)
        item = doc["items"]["feat-a/decision"]
        self.assertEqual(item["state"], "delivered")
        self.assertEqual(item["deliveries"], 1)
        self.assertIsNone(item["last_error"])

    def test_retry_pass_does_not_reping_the_desktop(self) -> None:
        chat, desktop = ChatSpy(ok=False), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        self.assertEqual(len(desktop.calls), 1)
        doc, _ = self.pass_over(
            [row("feat-a", "needs_approval")],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=60),
            marker=marker,
        )
        self.assertEqual(len(desktop.calls), 1)
        self.assertEqual(doc["items"]["feat-a/decision"]["state"], "degraded")

    def test_unavailable_source_keeps_items_and_never_resolves_them(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        source = self.tmp / "queue.json"
        source.unlink()
        cfg = dict(self.nt.DEFAULT_CONFIG)
        section, drift, kind = self.nt.read_backlog(source, FIXED_NOW + timedelta(seconds=60), cfg)
        self.assertEqual(section["status"], "unavailable")
        doc, code = self.nt.run_pass(
            section, drift, kind, str(source), marker, cfg, chat, desktop,
            FIXED_NOW + timedelta(seconds=60),
        )
        self.assertEqual(code, 1)
        self.assertEqual(doc["source"]["status"], "unavailable")
        self.assertEqual(doc["items"]["feat-a/decision"]["state"], "delivered")
        self.assertEqual(len(chat.calls), 1)

    def test_no_webhook_configured_degrades_instead_of_losing_the_item(self) -> None:
        doc, code = self.pass_over([row("feat-a", "needs_approval")], chat=None, desktop=DesktopSpy())
        self.assertEqual(code, 1)
        self.assertEqual(doc["items"]["feat-a/decision"]["state"], "degraded")
        self.assertEqual(doc["items"]["feat-a/decision"]["last_error"], "chat_not_configured")


class RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    status_code = 200

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        type(self).requests.append({"path": self.path, "body": body})
        payload = b"{}"
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


class TestRealHttpSmoke(Base):
    def setUp(self) -> None:
        super().setUp()
        RecordingHandler.requests = []
        RecordingHandler.status_code = 200
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        self.port = self.server.server_address[1]
        self.webhook = f"http://127.0.0.1:{self.port}/hook"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_real_http_delivery_posts_the_message(self) -> None:
        ok, code = self.nt.deliver_chat(self.webhook, "rizzstack: decision needed — feat-a (needs_approval)", 10.0)
        self.assertTrue(ok)
        self.assertIsNone(code)
        self.assertEqual(len(RecordingHandler.requests), 1)
        seen = RecordingHandler.requests[0]
        self.assertEqual(seen["path"], "/hook")
        body = json.loads(seen["body"])
        self.assertIn("feat-a", body["text"])
        self.assertIn("decision needed", body["text"])

    def test_http_error_degrades_with_a_generic_code(self) -> None:
        RecordingHandler.status_code = 500
        ok, code = self.nt.deliver_chat(self.webhook, "rizzstack: decision needed — feat-a", 10.0)
        self.assertFalse(ok)
        self.assertEqual(code, "chat_delivery_failed")

    def test_end_to_end_subprocess_degrade_then_catch_up(self) -> None:
        state = self.tmp / "state"
        status_dir = self.tmp / "status"
        state.mkdir()
        write_queue(state / "queue.json", [row("feat-e2e", "needs_approval", "job-9")])
        webhook_file = self.tmp / "chat-webhook"
        webhook_file.write_text(self.webhook + "\n", encoding="utf-8")
        webhook_file.chmod(0o600)

        dead = socket.socket()
        dead.bind(("127.0.0.1", 0))
        dead_port = dead.getsockname()[1]
        dead.close()
        dead_file = self.tmp / "chat-webhook-dead"
        dead_file.write_text(f"http://127.0.0.1:{dead_port}/hook\n", encoding="utf-8")

        argv = [
            sys.executable, str(NOTIFIER_PATH),
            "--state-dir", str(state),
            "--status-dir", str(status_dir),
            "--chat-webhook-file",
        ]

        def run(source: Path):
            proc = subprocess.run(
                argv + [str(source), "--print"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            return proc

        degraded = run(dead_file)
        self.assertEqual(degraded.returncode, 1)
        marker = json.loads((status_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["items"]["feat-e2e/decision"]["state"], "degraded")

        caught_up = run(webhook_file)
        self.assertEqual(caught_up.returncode, 0)
        self.assertEqual(len(RecordingHandler.requests), 1)
        body = json.loads(RecordingHandler.requests[0]["body"])
        self.assertIn("feat-e2e", body["text"])
        marker = json.loads((status_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["items"]["feat-e2e/decision"]["state"], "delivered")

        silent = run(webhook_file)
        self.assertEqual(silent.returncode, 0)
        self.assertEqual(len(RecordingHandler.requests), 1)

        for proc in (degraded, caught_up, silent):
            self.assertNotIn(self.webhook, proc.stdout)
            self.assertNotIn(self.webhook, proc.stderr)
        status_text = (status_dir / "status.json").read_text(encoding="utf-8")
        self.assertNotIn(self.webhook, status_text)
        self.assertNotIn("/hook", status_text)

    def test_end_to_end_subprocess_real_http_via_environment_variable(self) -> None:
        state = self.tmp / "state2"
        status_dir = self.tmp / "status2"
        state.mkdir()
        write_queue(state / "queue.json", [row("feat-env", "blocked", "job-8")])
        env = dict(os.environ)
        env["RIZZSTACK_NOTIFIER_CHAT_WEBHOOK"] = self.webhook
        proc = subprocess.run(
            [
                sys.executable, str(NOTIFIER_PATH),
                "--state-dir", str(state),
                "--status-dir", str(status_dir),
                "--print",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(RecordingHandler.requests), 1)
        body = json.loads(RecordingHandler.requests[0]["body"])
        self.assertIn("feat-env", body["text"])
        self.assertIn("unblock needed", body["text"])


class TestStatusDocument(Base):
    def test_document_shape(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        doc, _ = self.pass_over(all_status_rows(), chat=chat, desktop=desktop)
        self.assertEqual(doc["schema"], STATUS_SCHEMA)
        self.assertEqual(doc["notifier"], NOTIFIER_NAME)
        self.assertTrue(doc["generated_at"].endswith("Z"))
        self.assertEqual(doc["source"]["kind"], "queue")
        self.assertEqual(doc["source"]["status"], "live")
        self.assertIsNone(doc["source"]["error"])
        self.assertEqual(doc["run"]["pass_result"], "ok")
        self.assertTrue(doc["run"]["chat_configured"])
        counts = doc["dashboard"]["counts"]
        self.assertEqual(counts.get("needs_approval"), 1)
        self.assertEqual(counts.get("blocked"), 1)
        self.assertEqual(counts.get("failed"), 1)
        for entry in doc["drift"]:
            self.assertIn("code", entry)
            self.assertIn("ts", entry)
        for item in doc["items"].values():
            self.assertIn("first_seen_at", item)
            self.assertIn("last_seen_at", item)
            self.assertIn("last_notified_at", item)
            self.assertTrue(item["first_seen_at"].endswith("Z"))

    def test_marker_round_trip_and_resolved_retention(self) -> None:
        chat, desktop = ChatSpy(), DesktopSpy()
        marker = {"schema": STATUS_SCHEMA, "items": {}}
        self.pass_over([row("feat-a", "needs_approval")], chat=chat, desktop=desktop, marker=marker)
        doc, _ = self.pass_over(
            [row("feat-a", "running")],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=60),
            marker=marker,
        )
        status_file = self.tmp / "status.json"
        self.nt.save_marker(status_file, doc)
        loaded = self.nt.load_marker(status_file)
        self.assertEqual(loaded["items"]["feat-a/decision"]["state"], "resolved")

        doc2, _ = self.pass_over(
            [],
            chat=chat,
            desktop=desktop,
            now=FIXED_NOW + timedelta(seconds=60 + self.nt.DEFAULT_CONFIG["resolved_retention_s"] + 1),
            marker=loaded,
        )
        self.assertNotIn("feat-a/decision", doc2["items"])

    def test_snapshot_document_source(self) -> None:
        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "generated_at": "2026-11-16T09:29:00Z",
            "backlog": {
                "status": "live",
                "error": None,
                "collected_at": "2026-11-16T09:29:00Z",
                "features": [
                    {
                        "schema": SNAPSHOT_SCHEMA,
                        "generated_at": "2026-11-16T09:29:00Z",
                        "feature_id": "feat-snap",
                        "job_id": None,
                        "status": "needs_approval",
                        "depends_on": [],
                    }
                ],
                "counts": {"needs_approval": 1},
            },
        }
        doc, code = self.pass_over([], chat=ChatSpy(), desktop=DesktopSpy(), raw=json.dumps(snapshot))
        self.assertEqual(code, 0)
        self.assertEqual(doc["source"]["kind"], "snapshot")
        self.assertEqual(set(doc["items"]), {"feat-snap/decision"})

    def test_snapshot_schema_mismatch_is_drift(self) -> None:
        snapshot = {"schema": "rizzstack.notifier/wrong/1", "backlog": {}}
        doc, code = self.pass_over([], raw=json.dumps(snapshot))
        codes = {entry["code"] for entry in doc["drift"]}
        self.assertIn("snapshot_schema_mismatch", codes)
        self.assertEqual(doc["source"]["status"], "unavailable")

    def test_malformed_source_is_drift_and_unavailable(self) -> None:
        doc, code = self.pass_over([], raw="not json at all")
        codes = {entry["code"] for entry in doc["drift"]}
        self.assertIn("source_unreadable", codes)
        self.assertEqual(doc["source"]["status"], "unavailable")

    def test_notifier_writes_only_its_own_status_file(self) -> None:
        state = self.tmp / "state3"
        state.mkdir()
        write_queue(state / "queue.json", all_status_rows())
        before = sorted(p.name for p in state.iterdir())
        cfg = dict(self.nt.DEFAULT_CONFIG)
        section, drift, kind = self.nt.read_backlog(state / "queue.json", FIXED_NOW, cfg)
        doc, _ = self.nt.run_pass(
            section, drift, kind, str(state / "queue.json"), {"schema": STATUS_SCHEMA, "items": {}},
            cfg, ChatSpy(), DesktopSpy(), FIXED_NOW,
        )
        self.nt.save_marker(self.tmp / "elsewhere" / "status.json", doc)
        after = sorted(p.name for p in state.iterdir())
        self.assertEqual(before, after)


class TestCliMain(Base):
    def setUp(self) -> None:
        super().setUp()
        RecordingHandler.requests = []
        RecordingHandler.status_code = 200
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        self.port = self.server.server_address[1]
        self.webhook = f"http://127.0.0.1:{self.port}/hook"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_one_shot_run_delivers_and_persists(self) -> None:
        state = self.tmp / "state-cli"
        status_dir = self.tmp / "status-cli"
        state.mkdir()
        write_queue(state / "queue.json", [row("feat-cli", "needs_approval")])
        saved = os.environ.pop("RIZZSTACK_NOTIFIER_CHAT_WEBHOOK", None)
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            code = self.nt.main(
                [
                    "--state-dir", str(state),
                    "--status-dir", str(status_dir),
                    "--print",
                ]
            )
        finally:
            sys.stdout = old_stdout
            if saved is not None:
                os.environ["RIZZSTACK_NOTIFIER_CHAT_WEBHOOK"] = saved
        self.assertEqual(code, 1)
        doc = json.loads(buf.getvalue())
        self.assertEqual(doc["items"]["feat-cli/decision"]["state"], "degraded")
        self.assertEqual(doc["items"]["feat-cli/decision"]["last_error"], "chat_not_configured")

        os.environ["RIZZSTACK_NOTIFIER_CHAT_WEBHOOK"] = self.webhook
        buf2 = io.StringIO()
        sys.stdout = buf2
        try:
            code = self.nt.main(
                [
                    "--state-dir", str(state),
                    "--status-dir", str(status_dir),
                    "--print",
                ]
            )
        finally:
            sys.stdout = old_stdout
            os.environ.pop("RIZZSTACK_NOTIFIER_CHAT_WEBHOOK", None)
        self.assertEqual(code, 0)
        self.assertEqual(len(RecordingHandler.requests), 1)
        marker = json.loads((status_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["items"]["feat-cli/decision"]["state"], "delivered")

    def test_bad_config_is_refused(self) -> None:
        config_file = self.tmp / "bad.json"
        config_file.write_text(json.dumps({"escalate_after_s": "soon"}), encoding="utf-8")
        state = self.tmp / "state-bad"
        state.mkdir()
        write_queue(state / "queue.json", [row("feat-bad", "blocked")])
        code = self.nt.main(
            [
                "--state-dir", str(state),
                "--status-dir", str(self.tmp / "status-bad"),
                "--config", str(config_file),
            ]
        )
        self.assertEqual(code, 2)

    def test_unknown_config_key_is_drift(self) -> None:
        config_file = self.tmp / "odd.json"
        config_file.write_text(json.dumps({"escalate_after_s": 90, "mystery": 1}), encoding="utf-8")
        state = self.tmp / "state-odd"
        status_dir = self.tmp / "status-odd"
        state.mkdir()
        write_queue(state / "queue.json", [row("feat-odd", "needs_approval")])
        env_webhook = os.environ.get("RIZZSTACK_NOTIFIER_CHAT_WEBHOOK")
        os.environ["RIZZSTACK_NOTIFIER_CHAT_WEBHOOK"] = self.webhook
        try:
            code = self.nt.main(
                [
                    "--state-dir", str(state),
                    "--status-dir", str(status_dir),
                    "--config", str(config_file),
                ]
            )
        finally:
            if env_webhook is None:
                os.environ.pop("RIZZSTACK_NOTIFIER_CHAT_WEBHOOK", None)
            else:
                os.environ["RIZZSTACK_NOTIFIER_CHAT_WEBHOOK"] = env_webhook
        self.assertEqual(code, 0)
        doc = json.loads((status_dir / "status.json").read_text(encoding="utf-8"))
        codes = {entry["code"] for entry in doc["drift"]}
        self.assertIn("config_unknown_key", codes)
        self.assertEqual(doc["items"]["feat-odd/decision"]["state"], "delivered")

    def test_config_webhook_file_holds_the_endpoint(self) -> None:
        state = self.tmp / "state-webhook"
        status_dir = self.tmp / "status-webhook"
        state.mkdir()
        write_queue(state / "queue.json", [row("feat-w", "blocked")])
        webhook_file = self.tmp / "hook-file"
        webhook_file.write_text(self.webhook + "\n", encoding="utf-8")
        code = self.nt.main(
            [
                "--state-dir", str(state),
                "--status-dir", str(status_dir),
                "--chat-webhook-file", str(webhook_file),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(RecordingHandler.requests), 1)


# Secret-shape patterns are assembled from fragments at runtime so no
# credential-shaped literal appears in this file either.
def _secret_patterns():
    hex_pair = "[0-9a-fA-F]{"
    b64 = "[A-Za-z0-9"
    jwt_head = "ey"
    return tuple(
        re.compile(pattern)
        for pattern in (
            hex_pair + "40}" + "|[0-9a-fA-F]{64}",
            b64 + "+/]{32,}",
            jwt_head + "J[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.",
            "AKIA[0-9A-Z]{16}",
            "gh[pousr]_[A-Za-z0-9]{20,}",
            "github_pat_[A-Za-z0-9_]{20,}",
            "xo" + "x[baprs]-[A-Za-z0-9-]{10,}",
            "sk-[A-Za-z0-9]{20,}",
            "Bear" + "er\\s+[A-Za-z0-9._~+/-]{16,}",
        )
    )


FILES_UNDER_HYGIENE = (NOTIFIER_PATH, SERVICE_PATH, README_PATH, Path(__file__).resolve())


class TestScannerHygiene(unittest.TestCase):
    def test_no_line_of_the_deliverable_is_secret_shaped(self) -> None:
        hits = []
        for path in FILES_UNDER_HYGIENE:
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), start=1):
                for pattern in _secret_patterns():
                    if pattern.search(line):
                        hits.append(f"{path.name}:{number}")
        self.assertEqual(hits, [])


class TestUnitAndReadme(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SERVICE_PATH.read_text(encoding="utf-8")
        self.readme = README_PATH.read_text(encoding="utf-8")

    def test_unit_is_a_looping_user_service(self) -> None:
        self.assertIn("[Unit]", self.service)
        self.assertIn("[Service]", self.service)
        self.assertIn("[Install]", self.service)
        self.assertIn("Type=simple", self.service)
        self.assertIn("--loop", self.service)
        self.assertIn("EnvironmentFile=", self.service)
        self.assertIn("WantedBy=default.target", self.service)
        self.assertIn("Restart=on-failure", self.service)

    def test_unit_hardening_and_writable_marker(self) -> None:
        self.assertIn("NoNewPrivileges=yes", self.service)
        self.assertIn("ProtectHome=read-only", self.service)
        self.assertIn("ReadWritePaths=", self.service)
        self.assertIn("PrivateTmp=yes", self.service)

    def test_unit_names_the_webhook_source_without_a_value(self) -> None:
        self.assertIn("RIZZSTACK_NOTIFIER_CHAT_WEBHOOK", self.service)
        for line in self.service.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotIn("://", stripped)
            self.assertNotIn("hook", stripped.lower())

    def test_readme_documents_install_and_the_env_var(self) -> None:
        self.assertIn("rizzstack-decision-notifier", self.readme)
        self.assertIn("systemctl --user enable --now rizzstack-decision-notifier", self.readme)
        self.assertIn("RIZZSTACK_NOTIFIER_CHAT_WEBHOOK", self.readme)
        self.assertIn("0600", self.readme)
        for line in self.readme.splitlines():
            if "hook" in line.lower() or "webhook" in line.lower():
                self.assertNotIn("://", line)


if __name__ == "__main__":
    unittest.main()
