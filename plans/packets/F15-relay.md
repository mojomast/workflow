# F15 — Coordinator-hosted relay as the product default

- packet_id: F15
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- workflow_ref: d4e6c504884fbf64c86c18033b59484137614646
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/14-networking-and-worker-deploy.md §Recommendation and §Why this default; docs/05-infrastructure-hosting-networking.md (the historical Tailscale-only path stays a power-user overlay); docs/13-bundlebees-hardening.md §6 (WorkerBackend adapter contract); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the 2026-11-16 handoff notes

## Intent

Make the coordinator-hosted relay the documented product default for how a bundlebees worker
reaches Orbit: every worker dials out over HTTPS or a WebSocket (long-poll as the fallback) with a
one-time pairing code, then a short-lived scoped worker credential. No inbound ports on the worker,
no coordinator credentials in the sandbox, and no mesh or account as a first-run requirement. The
unit of trust becomes a worker credential, not a network membership: revoking it is enough to stop
a worker even if a tunnel is still up. localhost stays the zero-setup default when Orbit and the
worker already share a machine — that part is built and must not regress. The NAT fallback and the
probe order that sit on top of this relay are F16 and F17; immediate revocation is F18.

## Delivered and remaining

| Delivered | The `orbit-loopback` adapter is the default when Orbit and the worker share a machine or a compose network (docs/14 §Built versus planned); the application contract a relay has to carry already exists coordinator-side: a brief, an HMAC-signed lease, sandboxed verify and a transport-independent WorkerBackend; docs/14 states the relay recommendation and the reasoning |
| Remaining | Everything that runs: the Orbit join endpoint that mints a one-time pairing code and QR payload, the dial-out relay surface (claim, event stream, evidence upload), scoped worker credentials with a refresh endpoint, the worker-side dial-out client, and the docs that make the relay the documented default in docs/14 and docs/15 |

## Acceptance criteria

- AC-001 Orbit mints a one-time pairing code with an expiry (about 15 minutes, single use) and a QR payload that carries the code, the expiry, an Orbit URL if one is known and a tailcat address if a userspace listener is running, and the QR payload contains no coordinator-wide credential -> proven by orbitdesktop tests/worker-join/pairing.test.mjs::qr_payload_carries_no_coordinator_wide_credential
- AC-002 A worker that presents a valid pairing code once receives a scoped worker credential plus a refresh endpoint, and the same code is refused afterwards -> proven by orbitdesktop tests/worker-join/pairing.test.mjs::pairing_code_is_single_use
- AC-003 The relay accepts claim, event-stream and evidence-upload requests only with a valid scoped worker credential and refuses an unknown, expired or revoked one with a stable error -> proven by orbitdesktop tests/worker-join/relay-auth.test.mjs::relay_refuses_an_unknown_expired_or_revoked_worker_credential
- AC-004 A joined worker never opens an inbound port: it long-polls or holds a WebSocket, advertises its capabilities and waits for leased work, and after a transport drop it reconnects with the same credential until expiry or revocation -> proven by orbitdesktop tests/worker-join/dialout.test.mjs::worker_dials_out_and_never_listens
- AC-005 The relay path keeps the sandbox rule: each attempt runs in a disposable environment with no coordinator credentials, no worker credential and no overlay material, and only the patch and the evidence come back -> proven by orbitdesktop tests/worker-join/relay-auth.test.mjs::the_sandbox_never_holds_a_worker_credential

## Dependencies

- docs/13-bundlebees-hardening.md §6: the WorkerBackend contract the relay must satisfy unchanged — networking is a transport under the contract, not a second API
- docs/14-networking-and-worker-deploy.md §Why this default: the rationale this packet implements, including "the unit of trust is a worker token, not a VPN membership"

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge; an agent's go-ahead never stands in for it
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: running the relay on the live host, spending resources, pushing to a protected branch, or widening the credential model beyond scoped, short-lived worker credentials with revocation

## Next executable action

1. Freeze the acdd/1 contract for AC-001–AC-003 (the pairing and relay-auth invariants) against the current orbitdesktop main head, and write those three tests red before any join endpoint exists.
