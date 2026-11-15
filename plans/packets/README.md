# Feature packet pack — rizzstack dogfood campaign

**Status:** drafts for Kyle's review. No packet here is authority. Nothing is dispatched, merged, tagged or spent until Kyle's explicit yes, recorded verbatim ([docs/19 §6](../../docs/19-coordinator-playbook.md), [docs/22 §3](../../docs/22-autonomy-architecture.md)).

**Protocol pin:** every packet pins `workflow_ref = 755d6c43124c13f35541dd0356a238561627f998` (workflow `main` at the time of drafting, Nov 15, 2026). Per [docs/25](../../docs/25-feature-packet.md), a packet whose pin does not bear the current schema bytes fails `validator_mismatch` — if `main` moves before these are admitted, the executor re-pins to the commit that bears the schema and re-validates; the packet bodies do not change.

## What is a draft vs admissible

The packet schema is closed (`additionalProperties: false`) and the validator fails closed. Two honest limitations of these drafts, recorded rather than hidden:

1. **`contract_sha256` is not computed here.** Freezing requires the canonical-JSON hash ([docs/16 §2](../../docs/16-acdd-tdd.md)), which the executor computes with `tools/feature_packet.py` at admission. Exact-feature packets therefore ship with `review.status: "draft"`; the executor's freeze step (`contract freeze` → set `contract_sha256` → re-validate) is the gate that makes them admissible. A draft contract cannot be cited as frozen evidence.
2. **`source_rev` / `root_revision` are named as the wave's authorized base**, which Kyle sets at authorization time. The examples use the placeholder pattern `BASE0…` is NOT used — instead each packet carries a `TODO(authorization)` marker in `request.provenance` and the executor substitutes the real 40-hex SHA from the sealed authorization before validation. A packet with a placeholder revision will fail the schema's `^[0-9a-f]{40}$` pattern, which is the intended alarm: no packet is admitted against an unsealed authorization.

## Wave 0 (admission test — not packets)

Wave 0 has no feature packets: it is the live restart trial (bundlebees #26/#27) and one real-bee factory run, authorized directly as a job. Packets begin at Wave 1.

## Packet index

| File | Wave | Feature id | Kind | Repo | Depends on |
|---|---|---|---|---|---|
Packets are drafted as `.packet.md` files (architect-mode drafting lane is Markdown-only); each contains the exact packet JSON in a fenced block for verbatim transcription at admission.

| Packet | Wave | Feature id | Kind | Repo | Depends on |
|---|---|---|---|---|---|
| [F1-bee-ci-orchestrator.packet.md](F1-bee-ci-orchestrator.packet.md) | 1 | `wf-f1-bee-ci-orchestrator` | exact | mojomast/workflow | — |
| [F2-bee-ci-collector.packet.md](F2-bee-ci-collector.packet.md) | 1 | `wf-f2-bee-ci-collector` | exact | mojomast/workflow | — |
| [F3-git-pr-observer.packet.md](F3-git-pr-observer.packet.md) | 1 | `bb-f3-git-pr-observer` | exact | mojomast/bundlebees | — |
| [F4-multi-dependency-packets.packet.md](F4-multi-dependency-packets.packet.md) | 2 | `wf-f4-multi-dep-packets` | exact | mojomast/workflow | — |
| [F5-authorize-recovery-flags.packet.md](F5-authorize-recovery-flags.packet.md) | 2 | `bb-f5-authorize-recovery-flags` | exact | mojomast/bundlebees | — |
| [F6-regression-attribution.packet.md](F6-regression-attribution.packet.md) | 2 | `bb-f6-regression-attribution` | exact | mojomast/bundlebees | — |
| [F7-report-head-binding.packet.md](F7-report-head-binding.packet.md) | 2 | `wf-f7-report-head-binding` | exact | mojomast/workflow | — |
| [F8-observability-collector.packet.md](F8-observability-collector.packet.md) | 3 | `wf-f8-observability-collector` | exact | mojomast/workflow | — |
| [F9-failure-class-consumption.packet.md](F9-failure-class-consumption.packet.md) | 3 | `wf-f9-failure-class-consumption` | **descendant** | mojomast/workflow | `bb-f6-regression-attribution` |
| [F10-alert-delivery.packet.md](F10-alert-delivery.packet.md) | 3 | `wf-f10-alert-delivery` | exact | mojomast/workflow | — |

Waves 4–6 packets (Orbit onboarding, networking, parking enforcement, releases) are drafted after Wave 0 proves the loop — drafting them now would freeze leases against repos whose `main` will have moved through Waves 1–3, violating the exact-policy rule that a packet's revision must equal its contract's `source_rev`.

**Standing commitment (Kyle, Nov 15):** drafting the Wave 4–6 packets is a required gate, not an option. When Wave 0's RETURN lands, the coordinator drafts F11–F19 into this directory before opening the wave-1 authorization:

| Wave | Features to draft | Source chapters |
|---|---|---|
| 4 | F11 runnable-by-anyone slices · F12 Connect-GitHub/repo picker · F13 Bifrost router · F14 ACDD evidence-view wiring | [docs/15](../../docs/15-agent-agnostic-and-orbit-start.md), [docs/17](../../docs/17-orbit-plans.md), [docs/16 §9](../../docs/16-acdd-tdd.md) |
| 5 | F15 coordinator-hosted relay · F16 tailcat adapter · F17 worker image/join · F18 Workers-list revocation · F19 scoped worker-host tokens | [docs/14](../../docs/14-networking-and-worker-deploy.md), [docs/20 §6](../../docs/20-orchestrator-handoff.md) |
| 6 | F20+ parking enforcement (hyvv 409, bundlebees refusal, Orbit Parked column) | [docs/18 §10](../../docs/18-parking-projects.md) |

Each draft follows the same conventions as F1–F10: exact packet JSON, `TODO(authorization)` markers, disjoint leases, full evidence set. The Wave-0 RETURN manifest is the trigger; a coordinator reaching Wave 4 without these packets on disk has skipped a gate and records a continuity defect.

## Shared packet conventions

- **`budget`**: 2 bees, 5400 s wall clock per feature (well inside the pooled cap of 12; Kyle adjusts per wave authorization).
- **`required_evidence`**: `["red", "green", "regression", "gitleaks", "integration"]` — the full factory path, since dogfooding the loop is the point.
- **`prohibited`**: push to origin, merge, tag, release, deploy, publish, edit approved tests, force-push, branch deletion, history rewrite, printing secrets or private hosts.
- **`human_gates`**: `["merge", "release", "deploy", "publish"]` (the acdd/1 minimum set).
- **Disjoint leases within a wave**: F1/F2 both touch `contrib/bee-ci/` but different files; F1 owns the pipeline/orchestrator modules, F2 owns the collector and adapters. They are sequenced F1 → F2 (descendant-style dependency expressed at the queue, not in the packet) if run concurrently — or simply run in separate waves. The executor picks per the playbook's lane rules ([docs/19 §1](../../docs/19-coordinator-playbook.md)).
- **Test ids use JUnit form** (`path::Class::test`) per the first dogfood lesson ([docs/16 §12](../../docs/16-acdd-tdd.md)).
