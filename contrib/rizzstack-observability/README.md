# rizzstack-obs-collector

A stdlib-only, **read-only** aggregator that assembles one
`rizzstack.observability/snapshot/1` document (contract:
[`observability/schemas/snapshot.schema.json`](../../observability/schemas/snapshot.schema.json))
from the sources an operator already has, and serves it as JSON over loopback
HTTP behind a bearer credential. No dependency beyond Python 3.9+; no writes
anywhere; nothing leaves the machine except through the loopback socket you
choose to open.

## Why

The observability record formats in `observability/` are frozen contracts, but
nothing reads them yet. This collector is the smallest read path: it turns
plugin local state, the Hermes bundlebees CLI, the `gh` CLI, and a
`bee.usage/v1` JSONL ledger into one validating snapshot that the planned Orbit
dashboard (or any local consumer) can poll.

## Sources and sections

| Section | Source | Notes |
| --- | --- | --- |
| `fleet` | `hermes bundlebees attempts` and `hermes bundlebees status` (read-only CLI subcommands) | Live attempt states normalized to the lifecycle-aligned state vocabulary; unrecognized labels are carried as `unknown` with the raw label in `detail`. `in_flight` and `bee_cap` come from the CLI's `status` summary; when that call cannot answer, `in_flight` falls back to counting active rows the `attempts` call itself reported, and `bee_cap` stays null. |
| `usage` | a `bee.usage/v1` JSONL file (`--usage PATH`) | Tokens and cost aggregated by model/provider and by repo. Unknown token or cost values stay null and set the family's status to `partial`/`unknown` — unknown is never folded into 0. |
| `pipeline` | `jobs/*.json` under `--state-dir` | Task states, escalation reasons (including an awaiting approval gate), and blocker rows for rejected/failed/superseded tasks. Unrecognized task states are skipped: the vocabulary is closed. |
| `backlog` | `queue.json` | Feature rows and per-status counts. |
| `ci` | `gh pr list` / `gh pr checks` (read-only) | Repos are the union of `--repo OWNER/NAME` flags and the repos named by pipeline jobs. Check names only — never logs or URLs. |
| `failures` | `verify-results/*.json` | Classified with the closed `failure/v1` class vocabulary; passing verify records produce no row. |
| `health` | metrics `*.jsonl` + usage quota hints + fleet counts | Scheduler liveness from the newest metrics event age; quota rows in the `resource-snapshot/v1` row shape. |
| `alerts` | derived | Warn-only checks against the `alert.thresholds/v1` keys (bee cap, allowance percent, DeepSeek floor, blocker age, daily spend, no-progress window). Thresholds load from `observability/alerts.defaults.json` when present. |

Every record — the document and every row inside a section — carries `schema`
and `generated_at`. Every section carries `status`:

- `live` — the source was read this run;
- `stale` — the source was read but its newest data is older than
  `--stale-after-s` (default 1800 s);
- `unavailable` — the source is missing, unreadable, or the reader refused:
  rows are empty and `error` names a generic cause.

The top-level `degraded` array lists the sections not `live` this run. A
missing source is a degradation, never a crash, and the other sections still
report.

The fleet section derives from two fixed read-only subcommands. When the CLI
cannot answer, it degrades with a precise generic cause — `fleet_cli_missing`
(the binary is absent or not executable), `fleet_cli_timeout` (the subprocess
budget elapsed), `fleet_command_failed` (non-zero exit), or
`fleet_output_unparseable` (exit 0 but no attempts list in the output) — and
`in_flight`/`bee_cap` stay null rather than collapsing to zero. When the
newest row's `updated_at` is older than `--stale-after-s`, the section marks
itself `stale` while keeping the rows it read. The health section consumes the
same fleet numbers: its `bees_in_flight` quota row (value, cap, remaining)
appears only when the CLI reported them, and unknown counts stay null there
too.

## Usage

```bash
# Print one snapshot to stdout (no credential needed for a local dump):
python3 contrib/rizzstack-observability/collector.py \
    --state-dir ~/.hermes/plugin-state \
    --usage ~/.hermes/usage/usage.jsonl

# Serve it on loopback with a bearer check (credential file, mode 0600):
python3 contrib/rizzstack-observability/collector.py \
    --state-dir ~/.hermes/plugin-state \
    --usage ~/.hermes/usage/usage.jsonl \
    --serve --host 127.0.0.1 --port 8787 \
    --bearer-token-file ~/.config/rizzstack-obs/8787.credential
```

Then:

```bash
curl -H "Authorization: Bearer $(cat ~/.config/rizzstack-obs/8787.credential)" \
    http://127.0.0.1:8787/ | python3 -m json.tool | less
```

Flags:

| Flag | Meaning |
| --- | --- |
| `--state-dir DIR` | plugin local state: `jobs/`, `verify-results/`, `metrics/`, `queue.json` |
| `--usage PATH` | `bee.usage/v1` JSONL ledger (path argument; not copied or rewritten) |
| `--repo OWNER/NAME` | extra repo for the `ci` section; repeatable |
| `--stale-after-s N` | freshness threshold (default 1800) |
| `--bundlebees-bin NAME` | Hermes CLI binary for the fleet section (default `hermes`) |
| `--gh-bin NAME` | GitHub CLI binary (default `gh`) |
| `--cli-timeout-s S` | subprocess timeout (default 10) |
| `--serve` | serve on loopback HTTP instead of printing |
| `--host` / `--port` | bind address (loopback addresses only) and port |
| `--bearer-token-file PATH` | file holding the serving credential, mode 0600 |

## Serving and credentials

- The server refuses any non-loopback bind address. The snapshot is not meant
  to leave the machine unescorted; put a tunnel with its own authentication in
  front of it if a remote consumer needs it.
- Every request must present `Authorization: Bearer <credential>`. The
  credential comes from `--bearer-token-file`, then the suppressed
  `--bearer-token` flag (discouraged: it can leak through a process listing),
  then the `RIZZSTACK_OBS_TOKEN` environment variable. Serving without one
  refuses to start (exit 2).
- The credential is compared in constant time and is never printed or logged.
  Request logging is disabled entirely: request paths and headers are dropped
  on the floor. Errors are reported as generic codes (`fleet_command_failed`,
  `source_missing`, …) — stderr from the invoked CLIs is never copied into a
  record or a log line.
- The systemd user template `rizzstack-obs-collector.service` wires this up
  with an `EnvironmentFile` so the credential never appears on a command line.

## Read-only guarantees

- Files are opened for reading only; nothing is created, moved, or removed.
- The CLI calls it makes are a fixed read-only allowlist, exactly as invoked
  in `collector.py`: `<bundlebees-bin> bundlebees attempts`,
  `<bundlebees-bin> bundlebees status`, `gh pr list --repo <slug> --state open --json …`, and
  `gh pr checks <number> --repo <slug> --json name,state`. `gh pr view` is
  not on the allowlist and is never called, and no mutating bundlebees or
  `gh` verb is ever called.
- The collector holds no credential of its own: the fleet and CI sections use
  whatever ambient authentication those CLIs already have. It does not read,
  write, or move keys.
- `tests/test_obs_snapshot.py::TestReadOnly` proves no file in the state tree
  changes across snapshots.

## Privacy

Records keep the observability package's rules: repository fields are
`owner/name` slugs, and keeping prompts, patches, transcripts, credentials,
hostnames, and IP addresses out of a snapshot starts with the source
documents — the collector's own guarantee is only what `scrub()` does to
free text: URLs masked, control characters dropped, length capped.
`scrub()` does not classify prompts; it neither recognizes nor removes
prompt text. The usage section aggregates numbers only; it never copies
ledger rows.

## Tests

```bash
python3 -m pytest tests/test_obs_snapshot.py -q
python3 -m pytest tests/test_obs_fleet_wiring.py -q
python3 -m unittest discover -s observability/tests
```

The fixture state under `tests/fixtures/observability-state/` is synthetic.
The fixture-driven suite replaces a static example document: `observability/examples/` ships no snapshot example, and these fixtures exercise every section of the contract instead.

## Not in scope here

The Orbit dashboard view and any write path remain planned work (see
`observability/README.md` and `ROADMAP.md`). This collector only assembles and
serves the contract document. Alert delivery exists in one bounded form: the
decision-queue notifier below.

---

# rizzstack-decision-notifier

A durable, stdlib-only notifier over the written in-repo decision-queue
contract: the feature-queue statuses in
[`docs/22-autonomy-architecture.md` section 5](../../docs/22-autonomy-architecture.md),
the backlog section shape in
[`observability/schemas/snapshot.schema.json`](../../observability/schemas/snapshot.schema.json),
and the `queue.json` normalization of the collector above. It reads either a
`queue.json` directly or an already-assembled `rizzstack.observability/snapshot/1`
document, and any divergence from the written contract is reported as drift in
its status document instead of being silently folded in.

## Severity design (anti-fatigue)

Only owner-needed items notify. Per the contract reading, the owner-needed
pending kinds are exactly:

- `needs_approval` — waits on a **decision**;
- `blocked` — waits on a **blocker**.

Both are severity-high: they get one chat delivery plus one desktop
notification. Every routine status (`queued`, `claimed`, `running`,
`ready_for_review`) is dashboard-only: it lands in the status document's
dashboard block and nothing is pushed. `failed` is excluded from notification:
it is a verify outcome, not an owner request. The pending-kind set is one line
(`PENDING_KINDS`) in `decision_notifier.py`; a config override that diverges
from it is honored and reported as `contract_divergence` drift, so the
wf#43/#44 review can flip it in one place with the divergence on record.

## Durability: the delivery marker

One status document — `status.json` in the status directory — is the persisted
delivery marker. On every pass:

- **dedupe by item id** (`feature_id/kind`): a pending item is notified once,
  not once per pass;
- **aging escalation** (config data, default `escalate_after_s` 14400 s — the
  `alert.thresholds/v1` `blocker_age_s` default): an item still pending after
  the configured age is escalated again, with the escalation round and the
  first-seen time in the message;
- **degrade-to-marker**: when chat delivery fails (or no chat webhook is
  configured yet), the item stays in the marker with a generic error code and
  is retried on every later pass until it is delivered — never silent loss.
  Delivery is at-least-once: a crash between delivery and the marker write may
  re-notify, it can never silently drop;
- resolved items (left the pending set, changed kind) are recorded with a
  reason and trimmed after `resolved_retention_s` (default 7 days).

The status document also carries the run result (`ok` / `degraded`), the
source status (`live` / `stale` / `unavailable`), the dashboard block (queue
counts plus routine rows), and the drift rows. It never carries the chat
endpoint or any credential material — only generic codes such as
`chat_delivery_failed`, `chat_not_configured`, `desktop_unavailable`. The
notifier writes nothing but its own `status.json`.

## Usage

```bash
# One pass over the plugin state's queue.json (status.json under
# ~/.local/state/rizzstack-decision-notifier by default):
python3 contrib/rizzstack-observability/decision_notifier.py \
    --state-dir ~/.hermes/plugin-state

# With a chat webhook from a 0600 file, printing the status document:
python3 contrib/rizzstack-observability/decision_notifier.py \
    --state-dir ~/.hermes/plugin-state \
    --chat-webhook-file ~/.config/rizzstack-obs/notifier.chat-webhook \
    --print

# Continuous: one pass every 300 s (what the systemd unit runs):
python3 contrib/rizzstack-observability/decision_notifier.py \
    --state-dir ~/.hermes/plugin-state --loop --interval-s 300

# Consume an assembled snapshot document instead of queue.json:
python3 contrib/rizzstack-observability/decision_notifier.py \
    --snapshot /tmp/snapshot.json --print
```

Flags:

| Flag | Meaning |
| --- | --- |
| `--state-dir DIR` | directory holding `queue.json` (same layout the collector reads) |
| `--snapshot PATH` | read an assembled snapshot document instead of `queue.json` |
| `--status-dir DIR` | directory for the `status.json` delivery marker (default `~/.local/state/rizzstack-decision-notifier`) |
| `--config FILE` | JSON config overrides: `escalate_after_s`, `stale_after_s`, `chat_timeout_s`, `chat_message_max_chars`, `resolved_retention_s`, `pending_kinds` |
| `--chat-webhook-file PATH` | file holding the chat webhook URL, mode 0600 |
| `--desktop-cmd NAME` | desktop notification command (default `notify-send`) |
| `--no-desktop` | disable desktop notifications |
| `--loop` / `--interval-s N` | one pass every N seconds instead of one pass |
| `--print` | print the status document to stdout |

Exit codes: 0 clean pass, 1 degraded pass (delivery failure, missing webhook
with owner-needed items, or unavailable source), 2 refusal (bad config or
arguments).

## Chat delivery and credentials

- The chat webhook is a Slack-compatible incoming webhook: the notifier POSTs
  `{"text": message}` to it. The message carries the kind, the feature id and
  the queue status — nothing else, and never an endpoint or credential.
- The webhook is read at runtime from `--chat-webhook-file`, then from the
  `RIZZSTACK_NOTIFIER_CHAT_WEBHOOK` environment variable. It is never inlined
  in source, never placed on a command line, never printed or logged, and
  never copied into `status.json`. Treat the webhook URL as a secret.
- Chat failures are one generic code (`chat_delivery_failed`); the HTTP
  response body and the exception text are dropped on the floor.
- Desktop notifications are best effort (`notify-send --app-name rizzstack`).
  A desktop failure is recorded but does not hold the item back: the chat
  delivery is what marks an item delivered.
- A pass with nothing owner-needed is silent: no chat, no desktop, exit 0.

## Installing as a systemd user service

```bash
install -d -m 0700 ~/.config/rizzstack-obs
install -m 0600 /dev/null ~/.config/rizzstack-obs/notifier.env
  then put one line in it assigning the chat webhook value to the
  RIZZSTACK_NOTIFIER_CHAT_WEBHOOK variable
install -d -m 0700 ~/.local/state/rizzstack-decision-notifier
install -m 0755 contrib/rizzstack-observability/decision_notifier.py \
    ~/.local/bin/decision_notifier.py
install -m 0644 contrib/rizzstack-observability/rizzstack-decision-notifier.service \
    ~/.config/systemd/user/rizzstack-decision-notifier.service
systemctl --user daemon-reload
systemctl --user enable --now rizzstack-decision-notifier
```

The unit runs the notifier in loop mode (one pass every 300 s), reads the
chat webhook from the environment file, and confines writes to the status
directory via `ProtectHome=read-only` plus `ReadWritePaths`. Check the
delivery marker any time with
`python3 -m json.tool ~/.local/state/rizzstack-decision-notifier/status.json`.

## Tests

```bash
python3 -m pytest tests/test_decision_notifier.py -q
```

The suite pins the contract reading (queue vocabulary, pending kinds, backlog
shape against the written schema), proves owner-needed-only delivery, dedupe,
aging escalation, degrade-to-marker plus catch-up, silence, and runs an
end-to-end smoke over real HTTP chat delivery to a loopback server — including
the no-endpoint-leakage class over `status.json` and stderr.
