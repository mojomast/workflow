# What's new

A dated account of recent, verified work on this workflow and the Orbit,
bundlebees, and hyvv stack it coordinates. Times are America/Toronto.
Pull request numbers and SHAs were checked against GitHub on 12 November
2026. This file does not edit earlier documentation chapters.

## 12 November 2026

### This repository

- **Workflow pull request #4** (merged as `ab21f58`, 12:36 PM). Demo `--out`
  guard, teaching-only lease labels, CI, and a cold-start acceptance test.
  This is the current `main`.
- **Workflow pull request #5** (open, `feat/acdd-tdd`, head `3d12fae`).
  Agent-agnostic ACDD + TDD: work-item contracts, RED / GREEN / REFACTOR /
  REVIEW evidence, profiles, a reference demo, an Orbit plans chapter, and a
  docs pass. Contracts and evidence stay portable across agent frameworks.
- **Workflow pull request #6** (open, `tools/acdd-lint`, head `8a2cad3`,
  based on #5). `acdd-lint`, built test-first, including dogfood evidence
  from this date.
- **Workflow pull request #7** (open, `contrib/hermes-bees`, head `f5ca267`).
  Hermes Forge's sanitized reference tree for the Windows bee pipeline:
  [contrib/hermes-bees/](https://github.com/mojomast/workflow/tree/contrib/hermes-bees/contrib/hermes-bees)
  adds a launcher and bees handoff document, draft usage-record
  documentation, and sanitized scripts. See
  [pull request #7](https://github.com/mojomast/workflow/pull/7).
- **Observability record formats** (this pull request, on `main`). JSON
  Schemas, examples, and tests for lifecycle, classified-failure, VCS, board
  and blocker, and resource snapshot records. The Hermes Forge usage record
  is referenced, not redefined. See `observability/README.md`.

Earlier documentation pull requests on this repository, already on `main`,
are #1 (infrastructure and working-together), #2 (reference workflow and
three-layer architecture), and #3 (poster, bundlebees hardening, networking,
and Orbit start; merged as `baec166` at 12:03 PM).

### bundlebees

- **Pull request #3** (merged as `509649b`, 11:54 AM). Hardened verifier and
  contracts: sandbox, strict briefs, leases, revision checks, outcome
  metrics, and agent adapters.
- **Pull request #4** (merged as `c10aa42`, 12:36 PM). Never auto-select the
  unshare sandbox; add CI. Current published tags remain `v0.1.0` and
  `v0.1.1` (the latter from earlier today at 8:55 AM); a new release tag is
  still ahead (see ROADMAP.md).
- **Pull request #5** (open, `feat/acdd-tdd`, head `075bc1a`). Contracts,
  signed evidence, and contract-aware dispatch, verify, and integrate.

### hyvv

At 4:26 PM America/Toronto, the standalone worker-host runtime was named
**hyvv**, at `mojomast/hyvv`, which Hermes Forge is building. It is a fourth
layer next to this workflow, bundlebees, and Orbit, and it owns the
versioned `/v1` worker API contract. Merges and the first tag still need an
explicit yes. This repository does not vendor hyvv source.

The current PC launcher line, 0.1.13 to 0.1.15, is the runtime hyvv is
being built from. The handoff in
[workflow pull request #7](https://github.com/mojomast/workflow/pull/7)
documents the 0.1.11–0.1.15 line, including minting `attempt_id`, exporting
unpushed or local branches, OpenCode Go / DeepSeek routing, and falling
back to DeepSeek on a monthly-limit 429. See
[contrib/hermes-bees/README.md](https://github.com/mojomast/workflow/blob/contrib/hermes-bees/contrib/hermes-bees/README.md)
and [contrib/hermes-bees/OBSERVABILITY.md](https://github.com/mojomast/workflow/blob/contrib/hermes-bees/contrib/hermes-bees/OBSERVABILITY.md)
on the #7 branch.

The operational bee cap is 12, shared across coordinators.

### Orbit

- **Pull request #24** (merged as `47f2fc9`, 12:55 PM). Reconcile `main`
  with the live Orbit tree as of this date.
- **Pull request #25** (open, `feat/runnable-by-anyone`, head `e596edb`).
  One-command deploy, onboarding wizard, adapters, an opt-in router, and SSH
  hosts. Kept separate until it is validated.
- **Pull request #26** (open, `feat/acdd-evidence-view`, head `9a88c29`).
  Read-only ACDD evidence view (slice 1, not fully wired). Reconcile onto
  #25 after #25 is validated.

The official observability dashboard is planned as a new Orbit view, not as
an extension of the older control-plane app.
