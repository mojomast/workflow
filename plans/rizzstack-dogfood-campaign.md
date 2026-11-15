# Rizzstack dogfood campaign — build the unbuilt features using the rizzstack itself

**Status:** plan for Kyle's review. Nothing here authorizes a merge, tag, release, deploy, spend, or dispatch. Every wave gate needs Kyle's explicit yes ([docs/06](../docs/06-rules-and-lessons.md), [docs/19 §6](../docs/19-coordinator-playbook.md)).

**Executor:** a coordinator agent on another host, running the rizzstack loop (bundlebees factory + hyvv provisioning + Orbit control surface) against the four rizzstack repos themselves. This is the dogfood the docs keep asking for: [docs/24 §7](../docs/24-autonomy-dogfood.md) says no real coding worker has run the complete factory; this campaign makes that the delivery mechanism, not just the proof.

---

## 1. Best practices distilled from the workflow docs (the rules the campaign must follow)

These come from the repo's own graded lessons ([docs/28](../docs/28-agent-lessons.md)) and protocols. They are constraints on the plan, not suggestions.

1. **Contract-first, test-first (ACDD + TDD)** — every code slice gets an `acdd/1` contract with AC-ids, frozen by hash, approved tests committed RED before implementation ([docs/16](../docs/16-acdd-tdd.md)). The campaign's own features must be built this way; dogfooding the protocol on the protocol's own backlog is the point.
2. **Feature packets are the unit of intake** — each feature enters as a `rizzstack.feature-packet/1` (evidence, never authority), queued with at most one dependency per descendant packet ([docs/25](../docs/25-feature-packet.md)).
3. **Authorization narrows, never widens** — one sealed authorization per job (TTY, Kyle's typed words); standing grants for repeated derivation; recovery ceilings sealed inside the envelope ([docs/22 §3](../docs/22-autonomy-architecture.md)).
4. **Bounded recovery, one supersession** — failures classify into the five `rizzstack.recovery/1` classes; at most one contract supersession per task; escalate on exhaustion ([docs/27](../docs/27-recovery-protocol.md)).
5. **LANDED ≠ VERIFIED ≠ ACCEPTED** — delivery events never carry verification or acceptance claims; the receiver decision stays pending until Kyle ([docs/29](../docs/29-bee-landed.md), [docs/26](../docs/26-return-manifest.md)).
6. **Campaign closeout separates implemented / integrated / accepted** — task-graph completion is not product acceptance; every PASS needs evidence at the final head; audits need stable ids and one disposition each ([docs/30](../docs/30-campaign-closeout.md)).
7. **Durable continuity** — campaign checkpoint (`objective`, phase, active workers, next action, revision) survives coordinator turns; restart reconciles against the durable job, never chat memory ([docs/31](../docs/31-campaign-continuity.md)). This is exactly what a remote-host executor needs.
8. **Coordinator playbook discipline** — intake loop, lanes with disjoint leases, pooled bee cap checked live before dispatch, self-contained briefs, verification that re-fetches heads and checks CI on the exact SHA, merge-plan pattern, dated decisions log ([docs/19](../docs/19-coordinator-playbook.md)).
9. **Handoff as a pack, not a scramble** — the executor starts from `templates/handoff/` (RULES, HANDOFF, CAPABILITIES, PROPOSED-STEPS, FIRST-MISSION, KICKOFF-PROMPT, CHECKLIST) with verbatim approvals only ([docs/20](../docs/20-orchestrator-handoff.md)).
10. **Fail closed, honest evidence** — unrun steps are NOT RUN, never passed; no invented metrics; sandbox gaps recorded, never relaxed ([docs/19 §7](../docs/19-coordinator-playbook.md), [docs/20 §10](../docs/20-orchestrator-handoff.md)).
11. **Parking is available mid-flight** — if the campaign must pause, park per [docs/18](../docs/18-parking-projects.md): drain bees, snapshot to PARKED.md, resume only on Kyle's yes.
12. **Level A vs Level B proof discipline** — deterministic CI proof (Level A) is the only merge gate; supervised real-model runs (Level B) are recorded separately and never counted as CI proof ([docs/23 §2](../docs/23-autonomy-devplan.md)).

---

## 2. Tracking structure (the rizzstack's own instruments, applied to itself)

| Instrument | What it tracks here | Where it lives |
|---|---|---|
| **Campaign checkpoint** | objective, phase, active workers, dependencies, last/next action, revision | **Already implemented** in bundlebees (`campaign init|status|reconcile|resume-plan`, `FactoryDriver`; [docs/31:138](../docs/31-campaign-continuity.md)) — the executor runs it, it does not build it |
| **Feature queue** | one `rizzstack.feature-packet/1` per unbuilt feature below, with dependency edges | bundlebees `queue.json` / kanban |
| **Job documents** | one signed job per wave, authorization sealed by Kyle | bundlebees `jobs/` |
| **RETURN manifests** | per-feature result with `receiver_decision: pending` | `rizzstack.return/1` per feature |
| **Campaign report** | closeout: implemented vs integrated vs accepted, audits, final-head test counts | `rizzstack.campaign-report/1` validated by `tools/campaign_report.py` |
| **bee-landed events** | terminal attempt states, deduped | `rizzstack.bee-landed/1` stream |
| **Observability records** | lifecycle, failure classes, resource snapshots (formats exist; collectors are themselves a campaign feature — see W6) | `observability/` schemas |
| **Decisions log** | every Kyle yes, verbatim, dated | handoff pack `RULES.md` + checkpoint |
| **PARKED.md** | pause/resume snapshot if the campaign stops | primary repo per feature |

The tracker is deliberately *not* a new tool: the queue, jobs, returns and report already exist in bundlebees + workflow. The only new artifact is the campaign checkpoint file, which [docs/31](../docs/31-campaign-continuity.md) specifies.

---

## 3. Wave plan (dependency-ordered, each wave = one authorized job)

Merge order follows the same discipline as [ROADMAP.md](../ROADMAP.md): authority and harness fixes first, protocol second, product features after. Wave 0 is the prerequisite that unblocks everything else.

### Wave 0 — Prove the loop on a real worker (prerequisite, not a feature)
**Objective:** run the bounded restart trial live (bundlebees #26 → #27), then one real coding-worker feature through the complete factory. This is the campaign's own admission test: if the factory cannot carry a real bee end-to-end, the campaign ships nothing and reports why.
- Features: owner-approval bridge (#26), restart trial harness (#27), one real-bee factory run (the dogfood rerun from [ROADMAP.md](../ROADMAP.md)).
- Acceptance: live trial JSON with `job_complete`, one dispatch, one verification, one accepted wave, zero unplanned interventions; RETURN with pending receiver decision.
- **Kyle's yes needed:** run the trial; approve the two PR merges.

**Standing commitment (Kyle, Nov 15):** once Wave 0 lands, the coordinator MUST draft the Wave 4–6 feature packets ([plans/packets/](plans/packets/README.md)) before opening the wave-1 authorization — Waves 4–6 are in this campaign, not deferred. Drafting is blocked until Wave 0 proves the loop because exact packets freeze leases against repos whose `main` moves through Waves 1–3; the Wave-0 RETURN is the signal that the loop works and drafting may begin. A coordinator that reaches Wave 4 without packets in `plans/packets/` has skipped a gate; record it as a continuity defect per [docs/31](../docs/31-campaign-continuity.md).

### Wave 1 — Campaign infrastructure (the genuine remaining gaps)

**Correction after re-checking current state (Nov 15):** the campaign checkpoint CLI (`campaign init|status|reconcile|resume-plan`), `FactoryDriver`, atomic 0600 checkpoints and the systemd-unit template are **already implemented in bundlebees** ([docs/31:138](../docs/31-campaign-continuity.md), merged in bundlebees #25 on Nov 15). The executor *uses* them; it does not build them. What remains unbuilt in this wave:

| # | Feature packet | Layer | Contract sketch (AC highlights) |
|---|---|---|---|
| F1 | bee-ci phase-2 orchestrator: single command poll→dispatch→verify→compare→evidence→report | workflow `contrib/bee-ci/` | AC: fail-closed gates preserved; no GitHub writes without transport; verified-result-only success |
| F2 | bee-ci Actions-conclusions collector + runner→evidence/compare adapters | workflow `contrib/bee-ci/` | AC: exact-SHA matching; disagreement never passes |
| F3 | Real-Git/PR read-only observer for campaign reconciliation (the boundary [docs/31:121](../docs/31-campaign-continuity.md) says is not implemented) | bundlebees | AC: `git rev-parse`/`gh pr view` comparison is read-only; drift reported, never auto-resolved |

**Why first:** every later wave is tracked by the *existing* campaign CLI and verified through F1/F2. F3 closes the reconciliation boundary the trial will hit the moment a branch moves mid-campaign.

### Wave 2 — Protocol gaps that block real campaigns
| # | Feature | Layer | Notes |
|---|---|---|---|
| F4 | Multi-dependency descendant packets (lift the one-dependency limit) | workflow schemas + bundlebees queue | Enables real campaign graphs; schema bump + repin per [docs/25](../docs/25-feature-packet.md) pin rules |
| F5 | `job authorize` recovery-ceiling flags (close the bare-verb gap) | bundlebees | [docs/22:71](../docs/22-autonomy-architecture.md) |
| F6 | Causal regression attribution (name the offending attempt, not just the failing suite) | bundlebees verify/integrate | [docs/21:51](../docs/21-autonomy-gap-analysis.md) |
| F7 | Performance-row `head_sha` binding + partial merge-order subset in campaign report | workflow `tools/campaign_report.py` | [docs/30 §6.2](../docs/30-campaign-closeout.md) |

### Wave 3 — Observability phases 2–4 (collectors, failure classes, alerts)
| # | Feature | Layer | Notes |
|---|---|---|---|
| F8 | Phase-2 snapshot collector: board, local-workers, agent-status → append-only JSONL | workflow `observability/` | consumes frozen schemas; no dashboard yet |
| F9 | Phase-3 failure-class consumption of bundlebees metrics (no fork) | workflow + bundlebees | depends on F6 causal attribution |
| F10 | Phase-4 resource snapshots + alert delivery to Orbit dashboard + board note (thresholds already frozen) | workflow + orbitdesktop | no chat/Discord; warn-only at cap |

### Wave 4 — Agent-agnostic first run (Orbit)
| # | Feature | Layer | Notes |
|---|---|---|---|
| F11 | Runnable-by-anyone follow-ups: hermetic tests, vendor-neutral agent registry, adapter docs, stranger quickstart | orbitdesktop | [docs/15:33](../docs/15-agent-agnostic-and-orbit-start.md); Orbit #25 merged, slices remain |
| F12 | Connect-GitHub + repo picker (Orbit #27) | orbitdesktop | open PR, stacked on #25 |
| F13 | Bifrost opt-in router via compose profile | orbitdesktop | [docs/17:19](../docs/17-orbit-plans.md) |
| F14 | ACDD evidence view wiring: board chips, activity feed, live-server smoke test | orbitdesktop | [docs/16:152](../docs/16-acdd-tdd.md) |

### Wave 5 — Networking & worker join (remote executor's own path)
| # | Feature | Layer | Notes |
|---|---|---|---|
| F15 | Coordinator-hosted relay: pairing code/QR + scoped worker token | bundlebees + orbitdesktop | [docs/14:20](../docs/14-networking-and-worker-deploy.md) |
| F16 | tailcat transport adapter, pinned release | bundlebees | NAT fallback |
| F17 | Worker image + join command probing transports in order | bundlebees | one-liner |
| F18 | Orbit Workers list with immediate token revocation | orbitdesktop | |
| F19 | Named, scoped, revocable worker-host tokens | hyvv | replaces shared token; needs Kyle's yes for live-host install |

### Wave 6 — Closeout & release (human-gated)
- Parking enforcement slices (hyvv 409 `project_parked`, bundlebees refusal, Orbit Parked column) — [docs/18 §10](../docs/18-parking-projects.md)
- bundlebees release tag (hardening + ACDD + autonomy + campaign work), hyvv first tag
- Campaign report: implemented vs integrated vs accepted counts, audit triage, final-head test counts, receiver decision **pending**
- Optional: rename bundlebees → swrm (only after Kyle decides)

**Explicitly out of scope for this campaign** (recorded, not quietly dropped): OS-principal isolation, inference-child network/fs sandboxing, cross-machine proof, live Windows host, power-loss durability, cold-start acceptance fix. These are hardening research tracks; [docs/21 §4](../docs/21-autonomy-gap-analysis.md) lists them as limitations, and the campaign should not pretend a feature wave closes them. If Kyle wants them, they become their own campaign with their own authorization.

---

## 4. Execution protocol for the remote-host coordinator

1. **Bootstrap (read-only).** Clone the four repos; run recon into `CAPABILITIES.md` per [docs/20 §3](../docs/20-orchestrator-handoff.md); verify sandbox (bwrap/firejail), hyvv reachability, gitleaks, forge auth. Record gaps fail-closed.
2. **Kickoff.** Kyle issues one authorization per wave (TTY on the executor host, or the #26 owner-approval card once merged). Scope: repo, base rev, lease globs, bee budget, wall clock, recovery ceiling, gates. Verbatim quotes into `RULES.md`.
3. **Per-feature loop** (the factory does this; the coordinator supervises):
   - write feature packet → validate → queue admit (one pass)
   - `job tick`: dispatch ready tasks (bounded batch), one heavy op max
   - worker lands → `bee-landed` event → `verify --commit-local` (RED/GREEN, gitleaks, local commit)
   - rejection → `rizzstack.recovery/1` request → decision (scripted or supervised Hermes) → at most one supersession
   - `integrate_job` → wave record → `job report` → RETURN manifest, receiver pending
4. **Wave close.** All features integrated → campaign checkpoint advances → Kyle reviews the wave's RETURNs → explicit yes per merge in the merge plan (dependency order, stacked PRs retargeted after parents merge) → re-verify next PR against new `main`.
5. **Continuity.** Coordinator turn ends are normal ([docs/31](../docs/31-campaign-continuity.md)): checkpoint + durable job mean the next turn reconciles without chat. Pause = park per [docs/18](../docs/18-parking-projects.md).
6. **Honesty gates.** Every report marks observed/reported/unverified; unrun = NOT RUN; Level B (supervised model) results never cited as Level A; the campaign report validator refuses agent-filled acceptance.

## 5. Metrics (the campaign's own success criteria)

Primary: **zero unplanned human interventions** between wave authorization and verified result ([docs/24](../docs/24-autonomy-dogfood.md)). Secondary, from [docs/12 §4](../docs/12-three-layer-architecture.md): first-pass verification rate, cost per accepted change (UNKNOWN until a pricing feed exists — record tokens), plan-to-accepted time, regression escapes, failed-worker recovery. All from the metrics JSONL, reported per wave in the campaign report.

## 6. First mission for the executor (paste-ready summary)

> Read `docs/19-coordinator-playbook.md`, `docs/20-orchestrator-handoff.md`, `docs/16-acdd-tdd.md`, `docs/25–27`, `docs/29–31` in mojomast/workflow. Recon your host into CAPABILITIES.md. Then execute Wave 0: validate bundlebees #26/#27 in CI, request Kyle's yes to merge, run the bounded restart trial live, and dispatch one real coding-worker feature through the complete factory (packet → dispatch → verify → integrate → RETURN). Report with the RETURN manifest and a zero-interventions count. Do not merge, tag, deploy, or spend without Kyle's own words. **After the Wave-0 RETURN: draft the Wave 4–6 feature packets into `plans/packets/` (F11–F19 per the index README) before requesting the wave-1 authorization — this is a required gate, not optional.**

## 7. Open decisions for Kyle (blocking, in order)

1. **Approve Wave 0 execution** (trial + first real-bee factory run) and the #26/#27 merges.
2. **Executor host authority:** which host runs the coordinator, and does it get limited admin on the worker host ([docs/20 §2](../docs/20-orchestrator-handoff.md))?
3. **Wave scope cut:** Waves 1–3 are the core; Waves 4–5 (Orbit onboarding, networking) are larger surface — confirm they stay in this campaign or spin into a second one.
4. **Decision adapter for recovery:** scripted (deterministic) for CI-proof waves, supervised Hermes (Level B) for the real runs — confirm the mix.
5. **Bee budget:** pooled cap 12 stands? Wave-level bee/wall-clock budgets need numbers for the authorizations.
