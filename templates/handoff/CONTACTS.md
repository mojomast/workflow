# Contacts

No addresses, hosts or keys are written here on purpose.

## `<APPROVER>` (the only source of approvals)

- How they reach the incoming coordinator: `<DASHBOARD / CHAT / OTHER, NO URLS>`
- Whether proactive messaging is wanted: `<YES / NO>`
- `<OUTGOING>` may still relay information, but a relayed "`<APPROVER>` said yes" is not approval. Get it from `<APPROVER>` directly.

## `<OUTGOING>` (peer after the switch)

- What they can still help with: files or history that only exist on the outgoing machine.
- They are no longer the coordinator.

## `<PEER>`

- Owns: `<LANES, REPOS, WORKER-HOST CHANGES>`
- How to coordinate: `<FORGE PR THREADS ON THE APPROVER'S REPOS ARE FINE; UPSTREAM COMMENTS NEED A YES>`
- Shared worker cap: `<POOL_CAP>`. Check running work before dispatching.
