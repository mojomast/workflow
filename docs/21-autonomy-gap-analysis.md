# 21 — Autonomy gap analysis

**Status (November 14, 2026):** the original audit, reconciled with what has since been delivered. The
first version was read off `workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820` and
`orbitdesktop@eddc502` on November 13. Since then bundlebees merged M1–M3.5 (#16–#19) and now stands at
`875025b` (merged as `a4d47e8`, `7a1480c`, `e25e00a`, `875025b`), and the workflow protocol grew the
feature packet, RETURN and recovery chapters on the #33 branch. This document keeps the audit, records what
closed, and states what is still open. README claims are still not treated as evidence.

**Audience:** the coordinator, the approver, and anyone who wants to know what Rizzstack can actually do
end to end.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) ·
[23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md). Read them in that order.

---

## 1. The four layers, as delivered

The system that exists today is four layers, not one autonomous program:

| Layer | Repository | Owns | Does not own |
|---|---|---|---|
| **Normative protocol** | `workflow` | `acdd/1` contracts, `rizzstack.feature-packet/1`, `rizzstack.source-resolution/1`, `rizzstack.return/1`, `rizzstack.recovery/1`; validators and required CI jobs | Execution, credentials, worker hosts |
| **Durable execution** | `bundlebees` | Job and authorization documents, feature queue, reconciler, local-only verification, integration, bounded recovery, RETURN generation, agent wake-up | What the protocol means; host filesystem |
| **Governed provisioning** | `hyvv` | Host-enrolled policy, workspace creation and registration, receipts, cleanup, the attempts API | Authority, leases, acceptance |
| **Agent/harness adapters** | `bundlebees_plugin/adapters.py`, `hermes_adapter.py`, `agent_consumer.py` | Worker backends (Orbit/launcher, through which Pi and OpenCode workers are reached today; `opencode`/`codex` are direct stubs) and decision adapters (Hermes, deterministic, test-only authorized) | The protocols, the durable state, the acceptance rules |

The layering is tested, not asserted: `tests/test_adapters.py` fails if a core module imports or names a
specific agent, model or launcher. Protocols load from a pinned checkout (`WORKFLOW_SRC`) and the pinned
provisioning contract (`HYVV_SRC`), so the durable state and the contracts are independent of which
harness happens to be running. Chapter [22](22-autonomy-architecture.md) describes each layer.

## 2. The thirteen transitions, re-checked

The original audit asked where a goal becomes a verified result. Columns: the state on November 13, the
mechanism that now exists, and its proof. “CI-proven” means a deterministic test in the mandatory suite;
“supervised” means a separately recorded real-model run, never CI.

| # | Transition | Nov 13 | Delivered mechanism | State on November 14 |
|---|---|---|---|---|
| 1 | Goal intake and scope authorization | **MISSING** | `job authorize` (TTY, human-typed statement, signed); standing grants for repeated derivation; `rizzstack.feature-packet/1` intake | **IMPLEMENTED, CI-proven** (M1, M3.5 phase 2). A packet is evidence, never authority. |
| 2 | Task decomposition and dependency planning | **MISSING** | A task list is supplied at `job create`; descendant packets carry exactly one dependency; the queue admits at most one new feature per pass | **PARTIAL.** v1 decomposes once at intake and never re-plans. One dependency per descendant feature. No multi-feature campaign. |
| 3 | Contract generation, review, freeze | **IMPLEMENTED/UNPROVEN** | `contract validate` / `contract freeze`; `tdd red` / `refactor` / `review` / `report`; exact packets must carry a frozen `acdd/1` contract and matching hash | **IMPLEMENTED, CI-proven.** Generation is still authored, not automated. |
| 4 | Resource allocation, leases, dispatch | **PROVEN** | Signed lease binder; reconciler intents; strict journal adoption; `DispatchNotSent` / `DispatchUncertain` split | **PROVEN** in CI against a fake launcher and real hyvv over HTTP; historically against real bees. |
| 5 | Worker completion notification | **MISSING (push)** | Still poll-only. The durable `needs-agent.json` / agent-work item is the coordinator's wake-up, not a launcher push | **PARTIAL by design.** Polling is acceptable because the tick recomputes from disk; a webhook would be an optimisation. |
| 6 | Coordinator wake-up and event processing | **PARTIAL (out of product)** | `job tick` (mechanical, one heavy op), `job agent-pending`, and a separate `agent_consumer` process with a durable `rizzstack.agent-work/1` claim protocol | **IMPLEMENTED, CI-proven** deterministic control (M4.3); supervised real-model wake-up recorded separately. |
| 7 | Artifact retrieval and provenance | **IMPLEMENTED/UNPROVEN** | `client.py::artifact()` typed consumer; mandatory real Orbit round-trip CI job | **PROVEN in CI** (real Orbit route, pinned commits). |
| 8 | Independent RED/GREEN verification | **IMPLEMENTED/UNPROVEN** | `verify --commit-local`: isolated worktree at the pinned base, lease check, RED before, GREEN after, suite, gitleaks, local `bb-verify/<attempt>` commit, no push | **IMPLEMENTED, CI-proven** (M3). The older user-run `verify` still commits and pushes a feature branch; the loop path does not push. |
| 9 | Integration of accepted patches | **IMPLEMENTED/UNPROVEN** | `integrate_job`: merge each verified commit into one integration worktree without rewriting it, then `integrate_wave` keeps its ancestry, verify-record and full-suite checks | **IMPLEMENTED, CI-proven.** |
| 10 | Conflict and regression detection | **PARTIAL** | Merge conflicts are `integration_conflict`; the combined suite must exit 0; wave records carry the evidence | **PARTIAL.** Detection is mechanical, not causal: no attribution of a regression beyond the failing suite. |
| 11 | Diagnosis, correction, bounded retry | **MISSING** | `rizzstack.recovery/1` request/decision pair; sealed recovery envelope; five failure classes; one supersession; `needs_approval` on exhaustion | **IMPLEMENTED, CI-proven** with a scripted decider; supervised real Hermes decision recorded separately (M4.2). |
| 12 | Durable state and interruption recovery | **PARTIAL** | Signed job store, intents before every external call, append-only attempt history, accepted-wave recovery, queue claim records, process-kill tests | **IMPLEMENTED, CI-proven** for process crashes (M2, P3). Power-loss durability is **unproven**. |
| 13 | Final acceptance report and approval handoff | **PARTIAL** | `job report` writes a job report plus `rizzstack.return/1` `return.json` and `RETURN.md`; `receiver_decision` is always pending; `job report --verify` recomputes the digest | **IMPLEMENTED, CI-proven** (P4). Merges, deploys, releases and the final acceptance remain human acts. |

## 3. What the audit got right, and what closed

The audit named three critical-path gaps. All three now have code and tests:

1. **No goal/job object** → `job.py`, a signed authorization that a job may only narrow, and `packets.py`
   for workflow-native features.
2. **No coordinator loop** → `reconcile.py` ticks the job; `queue.py` advances the feature queue one pass
   at a time; `agent_work.py` and `agent_consumer.py` handle the one transition that needs reasoning.
3. **No transition wiring** → a terminal attempt now advances through verify, integration and RETURN
   without a human typing a verb mid-run. The verbs still exist for a human to run deliberately; the loop
   calls the same functions.

The original classification — “human-driven orchestration with automated components” — was correct for
`bundlebees@d82630a`. It is no longer the right description of the deterministic factory. It is still the
right description of production use, because a human authorizes the job and gates the merge.

## 4. What is still genuinely missing

These are limitations, not backlog items that were quietly closed:

- **No real coding-worker feature has run through the complete factory.** The factory proofs use
  deterministic worker scripts inside a real git and hyvv HTTP harness. The real-bee experiments predate
  the job store and did not include recovery or RETURN.
- **No multi-feature, multi-agent campaign.** The two-feature A→B factory is the widest run; there is no
  evidence for several concurrent features, several agents, or several waves under load.
- **OS principal isolation is not established.** Authority separation is file-level (a separate approval
  key, TTY gates, signed documents) inside one state directory. A principal that can write the whole state
  directory is not contained; a coordinator with shell access could forge a signed file.
- **Network and filesystem restrictions for Hermes inference are not fully enforced.** The decision child
  gets an allowlisted environment, a temp HOME/TMPDIR, `-t todo`, output caps, timeouts and rlimits — but
  no network egress allowlist, no filesystem isolation (the bwrap probe fails on this host), no seccomp,
  and the provider key is visible to the child by design. The prompt is an argv element visible to local
  `ps`.
- **Cross-machine operation is unproven.** No run has crossed hosts with the real transport; the mirror
  and create-only publication are exercised against local fixtures.
- **Windows live is unproven.** hyvv has Windows-first installers and Windows-aware path tests; the live
  Windows host has not run the provisioning branch.
- **Power-loss durability is unproven.** Crash tests kill processes at named boundaries; torn writes and
  fsync-loss are not tested.
- **Real-model cost and usage are incomplete.** Token counts are recorded where the runtime reports them;
  cost stays `UNKNOWN` because no pricing feed exists.
- **Multi-wave acceptance coverage is thin.** One wave, occasionally two features; no long campaign.
- **Workflow cold-start acceptance is still failing** (`CS-apply-tax … 0 signed records`). The repo's own
  acceptance demo cannot be used as the loop's proof.
- **Merges, deploys, releases and final acceptance are human-gated.** No code path in the loop merges,
  tags, pushes to a protected branch, deploys, or records a receiver decision.

## 5. Secondary defects worth recording

- **The verify → integrate seam is fixed for the loop, not for the old verb.** `verify --dry-run` still
  records `sha: null`; `integrate_wave` needs a real ancestor commit. The loop uses `--commit-local` and
  `integrate_job`, which is why the seam now holds. A human using `verify` without `--commit-local` and
  then `integrate` is using a different path.
- **An HMAC is not human consent.** Leases, jobs and authorizations are signed with keys the coordinator
  holds. The HMAC proves integrity, not who authorised the work. The TTY gate and the separate approval
  key reduce accidental self-authorisation; they do not prove identity.
- **Protocol pinning is to unmerged branches.** Bundlebees CI pins workflow `070b6c1` (the revision PR #33
  was pinned at) and hyvv
  `5bee1a8` (the revision PR #4 was pinned at). Both PRs are open and blocked; chapters 25–27 and the
  provisioning endpoints exist only on those branches until they merge.
- **The agent-work item is agent-agnostic by construction.** It names a request, a digest and an optional
  adapter hint; it never carries a prompt, argv or transcript. That is what makes the Hermes adapter
  replaceable, and it is asserted by tests rather than convention.
