# 22 — Autonomy architecture

**Status (November 13, 2026):** The smallest coordinator that can carry an authorized goal to a verified
result. Revised after review: the verification/integration seam, crash-safe side effects, authorization
provenance, the real wake-up path, the minimum recovery inside the slice, and tick granularity are now
specified rather than assumed.

**Audience:** the coordinator and anyone implementing the loop.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) ·
[23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md).

---

## 1. Reconcile against durable state; wake an agent deliberately

Two separate mechanisms. Conflating them is the main design error to avoid:

- **Reconciliation is mechanical.** It compares durable intent (files on disk) with durable reality (the
  launcher journal, git) and performs the transitions that need no judgement.
- **Waking an agent is a distinct, explicit step**, taken only when a transition requires reasoning:
  decomposition, failure diagnosis, authoring a superseding contract.

The launcher offers no callback, webhook or push — `hyvv` exposes `GET /v1/attempts`,
`/v1/attempts/{id}` and `/v1/attempts/{id}/events?cursor`, nothing else. So the reconciler polls, and a
poll result is never a truth claim: it only says *go look at attempt X*. Polling the launcher is not the
same thing as resuming an agent, and §9 specifies the second separately.

## 2. Authority: two files, and the job may only narrow

An HMAC proves a file was written by whoever holds the key. The coordinator holds the key, so an HMAC over
a job document proves integrity, not human consent. Authority is therefore a separate object:

**`authorizations/<job_id>.json`** — the only source of authority. Written by `bundlebees job authorize`,
which:

- refuses to run without a TTY (a non-interactive process cannot create one);
- requires the human to type the statement of intent, stored verbatim;
- records repo, base rev, scope globs, bee budget, wall-clock budget and the gate list;
- is signed, so later edits are detectable.

**`jobs/<job_id>.json`** — the coordinator's working document. It **references** the authorization and may
only narrow it:

- every task lease must be a subset of `authorization.scope`;
- the task count may not exceed `budget.bees`; the deadline may not exceed `budget.wall_clock_s`;
- repo and base must match exactly.

Widening is a hard refusal (`authorization_widened`), not a warning.

**Gate outcomes** (`approvals/<job_id>.<gate>.json`) are created the same way — interactive, human-typed,
signed — and are the only thing that moves a job out of `awaiting_approval`.

**Stated plainly:** a coordinator with shell access could forge these files. What this buys is that
self-authorization is no longer accidental, and that forgery is a visible signed artifact in the audit
trail. It is not cryptographic proof of human identity, and this document does not claim one. Merges,
pushes, releases and deployments remain separately authorised acts, given directly and in the approver's
own words to whoever performs them.

## 3. Job document

`<state_dir>/jobs/<job_id>.json`, atomic write (tmp + fsync + rename), mode 0600, signed.

```json
{
  "job_id": "job_20261113_a",
  "authorization": {"ref": "authorizations/job_20261113_a.json", "sha256": "..."},
  "goal": {"summary": "...", "repo": "mojomast/workflow", "base_rev": "817eac4..."},
  "tasks": [
    {"task_id": "T1", "objective": "...", "lease": ["..."], "depends_on": [],
     "contract_path": "...", "contract_sha256": "...",
     "state": "pending", "attempts": [], "verify": null, "intent": null}
  ],
  "integration": {"wave": "w1", "state": "pending", "evidence": null},
  "approval_gate": {"required": true, "for": "merge", "state": "waiting"},
  "injected_failures": [],
  "events": []
}
```

Task states: `pending → dispatching → dispatched → running → verifying → verified → integrating →
accepted`, with `rejected`, `failed` and `superseded` reachable and always carrying a reason.

## 4. Tick granularity (the rule the tests assert)

One tick performs:

- **unlimited pure state updates** — refresh attempt state, append events, recompute readiness;
- **a bounded batch of dispatches** — every ready task whose dependencies are accepted, capped by the
  remaining bee budget;
- **at most one heavy operation** — one verification run *or* one integration run, never both, never two.

This is not aesthetics. Dispatch is cheap and independently idempotent per task (each carries its own
intent and lease); verification and integration are expensive, mutate a worktree and are order-sensitive.
Serialising those two removes a class of interleaving bugs without slowing the common case, because
dispatching three tasks still happens in a single tick.

It resolves the earlier contradiction: a fresh tick on a planned job dispatches **all ready tasks** and
performs **no verify and no integrate**. Both halves are acceptance criteria, not commentary.

## 5. Crash-safe side effects

State-machine guards run *before* an action; a crash happens *during* one. Every external action is
therefore written down twice — an intent before, a confirmation after.

**Intent record** — `<state_dir>/jobs/<job_id>/intents/<task_id>-<n>.json`, fsynced before the call:

```json
{"task_id": "T1", "attempt_no": 1, "client_request_id": "uuid5(job_id, task_id, attempt_no)",
 "state": "dispatching", "base_rev": "...", "lease_sha256": "...", "written_at": "..."}
```

**Dispatch protocol**

1. Take the single-writer lock (§6).
2. Write the intent with `state: dispatching`.
3. Create the lease (HMAC over attempt id, files, base rev).
4. `POST /v1/attempts`.
5. Write the confirmation (`state: dispatched`, `attempt_id`) and update the task.

**Adoption after a crash.** On the next tick, an intent still in `dispatching` is reconciled against the
launcher journal instead of re-POSTed:

- the launcher journals each attempt's brief (`a["brief"]`, including `objective`, `source_rev` and
  `assigned_files`), so candidates are attempts whose objective, source rev and assigned files match the
  intent and whose `created_at >= intent.written_at`;
- exactly one candidate → adopt it, write the confirmation, emit `attempt_adopted`;
- zero candidates → re-dispatch; the previous call never landed;
- two or more → **stop and escalate** (`dispatch_ambiguous`). Never guess which attempt is yours.

**Verify and integrate** use the same shape: intent first, result recorded after. A crash before the
verify commit leaves no branch; a crash after leaves a branch whose name embeds the attempt id, so the next
tick finds and adopts it rather than re-running the suite.

**Idempotency key.** `client_request_id = uuid5(job_id, task_id, attempt_no)` is carried in the intent and
the lease metadata. It is not sent to the launcher today — the brief schema is strict and there is no
reason to change hyvv for this — so the adoption rule above is what makes a lost response recoverable.

## 6. Single writer

`<state_dir>/jobs/<job_id>.lock`, taken with `O_CREAT|O_EXCL`, holding `{pid, host, started_at,
heartbeat_at}`. A tick that cannot take the lock exits 0 without acting. A lock is stale only when its pid
is gone **and** its heartbeat is older than two tick intervals; the taking tick writes a `lock_stolen`
event before proceeding, so a steal is always visible. Cron overlap, a manual `job tick` and a retried
agent turn can therefore never double-dispatch.

## 7. Verification: commit locally, never push

The seam that was broken: `verify --dry-run` applies and tests without committing and records `sha: null`,
while `integrate_wave` requires a real commit that is an ancestor of HEAD. The autonomous path uses
**isolated local commits**:

`bundlebees verify <attempt> --commit-local`:

1. `git worktree add --detach <tmp> <base_rev>` — a fresh checkout of the pinned base, never the user's
   working tree;
2. re-check the lease inside that worktree, then `git apply --check` followed by `git apply`;
3. run the declared tests, the regression suite and gitleaks;
4. on success **only**: `git commit` on a local throwaway branch `bb-verify/<attempt_id>`, recording
   `{commit_sha, base_rev, tree_sha, patch_sha256, tests, gitleaks}`;
5. prove the recording is honest: `git diff --stat <base_rev>..<commit_sha>` must equal the patch's file
   list, and `git merge-base --is-ancestor <base_rev> <commit_sha>` must hold;
6. remove the worktree. The branch stays local and is never pushed.

On failure there is no commit and the record says so. `integrate_wave` is unchanged: it now receives the
ancestor commit it always required, and keeps its guarantee that every attempt is verified and the full
suite is green before a wave is accepted.

Pushing remains an explicit, separately authorised act. No code path in the loop pushes.

## 8. Integration and bounded recovery

`integrate_wave` is reused as-is. Recovery is classified and bounded:

| Class | Detected by | Bounded action |
|---|---|---|
| `implementation` | the task's own tests fail on its patch | re-dispatch the same contract, attempts +1 |
| `interaction` | tests pass individually, fail combined | re-dispatch once with an added regression test in the lease, re-integrate once |
| `specification` | the contract names a test or field that does not exist at the base | freeze a superseding contract (`supersedes`, `supersedes_sha256`), re-dispatch once |
| `environment` | missing tool, disk, permissions | stop and report, no dispatch |
| `infrastructure` | launcher or Orbit unreachable | no dispatch, retry the tick with backoff |

Hard stops: `max_attempts_per_task` (3), two integration attempts per wave, `budget.bees`,
`budget.wall_clock_s`. Exhausting any of them produces `awaiting_approval` with a concrete question —
never a success.

## 9. Wake-up: exactly what runs

Two Hermes cron entries. Both are adapters, removable, and absent from the protocol:

**Entry 1 — mechanical, every 60 s.** Runs `bundlebees job tick --json`: pure reconciliation per §4. When a
transition needs judgement it writes `jobs/<job_id>/needs-agent.json` and exits 0:

```json
{"job_id": "...", "task_id": "T2", "kind": "diagnose_verify_failure", "created_at": "...",
 "prompt": "Job job_… task T2 failed verification (class: specification). Record your decision with: bundlebees job note --job … --task T2 --note '<finding>'."}
```

**Entry 2 — reasoning, every 60 s.** Runs `bundlebees job agent-pending --print-prompt`. Empty output →
exit immediately; this is the common case and costs nothing. Non-empty → **an agent turn** with that
prompt: the agent reasons, records its decision through the CLI, and exits. The prompt file is removed when
consumed, so a missed wake-up is retried on the next tick rather than lost.

That is the whole wake-up mechanism: a file, a command, and an agent turn. Adapters are Hermes cron (above),
a bare terminal (a human reads `job agent-pending`), and anything else that can run a command. Nothing in
the job format, the state machine or the event contract mentions Hermes.

**A missed event is not a lost job.** The tick is stateless and recomputes from disk, which is precisely
why polling is acceptable here and why a webhook would be an optimisation rather than a requirement.

## 10. Event record

Events are plain JSON, appended to the job document and mirrored to `jobs/<job_id>/events.jsonl` for
tailing:

```json
{"job_id": "...", "task_id": "T1", "attempt_id": "att_...", "kind": "attempt.terminal",
 "state": "succeeded", "at": "...", "cursor": 412,
 "artifact": {"result_path": "...", "sha256": "..."},
 "provenance": {"source": "hyvv.journal", "launcher_version": "0.1.16", "observed_at": "..."}}
```

An event never implies correctness. It says *look at attempt X*; the artifact is fetched and verified
separately, always.

## 11. Persistence

| What | Where | Survives crash | Signed |
|---|---|---|---|
| Authorization | `authorizations/<job_id>.json` | yes | yes |
| Job (tasks, gates, events) | `jobs/<job_id>.json` | yes | yes |
| Dispatch/verify intents | `jobs/<job_id>/intents/*.json` | yes | no (reconciled) |
| Leases | `leases/<attempt_id>.json` | yes | HMAC |
| Attempt truth | launcher journal on disk | yes | external |
| Verify records | `jobs/<job_id>/verify/<attempt_id>.json` | yes | no |
| Wave records | `jobs/<job_id>/waves/<wave>.json` | yes | no |
| Approvals | `approvals/<job_id>.<gate>.json` | yes | yes |

On restart the reconciler re-reads all of it, adopts in-flight attempts per §5 and continues. It never
re-dispatches an attempt whose lease exists and whose launcher state is non-terminal, and never accepts a
patch without a lease.

## 12. Human authority

Authorized once at `job authorize`: the goal, repo and base, file scope, bee budget, wall-clock budget and
which gates exist. Inside that envelope the loop acts without asking.

Still requiring a direct human act every time: merge, push, release, deploy, restart, spending beyond the
budget, widening the scope, and resolving any gate. Silence is not consent; a relayed approval is not
approval; the reconciler writes `awaiting_approval` and then does nothing at all.

## 13. What this deliberately does not add

No broker, no database, no new service, no plugin rewrite, no scheduler beyond two cron entries. The
reconciler is a module plus a CLI verb; state is JSON in the existing state dir; the verbs are the ones
that already ship.
