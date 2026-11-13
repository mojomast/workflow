## Autonomy: where the loop breaks, and the smallest thing that closes it

Four chapters, written **after** reading the code in all four repositories at the pinned SHAs —
`workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820`, `orbitdesktop@eddc502` — not from README claims.
Documentation only: no code, no service, no configuration.

| Chapter | What it says |
|---|---|
| [21 Gap analysis](docs/21-autonomy-gap-analysis.md) | The thirteen transitions from an authorized goal to a verified result, each classified **PROVEN / IMPLEMENTED-UNPROVEN / PARTIAL / MISSING** with file-level citations |
| [22 Architecture](docs/22-autonomy-architecture.md) | Reconcile against durable state instead of subscribing to transient events; signed job document, one transition per tick, state machine, event contract, bounded recovery, human-authority boundary |
| [23 Development plan](docs/23-autonomy-devplan.md) | Six milestones with frozen acceptance contracts; what must be built now and what deliberately waits |
| [24 Dogfood](docs/24-autonomy-dogfood.md) | A two-task objective with one failure declared in advance; 4 bees, 90 minutes, and zero unplanned human interventions as the primary metric |

### The headline finding

**Rizzstack today is human-driven orchestration with automated components, not autonomous
orchestration.** Parallelism is real (3 concurrent bees, Experiments A and B). Verification is real when
invoked. Integration is genuinely fail-closed — `revision.integrate_wave` refuses a wave unless every
attempt has an `ok` verify result with an ancestor sha *and* the full suite exits 0.

But three transitions are missing:

1. **No job object.** Leases are per-attempt, the launcher journal is per-attempt, and the goal itself
   lives in a chat message. Every attempt is durable; the *work* is not.
2. **Nothing wakes the coordinator.** `hyvv` offers `GET /v1/attempts/{id}/events?cursor` and no callback,
   webhook or push. `orbitdesktop` polls it. A bee reaching a terminal state causes nothing.
3. **Verification and integration are verbs a human types.** Nothing calls `bundlebees verify` or
   `integrate` on a state transition.

### The smallest slice

A signed job document plus a reconciler that performs exactly one transition per cron tick, wired to the
verbs that already exist. No broker, no database, no new daemon. Because the launcher journal is already
a system of record, reconciling against it also gives crash recovery for free.

One prerequisite is already built and waiting: the typed artifact consumer (bundlebees #15) is still a
draft PR, so the loop would otherwise read artifacts through the coordinator's rig rather than product
code.

### Notes for review

- The documents cite real files and functions (`leases.py::record_lease`, `tools.py::_dispatch`,
  `revision.py::integrate_wave`, `acdd_cli.py` `contract`/`tdd`), and mark uncertainty rather than
  filling it in.
- One correction found while writing: the `verify` flag is `--dry-run` (apply and test without
  committing or pushing), not a `--no-push` that does not exist. The autonomous path must use it;
  `verify` otherwise commits and pushes by default.
- The known cold-start acceptance failure is recorded as open and deliberately not prioritised, per the
  instruction that it must not block the loop.
- README index rows and a changelog entry are included.

Docs-only. The bee-ci contexts are not posted yet — they are required before this can merge, and I will
run the gate at the head when asked to prepare it for merge.
