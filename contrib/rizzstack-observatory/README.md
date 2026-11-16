# rizzstack-observatory: live panel wiring

This directory documents how the Observatory live panel is wired to its two
backend routes and where every moving part lives. The panel itself is
`apps/rizzstack-observatory/`; the streaming side of the backend is
`contrib/rizzstack-observability/events_bridge.py`.

## The two routes

| Route | Served by | Lease | Purpose |
| --- | --- | --- | --- |
| `GET /obs-snapshot` | `contrib/rizzstack-observability/collector.py` | already merged (base) | one point-in-time `rizzstack.observability/snapshot/1` document: fleet, usage, pipeline, backlog, ci, failures, health, alerts |
| `GET /obs-events` | `contrib/rizzstack-observability/events_bridge.py` | this lease | Server-Sent Events stream of the launcher's per-attempt event feed, with cursor resume |

The browser only ever talks to its own origin. The **orbitdesktop proxy**
terminates the browser session, checks the operator in, and forwards both
routes over the tailnet to the collector and the bridge. The proxy
implementation itself is **out of this lease** - it is a named gap tracked
for its own PR; this lease defines the contract it will forward (paths,
headers, stream framing) and nothing more.

## App file layout

```
apps/rizzstack-observatory/
  app.js      panel logic: fleet -> bee -> streaming turn tail
  styles.css  panel styling (dark, dense, monospace tail)
```

`app.js` mounts itself: if the serving shell does not provide the skeleton,
it builds one into `document.body`. A shell that wants to host the panel
only needs those ids to exist somewhere in the page:

| Element id | Role |
| --- | --- |
| `obs-panel` | root (optional; built when missing) |
| `obs-status` | connection badge, cursor and rate line |
| `obs-fleet` | fleet column: one row per attempt (bee) |
| `obs-bee-name` | selected bee heading |
| `obs-filters` | kind filter chips |
| `obs-tail` | the streaming turn tail of the selected bee |
| `obs-reconnect` | manual reopen button (after a `bye`) |

`app.js` also exports its pure helpers (`railsKindOf`, `normalizeEvent`,
`collapseToolUpdates`, `applyWindow`, `RAILS_KINDS`, `WINDOW_ROWS`) under
`module.exports` so the node stress harness can exercise the real panel code
without a browser.

## Event pipeline and the mapping table

The launcher writes one JSON event per line (stdout, or a JSONL file). The
bridge normalizes each line and emits frames whose `event:` name is the
**rails vocabulary** kind. The panel only speaks that vocabulary, so a later
upgrade to rails-native rendering is a data swap, not a rewrite.

`KIND_MAP` in `events_bridge.py` is the single adjustment point for kind
drift; `FIELD_CANDIDATES` is the single adjustment point for payload
field-name drift (first present candidate wins, unknown fields pass through
in `payload`).

| Launcher kind (tolerant aliases) | Rails vocabulary | Panel row |
| --- | --- | --- |
| `attempt_started`, `attempt.start`, `bee_started` | `bee.started` | bee lifecycle row |
| `attempt_state`, `state_changed`, `phase_changed` | `bee.state` | state badge row (lifecycle enum) |
| `attempt_finished`, `attempt_completed` | `bee.finished` | bee lifecycle row |
| `turn_started`, `turn.start` | `turn.started` | turn heading |
| `turn_finished`, `turn.finish`, `turn_complete` | `turn.finished` | turn heading close |
| `tool_update`, `tool.update`, `tool_progress`, `tool_call` | `tool.progress` | collapsed tool row |
| `tool_result`, `tool.done`, `tool_finished`, `tool_output` | `tool.done` | tool result row |
| `bee_note`, `note`, `log`, `heartbeat` | `bee.note` | note row |
| `bee_error`, `error`, `failure` | `bee.error` | error row |
| anything else | `event.other` | passthrough row |

Payload state labels are normalized through the same closed lifecycle enum
the collector uses (`verifying` folds to `working`, `complete` to
`succeeded`, and so on); unrecognized labels are preserved as-is, never
dropped.

## Cursor resume semantics

- Every data frame carries a monotonic `id:` (the bridge sequence number).
- A client that reconnects sends `Last-Event-ID` (EventSource does this
  automatically) or `?cursor=N`; the bridge replays everything after that
  sequence from its bounded buffer, then continues live.
- `?cursor=0` or `?replay=1` replays the whole buffer.
- A positive cursor older than the buffer triggers an `event: reset` frame;
  the panel then refetches `/obs-snapshot` and reopens a fresh stream.
- A client without a cursor gets a `hello` frame with the current cursor and
  live frames only - history comes from the snapshot route.
- Idle periods are flushed as comment-only frames (`: ping`) with **zero
  data frames**, so proxies keep the stream warm without inventing events.
- When the launcher source ends, clients are caught up and the stream closes
  with an `event: bye` frame.

## Gate and tailnet-only posture

The bridge checks the shared gate value **server-side on every request**,
using a constant-time comparison, and never echoes it. The value is read at
runtime:

1. `--gate-file PATH` (single line, mode 0600) wins;
2. otherwise the `RIZZSTACK_OBS_TOKEN` environment variable - the same
   store the collector already uses, so the proxy can forward one
   credential to both routes.

There is deliberately **no inline flag**. Rejected alternative, documented
for the record: inlining the shared value with a redaction notice. It was
rejected because the verify scanner reads every added line of every leased
file and because the tailnet-only posture requires env/config sourcing
anyway - an inline value would be dead code inviting the exact failure mode
the scanner exists to catch. An unconfigured bridge refuses to start.

Peers must come from loopback or the tailnet range `100.64.0.0/10`; anything
else is refused with 403 before the gate is evaluated. Binding a wildcard
address is refused. Requests are never logged, because headers could carry
credential material.

## Running it

```
python3 contrib/rizzstack-observability/events_bridge.py \
  --serve --launcher "python3 /path/to/launcher --emit jsonl" --port 8790

python3 contrib/rizzstack-observability/events_bridge.py \
  --serve --source /path/to/events.jsonl --port 8790

python3 contrib/rizzstack-observability/events_bridge.py \
  --source /path/to/events.jsonl        # filter mode: normalized JSONL on stdout
```

Flags: `--host` (specific loopback or tailnet address; wildcard refused),
`--gate-file`, `--gate-env`, `--buffer` (replay buffer size, default 5000),
`--heartbeat-ms` (idle flush interval, default 1000).

Smoke shape (as exercised by the worker checks): start the bridge with a
scripted launcher, then `curl -sN` the events route with the gate header and
watch ordered `id:`/`event:`/`data:` frames end in `bye`.

## Tests

```
python3 -m pytest tests/test_obs_events_bridge.py -q
```

The suite is stdlib-only. On machines where pytest is not installed on the
system interpreter, use a venv (the sandbox note in the lease history
documents this). The collapse/windowing contracts are mirrored in python
there; `apps/rizzstack-observatory/app.js` itself is exercised against the
same numbers by a small node harness that imports the exported helpers and
asserts the stress class: 2000 tool progress events in 8 runs collapse to
exactly 8 rows, with ingest plus drain in the tens of milliseconds.

## Scope boundaries and carried issues

- The orbitdesktop proxy implementation is a named gap for its own PR.
- Multi-attempt subscriptions (one stream fanning out to several bees) are
  out of scope for v1; the stream is per-bridge, the panel filters by bee.
- The collector and the `/obs-snapshot` document are base scope; this lease
  only consumes them tolerantly (a missing or failing snapshot degrades to
  stream-only operation).
- Launcher payload field names are normalized tolerantly; when the real
  launcher's field names drift, adjust `FIELD_CANDIDATES` (and, for kind
  spellings, `KIND_MAP`) - those tables are the single adjustment points.
- Carried from earlier rounds: six offline test failures in
  `tests/test_feature_packet.py` and `tests/test_return_manifest.py` are
  pre-existing at the base commit (they pin remote commits and fail without
  network); they are unrelated to this lease.
