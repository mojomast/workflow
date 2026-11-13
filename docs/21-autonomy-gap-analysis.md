# 21 — Autonomy gap analysis

**Status (November 13, 2026):** Where the loop breaks today, read off the code rather than the READMEs. Written after auditing `workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820` and `orbitdesktop@eddc502`.

**Audience:** the coordinator, the approver, and anyone who wants to know what Rizzstack can actually do end to end.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) · [23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md). Read them in that order.

---

Scope: `workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820`, `orbitdesktop@eddc502`,
launcher 0.1.16 (verified live: `active 0`, `max_concurrent 10`). Every claim below cites code I read in
this audit; README claims are not treated as evidence.

## The thirteen transitions

| # | Transition | State | Where it lives today | What actually advances it |
|---|---|---|---|---|
| 1 | Goal intake and scope authorization | **MISSING** | — | A human writes a prompt. No artifact records the goal, its scope or its budget. |
| 2 | Task decomposition and dependency planning | **MISSING** | — | The agent decomposes in its head; nothing persists tasks or dependencies. |
| 3 | Contract generation, review, freeze | **IMPLEMENTED/UNPROVEN** | `bundlebees_plugin/acdd_cli.py` — `contract validate`, `contract freeze`; `contract.py`; `tdd.py` freeze-by-hash | CLI verbs typed by a human/agent. Freeze exists and binds a sha256; no automated producer of contracts. |
| 4 | Resource allocation, leases, dispatch | **PROVEN** | `tools.py::_dispatch`, `_dispatch_acdd`, `_record_dispatch`; `leases.py::record_lease` (HMAC over every field, `<state_dir>/leases/<attempt_id>.json`); `hyvv` `POST /v1/attempts` | Human/agent calls the `bundlebees_dispatch` tool. Proven in Experiments A and B (4 + 3 bees). |
| 5 | Worker completion notification | **MISSING (push)** / **PARTIAL (poll)** | `hyvv` exposes `GET /v1/attempts`, `GET /v1/attempts/{id}`, `GET /v1/attempts/{id}/events?cursor`; **no callback, webhook, SSE or push** (grepped: none) | Nothing. A human or the agent asks. |
| 6 | Coordinator wake-up and event processing | **PARTIAL (out of product)** | `~/.hermes/scripts/rizz-ci-watch.sh` + cron, written by the coordinator, not by any repo | A 30-minute cron that only watches PRs. Not a job processor, not in `bundlebees`. |
| 7 | Artifact retrieval and provenance | **IMPLEMENTED/UNPROVEN** | Orbit `server/local-worker-artifact.mjs` + `op=artifact` (merged #28); bundlebees consumes only via private `_op` — the typed client is **draft PR #15, not merged** | Human runs the call. Proven once by the coordinator's rig, not by product code on main. |
| 8 | Independent RED/GREEN verification | **IMPLEMENTED/UNPROVEN** | `cli.py` `verify` (apply patch, run named tests, commit+push unless `--dry-run`); `sandbox.py` (bwrap/firejail); `acdd_cli.py::verify_preflight`; `tdd.py` records | Human types `bundlebees verify <attempt>`. The coordinator's own verifications in A/B were manual procedures, not this CLI. |
| 9 | Integration of accepted patches | **IMPLEMENTED/UNPROVEN** | `cli.py` `integrate --wave --attempts`; `revision.py::integrate_wave` (requires each attempt's `ok` verify result with an ancestor sha; runs the full suite; accepts only on exit 0) | Human types the command. Never exercised end to end on real patches. |
| 10 | Conflict and regression detection | **PARTIAL** | `integrate_wave` collects per-attempt problems and runs the suite; `git apply` refuses conflicts | Exists as a command, but no classification of *why* integration failed beyond problems + suite exit. |
| 11 | Diagnosis, correction, bounded retry | **MISSING** | — | Nothing. No failure classification, no retry budget, no corrective brief generation, no superseding-contract flow (that was done by hand in Experiment B). |
| 12 | Durable state and interruption recovery | **PARTIAL** | Leases are durable and HMAC-verified; hyvv journals attempts and results on disk; Orbit has its own ledger | No job/task/attempt-graph state anywhere. Restart recovery = the human re-reads and re-asks. |
| 13 | Final acceptance report and approval handoff | **PARTIAL** | `acdd_cli.py tdd report` (acceptance report); `metrics.py` | A human assembles the summary in chat. No acceptance artifact tied to a job. |

## What exists but is invisible from the docs

- **Lease enforcement is real**: `leases.py::lease_files`, `_lease_matches`, `ignored_worker_claims` —
  a worker's claimed file list is discarded and the signed lease is authoritative.
- **Verification refuses to push to main**: `verify` refuses `main`/`master` branches explicitly.
- **Integration is fail-closed**: `integrate_wave` will not accept a wave unless every attempt has an
  `ok` verify result whose sha is an ancestor of HEAD, and the full suite exits 0.
- **The launcher is a durable journal**: every attempt, event and result is on disk; `active`/`queued`
  are derived from it. This is the only component that already behaves like a system of record.

## What is genuinely missing (the critical path)

1. **No goal/job object.** Nothing represents "this authorized objective, these tasks, these
   dependencies, this budget". Everything today is per-attempt.
2. **No coordinator loop.** No process anywhere asks "what is ready? what finished? what should happen
   next?" The Hermes agent does this when a human prompt wakes it; the cron does a different, narrow job.
3. **No transition wiring.** `verify` and `integrate` are verbs a human types. Nothing calls them when an
   attempt reaches a terminal state, so the chain from "bee finished" to "patch verified and integrated"
   is a human, not a system.

Those three are the autonomy gap. Everything else is either proven or a bounded extension of something
proven.

## Honest classification of the "autonomous" claim

Rizzstack today is **human-driven orchestration with automated components**. Parallelism is real (3 bees
concurrently, Experiments A/B), verification is real when invoked, and integration is fail-closed — but
every transition that matters is initiated by a person or by the agent acting on a person's prompt.
Calling it autonomous would be false.

## Secondary defects worth recording, not blocking

- **bundlebees #15 (typed artifact client) is unmerged** — the consumer path exists only as the
  coordinator's rig code. Any autonomous loop needs it on main.
- **Cold-start acceptance is red on main** (`CS-apply-tax … 0 signed records`). Per instruction this is
  not prioritised; it does not block the loop, but it means the repo's own acceptance demo cannot be
  used as the loop's proof.
- **The `verify` CLI pushes a branch** by default. For an autonomous loop that is a policy surface: the
  autonomous path must pass `--dry-run`; a push is an explicit, lease-authorised act.
