# What's next

Planned and in-flight work on the rizzstack: workflow (method), hyvv (worker
host), bundlebees (orchestration) and Orbit (control surface), bottom to top,
plus the umbrella repo and the two newer Hermes plugins. Status is one of
**done**, **open PR**, or **planned**. Pull request numbers, states and merge
commits were checked against GitHub on 24 November 2026, America/Toronto. Items
that spend resources, merge, tag, release, deploy, or change the live hyvv
worker host still need an explicit yes from the repository operator before
they happen.

The day-by-day history is in the umbrella repo's
[NEWS.md](https://github.com/mojomast/rizzstack/blob/main/NEWS.md); the
machine-readable queue is [`plans/backlog.json`](plans/backlog.json).

## The 12 November merge order

**Done.** Every step of the merge order the 12 November review recommended has
merged or been superseded by a merged port:

| Step | Status |
|---|---|
| Orbit authority fixes [#25](https://github.com/mojomast/orbitdesktop/pull/25), [#26](https://github.com/mojomast/orbitdesktop/pull/26), [#28](https://github.com/mojomast/orbitdesktop/pull/28) | **Done** (merged 12 Nov; #28 as `eddc502`). |
| bundlebees review fixes #12 | **Done** as a port: #12 was closed and [#14](https://github.com/mojomast/bundlebees/pull/14) landed the same C1/C6 findings (`d82630a`). #5 merged as `2f83ae4`. |
| Artifact protocol: bundlebees #7, #9 | **Done**: [#9](https://github.com/mojomast/bundlebees/pull/9) merged (`7b77c3d`); #7 closed as superseded by #9. |
| Self-integration, metrics, usage: bundlebees #8, #10, #11, #6 | **Done**: [#10](https://github.com/mojomast/bundlebees/pull/10) (`cad64bb`) and [#11](https://github.com/mojomast/bundlebees/pull/11) (`39602ff`) merged; #8 closed as superseded by #10, #6 as superseded by #11. |
| workflow [#5](https://github.com/mojomast/workflow/pull/5), [#6](https://github.com/mojomast/workflow/pull/6), [#8](https://github.com/mojomast/workflow/pull/8), [#9](https://github.com/mojomast/workflow/pull/9) | **Done** (merged 12 Nov). |
| workflow [#7](https://github.com/mojomast/workflow/pull/7) (Hermes Forge contrib) | **Open PR** (draft since 12 Nov). Candidate to close; that needs the owner's yes. |
| hyvv [#1](https://github.com/mojomast/hyvv/pull/1) | **Done** (merged as `17a51f7`). |

## Hardening (P0 and P1)

**Done.** Worker-result retrieval (Orbit #28, bundlebees #9), bundlebees
self-integration in the sandbox (#10), metrics without double counting and
with unavailable kept apart from zero (#11), and collected-test-id validation
(#14) are all on `main`.

- **Orbit CI and branches.** The standing constraints still apply: separate
  real regressions from failures that also happen on the base, no
  whitelisting of failing checks, Orbit stays a read-only evidence consumer,
  document the Docker-mode router limitation, and do not mount the Docker
  socket.

## Rails activity ledger (`rizzstack.rails/1`)

- **Done (code):** the four-repository implementation merged as workflow
  [#91](https://github.com/mojomast/workflow/pull/91), hyvv
  [#26](https://github.com/mojomast/hyvv/pull/26), orbitdesktop
  [#46](https://github.com/mojomast/orbitdesktop/pull/46) and bundlebees
  [#82](https://github.com/mojomast/bundlebees/pull/82), with the
  qualification evidence in [#92](https://github.com/mojomast/workflow/pull/92).
  All 22 `RAILS-*` slices are `landed` in the backlog
  ([#94](https://github.com/mojomast/workflow/pull/94)).
- **Planned (release):** the [release decision](evidence/rails-rc/release/DECISION.md)
  is **HOLD**. It needs the worker-assignment binding chosen and a live
  Windows canary before `rails_enabled` is turned on anywhere.

## M2 canary

**Done (one run).** `M2-CANARY-RUN` is `landed` in the backlog on the accepted
RETURN `0515b019` and the attributed re-dispatch (#94). Whether it ran on the
native Windows worker is **unconfirmed**: no committed record names the
worker host, and [`evidence/rails-rc/windows-canary.md`](evidence/rails-rc/windows-canary.md)
records the native Windows run as blocked before live preflight.

## Real-agent dogfood rerun

**Planned.** The multi-worker rerun with a deliberate out-of-scope rejection
and a signed integration record has no single recorded run on `main`. The
closest landed evidence is the one-bee M2 canary above and the four-repository
Rails acceptance run. Needs the operator's yes before it starts.

## Observability

Two different snapshot documents now exist; their names are close, so check
the schema id.

- **Done:** `rizzstack.observability/snapshot/1` and the read-only collector
  ([#36](https://github.com/mojomast/workflow/pull/36), `84263c1`), the Phase 1
  record formats ([#8](https://github.com/mojomast/workflow/pull/8)), a
  `decisions` section from the owner-decision queue
  ([#96](https://github.com/mojomast/workflow/pull/96),
  [#97](https://github.com/mojomast/workflow/pull/97)), concurrent cold reads
  ([#107](https://github.com/mojomast/workflow/pull/107)) and the
  fleet-fallback fixes (#109–#114). The snapshot carries fleet, usage,
  pipeline, backlog, CI, failures, health, alerts and bottlenecks sections.
- **Done:** the Orbit Observatory and Hive apps that read it
  (orbitdesktop `apps/rizzstack-observatory`, `apps/rizzstack-hive`; the Hive
  via the authenticated extension proxy, orbitdesktop #66, #69, #81, #83).
- **Done:** `rizzstack.observability/1`, a separate redacted snapshot for
  Hermes chat cards, and the read-only `rizzobs` plugin
  ([orbit-control-plane #4](https://github.com/mojomast/orbit-control-plane/pull/4)).
  Renaming one of the two ids is an open decision.
- **Planned:** alert delivery to a board note, optional OTLP export, Bifrost
  labels, and dollar-cost or DeepSeek/OpenRouter usage in the chat cards (each
  needs its own yes).

## Owner decision queue and risk tiers

- **Done:** the `rizzstack.owner-decision/1` queue and schema
  ([`docs/decision-queue.md`](docs/decision-queue.md)) and the approval surface
  (orbitdesktop [#41](https://github.com/mojomast/orbitdesktop/pull/41)).
- **Done:** risk tiers, from derivation and policy table to fail-closed
  enforcement at dispatch: bundlebees
  [#241](https://github.com/mojomast/bundlebees/pull/241),
  [#242](https://github.com/mojomast/bundlebees/pull/242),
  [#246](https://github.com/mojomast/bundlebees/pull/246),
  [#247](https://github.com/mojomast/bundlebees/pull/247). Only the floor and
  the high-tier contract requirement are enforced; human gates, reviewer
  counts and minimum verifications are still report-only.
- **Open PR:** a dispatch preflight that runs the same gates without
  dispatching (bundlebees [#252](https://github.com/mojomast/bundlebees/pull/252)),
  corrected risk docstrings ([#251](https://github.com/mojomast/bundlebees/pull/251))
  and the workflow/hyvv pin bump for the Hermes host update
  ([#253](https://github.com/mojomast/bundlebees/pull/253)).

## Quality gates

- **Done:** slop-lint engine, baseline ratchet and CLI
  ([#116](https://github.com/mojomast/workflow/pull/116)), blocking on new
  findings in workflow ([#124](https://github.com/mojomast/workflow/pull/124)),
  hyvv (#35), bundlebees (#248) and orbitdesktop (#87).
- **Done:** rework metrics (bundlebees #243, #244; workflow
  [#120](https://github.com/mojomast/workflow/pull/120); orbit-control-plane #3)
  and the fork-safe PR summary comment
  ([#117](https://github.com/mojomast/workflow/pull/117),
  [#127](https://github.com/mojomast/workflow/pull/127)).
- **Done, not in CI:** lessons-check
  ([#122](https://github.com/mojomast/workflow/pull/122)) is report-only.
- **Planned:** slop-lint and gitleaks for uirizz and orbit-control-plane, a
  gitleaks job in rizzstack, and lessons-check as an advisory CI job.

## Memory (`rizzstack.memory/1`)

- **Done:** the contract ([#50](https://github.com/mojomast/workflow/pull/50)),
  the Hindsight trial harness (#82, #88), and the disk vault service with write
  quarantine, index and retention
  ([#98](https://github.com/mojomast/workflow/pull/98), #101, #102, #104).
- **Planned:** a read-only query CLI, a seed loader, capture and recall behind
  the flag, then a small canary. Not wired into the runtime; `MEMORY_ENABLED`
  stays off until the owner approves a restart with it on.

## Orbit onboarding

- **Done:** minimal install, onboarding wizard, adapters, the opt-in router
  and SSH hosts ([Orbit #25](https://github.com/mojomast/orbitdesktop/pull/25),
  [#46](https://github.com/mojomast/orbitdesktop/pull/46)).
- **Open PR:** the optional connect-GitHub step and repository picker,
  [Orbit #27](https://github.com/mojomast/orbitdesktop/pull/27) (draft since
  12 Nov; packet [F12](plans/packets/F12-connect-github-repo-picker.md)). Which
  repos are tracked stays user-managed; one operator's defaults are data, not
  a shipped default.
- **Planned:** packets [F11](plans/packets/F11-runnable-by-anyone.md) and
  F13–F19 (router profile, evidence wiring, relay, NAT fallback, join probing,
  revocable tokens, live-host join install) are drafted, not dispatched.

## Releases and tags

**Planned.** The only release tags are bundlebees v0.1.0 (11 Nov) and v0.1.1
(12 Nov, before the hardening merges) and uirizz v0.1.0 (23 Nov). workflow,
hyvv, orbit-control-plane and rizzstack have no release tags; Orbit's last tags
are the `hermes-plugin-v0.3.0` line from September. A coordinated release at
one tested set of revisions needs an explicit yes before tagging.

## hyvv repo

**Done.** hyvv (`mojomast/hyvv`) is the standalone worker-host runtime and owns
the versioned `/v1` API contract that Orbit and bundlebees test against, plus
an install script ([#1](https://github.com/mojomast/hyvv/pull/1)). Since then:
Rails recording (#26), the apply-update deployment receipt on `/v1/health`
([#31](https://github.com/mojomast/hyvv/pull/31),
[#32](https://github.com/mojomast/hyvv/pull/32)) and the Windows journal and
shutdown fixes ([#33](https://github.com/mojomast/hyvv/pull/33)). **Planned:**
list provisioning and landing export in `contract/v1/STATUS.json`, and a first
tag (needs a yes).

## Parking projects

**Done (spec) / planned (enforcement).**
[workflow #9](https://github.com/mojomast/workflow/pull/9) (chapter 18) merged
the protocol for parking and resuming a project. Enforcement in hyvv, the bee
scripts, Orbit and bundlebees is **planned**.

## Rename

**Planned, not started, pending the owner.** Two proposals exist: renaming the
bundlebees plugin to **swrm**, and the wider rebrand whose execution runbook is
[workflow #58](https://github.com/mojomast/workflow/pull/58), an open PR that
stays untouched until the owner decides. Nothing has been renamed; no
repository, package, plugin id or doc changes until then.

## Hermes Forge usage work

**Done (schema) / open PR.** `bee.usage/v1` is frozen, and the usage pipeline
(launcher receipts, outbox, ingest, pricing snapshots, rollup) reached
mainline on 16 November. The handoff in
[workflow #7](https://github.com/mojomast/workflow/pull/7) is still an open
draft.
