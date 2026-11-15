# 31 — Campaign continuity and evidence

Chapter 30 defines the closeout record. This chapter defines how an authorized
campaign keeps moving toward that record without a human typing `what's next`,
while keeping merge, release, deployment, publishing and final acceptance as
human gates.

The case study is the Jackpot Syndicate build (2026-11-14/15). It was a
chat-coordinated build, not a factory-driver campaign. That distinction matters:
most pauses were the end of a coordinator turn, not a stuck job.

## 31.1 What the transcript actually shows

The durable transcript is the Hermes session `local-2b8bc3…`, with timestamped
user and assistant turns. Worker and job records are in the bundlebees job files
under the plugin state directory. The table below uses the transcript's UTC
timestamps; a "gap" is wall-clock time between the recorded assistant report and
the user message. It is an upper bound on idle time, not a measurement of how long
a worker was blocked.

| UTC | User turn | Previous coordinator report | Gap | Classification |
|---|---|---|---|---|
| 01:33:00 | `whats next` | 01:32:35, T-015 only lane in flight | 25 s | tick stopped (turn ended); unnecessary nudge |
| 01:46:25 | `t-080 landed` | 01:38:33, T-080 in flight | 7 m 52 s | tick stopped; worker wait; nudge |
| 02:09:56 | `072 and 073 landed` | 01:50:07, wave in flight | 19 m 49 s | tick stopped; worker wait; nudge |
| 02:24:46 | `081 lkanded` | 02:14:07, wave in flight | 10 m 39 s | tick stopped; worker wait; nudge |
| 02:46:08 | `bees landed` | 02:26:10, wave in flight | 19 m 58 s | tick stopped; worker wait; nudge |
| 03:26:55 | `the last bee landeed` | 03:15:59, final wave in flight | 10 m 56 s | tick stopped; terminal wave; nudge (the exact attempt is not reconstructed) |

The six recorded silences total **1 h 9 m 39 s** of wall clock. That is a measure
of how long the owner was silent, not of worker idle time: bees were running for
part of every gap. No gap is evidence that a worker was stuck.

Other user turns were not continuity pauses:

- 01:36:45 asked what the assets were — a genuine information decision.
- 05:59:24 asked for another improvement pass — **new instruction**, not the
  original objective continuing.
- 06:49:21 asked for push/handoff — a handoff request, not a blocked campaign.
- The dashboard, game-link, missing-UI, larger-UI, research and subagent turns
  changed the product or the method; they were owner decisions, not nudges.

No literal `resume` appears in the Jackpot segment. The owner's phrasing
(`whats next`, `landed`) performed the resume. The only literal `resume live
commissioning` in the durable transcript belongs to the factory run, not to
Jackpot.

The durable worker state says the same thing differently: the bundlebees lease
directory contains **22 lease files whose brief names `mojomast/jackpotsyndicate`**,
but the job directory contains **15 job documents, all `smoke-*`** — there is no Jackpot
job document and no campaign/queue entry. The build's authority was per-lease
dispatch, not one authorized job. That is why a restart had nothing durable to
reconcile at the campaign level; the coordinator had to reconstruct progress from
leases, Git and chat on every turn.

### Classification

- **Session ended** — not observed for Jackpot. The session stayed alive across
  compactions; no host or process restart is evidenced.
- **Scheduler or tick stopped** — the dominant cause. There was no resident
  scheduler or tick for this build. Each coordinator turn ended after reporting,
  and the next turn began when the owner spoke.
- **Worker wait** — present inside the gaps, but not sufficient to explain them:
  a watcher or notification existed, yet the coordinator did not turn the
  completion into the next authorized action.
- **Failure** — no pause in the table is explained by a recorded test or worker
  failure. Failures in the build were handled inside turns and preserved in the
  record (for example the reverted symbol-dedupe experiment).
- **Genuine decision needed** — the asset, UI, research, subagent and new-pass
  turns. These are expected gates, not nudges.
- **Another cause** — the 03:26:55 worker identity is not recovered from the
  transcript; it is classified as a terminal-wave nudge with an unknown attempt.
- **Uncertainty** — the source is a chat transcript, not a per-tick scheduler log.
  Gaps measure wall-clock silence, not worker runtime. No claim is made about
  exact compute time or token usage.

## 31.2 What must be durable

A campaign checkpoint must record at least:

1. objective and the one job that executes it;
2. a snapshot of the sealed authorization: auth id, statement, repo, base
   revision, scope, budget and human gates;
3. phase: `authorized`, `ready_to_advance`, `running`, `ready_for_review` or
   `blocked`;
4. active workers/tasks, with state and attempt ids;
5. dependencies;
6. the last completed action;
7. the next action;
8. the wait condition and, when blocked, the blocker;
9. a revision that changes only when the reconciled view changes.

The job remains the authority. A campaign record is a review objective and a
checkpoint, not a grant. If the record's repo/base revision no longer matches the
job, reconciliation refuses rather than silently adopting a different job.

## 31.3 Restart reconciliation

On every scheduler pass and on restart:

1. load the checkpoint and the durable job;
2. verify repo/base revision match;
3. derive accepted, active, failed, ready and dependency-blocked tasks;
4. adopt completed and in-flight work from the job's durable state — do not
   dispatch a second time;
5. record the latest event as the last completed action;
6. choose the next action and wait condition;
7. write only if the view changed;
8. stop at `ready_for_review` or `blocked`, with the reason recorded.

The campaign layer does not dispatch. Duplicate suppression remains in the job's
dispatch intent/idempotency key, the signed lease and the queue's exclusive
claim. A second accepted wave after a restart is a job/queue defect; the
checkpoint must not paper over it.

**Current implementation boundary.** `reconcile` reads the durable job (with
`jobs.load_job`'s accepted-wave recovery) and the task/worker state; it does not
independently query Git or the GitHub PR. The job's accepted refs are the durable
Git evidence it relies on, and the launch/landing path owns the worker state. A
campaign that needs a separate `git rev-parse`/`gh pr view` comparison has to add
a read-only observer; that is not implemented here and must not be reported as
done. The trial below is therefore a job-state restart trial, not a full Git/PR
race trial.

## 31.4 Wake-up mechanism

The supported mechanism is a host-run resident process:
`bundlebees_plugin.factory_driver --interval … --campaign-id …`. `job tick` and
`job queue run --once` are one-shot commands; cron may call them, but this
repository does not install a cron entry. A prompt instruction is not a
scheduler.

What is **implemented** in bundlebees:

- `campaign init|status|reconcile|resume-plan` commands;
- `FactoryDriver(campaign_id=...)` reconciliation on each pass;
- a systemd-unit *template* in `docs/CAMPAIGN-CONTINUITY.md`;
- atomic, mode-`0600`, idempotent checkpoints;
- deterministic restart tests.

What requires the **host**:

- installing, enabling or restarting the unit;
- choosing an interval and a restart policy;
- providing the launcher/queue/repo environment;
- keeping the host awake.

What remains **manual/unproven**:

- a real systemd restart on the coordinator host;
- a launcher reboot with a real bee in flight;
- a live-agent multi-hour campaign with no owner nudge;
- a real-Git/PR reconciliation after an actual branch move.

If the host is down, the campaign is idle. On restart it reconciles; it does not
assume time passed safely or that a worker is still alive without evidence.

## 31.5 Product evidence throughout the build

Before dispatch:

- every product acceptance criterion gets an id, statement, evidence kind,
  evidence stage, owner and intended evidence reference;
- one vertical slice exercises the real user journey and the main integration
  risk before the graph expands;
- task completion, integrated behavior, evidence readiness and the owner's final
  acceptance stay separate.

After integration waves and on the final combined revision:

- run the real application journey, not just unit tests;
- capture visual evidence where the product is visual;
- exercise persistence and cross-feature behavior;
- run the full suite and record command, exit code and counts at the final head;
- list everything not run, with a reason.

The Jackpot lesson: a reachable board and meta screen did not prove the authored
art was visible. A DOM assertion is not a visual acceptance.

## 31.6 Campaign-report hardening

`workflow/schemas/campaign-report.schema.json` and
`workflow/tools/campaign_report.py` now reject:

- `ready_for_review` with failed test runs, no test runs, or a recorded test run
  whose `head_sha` is not the final `head_rev`;
- a `PASS` on a revision-bound criterion (`test`, `integration`, `visual`,
  `performance`, `asset`) with no head or a stale head;
- empty, placeholder, bare-label or absolute-path evidence;
- audit findings without at least one of fixed/rejected/deferred;
- a non-pending receiver decision, or an incomplete merge order.

`NOT RUN` remains allowed in a ready report only when disclosed in
`known_limits`; it is a limit the receiver can accept or reject. The validator
proves shape and internal consistency, not that an artifact exists, that a URL
returns the claimed bytes, or that a command actually ran. A valid report is a
reviewable claim, not proof.

## 31.7 Bounded trial

The deterministic trial is
`bundlebees-closeout/tests/test_campaign_continuity.py`: two tasks, simulated
dispatch/integration state, a fresh checkpoint read, a second reconcile, an
unchanged revision, no redispatch, `ready_for_review` requiring a human. It is
not a live-host trial.

Measured on **2026-11-15 UTC**:

- `pytest tests/test_campaign_continuity.py -q` → **10 passed**;
- `pytest tests/test_campaign_continuity.py tests/test_project_plan.py -q` →
  **20 passed**;
- full `pytest -q` after the campaign layer: see the PR checks; the local run is
  recorded in the campaign report, not asserted here.

No live-host restart, no real-agent multi-hour run and no Git/PR race trial were
run. Those are separate approvals.

## 31.8 Change map

| Repository | Branch | What changed |
|---|---|---|
| `mojomast/workflow` | `feat/campaign-closeout` | closeout schema/validator/template/chapter 30; this chapter; hardened evidence and stale-head checks |
| `mojomast/bundlebees` | `feat/campaign-acceptance` | task/project/campaign boundary; campaign checkpoint module and CLI; driver reconciliation; project acceptance evidence metadata; continuity docs |
| `mojomast/orbitdesktop` | `feat/campaign-closeout-boundary` | docs: Orbit's ACDD evidence view is per-job evidence, not a campaign closeout |

Nothing is merged, tagged, released, deployed or published by this change.
