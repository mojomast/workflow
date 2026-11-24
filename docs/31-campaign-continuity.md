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
3. phase: `authorized`, `ready_to_advance`, `running`, `job_complete`,
   `ready_for_review` or `blocked`;
4. active workers/tasks, with state and attempt ids;
5. dependencies;
6. the last completed action;
7. the next action;
8. the wait condition and, when blocked, the blocker;
9. a revision that changes only when the reconciled view changes.

The job remains the authority. A campaign record is a review objective and a
checkpoint, not a grant. `job_complete` means the queue/job acceptance check
passed — verified attempts, gitleaks, suite and an accepted integration wave —
not that every task row merely says `accepted`. Campaign `ready_for_review`
remains unavailable until a verified closeout gate exists. If the record's repo/base revision no longer matches the
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
8. stop at `job_complete`, `ready_for_review` or `blocked`, with the reason
   recorded. Task-row acceptance alone does not produce `job_complete`; missing
   job evidence is `blocked` at `repair_job_evidence`.

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
  `performance`, `asset`) with no head or a stale head, and a passing `test`
  criterion whose command a recorded run reports as failing;
- empty, placeholder, bare-label or absolute-path evidence;
- an audit with no `status`, a `clean` audit that reports findings or names no
  head, a `findings` audit with no findings, a `not_run` audit with no reason or
  with findings, and a ready report in which no audit actually ran;
- an audit finding with no id, no single disposition, a duplicate id, or a
  rejected/deferred finding without a reason; legacy untraceable disposition
  arrays are refused;
- a `NOT RUN` criterion that no `not_run` entry names by id;
- a non-pending receiver decision, a non-finite performance value or budget, an
  unknown field, or a merge order that is not the open PRs in `merge_order`
  position order (positions are exactly `1..N`, closed PRs have no position).

`merge_order` is a position, not a PR number: a report whose first PR is `#2`
with position `1` is valid, and `recommended_merge_order` must equal the open PR
numbers sorted by position. Comparing the two as sets is what the earlier
validator did, which refused normal reports and accepted contradictory ones.

`NOT RUN` remains allowed in a ready report only when disclosed in
`known_limits` and named in `not_run`; it is a limit the receiver can accept or
reject. A `not_run` audit is disclosed the same way and never counts as an audit
that ran. The validator proves shape and internal consistency, not that an
artifact exists, that a URL returns the claimed bytes, or that a command actually
ran. A valid report is a reviewable claim, not proof.

## 31.7 Bounded trial

The deterministic trial is
`bundlebees/tests/test_campaign_continuity.py`: two tasks, simulated
dispatch/integration state, a fresh checkpoint read, a second reconcile, an
unchanged revision, no redispatch, and `job_complete` requiring a campaign
closeout rather than review acceptance. The separate production-driver restart test
(`bundlebees/tests/test_factory_cli_e2e.py`) uses an authorized job in the real
feature queue and the real `job_cli.tick` path in CI; it is not a live-host
trial.

Measured on **2026-11-15 UTC**:

- workflow `python3 -m unittest tests.test_campaign_report -q` → **100 passed**;
- workflow `python3 -m unittest discover -s tests -t . -q` → **346 passed**;
- bundlebees `pytest tests/test_campaign_continuity.py -q` → **18 passed**;
- `pytest tests/test_campaign_continuity.py tests/test_project_plan.py -q` →
  **28 passed**;
- bundlebees CI run `43719698698` at code head `817b7ee`: **1324 passed,
  7 skipped**, 4/4 checks green (tests sandbox included, real Orbit round trip,
  plugin doctor, gitleaks);
- workflow CI run `43719698748` at `57cea41`: **14/14 checks green**, including
  the campaign report protocol (the job runs `tests.test_campaign_report`, which
  held 48 tests at that commit; the repo-wide `unittest discover` count there was
  294).

No live-host restart, no real-agent multi-hour run and no Git/PR race trial were
run. Those are separate approvals.

## 31.8 Change map

| Repository | Branch | What changed |
|---|---|---|
| `mojomast/workflow` | `feat/campaign-closeout` | closeout schema/validator/template/chapter 30; this chapter; hardened evidence and stale-head checks |
| `mojomast/bundlebees` | `feat/campaign-acceptance` | task/project/campaign boundary; campaign checkpoint module and CLI; driver reconciliation; project acceptance evidence metadata; continuity docs |
| `mojomast/orbitdesktop` | `feat/campaign-closeout-boundary` | docs: Orbit's ACDD evidence view is per-job evidence, not a campaign closeout |

Nothing is merged, tagged, released, deployed or published by this change.

## 31.9 Rails RETURN contract

A campaign that ships rails evidence attaches one companion document to its
RETURN. The companion is `rizzstack.rails-evidence/1`, frozen in
[`schemas/rails/evidence.schema.json`](../schemas/rails/evidence.schema.json)
and summarized in [`schemas/rails/README.md`](../schemas/rails/README.md); the
event family it describes is `rizzstack.rails/1`. The package is the operator
read path documented in
[`contrib/rizzstack-observability/README.md`](../contrib/rizzstack-observability/README.md),
and the requirement comes from
[`specs/rizzstack-rails-spec.md`](../specs/rizzstack-rails-spec.md) section 8:
RETURN gains a `rails-evidence.json` sidecar referenced through the existing
RETURN evidence mechanism.

### What the RETURN manifest must carry

A RETURN manifest is `rizzstack.return-manifest/1` as frozen in
[`schemas/return-manifest.schema.json`](../schemas/return-manifest.schema.json),
and its rails companion describes the `rizzstack.rails/1` event family;
the human document follows [`templates/RETURN.md`](../templates/RETURN.md). The
manifest has no rails block. The rails sidecar is referenced from the existing
`acceptance` array: the rails-backed criterion names the sidecar path or
reference in its `evidence` list, exactly as that schema describes ("paths or
references to the recorded check"). The sidecar itself
(`rizzstack.rails-evidence/1`) must carry:

- `schema` — the literal `rizzstack.rails-evidence/1`, so an unrecognized
  version is refused rather than widened;
- `generated_at` — one UTC timestamp in the fixed microsecond format;
- `machines` — public `alias` plus `role` (`worker`, `coordinator`, `reviewer`,
  `owner`, `other`), never a hostname;
- `ledgers` — `machine` to `ledger_uuid`, never a filesystem path;
- `origin_heads` — each chain's `chain_id`, `seq` and `hash`: the anchor the
  produced range is checked against;
- `imported_checkpoints` — `chain_id`, `seq`, `hash` and `source` for every
  imported stream the consumer relied on;
- `source_coverage` — per adapter `status` (`covered`, `partial`, `gap`,
  `unavailable`) and its explicit `gaps`, each with a `code` and optional
  `source_id`, `range_start`, `range_end`;
- `selected_event_ids` — the exact ledger event ids shown as evidence;
- `code_rev` and `contract_sha256` — the code revision and contract hash the
  evidence is bound to;
- `redaction_policy` — the frozen literal `rails-safe/1`;
- `intervention_count` — the owner-intervention count for the campaign;
- `verification_links` — the `event_id` and `ac_id` pairs that tie a
  verification event to an acceptance criterion (with the optional `verdict`);
- `receiver_decision` — always `pending` (see below);
- `limitations` — optional plain strings for what the evidence does not cover.

A `PASS` in `verification_links` still needs nonempty evidence on the event
itself. Worker claims and transport completions never become a verified state
because they appear in this file.

### Evidence links required

Every reference in the sidecar and in the RETURN evidence column must resolve,
and must resolve to something a receiver can actually open:

- the sidecar path is named in `acceptance[].evidence` for the rails-backed
  criterion, and the same location is written in the RETURN **Evidence** table;
- `selected_event_ids` and `verification_links` use the same immutable
  `event_id` form the ledger uses, so a bounded query and the RETURN agree on
  identity;
- `origin_heads` and `imported_checkpoints` name chain, sequence and hash, so
  the receiver can re-check the exported range against its own copy;
- `source_coverage` names every gap; a gap is missing evidence, never an empty
  success, and it stays visible in the receiver's decision;
- the contract is named by id and file, not by prose: `rizzstack.rails/1` from
  [`schemas/rails/event.schema.json`](../schemas/rails/event.schema.json) and
  the companion from
  [`schemas/rails/evidence.schema.json`](../schemas/rails/evidence.schema.json).

A reference that does not resolve is a broken handoff, not a minor formatting
issue: the receiver cannot verify a claim whose evidence it cannot open.
[`tests/test_rails_contract.py`](../tests/test_rails_contract.py) checks this
chapter's links and required sections, so a missing or invented interface fails
the contract suite.

### Receiver decision stays pending

The sidecar's `receiver_decision` is the constant `pending`, and the RETURN
manifest's own `receiver_decision` is likewise `pending` for the producer.
Rails evidence cannot record a human decision: the decision lives in the RETURN
document and the existing owner review, never in the ledger and never in this
sidecar. A non-pending value is refused by the manifest validator; the producer
says `pending` and stops there.

### Limits of rails evidence

- Hashes prove integrity relative to a stated anchor; they never prove
  completion, correctness or that a producer was honest.
- An unanchored suffix, a deleted suffix without a known head, a compromised
  producer or one principal rewriting every copy of the ledger remains an
  openly stated limit.
- A partial or stale source keeps `partial` coverage plus explicit gaps; the
  receiver should treat that as incomplete evidence, not as a failed build.
- The sidecar reports what the read path observed. It does not execute, retry,
  approve or accept anything, and it does not turn an observation into
  authorization.
