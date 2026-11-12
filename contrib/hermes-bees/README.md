# Hermes bees (reference)

Windows/PowerShell reference for the bee pipeline that runs on one host: a local PC launcher, `bees.ps1` as the coordinator link, a beekeeper profile that dispatches work, and a verify bee whose claims are reports only.

This tree is a sanitized snapshot of the scripts that were live on 12 November 2026. It is not an installer, not a second source of truth for docs/ or CI, and it includes no key files. Paths and host-specific values in a live checkout must be replaced with local values.

The token and cost design lives in [OBSERVABILITY.md](OBSERVABILITY.md). That schema is draft v1 and freezes when observability slice 1 lands.

## Layout

- `scripts/bees.ps1` — the one small link between the box coordinator and the PC beekeeper. Verbs: `status`, `handoff`, `result`, `settle`, `usage`.
- `scripts/test-verify-for.ps1` — 26 checks: `VerifyFor` (leased-hash compare, telemetry extras, scope violations), lifecycle for `SettlePlan` / `ResultSummary`, and the Hermes CLI `--json` contract used by `SettleCard`, plus UTF-8 (no BOM) writes of `owned-cards.json`.
- `scripts/make-verify-brief.py` — renders the default verify-bee brief for a succeeded work bee.
- `scripts/templates/render_brief.py`, `scripts/templates/verify.md`, `scripts/templates/_house-rules.md` — brief templates. Commands are rewritten to `python3`.
- `scripts/bee-watch.py` and `scripts/test_bee_watch.py` — Hermes cron pre-check: a level-triggered reconcile that wakes the beekeeper when desired and actual state diverge, including short bees that finished between ticks. 11 unit tests. On the live host this file is kept under the beekeeper profile's `scripts/` directory, not next to `bees.ps1`.
- `scripts/beekeeper/beekeeper-guard.py` and `scripts/test_beekeeper_guard.py` — `pre_tool_call` harness guard that denies mid-run parks (`kanban_block` / `kanban_schedule` and the equivalent CLI) while a bee is in flight or waiting for verify. 9 unit tests. On the live host the guard lives under the profile's `agent-hooks/` directory; the hook snippet is in `profile/hooks.yaml`.
- `profile/SOUL.md` — sanitized rules sections from the live beekeeper profile.
- `skills/bee-verify/SKILL.md` — sanitized rules sections of the bee-verify skill, plus `skills/bee-verify/scripts/replay_verify.py` for a read-only VerifyFor replay when PowerShell cannot run.

Do not edit `docs/` chapters, the repository root `README.md`, the demo, `tools/`, or `.github/` from this contribution. Those belong to other workstreams.

## The PC launcher (docs only)

The launcher itself is **not vendored here**. It is becoming [`mojomast/hyvv`](https://github.com/mojomast/hyvv), a standalone worker-host runtime with a versioned `/v1` API contract. As of 12 November 2026 the live tree is still the private checkout on the Windows bee host (`orbit-local-workers/pc-launcher`); hyvv is being set up and is not yet the source of truth. Until that repository is published and this snapshot is pointed at it, this document is the reference for behaviour, not the source.

It is a local Windows Python service (`launcher.py`, version **0.1.15** as of this snapshot) that runs OpenCode bees in CUA sandboxes and writes attempt and result files under `%USERPROFILE%\.orbit-launcher\attempts\`. It binds only to loopback by default, with an optional extra loopback listener. It will refuse to bind any address that is not loopback or a Tailscale address (0.1.11). Provider keys are read by environment name first, then from a user-only file, and are never logged: `ORBIT_WORKER_GO_KEY` for OpenCode Go, `DEEPSEEK_API_KEY` for DeepSeek official.

### Versions 0.1.11 to 0.1.15

Each idle swap was taken with a backup and automatic rollback. Nothing in this contribution is a release of the launcher.

| Version | What changed |
| --- | --- |
| 0.1.11 | Loopback bind (optional extra loopback listener). Native beekeeper dispatch on this host. |
| 0.1.12 | DeepSeek official as a first-class route, with `deepseek-v4.1-flash` aliased to official `deepseek-flash`, after OpenCode Go hit a monthly limit. |
| 0.1.13 | Mint `attempt_id` as `att_` plus 16 hex characters when the bundlebees client omits one. |
| 0.1.14 | `export_project` of an unpushed or local branch: if `source_rev` is already a local commit, archive that commit and do not fetch a work branch that is not on the remote yet. The local checkout is never reset. `core.autocrlf` is forced off so Windows `git archive` stays LF. |
| 0.1.15 | Go / DeepSeek routing and a one-shot monthly-limit fallback (see below). Live since 3:59 PM ET on 12 November 2026. |

### Routing (0.1.15)

- An unprefixed model, or a `go:` prefix — including bare `deepseek-v4.1-flash` — goes to **OpenCode Go**.
- A `deepseek:<model>` prefix (for example `deepseek:deepseek-flash`) or a brief marked `priority: high` goes to **DeepSeek official**.
- If Go returns a monthly-limit 429, the launcher retries **once** on DeepSeek official and records `fallback=deepseek` (and a `fallback` / `model_history` entry on the attempt). A generic rate limit does not trigger this path.
- The orchestrator / beekeeper coordinator stays on DeepSeek; this table applies to bees.

After 0.1.15, name important slices `deepseek:deepseek-flash` (or set `priority: high`). Plain `deepseek-v4.1-flash` now means Go.

## `bees.ps1` behaviour

`bees.ps1` never dispatches a bee itself, never pushes, and never cancels or restarts the launcher. Verbs: `status [card]`, `handoff <brief.json> [-DryRun]`, `result <card> [-Full] [-OutFile path]`, `settle <card>`.

- **VerifyFor, scoped to the lease.** The newest verify bee whose `brief.verify_of` names one of the card's work attempts is cross-checked against launcher-observed data. The lease is the work brief's `assigned_files` (or, if that list is empty, the work patch paths). For paths on the lease, file hashes must match (`patch_matches_work`).
- **Telemetry extras vs scope vs content.** `shots/**` and `**/PROGRESS.log` are `telemetry_extras` (a warning only). Any other path outside the lease is `scope_violation`, which fails the card. A hash difference on a leased path is a content mismatch, not a scope problem.
- **python3.** Work and verify commands use `python3`, not `python`. `make-verify-brief.py` and `render_brief.py` rewrite a leading `python` token.
- **Verify against the seeded base.** The launcher (>= 0.1.11) seeds a fresh tree and uploads the work patch. The seeded base is `local_base_rev` when the work result recorded it. The verify template applies the patch to that tree; it must not require `HEAD` to equal `source_rev` or the branch name to match the work branch.
- **SettleCard.** Idempotent. A pass unblocks the card if it was `blocked` / `scheduled` / `needs_input`, then `request-review` (with `--force` if the card is still `running`). A fail keeps or moves the card to `blocked`. Already `review` or `done` on a pass, or already `blocked` on a fail, is a no-op. `bees.ps1 result` prints a compact verdict summary first, with no 1 KB cap, and then settles. Settlement follows the Hermes CLI contract: `--json` is passed only on verbs that support it (`show`, `list`, `create`, `dispatch`, …); `unblock`, `block` and `request-review` are judged by process exit code, with JSON parsed only when stdout actually contains it.
- **owned-cards.json.** Handoff registers the card id in this file, written as UTF-8 without a BOM (`utf-8-sig` is accepted on read). bee-watch uses it, with bundlebees leases, as the ownership source.
- **No mid-run park.** The handoff body tells the beekeeper not to `kanban_block` or park the card as `needs_input` while a bee is running. That mid-run park sticks the card so later complete/review updates are refused.

## Verify-bee authority

Worker claims are **reports**. The coordinator, or `hermes bundlebees verify`, is the authority.

`VerifyFor` reads the verify bee's `worker_claims` (shape A: `verdict` / `commands` / `secret_scan`; shape B: `checks[]` with `passed`) and then decides the card itself: claimed pass, leased hashes match, no scope violation, no failed commands, and a clean secret scan (`secret_hits == 0`; a missing scan is a fail). A claimed pass can still fail the card.

## Pilot evidence (12 November 2026, America/Toronto)

Times below are converted to ET. Token counts are the launcher's `observed.usage` (`cachedReadTokens`, `inputTokens` which excludes cached reads, `outputTokens`, `thoughtTokens`). Durations are `updated_at - created_at` on the attempt record.

### Pilot `0114d` (launcher 0.1.14)

Verification passed. The verify bee's `shots/` progress log was a telemetry warning, not a content mismatch or a scope violation. The card settled toward review.

| Role | Started (ET) | Duration | Cached read | Uncached input | Output | Reasoning | Total | Model (served) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Work | 3:43:02 PM | 13 s | 44,800 | 235 | 91 | — | 45,126 | `deepseek-v4.1-flash` |
| Verify | 3:50:04 PM | 31 s | 49,536 | 140 | 866 | 163 | 50,705 | `deepseek-v4.1-flash` |

### Pilot `0115` (launcher 0.1.15, both routes)

This run confirmed routing: the work bee used unprefixed `deepseek-v4.1-flash` (OpenCode Go); the verify bee was marked `priority: high` and was served on DeepSeek official as `deepseek:deepseek-flash`. Verification passed (leased files matched; 9 of 9 unit checks in `test-verify-for.ps1` had already been passing on the host). The result snapshot taken at 4:05:54 PM ET still showed the card `blocked`, which is one of the leftover card-state issues listed under staged fixes.

| Role | Started (ET) | Duration | Cached read | Uncached input | Output | Reasoning | Total | Route |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| Work | 4:00:56 PM | 25 s | 45,056 | 129 | 109 | — | 45,294 | Go (`deepseek-v4.1-flash`) |
| Verify | 4:04:42 PM | 26 s | 49,280 | 302 | 829 | 31 | 50,442 | DeepSeek official (`deepseek:deepseek-flash`, `priority: high`) |

Cache-hit share on these pilots was above 99%. List-price estimates at DeepSeek off-peak rates are well under a tenth of a cent per bee; coordinator spend is a separate, larger figure and is covered in OBSERVABILITY.md.

## Staged fixes

The 0116 pass applied the earlier leftovers in the live scripts (no launcher restart). Findings as of 12 November 2026:

- **bee-watch is a level-triggered reconcile.** It compares desired vs actual state every tick (Kubernetes-controller style). A short bee that finished between ticks still wakes the beekeeper; there is no requirement to have seen a non-terminal edge first.
- **The harness guard denies mid-run parks.** A `pre_tool_call` hook runs `beekeeper-guard.py` on `terminal`, `execute_code`, `process`, `kanban_block` and `kanban_schedule`. Waiting-for-a-bee parks are rejected while an owned bee is in flight or work has succeeded and verify has not been dispatched. Stuck and verify-fail reports are still allowed.
- **SettleCard follows the CLI's `--json` contract.** Hermes 0.23.1 `kanban unblock` / `block` / `request-review` have no `--json`. `Kanban` only adds `--json` on verbs that accept it, honors the process exit code, and parses JSON only when stdout actually contains it (retrying without the flag if the CLI says the argument is unrecognized).
- **owned-cards.json uses UTF-8 without a BOM.** `RegisterOwned` writes with `UTF8Encoding($false)`. Readers accept a BOM (`utf-8-sig`) so an older file still loads.
- **Tests (0116, live host):** bee-watch 11/11, guard 9/9, and `bees.ps1` 26/26 (`test-verify-for.ps1`: VerifyFor + lifecycle + CLI contract + owned-registry).
- **Remaining issue:** Hermes auto-blocks a card when the beekeeper exits without a terminal board call. bee-watch or SettleCard recovers it. The proposed fix is a first-class yield/wait transition so ending a turn mid-flight is a valid wait, not a protocol violation.

## Running the reference tests

From the directory that contains `bees.ps1`:

```powershell
powershell -File .\test-verify-for.ps1
python -m unittest test_bee_watch.py test_beekeeper_guard.py
```

`test-verify-for.ps1` copies `bees.ps1` functions into a temporary scope, writes fake attempt files under `$env:TEMP`, and prints `verify_for_check=ok`, `lifecycle_check=ok`, then `cli_contract_check=ok` on success (26 cases). The Python tests are stdlib-only (11 + 9).
