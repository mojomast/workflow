# 22 — Autonomy architecture

**Status (November 13, 2026):** The smallest coordinator that can carry an authorized goal to a verified result. Written after auditing `workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820` and `orbitdesktop@eddc502`.

**Audience:** the coordinator and anyone implementing the loop.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) · [23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md). Read them in that order.

---

Goal: one authorized objective in, one verified result out, with the human touched only at the approval
gate. Design constraint: extend what exists (launcher journal, leases, `bundlebees verify|integrate`,
`acdd` contract/TDD, cron) rather than adding a service.

## The core decision: reconcile, don't subscribe

The launcher already is a durable journal: every attempt has `state`, `events` with monotonic cursors,
`result` on disk, and `active`/`queued` derived from it. Orbit already mirrors it by polling
(`ORBIT_LOCAL_WORKERS_POLL_MS`, default 3000). No component offers a callback, and inventing one puts the
truth in a transient HTTP request.

**Therefore the coordinator is a reconciler, not a listener.** Each tick it compares durable intent
(the job file) with durable reality (launcher journal, git, repository) and performs the transitions
that are ready. Push notifications, if ever added, become an optimisation that wakes the reconciler
early — never the source of truth.

This also gives interruption recovery for free: a crashed coordinator loses nothing, because the next
tick recomputes from the journal.

## The job object

One JSON document per authorized objective, at `<state_dir>/jobs/<job_id>.json`, written atomically
(tmp + rename), mode 0600, and signed with the existing lease key so a hand-edited job is detectable.

```json
{
  "job_id": "job_20261113_a",
  "goal": {"summary": "...", "repo": "mojomast/workflow", "base_rev": "817eac4..."},
  "authorization": {"by": "kyle", "at": "...", "scope": ["tools/acdd-lint/**"],
                    "budget": {"bees": 6, "wall_clock_s": 7200, "max_attempts_per_task": 3}},
  "tasks": [
    {"task_id": "T1", "objective": "...", "lease": ["tools/acdd-lint/acdd_lint/checks_x.py"],
     "contract_path": "...", "contract_sha256": "...", "depends_on": [],
     "state": "pending|dispatched|running|verifying|verified|rejected|integrating|accepted|failed",
     "attempts": ["att_..."], "verify": {"ok": true, "evidence": "..."}}
  ],
  "integration": {"wave": "w1", "state": "pending|running|accepted|failed", "evidence": "..."},
  "approval_gate": {"required": true, "for": "merge", "state": "waiting|granted|refused"},
  "events": [{"at": "...", "transition": "T1 dispatched", "source": "tick|human"}]
}
```

Rules the object enforces:
- Tasks may only move forward along the state machine; every transition appends an event with a
  timestamp, the actor (`reconciler`, `worker`, `human`) and the evidence path.
- A task may not leave `pending` until every `depends_on` is `accepted`.
- `authorization.scope` is the only place file scope comes from; a task lease outside it is a hard
  refusal, not a warning.
- `budget.bees` and `max_attempts_per_task` are enforced by the reconciler before any dispatch.

## State machine (job level)

```
authorized ──plan──▶ planned ──dispatch(T1..Tn)──▶ running
   ▲                    │                            │
   │                    ▼                            ▼
   │              needs_approval ◀── integrate ◀── verifying ◀── all tasks verified
   │                    │                                          │
   └──── refused ───────┘                                          ▼
                                                           report_written
```

Job states: `authorized → planned → running → verifying → integrating → awaiting_approval → done`
with `failed` reachable from any state and carrying `failure_class`.

## The reconciler (the missing component)

One function, `reconcile(job) -> transition | None`, called by a cron tick (60 s while a job is active,
nothing when idle). Each call performs **exactly one** transition, in this order:

1. **Refresh** — read `GET /v1/attempts/{id}` for every dispatched attempt; append state changes.
2. **Reap** — for each attempt in a terminal state and task in `dispatched`/`running`:
   - `succeeded` → task `verifying`; queue a verify action.
   - `failed`/`cancelled` → task `rejected`; record `failure_class` from `observed.error`.
3. **Verify** — for a task in `verifying`, run `bundlebees verify <attempt> --dry-run` (apply and test without committing or
   pushing), capture the verify record, set `verified` or `rejected`.
4. **Dispatch** — for each `pending` task whose dependencies are all `accepted` and whose budget allows,
   call the same dispatch path the tool uses (`tools.py::_dispatch` + `leases.record_lease`).
5. **Integrate** — when every task is `verified`, run `bundlebees integrate --wave --attempts …`;
   `accepted` only if the command exits 0.
6. **Escalate** — when a task exceeds `max_attempts_per_task`, or integration fails twice, write a
   report and set `awaiting_approval` with a concrete question. Never loop forever.
7. **Report** — write `jobs/<id>.report.md` + `.json` (the acceptance artifact) and stop at the gate.

Idempotency: every action is guarded by the task state that must precede it, so re-running a tick after
a crash repeats nothing. Dispatch is additionally guarded by the lease file existing for that attempt id.

## Event contract (agent-agnostic)

An event is a plain JSON object, appended to the job's `events` array and mirrored to
`<state_dir>/jobs/<id>.events.jsonl` for tailing:

```json
{"job_id": "...", "task_id": "T1", "attempt_id": "att_...", "kind": "attempt.terminal",
 "state": "succeeded", "at": "...", "cursor": 412, "artifact": {"result_path": "...", "sha256": "..."},
 "provenance": {"source": "hyvv.journal", "launcher_version": "0.1.16", "observed_at": "..."}}
```

Producers: a reconciler tick (primary), hyvv journal read (authoritative), and in future a launcher
webhook. A Hermes tool adapter turns events into agent turns; a bare CLI adapter prints them. Neither is
required by the contract — the reconciler is.

**A notification never implies correctness.** The event only says "look at attempt X"; the artifact is
fetched and verified separately, always.

## Verification design

Reuse `bundlebees verify` rather than inventing a verifier, but change two defaults:
- `--dry-run` is the default in the autonomous path; a push requires an explicit lease field
  `may_push: true` and still ends at the approval gate.
- The verify record must include: patch sha256, base rev, per-AC test results, suite result, gitleaks
  result. Missing fields fail the task rather than passing it.

## Integration and bounded recovery

- Integration is the existing `integrate_wave`: all attempts verified, ancestor shas, full suite.
- On failure, classify into: `implementation` (a task's tests fail on its own patch), `interaction`
  (tests pass individually, fail combined), `specification` (the contract was wrong — Experiment B's W3
  case), `environment` (missing tool, disk, network), `infrastructure` (launcher/Orbit down).
- Recovery per class, bounded: `implementation` → re-dispatch the same contract (attempts +1);
  `interaction` → re-dispatch with an added regression test in the lease, then re-integrate once;
  `specification` → freeze a superseding contract (the B3b pattern) and re-dispatch, recording
  `supersedes`; `environment` → stop and report; `infrastructure` → back off and retry the tick, no
  dispatch.
- Hard stops: `max_attempts_per_task` (3), two integration attempts per wave, `budget.bees`,
  `budget.wall_clock_s`. On stop: report + `awaiting_approval`, never a silent success.

## Human authority

- The goal, its file scope, its bee budget and its wall-clock budget are authorized **once**, in the job
  file, by the human.
- Inside that envelope the reconciler acts without asking.
- Merge, release, deploy, restart, pushing to any branch not named in the authorization, spending above
  `budget.bees`, and any change to `authorization` itself require a direct human act.
- The reconciler writes `awaiting_approval` and **does nothing further** until a human grants or refuses.
  It must never interpret silence as consent, and never merge on a relayed approval.

## Persistence and interruption

Everything needed to resume is on disk and either signed or derived:
- job file (signed) — intent, scope, budget, task graph, approval state
- leases (HMAC) — what each worker was authorised to touch
- launcher journal — what actually happened
- verify records — what the coordinator proved
- wave record — what was integrated
A restarted reconciler re-reads these and continues. It never re-dispatches an attempt whose lease exists
and whose launcher state is non-terminal, and never accepts a patch whose lease is missing.

## What this deliberately does not add

No message broker, no database, no new daemon, no plugin rewrite. The reconciler is a function plus a
cron entry; the state is JSON in the existing state dir; the verbs are the ones that already shipped.
