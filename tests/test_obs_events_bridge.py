"""Contract tests for the rizzstack observability events bridge (RED-first).

The bridge (``contrib/rizzstack-observability/events_bridge.py``) turns the
launcher's per-attempt JSONL event stream into a same-origin Server-Sent
Events endpoint (``/obs-events``) for the Observatory live panel. This suite
pins the r4 lease criteria:

- the rails-vocabulary kind mapping table (the single adjustment point for
  launcher kind drift),
- tolerant launcher payload field normalization (unknown fields survive,
  missing fields become null, odd payloads never crash),
- the server-side shared-value gate: a request without the header is
  refused, a wrong value is refused without echoing it, an unconfigured
  bridge refuses to start, and no inline flag exists by design,
- the tailnet-only peer policy (loopback and 100.64.0.0/10 only),
- cursor resume semantics (replay after a cursor, reset after a gap),
- idle blips flushed as comment frames with zero data frames,
- source-ended streams closing with a ``bye`` event,
- end-to-end streaming over a real socket plus the default filter mode,
- the panel collapse and windowing contracts (python mirrors; the real
  ``app.js`` helpers are exercised against the same numbers by the stress
  harness).

Credentials in this file are assembled at runtime by concatenation so no
credential-shaped literal ever appears in source (house rule, see
``tests/test_obs_snapshot.py``). Stdlib only; pytest drives it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "contrib" / "rizzstack-observability" / "events_bridge.py"

GATE_ENV_NAME = "RIZZSTACK_OBS_TOKEN"

# Assembled at runtime (house rule): no credential-shaped literal in source.
GATE_PARTS = ("rizz", "stack", "-obs-", "gate-", "v", "1")
GATE = "".join(GATE_PARTS)
SCHEME_PARTS = ("Bea", "rer")
SCHEME_WORD = "".join(SCHEME_PARTS)
AUTH_NAME = "Auth" + "orization"


def gate_header(value: str | None = None) -> str:
    return SCHEME_WORD + " " + (GATE if value is None else value)


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("rizzstack_obs_events_bridge", BRIDGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = load_bridge_module()

RAILS_VOCAB = {
    "bee.started",
    "bee.state",
    "bee.finished",
    "bee.note",
    "bee.error",
    "turn.started",
    "turn.finished",
    "tool.progress",
    "tool.done",
    "event.other",
}


# ------------------------------------------------------------------ sse client


class SseStream:
    """Tiny raw-socket SSE reader with a hard deadline, for tests only."""

    def __init__(self, port: int, path: str = "/obs-events", headers: dict | None = None,
                 timeout_s: float = 5.0, host: str = "127.0.0.1") -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout_s)
        self.timeout_s = timeout_s
        lines = [f"GET {path} HTTP/1.1", f"Host: {host}:{port}", "Connection: close"]
        for name, value in (headers or {}).items():
            lines.append(f"{name}: {value}")
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))
        self._buf = b""
        status = self._readline(time.monotonic() + timeout_s)
        assert status is not None, "server closed before answering"
        parts = status.split()
        self.status = int(parts[1]) if len(parts) >= 2 else 0
        self.headers: dict[str, str] = {}
        while True:
            line = self._readline(time.monotonic() + timeout_s)
            if not line:
                break
            name, _, value = line.partition(":")
            self.headers[name.strip().lower()] = value.strip()
        self.eof = False

    def _readline(self, deadline: float) -> str | None:
        while b"\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("sse read deadline exceeded")
            self.sock.settimeout(min(remaining, 0.5))
            try:
                chunk = self.sock.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            self._buf += chunk
        raw, _, self._buf = self._buf.partition(b"\n")
        return raw.rstrip(b"\r").decode("utf-8")

    def read_blocks(self, want: int = 1, grace_s: float = 5.0) -> list[dict]:
        """Read up to ``want`` SSE blocks; returns early on EOF or deadline.

        A block is a dict of field/value pairs; comment-only idle frames come
        back as ``{"comments": [...]}``.
        """
        blocks: list[dict] = []
        deadline = time.monotonic() + grace_s
        current: dict = {}
        while len(blocks) < want:
            try:
                line = self._readline(deadline)
            except TimeoutError:
                break
            if line is None:
                self.eof = True
                break
            if line == "":
                if current:
                    blocks.append(current)
                    current = {}
                continue
            if line.startswith(":"):
                current.setdefault("comments", []).append(line)
                continue
            name, _, value = line.partition(":")
            current[name.strip()] = value.strip()
        return blocks

    def read_until_event(self, name: str, grace_s: float = 5.0) -> list[dict]:
        """Read blocks until one whose ``event`` equals ``name`` (inclusive)."""
        blocks: list[dict] = []
        deadline = time.monotonic() + grace_s
        while True:
            remaining = max(0.05, deadline - time.monotonic())
            got = self.read_blocks(want=1, grace_s=remaining)
            if not got:
                break
            blocks.extend(got)
            if any(block.get("event") == name for block in got):
                break
        return blocks

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def open_stream(srv, path: str = "/obs-events", headers: dict | None = None,
                timeout_s: float = 5.0) -> SseStream:
    host, port = srv.server_address[:2]
    merged = {AUTH_NAME: gate_header()}
    merged.update(headers or {})
    return SseStream(port, path=path, headers=merged, timeout_s=timeout_s, host=host)


def read_past_hello(stream: SseStream, want_after: int = 0, grace_s: float = 3.0) -> list[dict]:
    """Consume the retry+hello preamble, then up to ``want_after`` blocks."""
    prelude = stream.read_until_event("hello", grace_s=grace_s)
    assert prelude and prelude[-1]["event"] == "hello", prelude
    if want_after:
        return prelude + stream.read_blocks(want=want_after, grace_s=grace_s)
    return prelude


# -------------------------------------------------------------------- fixtures


@pytest.fixture()
def server_factory():
    made: list = []

    def factory(target, gate: str | None = GATE, heartbeat_s: float = 0.2):
        srv = bridge.make_server("127.0.0.1", 0, target, gate, heartbeat_s=heartbeat_s)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        made.append(srv)
        return srv

    yield factory
    for srv in made:
        srv.shutdown()
        srv.server_close()


def new_bridge(**kwargs):
    return bridge.Bridge(**kwargs)


# ---------------------------------------------------------------- kind mapping


class TestKindMapping:
    def test_known_launcher_kinds_map_into_rails_vocabulary(self) -> None:
        pairs = {
            "attempt_started": "bee.started",
            "attempt_finished": "bee.finished",
            "attempt_state": "bee.state",
            "state_changed": "bee.state",
            "turn_started": "turn.started",
            "turn_finished": "turn.finished",
            "tool_update": "tool.progress",
            "tool_result": "tool.done",
            "bee_note": "bee.note",
            "error": "bee.error",
        }
        for launcher_kind, rails_name in pairs.items():
            assert bridge.rails_kind(launcher_kind) == rails_name, launcher_kind

    def test_aliases_case_and_noise_are_tolerated(self) -> None:
        assert bridge.rails_kind("Tool-Update") == "tool.progress"
        assert bridge.rails_kind("  tool.update  ") == "tool.progress"
        assert bridge.rails_kind("TOOL_PROGRESS") == "tool.progress"
        assert bridge.rails_kind("totally-unknown-kind") == "event.other"
        assert bridge.rails_kind("") == "event.other"
        assert bridge.rails_kind(None) == "event.other"
        assert bridge.rails_kind(17) == "event.other"

    def test_mapping_is_total_over_the_rails_vocabulary(self) -> None:
        assert set(bridge.KIND_MAP.values()) <= RAILS_VOCAB
        assert all(isinstance(name, str) and name for name in bridge.KIND_MAP.values())
        assert bridge.UNKNOWN_KIND == "event.other"


# ------------------------------------------------------- tolerant field mapping


class TestTolerantFields:
    def test_canonical_fields_use_candidate_names(self) -> None:
        raw = {
            "kind": "tool_update",
            "attempt_id": "att_1",
            "turn_id": "t3",
            "tool_name": "pytest",
            "ts": "2026-11-16T09:30:00Z",
            "message": "running suite",
        }
        event = bridge.normalize_event(raw, seq=1, now_ms=lambda: 1_000_000)
        assert event["bee"] == "att_1"
        assert event["turn"] == "t3"
        assert event["tool"] == "pytest"
        assert event["kind"] == "tool.progress"
        assert event["detail"] == "running suite"
        assert isinstance(event["ts"], int) and event["ts"] > 1_700_000_000_000

    def test_missing_fields_become_none_and_extras_survive(self) -> None:
        raw = {"kind": "tool_update", "custom": {"deep": [1, 2]}}
        event = bridge.normalize_event(raw, seq=7, now_ms=lambda: 5_000)
        assert event["bee"] is None
        assert event["turn"] is None
        assert event["tool"] is None
        assert event["state"] is None
        assert event["payload"]["custom"] == {"deep": [1, 2]}
        assert event["seq"] == 7

    def test_odd_payloads_never_crash(self) -> None:
        for raw in ([], "a string", 5, None, {"kind": 5}, {"kind": {"a": 1}}, {"tool": ["x"]}):
            event = bridge.normalize_event(raw, seq=1, now_ms=lambda: 9_000)
            assert event["kind"] == "event.other"
            assert isinstance(event["raw_kind"], str)

    def test_detail_is_scrubbed_and_capped(self) -> None:
        noisy = "ab" + "x" * 500 + "\ncontrol\x07"
        event = bridge.normalize_event({"kind": "note", "detail": noisy}, seq=1, now_ms=lambda: 0)
        assert len(event["detail"]) <= 200
        assert "\x07" not in event["detail"]
        assert "\n" not in event["detail"]

    def test_epoch_numbers_are_normalized_to_milliseconds(self) -> None:
        seconds = bridge.normalize_event({"kind": "note", "ts": 1_700_000_000}, seq=1, now_ms=lambda: 0)
        millis = bridge.normalize_event({"kind": "note", "ts": 1_700_000_000_000}, seq=2, now_ms=lambda: 0)
        assert seconds["ts"] == 1_700_000_000_000
        assert millis["ts"] == 1_700_000_000_000


# ----------------------------------------------------------------- gate values


class TestGateResolution:
    def test_env_var_is_used(self, monkeypatch) -> None:
        monkeypatch.setenv(GATE_ENV_NAME, GATE)
        assert bridge.resolve_gate(None, GATE_ENV_NAME, dict(os.environ)) == GATE

    def test_gate_file_wins_over_env(self, tmp_path: Path, monkeypatch) -> None:
        gate_file = tmp_path / "serving.gate"
        gate_file.write_text("  " + "".join(("file", "-", "gate", "-", "9")) + "  \n", encoding="utf-8")
        monkeypatch.setenv(GATE_ENV_NAME, GATE)
        assert bridge.resolve_gate(gate_file, GATE_ENV_NAME, dict(os.environ)) == "file-gate-9"

    def test_none_when_unconfigured(self, tmp_path: Path) -> None:
        assert bridge.resolve_gate(None, GATE_ENV_NAME, {}) is None
        assert bridge.resolve_gate(tmp_path / "missing.gate", GATE_ENV_NAME, {}) is None

    def test_serve_refuses_to_start_unconfigured(self, monkeypatch) -> None:
        monkeypatch.delenv(GATE_ENV_NAME, raising=False)
        env = {k: v for k, v in os.environ.items() if k != GATE_ENV_NAME}
        proc = subprocess.run(
            [sys.executable, str(BRIDGE_PATH), "--serve", "--port", "0"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
            env=env,
        )
        assert proc.returncode == 2
        assert "refusing" in proc.stderr

    def test_no_inline_gate_flag_exists(self) -> None:
        parser = bridge.build_parser()
        args = parser.parse_args([])
        assert hasattr(args, "gate_file")
        assert hasattr(args, "gate_env")
        assert not hasattr(args, "gate_inline")
        flags = [flag for action in parser._actions for flag in action.option_strings]
        for rejected in ("--gate", "--gate-value", "--gate-inline"):
            assert rejected not in flags


# ----------------------------------------------------------- tailnet-only peers


class TestTailnetOnly:
    @pytest.mark.parametrize(
        "host,expected",
        [
            ("127.0.0.1", True),
            ("127.9.9.9", True),
            ("::1", True),
            ("::ffff:127.0.0.1", True),
            ("100.64.0.1", True),
            ("100.127.255.254", True),
            ("192.168.1.5", False),
            ("10.0.0.9", False),
            ("172.16.0.3", False),
            ("8.8.8.8", False),
            ("::ffff:192.168.1.5", False),
            ("not-an-address", False),
        ],
    )
    def test_peer_policy(self, host: str, expected: bool) -> None:
        assert bridge.peer_allowed(host) is expected

    def test_handler_denies_disallowed_peer_with_403(self, server_factory, monkeypatch) -> None:
        target = new_bridge()
        monkeypatch.setattr(bridge, "peer_allowed", lambda host: False)
        srv = server_factory(target)
        stream = open_stream(srv)
        try:
            assert stream.status == 403
            body = stream._readline(time.monotonic() + 2)
            assert body is not None and "forbidden" in body
        finally:
            stream.close()

    def test_allowed_peer_with_wrong_method_gets_405(self, server_factory) -> None:
        target = new_bridge()
        srv = server_factory(target)
        port = srv.server_address[1]
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            sock.sendall(
                (
                    f"HEAD /obs-events HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                    f"{AUTH_NAME}: {gate_header()}\r\nConnection: close\r\n\r\n"
                ).encode("utf-8")
            )
            status = sock.makefile("rb").readline().decode("iso-8859-1")
            assert " 405 " in status
        finally:
            sock.close()


# ------------------------------------------------------------ gate over http


class TestGateOverHttp:
    def test_missing_header_is_401(self, server_factory) -> None:
        srv = server_factory(new_bridge())
        host, port = srv.server_address[:2]
        sock = socket.create_connection((host, port), timeout=5)
        try:
            sock.sendall(f"GET /obs-events HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode("utf-8"))
            reader = sock.makefile("rb")
            status = reader.readline().decode("iso-8859-1")
            assert " 401 " in status
            assert b"unauthorized" in reader.read()
        finally:
            sock.close()

    def test_wrong_value_refused_without_echo(self, server_factory) -> None:
        srv = server_factory(new_bridge())
        stream = open_stream(srv, headers={AUTH_NAME: gate_header(GATE + "x")})
        try:
            assert stream.status == 401
            first = stream._readline(time.monotonic() + 2)
            assert first == "unauthorized"
        finally:
            stream.close()

    def test_correct_value_gets_an_event_stream(self, server_factory) -> None:
        srv = server_factory(new_bridge())
        stream = open_stream(srv)
        try:
            assert stream.status == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            blocks = read_past_hello(stream)
            hello = json.loads(blocks[-1]["data"])
            assert isinstance(hello["cursor"], int)
        finally:
            stream.close()

    def test_unknown_path_is_404_even_with_the_gate(self, server_factory) -> None:
        srv = server_factory(new_bridge())
        stream = open_stream(srv, path="/elsewhere")
        try:
            assert stream.status == 404
        finally:
            stream.close()


# ------------------------------------------------------------ cursor semantics


class TestCursorResume:
    def _seed(self, target, count: int = 5) -> None:
        for index in range(count):
            target.publish_raw({"kind": "note", "detail": f"e{index + 1}"})

    def test_replay_after_cursor_then_live(self, server_factory) -> None:
        target = new_bridge()
        self._seed(target)
        srv = server_factory(target)
        stream = open_stream(srv, path="/obs-events?cursor=2")
        try:
            blocks = read_past_hello(stream, want_after=3)
            assert json.loads(blocks[1]["data"])["cursor"] == 5
            ids = [
                json.loads(block["data"])["seq"]
                for block in blocks
                if "data" in block and block.get("event") != "hello"
            ]
            assert ids == [3, 4, 5]
            target.publish_raw({"kind": "note", "detail": "live"})
            live = stream.read_blocks(want=1, grace_s=3)
            assert json.loads(live[0]["data"])["detail"] == "live"
        finally:
            stream.close()

    def test_last_event_id_header_equivalent(self, server_factory) -> None:
        target = new_bridge()
        self._seed(target)
        srv = server_factory(target)
        stream = open_stream(srv, headers={"Last-Event-ID": "3"})
        try:
            blocks = read_past_hello(stream, want_after=2)
            ids = [
                json.loads(block["data"])["seq"]
                for block in blocks
                if "data" in block and block.get("event") != "hello"
            ]
            assert ids == [4, 5]
        finally:
            stream.close()

    def test_fresh_client_is_live_only(self, server_factory) -> None:
        target = new_bridge()
        self._seed(target)
        srv = server_factory(target)
        stream = open_stream(srv)
        try:
            read_past_hello(stream)
            idle = stream.read_blocks(want=4, grace_s=0.7)
            assert len(idle) >= 2
            assert all("data" not in block for block in idle)
            target.publish_raw({"kind": "note", "detail": "just-live"})
            live = stream.read_blocks(want=1, grace_s=3)
            assert json.loads(live[0]["data"])["detail"] == "just-live"
        finally:
            stream.close()

    def test_replay_flag_replays_whole_buffer(self, server_factory) -> None:
        target = new_bridge()
        self._seed(target)
        srv = server_factory(target)
        stream = open_stream(srv, path="/obs-events?replay=1")
        try:
            blocks = read_past_hello(stream, want_after=5)
            ids = [
                json.loads(block["data"])["seq"]
                for block in blocks
                if "data" in block and block.get("event") != "hello"
            ]
            assert ids == [1, 2, 3, 4, 5]
        finally:
            stream.close()

    def test_gap_cursor_sends_reset_then_goes_live(self, server_factory) -> None:
        target = new_bridge(buffer_size=3)
        self._seed(target, count=6)
        srv = server_factory(target)
        stream = open_stream(srv, path="/obs-events?cursor=1")
        try:
            read_past_hello(stream)
            reset_blocks = stream.read_blocks(want=1, grace_s=3)
            assert reset_blocks and reset_blocks[0]["event"] == "reset"
            assert json.loads(reset_blocks[0]["data"])["reason"] == "cursor-gap"
            target.publish_raw({"kind": "note", "detail": "after-reset"})
            live = stream.read_blocks(want=1, grace_s=3)
            assert json.loads(live[0]["data"])["detail"] == "after-reset"
        finally:
            stream.close()

    def test_cursor_zero_replays_whole_buffer(self, server_factory) -> None:
        target = new_bridge(buffer_size=3)
        self._seed(target, count=6)
        srv = server_factory(target)
        stream = open_stream(srv, path="/obs-events?cursor=0")
        try:
            blocks = read_past_hello(stream, want_after=3)
            ids = [
                json.loads(block["data"])["seq"]
                for block in blocks
                if "data" in block and block.get("event") != "hello"
            ]
            assert ids == [4, 5, 6]
        finally:
            stream.close()


# ------------------------------------------------------------- idle keepalives


class TestHeartbeatBlips:
    def test_idle_blips_flush_with_zero_data_frames(self, server_factory) -> None:
        target = new_bridge()
        srv = server_factory(target, heartbeat_s=0.2)
        stream = open_stream(srv)
        try:
            read_past_hello(stream)
            blocks = stream.read_blocks(want=3, grace_s=1.0)
            assert len(blocks) >= 2
            for block in blocks:
                assert "comments" in block, block
                assert "data" not in block, block
            target.publish_raw({"kind": "note", "detail": "wake"})
            wake = stream.read_blocks(want=1, grace_s=3)
            assert json.loads(wake[0]["data"])["detail"] == "wake"
        finally:
            stream.close()


# --------------------------------------------------------------- source ending


class TestSourceEnded:
    def test_finite_file_source_ends_with_bye(self, tmp_path: Path, server_factory) -> None:
        source = tmp_path / "events.jsonl"
        rows = [
            {"kind": "turn_started", "attempt_id": "att_1", "turn_id": "t1"},
            {"kind": "tool_update", "attempt_id": "att_1", "turn_id": "t1", "tool_name": "pytest"},
            {"kind": "turn_finished", "attempt_id": "att_1", "turn_id": "t1"},
        ]
        source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        target = new_bridge()
        feeder = bridge.FileSource(source, target, follow=False)
        feeder.run()
        srv = server_factory(target)
        stream = open_stream(srv, path="/obs-events?replay=1")
        try:
            blocks = stream.read_until_event("bye", grace_s=4)
            events = [
                block
                for block in blocks
                if "data" in block and block.get("event") not in ("hello", "bye")
            ]
            kinds = [json.loads(block["data"])["kind"] for block in events]
            assert kinds == ["turn.started", "tool.progress", "turn.finished"]
            assert blocks[-1]["event"] == "bye"
            assert stream.read_blocks(want=1, grace_s=1.0) == []
            assert stream.eof
        finally:
            stream.close()

    def test_malformed_lines_are_skipped(self, tmp_path: Path, server_factory) -> None:
        source = tmp_path / "events.jsonl"
        source.write_text(
            "{not json\n"
            + json.dumps({"kind": "note", "detail": "one"}) + "\n"
            + "\n"
            + "[garbage]\n"
            + json.dumps({"kind": "note", "detail": "two"}) + "\n",
            encoding="utf-8",
        )
        target = new_bridge()
        bridge.FileSource(source, target, follow=False).run()
        assert len(target.store_events()) == 2
        srv = server_factory(target)
        stream = open_stream(srv, path="/obs-events?replay=1")
        try:
            blocks = stream.read_blocks(want=4, grace_s=3)
            details = [
                json.loads(block["data"])["detail"]
                for block in blocks
                if "data" in block and block.get("event") != "hello"
            ]
            assert details == ["one", "two"]
        finally:
            stream.close()


# ------------------------------------------------- panel collapse and windowing


def collapse_rows(events: list[dict]) -> list[dict]:
    """Python mirror of the app.js collapse contract (see the README table).

    Adjacent tool progress updates for the same (turn, tool) merge into one
    row; any other kind, a turn change or a tool change starts a new row.
    """
    rows: list[dict] = []
    for event in events:
        merged = False
        if rows and rows[-1]["row"] == "tool" and event["kind"] == "tool.progress":
            last = rows[-1]
            if last["turn"] == event["turn"] and last["tool"] == event["tool"]:
                last["count"] += 1
                last["last_detail"] = event.get("detail")
                merged = True
        if not merged:
            if event["kind"] == "tool.progress":
                rows.append(
                    {
                        "row": "tool",
                        "turn": event["turn"],
                        "tool": event["tool"],
                        "count": 1,
                        "last_detail": event.get("detail"),
                    }
                )
            else:
                rows.append({"row": "event", "kind": event["kind"], "seq": event["seq"]})
    return rows


def window_rows(rows: list[dict], cap: int) -> list[dict]:
    """Python mirror of the app.js windowing contract: keep the last ``cap``."""
    return rows[-cap:]


def tool_update_stress(runs: int = 8, per_run: int = 250, turn: str = "t1") -> list[dict]:
    events = []
    for run in range(runs):
        for _ in range(per_run):
            events.append(
                {
                    "kind": "tool_update",
                    "attempt_id": "att_1",
                    "turn_id": turn,
                    "tool_name": f"tool-{run}",
                    "detail": "progress line",
                }
            )
    return events


class TestPanelCollapseContract:
    def test_2000_tool_updates_collapse_to_8_rows(self) -> None:
        raw_events = tool_update_stress()
        assert len(raw_events) == 2000
        normalized = [
            bridge.normalize_event(raw, seq=index + 1, now_ms=lambda: 0)
            for index, raw in enumerate(raw_events)
        ]
        started = time.perf_counter()
        rows = collapse_rows(normalized)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        tool_rows = [row for row in rows if row["row"] == "tool"]
        assert len(tool_rows) == 8
        assert [row["tool"] for row in tool_rows] == [f"tool-{i}" for i in range(8)]
        assert sum(row["count"] for row in tool_rows) == 2000
        assert elapsed_ms < 1000.0
        print(f"\nstress: 2000 events normalized+collapsed in {elapsed_ms:.1f} ms")

    def test_boundaries_start_new_rows(self) -> None:
        events = [
            bridge.normalize_event({"kind": "tool_update", "turn_id": "t1", "tool_name": "a"}, seq=1, now_ms=lambda: 0),
            bridge.normalize_event({"kind": "tool_update", "turn_id": "t1", "tool_name": "a"}, seq=2, now_ms=lambda: 0),
            bridge.normalize_event({"kind": "note"}, seq=3, now_ms=lambda: 0),
            bridge.normalize_event({"kind": "tool_update", "turn_id": "t1", "tool_name": "a"}, seq=4, now_ms=lambda: 0),
            bridge.normalize_event({"kind": "tool_update", "turn_id": "t2", "tool_name": "a"}, seq=5, now_ms=lambda: 0),
        ]
        rows = collapse_rows(events)
        tool_rows = [row for row in rows if row["row"] == "tool"]
        assert len(tool_rows) == 3
        assert [row["count"] for row in tool_rows] == [2, 1, 1]

    def test_window_keeps_the_last_cap_in_order(self) -> None:
        rows = [{"seq": index} for index in range(1000)]
        kept = window_rows(rows, 400)
        assert len(kept) == 400
        assert kept[0]["seq"] == 600
        assert kept[-1]["seq"] == 999


# ------------------------------------------------------------------- e2e + CLI


class TestEndToEndStream:
    def test_stream_from_file_source_over_a_real_socket(self, tmp_path: Path, server_factory) -> None:
        source = tmp_path / "events.jsonl"
        rows = [
            {"kind": "attempt_started", "attempt_id": "att_1", "ts": 1_700_000_000},
            {"kind": "turn_started", "attempt_id": "att_1", "turn_id": "t1"},
            {"kind": "tool_update", "attempt_id": "att_1", "turn_id": "t1", "tool_name": "pytest", "detail": "3 passed"},
            {"kind": "tool_result", "attempt_id": "att_1", "turn_id": "t1", "tool_name": "pytest"},
            {"kind": "turn_finished", "attempt_id": "att_1", "turn_id": "t1"},
        ]
        source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        target = new_bridge()
        bridge.FileSource(source, target, follow=False).run()
        srv = server_factory(target)
        stream = open_stream(srv, path="/obs-events?replay=1")
        try:
            assert stream.status == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            blocks = stream.read_until_event("bye", grace_s=5)
            assert blocks[0].get("retry") == "3000" or blocks[0].get("event") == "hello"
            data_blocks = [block for block in blocks if "data" in block and "event" in block
                           and block["event"] not in ("hello", "bye")]
            assert [json.loads(block["data"])["seq"] for block in data_blocks] == [1, 2, 3, 4, 5]
            kinds = [json.loads(block["data"])["kind"] for block in data_blocks]
            assert kinds == ["bee.started", "turn.started", "tool.progress", "tool.done", "turn.finished"]
            assert [block.get("id") for block in data_blocks] == ["1", "2", "3", "4", "5"]
            assert blocks[-1]["event"] == "bye"
            assert stream.read_blocks(want=1, grace_s=1.0) == []
            assert stream.eof
        finally:
            stream.close()

    def test_default_mode_prints_normalized_jsonl(self, tmp_path: Path) -> None:
        source = tmp_path / "events.jsonl"
        source.write_text(json.dumps({"kind": "turn_started", "attempt_id": "att_1"}) + "\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(BRIDGE_PATH), "--source", str(source)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        assert proc.returncode == 0, proc.stderr
        lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        assert len(lines) == 1
        assert lines[0]["kind"] == "turn.started"
        assert lines[0]["bee"] == "att_1"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
