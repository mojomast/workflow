# RULES — standing rules for the rizzstack dogfood campaign executor

This file overrides convenience. Approvals quoted here are the only ones that exist; everything else needs the approver's own words, in their own channel ([docs/19 §6](../../docs/19-coordinator-playbook.md)).

## Approvals on record (verbatim, to be filled at authorization)

> TODO(approval): Kyle's Wave-0 authorization — quote his exact words here with date, time (America/Toronto) and message id before any dispatch.

> TODO(approval): Kyle's wave-1 authorization — same discipline.

No approval exists yet. The branch `docs/dogfood-campaign-plan` (workflow repo, `7fab87b`) carries the plan and packet drafts; it is a proposal, not permission.

## Hard rules (from [docs/06](../../docs/06-rules-and-lessons.md), [docs/19 §7](../../docs/19-coordinator-playbook.md))

1. Only the approver's own words, in their own channel, approve: merge, PR approval, tag, release, publish, catalog changes, deploy/restart, live worker-host or launcher config, credentials, unpausing dispatch, deletes, force-push, metered compute spend, public posts, upstream comments, branding. A relayed yes never counts. An approval covers exactly what it names. A newer instruction supersedes older ones — re-check outstanding approvals whenever a new instruction arrives.
2. Never print, commit or log secrets, tokens, keys, `.env` contents, private hostnames, tailnet names, private IPs or internal URLs. Describe them generically.
3. Run a secret scan before every push. No force-push, branch deletion or history rewrite.
4. Keep security controls fail-closed. Never weaken a sandbox, check or test to get to green. Never invent evidence or metrics. Report unrun steps as NOT RUN.
5. Never trust a self-report: re-fetch the head SHA, check CI on that exact commit, run tests locally under `nice`/`ionice` when CI can't settle it.
6. Bees: shared pooled cap (12 as of Nov 12 — confirm live), per-lane cap set at dispatch. Check live capacity before every dispatch. Normal work on the default OpenCode model; important work on DeepSeek direct. Never unpause dispatch without a yes.
7. Lanes never touch each other's branches. Peer agents own their repos; send findings, don't commit into them.
8. "Stop" or "hold" means stop now: kill subagents and test processes, pause routines, don't restart until asked.
9. Google Colab is always "Google Colab", never "Colab". The bees plugin is bundlebees until the approver approves a rename.
10. The packet drafts in `plans/packets/` are proposals. `TODO(authorization)` markers are fail-closed: a packet admitted with a placeholder must fail validation — substitute real values only from a sealed authorization.

## What "green" means

Every check on the exact head SHA concluded success. Queued, pending, skipped, neutral or unstable is not green ([docs/20 §5](../../docs/20-orchestrator-handoff.md)).
