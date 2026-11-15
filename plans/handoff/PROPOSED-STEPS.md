# PROPOSED-STEPS — done, blocked, backlog

## Done (by the planning agent, on Kyle's machine)

- Full-coverage inspection of the workflow repo (all 32 docs, ROADMAP, CHANGELOG, PR.md, CI.md, observability, acceptance, bee-ci, contrib, templates) with live GitHub cross-check.
- Unbuilt-features inventory delivered to Kyle (features mentioned but not yet built, with file:line citations).
- Campaign plan written and verified against current state (caught and fixed the already-shipped checkpoint CLI error).
- Ten feature packet drafts (F1–F10, Waves 1–3) with exact `rizzstack.feature-packet/1` JSON.
- Wave-0 gate encoded: Wave 4–6 packets (F11–F19) are drafted by the coordinator after the Wave-0 RETURN, before the wave-1 authorization.
- Plan + packets pushed to `mojomast/workflow` branch `docs/dogfood-campaign-plan` @ `7fab87b` (secret-scanned; one false positive — `sk-` inside "task-graph" — verified clean).

## Blocked (waiting on Kyle)

- Wave-0 authorization (trial + first real-bee factory run) — plan §7 item 1.
- Merge of bundlebees #26/#27 and of this plan branch — each needs his own yes.
- Executor host authority + worker-host admin scope — plan §7 item 2.
- Decision-adapter mix (scripted vs supervised Hermes) — plan §7 item 4.
- Wave-level bee/wall-clock budget numbers — plan §7 item 5.

## Backlog (the campaign itself, in order)

1. Wave 0: admission test (see HANDOFF.md first mission).
2. Draft Wave 4–6 packets (F11–F19+) — required gate after Wave-0 RETURN.
3. Wave 1: F1 bee-ci orchestrator, F2 collectors/adapters, F3 Git/PR observer.
4. Wave 2: F4 multi-dependency packets, F5 authorize recovery flags, F6 regression attribution, F7 report head-binding.
5. Wave 3: F8 observability collector, F9 failure-class consumption (descendant of F6), F10 alert delivery.
6. Wave 4: F11–F14 (Orbit agent-agnostic first run).
7. Wave 5: F15–F19 (networking/worker join).
8. Wave 6: F20+ parking enforcement, release tags, campaign closeout report.

## Requirements for you to stand alone

- Sealed Wave-0 authorization (TTY or #26 approval card).
- hyvv reachable with valid auth from this host.
- A working sandbox (local bwrap/firejail or the worker-host container route).
- gitleaks installed checksum-verified.
- Named, scoped tokens for anything beyond read access (shared-token stopgap only per [docs/20 §6](../../docs/20-orchestrator-handoff.md); named tokens are backlog, not a blocker).
