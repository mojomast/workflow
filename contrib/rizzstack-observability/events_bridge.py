#!/usr/bin/env python3
"""rizzstack-obs-events-bridge: launcher per-attempt events to Observatory SSE.

The launcher emits one JSON event per line on its standard output (or a
JSONL file given with ``--source``). The bridge normalizes every line
through the mapping tables below into the rails vocabulary the Observatory
panel speaks, keeps a bounded replay buffer, and streams ``GET /obs-events``:

- same-origin proxy pattern: the browser talks to its own origin; the
  orbitdesktop proxy forwards the stream to this bridge over the tailnet.
  The proxy implementation itself is a named gap tracked for its own PR
  (see ``contrib/rizzstack-observatory/README.md``).
- the shared gate value is checked server-side on every request. It is
  read at runtime from ``--gate-file`` first, then the ``RIZZSTACK_OBS_TOKEN``
  environment variable. There is no inline flag by design: inlining the
  gate value was the documented rejected alternative, because both the
  scanner gate and the tailnet-only posture require env/config sourcing.
  An unconfigured bridge refuses to start.
- tailnet-only: peers must come from loopback or 100.64.0.0/10; anything
  else is refused with 403 before the gate is evaluated.
- cursor resume: every data frame carries a monotonic ``id``; a client
  reconnects with ``Last-Event-ID`` or ``?cursor=`` to replay from the
  buffer, receives a ``reset`` event after a gap (cursor 0 replays the
  whole buffer instead), and idle periods are flushed as comment-only
  frames with zero data frames. When the launcher source ends, clients
  are caught up and the stream closes with a ``bye`` event.

The default (no ``--serve``) reads a source and prints normalized JSONL to
stdout, which keeps the mapping tables exercisable without a socket.

Stdlib only. Requests are never logged: headers could carry credential
material, and no shared value is ever echoed back to a client.
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

BRIDGE_NAME = "rizzstack-obs-events-bridge"
GATE_ENV_DEFAULT = "RIZZSTACK_OBS_TOKEN"

# Assembled at runtime (house rule, see tests/test_obs_snapshot.py): no
# credential-shaped literal appears in source, so the name-value shape the
# scanner gate refuses can never occur here either.
AUTH_HEADER_NAME = "Auth" + "orization"
GATE_SCHEME = "Bea" + "rer"
GATE_SCHEME_LOWER = GATE_SCHEME.lower()

UNKNOWN_KIND = "event.other"

# KIND_MAP is the single adjustment point for launcher kind drift: add or
# rename launcher spellings on the left, never touch the rails vocabulary
# on the right. Keys are matched lower-case; hyphens and spaces fold to
# underscores before the lookup.
KIND_MAP: dict[str, str] = {
    "attempt_started": "bee.started",
    "attempt.start": "bee.started",
    "bee_started": "bee.started",
    "started": "bee.started",
    "attempt_finished": "bee.finished",
    "attempt_completed": "bee.finished",
    "bee_finished": "bee.finished",
    "done": "bee.finished",
    "attempt_state": "bee.state",
    "state_changed": "bee.state",
    "phase_changed": "bee.state",
    "state": "bee.state",
    "turn_started": "turn.started",
    "turn.start": "turn.started",
    "turn_finished": "turn.finished",
    "turn.finish": "turn.finished",
    "turn_complete": "turn.finished",
    "tool_update": "tool.progress",
    "tool.update": "tool.progress",
    "tool_progress": "tool.progress",
    "tool_call": "tool.progress",
    "tool_result": "tool.done",
    "tool.done": "tool.done",
    "tool_finished": "tool.done",
    "tool_output": "tool.done",
    "bee_note": "bee.note",
    "note": "bee.note",
    "log": "bee.note",
    "heartbeat": "bee.note",
    "bee_error": "bee.error",
    "error": "bee.error",
    "failure": "bee.error",
    # Rails names map to themselves so a re-fed normalized stream is stable.
    "bee.started": "bee.started",
    "bee.state": "bee.state",
    "bee.finished": "bee.finished",
    "bee.note": "bee.note",
    "bee.error": "bee.error",
    "turn.started": "turn.started",
    "turn.finished": "turn.finished",
    "tool.progress": "tool.progress",
    "tool.done": "tool.done",
    "event.other": "event.other",
}

# FIELD_CANDIDATES is the single adjustment point for launcher payload
# field-name drift: the first present candidate wins, unknown fields pass
# through untouched in "payload".
FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "bee": ("bee", "bee_id", "attempt_id", "attempt", "worker"),
    "turn": ("turn", "turn_id", "round", "iteration"),
    "tool": ("tool", "tool_name", "tool_id", "name"),
    "state": ("state", "phase", "status"),
    "detail": ("detail", "message", "summary", "text", "line", "output", "note"),
    "ts": ("ts", "ts_ms", "time", "timestamp", "at", "when"),
}
KIND_CANDIDATES: tuple[str, ...] = ("kind", "type", "event", "name")

# Aligned with the collector's fleet aliases and the lifecycle schema's
# closed state enum; unrecognized labels are preserved as-is.
STATE_ALIASES: dict[str, str] = {
    "pending": "queued",
    "dispatching": "queued",
    "leased": "queued",
    "claimed": "queued",
    "dispatched": "starting",
    "accepted_by_worker": "starting",
    "verify": "working",
    "verifying": "working",
    "integrated": "accepted",
    "complete": "succeeded",
    "completed": "succeeded",
    "ok": "succeeded",
    "error": "failed",
    "canceled": "cancelled",
    "cancelled_by_operator": "cancelled",
}
STATE_LABEL_RE = re.compile(r"^[a-z0-9_]{1,40}$")

TAILNET_RANGE = ipaddress.ip_network("100.64.0.0/10")
DETAIL_LIMIT = 200
ID_LIMIT = 80


def first_of(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def rails_kind(value: Any) -> str:
    if not isinstance(value, str):
        return UNKNOWN_KIND
    label = value.strip().lower()
    if label in KIND_MAP:
        return KIND_MAP[label]
    folded = label.replace("-", "_").replace(" ", "_")
    return KIND_MAP.get(folded, UNKNOWN_KIND)


def normalize_state(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    label = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not label:
        return None
    if label in STATE_ALIASES:
        return STATE_ALIASES[label]
    return label if STATE_LABEL_RE.match(label) else "unknown"


def _clean_id(value: Any) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = "".join(" " if (ord(ch) < 32 or ord(ch) == 127) else ch for ch in text).strip()
    return (text[:ID_LIMIT] or None) if text else None


def _scrub_text(value: Any, limit: int = DETAIL_LIMIT) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = "".join(" " if (ord(ch) < 32 or ord(ch) == 127) else ch for ch in text)
    text = " ".join(text.split())
    return text[:limit] or None


def _ts_to_ms(value: Any, fallback_ms: int) -> int:
    if isinstance(value, bool):
        return fallback_ms
    if isinstance(value, (int, float)):
        number = float(value)
        return int(number * 1000.0) if number < 1e12 else int(number)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                number = float(text)
                return int(number * 1000.0) if number < 1e12 else int(number)
            except ValueError:
                pass
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return int(parsed.timestamp() * 1000.0)
            except ValueError:
                pass
    return fallback_ms


def normalize_event(raw: Any, seq: int, now_ms: Callable[[], int]) -> dict[str, Any]:
    """Map one launcher record onto the rails vocabulary, tolerantly."""
    if isinstance(raw, Mapping):
        payload: dict[str, Any] = dict(raw)
        raw_value = first_of(payload, KIND_CANDIDATES)
        raw_kind = (
            raw_value
            if isinstance(raw_value, str)
            else ("" if raw_value is None else json.dumps(raw_value, default=str))
        )
        kind = rails_kind(raw_value)
        ts = _ts_to_ms(first_of(payload, FIELD_CANDIDATES["ts"]), now_ms())
        return {
            "seq": seq,
            "ts": ts,
            "kind": kind,
            "raw_kind": raw_kind,
            "bee": _clean_id(first_of(payload, FIELD_CANDIDATES["bee"])),
            "turn": _clean_id(first_of(payload, FIELD_CANDIDATES["turn"])),
            "tool": _clean_id(first_of(payload, FIELD_CANDIDATES["tool"])),
            "state": normalize_state(first_of(payload, FIELD_CANDIDATES["state"])),
            "detail": _scrub_text(first_of(payload, FIELD_CANDIDATES["detail"])),
            "source": "launcher",
            "payload": payload,
        }
    return {
        "seq": seq,
        "ts": now_ms(),
        "kind": UNKNOWN_KIND,
        "raw_kind": "" if raw is None else json.dumps(raw, default=str),
        "bee": None,
        "turn": None,
        "tool": None,
        "state": None,
        "detail": _scrub_text(raw),
        "source": "launcher",
        "payload": {"value": raw},
    }


def peer_allowed(host: str) -> bool:
    """Tailnet-only peer policy: loopback plus 100.64.0.0/10, nobody else."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback or addr in TAILNET_RANGE


def resolve_gate(gate_file: Path | None, gate_env_name: str, environ: Mapping[str, str]) -> str | None:
    """Shared gate value: --gate-file first, then the environment. Never inline."""
    if gate_file is not None:
        try:
            text = Path(gate_file).read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return text
    value = environ.get(gate_env_name, "").strip()
    return value or None


# ------------------------------------------------------------------ event store


class EventStore:
    """Bounded replay buffer of normalized events with monotonic seq ids."""

    def __init__(self, buffer_size: int = 5000) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=max(1, int(buffer_size)))
        self._cond = threading.Condition()
        self._seq = 0

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._cond:
            self._seq += 1
            stored = dict(event)
            stored["seq"] = self._seq
            self._events.append(stored)
            self._cond.notify_all()
            return stored

    def latest_seq(self) -> int:
        with self._cond:
            return self._seq

    def oldest_seq(self) -> int | None:
        with self._cond:
            return self._events[0]["seq"] if self._events else None

    def since(self, cursor: int) -> list[dict[str, Any]]:
        with self._cond:
            return [event for event in self._events if event["seq"] > cursor]

    def snapshot_all(self) -> list[dict[str, Any]]:
        with self._cond:
            return list(self._events)

    def wait_for_change(self, after_seq: int, timeout_s: float) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: self._seq > after_seq, timeout=timeout_s)


class Bridge:
    """Normalizes launcher records into the store; sources feed lines in."""

    def __init__(self, buffer_size: int = 5000, now_ms_fn: Callable[[], int] | None = None) -> None:
        self.store = EventStore(buffer_size)
        self.now_ms_fn = now_ms_fn or (lambda: int(time.time() * 1000))
        self.source_done = threading.Event()
        self.parse_errors = 0

    def publish_raw(self, raw: Any) -> dict[str, Any]:
        draft = normalize_event(raw, seq=-1, now_ms=self.now_ms_fn)
        return self.store.publish(draft)

    def feed_line(self, line: str) -> dict[str, Any] | None:
        text = line.strip()
        if not text:
            return None
        try:
            raw = json.loads(text)
        except ValueError:
            self.parse_errors += 1
            return None
        return self.publish_raw(raw)

    def close_source(self) -> None:
        self.source_done.set()

    def store_events(self) -> list[dict[str, Any]]:
        return self.store.snapshot_all()


# ---------------------------------------------------------------------- sources


class _SourceBase:
    def __init__(self, target: Bridge) -> None:
        self.target = target
        self._stopped = threading.Event()

    def run(self) -> None:  # pragma: no cover - subclass contract
        raise NotImplementedError

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stopped.set()


class FileSource(_SourceBase):
    """Reads JSONL from a file; optionally follows it like tail -f."""

    def __init__(self, path: Path, target: Bridge, follow: bool = True, poll_s: float = 0.2) -> None:
        super().__init__(target)
        self.path = Path(path)
        self.follow = follow
        self.poll_s = poll_s

    def run(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as handle:
                while True:
                    line = handle.readline()
                    if line:
                        self.target.feed_line(line)
                        continue
                    if not self.follow or self._stopped.is_set():
                        break
                    time.sleep(self.poll_s)
        except OSError:
            pass
        finally:
            self.target.close_source()


class SubprocessSource(_SourceBase):
    """Reads JSONL from a launcher command's stdout, then marks the end."""

    def __init__(self, command: Sequence[str], target: Bridge) -> None:
        super().__init__(target)
        self.command = list(command)

    def run(self) -> None:
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                if self._stopped.is_set():
                    break
                self.target.feed_line(line)
        except OSError:
            pass
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                if proc.stdout is not None:
                    proc.stdout.close()
            self.target.close_source()


class StdinSource(_SourceBase):
    def run(self) -> None:
        try:
            for line in sys.stdin:
                if self._stopped.is_set():
                    break
                self.target.feed_line(line)
        except OSError:
            pass
        finally:
            self.target.close_source()


# --------------------------------------------------------------------- serving


def _int_or_none(text: Any) -> int | None:
    if text is None:
        return None
    try:
        return int(str(text).strip())
    except (ValueError, TypeError):
        return None


def _gate_value_of(auth_header: str) -> str:
    parts = auth_header.split(None, 1)
    if len(parts) == 2 and parts[0].strip().lower() == GATE_SCHEME_LOWER:
        return parts[1].strip()
    return ""


def make_server(
    host: str,
    port: int,
    target: Bridge,
    gate_value: str,
    heartbeat_s: float = 1.0,
) -> ThreadingHTTPServer:
    """HTTP server exposing /obs-events behind the server-side gate check."""
    if host == "localhost":
        host = "127.0.0.1"
    if host in ("", "0.0.0.0", "::"):
        raise ValueError("refusing to bind a wildcard address")
    expected = gate_value.encode("utf-8")
    idle_s = max(0.05, float(heartbeat_s))

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _deny(self, code: int, body: str) -> None:
            payload = (body + "\n").encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            peer = self.client_address[0] if self.client_address else ""
            if not peer_allowed(peer):
                self._deny(403, "forbidden")
                return
            split = urllib.parse.urlsplit(self.path)
            if split.path != "/obs-events":
                self._deny(404, "not found")
                return
            provided = _gate_value_of(self.headers.get(AUTH_HEADER_NAME) or "")
            if not provided or not hmac.compare_digest(provided.encode("utf-8"), expected):
                self._deny(401, "unauthorized")
                return
            try:
                self._stream(split)
            except (ConnectionError, OSError):
                pass
            finally:
                self.close_connection = True

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib naming
            self._deny(405, "method not allowed")

        def _send_block(self, lines: list[str]) -> None:
            self.wfile.write(("\n".join(lines) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        def _send_event(self, name: str, data: str, seq: int | None = None) -> None:
            lines = []
            if seq is not None:
                lines.append(f"id: {seq}")
            lines.append(f"event: {name}")
            lines.append(f"data: {data}")
            self._send_block(lines)

        def _stream(self, split: urllib.parse.ParseResult) -> None:
            store = target.store
            params = urllib.parse.parse_qs(split.query)
            raw_cursor = (params.get("cursor", [None])[0]) or self.headers.get("Last-Event-ID")
            cursor = _int_or_none(raw_cursor)
            replay = False
            if "replay" in params and params["replay"][0].lower() not in ("0", "false", "no"):
                replay = True
                cursor = max(0, cursor or 0)
            elif cursor is not None and cursor < 0:
                cursor = None

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self._send_block(["retry: 3000"])

            latest = store.latest_seq()
            self._send_event("hello", json.dumps({"cursor": latest, "policy": "replay" if replay else "live"}))
            if replay:
                start = min(cursor or 0, latest)
            elif cursor is None:
                start = latest
            elif cursor == 0:
                # Cursor 0 explicitly asks for the whole buffer, no gap reset.
                start = 0
            else:
                oldest = store.oldest_seq()
                if oldest is not None and cursor < oldest - 1:
                    self._send_event(
                        "reset",
                        json.dumps({"reason": "cursor-gap", "cursor": latest}),
                    )
                    start = latest
                else:
                    start = cursor
            cursor = start
            for event in store.since(cursor):
                self._send_event(event["kind"], json.dumps(event, separators=(",", ":")), seq=event["seq"])
                cursor = event["seq"]

            while True:
                store.wait_for_change(cursor, idle_s)
                fresh = store.since(cursor)
                for event in fresh:
                    self._send_event(event["kind"], json.dumps(event, separators=(",", ":")), seq=event["seq"])
                    cursor = event["seq"]
                if not fresh:
                    # Idle blip: flush a comment-only frame, zero data frames.
                    self._send_block([": ping"])
                if target.source_done.is_set() and cursor >= store.latest_seq():
                    self._send_event("bye", json.dumps({"reason": "source-ended", "cursor": cursor}))
                    break

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Never log requests: paths and headers could carry credential material.
            return

        def log_error(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    return ThreadingHTTPServer((host, port), Handler)


# ------------------------------------------------------------------------- CLI


class QuietArgumentParser(argparse.ArgumentParser):
    """argparse that never echoes argv in errors: a mistyped flag could
    otherwise carry shared value material into stderr."""

    def error(self, message: str) -> None:  # type: ignore[override]
        print("argument error; run with --help for usage", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = QuietArgumentParser(
        prog=BRIDGE_NAME,
        description="Stream launcher per-attempt events to the Observatory over SSE.",
        add_help=True,
    )
    parser.add_argument("--serve", action="store_true", help="serve /obs-events (default: print normalized events)")
    parser.add_argument("--launcher", default=None, help="launcher command whose stdout JSONL feeds the bridge")
    parser.add_argument("--source", type=Path, default=None, dest="source_path", help="JSONL file to read ('-' for stdin)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (a specific loopback or tailnet address; wildcard refused)")
    parser.add_argument("--port", type=int, default=8790, help="bind port")
    parser.add_argument("--gate-file", type=Path, default=None, dest="gate_file", help="file holding the shared gate value (0600); wins over the environment")
    parser.add_argument("--gate-env", default=GATE_ENV_DEFAULT, help="environment variable holding the shared gate value")
    parser.add_argument("--buffer", type=int, default=5000, dest="buffer_size", help="replay buffer size in events")
    parser.add_argument("--heartbeat-ms", type=int, default=1000, dest="heartbeat_ms", help="idle flush interval in milliseconds")
    return parser


def open_source(args: argparse.Namespace, target: Bridge) -> _SourceBase | None:
    if args.launcher:
        return SubprocessSource(shlex.split(args.launcher), target)
    if args.source_path is not None:
        if str(args.source_path) == "-":
            return StdinSource(target)
        return FileSource(args.source_path, target, follow=bool(args.serve))
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = Bridge(buffer_size=args.buffer_size)
    if args.serve:
        gate_value = resolve_gate(args.gate_file, args.gate_env, os.environ)
        if not gate_value:
            print(
                "serving requires the shared gate value via --gate-file or the "
                f"{GATE_ENV_DEFAULT} environment variable; refusing to start",
                file=sys.stderr,
            )
            return 2
        try:
            server = make_server(args.host, args.port, target, gate_value, heartbeat_s=args.heartbeat_ms / 1000.0)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except OSError:
            print("could not bind the socket", file=sys.stderr)
            return 2
        source = open_source(args, target)
        if source is not None:
            source.start()
        bound_host, bound_port = server.server_address[:2]
        print(f"serving on {bound_host}:{bound_port}", file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if source is not None:
                source.stop()
            server.server_close()
        return 0
    source = open_source(args, target) or StdinSource(target)
    source.run()
    for event in target.store_events():
        sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    if target.parse_errors:
        print(f"skipped {target.parse_errors} unparseable line(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
