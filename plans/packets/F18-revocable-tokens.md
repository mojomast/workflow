# F18 — Immediate worker-credential revocation in the Orbit Workers list

- packet_id: F18
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- workflow_ref: d4e6c504884fbf64c86c18033b59484137614646
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/14-networking-and-worker-deploy.md §How to revoke a worker (planned) and §Why this default; docs/06-rules-and-lessons.md (the open-relay lesson: token on every route, loopback bind, constrained access); docs/13-bundlebees-hardening.md §3 (the immutable coordinator lease a cancelled attempt cannot bypass); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the 2026-11-16 handoff notes

## Intent

One action in the Orbit Workers list ends a worker's access immediately: it invalidates that
worker's credential at the source of truth, refuses new claim and refresh requests, cancels
in-flight attempts, and works while the worker is offline — the next reconnect fails closed. This
packet freezes the order of operations the docs already argue for: revocation at the application
layer first, transport teardown second, pairing-material rotation third, and the assumption that
the sandbox was hostile fourth. A mesh membership or an open tunnel is backup, never the primary
control: because the unit of trust is a short-lived scoped worker credential, revoking it is enough
even if the tunnel is still up.

## Delivered and remaining

| Delivered | The documented revocation order in docs/14 (revoke at the source of truth, tear down the transport as a second layer, rotate pairing material, assume a hostile sandbox); the trust rationale in docs/14 §Why this default; the lease model a cancelled attempt must still satisfy |
| Remaining | The Orbit Workers list revocation action wired to the relay credential store, the fail-closed reconnect behaviour, the in-flight-attempt cancellation and evidence quarantine, the offline-revocation guarantee, and the tests below |

## Acceptance criteria

- AC-001 Revoking a worker in the Orbit Workers list invalidates its worker credential immediately: the next claim or refresh request from that worker is refused with a stable error, and no grace window accepts it -> proven by orbitdesktop tests/worker-join/revocation.test.mjs::a_revoked_worker_cannot_claim_or_refresh
- AC-002 Revocation works while the worker is offline: the revoked state is recorded server-side, and when the worker reconnects it is refused before any work item is offered -> proven by orbitdesktop tests/worker-join/revocation.test.mjs::revocation_applies_to_an_offline_worker_on_reconnect
- AC-003 Revoking a worker cancels its in-flight attempt and quarantines the attempt's evidence: nothing from that attempt reaches an accepted wave, and the cancelled attempt still obeys the coordinator's lease record -> proven by orbitdesktop tests/worker-join/revocation.test.mjs::revocation_cancels_and_quarantines_the_in_flight_attempt
- AC-004 Transport teardown stays a separate second layer and is never required to stop claims: with the transport still up (a tunnel, a mesh node, a tailcat address), a revoked worker's requests are already refused -> proven by orbitdesktop tests/worker-join/revocation.test.mjs::transport_teardown_is_not_required_to_stop_claims
- AC-005 The revocation UI states what it does and does not do: it ends the worker's access and cancels attempts, it does not by itself rotate the Orbit listener material, discard a saved tailcat key or expire a mesh node — those remain separate documented actions -> proven by orbitdesktop tests/worker-join/revocation.test.mjs::the_ui_states_what_revocation_does_not_do

## Dependencies

- F15 (drafted): the relay and its scoped worker credentials — the store this action revokes against; without the relay there is nothing to revoke
- docs/13-bundlebees-hardening.md §3: the coordinator-side lease record — a cancelled attempt never gets its file scope from a worker's self-report, so cancellation cannot be talked out of scope
- docs/14-networking-and-worker-deploy.md §How to revoke a worker: the four-step order this packet implements, including "prefer credential revocation first so you do not have to rotate a published join address for one bad worker"

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge; an agent's go-ahead never stands in for it
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: revoking anything on the live host, rotating Orbit admin material, deleting worker records or history, spending resources, pushing to a protected branch

## Next executable action

1. Write the fail-closed reconnect test (AC-002) red first — a revoked worker that comes back online must be refused before any work is offered — then wire the Workers list action behind it.
