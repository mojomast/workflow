# 23 — Autonomy development plan

**Status (November 13, 2026):** The critical-path plan, revised after review. Bounded recovery and the
final report are now **inside** the slice rather than behind it, the verification seam is defined as local
commits, and the crash/wake-up tests are named acceptance criteria rather than intentions.

**Audience:** the coordinator and whoever assigns the bee work.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) ·
[23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md).

---

Principle: the smallest slice that can run an authorized objective end to end **including one recoverable
failure and a final report**. If the slice stops at "patches verified", the dogfood cannot demonstrate
autonomy — it would need a human to handle the injected failure and write the summary, which is the thing
being tested.

## The critical path

1. A durable job object, narrowing a human authorization.
2. A reconciler that dispatches, reaps and verifies — crash-safe at every external call.
3. The wake-up: a mechanical tick, plus a real agent turn when reasoning is required.
4. Bounded recovery: classify, retry once, supersede the contract when the spec was wrong.
5. The report and the approval gate.

## Milestones

### M0 — typed artifact consumer (done)
- **Repo/location:** `bundlebees_plugin/client.py` — merged. PR #15, head `d7b06f3`, merge commit
  `f4ce9ef2ede695a0cd0bdbb00e803c726a9de399` on `main`.
- **Why it mattered:** the loop must read artifacts through product code, not the coordinator's rig.
- **What the merge required beyond the feature:** the PR's own gate was fail-open. `ci.yml` installed
  hand-maintained dependency lists that had drifted from `pyproject.toml` (the test job was missing
  `jsonschema`; the Orbit job was missing nearly everything), and the Hermes Plugin Doctor job passed
  green while printing `Plugin registration failed: No module named 'jsonschema'` and registering zero
  tools. Both are fixed: the jobs derive their requirements from `pyproject.toml`, the doctor's declared
  runtime dependencies are installed into the Hermes environment it actually uses, and the doctor step now
  asserts its output (no `ERROR`, exactly 4 tools) instead of trusting an exit code that is always 0.
- **Evidence:** 576 passed / 3 skipped; Orbit round trip 36 passed; gitleaks clean; doctor 4 tools + 1
  hook. Negative case proven with the real binary: an unsatisfiable declared dependency produces the
  `ERROR` line and 0 tools, and the gate exits 1.

### M1 — job state and authorization
- **Repo/location:** `bundlebees_plugin/job.py` (new), `bundlebees_plugin/schemas/job.schema.json` (new).
- **Lease:** `bundlebees_plugin/job.py`, `bundlebees_plugin/schemas/job.schema.json`,
  `tests/test_job.py`.
- **Reuse:** `leases.py::_ensure_key`, `_sign`, `_lease_matches`; the atomic-write pattern; `contract.py`
  hashes.
- **New behaviour:** signed job documents; authorization objects that can only be narrowed; the task state
  machine; event append; refusal codes `job_tampered`, `job_bad_transition`, `authorization_widened`,
  `lease_out_of_scope`.
- **Acceptance contract:**
  - AC-001 a job round-trips with every field intact and its HMAC verifying;
  - AC-002 a hand-edited field is refused (`job_tampered`);
  - AC-003 an illegal transition is refused (`job_bad_transition`);
  - AC-004 a task whose dependency is not `accepted` cannot be dispatched;
  - AC-005 a lease outside `authorization.scope` is refused (`lease_out_of_scope`);
  - AC-006 a job whose scope, budget or base exceeds its authorization is refused
    (`authorization_widened`), including when the authorization file is missing;
  - AC-007 `job authorize` refuses to run without a TTY.
- **Tests:** `tests/test_job.py`.
- **Complexity:** M. **Order:** 1.

### M2 — the reconciler, crash-safe
- **Repo/location:** `bundlebees_plugin/reconcile.py` (new).
- **Lease:** `bundlebees_plugin/reconcile.py`, `tests/test_reconcile.py`,
  `tests/test_reconcile_crash.py`.
- **Reuse:** `tools.py::_dispatch` / `_record_dispatch`; injectable launcher client so tests never touch a
  live host; `leases.py` for signing.
- **New behaviour:** `tick(job) -> transitions[]` implementing §4 granularity (unbounded pure updates, batch
  dispatch, one heavy op); intent → call → confirm at every external step; adoption of in-flight attempts;
  the single-writer lock.
- **Acceptance contract:**
  - AC-001 **granularity:** a fresh tick on a planned three-task job creates three attempts, three leases
    and three confirmations, and performs no verify and no integrate;
  - AC-002 **duplicate dispatch:** two ticks started concurrently produce exactly one attempt per task (the
    second exits on the lock);
  - AC-003 **crash between dispatch and persistence:** an intent left in `dispatching` with a matching
    journal attempt is adopted, and no second POST is issued;
  - AC-004 **crash before the call:** an intent with no matching journal attempt is re-dispatched exactly
    once;
  - AC-005 **ambiguity:** two matching candidates → `dispatch_ambiguous`, no dispatch, job escalates;
  - AC-006 **failed verification:** a patch whose named test fails is `rejected` with a class, no commit
    exists, and the wave does not advance;
  - AC-007 **idempotency:** a tick over an unchanged world emits zero transitions.
- **Tests:** `tests/test_reconcile.py` (granularity, failure classification, idempotency),
  `tests/test_reconcile_crash.py` (kill points before/after the POST, lock contention, ambiguity).
- **Complexity:** L. **Order:** 2 (depends on M1).

### M3 — verification by local commit, and the wake-up
- **Repo/location:** `bundlebees_plugin/cli.py` (`verify --commit-local`, `job tick|status|note|report`,
  `job agent-pending`), `bundlebees_plugin/verify_local.py` (new) for the worktree/commit logic.
- **Lease:** `bundlebees_plugin/verify_local.py`, `tests/test_verify_local.py`; `cli.py` coordinator-owned.
- **Reuse:** the existing `verify` flow for patch application and test running; `git worktree`; gitleaks.
- **New behaviour:** isolated worktree at the pinned base, local commit on `bb-verify/<attempt_id>`, no
  push, tree/diff equality proof, worktree cleanup, and the `needs-agent.json` handoff.
- **Acceptance contract:**
  - AC-001 a good patch yields a real commit whose parent is `base_rev`, `merge-base --is-ancestor` holds,
    and `git diff --stat base..HEAD` equals the patch's file list;
  - AC-002 nothing is pushed: `git ls-remote` on the worktree's remote shows no `bb-verify/*` ref, and the
    command performs no network call in tests;
  - AC-003 a failing patch produces no commit and a `rejected` record;
  - AC-004 the user's working tree is untouched (verified by comparing status before/after);
  - AC-005 `job tick` writes `needs-agent.json` only when a reasoning transition is pending, and
    `job agent-pending --print-prompt` returns that exact prompt once and empty afterwards;
  - AC-006 a cron-shaped invocation (`job tick --json`) run twice produces one transition per new fact, and
    exits 0 with no output when nothing is pending.
- **Tests:** `tests/test_verify_local.py`, `tests/test_wakeup.py` (the second invokes the CLI as a
  subprocess, exactly as cron would).
- **Complexity:** M. **Order:** 3 (depends on M2).

### M4 — bounded recovery
- **Repo/location:** `bundlebees_plugin/reconcile.py` (`classify_failure`, `plan_recovery`),
  `bundlebees_plugin/acdd_cli.py` (supersede).
- **Lease:** `bundlebees_plugin/reconcile.py` (second pass), `tests/test_recovery.py`.
- **New behaviour:** the five failure classes; `max_attempts_per_task`; one interaction re-integrate; one
  specification supersede (`supersedes`, `supersedes_sha256`); escalation on exhaustion.
- **Acceptance contract:**
  - AC-001 a patch failing its own tests is re-dispatched at most `max_attempts_per_task` times, then
    escalates;
  - AC-002 an interaction failure re-integrates once with an added regression test in the lease, and a
    second failure escalates;
  - AC-003 a contract naming a non-existent test is classified `specification`, superseded once, and the
    corrected patch is accepted;
  - AC-004 `environment` and `infrastructure` never dispatch;
  - AC-005 exhausting any budget yields `awaiting_approval`, never `done`.
- **Tests:** `tests/test_recovery.py`.
- **Complexity:** M. **Order:** 4 (depends on M3).

### M5 — report and approval gate
- **Repo/location:** `bundlebees_plugin/job.py` (report writer), `cli.py job report|approve`.
- **Lease:** `bundlebees_plugin/report.py` (new), `tests/test_report.py`.
- **New behaviour:** `jobs/<id>.report.{md,json}` with per-task evidence, integration record, measurements
  (UNKNOWN where unmeasured), and the exact decision required; `approve`/`refuse` written only from a TTY.
- **Acceptance contract:**
  - AC-001 one row per task with verify evidence, commit sha and lease;
  - AC-002 the job stops at `awaiting_approval` and further ticks perform no action;
  - AC-003 `job approve` without a TTY is refused; with a TTY it writes a signed approval;
  - AC-004 the report never claims a merge, push or deploy happened;
  - AC-005 unmeasured values print `UNKNOWN`, never zero or a guess.
- **Tests:** `tests/test_report.py`.
- **Complexity:** S. **Order:** 5 (depends on M4).

## Integration test matrix (required before the dogfood)

| Test | What it proves |
|---|---|
| duplicate dispatch | two concurrent ticks → one attempt per task |
| crash between dispatch and persistence | intent + journal adoption, no second POST |
| failed verification | no commit, classified rejection, wave blocked |
| local-only committed integration | `integrate_wave` receives a real ancestor commit; no ref is pushed |
| real wake-up without a human | `job tick` via subprocess writes `needs-agent.json`; a second subprocess consumes the prompt and records a decision through the CLI |
| end-to-end two-task run against a fake launcher | dispatch → reap → verify → integrate → report, zero manual steps |

The first five are the reviewer's list; the sixth is what makes the dogfood a confirmation rather than a
first attempt.

## Ordering and dependencies

`M1 → M2 → M3 → M4 → M5`, strictly. M2's crash handling depends on M1's intents; M3's local commits are
what M4's integration reuses; M5 reports on evidence M4 produces. Bee-assignable work is M1, M3's
`verify_local.py`, M4 and M5's `report.py`; the reconciler (M2) and `cli.py` wiring stay coordinator-owned
because they encode the ordering rules this whole plan exists to get right.

## Explicitly deferred

- Launcher push/webhook events (the reconciler makes them an optimisation).
- Automatic re-planning: v1 decomposes once at `job start`, reviewed as part of the single authorization.
- Multi-repo jobs; dashboards; alerting; cost accounting (no pricing feed — cost stays UNKNOWN).
- Parallel verification: one heavy operation per tick is deliberate, not a limitation to remove yet.
