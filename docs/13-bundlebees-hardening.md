# 13 — Bundlebees hardening

This chapter describes the verifier and contract hardening that now lives on [bundlebees](https://github.com/mojomast/bundlebees) `main`. It closes the review gap left in [12](12-three-layer-architecture.md) and [03](03-development-and-orchestration.md), which previously said this work was still in a separate pull request.

The unit of progress is an accepted artifact with evidence, and every guarantee below is enforced in the coordinator, independent of which agent produced the work.

## Status (Nov 12, 2026, America/Toronto)

| Item | State |
|---|---|
| Code | On `main` at [`c10aa42`](https://github.com/mojomast/bundlebees/commit/c10aa42eb90298460b8e2db1d7aba54e4688138f) **(verified)**: hardening from PR #3 plus the strong-sandbox fix and CI from PR #4 |
| Pull requests | [PR #3](https://github.com/mojomast/bundlebees/pull/3) merged Nov 12, 11:54 AM ET; [PR #4](https://github.com/mojomast/bundlebees/pull/4) merged Nov 12, 12:36 PM ET **(verified)** |
| ACDD + TDD | Contract validation, TDD evidence and contract-aware verify are on the `feat/acdd-tdd` branch, under review, **not merged**; see [16](16-acdd-tdd.md) |
| Release | **Not tagged.** [v0.1.1](https://github.com/mojomast/bundlebees/releases/tag/v0.1.1) remains the latest release. The CHANGELOG lists this work as **0.2.0, unreleased** |
| Catalog | [#153888](https://github.com/NousResearch/hermes-agent/pull/153888) was still open and still pointed at the v0.1.1 line when checked |
| Live baseline | The plugin can now write a metrics log; those figures are not yet a measured baseline from live orchestrations |

This repository does not tag or release bundlebees. Upstream docs for implementers are the plugin [README](https://github.com/mojomast/bundlebees/blob/c10aa42eb90298460b8e2db1d7aba54e4688138f/README.md) and [docs/ADAPTERS.md](https://github.com/mojomast/bundlebees/blob/c10aa42eb90298460b8e2db1d7aba54e4688138f/docs/ADAPTERS.md).

The historical bees path — Cua sandboxes on Kyle's PC, `verify.sh` on the box, Orbit as the transport — is still in [03](03-development-and-orchestration.md). That path is one implementation. The contracts below are what the plugin now enforces when you run its own verify and integrate commands.

## 1. Sandboxed verify

`hermes bundlebees verify` no longer runs worker tests in the coordinator worktree. It copies the worktree (without `.git`) to a temporary directory and runs the named tests there. The environment is rebuilt from scratch: no coordinator credentials, no SSH agent, an empty `HOME`. Only evidence comes back (backend, exit code, junit counts, an output tail, diff stats).

Isolation backends. `auto` picks bubblewrap, then firejail, and nothing else:

| Backend | What it provides |
|---|---|
| **bubblewrap** (`bwrap`) | Preferred. `--unshare-all`, unprivileged uid 65534, no network, only `/usr`, the Python install and the copy mounted; host home and `/tmp` hidden |
| **firejail** | `--net=none --private` |
| **unshare** | `--user --net --pid`. Weak: network and PID isolation only; the coordinator's filesystem stays readable. **Never auto-selected** (see below) |

**Weak backend needs an explicit opt-in ([PR #4](https://github.com/mojomast/bundlebees/pull/4), merged Nov 12):** after an external review flagged that `unshare` does not hide the coordinator's files, `auto` picks only bubblewrap or firejail. `unshare` runs only when `verify_isolation: unshare` is set *and* the documented-unsafe override `verify_allow_weak_unshare` (or `BUNDLEBEES_ALLOW_WEAK_UNSHARE=1`) is on; otherwise verify fails closed. PR #4 also added CI (tests under bubblewrap, plugin doctor, gitleaks).

With no backend, verify and integrate **fail closed** (`sandbox_unavailable`). The only way around that is the clearly labelled setting `verify_allow_unsafe_local` (default `false`), which still uses a temp copy and a scrubbed environment but runs as the same user with the network on. Use it only on a disposable single-user machine with no credentials; `hermes bundlebees doctor` warns when it is in effect.

`verify_isolation` can pin `auto`, `bwrap`, `firejail` or (with the override) `unshare`. `verify_timeout_s` (default 900) is the wall-clock limit for one sandboxed run.

## 2. Strict brief schema

A brief is validated in `bundlebees_plugin/brief.py` against `brief.schema.json` **before** any launcher call. Required fields:

- `objective`
- `source_rev` — a full 40- or 64-character hex commit
- `assigned_files` — non-empty, repository-relative
- `acceptance` — a criteria list, or `{criteria, commands, tests}`

Optional: `branch`, `tests`, `run_id`, `wave`, `retry_of`. Dispatch records a signed lease for the attempt. The default model remains `deepseek-v4.1-flash`.

## 3. Immutable coordinator lease

File scope comes only from the coordinator, never from the worker's self-report.

At dispatch, `bundlebees_dispatch` writes `leases/<attempt_id>.json` under plugin data: created with `O_EXCL`, mode `0400`, HMAC-SHA256 signed with a `0600` key. Verify refuses a missing or edited lease (`lease_missing`, `lease_tampered`) and ignores — then reports — any scope the worker result claims. Branch and tests for verify come from the user or the lease, never from worker metadata.

The [reference demo](../reference/README.md) only illustrates this idea: its lease fingerprints are plain SHA-256 hashes stored next to the data, so anyone who can edit the store can recompute them. That is for teaching. Use the HMAC-signed bundlebees lease for real enforcement.

`hermes bundlebees lease <attempt_id> --brief <file>` records a lease for a brief that was dispatched outside the tool. It refuses to overwrite.

## 4. `source_rev` checks and the combined-branch suite

Verify requires all three:

1. The worker's declared base equals the brief's full `source_rev`.
2. The patch applies to that exact commit (checked in a temporary index).
3. The feature branch descends from it.

Failures have stable codes: `base_undeclared`, `base_mismatch`, `source_rev_missing`, `patch_not_at_source_rev`, `branch_diverged`. `main` and `master` are refused. A secret scan still runs before tests.

A wave is accepted only after `hermes bundlebees integrate --wave <id> --attempts …` sees an `ok` verify record (an ancestor of `HEAD`) for every slice, then runs the **full suite on the combined branch** in the sandbox. That writes `waves/<id>.json`. `bundlebees_attempt op=review accepted=true` returns `integration_required` until the attempt is in an accepted wave.

## 5. Metrics log and summary CLI

Outcomes are appended to a hash-chained JSONL log at `metrics/<run_id>.jsonl` (dispatch, verify, integrate, intervention, recovery). `hermes bundlebees metrics [--run <id>] [--json] [--note <text>]` summarizes:

- first-pass verification rate
- accepted changes
- tokens and cost per accepted change (when the worker reported them)
- human interventions
- plan-to-accepted time
- regressions found
- failed-worker recoveries

This is the production instrumentation that [12 §4](12-three-layer-architecture.md#4-measurement) asked for. It is **code on `main`**, not yet a measured baseline from live orchestrations. The [reference demo](../reference/README.md) still writes a miniature JSONL with synthetic cost units so the schema can be inspected offline.

## 6. WorkerBackend adapter contract

The contracts above never assume a specific agent, model or launcher (core modules are tested not to name one). A worker backend implements two calls:

```python
class WorkerBackend(Protocol):
    name: str
    def create(self, brief: dict, *, model: str,
               kanban_task_id: str | None = None) -> dict: ...
    def result(self, attempt_id: str) -> dict: ...
```

`normalize_result` reduces a runtime's output to a patch, a declared base, usage, and the checks the worker claims it ran. Everything else is dropped, including any lease or file list the worker reports. `untrusted` is always `true`.

Registered adapters:

| Adapter | State |
|---|---|
| `orbit-loopback` | **Default.** DeepSeek bees through the Orbit / Hermes launcher on loopback |
| `launcher` | Talks to a configured launcher endpoint (`direct` / `http` / `https` are aliases) |
| `opencode` | Documented stub: every operation raises `unsupported_adapter` |
| `codex` | Documented stub: same fail-closed behaviour |

How to implement a stub, and what must stay in the trusted coordinator, is in [docs/ADAPTERS.md](https://github.com/mojomast/bundlebees/blob/c10aa42eb90298460b8e2db1d7aba54e4688138f/docs/ADAPTERS.md). Networking is a transport under this contract, not a second API; see [14](14-networking-and-worker-deploy.md).

## What this does not change

- The model still does not apply a patch, run the suite, push a branch, merge, tag, force-push or deploy. Those stay user-run.
- Event bodies, logs and `worker_claims` remain untrusted text.
- Authorizing a new project on Kyle's PC launcher still requires his OK and a launcher restart, as in [03](03-development-and-orchestration.md).
- How a newcomer should reach a remote coordinator (pairing codes, tailcat, a public join URL) is planned work, documented in [14](14-networking-and-worker-deploy.md).
- Making Orbit itself runnable by anyone, with a first agent that can set up the rest, is in progress; see [15](15-agent-agnostic-and-orbit-start.md).
