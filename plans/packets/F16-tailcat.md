# F16 — tailcat as the default zero-account NAT fallback

- packet_id: F16
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- workflow_ref: d4e6c504884fbf64c86c18033b59484137614646
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/14-networking-and-worker-deploy.md §What tailcat is, §Fit for this workflow and §Why this default; the tailscale/tailcat repository (BSD-3-Clause, open-sourced 31 August 2026 at TailscaleUp, latest release v0.7.0 of 19 September 2026 at the time of that research); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the 2026-11-16 handoff notes

## Intent

When both sides sit behind NAT and neither wants an account, tailcat becomes the default fallback
transport: Tailscale's official data plane (WireGuard, magicsock, DERP), published under the
BSD-3-Clause licence, with no Tailscale account, no root, no control plane and no system network
changes. The tailcat address travels inside the
same pairing QR as the pairing code, the same worker protocol runs over it as over any other
transport, and the WorkerBackend contract does not change when the transport does. This packet
freezes the honesty rules with the adapter: tailcat is young, its README promises no API, CLI or
wire-format stability, and its original threat model was the same person on both ends — so it ships
pinned to an exact release, behind the pairing layer, with ephemeral keys by default, and with a
documented self-hosted DERP option for serious relayed throughput.

## Delivered and remaining

| Delivered | The written evaluation in docs/14 (what tailcat is and is not, its security model, maturity caveats and install cost); the WorkerBackend contract that keeps networking a transport; the relay design this adapter feeds (F15) |
| Remaining | The tailcat transport adapter itself: a release-pinned integration in the worker backend and an Orbit-side userspace listener whose address is embedded in the pairing QR, the ephemeral-by-default handling with an `--allow` restrict path, the self-hosted DERP documentation, and the tests below |

## Acceptance criteria

- AC-001 The adapter pins one exact tailcat release (v0.7.0 or later at integration time) and refuses to run against an unpinned or floating version -> proven by orbitdesktop tests/worker-join/tailcat-adapter.test.mjs::adapter_pins_an_exact_release
- AC-002 A join over tailcat completes the pairing flow and reaches the relay with no Tailscale account, no root, no TUN device and no routing or DNS change on either side -> proven by orbitdesktop tests/worker-join/tailcat-adapter.test.mjs::join_over_tailcat_needs_no_account_and_no_root
- AC-003 By default the listener uses ephemeral keys that die with the process, so the printed address stops working when the listener exits; a stable key is an explicit choice that names its client keys through `--allow`, and a WireGuard pre-shared key stays on -> proven by orbitdesktop tests/worker-join/tailcat-adapter.test.mjs::ephemeral_keys_die_with_the_listener_process
- AC-004 Dropping the transport does not change the worker protocol: the same claim, event and result messages flow over tailcat, over a plain HTTPS relay URL and over a loopback connection, asserted by one table-driven test -> proven by orbitdesktop tests/worker-join/transport-independence.test.mjs::the_worker_protocol_is_transport_independent
- AC-005 The docs shipped with the adapter state the maturity caveats (no stability promise, early threat model, rate-limited public DERP) and the self-hosted DERP option, and never present tailcat as a mesh, a Tailscale account substitute or Headscale -> proven by orbitdesktop tests/worker-join/tailcat-docs.test.mjs::docs_state_the_caveats_and_the_selfhosted_derp_option

## Dependencies

- F15 (drafted): the relay whose surface tailcat carries; tailcat is a transport under that contract, never a second coordinator
- docs/14-networking-and-worker-deploy.md §What tailcat is: the properties and caveats this packet freezes, including the bearer-capability nature of the address and the rate-limited public DERP
- docs/14-networking-and-worker-deploy.md §Recommendation: "Do not make hosted Tailscale the default" — tailcat is the zero-account fallback, hosted Tailscale stays a power-user overlay

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge, and his explicit yes before a pinned third-party binary (the tailcat release) is added to the worker image or the compose file, because that choice ships a supply-chain dependency
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: making any mesh product the first-run requirement, enabling a stable or saved tailcat key by default, publishing a no-auth tailcat endpoint in DNS, or spending resources on public DERP throughput testing

## Next executable action

1. Freeze the acdd/1 contract for AC-004 (transport independence) against the current bundlebees WorkerBackend contract, and write the table-driven test red against a stub tailcat adapter before the real release pin is chosen.
