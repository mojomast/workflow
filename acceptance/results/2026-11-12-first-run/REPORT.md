# Cold-start acceptance report — first run, Nov 12, 2026 (America/Toronto)

**Result: PASS** in 1.17 s. Accepted integration artifact: `true`.

## Environment

| Key | Value |
|---|---|
| mode | local |
| python | Python 3.13.5 |
| git | git version 2.47.3 |
| workflow_ref | 183813f0ccdea4457c9720b9667640f9d9fd8496 (from WORKFLOW_SRC) |
| bundlebees_ref | main |
| os | Linux 6.12.94+ |
| sandbox backend | bwrap |
| worker backend | scripted-offline |
| workflow commit | 183813f0ccdea4457c9720b9667640f9d9fd8496 |
| bundlebees commit | 509649b77d89f42dbcf7713f3a5178ad8f8de333 |

## Steps

| # | Step | Result | Detail |
|---|---|---|---|
| 1 | `reference-demo` | PASS | result:         OK |
| 2 | `start` | PASS | plugin registered: 4 tools, sandbox=bwrap |
| 3 | `register-worker` | PASS | worker backend 'scripted-offline' healthy |
| 4 | `dispatch` | PASS | 3 parallel dispatches, signed leases: ['att-W1.json', 'att-W2.json', 'att-W3.json'] |
| 5 | `violation` | PASS | W3 edited shop/pricing.py outside its lease and claimed it |
| 6 | `verify-honest` | PASS | W1 rc=0, W2 rc=0 |
| 7 | `verify-rejects-violation` | PASS | W3 rc=1 code=scope_violation |
| 8 | `integrate` | PASS | rc=0; wave record written |
| 9 | `outputs` | PASS | independent pytest: 4 passed in 0.01s; W3 change absent |
| 10 | `artifact` | PASS | acceptance-artifact.json accepted=True |

## Interventions

Manual interventions during the run: **0**. Environment workarounds and escape hatches are listed too, so nothing that needed a hand is hidden.

| Kind | What | Why |
|---|---|---|
| environment | ran in a clean temp HOME + venv instead of a container | docker not used (ACCEPTANCE_MODE=local) |

## Metrics (bundlebees summary for the run)

```json
{
  "accepted_changes": 2,
  "attempts_dispatched": 3,
  "attempts_verified": 3,
  "cost_per_accepted": 0.0,
  "cost_usd_total": 0.0,
  "failed_worker_recoveries": 0,
  "first_pass_rate": 0.6666666666666666,
  "human_interventions": 0,
  "plan_to_accepted_s": {
    "max": 1.0,
    "median": 1.0
  },
  "regressions_found": 0,
  "run_id": "acceptance",
  "tokens_per_accepted": 0.0,
  "tokens_total": 0,
  "waves_accepted": 1,
  "waves_rejected": 0
}
```

## Reviewer notes

- **What failed or needed a hand, and why:** nothing during the run; zero manual interventions. One environment workaround: the box has no docker, so the script used a clean temp HOME + venv instead of a container (logged above). The sandbox was real bubblewrap.
- **Earlier development run (honest history):** the very first run, on harness commit `a03123c`, also passed all 10 steps, but it reported W3's rejection code as `None` because the harness read the code from the verify record, which does not store it. The harness now parses the CLI output (`scope_violation`) and saves `verify-W*.log`. That fix is the only change between the two runs. A run against the bundlebees sandbox PR branch (`fix/strong-sandbox-and-ci`) also passed.
- **Anything the harness could not check:** no Hermes host process or Orbit launcher was started (the plugin ran in a minimal host through its documented injection seams); the worker was the scripted offline backend; the optional real-adapter path has not been run. This run was on the same machine that built the harness, so it is not yet the "unrelated machine, someone else" test.
- **Follow-ups:** run it on an unrelated machine (docker mode); run the real-adapter mode against a launcher project that mirrors the toy repo; add a step that starts Orbit once Orbit's first-run path ([15](../../../docs/15-agent-agnostic-and-orbit-start.md)) lands.
