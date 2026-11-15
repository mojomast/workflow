# CAPABILITIES — recon template for the executor host

Fill this in on your host, read-only, before changing anything ([docs/20 §3](../../docs/20-orchestrator-handoff.md)). Re-run after every install or restart. Record gaps fail-closed: a missing capability is a hard gap, never a hint to relax policy.

| Area | What to record | Your finding |
|---|---|---|
| Runtime | Agent version, install method, gateway/dashboard health | TODO |
| Models and keys | Provider names and key **names only** (never values) | TODO |
| Plugins | Enabled/disabled, versions, pinned SHAs | TODO |
| Forge access | Account, scopes; whether it *could* merge (ability ≠ permission) | TODO |
| Secret scan | Tool, version, checksum-verified install path | TODO |
| Local clones | Repos, fetched branches, dedicated venv | TODO |
| Worker host (hyvv) | Reachability + auth: unauthenticated denied (not timeout), authenticated succeeds | TODO |
| Control surface | What already runs here (don't hijack an existing instance) | TODO |
| Sandbox | Can this host run bwrap or firejail verify? (`unshare` is never auto-selected) | TODO |
| Scheduling | Cron/systemd equivalents present; existing jobs (don't duplicate merge automation) | TODO |
| Messaging | How Kyle talks to you | TODO |
| Headroom | Disk, memory, CPU, existing load | TODO |

## Known gaps to expect (from the workflow docs)

- If the kernel blocks unprivileged user namespaces, bwrap refuses — that is correct fail-closed behaviour; record it and route verify/integrate to isolated worker containers per [docs/20 §10](../../docs/20-orchestrator-handoff.md). Do not relax host policy.
- A loopback-only worker-host bind will not serve a remote coordinator; confirm before promising dispatch.
- If gitleaks is missing, do not push from this host until it is installed checksum-verified.

## Sandbox routing decision (fill after recon)

- [ ] Local bwrap/firejail available → verify locally
- [ ] Local sandbox unavailable → route verify/integrate to worker-host containers, record in PROPOSED-STEPS.md as real backlog work
