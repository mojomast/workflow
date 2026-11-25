# Rails R00 — source/attachment feasibility

Status: R00 slice S deliverable (spec section 9, packet R00/S). Governing spec: `specs/rizzstack-rails-spec.md`
(read at the working head that carries it; its own source pins are re-verified below per the section 2
recheck-at-admission rule). Companion fixture: `schemas/rails/fixtures/source-matrix.json` (machine-readable
pins, sanitized native trace, session shape, hook citations with line digests). Test: `tests/test_rails_feasibility.py`.

Every hook citation below was taken from a fresh checkout of the named repository at its exact pinned
revision, and each citation carries a SHA-256 line digest in the matrix so a reviewer can re-verify it
independently. No hook is guessed: where the pinned evidence does not settle a question, the verdict below
says so explicitly (Q2 is unresolved for exactly that reason).

## 1. Source pins

| Repo | Pinned revision | Version at pin | Verified | Method |
|---|---|---|---|---|
| workflow | `9f6aa6dc7a74890ef2284d7aa4432efc9b6a4169` | commit-pinned (spec §2) | 2026-11-17 | clone of origin checked out at the exact commit; this working tree (base `c31de3b`) carries the same cited files |
| bundlebees | `b2db04b8c8463cef5cbf25a64dcaf2130edd142e` | 0.1.1 (`pyproject.toml`) | 2026-11-17 | fresh clone at the exact commit; anchors verified line-by-line |
| hyvv | `316bd975e212973837daeefc271a491471ea882c` | 0.1.17 (`launcher.py` VERSION) | 2026-11-17 | fresh clone at the exact commit; anchors verified line-by-line |
| orbitdesktop | `8530a14be7ce480ef35dd11890e72de4c89bed09` | 0.3.1 (`package.json`) | 2026-11-17 | fresh clone at the exact commit; anchors verified line-by-line |
| vibeline | `d5d0f425a64906ae1a50c1222314a5420da404d5` | 0.2.0 (`plugin.yaml`) | 2026-11-17 | fresh clone whose head equals the pin; anchors verified line-by-line |

All five pins from spec §2 exist on their origins and were re-checked at admission. Two repo-rule anchors
that bind this work: `docs/06-rules-and-lessons.md:15` (workflow) forbids committing credential material or
private hosts, and `AGENTS.md:9` (orbitdesktop) requires real browser validation and bundle parity when
served code changes — binding for R17D.

## 2. Hook locations

### 2.1 Proxy / auth attachment (orbitdesktop) — consumed by R16, R17

The deployed `/obs-snapshot` proxy **does not exist in the pinned tree**: a tree-wide search for
`obs-snapshot` at the pin returns zero files (recorded as an absence check in the matrix). What the pinned
tree actually serves:

- Static catalog apps are served from `apps/<slug>` by `workspaceService.serveApp`
  (`server/workspace.mjs:192`, path rooting enforced at `server/workspace.mjs:197`), dispatched at
  `server/index.mjs:359` under `/apps/`. This is the serving layer Observatory uses today; the
  Observatory app fetches its snapshot document by configured URL with an operator-entered credential
  held only in that app's local storage (`apps/rizzstack-observatory/app.js:6-10` header comment).
- Every owner JSON API passes one shared boundary: the credential is read from the request's credential
  header only (`server/technology-owner-route.mjs:9`), and the route refuses anything that fails the
  host/origin gate or the constant-time credential match with `permission_denied`
  (`server/technology-owner-route.mjs:10`; the same boundary guards workbench dispatch routes at
  `server/workbench-owner-route.mjs:11`). The comparison helper is timing-safe and length-bounded
  (`server/security.mjs:4-8`).
- The server itself: owner credential from configuration or generated at boot and never logged
  (`server/index.mjs:59`), the generated one persisted only to a private runtime file with owner-only
  mode via atomic rename (`server/index.mjs:100`), unexpected Host refused before routing
  (`server/index.mjs:322`), owner routes registered by exact path (`server/index.mjs:326`), and an
  existing same-shaped evidence route wired through an explicit authorize callback
  (`server/index.mjs:144`, dispatched at `server/index.mjs:372`).

Safe extension seam for R16/R17: register `/api/rizzstack/rails/*` as a new owner-route module following
the `technologyOwnerRoute` pattern and add its dispatch line to `server/index.mjs` (exact-path
registration, `server/index.mjs:325-340` region). GET routes stay read-only behind the owner boundary;
mutations require the existing owner principal; the catalog pane stays read-only unless owner mutation
capability is proven (spec §7 default: trusted shell dialog mediation).

### 2.2 Queue / fencing (bundlebees) — consumed by R15

The existing `queue.py` is a feature queue: "intake, durable claim, and one-pass consumption" over the job
store, with kanban status explicitly never treated as completion evidence (`bundlebees_plugin/queue.py:1`),
lifecycle states at `bundlebees_plugin/queue.py:29`, the mutation seam `QueueAdapter.set_status` at
`bundlebees_plugin/queue.py:95`, and a file-backed implementation for hosts without a Kanban bridge at
`bundlebees_plugin/queue.py:99`. The coordinator scheduler keeps a durable claim queue
(`bundlebees_plugin/work_scheduler.py:3`) with claim serialization at
`bundlebees_plugin/work_scheduler.py:614` and durable atomic replaces at
`bundlebees_plugin/work_scheduler.py:303`. Two existing facts the rails plan can build on: the launcher
adapter already records that no server-enforced idempotency exists yet
(`bundlebees_plugin/launcher_adapter.py:58`), and `reconcile.py` already derives a stable idempotency key
from job, task and attempt (`bundlebees_plugin/reconcile.py:1297`); intervention records already exist in
the append-only outcome log (`bundlebees_plugin/metrics.py:38`). A case-insensitive search for
fencing across the plugin package returns zero matches (absence check in the matrix).

### 2.3 Native worker stream (hyvv) — consumed by R08, R09

The deployed stream is per-attempt and append-only: events are appended to
`attempts/<attempt_id>.events.jsonl` (`launcher.py:1474`), read incrementally through an offset-indexed
`events_since(aid, cursor)` (`launcher.py:1462`, `launcher.py:1482`). Record shape: launcher state records
carry `lseq`, `ts`, `kind: "state"`, `state`, `detail` (`launcher.py:1631`); heartbeat records carry
`idle_s` (`launcher.py:1718`); upstream worker events pass through with the kind prefixed `worker:` and
launcher-assigned `lseq`/`ts` (`launcher.py:1713`), paged 200 at a time from the worker runtime
(`launcher.py:1068`); upstream kinds observed are `turn_started`, `message`, `turn_ended`, `error`,
`exited` (`launcher.py:1282-1298` for the agy backend; the opencode backend passes its runtime kinds
through at `launcher.py:1069-1071`). The launcher redacts credential-shaped content before storage
(`launcher.py:174`). The existing transport is authenticated on every request with a constant-time
credential check (`launcher.py:2200`) and already exposes the events export route whose response carries
`events`, `state`, `cursor` (`launcher.py:2273`) plus the authenticated landing export
(`launcher.py:2253`). Terminal receipts are durable CloudEvents (`launcher.py:181`, built at
`launcher.py:339`) with crash replay at startup (`launcher.py:1615`) and durable integer export positions
in the landing export index (`landing_export.py:9`, `landing_export.py:159`, entrypoint at
`landing_export.py:462`).

Finding: the native stream has **no tool-level start or finish records**. Tool pairing cannot be sourced
from the launcher log; tool-call granularity exists only in the Hermes message stream
(`vibeline/sessions.py:119`). R08 must not fabricate tool pairs (spec §5 already forbids it).

### 2.4 Hermes session read contract (vibeline) — consumed by R07

The session database is the Hermes home `state.db` (`vibeline/sessions.py:23`) opened strictly read-only
via URI mode (`vibeline/sessions.py:27`). The read path consumes: `sessions` rows keyed by `id` with
`parent_session_id` linking subagents (`vibeline/sessions.py:237`; parents exclude `source='subagent'`,
`vibeline/sessions.py:221`), `messages` columns `id, role, content, tool_call_id, tool_calls, tool_name,
timestamp, display_kind` plus an optional `active` flag (`vibeline/sessions.py:227`), tool results paired
to calls by equal `tool_call_id` within the session (`vibeline/sessions.py:119`) with calls parsed from
the `tool_calls` JSON (`vibeline/sessions.py:61`), ghosting driven by the active flag
(`vibeline/sessions.py:126`) which is version-dependent — older installs lack the column and the reader
falls back (`vibeline/sessions.py:216-218`) — and a change-detection version vector
(`vibeline/sessions.py:38`). The full column-level descriptor is the matrix's `session_shape` block. Upstream
tests already build this exact schema in memory (`vibeline/tests/test_features.py:24`), and upstream
declares a Hermes version floor (`vibeline/plugin.yaml:7`).

Upstream hooks that rails must **replace**, not reuse (spec §2 adaptation column): `ledger.py` opens a
writable connection despite read-only intent (`vibeline/ledger.py:40`), falls back to a bundled example
database (`vibeline/ledger.py:15`), and treats expected-red as a prose prefix (`vibeline/ledger.py:72`);
`web.py` loads the whole ledger unbounded (`vibeline/web.py:113`), trusts loopback callers without any
credential (`vibeline/web.py:286`), and accepts the credential from the query string
(`vibeline/web.py:292`); its mutation routes (`/api/spawn`, `/api/rewind`, `/api/feedback`) must not be
registered (`vibeline/web.py:315`). The legacy chain algorithm itself is stable and must be matched
exactly: `_CHAIN_KEYS` (`vibeline/ledger.py:75`), canonical bytes
(`vibeline/ledger.py:90`), hash = SHA-256 of previous hash plus canonical bytes (`vibeline/ledger.py:91`).

## 3. Uncertainties

**Q1 verdict: resolved** — the deployed `/obs-snapshot` proxy is absent from the pinned orbitdesktop tree
(absence check: zero matches). The actual serving layer at the pin is `workspaceService.serveApp` for
static catalog apps under `/apps/` (`server/workspace.mjs:192`, dispatched `server/index.mjs:359`) plus
the shared owner-route boundary for all owner JSON APIs
(`server/technology-owner-route.mjs:9-10`, `server/workbench-owner-route.mjs:11`, host gate at
`server/index.mjs:322`). Evidence citations: matrix Q1 block (five citations, digests included). The safe
extension seam for `/api/rizzstack/rails/*` is a new owner-route module registered by exact path in
`server/index.mjs` (pattern: `server/index.mjs:326`, precedent `server/index.mjs:144`/`372`). Residual
(stated, not settled here): the deployed host's own router/reverse-proxy configuration is deployment-side
and outside every repo; recheck it at R17 admission before production registration.

**Q2 verdict: unresolved** — the fenced action-queue interface the spec requires (stable committed
operation identity, idempotency/reconciliation semantics, authority revalidation, replayable transition
history) does not exist in the pinned bundlebees tree, and the in-flight module the spec calls
user-reported is not in this tree either. Evidence: `queue.py` is a feature-queue pointer over the job
store with a plain status transition (`bundlebees_plugin/queue.py:1`, `95`), the work scheduler serializes
claims with a lock file and atomic replaces but defines no fencing epoch or operation identity
(`bundlebees_plugin/work_scheduler.py:614`, `303`), the launcher adapter explicitly records that no
server-enforced idempotency exists yet (`bundlebees_plugin/launcher_adapter.py:58`), and a
case-insensitive search for fencing across the plugin package returns zero matches. The reason this stays
unresolved: any operation-identity or fencing semantics attributed to the queue today would be a guess,
and review rejects guessed hooks. Downstream rule (already fixed by spec §7): until the real interface
exists, R15 implements `capability_unavailable` for mutations — read-only rails ships, mutation tasks are
blocked, and `queue.transition`/`lease` rails events record only what rails observes. What the evidence
does settle: `reconcile.py:1297` provides a stable key basis (job, task, attempt) reusable for rails
dedupe keys, and intervention records already land in the append-only outcome log
(`bundlebees_plugin/metrics.py:38`).

**Q3 verdict: resolved** — the deployed native stream is attempt-level with the exact shapes cited in
§2.3: state/heartbeat/`worker:<kind>` records over an append-only per-attempt JSONL, upstream kinds
`turn_started`, `message`, `turn_ended`, `error`, `exited`, no tool-level events, no rotation observed
(one append-only file per attempt; restarts replay terminal receipts, `launcher.py:1615`), and final
receipt identity carried by the durable bee-landed CloudEvent with crash replay
(`launcher.py:181`, `339`, `1615`) plus durable integer export positions (`landing_export.py:9`). The
sanitized native trace in the matrix mirrors this shape with synthetic records only. Downstream rule:
R08's launcher-log adapter emits attempt-level lane events with fixture-versioned parsers for
`worker:`-prefixed kinds, dedupes native and backfilled records on (attempt_id, lseq), and never
fabricates tool pairs or durations; tool-level timing comes from the Hermes-session source where present.
The existing authenticated transport (`launcher.py:2200`) and export route shape (`launcher.py:2273`) are
the D5 pull basis. Residual: upstream worker kinds may evolve — recheck the parser fixture at R08
admission per spec §2.

**Q4 verdict: resolved** — the read-side Hermes schema contract is fixed by the pinned vibeline read path
and its in-memory test fixtures: tables `sessions` (id, source, model, parent_session_id, started_at,
ended_at, end_reason, title, cwd, git_branch, api_call_count, tool_call_count, input_tokens,
output_tokens, cache_read_tokens, reasoning_tokens) and `messages` (id, session_id, role, content,
tool_call_id, tool_calls, tool_name, timestamp, display_kind, optional active), pairing by `tool_call_id`,
topology by `parent_session_id` with `source='subagent'`, and the active-flag fallback for older installs
(citations in §2.4 and the matrix `session_shape` block). Downstream rule: R07 builds its read-only
fixture from this descriptor, ingestion stays allowlisted per session (never default all-session ingest),
and missing tables or columns map to `unsupported_source_version` (spec §5). Residual: the installed
Hermes application is not one of the five pinned repos, so the live installed schema (including WAL
behavior) must be rechecked at R07 admission; this descriptor fixes the consumed contract, not the
application's own schema version.

## 4. Sanitization

No credential material appears in this deliverable. The matrix's `sanitization` block states the policy;
its native-trace records are synthetic (fabricated timestamps, neutral placeholder payloads, no real
attempt ids, run ids, hosts, paths, models or credentials), and the session-shape block is a schema-level
descriptor with no session content. Header and credential values are described as withheld wherever the
underlying code would carry one. The three leased files are checked by the package tests
(`FeasibilityDoc.test_doc_is_sanitized`, `test_matrix_is_sanitized`) against a structural
name-colon-value guard, and were additionally scanned with the coordinator's own gate pattern before each
commit (empty result required and obtained).

## 5. RED-first evidence

Package tests were committed first (`tests/test_rails_feasibility.py`, commit `73ed31c` "rails R00:
RED-first feasibility tests") while the fixture and doc were absent. RED run
(`python -m unittest discover -s tests -p test_rails_feasibility.py`): 15 tests, 3 failures and 12 errors —
every failure caused by the missing `schemas/rails/fixtures/source-matrix.json` (assertion: "missing
fixture") or the missing `specs/rails-feasibility.md` (empty doc text). After the matrix landed (before
this document), 2 failures and 2 errors remained, all doc-only. This revision is GREEN: 15/15 with
`RAILS_SOURCE_ROOTS` unset (structural tier + local workflow citations) and also under a configured
pinned-source root set (deep tier: every external citation anchor matched at its pinned line, and each
checkout's `git rev-parse HEAD` equals the matrix pin). Reviewer reproduction of the deep tier: check out
each repo at its pin, set `RAILS_SOURCE_ROOTS` to the JSON mapping described in the test docstring, run
the same unittest command.

## 6. Open items for downstream packages

- R01: complete the closed schemas and hash vectors; the draft envelope (`schemas/rails/event.schema.json:3`)
  and examples are already in tree. The workflow-side compatibility contract is pinned in §2.4.
- R07: build the Hermes fixture from the matrix `session_shape`; recheck the installed schema at admission.
- R08: launcher-log adapter per Q3's downstream rule; parser fixtures versioned.
- R15: queue stays `capability_unavailable` until Q2's real interface exists; reuse the reconcile key basis
  for dedupe.
- R16/R17: attach `/api/rizzstack/rails/*` per Q1's extension seam; recheck deployed router configuration
  and installed Hermes/worker versions at admission; browser validation per `AGENTS.md:9`.
