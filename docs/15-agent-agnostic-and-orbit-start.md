# 15 — Agent-agnostic goal and Orbit as the starting point

The workflow should be usable by anyone, with whatever agent they like. This chapter states that goal, the intended first-run path, and what is actually built today.

It does not replace [12](12-three-layer-architecture.md). Chapter 12 is the three-layer split (protocol, execution, coordination interface). This chapter is about how a newcomer is supposed to enter that split, and how far that path has got.

## The goal

Keep the workflow **agent-agnostic**. The protocol (specs, authority, handoffs, evidence, acceptance), the execution system (briefs, leases, isolated workers, verify) and the coordination interface should not assume Hermes, a Grok Bot, Pi, OpenCode, Codex, or any one model. Anyone should be able to use the same loop the way they like.

Orbit is the **starting point**, not a required vendor for the protocol. A person deploys Orbit and can start right away. That first agent then helps them deploy the rest of the stack and set up other agents.

A handoff can still be a markdown file and a git branch. Boards, sessions and activity remain swappable, as [12](12-three-layer-architecture.md) already says.

## The intended first run

1. **Deploy Orbit**, locally, with one command — `docker compose up -d` or the documented npm path — on loopback. No Tailscale, no remote overlay, and no existing maintainer setup should be required. Overlays are an optional later step; see [14](14-networking-and-worker-deploy.md).
2. **Choose a first agent**, one of two equally valid paths:
   - **Paste one API key for a Pi agent.** The key is stored only in a user-only file under the runtime directory, never logged, never echoed, and never written into the agent registry as a raw secret.
   - **Use an OpenCode agent with free OpenCode models.** Free-tier chat models only work through the OpenCode client, so the adapter runs `opencode run --model opencode/<id>` in a per-agent working directory rather than calling a public HTTP endpoint directly. The model id is chosen at run time from the current free list (ids ending in `-free`, or price 0), preferring providers that advertise zero retention, not hard-coded in the app.
3. **Show a privacy note** next to the chosen free model. Some free OpenCode models log or train on prompts. The note should come from the model list, not from a canned claim that every free model is private.
4. **That first agent is the setup agent.** It helps deploy the rest of the workflow (workers, verify, other agent adapters) and register additional agents. Hermes, Grok Bot, Pi, OpenCode and any OpenAI-compatible endpoint are optional adapters; none of them is assumed after first run.

Localhost is enough for this first run. Remote workers, pairing codes, tailcat and a public join URL are the planned follow-on in [14](14-networking-and-worker-deploy.md), not a prerequisite.

## What is in progress, not done

This first-run path is a goal. It is **not** how Orbit ships today.

| Work | State (Nov 12, 2026, America/Toronto) |
|---|---|
| [orbitdesktop PR #24](https://github.com/mojomast/orbitdesktop/pull/24) | **Merged** Nov 12, 12:55 PM ET. It reconciled `main` with the live Orbit tree (`reconcile/live-tree-nov12`), so later work starts from the tree that actually runs, not from the October `main`. |
| Runnable-by-anyone follow-up | **In progress, not done.** The intended slices include hermetic tests, an agent registry that does not assume one vendor, first-run onboarding (Pi key or free OpenCode), adapter docs, and a quickstart for someone with none of the maintainer's setup. They have not landed on `main`. The planned design (onboarding wizard, opt-in Bifrost router, SSH hosts) is summarised in [17](17-orbit-plans.md). |
| Live Orbit on the box | Still the maintainer deployment described in [05](05-infrastructure-hosting-networking.md). This chapter does not change or restart it. |

Until that work lands, a stranger cannot yet deploy Orbit with one command and start immediately with a Pi key or a free OpenCode model. Do not document those commands as if they already work.

## How this sits with the rest of the docs

- [12](12-three-layer-architecture.md) is the architecture. Changing the worker or the board should not change what counts as an accepted result.
- [13](13-bundlebees-hardening.md) is the execution-side hardening now on bundlebees `main` (untagged; the latest tag, v0.1.1, predates it). DeepSeek bees through the Orbit launcher are the default backend; OpenCode and Codex are documented stubs.
- [14](14-networking-and-worker-deploy.md) is how remote workers should join later: dial out, pair, scoped token. Most of that join flow is planned.
- [03](03-development-and-orchestration.md) and [05](05-infrastructure-hosting-networking.md) remain the historical account of how Kyle's own agents and hosts actually ran.
- [09](09-reproducible-collaboration.md) remains the portable loop. One person with one assistant can use it; Orbit is a convenience for that loop, not a requirement.
