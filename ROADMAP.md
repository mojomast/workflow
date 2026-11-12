# What's next

Planned and in-flight work on this workflow and the Orbit, bundlebees, and
launcher stack it coordinates. Status is one of **done**, **open PR**, or
**planned**. Pull request numbers and SHAs were checked against GitHub on
12 November 2026, America/Toronto. Items that spend resources, merge, tag,
release, deploy, or change the live launcher still need an explicit yes
from the repository operator before they happen.

## Merge order

When the open work below is ready, the agreed order is:

1. bundlebees [#5](https://github.com/mojomast/bundlebees/pull/5) (open, head `075bc1a`)
2. workflow [#5](https://github.com/mojomast/workflow/pull/5) (open, head `3d12fae`)
3. workflow [#6](https://github.com/mojomast/workflow/pull/6) (open, head `8a2cad3`; based on workflow #5)
4. Orbit [#25](https://github.com/mojomast/orbitdesktop/pull/25) (open, head `e596edb`)
5. Orbit [#26](https://github.com/mojomast/orbitdesktop/pull/26) (open, head `9a88c29`; reconcile onto #25 after #25 is validated)

Each merge still needs its own explicit yes. Workflow
[#7](https://github.com/mojomast/workflow/pull/7) (open, head `f5ca267`) and
this observability formats pull request are on `main` and can merge
independently of that sequence, but also need a yes.

## Hardening (P0 and P1)

**Planned** (no public pull request number verified for these items yet).

- **P0 — Worker-result retrieval.** An authenticated, coordinator-only
  artifact endpoint. No direct launcher file reads. Keep attempt identity,
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
  contract test file. Validate test references against collected test ids.
  Preserve history. Add regression tests.
- **P1 — Orbit CI and branches.** Separate real regressions from failures
  that also happen on the base. Use a pinned Playwright or tested runner
  image, with no whitelisting of failing checks. Keep Orbit #25 separate
  until it is validated, then reconcile #26 onto it. Orbit stays a
  read-only evidence consumer. Document the Docker-mode router limitation,
  and do not mount the Docker socket.

## Real-agent dogfood rerun

**Planned.** Runs once launcher 0.1.15 is validated. Needs the operator's
explicit yes before it starts, and again before any workflow-repo allowlist
entry is applied. Planned shape: two or more parallel workers, plus a
deliberate out-of-scope rejection, and a signed integration record. A
workflow is not accepted if that record says the integration was
incomplete.

## Observability

**Open PR / planned.** Record formats are this pull request (Phase 1).
Later phases, each needing its own yes:

1. **Phase 1 — Contracts** (this pull request). Lifecycle, classified
   failure, VCS, board, and resource snapshot schemas, examples, and tests.
   Usage stays with Hermes Forge (`bee.usage/v1` draft in
   [contrib/hermes-bees/OBSERVABILITY.md](https://github.com/mojomast/workflow/blob/contrib/hermes-bees/contrib/hermes-bees/OBSERVABILITY.md)
   on [workflow #7](https://github.com/mojomast/workflow/pull/7)).
2. **Phase 2 — Snapshot collector.** Pull board, local-workers, and
   agent-status into append-only JSONL. Include route and fallback. No
   dashboard yet. **Planned.**
3. **Phase 3 — Failure class and clean denominators.** Consume the
   authorized bundlebees P1 metrics fix; do not fork it. **Planned.**
4. **Phase 4 — Resource snapshots and alerts.** DeepSeek and both OpenCode
   Go balances (saved keys, never logged), Google Colab compute units, Grok
   Bot usage, disk, CPU, and RAM. Alerts go to the Orbit dashboard and a
   board note only (no chat, no Discord). At the shared cap of 12, warn
   now; pausing non-priority bees is a later phase with its own yes.
   Unknown values stay unavailable, never silent zero. **Planned.**
5. **Phase 5 — Git, pull request, and CI snapshots** for an allowlisted
   set of repositories. **Planned.**
6. **Phase 6 — A new, read-only Orbit Observability view**, dark mode,
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

## Launcher as its own worker-host repository

**Planned, awaiting the operator's approval.** The PC launcher would become
its own worker-host repository, with a versioned `/v1` API contract that
Orbit and bundlebees test against, plus an install script. It is not
approved, and nothing in this pull request starts that split.

## Hermes Forge usage work

**Open PR / planned.** Workflow #7 carries the draft usage schema and
handoff. A freeze notice and ledger path come once Hermes Forge slice 1
passes. Hermes Forge owns bundlebees usage parsing and the usage record
fields, and is staging the Orbit adapter pass-through separately.
