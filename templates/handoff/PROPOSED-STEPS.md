# Proposed steps / status

Updated: `<DATE, TIME, ZONE>`.

## Done (`<APPROVER>` approved)

- `<ITEM>`

## Blocked / needs a decision

1. `<ITEM AND THE OPTIONS, WITH WHAT A YES WOULD AUTHORIZE>`

## Incoming coordinator backlog

- Named, scoped, independently revocable worker-host tokens, if the handoff used a shared token. Design and tests first; installing them on the live worker host needs a yes.
- Own control-surface instance on the incoming host, if required by the dependency audit. Prefer a second instance with its own port, service, data and token when an older instance already runs there. Measure headroom; run under `nice`/`ionice` with a memory cap. **Deploy and start need a yes.** Do not run unmerged feature-branch code on the incoming host.
- Route verify/integrate into worker containers if the incoming host cannot sandbox (see `CAPABILITIES.md`). Do not relax the host's security policy.
- `<FIRST MISSION, IF NOT ALREADY STARTED>`
- `<OTHER BACKLOG>`

## Requirements: no dependence on the outgoing coordinator's surfaces

Quote the approver if they said this directly:

```text
<VERBATIM, IF ANY>
```

- **R1 Board / task queue:** `<REPLACEMENT>`
- **R2 Artifact or patch retrieval:** `<REPLACEMENT>`
- **R3 Observability / evidence:** `<REPLACEMENT>`
- **R4 Verify/integrate sandbox:** `<REPLACEMENT>`
