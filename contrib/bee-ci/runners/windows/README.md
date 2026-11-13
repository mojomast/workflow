# bee-run Windows runner (stub)

This directory holds the job wrapper for a future **native Windows** bee. The
bee runtime today is Linux containers only; there are no native Windows bees
and this wrapper is not wired into CI. It is a stub so the job/result contract
can be reviewed and tested before a Windows VM exists.

Nothing in this change was executed on a Windows host. See
[NOT RUN](#not-run) for the exact gaps.

## Usage

```powershell
.\run-job.ps1 `
  -JobManifest C:\bee\job.json `
  -Checkout   C:\bee\worktree `
  -ResultManifest C:\bee\result.json
```

Plan without running the steps:

```powershell
.\run-job.ps1 -JobManifest .\job.json -Checkout . -ResultManifest .\plan.json -PlanOnly
```

The wrapper exits `0` when every executed step passed and `1` when a step
failed, a step timed out, or the manifest/checkout was rejected. The result
manifest is written even when the job is rejected, when possible.

`run-job.ps1` requires Windows PowerShell 5.1 or PowerShell 7+.

## Job manifest

```json
{
  "schema_version": 1,
  "job_id": "windows-ci-001",
  "timeout_seconds": 60,
  "redact": ["literal-value-that-must-not-appear"],
  "steps": [
    {
      "id": "restore",
      "name": "Restore packages",
      "command": "dotnet restore",
      "timeout_seconds": 300
    },
    {
      "id": "test",
      "command": ["dotnet", "test", "--no-restore"],
      "cwd": "src"
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `job_id` | yes | Safe identifier (`A-Z`, `a-z`, `0-9`, `.`, `_`, `-`; max 128 chars) |
| `steps` | yes | Non-empty list, at most 1000 entries |
| `timeout_seconds` | no | Default per-step timeout; falls back to the contract default (900) |
| `redact` | no | Literal strings removed from commands and captured output |
| `steps[].id` | yes | Unique safe identifier for the step |
| `steps[].command` | yes | Non-empty string, or an array of arguments |
| `steps[].name` | no | Display name; defaults to the step id |
| `steps[].timeout_seconds` | no | Per-step override, 1..86400 seconds |
| `steps[].cwd` | no | Relative to the checkout, must resolve inside it |
| `steps[].continue_on_error` | no | Boolean; default `false` (fail-fast) |

An array command is converted to a PowerShell call expression with each
argument single-quoted, for example `["dotnet", "test"]` becomes
`& 'dotnet' 'test'` and is not re-parsed as a shell pipeline. A string command
is passed to a fresh `-NoProfile -NonInteractive` PowerShell process as-is.

The job manifest is trusted input: its commands execute on the runner. Only
run manifests produced by the coordinator, and never put secrets directly in a
command or step name. Redaction is defence in depth, not a guarantee.

## Command plan

`-PlanOnly` emits a `bee-run/command-plan` JSON document with the resolved
working directory, timeout, command and failure policy for each step. Commands
are redacted before the plan is written. The plan is deterministic for a given
manifest and checkout.

## Result manifest

Each executed step records its `status`, `exit_code`, `duration_ms`,
`timed_out`, `stdout`, `stderr` and `output_truncated`. The overall status is
`passed` only when every executed step passed. The first failure is echoed in
`failure`:

```json
{
  "schema_version": 1,
  "kind": "bee-run/result-manifest",
  "job_id": "windows-ci-001",
  "status": "failed",
  "failure_policy": "fail-fast",
  "steps": [
    {
      "index": 2,
      "id": "test",
      "status": "failed",
      "exit_code": 7,
      "duration_ms": 1234,
      "timed_out": false,
      "stdout": "",
      "stderr": "test failed",
      "output_truncated": false
    }
  ],
  "failure": {
    "step_id": "test",
    "exit_code": 7,
    "reason": "non_zero_exit"
  }
}
```

A timeout has `"status": "timed_out"`, `"timed_out": true`,
`"exit_code": null` and `"failure": {"step_id": "...", "exit_code": null,
"reason": "timeout"}`. A non-zero exit has `"reason": "non_zero_exit"`. A
manifest rejected before execution records `invalid_job_manifest` or
`runner_error` with a redacted message.

By default the runner stops at the first failure. Set `continue_on_error` on
the failing step to run the remaining steps; the overall manifest still reports
`failed`.

## Security and redaction

- Rejects a missing checkout, missing or oversized job manifest (over 1 MiB),
  unsafe or duplicate ids, too many steps, invalid timeouts, and `cwd` values
  that escape the checkout. Symbolic links and junctions are resolved before
  the containment check, so an in-checkout link cannot point outside it.
- Never logs the process environment. Values of environment variables whose
  names look sensitive are added to the redaction set without their names being
  written out.
- Redacts declared literals, sensitive environment values, bearer/basic
  authorization values, common `password`/`token`/`secret`/`api_key`
  assignments, and credentials embedded in URLs.
- Redacts before truncation, caps each captured stream at 20,000 characters,
  and writes the result manifest atomically.
- On timeout, kills the step's process tree (`taskkill /T /F` on Windows) and
  records the timeout.

## Offline contract

The machine-readable contract sits between the `BEGIN BEE-RUN CONTRACT` and
`END BEE-RUN CONTRACT` markers in `run-job.ps1`. The Python tests read the same
contract, so the plan/result shapes, failure policy, limits and redaction rules
cannot silently drift from the script.

## Tests

```bash
python -m pytest contrib/bee-ci/tests/test_windows_runner.py -q
```

The Python tests cover manifest parsing, command-plan construction, per-step
exit-code recording, failure propagation, timeout results, redaction and the
static contract used by the PowerShell script. When `pwsh` is available on the
test host, one test also runs `-PlanOnly` and checks the emitted plan; that is a
plan-construction check, not a Windows execution check.

## NOT RUN

These items need a real Windows host and were **not executed**; they are not
reported as passing:

- Running any step on Windows, including exit-code capture from Windows
  processes.
- Process-tree termination through `taskkill /T /F` after a timeout.
- Windows path, drive, ACL, symlink and working-directory semantics.
- PowerShell 5.1 compatibility; the script targets 5.1+ but was not exercised
  on Windows PowerShell 5.1.
- `Start-Process` redirection and encoding behaviour on Windows.
- Integration with the bee coordinator, a Windows VM image, Orbit or CI.
- The pytest case `test_real_windows_host_execution`, which is deliberately
  skipped with the reason "requires a real Windows host".
- `test_plan_only_under_powershell` is skipped when no PowerShell binary is
  installed. Even when it runs, it only builds a plan; it does not prove
  Windows execution.

A manual smoke test of generic pass/fail/timeout logic under PowerShell 7 on
Linux was possible during review, but it is not Windows evidence and is not
part of the committed test result.
