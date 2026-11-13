# What's next

Planned and in-flight work on the rizzstack: workflow (method), hyvv (worker
host), bundlebees (orchestration) and Orbit (control surface), bottom to top. Status is one of **done**, **open PR**, or
**planned**. Pull request numbers and SHAs were checked against GitHub on
12 November 2026, America/Toronto. Items that spend resources, merge, tag,
release, deploy, or change the live hyvv worker-host still need an
explicit yes from the repository operator before they happen.

## Merge order

This follows the dependency order recommended by the independent review on 12
November. It's a plan, not permission: every merge needs Kyle's own yes.

1. **Authority fixes first.** Orbit [#25](https://github.com/mojomast/orbitdesktop/pull/25)
   requires an explicit, successful approval response. [#28](https://github.com/mojomast/orbitdesktop/pull/28)
   requires authenticated coordinator ownership. [#26](https://github.com/mojomast/orbitdesktop/pull/26)
   verifies evidence or uses a verifier-authenticated acceptance report. **Open PR.**
2. **bundlebees review fixes**, [#12](https://github.com/mojomast/bundlebees/pull/12)
   (collected test ids, coordinator-recorded reviews, CI jsonschema; #5 is
   already merged as `2f83ae4`). **Open PR.**
3. **Artifact protocol:** Orbit #28, then bundlebees #7/#9, rebased on the
   final bundlebees base. The cross-repo round trip becomes a required CI
   test. **Open PR.**
4. **Reconcile bundlebees #8/#10 with #7/#9** (both change the CLI), with a
   fully accepted combined run inside the real bwrap sandbox; then metrics
   ([#11](https://github.com/mojomast/bundlebees/pull/11)) and usage parsing
   ([#6](https://github.com/mojomast/bundlebees/pull/6)). **Open PR.**
5. **workflow [#5](https://github.com/mojomast/workflow/pull/5)**, pinned to
   bundlebees `2f83ae4` with ACDD required. Bump the pin on purpose after
   bundlebees #12. **Open PR.**
6. **workflow [#6](https://github.com/mojomast/workflow/pull/6)** (stacked on #5). **Open PR.**
7. **workflow [#7](https://github.com/mojomast/workflow/pull/7)** (Hermes
   Forge), then **[#8](https://github.com/mojomast/workflow/pull/8)** (this
   PR). [#9](https://github.com/mojomast/workflow/pull/9) is independent. **Open PR.**
8. **Orbit #25, then #26** rebased on the final onboarding branch, with the
   browser matrix re-run after the security fixes. **Open PR.**
9. **hyvv** ([#1](https://github.com/mojomast/hyvv/pull/1)) is reviewed as its
   own runtime deliverable once source, installer and `/v1` contract tests are
   public. Then comes the full four-layer cold-start and real-agent
   acceptance run. **Open PR.**

## Hardening (P0 and P1)

**Open PR / in review.** These are now open pull requests: artifact retrieval in
Orbit [#28](https://github.com/mojomast/orbitdesktop/pull/28) and bundlebees
#7/#9, self-integration in bundlebees #8/#10, metrics in bundlebees #11, and
collected-test-id validation in bundlebees #12. None of them is merged.

- **P0 — Worker-result retrieval.** An authenticated, coordinator-only
  artifact endpoint. No direct hyvv file reads. Keep attempt identity,
  revision, patch hash, metadata, and usage. Raw patches stay out of
  model-visible responses and logs. Validate ownership, state, size, and
  integrity. Handle pending, missing, disconnected, restarted, malformed,
  and oversized results. Block path traversal, symlinks, and substitution.
  Keep it idempotent. Acceptance tests first, including a real round trip.
- **P0 — bundlebees self-integration.** Remove the dependency on the
  checkout folder name without renaming `/work` or weakening isolation.
  Integration runs the regression suite, the contract acceptance tests, and
  the security tests, and records not-run vs failed vs passed. Show it
  working inside real `bwrap`. Keep fail-closed behaviour.
- **P1 — Metrics.** No double counting. Tell environmental failures apart
  from real regressions. Tell unavailable values apart from zero. Capture
  per-attempt usage. Use explicit denominators. Represent every approved
  contract test file. Validate test references against collected test ids (bundlebees #12).
  Preserve history. Add regression tests.
- **P1 — Orbit CI and branches.** Separate real regressions from failures
  that also happen on the base. Use a pinned Playwright or tested runner
  image, with no whitelisting of failing checks. Keep Orbit #25 separate
  until it is validated, then reconcile #26 onto it. Orbit stays a
  read-only evidence consumer. Document the Docker-mode router limitation,
  and do not mount the Docker socket.

## Real-agent dogfood rerun

**Planned.** Runs once hyvv (the current 0.1.15 launcher line) is validated. Needs the operator's
explicit yes before it starts, and again before any workflow-repo allowlist
entry is applied. Planned shape: two or more parallel workers, plus a
deliberate out-of-scope rejection, and a signed integration record. A
workflow is not accepted if that record says the integration was
incomplete.

## Observability

**Open PR (formats) / planned (everything that runs).** Only the record
formats exist, in this pull request (Phase 1). They're frozen contracts, not
a working pipeline. **The collectors, the Orbit Observability dashboard, alert
delivery, board notes and the lifecycle visualization are all planned.**
Later phases, each needing its own yes:

1. **Phase 1 — Contracts** (this pull request). Lifecycle, classified
   failure, VCS, board, and resource snapshot schemas, examples, and tests.
   Plus a common envelope discriminator and open provider labels (review P1
   and P3). Usage stays with Hermes Forge (`bee.usage/v1`, now frozen; earlier draft in
   [contrib/hermes-bees/OBSERVABILITY.md](https://github.com/mojomast/workflow/blob/contrib/hermes-bees/contrib/hermes-bees/OBSERVABILITY.md)
   on [workflow #7](https://github.com/mojomast/workflow/pull/7)).
2. **Phase 2 — Snapshot collector.** Pull board, local-workers, and
   agent-status into append-only JSONL. Include route and fallback. No
   dashboard yet. **Planned.**
3. **Phase 3 — Failure class and clean denominators.** Consume the
   authorized bundlebees P1 metrics fix; do not fork it. **Planned.**
4. **Phase 4 — Resource snapshots and alerts.** DeepSeek and both OpenCode
   Go balances (saved keys, never logged), Google Colab compute units, Grok
   Bot usage, disk, CPU, and RAM. Default thresholds (`alert.thresholds/v1`
   in this pull request) are: DeepSeek below $5, a Go key at 80% of monthly
   allowance, 5 Go 429s in a row, a bee stuck 30 minutes, a blocker older
   than 4 hours, disk below 10% free, bees at 12 of 12, and daily model
   spend above $10 (this supersedes a $5/day draft). Alerts go to the Orbit
   dashboard and a board note only (no chat, no Discord). At the shared cap
   of 12, warn only; pausing non-priority bees is a later phase with its
   own yes. Operators may override the defaults. Unknown values stay
   unavailable, never silent zero. The thresholds exist as data only:
   collectors, alert delivery and board notes remain **planned**.
5. **Phase 5 — Git, pull request, and CI snapshots** for an allowlisted
   set of repositories. **Planned.**
6. **Phase 6 — A new, read-only Orbit Observability view** (dashboard and
   lifecycle visualization), dark mode,
   after Orbit #25 is validated and #26 is reconciled onto it, or as a
   later PR that merges cleanly. No Docker socket. **Planned.**
7. **Phase 7 — Optional OTLP export, Bifrost labels,** and a decision
   about the older control-plane dashboard. The Temple of Hermes BBS waits
   for a later version. **Planned.**

Version 1 of the dashboard also includes the Hermes host, Cursor cloud
agents, Grok Bot usage, and Google Colab compute units.

## Orbit onboarding

**Planned** (largely Orbit #25, plus follow-on work that is not in this
repository).

- Minimal install.
- Bifrost as an opt-in router.
- SSH hosts.
- An optional connect-GitHub step (device-flow or a token stored locally,
  never logged).
- A repository picker: which repos are tracked is user-managed and part of
  onboarding. One operator's current defaults are `mojomast/workflow`,
  `mojomast/bundlebees`, and `mojomast/orbitdesktop`.

## bundlebees release tag

**Planned.** A release tag after the hardening and ACDD work that should go
into it, with an explicit yes before tagging.

## hyvv repo (approved, in progress by Hermes Forge; merges and first tag need Kyle's yes)

**Approved, in progress by Hermes Forge.** Merges and the first tag still
need an explicit yes. hyvv (`mojomast/hyvv`) is the standalone worker-host
runtime, a fourth layer next to this workflow, bundlebees, and Orbit. It
owns the versioned `/v1` API contract that Orbit and bundlebees test
against, plus an install script. Nothing in this pull request starts or
vendors that work.

## Parking projects

**Open PR.** [workflow #9](https://github.com/mojomast/workflow/pull/9)
(chapter 18) is the protocol for parking and resuming a project. Parking
stops new dispatch, lets running bees finish, and moves queued cards to a
Parked column. A `PARKED.md` snapshot makes resuming auditable. It's a
protocol spec, not a deployed service. Enforcement in hyvv, the bee
scripts, Orbit and bundlebees is **planned**.

## Rename bundlebees to swrm

**Planned, not started, pending Kyle.** A proposed rename of the bundlebees
plugin to **swrm**. Nothing has been renamed, and no repository, package,
plugin id or doc changes until Kyle decides.

## Hermes Forge usage work

**Done (schema) / open PR.** Hermes Forge froze `bee.usage/v1` (orbitdesktop
`feat/bee-usage-observability`, `1617ae0`). Workflow #7 carries the handoff. Hermes Forge owns bundlebees usage parsing and the usage record
fields, and is staging the Orbit adapter pass-through separately.
