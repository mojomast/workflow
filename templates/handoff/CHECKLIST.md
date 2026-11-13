# Orchestrator handoff checklist

Tick in place. Do not invent a green row. See [docs/20-orchestrator-handoff.md](../../docs/20-orchestrator-handoff.md) §13.

## Approver

- [ ] Has said, in their own words, that coordination should move, and to whom
- [ ] Has said how they will talk to the incoming coordinator
- [ ] Has confirmed which in-flight approvals still stand, verbatim
- [ ] Has approved each live-host step that needs a yes (credential placement, plugin install and restart, scheduled merge job, worker-host admin, a new control-surface instance)

## Outgoing coordinator

- [ ] Has stopped adding work; in-flight items are finished or written into the pack
- [ ] Recon of the incoming host is in `CAPABILITIES.md`
- [ ] Pack is on the incoming host (and a copy the approver can read), with no secrets in it
- [ ] Approvals are quoted verbatim, with scope and the definition of green
- [ ] Credentials are in the incoming environment file (mode `0600`), backed up, verified, never printed
- [ ] Named, scoped tokens (if still needed) are on the incoming backlog, not started as outgoing work
- [ ] Plugin install has a backup and a rollback script; post-install config was diffed; collateral changes were restored
- [ ] Fail-closed merge automation covers only the verbatim approved PRs; dry-run was read; it will not race another merger
- [ ] Dependencies on the outgoing control surface are audited; replacements are requirements, not hopes
- [ ] Sandbox gaps are recorded and left fail-closed
- [ ] Kickoff prompt is current, with three verification actions, and contains no private hosts or secrets
- [ ] Peer agents have been told about the switch and still own their lanes

## Incoming coordinator (first session)

- [ ] Read `RULES.md` first, then the rest of the pack in order
- [ ] Re-checked live PR heads and CI; did not trust the snapshot
- [ ] Completed the three kickoff verification actions and reported them
- [ ] Started only the first mission, under the standing worker cap
- [ ] Asked the approver before anything not already quoted in `RULES.md`
