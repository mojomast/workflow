# F17 — One-liner join command that probes transports in a fixed order

- packet_id: F17
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- workflow_ref: d4e6c504884fbf64c86c18033b59484137614646
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/14-networking-and-worker-deploy.md §Worker deploy sketch (planned) and §Why this default; ROADMAP.md §hyvv repo (the versioned /v1 contract and install script the worker image builds on); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the 2026-11-16 handoff notes

## Intent

Give a newcomer one command and no transport guesswork: a worker image whose `join` command probes
transports in a documented fixed order — an HTTPS Orbit URL first, localhost second, tailcat third,
and a mesh client only when a tagged auth material was explicitly provided — then presents the
pairing code and settles into the dial-out loop. The documented shape in docs/14 is documentation,
not a shipped command:

`docker run --rm -it --name bb-worker ghcr.io/mojomast/bundlebees-worker:latest join --code XXXX-YYYY`

with `--orbit-url`, `--tailcat` or `--ts-authkey` overrides for operators who already know their
transport. This packet turns that shape into a real, tested command with a frozen probe order, a
parsed QR payload and a named error when every transport fails — and it keeps the image a
supervisor, not a wide-open Docker socket: it talks to a sibling or nested sandbox runtime that
never sees the worker credential file.

## Delivered and remaining

| Delivered | The documented command shape and probe order in docs/14; the pairing QR payload this command consumes is specified in F15; capabilities advertisement (os, arch, sandbox, gpu) is already part of the worker sketch |
| Remaining | Everything that runs: the worker image itself, the join binary with the fixed probe order, QR payload parsing and validation, the capability advertisement in the first claim, the named failure taxonomy when all probes fail, and the ghcr publication (a release gate, not a code gate) |

## Acceptance criteria

- AC-001 The join command probes transports in the documented fixed order — HTTPS URL, then localhost, then tailcat, then mesh-with-provided-auth — and the order is asserted by a table-driven test that fails if the sequence changes silently -> proven by orbitdesktop tests/worker-join/probe-order.test.mjs::probes_run_in_the_documented_fixed_order
- AC-002 A QR payload carrying an Orbit URL and a tailcat address joins with no extra flags; a QR missing a field degrades with a named error and a printed next step, never a crash or a silent fallback -> proven by orbitdesktop tests/worker-join/probe-order.test.mjs::qr_fields_join_without_extra_flags
- AC-003 An explicit `--orbit-url` or `--tailcat` override skips the earlier probes, and every skipped or failed probe is logged with the reason before the next one is tried -> proven by orbitdesktop tests/worker-join/probe-order.test.mjs::explicit_overrides_skip_earlier_probes_and_are_logged
- AC-004 A joined worker's first claim carries its advertised capabilities (os, arch, sandbox=docker|cua, gpu=nvidia|metal|none) and the coordinator schedules only work that matches them -> proven by orbitdesktop tests/worker-join/probe-order.test.mjs::first_claim_carries_advertised_capabilities
- AC-005 The image runs as a supervisor and hands each attempt to a disposable sandbox runtime that holds no worker credential and no overlay material; nothing in the image path opens the Docker socket to the attempt -> proven by orbitdesktop tests/worker-join/probe-order.test.mjs::the_supervisor_never_hands_the_attempt_its_credential_file

## Dependencies

- F15 (drafted): the relay and the pairing QR payload — the first probe target and the payload schema this command consumes
- F16 (drafted): the tailcat adapter — the third probe and the address format inside the QR
- docs/14-networking-and-worker-deploy.md §Worker deploy sketch: the join flow this packet implements, including the persistent-worker variant (volume for the credential file and logs, systemd or compose unit) that stays out of scope here
- docs/14-networking-and-worker-deploy.md §Sandbox, contract and platforms: the supervisor rule AC-005 freezes, and the platform notes that keep GPU or cloud provider material out of the sandbox

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge; a separate explicit yes before the image is published to ghcr or pinned anywhere outside this repository
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: publishing the worker image, changing the hyvv /v1 contract, mounting the Docker socket into an attempt, or putting any provider or host credential material into the image or the sandbox

## Next executable action

1. Freeze the QR payload schema and write the probe-order table test (AC-001–AC-003) red against a stub join binary, before any image build exists.
