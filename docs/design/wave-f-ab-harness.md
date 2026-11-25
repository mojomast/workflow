# Wave F design: an A/B harness scored by tokens per verified patch

Status: **accepted as design** (Kyle, chat t1650u). Design only. Wave F of the Nov 24 next-level review ([rizzstack #17](https://github.com/mojomast/rizzstack/pull/17)). The memory canary (W2-G) stays paused until experiment F1 reports.

## Problem

Context and routing changes ship on judgment: memory recall adds text to every brief, the codemap
slices change what bees read, and model cascades change cost. Nothing measures the effect before the
change is switched on. The weekly number from wave A slice M1 (tokens per verified patch) says how
the factory is doing, not what caused it.

## Decision (proposed)

1. **Task set.** Replay past tasks: each merged wave-A-style slice gives a frozen brief, the RED
   commit and the approved tests. Start with 20 tasks across bundlebees, hyvv and orbitdesktop.
   Tasks whose tests needed a fix after merge are excluded (flawed tests skew the score).
2. **Arms.** One variable per experiment (for example memory recall off/on). Everything else is
   pinned: model, harness, budget, source_rev, sandbox.
3. **Score.** Primary: tokens per verified patch (verify GREEN, full suite green, scope clean).
   Secondary: verified rate, regressions (from the affected-tests list), wall time. Unknown usage is
   reported as unknown, never zero (the same rule as M1).
4. **Runs.** Each arm runs each task N=3 times on the worker host in a dedicated project, never
   against a live repo branch. A run is one hyvv attempt with a ticket like any other dispatch.
5. **Decision rule.** Switch a change on only when the primary metric improves by at least 10% and
   the verified rate does not drop, both with a bootstrap 90% interval that excludes zero.
6. **Outputs.** `evidence/ab/<experiment>/` holds the plan, raw attempt records and a summary
   (Rails events once wave D lands). Later: an advisory mutation gate on approved tests, and
   OpenTelemetry GenAI spans from hyvv and bundlebees.

## First experiments (in order)

| # | Variable | Why first |
|---|---|---|
| F1 | memory recall off vs on | gates W2-G |
| F2 | codemap slice in the brief vs none | the review cites over 20% more inference cost for generic repo overviews |
| F3 | test-context brief (failing output + affected tests) vs objective only | the review's strongest evidence |
| F4 | cheap model first, escalate on verify failure, vs one model | cost |

## Cost

20 tasks x 2 arms x 3 runs = 120 attempts per experiment. That is the main reason to keep N and the
task set small and to run the experiments one at a time.

## Exit

Every context or routing change ships with its measured effect.

## Decisions for the owner

- The budget per experiment (attempts and tokens), and whether F1 runs before any memory restart.
- N and the decision threshold.
