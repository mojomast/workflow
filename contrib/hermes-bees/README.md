# Hermes bees (reference)

Windows/PowerShell reference for the bee pipeline that runs on one host: a local PC launcher, `bees.ps1` as the coordinator link, a beekeeper profile that dispatches work, and a verify bee whose claims are reports only.

This tree is a sanitized snapshot of the scripts that were live on 12 November 2026. It is not an installer, not a second source of truth for docs/ or CI, and it includes no key files. Paths and host-specific values in a live checkout must be replaced with local values.

The token and cost design lives in [OBSERVABILITY.md](OBSERVABILITY.md). That schema is draft v1 and freezes when observability slice 1 lands.

## Layout

- `scripts/bees.ps1` — the one small link between the box coordinator and the PC beekeeper.
- `scripts/test-verify-for.ps1` — unit checks for `VerifyFor` (leased-hash compare, telemetry extras, scope violations) plus lifecycle checks for `SettlePlan` / `ResultSummary`.
- `scripts/make-verify-brief.py` — renders the default verify-bee brief for a succeeded work bee.
- `scripts/templates/render_brief.py`, `scripts/templates/verify.md`, `scripts/templates/_house-rules.md` — brief templates. Commands are rewritten to `python3`.
- `scripts/bee-watch.py` — Hermes cron pre-check that wakes the beekeeper when a leased attempt goes terminal or looks stuck. On the live host this file is kept under the beekeeper profile's `scripts/` directory, not next to `bees.ps1`.

Do not edit `docs/` chapters, the repository root `README.md`, the demo, `tools/`, or `.github/` from this contribution. Those belong to other workstreams.

## The PC launcher (docs only)

The launcher itself is **not vendored here**. As of 12 November 2026 it is a private tree on the Windows bee host (`orbit-local-workers/pc-launcher`): no public repository under mojomast, no license file, and no git remote. Until that tree is published under a license that allows it, this document is the reference for behaviour, not the source.

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
- **SettleCard.** Idempotent. A pass unblocks the card if it was `blocked` / `scheduled` / `needs_input`, then `request-review` (with `--force` if the card is still `running`). A fail keeps or moves the card to `blocked`. Already `review` or `done` on a pass, or already `blocked` on a fail, is a no-op. `bees.ps1 result` prints a compact verdict summary first, with no 1 KB cap, and then settles.
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

TODO. Fixes were being staged next to the live files, not applied, when this snapshot was taken. Known leftovers, all in scripts (no launcher restart required unless later work says otherwise):

- The bee watcher can miss a very quick bee, so the verify step may stall until it is nudged.
- The beekeeper can still park a card mid-run, against the no-mid-run-park rule.
- The coordinator's closing step can trip on a Hermes command that does not return JSON.

This section should be filled in once those fixes are applied and re-piloted.

## Running the reference tests

On Windows, from the directory that contains `bees.ps1`:

```powershell
powershell -File .\test-verify-for.ps1
```

The script copies `bees.ps1` functions into a temporary scope, writes fake attempt files under `$env:TEMP`, and prints `verify_for_check=ok` then `lifecycle_check=ok` on success.
