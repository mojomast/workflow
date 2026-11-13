# bee-run Linux job runner

`run.sh` executes a bee-run job manifest inside the Cua bee container that the
launcher already provides. It runs commands in the current environment, in
declared order, and writes a result manifest. It does not create containers,
does not require Docker, and does not mount host paths.

## Usage

```sh
contrib/bee-ci/runners/linux/run.sh JOB_MANIFEST.json RESULT_MANIFEST.json
```

Exit status is `0` for a passing job, `1` for a failed or timed-out job, and
`2` for an invalid or refused manifest. A result manifest is written in every
case.

## Job manifest

```json
{
  "job_id": "example",
  "timeout_s": 300,
  "steps": [
    {"id": "install", "run": "npm ci"},
    {"id": "test", "run": "npm test", "timeout_s": 600}
  ]
}
```

- `job_id` is optional and is copied into the result.
- `steps` is required and must be a non-empty list.
- Each step needs a non-empty `run` string. `id` defaults to `step-N`.
- `timeout_s` is a positive number of seconds. A step value overrides the
  job default. An unset or `null` timeout means no step timeout.
- Commands run with `/bin/bash -c` in the launcher's current working directory
  and environment. Execution stops at the first non-zero exit or timeout;
  later steps are recorded as `skipped`.

The runner refuses manifests that ask for mounts, volumes, secrets, or
credentials, because it cannot provide them. It also refuses a manifest that
requires network isolation, because it cannot verify network isolation. It
never reports network isolation as measured.

## Result manifest

```json
{
  "schema": "bee-ci.result.v1",
  "runner": "linux",
  "job_id": "example",
  "status": "failed",
  "reason": null,
  "started_at": "2026-01-01T00:00:00Z",
  "finished_at": "2026-01-01T00:00:02Z",
  "duration_ms": 2000.1,
  "failing_step": "test",
  "steps": [
    {
      "id": "install",
      "command": "npm ci",
      "status": "passed",
      "exit_code": 0,
      "duration_ms": 1200.0
    },
    {
      "id": "test",
      "command": "npm test",
      "status": "failed",
      "exit_code": 1,
      "duration_ms": 800.1
    }
  ],
  "limits": {
    "cpu": {"status": "observed", "value": "200000 100000", "source": "cpu.max"},
    "memory": {"status": "unverified", "value": "unverified", "reason": "limit file is not readable from this container"},
    "pids": {"status": "unverified", "value": "unverified", "reason": "limit file is not readable from this container"}
  },
  "isolation": {
    "network": {
      "status": "unverified",
      "measured": false,
      "isolated": false,
      "reason": "network isolation is not measured by this runner"
    }
  }
}
```

Step status is `passed`, `failed`, `timeout`, or `skipped`. A timeout records
`exit_code: null`. The result file is written atomically with mode `0600`.

## Limits

The runner reads the raw cgroup files it can see: cgroup v2 `cpu.max`,
`memory.max`, and `pids.max`, with cgroup v1 fallbacks for CPU, memory, and
pids. Every limit it cannot read is reported as `unverified` with the literal
value `"unverified"`. Observed values are recorded as text; the runner does not
interpret or enforce them.

`BEE_CI_CGROUP_ROOT` overrides the cgroup root (default `/sys/fs/cgroup`) and is
used by tests to exercise the unverified path.

## What this runner cannot verify today

- Network isolation, egress rules, DNS behavior, or connectivity. The result
  always says `unverified`; requests that require network isolation are
  refused before any command runs.
- Container identity, image digest, runtime, namespaces, capabilities, seccomp,
  AppArmor, or that the launcher's isolation is intact. The runner only
  inherits the environment it starts in and does not create or inspect a
  container.
- Filesystem isolation or mounts. The runner never mounts a host path and
  refuses manifests that ask for mounts.
- Credential access. The runner does not inspect credentials or describe the
  environment, but commands inherit the launcher environment and can read
  files available to them. Do not put secrets in manifest commands: commands
  are recorded verbatim in the result.
- CPU, memory, and pids limits that are not exposed as readable cgroup files,
  and whether an observed limit is actually enforced.
- Command output, artifacts, file integrity, and post-run workspace state.
  Output is not captured into the result manifest.
- Escaped descendants. A timeout kills the step's process group, but a
  process that deliberately detaches into a new session may survive.

## Tests

```sh
python -m pytest contrib/bee-ci/tests/test_linux_runner.py -q
```

The tests inject a fake command runner through `BEE_CI_TEST_MODE=1` and
`BEE_CI_TEST_COMMAND_RUNNER`; production runs use neither variable and execute
commands with `/bin/bash -c`.
