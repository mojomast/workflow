# 24 — Autonomy dogfood

**Status (November 13, 2026):** One authorized objective, one injected failure, zero unplanned human interventions. Written after auditing `workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820` and `orbitdesktop@eddc502`.

**Audience:** the approver and the coordinator running the campaign.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) · [23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md). Read them in that order.

---

One real objective, one authorization, one verified result, no human in the middle. Failure with accurate
evidence is an acceptable outcome; a success that needed undisclosed help is not.

## The objective

**"Add contract-source-revision validation to `acdd-lint`."**

Two tasks, disjoint leases, both genuinely useful — a frozen contract whose `source_rev` is not a
reachable commit, or not a full 40-hex sha, currently passes lint while making every downstream evidence
record meaningless.

| Task | Requirement | Lease |
|---|---|---|
| T1 | a contract whose `source_rev` is not 40 hex is refused (`contract_source_rev_malformed`); a valid sha is silent | `tools/acdd-lint/acdd_lint/checks_source_rev.py`, `tools/acdd-lint/tests/test_check_source_rev.py` |
| T2 | a contract whose `source_rev` is not reachable from the repository head is refused (`contract_source_rev_unreachable`), with an explicit "not checked" result when no repository is supplied | `tools/acdd-lint/acdd_lint/checks_reachability.py`, `tools/acdd-lint/tests/test_check_reachability.py` |

Wiring into `cli.py` stays coordinator-owned, exactly as in Experiment B.

## Why this objective

- **Real:** it closes a defect the method has today (a contract can pin a commit nobody can reproduce).
- **Deterministic:** pure Python, a git fixture repo, no network, no model judgement.
- **Partitionable:** two independent files, no shared registry.
- **Not trivial:** a text-file change cannot satisfy it; T2 needs real `git merge-base --is-ancestor`
  behaviour and a not-checked path.
- **Bounded:** one bee each, ~10–20 minutes of worker time.

## The controlled failure (declared in advance, not discovered by luck)

T2's **first** contract will name a test id that does not exist at the pinned revision
(`tests/test_check_reachability.py::Reachability::test_ancestor_ok` while the real method is
`test_reachable_commit_is_silent`). The bee will produce a patch whose named test cannot pass. The loop
must:

1. verify → RED missing / test not found → task `rejected` with `failure_class: specification`;
2. freeze a **superseding** contract (`supersedes` + `supersedes_sha256`, the B3b pattern);
3. re-dispatch T2 once with the corrected contract;
4. accept the corrected patch and integrate.

This is disclosed in the job file under `injected_failures`, so nobody can later mistake it for a real
defect or claim the run was flawless.

## Authorization (asked once)

One envelope, written into the job file before dispatch:

- repo `mojomast/workflow` at `817eac4` (or whatever main is at authorization time)
- scope: `tools/acdd-lint/**` only
- budget: **4 bee dispatches** (T1, T2-fail, T2-retry, one spare), **90 minutes** wall clock
- push: **forbidden** — the loop ends with a patch set and a report; branches and PRs are a human act
- merge/deploy/release: **forbidden**, approval gate at the end

## What the human does, and does not do

Human, once: authorize the goal, scope and budget.

Human, at the end: read the report, look at the final patch, decide.

Human, in between: **nothing**. Not "is it done?", not "verify this", not "integration failed, try again".
If the coordinator needs a human mid-run, that is a **failure of the experiment**, recorded as an
intervention with its reason.

## Success conditions (all must hold)

1. Authorization recorded once through `job authorize` (interactive, human-typed), with scope and budget;
   the job only narrows it.
2. The loop dispatches T1 and T2 without a prompt.
3. A terminal attempt state advances the job without a human turn — the mechanical cron tick did it, and
   any reasoning step was a second, separate agent turn driven by `needs-agent.json`, not by a person.
4. Each patch is verified independently in an isolated worktree at the pinned base: lease check,
   RED/GREEN, suite, gitleaks — and on success a **local** commit on `bb-verify/<attempt_id>`, never a push.
5. Verified patches integrate automatically through `integrate_wave`, which receives a real ancestor
   commit (not `sha: null`); the combined suite runs.
6. The T2 injected failure is handled autonomously: classified `specification`, superseded, re-dispatched
   once, accepted — with the failing attempt and its evidence preserved.
7. The report and the acceptance artifact exist on disk with per-task evidence, and no gate is resolved.
8. The loop stops at the approval gate and performs no merge, push or deploy.

**What the slice must contain for this to be honest:** bounded recovery (M4) and the report/gate (M5) are
inside the slice, not after it. A run that needs a human to handle the injected failure, or to write the
summary, is not an autonomy demonstration — it is the current state with extra steps.

## Measurements

| Metric | Source | Note |
|---|---|---|
| Human interventions after authorization | reconciler `events` with `actor: human` | **primary metric: must be 0** |
| Autonomous transitions | count of `events` with `actor: reconciler` | target ≥ 8 |
| Worker execution time | launcher attempt `created_at` → terminal | per bee |
| Coordinator overhead | wall clock − sum(worker time) | includes cron granularity (≤60 s per transition) |
| Accepted vs rejected patches | job tasks | expect 3 submitted, 2 accepted, 1 rejected (the injected failure) |
| Retry / repair cycles | events with `kind: retry` | expect exactly 1 |
| Integration failures | wave records | expect 0 after the corrected patch |
| Recovery success | injected failure resolved without a human | boolean |
| Wall clock | authorization → `awaiting_approval` | — |
| Tokens | launcher `observed.usage` per attempt | summed, actual values |
| Cost | — | **UNKNOWN** (no pricing feed) |
| Resource use | `/v1/health` active/max, host load | per-bee CPU/RAM **UNKNOWN** |

## Failure modes and what they mean

| Observation | Meaning |
|---|---|
| Job stalls with a task in `dispatched` and no state change | the cron tick is not running, or the reconciler crashed — infrastructure defect |
| A verified patch is integrated without RED evidence | correctness defect in the verifier wiring; stop the experiment |
| The injected failure is "recovered" by editing the contract to match the bee's output | the exact defect Experiment B caught; treat as a failed run |
| The loop reports success but the combined suite was not run | acceptance was manufactured; failed run |
| A human is asked anything between authorization and the report | the loop is not autonomous yet; record the reason |

## Crash honesty

If the coordinator is killed mid-run (deliberately or not), the run is not restarted from scratch and not
quietly re-dispatched. The next tick must adopt the in-flight attempt from the launcher journal, and the
report must say `attempt_adopted` with the crash window. A duplicate dispatch is a failed run, even if the
final result looks correct.

## What this proves if it passes

That a single authorization can carry a real, non-trivial change from goal to verified, integrated,
auditable result — including one genuine failure recovered inside the declared budget — with the human
touched only at the gate. That is the claim worth making.

## What it does not prove

Cost, multi-repo work, goals requiring decomposition beyond two tasks, behaviour under launcher outages,
or scale beyond three concurrent workers. Those stay open, and the report will say so.
