## Autonomy: where the loop breaks, and the smallest thing that closes it

Four chapters, written **after** reading the code in all four repositories at the pinned SHAs —
`workflow@817eac4`, `bundlebees@d82630a`, `hyvv@4ebd820`, `orbitdesktop@eddc502` — not from README claims.
Documentation only: no code, no service, no configuration.

| Chapter | What it says |
|---|---|
| [21 Gap analysis](docs/21-autonomy-gap-analysis.md) | The thirteen transitions from an authorized goal to a verified result, each classified **PROVEN / IMPLEMENTED-UNPROVEN / PARTIAL / MISSING** with file-level citations |
| [22 Architecture](docs/22-autonomy-architecture.md) | Reconcile against durable state; signed job document; authority the job may only narrow; crash-safe side effects; local-commit verification; bounded recovery; the real wake-up path |
| [23 Development plan](docs/23-autonomy-devplan.md) | Five milestones with frozen acceptance contracts, exact file leases and an integration-test matrix; what must be built now and what waits |
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

### Revision after review (`946f455`)

Six corrections, each specified in the documents rather than promised:

1. **Verify → integrate seam.** `verify --dry-run` records `sha: null`, which `integrate_wave` cannot
   consume, while the default `verify` pushes. The autonomous path is now `--commit-local`: an isolated
   worktree at the pinned base, tests and gitleaks, then a **local** `bb-verify/<attempt_id>` commit whose
   parent is the base and whose diff must equal the patch's file list. Nothing is pushed; `integrate_wave`
   is unchanged and keeps its guarantee.
2. **Crash-safe side effects.** An intent is written and fsynced before every external call. After a crash
   the next tick reconciles against the launcher journal: one match adopts, zero re-dispatches, two
   escalates (`dispatch_ambiguous`). Idempotency key `uuid5(job, task, attempt)`, plus an `O_EXCL`
   single-writer lock with visible `lock_stolen` events.
3. **Authorization provenance.** An HMAC proves integrity, not consent — the coordinator holds the key. So
   authority is a separate object, written interactively (TTY required) with the human's typed statement,
   which the job may only narrow. The docs say plainly that this deters accidental self-authorization and
   makes forgery visible; it is not proof of identity.
4. **Wake-up.** Two cron entries named exactly: a mechanical `job tick`, and a second agent turn driven by
   `needs-agent.json`. Polling the launcher is explicitly not the same as resuming an agent. The protocol
   side is a file and CLI verbs — no Hermes assumption anywhere in the job format.
5. **Milestone dependencies.** Bounded recovery and the report/gate are now **inside** the slice (M4, M5),
   because the dogfood cannot demonstrate autonomy if a human has to handle its own injected failure.
6. **Granularity.** Unlimited pure updates, batch dispatch, at most one heavy operation per tick. A fresh
   tick dispatches all ready tasks and performs no verify and no integrate — both halves are acceptance
   criteria and are tested.

### Verified CI state of the prerequisite (bundlebees #15)

Measured, not assumed: at `01b3cfb` in a clean venv built the way CI builds it, collection fails with
**18 errors**; `jsonschema` alone leaves `fastapi`; that leaves `httpx`; with all three the suite is
**563 passed, 16 skipped in 78.84 s**. `ci.yml` installs a hand-listed dependency set and never installs
the project, which is why the same two jobs also fail on main (run `43356463416`). The fix is a CI change
that has not been authorized, so #15 is not merged on a red gate.

### Notes for review

- The documents cite real files and functions (`leases.py::record_lease`, `tools.py::_dispatch`,
  `revision.py::integrate_wave`, `acdd_cli.py` `contract`/`tdd`), and mark uncertainty rather than filling
  it in.
- The known cold-start acceptance failure is recorded as open and deliberately not prioritised, per the
  instruction that it must not block the loop.
- README index rows and a changelog entry are included.

### Gate at this head

`bee-ci/reference`, `bee-ci/project-state`, `bee-ci/secret-scan` — **success** at
`946f4558fa1e4f422fa8653c318c2160dece9d49`. Draft, not merged; no deployment, restart or dispatch.
