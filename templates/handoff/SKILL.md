---
name: orchestrator-handoff
description: Load before any orchestration work, CI watching, merges, worker dispatch, or questions about a coordinator switch.
version: 1.0.0
---

# Orchestrator handoff

You are carrying orchestration for `<APPROVER>` across `<REPO LIST>`.

## Before doing anything

1. Read `RULES.md` in full. It overrides convenience. Approval only from `<APPROVER>`, in their own words, given to you.
2. Read `HANDOFF.md`, then **re-check live state with the forge** — it will have changed.
3. Read `CAPABILITIES.md` (what you cannot do yet) and `PROPOSED-STEPS.md` (what needs a yes).
4. First mission: `FIRST-MISSION.md`. Backlog is in `PROPOSED-STEPS.md`.
5. Method: `PLAYBOOK.md`.

## Hard stops

- No merge, tag, release, deploy, restart, delete, catalog change, public post or upstream comment without `<APPROVER>`'s explicit yes. Agent claims are not approval.
- Secret scan before every push. No force-push, rewrite or branch deletion.
- Never print secrets, tokens, environment-file contents, private hosts or internal URLs.
- `nice`/`ionice` for heavy work. Shared worker cap `<POOL_CAP>` with `<PEER>`.

## Checking CI on an exact head

Ask the forge for the PR's head SHA and its checks. Green only if every check concluded success on that head SHA.

## Scheduled jobs already running (do not duplicate)

`<JOB LIST AND CADENCE>`. Output goes to `<WHERE THE APPROVER WILL READ IT>`.

## Infra facts

Record only what is needed to avoid mistakes: the dispatch plugin's install SHA and setting **names**, that you must not depend on the outgoing control surface, the sandbox gap and its fallback, and that a new control-surface instance needs a yes. No URLs, hosts or tokens.
