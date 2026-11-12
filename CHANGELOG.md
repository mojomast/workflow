# What's new

A dated account of recent, verified work on this workflow and the rizzstack
it coordinates. Times are America/Toronto. Pull request numbers, heads and
merge SHAs were checked against GitHub on 12 November 2026 at about 5:15 PM.
Heads of open pull requests move; GitHub is the source of truth. This file
does not edit earlier documentation chapters.

## 12 November 2026

### The rizzstack: four layers

Bottom to top: **workflow** (the method, this repo), **hyvv** (the worker
host, `mojomast/hyvv`, owns the versioned `/v1` worker API), **bundlebees**
(orchestration, a Hermes plugin), and **Orbit** (the control surface,
`mojomast/orbitdesktop`). hyvv was named at 4:26 PM. It's being extracted
from the runtime earlier chapters call "the PC launcher" (the 0.1.11–0.1.15
line), and its initial import is [hyvv #1](https://github.com/mojomast/hyvv/pull/1)
(open).

### Merged today

- **bundlebees [#5](https://github.com/mojomast/bundlebees/pull/5)**, merged
  at 4:44 PM as `2f83ae4`: ACDD contracts, HMAC-signed TDD evidence, and
  contract-aware dispatch, verify, integrate, refactor and review. No new
  tag; published tags are still `v0.1.0` and `v0.1.1`.
- **workflow [#4](https://github.com/mojomast/workflow/pull/4)** (`ab21f58`,
  12:36 PM), bundlebees [#3](https://github.com/mojomast/bundlebees/pull/3)
  (`509649b`) and [#4](https://github.com/mojomast/bundlebees/pull/4)
  (`c10aa42`), and Orbit [#24](https://github.com/mojomast/orbitdesktop/pull/24)
  (`47f2fc9`), all earlier in the day.

Every other merge Kyle approved at 4:43 PM (workflow #5–#8) was paused at
4:53 PM after the independent review below. Each still needs his yes.

### Independent engineering review (about 4:50 PM)

An independent review of workflow #5–#8, bundlebees #5, Orbit #25/#26/#28 and
hyvv found blocking issues. It concluded that the components show real
progress but aren't yet a production-ready four-layer workflow. Kyle
approved fixing every blocking finding on the existing branches, then asking
him before any merge. Status at the time of writing:

| Finding | Where | Status |
|---|---|---|
| AC test refs checked only by file, not by collected test id (C1) | bundlebees | Fix in [bundlebees #12](https://github.com/mojomast/bundlebees/pull/12) (open): sandboxed collect-only check and a signed manifest, required before freeze and dispatch |
| A review record implied authenticated human identity (C6) | bundlebees | Fix in bundlebees #12: coordinator-recorded reviews, human authorization reserved |
| Optional jsonschema test skipped in CI | bundlebees | Fix in bundlebees #12 |
| Floating CI dependency on a bundlebees branch; file-level AC refs in evidence | workflow #5 | Fixed on #5: CI pins `2f83ae4` with ACDD required; build contracts re-frozen with exact test ids |
| RED-before-GREEN inferred from phase labels on a timestamp tie (C2) | workflow #6 | Fixed on #6: signed `sequence` + `prev_sha256`, ties are `order_unproven` (bee-built, coordinator-verified) |
| Dogfood described as more than it was (C3) | workflow #6 | Fixed on #6: an implementation success and a revealing experiment, not an accepted run |
| Observability tests never ran in CI; closed route and source vocabularies (P1); no common discriminator with `bee.usage/v1` (P3) | workflow #8 | Fixed on #8 (this pull request) |
| PowerShell verify helper widened its lease from worker-result data | workflow #7 | Hermes Forge's branch |
| Any text reply treated as a host approval | Orbit #25 | Being fixed on the branch |
| Evidence shown without verifying its signature; accepted view unreachable | Orbit #26 | Being fixed on the branch |
| Coordinator name trusted against only the shared board key | Orbit #28 | Being fixed on the branch |
| bundlebees #7 and #8 both change the CLI; full sandboxed combined run | bundlebees #7–#10 | Reconciliation pending |

### This repository: open pull requests

- **[#5](https://github.com/mojomast/workflow/pull/5)** `feat/acdd-tdd`:
  agent-agnostic ACDD + TDD (chapter 16), reference demo, Orbit plans
  chapter, cold-start acceptance with a required ACDD step.
- **[#6](https://github.com/mojomast/workflow/pull/6)** `tools/acdd-lint`
  (stacked on #5): `acdd-lint` and the first dogfood run. 4 bee attempts,
  4 first-try GREENs, the 35 approved tests passing, integration failed in
  the sandbox, **0 accepted changes and 2 rejected waves**.
- **[#7](https://github.com/mojomast/workflow/pull/7)** `contrib/hermes-bees`
  (draft, Hermes Forge): the sanitized Windows bee pipeline reference.
- **[#8](https://github.com/mojomast/workflow/pull/8)** `feat/observability-records`
  (this pull request): frozen record formats, default alert thresholds
  (`alert.thresholds/v1`, set 4:34 PM), an envelope discriminator, and this
  changelog and roadmap. **Formats only, not a working pipeline:** there are
  no collectors, dashboard, alert delivery or board notes yet.
- **[#9](https://github.com/mojomast/workflow/pull/9)** `feat/park-project`:
  the protocol for parking and resuming a project (chapter 18). It's a
  protocol, not a deployed service.

### bundlebees: open pull requests

[#6](https://github.com/mojomast/bundlebees/pull/6) usage parsing (Hermes
Forge), [#7](https://github.com/mojomast/bundlebees/pull/7) and
[#9](https://github.com/mojomast/bundlebees/pull/9) the Orbit artifact client,
[#8](https://github.com/mojomast/bundlebees/pull/8) and
[#10](https://github.com/mojomast/bundlebees/pull/10) sandboxed
self-integration, [#11](https://github.com/mojomast/bundlebees/pull/11)
metrics accounting, and [#12](https://github.com/mojomast/bundlebees/pull/12)
the review fixes above. No tag until Kyle says so.

### Orbit: open pull requests

[#25](https://github.com/mojomast/orbitdesktop/pull/25) runnable by anyone
(draft), [#26](https://github.com/mojomast/orbitdesktop/pull/26) read-only
ACDD evidence view, [#27](https://github.com/mojomast/orbitdesktop/pull/27)
onboarding Connect GitHub and repo picker (draft, stacked on #25), and
[#28](https://github.com/mojomast/orbitdesktop/pull/28) the coordinator-only
worker artifact API. Older drafts #16–#21 stay open by choice.

### Usage record

Hermes Forge froze `bee.usage/v1` (orbitdesktop `feat/bee-usage-observability`,
`1617ae0`). This repository references it and doesn't redefine it.
`observability/envelope.py` maps its `schema_version` discriminator onto the
`schema` field these records use.

The operational bee cap is 12, shared across coordinators.
