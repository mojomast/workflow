# Build workflow — Kyle Durepos (mojomast)

<p align="center">
  <img src="docs/assets/workflow-map/workflow-map.png" alt="The build workflow at a glance: plan and spec, orchestration, bees and other workers, verification, then a pull request, merge and deploy, each behind Kyle's explicit yes." width="1280">
</p>

<p align="center"><em>The whole workflow on one poster. A <a href="docs/assets/workflow-map/workflow-map.html">print-resolution HTML version</a> ships in the repo; open the file locally (fonts are beside it).</em></p>

How Kyle and his agents plan, build, ship and host software, written down from what actually happened between mid-October and mid-November 2026. It covers the agents roster, the orchestration patterns (executors, Cursor cloud agents, DeepSeek "bees" in Cua sandboxes), the pipelines we built for assets and video, the infrastructure (the box, Orbit, Tailscale, moltussy-1, the public application VPS with Docker and systemd, Google Colab, GitHub Pages), and the rules and lessons that came out of it.

Sources: the MR.INDIA bot's durable memory and shared memory (journal entries from MR.INDIA, Hermes Forge, Hermes Plugin Builder, BABA BOOEY, Cheese, DOLAN and hammy), the saved skills under the box's workflows folder, the scripts and briefs on the box, and `gh` data for the public repos. Teammate bots wrote their own accounts into [`contrib/`](contrib/). The [Codex account](contrib/codex.md) adds accessible collaboration history, delivered artifacts and pinned public evidence. Historical accounts distinguish observed, reported and unverified outcomes; the operating guide and teaching exercise below are proposals distilled from those accounts.

Secrets, tokens, tailnet hostnames, private IPs and private URLs are deliberately left out and described generically ("the tailnet-only Orbit URL").

## The workflow at a glance

To **learn or repeat the workflow**, start with [09 Reproducible collaboration](docs/09-reproducible-collaboration.md), copy the [handoff template](templates/HANDOFF.md), and try [10 Teaching the workflow](docs/10-teaching-the-workflow.md). The [three-layer architecture](docs/12-three-layer-architecture.md) explains how the protocol, bundlebees and Orbit fit together; [bundlebees hardening](docs/13-bundlebees-hardening.md) is what the plugin now enforces on `main`; [networking and worker deploy](docs/14-networking-and-worker-deploy.md) covers how remote workers should join (much of that is still planned); and [Orbit as the starting point](docs/15-agent-agnostic-and-orbit-start.md) is the agent-agnostic first-run goal (in progress). The [reference demo](reference/README.md) runs a miniature of the loop offline (Python 3 and git; no private infrastructure). The [cold-start acceptance test](acceptance/README.md) clones both public repos into a clean environment and runs the real bundlebees dispatch → verify → integrate path end to end, logging every manual intervention. For a live-host change, use [11 Working together](docs/11-working-together.md) and the [infrastructure deploy template](templates/INFRA-DEPLOY.md). Current live-host ports, container names and paths stay in the authorized host runbook, not in this public repository. The diagram below describes the existing build/release path; chapter 09 adds the research, creative-production and independent-review loop around it. [Chapter 20](docs/20-orchestrator-handoff.md) is how to hand orchestration from one coordinator agent to another.

```mermaid
flowchart LR
    K([Kyle: idea / ask]) --> P[Plan & spec<br/>research, PLAN.md / SPEC.md,<br/>task slices + file leases]
    P -->|Kyle approves plan| O{Orchestrator bot<br/>MR.INDIA / Hermes Forge /<br/>Hermes Plugin Builder / Cheese}
    O --> B[DeepSeek bees<br/>Cua sandboxes on Kyle's PC<br/>via Orbit launcher]
    O --> C[Cursor cloud agents<br/>Opus / Sonnet, last resort]
    O --> E[Executor subagents<br/>on the box]
    O --> G[Asset pipelines<br/>GenerateImage, Google Colab<br/>ComfyUI, Remotion, HyperFrames]
    B --> V[verify.sh on the box<br/>scope check, own tests,<br/>schema budget, secret scan]
    C --> V
    E --> V
    V --> PR[Feature branch + PR]
    PR -->|Kyle's explicit yes| M[Merge → tag → release]
    M -->|Kyle's yes| D[Deploy to moltussy-1 / VPS / Pages<br/>backup + rollback SHA]
    M -->|Kyle's yes| CAT[Nous catalog PR<br/>YAML-only, SHA-pinned]
    CAT --> R[Maintainer review] -->|change requests| O
    D --> DEMO[Demo video, X post drafted,<br/>Kyle posts, Typeform after yes]
```

Every arrow labelled "Kyle's yes" is a hard gate: merges, tags, releases, deploys, catalog PRs, posts and form submits each need Kyle's own words, not another agent's relay. See [06 Rules and lessons](docs/06-rules-and-lessons.md).

## Index

| Doc | What's in it |
|---|---|
| [01 Planning and spec](docs/01-planning-and-spec.md) | How an idea becomes a researched plan, spec, task slices and file leases, and how approval works |
| [02 Assets](docs/02-assets.md) | Game art, the assetrizz library, banners, screenshots, video, voice, provenance and originality rules |
| [03 Development and orchestration](docs/03-development-and-orchestration.md) | Agents roster, executors, cloud agents, DeepSeek bees, Orbit, routines, briefing patterns, review → merge → release → catalog |
| [04 Pipelines](docs/04-pipelines.md) | Each pipeline used or built: inputs, tools, outputs, where it lives |
| [05 Infrastructure, hosting, networking](docs/05-infrastructure-hosting-networking.md) | The box, Orbit, Tailscale, Kyle's PC, moltussy-1, the public application VPS, GitHub Pages, Google Colab; a generic public-host pattern (live topology stays in the host runbook) |
| [06 Rules and lessons](docs/06-rules-and-lessons.md) | Standing rules, naming, approval gates, pitfalls and fixes |
| [07 Projects](docs/07-projects.md) | Timeline of what shipped, with repo links and outcomes |
| [08 Repositories](docs/08-repositories.md) | Every repo we worked on, plus deep build histories of Eye Of Hermes, Temple of Hermes, assetrizz and the aircraft Doppler geolocation plugin |
| [09 Reproducible collaboration](docs/09-reproducible-collaboration.md) | Proposed common loop, roles, acceptance evidence, corrections and portable handoffs |
| [10 Teaching the workflow](docs/10-teaching-the-workflow.md) | Practice session, exercises and a reproducibility rubric |
| [11 Working together](docs/11-working-together.md) | The live-host operating rhythm: preflight, backups, shared-host etiquette, secrets, verification and reporting |
| [12 Three-layer architecture](docs/12-three-layer-architecture.md) | Workflow as the protocol, bundlebees as the execution system, Orbit as the coordination interface; measurement fields now logged by the plugin, not yet a live baseline |
| [13 Bundlebees hardening](docs/13-bundlebees-hardening.md) | Sandboxed verify, strict briefs, immutable leases, `source_rev` and combined-branch checks, metrics JSONL, and the WorkerBackend contract, now on bundlebees `main` (untagged) |
| [14 Networking and worker deploy](docs/14-networking-and-worker-deploy.md) | Dial-out workers, pairing, tailcat, Cloudflare Tunnel and optional Tailscale; built versus planned is marked throughout |
| [15 Agent-agnostic goal and Orbit as the starting point](docs/15-agent-agnostic-and-orbit-start.md) | Deploy Orbit, start with a Pi API key or a free OpenCode model, and let that first agent set up the rest; orbitdesktop PR #24 and the runnable-by-anyone work are in progress, not done |
| 16–19 (open PRs, not on `main` yet) | 16 ACDD+TDD and 17 Orbit plans on [workflow #5](https://github.com/mojomast/workflow/pull/5); 18 parking on [workflow #9](https://github.com/mojomast/workflow/pull/9); 19 coordinator playbook on [workflow #10](https://github.com/mojomast/workflow/pull/10) |
| [20 Orchestrator handoff](docs/20-orchestrator-handoff.md) | How to switch coordinators mid-stream: recon, the handoff pack, approvals that carry over, credentials, plugin install with rollback, fail-closed merge automation, dependency and sandbox audits, a kickoff prompt, and a checklist |
| [Reference demo](reference/README.md) | Runnable miniature: two workers, an out-of-scope rejection, throwaway verification, templates, integration and a metrics log (Python 3 + git, no network) |
| [Templates](templates/HANDOFF.md) | [Handoff](templates/HANDOFF.md), [work return](templates/RETURN.md), [asset pack](templates/ASSET-PACK.md) and [infrastructure deploy](templates/INFRA-DEPLOY.md) contracts, plus the [orchestrator handoff kit](templates/handoff/) |
| [Worked example](examples/doppler-review-handoff.md) | A concrete Doppler review, correction and evidence cycle |
| [contrib/](contrib/) | First-person accounts from the teammate bots, kept as written (after a secret scan) |

## Who "we" is

Kyle directs. MR.INDIA is his main Grok Bot and the general orchestrator. Hermes Forge and Hermes Plugin Builder are specialist bots for Hermes plugins. BABA BOOEY, Cheese, DOLAN and hammy are Grok Bots that took specific projects. Hermes (Nous Research's agent) and Pi run as agents inside Orbit. Coding labour mostly runs as DeepSeek Flash "bees" in Cua sandboxes on Kyle's Windows PC, with Cursor cloud agents used for the hardest work until their cost pushed most work to bees. Details in [03](docs/03-development-and-orchestration.md).

ChatGPT/Codex sessions also contribute research, specifications, independent review, creative direction and delivered assets. Kyle transfers those packets to the builders and brings results back for review. The Comfyrizz brand pack, Emurizz spec, Doppler review and Terry animation exports show how that work joins the implementation history; see [contrib/codex.md](contrib/codex.md).
