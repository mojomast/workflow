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
| `fleet` | `hermes bundlebees attempt op=attempts` and `op=status` (read-only CLI calls) | Live attempt states normalized to the lifecycle-aligned state vocabulary; unrecognized labels are carried as `unknown` with the raw label in `detail`. |
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
- The CLI calls it makes are read-only (`op=attempts`, `op=status`,
  `gh pr list`, `gh pr checks`). It never calls a mutating bundlebees or `gh`
  verb.
- The collector holds no credential of its own: the fleet and CI sections use
  whatever ambient authentication those CLIs already have. It does not read,
  write, or move keys.
- `tests/test_obs_snapshot.py::TestReadOnly` proves no file in the state tree
  changes across snapshots.

## Privacy

Records keep the observability package's rules: repository fields are
`owner/name` slugs, free text is scrubbed (control characters dropped, URLs
masked, length capped), and escalation prompts, patches, transcripts,
credentials, hostnames, and IP addresses never enter a snapshot. The usage
section aggregates numbers only; it never copies ledger rows.

## Tests

```bash
python3 -m pytest tests/test_obs_snapshot.py -q
python3 -m unittest discover -s observability/tests
```

The fixture state under `tests/fixtures/observability-state/` is synthetic.

## Not in scope here

Alert delivery, the Orbit dashboard view, and any write path remain planned
work (see `observability/README.md` and `ROADMAP.md`). This collector only
assembles and serves the contract document.
