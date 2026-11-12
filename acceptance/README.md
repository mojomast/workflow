# Cold-start acceptance test

The question this answers: can someone other than the author clone the public repositories on a clean machine, start the system, register a worker, dispatch parallel work, watch the verifier reject a deliberate lease violation, and end with an accepted integration artifact — and how many times did a person have to step in?

It is offline by default: no API keys and no model calls. Network is used only to clone [mojomast/workflow](https://github.com/mojomast/workflow) and [mojomast/bundlebees](https://github.com/mojomast/bundlebees) and to `pip install pytest`.

## Run it

```bash
acceptance/cold_start.sh /tmp/acceptance-out        # docker if usable, else clean HOME + venv
ACCEPTANCE_MODE=docker acceptance/cold_start.sh out # force a fresh python:3.12-slim container
ACCEPTANCE_MODE=local  acceptance/cold_start.sh out # clean temp HOME + venv on this machine
```

Requirements: `git`, `python3`, and either docker or bubblewrap/firejail on the host. The output folder must be new or empty.

| Variable | Default | Meaning |
|---|---|---|
| `WORKFLOW_REF`, `BUNDLEBEES_REF` | `main` | Branch or tag to clone |
| `WORKFLOW_SRC` | unset | Clone the workflow repo from this path/URL instead (CI uses the PR checkout; local mode only) |
| `ACCEPTANCE_ADAPTER` | `scripted` | `scripted` is the offline worker. A real bundlebees adapter name (e.g. `launcher`) sends the two honest slices to a real backend; see below |
| `ACCEPTANCE_ALLOW_UNSAFE_LOCAL` | unset | `1` lets verify run without bubblewrap/firejail. Logged as an escape hatch |

## What it does

`cold_start.sh` makes a throwaway HOME, clones both repos fresh, creates a venv, and runs [`harness.py`](harness.py). The harness then:

| # | Step | How |
|---|---|---|
| 1 | `reference-demo` | Runs the workflow repo's [reference demo](../reference/README.md) from the fresh clone |
| 2 | `start` | Loads the bundlebees plugin from its fresh clone and registers it into a minimal host with the same `PluginContext` surface Hermes provides, plus a coordinator state dir |
| 3 | `register-worker` | Registers a worker backend that implements bundlebees' `WorkerBackend` contract (`create`/`result`, plus `health`/`projects`/`attempts`) |
| 4 | `dispatch` | Sends three briefs **in parallel** through the real `bundlebees_dispatch` tool: strict brief validation and an HMAC-signed coordinator lease per attempt |
| 5 | `violation` | Worker W3 edits `shop/pricing.py`, which is outside its lease (`shop/notes.py`), and claims the wider lease in its result |
| 6 | `verify-honest`, `verify-rejects-violation` | Runs the real `hermes bundlebees verify` handler per attempt, in the bubblewrap/firejail sandbox. W1 and W2 must verify; W3 must fail with `scope_violation` and leave nothing applied |
| 7 | `integrate` | Runs `hermes bundlebees integrate` for W1+W2: full suite on the combined branch, accepted wave record |
| 8 | `outputs` | Independently clones the combined branch from the bare remote, runs pytest itself, checks both features landed and W3's change did not, and reads the metrics summary |
| 9 | `artifact` | Writes `acceptance-artifact.json` (shas, verify records, wave record, metrics) |

Outputs in the folder you pass: `REPORT.md` (filled from [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md)), `summary.json`, `steps.jsonl`, `interventions.jsonl`, `acceptance-artifact.json`, `verify-W*.log`, `integrate.log`, `harness.log`.

## Interventions log

`interventions.jsonl` records every time something other than the script did the work, by kind:

- `manual` — a person had to act during the run. The goal is zero.
- `environment` — a workaround for the machine (no docker, CI lifting the AppArmor user-namespace restriction, `--privileged` in docker).
- `escape-hatch` — a safety setting was relaxed (`verify_allow_unsafe_local`).
- `operator-choice` — a non-default option such as a real adapter.

## What it does not prove (yet)

- **No Hermes host, no Orbit.** "Start the system" means loading the real bundlebees plugin into a minimal host through its documented injection seams (`bundlebees_state_dir`, `bundlebees_client`). Brief validation, signed leases, the sandbox, verify and integrate are the production code paths; Hermes' own process, plugin loader and Orbit's launcher are not exercised.
- **The worker is scripted.** It produces deterministic patches. The real-adapter mode (`ACCEPTANCE_ADAPTER=launcher` with `ACCEPTANCE_LAUNCHER_URL`, `ACCEPTANCE_PROJECT`, `BUNDLEBEES_LAUNCHER_TOKEN`) routes W1/W2 to a real launcher and keeps the W3 violation scripted, but it needs a launcher project that mirrors the toy repo and has **not been run yet**.
- **Same-author machine.** The first run was on the machine that built the harness (see [results](results/)). CI is a second clean environment. A run on an unrelated machine by someone else is still the real test.
