# bee-run CI: phase 1 shadow harness

This directory is a **phase 1 shadow harness**, not a CI service. It can store
bee results, verify a signed result, compare bee and GitHub Actions evidence for
the same commit, and render a local report. It does not post anything to GitHub,
does not create required checks, and does not gate a merge.

Read the limits before using it:

- Nothing in the phase 1 workflow writes to GitHub. `post_status.py` is dry-run
  by default, and its command-line `--live` path still refuses to post because
  the CLI never supplies a transport. A library caller could inject a transport
  and a token, but phase 1 does not use that branch.
- Nothing here configures branch protection, rulesets, required checks or
  workflow files. A green report is evidence for a human, not a merge gate.
- There is no single orchestrator. The stages are separate modules and CLIs;
  some hand-off data has to be assembled by the operator. The gaps are listed
  below rather than hidden behind a command that does not exist.
- A self-reported `status`, a successful dispatch, a compare "agreement" or a
  green HTML row is **not** a verified pass. Only `verify_result.py` can certify
  a run as a verified pass, and it can only do so for a correctly signed result
  whose head, job and every step exit code match the dispatch.

## Layout

```text
contrib/bee-ci/
  manifest.py                 job-manifest loader and bee eligibility
  poll.py                     PR-head poller and launcher queue adapter
  dispatch.py                 launcher submission for one or more work items
  verify_result.py            fail-closed signed-result verifier
  post_status.py              commit-status builder, dry-run only in phase 1
  compare.py                  bee vs GitHub Actions comparison
  evidence.py                 frozen bee-ci/evidence/v1 index store
  report/
    render.py                 static HTML renderer for the evidence index
    template.html             bundled dark-mode template
  schema/ci-job.schema.json   schema for jobs/*.yaml
  jobs/                       one dispatch manifest per repository
  runners/linux/run.sh        Linux job runner used inside a bee container
  runners/windows/            Windows wrapper stub, not wired into CI
  tests/                      offline contract tests
```

There is no `__init__.py`. These are top-level modules. Run the scripts from the
repository root, or set `PYTHONPATH=contrib/bee-ci` when importing them from
Python.

## Modules

| Module | Reads | Used by | Entry point |
| --- | --- | --- | --- |
| `manifest.py` | `jobs/*.yaml` and the schema | `dispatch.py` | none |
| `poll.py` | GitHub PRs and launcher status | standalone | `python3 contrib/bee-ci/poll.py` |
| `dispatch.py` | manifest and launcher API | standalone library | none |
| `verify_result.py` | signed result JSON | `post_status.py` | `python3 contrib/bee-ci/verify_result.py` |
| `post_status.py` | `verify_result` output | standalone | `python3 contrib/bee-ci/post_status.py` |
| `compare.py` | bee and Actions JSON | standalone | `python3 contrib/bee-ci/compare.py` |
| `evidence.py` | evidence index | report renderer reads its document | none |
| `report/render.py` | evidence index and template | standalone | `python3 contrib/bee-ci/report/render.py` |

Among these modules, only two Python import edges exist: `dispatch.py`
optionally imports `manifest.py`, and `post_status.py` imports
`verify_result.py`.
Everything else is joined by files or by an operator running the next CLI. The
report renderer reads the evidence document but does not import `evidence.py`.

### `manifest.py`: what work is allowed

Loads `jobs/<repo>.yaml` through `schema/ci-job.schema.json` and adds semantic
checks the schema cannot express:

- The repository must be one of `workflow`, `bundlebees`, `orbitdesktop`,
  `hyvv`; the manifest's `repo` field must match the file name.
- Job names must be unique.
- A `runner: bee` leg must be Linux (`ubuntu-*`) and `arch: x64`.
- A macOS or arm64 leg must be `github-only`. The schema also encodes this, so a
  hand edit cannot silently make an arm64 leg bee-eligible.
- `is_bee_eligible()` is fail-closed: missing, unknown, macOS or arm64 data
  returns `False` even if a job object carries `runner: bee`.

The YAML files are written in the JSON-compatible subset of YAML and are parsed
with `json`, so the loader needs the standard library plus `jsonschema`. There
is no CLI. `dispatch.py` is the only module in this tree that imports it, and
only for `work_items_for_repo()`.

### `jobs/*.yaml`: dispatch declarations, not runnable scripts

Each file declares five CI legs: three Linux x64 bee legs and two
`github-only` legs (macOS and arm64).

| Repository | Bee-declared legs | GitHub-only legs |
| --- | --- | --- |
| `workflow` | `reference`, `acceptance-light`, `secret-scan` | `macos-docs`, `arm64-smoke` |
| `bundlebees` | `plugin-tests`, `js-tests`, `verify-sandbox` | `macos-plugin`, `arm64-plugin` |
| `orbitdesktop` | `unit`, `browser-e2e`, `python-launcher` | `macos-desktop`, `arm64-desktop` |
| `hyvv` | `lint`, `unit`, `browser-e2e` | `macos-unit`, `arm64-unit` |

These files declare **eligibility**, not commands. They contain no `run` steps.
A bee-capable leg still needs a runner job manifest (see the runner section) with
the actual commands. The `python`, `node` and `browser` fields are declarations;
the Linux runner does not install or verify any of them. It uses whatever the
container image already has.

Two declarations are ahead of the current capability:
`acceptance-light` (cold-start acceptance) and `secret-scan` (gitleaks) are
marked `runner: bee` in `jobs/workflow.yaml`, but neither is bee-runnable today.
Treat them as GitHub Actions legs and do not dispatch them to a bee.

### `poll.py`: find new PR heads and queue or dispatch them

Designed to run from cron, it lists open pull requests for each configured
`owner/name` repo and treats each head SHA as one work item exactly once. Drafts,
closed PRs and merged PRs are skipped. Seen heads are stored in a JSON state file
with an exclusive `flock` and atomic replacement (mode `0600`). The state defaults
to `~/.local/state/bee-run/queued.json` and can be overridden with `BEE_CI_STATE`
or `--state`.

The launcher is injected. The default adapters are stdlib-only:

- `BEE_CI_LAUNCHER_URL` selects an HTTP adapter that calls `GET /status` and
  `POST /dispatch` on that configured base URL.
- `BEE_CI_LAUNCHER_STATUS_CMD` / `BEE_CI_LAUNCHER_DISPATCH_CMD` select command
  adapters split with `shlex` and run without a shell.
- With neither configured, `UnconfiguredLauncher` raises; the poll records that
  the launcher is unavailable and leaves items queued.
- `--cap` defaults to the launcher's reported capacity, then `BEE_CI_CAP`, then
  `3`. Dispatch happens only when the launcher is available and its active count
  is below the cap.
- A dispatch failure returns the item to `queued`, records the error type, and
  raises. An item left in `dispatching` is reported as `stuck` on the next run.

CLI:

```sh
python3 contrib/bee-ci/poll.py \
  --state /tmp/bee-ci-poll.json \
  --repo owner/name \
  --cap 0
```

`--cap 0` is the safe no-dispatch rehearsal: it polls GitHub and writes queue
state but dispatches nothing. It still makes a read-only GitHub request and
writes the state file. Real dispatch requires launcher configuration and a
token in the environment; never print either.

Two integration facts matter:

- `poll.py` does not import `manifest.py` or `dispatch.py`. Its item is
  `{repo, pr, head_sha, title, url}` with **no job field**, sent to its own
  launcher adapter (`POST /dispatch` for the HTTP adapter). `dispatch.py`
  requires a job and posts to `/v1/dispatch`. The two launcher protocols are not
  the same. Do not assume `poll.py` performs manifest expansion or uses
  `dispatch.py`.
- `poll.py`'s built-in repository list is not the four repositories in
  `manifest.REPOS`, and its entries are `owner/name` values while manifest keys
  are bare names. Running it without `--repo` polls a different list, and those
  items cannot be passed to `manifest.load_repo()` unchanged. Always pass
  `--repo` and keep the two lists aligned.

### `dispatch.py`: submit work items to the launcher

Turns a `(repo, head_sha, job)` work item into one launcher request. It is a
library, not a CLI.

- `WorkItem` is immutable and can be built from an object, a tuple or
  `from_dict`.
- Every submission mints a fresh `task_id` from the job name, process id, a
  process-local counter and a UUID. Reusing a job name as the id would let one
  parallel dispatch supersede another.
- The launcher token is read from `BEE_CI_LAUNCHER_TOKEN`,
  `BEE_LAUNCHER_TOKEN` or `LAUNCHER_TOKEN`, and only from the environment. It is
  placed in the `Authorization` header and nowhere else. Error messages are
  reduced to fixed, scrubbed text.
- The default HTTP transport posts to `BEE_CI_LAUNCHER_URL/v1/dispatch`.
- `dispatch()` returns a `DispatchResult` whose `state` is `success` or `error`.
  **A success here means the launcher accepted the submission. It does not mean
  the job passed.** Timeouts, HTTP errors, unreadable responses and launcher
  error states all become `error`, never `success`.
- `work_items_for_repo(repo, head_sha)` loads the manifest and returns only
  `is_bee_eligible()` jobs. `dispatch_repo()` is the convenience wrapper. Both
  need `jsonschema`; without it the manifest helper raises
  `manifest_unavailable`.

There is no dry-run flag. Calling it without a token returns a `missing_token`
error before any network call, which is a safe way to inspect the shape:

```sh
PYTHONPATH=contrib/bee-ci python3 - <<'PY'
from dispatch import WorkItem, dispatch

result = dispatch(WorkItem("workflow", "0" * 40, "reference"), env={})
print(result["state"], result["code"], result["error"])
PY
```

### `verify_result.py`: the only success gate

Verifies a result JSON object with `job_id`, `head_sha` and a non-empty `steps`
list. The signature is HMAC-SHA256 over canonical JSON (sorted keys, compact
separators, ASCII), excluding the `signature` field. The same scheme is used
for signed acceptance reports.

`verify_result()` returns `success` only when all of these hold:

1. The key is non-empty and the signature is present and valid.
2. The recorded `job_id` equals the expected dispatched job id.
3. The recorded `head_sha` equals the expected head (case-insensitive on hex).
4. `steps` is a non-empty list.
5. Every step is an object with an integer `exit_code` of exactly `0`.

Everything else is `error` or `failure`:

- missing key, missing signature, malformed object, missing job/head/steps:
  `error`;
- valid signature but job/head mismatch, a malformed step, a non-integer exit
  code, or any non-zero exit code: `failure`;
- an unexpected exception: `error`, with only the exception type in the reason.

The verifier does **not** inspect the runner's `status`, `reason`, `limits` or
`isolation` fields. It trusts the recorded step exit codes. That has two
consequences:

- A skipped or timed-out step must be recorded with `exit_code: null` (as the
  Linux runner does). The verifier rejects null, so a skipped test is a failure,
  never a pass. Never coerce a skipped step to `0` to make a result verify.
- A runner result whose own `status` says `failed` but whose every recorded
  exit code is `0` would still verify as success. Do not use `status` as the
  gate; use `verify_result` and review the steps.

CLI:

```sh
python3 contrib/bee-ci/verify_result.py RESULT.json \
  --expected-head "$HEAD" \
  --expected-job reference \
  --key-file /path/to/result-key
```

The key comes from `--key-file` when given, otherwise from the environment
variable named by `--key-env` (default `BEE_CI_RESULT_KEY`). Exit status is `0`
for success, `1` for a verified failure, and `2` for an error or unreadable
input. The CLI prints one JSON object with `ok`, `status`, `code` and `reason`.

A valid signature proves that the signer held the key and that the body has not
changed since signing. It does not prove that the commands actually ran. Keep
the key out of job manifests and command lines, and pair verification with
review of the retrieved diff.

### `post_status.py`: build a commit status, dry-run by default

Builds a GitHub commit-status record with context `bee-ci/<job>` and state
`success`, `failure` or `error`. It sanitizes both the description and the
target URL:

- `target_url` is kept only if it is a public `https` URL. Private hosts,
  tailnet names, IP addresses, credentials in URLs and non-HTTPS URLs are
  dropped, not rewritten.
- The description drops credentials embedded in URLs, IP addresses, private
  hosts and tailnet names, collapses whitespace and is truncated to 140
  characters.
- The token is read only from `BEE_CI_GITHUB_TOKEN` or `GITHUB_TOKEN` and is
  never placed in the record.

The CLI verifies the result first, then calls `post_status`:

```sh
python3 contrib/bee-ci/post_status.py RESULT.json \
  --expected-head "$HEAD" \
  --expected-job reference \
  --key-file /path/to/result-key
```

It prints the record with `"dry_run": true` and `"posted": false`, and exits
`0`/`1`/`2` for success/failure/error. No GitHub token is needed for the dry
run. The `--live` flag exists, but it still fails closed because the CLI does
not inject a transport; a library caller is the only way to reach the posting
branch, and must supply both a token and a transport. Phase 1 does not use that
branch.

`post_status` itself does **not** verify. It accepts a verification result and
copies its status. The CLI wires `verify_result` first. If you call the library
directly, pass a real `VerificationResult`; do not construct
`{"status": "success"}` from an unverified source.

### `compare.py`: bee versus GitHub Actions for the same exact SHA

Reads two JSON inputs and writes a deterministic report of agreements and
disagreements. It is local only and has no GitHub client.

Expected bee input:

```json
{"records": [{"sha": "<full sha>", "job": "unit", "state": "passed", "exit_code": 0}]}
```

Expected Actions input:

```json
{"records": [{"sha": "<full sha>", "job": "unit", "conclusion": "success"}]}
```

A bare JSON list of records is also accepted. `state` and `conclusion` are
classified as passed/failed/unknown; a bee record whose `state` and `exit_code`
contradict each other becomes `unknown`/`contradictory`, not a pass. Missing
sides are `disagree` with `missing-bee` or `missing-actions`; unknown values and
contradictions are `inconclusive`. None of those is counted as a pass.

SHA matching is exact after lowercasing; abbreviations are never expanded. The
code does not length-check the SHA, so a short SHA is accepted as a distinct key
and usually produces a missing-side row. Always pass full 40-hex heads.

CLI:

```sh
python3 contrib/bee-ci/compare.py \
  --bee bee.json \
  --actions actions.json \
  --out compare.json \
  --markdown compare.md \
  --fail-on-disagreement
```

The JSON report has `schema_version: 1`, `tool: bee-ci-shadow-compare`, a
summary and sorted rows. It contains no timestamps, so repeated runs over the
same inputs are byte-identical. `--fail-on-disagreement` exits `1` when any
disagreement, missing side or inconclusive row exists.

`compare.py` does **not** verify signatures. It classifies whatever records it
is given. A `state: passed` row is only meaningful if that result was separately
verified with `verify_result.py`.

### `evidence.py`: the frozen evidence index

Stores the `bee-ci/evidence/v1` document consumed by the report renderer. There
is no CLI.

```json
{
  "schema": "bee-ci/evidence/v1",
  "runs": [
    {
      "repo": "workflow",
      "head_sha": "<40 hex>",
      "job": "reference",
      "source": "bee",
      "state": "success",
      "exit_codes": [{"step": "tests", "exit_code": 0}],
      "started_at": "2026-11-13T00:00:00Z",
      "finished_at": "2026-11-13T00:00:01Z",
      "result_path": "evidence/workflow/<sha>/reference-bee.json"
    }
  ]
}
```

The contract is frozen at exactly these nine run fields:

| Field | Allowed value |
| --- | --- |
| `repo` | `workflow`, `bundlebees`, `orbitdesktop` or `hyvv` |
| `head_sha` | 40 hexadecimal characters |
| `job` | non-empty string |
| `source` | `bee` or `github` |
| `state` | `success`, `failure`, `error` or `pending` |
| `exit_codes` | `null` or a list of `{"step": string|null, "exit_code": int|null}` |
| `started_at` | `null` or ISO-8601 UTC ending in `Z` |
| `finished_at` | `null` or ISO-8601 UTC ending in `Z` |
| `result_path` | `null` or non-empty string |

There is no `schema_version` field inside a run; the version is the top-level
`schema`. The top-level object must contain exactly `schema` and `runs`. Extra or
missing run keys are rejected by `evidence.load()`.

Writes are atomic. `append()` deduplicates on
`(repo, head_sha, job, source)` and returns `False` for a duplicate. The first
record wins: a later record with the same key but a different state is ignored,
not used to update the index. This is append-only evidence, not a live status
table.

Two enforcement gaps to know:

- `append()` normalizes unknown or malformed `repo`, `head_sha`, `job` and
  `source` values to `null` instead of rejecting the write. `evidence.load()`
  accepts those nulls because it only validates non-null values. `render()`
  later refuses a run with a null or missing required string, so an index that
  loads cleanly is not automatically renderable.
- `render()` requires `repo`, `head_sha`, `job`, `source` and `state` to be
  non-empty strings, but it does not enforce the state enum or timestamps. Use
  `evidence.load()` to validate the frozen contract before rendering.

### `report/render.py`: one static HTML page

Consumes a `bee-ci/evidence/v1` document and writes plain HTML with no
JavaScript, no network access and no server. It sorts runs by repo, head, job,
source and original order, so the page is deterministic.

A bee-only or github-only run appears in the `DISAGREEMENT` section with a
`missing` badge on the absent side; it is never treated as a pass. Two sources
with different states, two different states for one source, or a missing side
are all listed there. Text and attributes are HTML-escaped and redacted for
tokens, credentials, URLs, private hosts, tailnet names, `localhost` and IP
addresses before output.

CLI:

```sh
python3 contrib/bee-ci/report/render.py evidence/index.json --out report.html
```

`--template` overrides the bundled `template.html`. The renderer is
presentation only; it does not verify results or validate the state enum.

## Runners

`runners/linux/run.sh JOB_MANIFEST RESULT_MANIFEST` runs commands in the current
environment inside the bee container. It does not create a container, does not
require Docker, does not mount host paths and does not install tools. It runs
each step with `/bin/bash -c`, stops at the first failure or timeout, and records
later steps as `skipped` with `exit_code: null`. The result file is written
atomically with mode `0600`.

A runner job manifest is different from a `jobs/*.yaml` dispatch manifest:

```json
{
  "job_id": "reference",
  "timeout_s": 600,
  "steps": [
    {"id": "demo", "run": "python3 reference/run_demo.py"},
    {"id": "tests", "run": "python3 -m unittest discover -s reference/tests -v"}
  ]
}
```

The runner refuses manifests that ask for mounts, volumes, secrets or
credentials, and refuses a manifest that requires network isolation. It reports
network isolation as `unverified`, never as measured, and reports unreadable
cgroup limits as `unverified`. Commands are recorded verbatim in the result, so
never put a secret in a step. Command output is not captured into the result.

`runners/windows/run-job.ps1` is a stub for a future native Windows bee. There
are no native Windows bees and this wrapper is not wired into CI. Its README
lists the Windows execution checks that were not run.

## Shadow pass in dry-run

A shadow pass means: run the bee side, obtain the GitHub Actions conclusions for
the same exact head SHA, compare them locally, and render the evidence. "Dry
run" here means no GitHub writes and no required checks. It can still run real
commands in a local checkout.

There is no checked-in orchestrator that performs every step. The walkthrough
below is runnable with this repository's own `reference` leg. For another
project, copy that leg's commands from that project's CI definition into the
runner manifest; the `jobs/*.yaml` files do not contain them.

To exercise the launcher path instead of running the Linux runner directly,
build per-leg work items with `dispatch.work_items_for_repo(repo, head_sha)` and
submit them with `dispatch.dispatch_repo(repo, head_sha, ...)`. That path has no
CLI. A dispatch success still means only that the launcher accepted the work;
the result must come back through verification and comparison as below.

### 0. Prerequisites

Python 3.10 or newer is enough for the verifier, poster, comparator, evidence
store and renderer. `manifest.py` and the manifest tests additionally need
`jsonschema`; the test suite needs `pytest`.

```sh
python3 -m venv /tmp/bee-ci-venv
/tmp/bee-ci-venv/bin/pip install pytest jsonschema
```

Use the venv's Python for the manifest tests. The standalone CLIs below use only
the standard library and can run with the system `python3`.

### 1. Check the harness offline

```sh
/tmp/bee-ci-venv/bin/python -m pytest contrib/bee-ci/tests -q
```

This runs the offline contract tests. The Windows runner test that needs a real
Windows host is skipped; a plan-only test also skips when no PowerShell binary
is installed.

### 2. Run one leg in a scratch directory

```sh
export SHADOW=/tmp/bee-ci-shadow
mkdir -p "$SHADOW"
export HEAD=$(git rev-parse HEAD)   # read-only; for a real shadow use the PR head

cat > "$SHADOW/job.json" <<'JSON'
{
  "job_id": "reference",
  "timeout_s": 600,
  "steps": [
    {"id": "demo", "run": "python3 reference/run_demo.py"},
    {"id": "tests", "run": "python3 -m unittest discover -s reference/tests -v"}
  ]
}
JSON

contrib/bee-ci/runners/linux/run.sh "$SHADOW/job.json" "$SHADOW/result.json"
```

The runner exits `0` for a pass and writes `result.json` either way. This is a
smoke test of the Linux runner and the reference commands; it is not yet a
signed result. For a real shadow, run the leg in a checkout of the PR head and
keep that exact SHA as `HEAD`.

### 3. Bind the head and sign

The Linux runner does not record `head_sha` and does not sign. The harness that
invokes it must add the head and sign the body. This local script creates a
throwaway key if one does not exist and writes `result.signed.json`:

```sh
python3 - "$SHADOW" "$HEAD" <<'PY'
import json, secrets, sys
from pathlib import Path
sys.path.insert(0, "contrib/bee-ci")
from verify_result import sign_payload

out, head = Path(sys.argv[1]), sys.argv[2]
key_file = out / "result.key"
if not key_file.exists():
    key_file.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
    key_file.chmod(0o600)
key = key_file.read_text(encoding="utf-8").strip()
result = json.loads((out / "result.json").read_text(encoding="utf-8"))
result["head_sha"] = head
result["signature"] = sign_payload(result, key)
(out / "result.signed.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
```

This throwaway key proves only that the envelope is internally consistent. It is
not evidence that a real signer produced the result. For a real shadow, use the
coordinator-held key file and do not put the key on a command line or in a
manifest.

### 4. Verify before calling anything a pass

```sh
python3 contrib/bee-ci/verify_result.py "$SHADOW/result.signed.json" \
  --expected-head "$HEAD" \
  --expected-job reference \
  --key-file "$SHADOW/result.key"
```

Expect a JSON line with `"status": "success"` and `"code": "proven"` for the
reference demo. If a step failed, timed out or was skipped, the status is
`failure` or `error`; do not continue as if it passed.

### 5. Dry-run the status record

```sh
python3 contrib/bee-ci/post_status.py "$SHADOW/result.signed.json" \
  --expected-head "$HEAD" \
  --expected-job reference \
  --key-file "$SHADOW/result.key"
```

The output contains `"dry_run": true` and `"posted": false`. Nothing is sent to
GitHub, and no token is read in this mode. Do not add `--live`; in phase 1 the
CLI would still refuse because it has no injected transport.

### 6. Compare with GitHub Actions conclusions

Write the bee and Actions records for the same full SHA. The bee `state` below
is legitimate only because step 4 returned success; if it did not, write the
failure or leave the record out.

```sh
cat > "$SHADOW/bee.json" <<JSON
{"records": [{"sha": "$HEAD", "job": "reference", "state": "passed", "exit_code": 0}]}
JSON

cat > "$SHADOW/actions.json" <<JSON
{"records": [{"sha": "$HEAD", "job": "reference", "conclusion": "success"}]}
JSON

python3 contrib/bee-ci/compare.py \
  --bee "$SHADOW/bee.json" \
  --actions "$SHADOW/actions.json" \
  --out "$SHADOW/compare.json" \
  --markdown "$SHADOW/compare.md"
```

In a real shadow, `actions.json` comes from the GitHub Actions conclusions for
that exact SHA. There is no checked-in Actions API collector, so this file is
assembled by the operator. `compare.py` does not verify the bee record; the
signature check in step 4 is what makes the bee side evidence.

### 7. Build and render an evidence index

Write one bee run and one github run for the same repo/head/job. The index must
use the frozen nine-field contract.

```sh
cat > "$SHADOW/index.json" <<JSON
{
  "schema": "bee-ci/evidence/v1",
  "runs": [
    {
      "repo": "workflow",
      "head_sha": "$HEAD",
      "job": "reference",
      "source": "bee",
      "state": "success",
      "exit_codes": [{"step": "demo", "exit_code": 0}, {"step": "tests", "exit_code": 0}],
      "started_at": "2026-11-13T00:00:00Z",
      "finished_at": "2026-11-13T00:00:01Z",
      "result_path": "result.signed.json"
    },
    {
      "repo": "workflow",
      "head_sha": "$HEAD",
      "job": "reference",
      "source": "github",
      "state": "success",
      "exit_codes": null,
      "started_at": "2026-11-13T00:00:00Z",
      "finished_at": "2026-11-13T00:00:01Z",
      "result_path": null
    }
  ]
}
JSON

PYTHONPATH=contrib/bee-ci python3 -c \
  'import evidence, sys; evidence.load(sys.argv[1])' "$SHADOW/index.json"

python3 contrib/bee-ci/report/render.py "$SHADOW/index.json" \
  --out "$SHADOW/report.html"
```

`evidence.load(...)` is the contract check. The renderer does not verify results;
it only displays the index. The `state: success` on the bee row is legitimate
only because step 4 verified it. A missing side is rendered as `missing`, not as
a pass.

There is no checked-in runner-result-to-evidence adapter. `evidence.append()`
can write a record from Python, but the operator or a small harness must supply
the mapping and the verified state.

### What this walkthrough does not prove

- It does not prove that GitHub Actions reached the same result; you supplied
  the Actions conclusions.
- It does not prove that a real bee ran the commands unless the result was
  signed with the real coordinator key and the head is the real PR head.
- It does not prove container isolation, network isolation, resource limits or
  that the declared Python/Node/browser versions were present. The Linux runner
  reports what it can read and marks the rest `unverified`.
- A throwaway key makes an internally consistent test envelope, not a trusted
  result.

## Fail-closed rules

These are the rules the code implements, and the rules an operator must keep:

1. **No verified result, no success.** A result becomes `success` only through
   `verify_result` with a valid signature, the expected head, the expected job
   and every step exit code exactly `0`.
2. **Skipped is not passed.** The Linux runner records a skipped or timed-out
   step with `exit_code: null`; the verifier rejects that. Do not rewrite a
   skipped step as `0`, and do not treat a runner `status` as a pass.
3. **Dispatch success is not job success.** `DispatchResult.state == "success"`
   means the launcher accepted the submission. It says nothing about the test
   outcome.
4. **Comparison is not verification.** `compare.py` classifies inputs. Missing
   sides, unknown states and contradictory bee records are disagreements or
   inconclusive, never passes. It does not check signatures.
5. **Rendering is not verification.** `report/render.py` shows `missing` for an
   absent side. No green row overrides a failed verifier.
6. **Unverified input becomes error, not success.** `post_status` maps any
   verification status outside `success`/`failure`/`error` to `error`, and
   `verify_result` maps missing keys, missing signatures, malformed input and
   unexpected exceptions to `error`.
7. **Launcher failures are errors.** Dispatch timeouts, HTTP errors, unreadable
   responses and launcher-reported errors never become success. A poll dispatch
   failure puts the item back in `queued` and raises; a stuck `dispatching`
   record is reported as `stuck`.
8. **First evidence record wins.** `evidence.append()` ignores a duplicate key,
   including one with a different state. A retry cannot silently overwrite an
   earlier record; treat the index as append-only evidence.

## Operational facts for the coordinator

### Bees never commit; the coordinator commits

A bee must leave its work in the working tree. The launcher builds the change it
retrieves with `git add -A && git diff --cached HEAD`. That is the launcher's
command, not a command for the bee to run. Anything committed moves `HEAD`, and
the change disappears from that diff; anything checked out, reset or stashed can
discard it.

- Do not run `git commit`, `git push`, `git checkout`, `git reset`, `git stash`
  or any other command that moves `HEAD` in a bee container.
- Keep edits inside the leased files. Delete `.pytest_cache`, `__pycache__` and
  other generated files before finishing; `git add -A` will include untracked
  non-ignored files.
- The coordinator retrieves the diff, reviews it, and commits from that diff.
  The bee does not own the commit, branch, PR, merge, tag, release or deploy.
- Phase 1 performs no merge, tag, release, publish, deploy, force-push, branch
  deletion or history rewrite. A shadow report is not authorization for any of
  them.

This is also why a bee cannot "fix" a bad result by committing a new state: the
retrieved artifact is the diff, and the result must be verified separately.

### Cold-start acceptance and gitleaks are not bee-runnable yet

Both are GitHub Actions jobs today:

| Leg | Why it cannot run in a bee yet |
| --- | --- |
| cold-start acceptance (`acceptance-light`) | The GitHub job installs `bubblewrap` and uses `sudo sysctl` to lift an AppArmor restriction on unprivileged user namespaces. The Linux runner has no supported way to install that tooling or change host sysctls; it only runs commands in the environment it is given. |
| gitleaks (`secret-scan`) | The GitHub job downloads a specific gitleaks release and scans full history with `fetch-depth: 0`. Nothing under `contrib/bee-ci` installs gitleaks, the runner does not install tools, and a bee checkout is not guaranteed to include full history. |

The `jobs/workflow.yaml` file currently marks both legs `runner: bee`. Treat that
as a target, not a capability. Keep both legs on GitHub Actions, do not dispatch
them to a bee, and do not record a bee `success` for either. `acceptance-light`
and `secret-scan` in a shadow report should come from the `github` source only
until the image and runner can actually satisfy them.

### Manifest declarations are not installed tools

`jobs/*.yaml` declares Python, Node and browser needs, but the Linux runner runs
in whatever image the launcher provides. It does not install Python, Node,
Chromium, Firefox or WebKit. The `orbitdesktop` and `hyvv` `browser-e2e` legs
declare `browser: chromium`; do not claim one ran unless the image is known to
provide it. The same applies to `python` and `node` version declarations.

### Polling state and capacity

- The state file is a dedupe record, not a source of truth about the forge. If
  it is lost, previously seen heads can be dispatched again.
- `--cap 0` is the no-dispatch rehearsal. A positive cap only dispatches when
  the launcher reports an active count below the cap.
- A `dispatching` record left behind by an interrupted run is reported as
  `stuck`; inspect the launcher and the state file rather than redispatching
  blindly.
- `poll.py` does not expand a manifest. If you need per-leg work items, build
  them with `dispatch.work_items_for_repo()` or an equivalent coordinator step.

### Secrets and redaction

- Launcher tokens are read from the environment only and scrubbed from dispatch
  errors. GitHub tokens are read from the environment only and never placed in a
  status record.
- `post_status` drops unsafe target URLs and redacts descriptions; the report
  renderer redacts tokens, credentials, URLs, private hosts, tailnet names and
  IP addresses.
- Redaction is defence in depth, not permission to put secrets in a command. The
  Linux runner records every step command verbatim in its result. Do not put
  tokens, keys or private hostnames in a job manifest or a command line.
- Never print, commit or paste environment variables, keys, private hosts,
  tailnet names or internal URLs into a report, an issue or this README.

## Testing

The full bee-ci suite is run with:

```sh
python3 -m pytest contrib/bee-ci/tests -q
```

It needs `pytest` and `jsonschema`. The tests are offline: they inject fake
GitHub, launcher and command runners. The Windows runner tests skip execution
checks that require a real Windows host; a plan-only test also skips when no
PowerShell binary is installed. A passing test run does not prove a bee ran a
real job.

## Known gaps (phase 1)

- No single command runs poll -> dispatch -> runner -> verify -> compare ->
  evidence -> report. The stages are separate.
- No GitHub Actions conclusions collector. `actions.json` is supplied by the
  operator.
- No runner-result-to-evidence or runner-result-to-compare adapter. The signed
  result is verified separately, and the comparison/evidence records are
  assembled by the operator.
- No live commit-status or check-run poster. `post_status.py` is dry-run only in
  practice; its live branch needs an injected transport that the CLI never
  provides.
- No required checks, branch protection or ruleset changes. This directory does
  not gate merges.
- No container creation, mount support, secret injection, artifact upload or
  network-isolation proof.
- No macOS or arm64 bee execution. Those legs are `github-only` by schema and
  loader.
- No cold-start or gitleaks execution in bees.
- No automatic evidence updates: the index is append-only and first-write-wins.
- No verification inside `compare.py`, `post_status.py`'s library entry point,
  `evidence.py` or the renderer. Verification is a separate gate that the caller
  must run first.

## Related documents

- [Cold-start acceptance](../../acceptance/README.md)
- [Coordinator playbook](../../docs/19-coordinator-playbook.md)
- [Bundlebees hardening](../../docs/13-bundlebees-hardening.md)
- [Reference demo](../../reference/README.md)
- [Linux runner README](runners/linux/README.md)
- [Windows runner README](runners/windows/README.md)
