# F13 — Bifrost opt-in router via a Compose profile

- packet_id: F13
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/17-orbit-plans.md §Token router; ROADMAP.md §Orbit onboarding; handoff notes 2026-11-16 (no router PR exists yet); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the handoff notes

## Intent

Turn docs/17's router design into delivered Orbit behaviour: Bifrost as the default router choice,
strictly opt-in through a Docker Compose profile, so that a normal `docker compose up` starts
nothing router-related and the wizard sets the profile only when the user chooses the router. The
router never becomes a second orchestrator or a required component; when it is not selected,
nothing runs. This packet freezes the off-by-default invariants and the key-handling rules first,
because those are the properties that must hold even before any UI exists.

## Delivered and remaining

| Delivered | The written design (docs/17 §Token router, ROADMAP §Orbit onboarding "Bifrost as an opt-in router"); no router code, compose entry or wizard wiring exists on orbitdesktop |
| Remaining | Everything that runs: the compose profile entry, the pinned image, the generated 0600 env file, per-role virtual keys, the wizard wiring, the non-Docker subprocess path, the docs (`ROUTER.md` becomes source of truth when landed) and the tests below |

## Acceptance criteria

- AC-001 With the router not selected, nothing runs: `docker compose config` shows no router service, no container, no process, no port and no router config file exists after a fresh start -> proven by orbitdesktop tests/router/off-by-default.test.mjs::no_selection_starts_nothing
- AC-002 Choosing the router is the only thing that enables it: the router service carries `profiles: ["router"]` and the wizard sets that profile only when the user chooses the router -> proven by orbitdesktop tests/router/off-by-default.test.mjs::only_the_router_profile_starts_the_router_service
- AC-003 The Bifrost image is pinned by version and digest, runs read-only with dropped capabilities and exposes no host port by default -> proven by orbitdesktop tests/router/off-by-default.test.mjs::image_is_digest_pinned_read_only_and_portless
- AC-004 Upstream provider keys live only in a generated env file with 0600 permissions — never in the config file, never in git, never in agent-visible state — and each role gets its own virtual key with a budget and rate limits (editable defaults) -> proven by orbitdesktop tests/router/keys.test.mjs::upstream_keys_stay_in_a_0600_generated_env_file
- AC-005 Agents are pointed at the router's OpenAI- or Anthropic-compatible base URL with their role's virtual key, and no agent or worker output, log or registry entry contains an upstream key -> proven by orbitdesktop tests/router/keys.test.mjs::agents_see_only_the_router_base_url_and_virtual_key
- AC-006 On non-Docker installs the router, when chosen, runs a checksum-pinned binary as a subprocess; LiteLLM appears only under Advanced, installed by image digest, never a floating tag; the external-router mode (one URL, one key) starts nothing locally -> proven by orbitdesktop tests/router/modes.test.mjs::binary_litellm_and_external_modes_follow_the_pin_rules
- AC-007 OpenCode free models stay a direct provider used by the OpenCode adapter, never routed, and this is stated in the router docs and asserted in the tests -> proven by orbitdesktop tests/router/modes.test.mjs::opencode_free_models_stay_direct

## Dependencies

- docs/17-orbit-plans.md §Token router: the design this packet freezes; it is the source of truth until orbitdesktop's `ROUTER.md` takes over
- F11 (drafted): the onboarding wizard base whose step 1 ("choose what to install") is where the router choice is made
- F12 (drafted): the connect-GitHub and repo-picker steps of the same wizard; the router step must compose with them, not duplicate them
- ROADMAP.md §Orbit CI and branches: "Document the Docker-mode router limitation, and do not mount the Docker socket" — a standing constraint on any router work in Orbit

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge, and his explicit yes before a pinned third-party image (Bifrost, and LiteLLM under Advanced) is added to the compose file, because that choice ships a supply-chain dependency
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: starting a router in any test, CI run or default install; mounting the Docker socket; unpinning any image; routing the OpenCode free models; running LiteLLM outside the Advanced choice

## Next executable action

1. Freeze the acdd/1 contract for AC-001–AC-003 (the off-by-default invariants) against the current orbitdesktop main head, so the strongest property lands before any router service is added.
