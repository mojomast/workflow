# 23 — Autonomy development plan

**Status (November 13, 2026):** Milestones that close the loop, each with a frozen acceptance contract. Written after auditing `workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820` and `orbitdesktop@eddc502`.

**Audience:** the coordinator and whoever assigns the bee work.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) · [23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md). Read them in that order.

---

Principle: the smallest slice that closes the loop. Every milestone is independently verifiable and
ships behind tests; nothing here replaces a working component.

## The critical path

Three missing things, in order of what unblocks the next: **(1) a durable job object**, **(2) a
reconciler that performs one transition per tick**, **(3) wiring the existing `verify`/`integrate` verbs
to state transitions**. Push notifications, planners and dashboards can all wait.

## Milestones

### M0 — merge the typed artifact consumer (prerequisite, already built)
- **Repo/location:** `bundlebees_plugin/client.py` — draft PR #15, branch `feat/oa3-client-artifact`.
- **Why:** the loop must read artifacts through product code, not the coordinator's rig.
- **Acceptance:** 15 artifact tests + 68 client/security tests green; real-route check against
  orbitdesktop `eddc502`.
- **Cost:** zero new work; it needs a merge decision, not engineering.

### M1 — job state module
- **Repo/location:** `bundlebees_plugin/job.py` (new), `bundlebees_plugin/schemas/job.schema.json` (new).
- **Reuse:** `leases.py::_ensure_key`, `_sign`, atomic-write pattern; `contract.py` for contract hashes.
- **New behaviour:** create/load/save a signed job document; append events; enforce the state machine and
  dependency rules; refuse a lease outside `authorization.scope`.
- **Security:** signed with the existing lease key; 0600; atomic rename; no secrets in the document.
- **Acceptance contract:** AC-001 round-trip preserves every field and the HMAC verifies; AC-002 a
  hand-edited field is refused (`job_tampered`); AC-003 an illegal transition raises (`job_bad_transition`);
  AC-004 a task whose dependency is not `accepted` cannot be dispatched; AC-005 a lease outside the
  authorized scope is refused (`lease_out_of_scope`).
- **Tests:** `tests/test_job.py` (six cases incl. tamper and dependency).
- **Complexity:** S. **Order:** 1.

### M2 — the reconciler
- **Repo/location:** `bundlebees_plugin/reconcile.py` (new).
- **Reuse:** `tools.py::_dispatch` and `_record_dispatch`; `harness`-style injectable clients so tests
  never touch a launcher or git; `adapters.py` result contract.
- **New behaviour:** `reconcile(job, deps) -> transition` performing exactly one of refresh / reap /
  verify / dispatch / integrate / escalate, per the architecture doc.
- **Security:** never trusts worker claims; verification goes through `bundlebees verify --dry-run`.
- **Acceptance contract:** AC-001 a terminal `succeeded` attempt moves its task to `verifying`;
  AC-002 a `failed` attempt sets `rejected` with a failure class and does not advance the wave;
  AC-003 a tick with an unchanged world performs no transition (idempotency); AC-004 dispatch happens
  only for `pending` tasks with satisfied dependencies and remaining budget; AC-005 a second tick after a
  simulated crash repeats no dispatch (lease present).
- **Tests:** `tests/test_reconcile.py` with a fake launcher journal and fake verify runner.
- **Complexity:** M. **Order:** 2 (depends on M1).

### M3 — CLI and the wake-up
- **Repo/location:** `bundlebees_plugin/cli.py` (`job start|tick|status|report`) + a Hermes cron entry
  every minute while a job is active.
- **Reuse:** the existing subcommand style; `cronjob_manage` for scheduling.
- **New behaviour:** `job tick` runs one reconcile; `job status` prints state + next action;
  `job report` writes the acceptance artifact.
- **Acceptance contract:** AC-001 `job tick` on a fresh job dispatches every ready task exactly once;
  AC-002 a tick on a completed job is a no-op; AC-003 `job status` lists each task's state and the next
  transition; AC-004 the cron entry stops firing when no job is active.
- **Complexity:** S. **Order:** 3.

### M4 — bounded recovery
- **Repo/location:** `bundlebees_plugin/reconcile.py` (+ `acdd_cli.py` superseding-contract path).
- **New behaviour:** classify failures (implementation / interaction / specification / environment /
  infrastructure); enforce `max_attempts_per_task` and two integration attempts; for `specification`,
  freeze a superseding contract and re-dispatch once, recording `supersedes`.
- **Acceptance contract:** AC-001 a patch that fails its own acceptance tests is rejected and
  re-dispatched at most `max_attempts_per_task` times; AC-002 an interaction failure re-integrates once
  with an added regression test; AC-003 a superseding contract records `supersedes` and `supersedes_sha256`;
  AC-004 exhausting the budget yields `awaiting_approval`, never a success.
- **Complexity:** M. **Order:** 4.

### M5 — approval gate and acceptance artifact
- **Repo/location:** `bundlebees_plugin/job.py`, `cli.py job report`.
- **New behaviour:** write `jobs/<id>.report.{md,json}` with per-task evidence, integration record,
  measurements and the exact human decision required; refuse to merge or push anything.
- **Acceptance contract:** AC-001 the report contains one row per task with verify evidence and sha;
  AC-002 the job stops at `awaiting_approval` and further ticks perform no action; AC-003 a refusal path
  records the reason and closes the job.
- **Complexity:** S. **Order:** 5.

## Explicitly deferred

- Push/webhook events from hyvv (the reconciler makes them an optimisation, not a requirement).
- A planner that decomposes goals automatically — v1 decomposes a goal into tasks **once**, at
  `job start`, with a human reviewing the task list as part of the single authorization. Automatic
  re-planning is a later, separate decision.
- Dashboards, alerting, cost accounting (no pricing feed exists; cost stays UNKNOWN).
- Multi-repo jobs. v1 is one repository per job.

## Bee assignment strategy for building this

The coordinator writes M1–M3 itself only where wiring is inseparable; the modules are well suited to
bees with disjoint leases:
- Bee A: `job.py` + `schemas/job.schema.json` + `tests/test_job.py`.
- Bee B: `reconcile.py` + `tests/test_reconcile.py` (depends on A's schema; dispatch after A is accepted).
- Bee C: `tests/test_reconcile.py` fixtures + `cli.py` wiring? No — wiring stays coordinator-owned, as in
  Experiment B. Bee C can own the report writer + its tests.

## Estimated shape

M1–M3 is the smallest slice that can run the dogfood end to end: roughly three bee-sized modules plus one
cron entry, no new service, no schema churn outside `bundlebees`. M4–M5 are needed before the loop can be
called *autonomous under failure*, and M5 is what makes the result reviewable without a human assembling
a summary by hand.
