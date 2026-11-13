# Changelog

## Unreleased

### Added

- [20 Orchestrator handoff](docs/20-orchestrator-handoff.md) and the [handoff kit](templates/handoff/): how to switch coordinators mid-stream. It covers recon of the incoming host, the pack contents, approvals that carry over only as the approver's verbatim words, shared credentials now with named tokens later, plugin install with a backup, a rollback script and a post-install config diff, fail-closed automation for already-approved merges, an audit of dependence on the outgoing control surface, sandbox gaps left fail-closed, a kickoff prompt with three verification actions, the outgoing coordinator stopping new work, and a checklist.
