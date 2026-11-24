# 17 Orbit plans: onboarding, routers and SSH hosts

Status: **planned or in progress, nothing here is merged yet.** This chapter records what Orbit (mojomast/orbitdesktop) is being built to do next, so the rest of this repo can point at one place. The work runs on the runnable-by-anyone branch of orbitdesktop, in slices built by DeepSeek bees and verified on the box. Each item below is marked; when a slice lands, the marker changes and the orbitdesktop docs (`docs/QUICKSTART.md`, `docs/CONFIG.md`, `docs/ROUTER.md`, `docs/HOSTS.md`, `docs/SETUP_CHECKLIST.md`) become the source of truth.

The three-layer model from [chapter 12](12-three-layer-architecture.md) does not change: the workflow repo is the protocol, bundlebees is the execution system, Orbit is the coordination interface. None of the plans below add a second orchestrator. They make Orbit easier to start (see [chapter 15](15-agent-agnostic-and-orbit-start.md)) and give agents a safe way to reach providers and hosts.

## Onboarding wizard (in progress)

A first-run wizard replaces hand-editing config files. Steps:

1. **Choose what to install** (in progress). Pick components: the agents you want, the optional token router, optional remote hosts. Anything not chosen does not run.
2. **Providers** (in progress). Either set providers directly (one key per provider, today's flow) or go through a router (built-in or external, below). Keys are masked in the UI and stored as files with 0600 permissions, never in the config file or in git.
3. **A model for each part** (in progress). Map a model to each role: setup agent, chat, workers, summarise. With a router, each role also gets a budget and a rate limit (editable defaults).
4. **Review and apply** (in progress). The wizard shows exactly what will run ("nothing extra" when no router or host is chosen) and then applies it.
5. **The setup agent installs** (in progress). A built-in setup-agent skill with a checklist finishes the install, checks each part and reports what it did.

Settings later lets you turn parts off, change budgets, rotate keys and upgrade.

## Token router (planned)

- **Off by default.** When it is not selected, nothing runs: no container, no process, no port, no config file.
- **Bifrost is the default router** (planned). Opt-in through a Docker Compose profile: the router service carries `profiles: ["router"]`, so a normal `docker compose up` starts nothing router-related; the wizard sets the profile only when you choose the router. The image is pinned by version and digest, runs read-only with dropped capabilities and has no host port by default. Upstream keys live only in a generated 0600 env file; each role gets its own virtual key with a budget and limits. Non-Docker installs run a checksum-pinned binary as a subprocess, again only when chosen.
- **LiteLLM only under Advanced, pinned by digest** (planned). It covers the most providers but is heavier (needs Postgres for virtual keys) and had supply-chain and injection incidents in 2026, so it is offered only as an advanced choice and only ever installed by image digest, never a floating tag.
- **External router mode** (planned). Paste one URL and one key (OpenRouter, or your own router elsewhere). Nothing runs locally.
- **OpenCode free models stay direct** (planned). Routers cannot front them: they work only from OpenCode's own client. They stay a direct provider used by the OpenCode adapter, alongside whatever router you choose.

Agents (Pi, OpenCode for paid models, Hermes, bundlebees workers) are pointed at the router's OpenAI- or Anthropic-compatible base URL with their role's virtual key. Orbit wires this; agents never see upstream keys.

## SSH hosts (in progress)

Add hosts for deploying infrastructure or workers, from the wizard ("Remote hosts, optional") or Settings → Hosts.

- **System OpenSSH, driven by an Orbit-owned config file** (in progress), not a Node SSH library. One Orbit-generated ed25519 key per install by default (per-host keys optional). The private key never reaches the browser, logs or agents.
- **Add-host flow** (in progress): address (or import from an ssh config snippet), how to reach it (direct, jump host, Tailscale, tailcat or Cloudflare), authorise with a restricted `authorized_keys` line or a short, fully shown bootstrap that creates a dedicated `orbit` user, then test the connection.
- **Verified first use, then strict pinning** (in progress). The test shows the host key fingerprint Orbit saw so you can compare it with the one the bootstrap printed. After that, host key checking is strict and a changed key fails hard with a re-verify flow. Never "accept any key".
- **Agents never hold keys** (in progress). They call Orbit's host API (list, run, put, deploy a named recipe). Orbit checks per-agent, per-host permission levels (`none`, `read`, `deploy`, `admin`), asks you before destructive commands and writes an append-only audit log per host.
- **SSH is for install, upgrade and removal only** (planned). A `bundlebees-worker` recipe installs a worker pinned by digest with a fresh pairing code; the worker then dials out to Orbit as in [chapter 14](14-networking-and-worker-deploy.md). Revoking a worker token and removing a host key are separate actions.
- **Later** (planned): Orbit as a small SSH certificate authority issuing short-lived certificates per agent session; Tailscale SSH and Teleport as bring-your-own options.

## ACDD evidence in Orbit (in progress)

Orbit will show ACDD contracts and TDD evidence from bundlebees: contract hash, RED → GREEN → REFACTOR → integration timeline, per-criterion status and plain-language failures, with "not run" never shown as passed. A read-only model and panel renderer are built on an orbitdesktop branch; wiring them into the board waits for the runnable-by-anyone work. Protocol: [chapter 16](16-acdd-tdd.md).

## What stays the same

- Merges, tags, releases, deploys and publishes stay behind Kyle's explicit yes ([06](06-rules-and-lessons.md)).
- Secrets, tailnet hostnames and private URLs stay out of public repos and out of agent prompts.
- Workers are untrusted until their output is verified independently.
