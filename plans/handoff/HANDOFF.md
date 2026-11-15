# HANDOFF — rizzstack dogfood campaign

**Date:** 2026-11-15 (America/Toronto). **Author:** Zoo (planning agent, GLM). **Approver:** Kyle Durepos (`mojomast`).

## The picture

You are a coordinator agent on a host other than Kyle's box. Your job: execute the dogfood campaign defined in [`plans/rizzstack-dogfood-campaign.md`](../rizzstack-dogfood-campaign.md) — building the rizzstack's own unbuilt features *by running the rizzstack factory loop on itself*.

The four layers you coordinate (bottom to top): **workflow** (protocol; `mojomast/workflow`), **hyvv** (worker host; `mojomast/hyvv`), **bundlebees** (orchestration; `mojomast/bundlebees`), **Orbit** (control surface; `mojomast/orbitdesktop`).

## Where the plan and packets live

- Branch: `mojomast/workflow` @ `docs/dogfood-campaign-plan`, head `7fab87b` (open PR pending Kyle's yes — do not merge).
- Plan: [`plans/rizzstack-dogfood-campaign.md`](../rizzstack-dogfood-campaign.md)
- Packet drafts (Waves 1–3): [`plans/packets/`](../packets/README.md) — F1–F10 with exact `rizzstack.feature-packet/1` JSON.
- Wave 4–6 packets (F11+): **not drafted yet.** Drafting them is a required gate triggered by the Wave-0 RETURN — see the standing commitment in the plan's Wave 0 section and the table in the packet index README.

## Current state (as of this handoff — re-verify everything live; snapshots go stale)

| Item | State at handoff | Re-check |
|---|---|---|
| workflow `main` | `755d6c4` (campaign closeout + continuity chapters merged) | `git rev-parse origin/main` |
| bundlebees `main` | #25 (campaign acceptance/continuity) merged Nov 15; #26 (owner-approval bridge) and #27 (restart trial harness) OPEN drafts | `gh pr list -R mojomast/bundlebees` |
| hyvv `main` | provisioning + Windows git-env fix merged (#5–#9) | `gh api repos/mojomast/hyvv/commits` |
| orbitdesktop `main` | #25 (runnable-by-anyone), #26 (ACDD view), #28 (artifact API), #29/#30 merged; #27 (Connect GitHub) open | `gh pr list -R mojomast/orbitdesktop` |
| This plan branch | pushed, PR not yet opened by Kyle | `gh pr list -R mojomast/workflow` |

## Approvals

See [`RULES.md`](RULES.md). None on record yet. The five blocking decisions are in the plan's §7: Wave-0 approval, executor host authority, Wave 4–5 scope (now resolved: they stay in-campaign), decision-adapter mix, bee budgets.

## First mission

Wave 0 — the campaign's admission test. Full definition in the plan; paste-ready summary in the plan's §6. In short: recon your host, validate bundlebees #26/#27 in CI, get Kyle's yes to merge them, run the bounded restart trial live, then dispatch one real coding-worker feature through the complete factory. Report with the RETURN manifest and a zero-interventions count.

**After the Wave-0 RETURN:** draft the Wave 4–6 packets into `plans/packets/` (F11–F19 per the index README) before requesting the wave-1 authorization. Required gate, not optional.

## Blockers

- No authorization sealed yet — every dispatch waits on Kyle's TTY authorization (or the #26 approval card once merged).
- The plan branch is unmerged; Kyle may edit the plan before merging. Re-read it after his review.

## Next action

Bootstrap recon per [`CAPABILITIES.md`](CAPABILITIES.md) template, then request the Wave-0 authorization from Kyle with the exact envelope you intend to operate inside (repo, base rev, scope, bee budget, wall clock, recovery ceiling, gates) — he approves what you name, nothing wider.
