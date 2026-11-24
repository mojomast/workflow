# 22 — Autonomy architecture

**Status (November 14, 2026):** the architecture as built, not as planned. Bundlebees `875025b` carries
the job store, reconciler, local verification, integration, bounded recovery, RETURN generation and the
agent wake-up; hyvv `5bee1a8` carries governed provisioning; workflow `070b6c1` carries the normative
contracts. Where a guarantee is only proven inside the deterministic harness, this chapter says so.

**Audience:** the coordinator and anyone implementing or replacing a part of the loop.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) ·
[23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md).

---

## 1. Four layers, one direction of dependency

```
workflow        normative protocol, schemas, validators      no state, no execution
   |
   v
bundlebees      durable jobs, queue, reconcile, verify,      owns authority, evidence
   |            integrate, recovery, RETURN, wake-up
   |
   v
hyvv            governed provisioning + attempts API          owns its host filesystem
   |
   v
adapters        worker backends and decision adapters         replaceable, never authoritative
```

The dependency points down. A layer never imports the one above it, and the durable records never encode
a harness type. Two mechanical checks enforce the important half of that claim:

- `bundlebees_plugin/adapters.py` is the only place an agent, model or launcher is named, and
  `tests/test_adapters.py` fails if a core module names one.
- `packets.py`, `recovery.py` and `return_report.py` load their validators from a pinned workflow
  checkout (`WORKFLOW_SRC`) instead of re-implementing them; a missing or unreadable checkout fails
  closed (`recovery_protocol_unavailable`, packet refusal) rather than falling back to a local guess.

## 2. The normative layer

The workflow repository defines what a job *is*; bundlebees decides what happened. Four versioned shapes
matter to the loop:

| Protocol | Shape | Enforced by |
|---|---|---|
| `acdd/1` | contract: acceptance criteria, approved tests, assigned files, frozen hash | `contract.py`, `tdd.py`, required workflow CI |
| `rizzstack.feature-packet/1` | the queued feature: request, repository, pinned `workflow_ref`, source policy, frozen contract (exact) or template + dependency + `policy_id` (descendant), scope, budget, evidence, gates | `packets.py` loading `tools/feature_packet.py` |
| `rizzstack.source-resolution/1` | the immutable record that binds a descendant packet digest to the dependency's accepted commit and the source-bound frozen contract | `handoff.py`, `packets.py` |
| `rizzstack.return/1` | the machine-readable result: packet digest, contract, per-criterion status and evidence, RED/GREEN, verification, integration, transport, attempts, recovery, limitations, unrun, pending approvals | `return_report.py` loading `tools/return_manifest.py` |
| `rizzstack.recovery/1` | request (mechanical) and decision (reasoned, mechanically validated) for one classified failure | `recovery.py` loading `tools/recovery.py` |

Chapters 25–27 describe these protocols. They live on the workflow `feat/feature-packet` branch (PR #33)
and are pinned by commit in bundlebees CI, so the runtime is running a fixed protocol revision even while
the PR is open.

**A packet is evidence and identity, never authority.** Editing one authorises nothing. The only authority
is the sealed authorization (or an enrolled policy) that the packet names.

## 3. Authority: separate documents, narrowing only

An HMAC proves a file was written by whoever holds the key. The coordinator holds the key, so an HMAC over
a job proves integrity, not human consent. Authority is therefore a separate object written through an
interactive path:

**`authorizations/<job_id>.json`** — written by `hermes bundlebees job authorize`, which refuses without a
TTY, requires the human to type the statement of intent (stored verbatim), and records repo, base revision,
scope globs, bee budget, wall-clock budget and the gate list. A recovery ceiling — attempts, contract
corrections, exact replacement selectors, file scope, test scope and the gates that stay in force — can be
sealed into the same signed body by the authoring path that supplies it (standing-grant derivation and the
descendant handoff do this); the bare `job authorize` CLI verb does not yet expose recovery flags, so a
hand-written authorization defaults to the empty ceiling.

**`jobs/<job_id>.json`** — the coordinator's working document. It references the authorization and may only
narrow it:

- every task lease must be a subset of `authorization.scope`;
- the task count may not exceed `budget.bees`; the deadline may not exceed `budget.wall_clock_s`;
- job and task `recovery_policy` blocks may restate the sealed recovery ceiling only to narrow it (`min`
  for attempts and corrections, intersection for selectors and scopes, union for gates);
- repo and base must match exactly.

Widening is a hard refusal (`authorization_widened`, and `_recheck_authority` refuses a widened recovery
request at admission and again at apply), not a warning. An authorization with **no** recovery block grants
one attempt, zero corrections and no replacement selectors — the empty ceiling, not a permissive default.

**Standing grants** (`rizzstack.standing-grant/1`, `grants.py`) let a human enroll one bounded envelope for
repeated work. Derivation is budget-reserved atomically with `O_EXCL` per-grant reservation files, so two
concurrent jobs cannot spend the same remaining units. Enrollment and revocation are TTY-only.

**Descendant policies** (`handoff.py`) are sealed with a separate approval key that ordinary job sealing
never uses. The coordinator can verify an enrollment but cannot mint one. That is file-level separation
inside one state directory, not OS-principal isolation.

**Stated plainly:** a coordinator with shell access could forge these files. What this buys is that
self-authorization is no longer accidental and that forgery is a signed artifact in the audit trail. Merges,
pushes, releases, deploys and final acceptance remain separately authorised human acts.

## 4. Job document and state machine

`<state_dir>/jobs/<job_id>.json`, atomic write (tmp + fsync + rename), mode 0600, signed.

```json
{
  "job_id": "job_20261113_a",
  "authorization": {"ref": "authorizations/job_20261113_a.json", "sha256": "..."},
  "goal": {"summary": "...", "repo": "mojomast/workflow", "base_rev": "..."},
  "tasks": [
    {"task_id": "T1", "objective": "...", "lease": ["..."], "depends_on": [],
     "contract_path": "...", "contract_sha256": "...",
     "state": "pending", "attempts": [], "verify": null, "intent": null}
  ],
  "integration": {"wave": "w1", "state": "pending", "evidence": null},
  "recovery_policy": {},
  "approval_gate": {"required": true, "for": "merge", "state": "waiting"},
  "injected_failures": [],
  "escalations": [],
  "events": []
}
```

Task states: `pending → dispatching → dispatched → running → verifying → verified → integrating →
accepted`, with `rejected`, `failed` and `superseded` reachable and always carrying a reason. Saving a job
refuses to drop or rewind accepted evidence.

## 5. The feature queue

`queue.py` is a thin durable pointer layer, not a second job store:

- `queue.json` (or the Hermes kanban backend) holds `feature_id → job_id`, status and dependency.
- Statuses: `queued`, `claimed`, `running`, `ready_for_review`, `blocked`, `failed`, `needs_approval`.
- A claim is written under a lock before work starts; a **Kanban status is never evidence that work
  completed**. Completion is derived from the job document being accepted.
- `job queue run --once` does one deterministic pass: advance every active claim first, then admit at
  most one new feature. `--once` is required; there is no daemon or cron installed by this repository.

The A→B factory uses the queue's production handoff: when A's job is accepted, the queue resolves B's
descendant packet against A's accepted commit, writes the source-resolution record, provisions B at that
revision through the mirror, and admits B. `_handoff_dependents` is a no-op unless a handoff context is
configured.

## 6. Tick granularity

One `reconcile.tick` performs:

- **unlimited pure state updates** — refresh attempt state, append events, recompute readiness;
- **a bounded batch of dispatches** — every ready task whose dependencies are accepted, capped by the
  remaining bee budget;
- **at most one heavy operation** — one verification run *or* one integration run, never both and never
  two.

Dispatch is cheap and idempotent per task; verification and integration are expensive, mutate a worktree
and are order-sensitive. Serialising those two removes a class of interleaving bugs without slowing the
common case: dispatching three tasks still happens in a single tick.

The tick returns a `TickResult` with a status: `ok`, `idle`, `locked`, `reconcile_wait`,
`awaiting_decision` or `escalated`, plus the transitions that were applied. A fresh tick on a planned job
dispatches all ready tasks and performs no verify and no integrate; both halves are asserted in tests.

## 7. Single writer and crash-safe side effects

The job lock is a kernel `flock` on `<state_dir>/jobs/<job_id>.lock` (O_CREAT|O_RDWR|O_NOFOLLOW, 0600),
with an `O_EXCL` fallback on non-POSIX. A tick that cannot take it returns `locked` and acts on nothing.
Age is never grounds to steal a lock from a live holder; on the fallback path a dead pid plus a stale
timestamp makes the steal visible as a `lock_stolen` event.

State-machine guards run *before* an action; a crash happens *during* one. Every external action is
therefore written twice — an intent before, a confirmation after.

**Intent record** — `jobs/<job_id>/intents/<task_id>-<n>.json`, fsynced before the call:

```json
{"task_id": "T1", "attempt_no": 1, "client_request_id": "uuid5(job_id, task_id, attempt_no)",
 "state": "dispatching", "base_rev": "...", "lease_sha256": "...", "written_at": "..."}
```

**Dispatch protocol**

1. Take the job lock (§7).
2. Write the intent with `state: dispatching`.
3. Create the lease (HMAC over attempt id, files, base rev).
4. `POST /v1/attempts`.
5. Write the confirmation (`state: dispatched`, `attempt_id`) and update the task.

**Adoption after a crash.** The launcher journals each attempt's brief, including `objective`,
`source_rev` and `assigned_files`. A next tick finds an intent still in `dispatching` and reconciles it
against that journal:

- one strict match → adopt it, write the confirmation, emit `attempt_adopted`;
- no match, and the request provably never left the process (`DispatchNotSent`) → re-dispatch;
- an unknown outcome (`DispatchUncertain`) → wait out a grace period measured in elapsed seconds, then
  escalate; never guess;
- two or more matches → **stop and escalate** (`dispatch_ambiguous`).

The `client_request_id` is carried in the intent and the lease metadata. Hyvv does not enforce it server
side, so the coordinator never claims `exactly_once`; adoption is what makes a lost response recoverable.

**Verify and integrate** use the same shape: intent first, result recorded after. A crash before the verify
commit leaves no branch; a crash after leaves `bb-verify/<attempt_id>`, which the next tick adopts after
re-proving it rather than re-running the suite. Accepted waves publish through a fsynced temp plus
create-only `link`, so a restart reconciles the accepted wave instead of integrating twice.

`faults.py` names the checkpoints (`tick.after_dispatch`, `wave.after_persist`,
`transport.after_publish`, queue ack boundaries) where a test may kill the process. A checkpoint is inert
unless a hook is registered in that process; a restarted process cannot re-trigger a fault, and no shipped
configuration can arm one.

## 8. Verification: commit locally, never push

`hermes bundlebees verify <attempt> --commit-local` runs `verify_local.verify_and_commit`:

1. `git worktree add --detach <tmp> <base_rev>` — a fresh checkout of the pinned base, never the caller's
   working tree;
2. re-check the lease inside that worktree; refuse anything the lease does not authorise;
3. prove the named tests are RED before the patch and GREEN after it;
4. apply the patch; the resulting file set must equal the lease;
5. run the declared tests, the regression suite and gitleaks;
6. on success **only**: `git commit` on a local branch `bb-verify/<attempt_id>`, recording
   `{commit_sha, base_rev, tree_sha, patch_sha256, tests, gitleaks}`;
7. prove the recording is honest: `git diff --stat <base_rev>..<commit_sha>` equals the patch's file set,
   and `git merge-base --is-ancestor <base_rev> <commit_sha>` holds;
8. remove the worktree. The branch stays local and is never pushed.

On failure there is no commit and the record says so. A restart is idempotent: an accepted record is
reused, and a commit whose record was lost is adopted only after re-proof.

Worker code runs in a disposable copy without `.git` under bubblewrap (all namespaces unshared,
unprivileged uid, only `/usr` and the Python install mounted) or firejail; `unshare` is never selected
automatically. With no strong backend, verify fails closed (`sandbox_unavailable`) unless the explicitly
unsafe `verify_allow_unsafe_local` is set.

## 9. Integration

`integrate_job.materialize` builds one integration worktree at the pinned base and **merges** each
verified commit (`--no-ff`). The sibling verification commits become ancestors of the integrated HEAD
without rewriting them, so their identities stay exactly as verified. Only then is `revision.integrate_wave`
called, with the ancestry, verify-record and full-suite checks it has always enforced. A conflict is
`integration_conflict`, never forced. An accepted wave is published behind a durable ref
`refs/bb/integrated/<job>`; `job recover --repo` restores it after a crash.

## 10. Bounded recovery

A rejection is not a retry licence. `recovery.py` writes a durable **request** before the rejection is
committed, derived from recorded evidence and normalised onto the protocol's five classes:

| Class | Meaning | Legal decisions |
|---|---|---|
| `implementation` | the patch did not satisfy the approved tests | retry within budget, escalate |
| `specification` | the acceptance selection itself is unusable | supersede once, escalate |
| `environment` | the host lacked a tool, dependency or route | escalate only |
| `infrastructure` | launcher, scheduler or storage failed | escalate only |
| `integration` | verified patches did not combine | bounded repair, escalate |

A **decision** is a separate document, adapter-supplied and mechanically validated against the request and
the sealed envelope: contract identity, class rules, attempts used, the exact corrected-test subset, and a
rationale. `job recover` records a decision; it never applies it. The next `job tick` applies it exactly
once through `apply_ready_decisions`, freezing one superseding contract (`supersedes` +
`supersedes_sha256`, original packet byte-identical) and permitting exactly one corrective dispatch.

Hard stops: the envelope's attempt and correction counts (v1 caps them at 5 and 1), the wave's integration
attempts, `budget.bees` and `budget.wall_clock_s`. Exhausting any of them produces `needs_approval` /
`awaiting_approval` with a concrete question — never a success. Duplicate or conflicting decisions are
refused.

## 11. Wake-up: mechanical, then deliberate

Two mechanisms, deliberately separate:

**Mechanical, every tick.** `bundlebees job tick` performs §6. When it escalates, it writes
`jobs/<job_id>/needs-agent.json` with the reason, detail and a prompt, and exits 0. The file is fsynced and
atomically replaced.

**Reasoning, a separate process.** There are two consumers, both optional and both absent from the
protocol:

- `bundlebees job agent-pending --job-id …` claims the pending prompt (a lease with a timeout, not a
  tombstone) and prints it. The agent records its answer with `job note --job-id … --note '…'`, which
  appends the decision event once and marks the handoff done. A missed wake-up is re-claimed, not lost.
- For recovery decisions, `agent_work.py` publishes one durable `rizzstack.agent-work/1` item per request
  under `recovery/<job>/<task>.<n>.work.json`: states `pending → claimed → completed | refused`, a single
  active claim, TTL and dead-pid adoption, at most two claims, idempotent completion.
  `python -m bundlebees_plugin.agent_consumer --state DIR --consumer NAME
  [--adapter hermes|deterministic|authorized] [--once|--interval N]` claims one item and either adopts an
  already-persisted proposal or invokes the configured adapter. The mechanical tick never calls inference;
  no corrective bee is dispatched until a validated decision exists.

The work item names a request, its digest and an optional adapter hint. It never carries a prompt, argv,
transcript or instruction for a particular agent — those belong to the adapter's own records. That is why
replacing Hermes is a configuration change, not a protocol change.

## 12. RETURN and acceptance

`job report` builds `jobs/<job>/return.json` (`rizzstack.return/1`) and `jobs/<job>/RETURN.md` from durable
records, re-proving the relationships before writing a byte: the intent packet is re-hashed against the
digest sealed into the job; a descendant's source resolution must validate against that packet and its
accepted commit; every accepted wave must have matching head, attempts and a zero suite; every claimed
verified attempt must have a verification record whose commit exists (when `--repo` is supplied); a
publication claim needs a transport receipt.

Acceptance is classified strictly from evidence: `PASS` needs a verification record with `suite.exit_code
== 0` covering the criterion's tests, or a validating signed `tdd-evidence/1` GREEN. `FAIL`, `NOT RUN`,
`BLOCKED` and `UNVERIFIED` are distinct. A task or job state of `accepted` is never evidence by itself.
`receiver_decision` is always `{status: "pending", decided_by: null, decided_at: null, note: null}`; the
generator refuses to emit a filled decision. `job report --verify` rebuilds the manifest from durable state
and compares `evidence_digest` without writing; drift is `report_tampered`.

## 13. Provisioning (the hyvv layer)

The coordinator never touches a worker filesystem. `provisioning.py` speaks `rizzstack.provisioning/1`:

- `GET /v1/provision/capabilities` — required; a backend that does not advertise, or advertises another
  schema, is incompatible. There is no legacy fallback.
- `POST /v1/provision/project` — declarative request: repo, full `source_rev`, profile, job id, project
  name, idempotency key.
- `GET /v1/provision/receipts/<key>` — read-only receipt lookup.
- `POST /v1/provision/cleanup` — bounded deletion under the enrolled root.

Authorisation comes from the host's enrolled `provisioning-policy.json`, never the request. The workspace
is derived from the profile root plus a validated name; reparse points are refused; the only child process
is `git` with a fixed argument vector; credentials stay on the host. A receipt carries `status=ready`,
repo, resolved revision, project, profile, host and verification of detached HEAD/clean tree. The
coordinator validates it against the authorization and binds the job to its digest; `Binding.validate()`
re-checks the receipt and frozen contract immediately before dispatch. 5xx is `ProvisionUncertain`
(reconcile, never re-POST); 409 is a conflict. `provision_bind.py` runs this as a phase of the ordinary job
tick — one job, one missing project, one provisioning operation, then normal dispatch.

## 14. Adapters and harness independence

Two seams, both outside the protocol:

| Seam | Interface | Implementations |
|---|---|---|
| Worker backend | `create(brief)`, `result(attempt_id)` | `orbit-loopback` (default; the launcher path through which Pi and OpenCode workers are reached today), `launcher`; `opencode` and `codex` are documented stubs that refuse with `unsupported_adapter` |
| Decision adapter | produce one strict proposal for a recovery request; the protocol validator still decides | `hermes`, `deterministic`, test-only `authorized` |

`normalize_result` reduces any worker reply to a patch, a declared base, usage and worker-claimed checks;
everything else is dropped. The Hermes adapter builds a read-only package (request, frozen contract,
verifier record, envelope, candidates, pinned source excerpts, exact question), persists raw stdout and its
sha256 before parsing, accepts exactly one proposal object, compiles the canonical decision mechanically,
and records it only after `validate_pair` passes. `adopt_proposal` re-hashes, reparses, recompiles and
re-validates a persisted proposal without asking the model again.

## 15. Persistence

| What | Where | Survives crash | Integrity |
|---|---|---|---|
| Authorization (and sealed recovery ceiling) | `authorizations/<job_id>.json` | yes | HMAC |
| Job (tasks, gates, events) | `jobs/<job_id>.json` | yes | HMAC |
| Feature queue | `queue.json` + `queue/<feature_id>.json` | yes | derived |
| Intent packet | `packets/<job_id>.json` | yes | digest sealed in job |
| Source resolution | `resolutions/<job_id>.json` | yes | digest |
| Dispatch/verify intents | `jobs/<job_id>/intents/*.json` | yes | reconciled |
| Leases | `leases/<attempt_id>.json` | yes | HMAC |
| Attempt truth | launcher journal on disk | yes | external |
| Verify records | `verify-results/<attempt_id>.json` | yes | evidence |
| Wave records | `waves/<wave>.json` | yes | evidence |
| Recovery request/decision | `recovery/<job_id>/<task>.<n>.request.json` / `.decision.json` | yes | digest |
| Agent work item | `recovery/<job_id>/<task>.<n>.work.json` | yes | digest |
| RETURN | `jobs/<job_id>/return.json`, `RETURN.md` | yes | `evidence_digest` |
| Approvals | `approvals/<job_id>.<gate>.json` | yes | HMAC |

On restart the reconciler re-reads all of it, adopts in-flight attempts per §7 and continues. It never
re-dispatches an attempt whose lease exists and whose launcher state is non-terminal, and never accepts a
patch without a lease.

## 16. Human authority

Authorized once at `job authorize` (or by deriving a job inside an enrolled grant): the goal, repo and
base, file scope, bee budget, wall-clock budget and which gates exist — plus the recovery ceiling when the
authoring path seals one. Inside that envelope the loop acts without asking.

Still requiring a direct human act every time: merge, push, release, deploy, restart, spending beyond the
budget, widening the scope, enrolling or revoking a grant or policy, and resolving any gate. Silence is not
consent; a relayed approval is not approval; the reconciler writes `awaiting_approval` and then does
nothing at all.

## 17. What this deliberately does not add

No broker, no database, no new service, no second scheduler, no plugin rewrite. The reconciler is a module
plus a CLI verb; the queue is a JSON pointer file or the existing kanban; state is JSON in the existing
state dir; the verbs are the ones that already ship. Cron entries, when installed, are adapters that run
`job tick` and `job queue run --once`; they are not part of the protocol and nothing in the job format,
state machine or event contract mentions Hermes.
