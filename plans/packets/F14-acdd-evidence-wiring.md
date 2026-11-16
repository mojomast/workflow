# F14 — Wire the ACDD evidence view into the board, feed and a live smoke

- packet_id: F14
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/16-acdd-tdd.md §9 and §10; docs/31-campaign-continuity.md §31.8 (Orbit change map); handoff notes 2026-11-16 (Orbit #26 and #30 merged); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the handoff notes

## Intent

Finish the ACDD evidence view that merged Orbit #26 built and merged #30 bounded: wire it into the
board and the activity feed, and give it a live smoke test against a running server. The view stays
read-only — Orbit only displays; the decision stays with bundlebees' verifier and the human gates —
and it stays per-job evidence, never a campaign closeout, which is exactly the boundary #30's change
map recorded. Wiring the panel into the board is held until the runnable-by-anyone work lands
(sequencing chosen by this packet; docs/16 §9 records only that board chips and the feed are
not wired yet); with #25 merged and F11 drafted, that wait is over.

## Delivered and remaining

| Delivered | Orbit #26 (merged, per the 2026-11-16 handoff notes): the read-only model (`server/acdd-evidence.mjs`), the panel renderer (`src/acdd-evidence-panel.ts`), the token-gated `GET /api/acdd-evidence` route, the Hermes menu and command-palette entry ("ACDD evidence"), dark mode only. Orbit #30 (merged): the boundary doc recording that Orbit's ACDD evidence view is per-job evidence, not a campaign closeout |
| Remaining | Board chips wired to per-card contract status, activity-feed rows for the RED → GREEN → REFACTOR → integration timeline, and a live-server smoke test with fixture evidence — the three items docs/16 §10 still marks planned |

## Acceptance criteria

- AC-001 Each board card with an ACDD contract shows a chip carrying that contract's latest verifier status, derived only from `tdd-evidence/1` verifier records keyed by `contract_sha256`; a card with no evidence shows no chip or a neutral one, never a passing one -> proven by orbitdesktop tests/acdd-evidence/board-chips.test.mjs::chip_reflects_only_verifier_evidence_and_absent_evidence_is_neutral
- AC-002 The activity feed records each RED → GREEN → REFACTOR → integration transition as an entry, and every failure it shows uses the named failure codes from docs/16 §7 verbatim (`red_invalid`, `tests_tampered`, `scope_violation`, `integration_failed`, `unrun`, and the rest) -> proven by orbitdesktop tests/acdd-evidence/activity-feed.test.mjs::feed_rows_carry_named_failure_codes_verbatim
- AC-003 A check that never ran is displayed as unrun, in its own colour, and is never shown as passed anywhere in the view -> proven by orbitdesktop tests/acdd-evidence/activity-feed.test.mjs::not_run_is_never_shown_as_passed
- AC-004 The live smoke starts a real Orbit server on loopback with fixture `tdd-evidence/1` records, calls the token-gated `GET /api/acdd-evidence`, and proves the panel, the board chips and the feed render from what that endpoint returns; the smoke runs offline against fixtures and never talks to a live deployment -> proven by orbitdesktop tests/acdd-evidence/live-smoke.test.mjs::smoke_renders_chips_feed_and_panel_from_a_running_server
- AC-005 The view stays display-only end to end: no chip, feed row or smoke assertion writes evidence, mutates a contract, or stands in for a verifier record or a human gate -> proven by orbitdesktop tests/acdd-evidence/live-smoke.test.mjs::the_view_writes_nothing

## Dependencies

- Orbit #26 (merged 2026-11-16 per handoff notes): the model, panel, route and menu entry this packet wires; their behaviour is the baseline, not something to rebuild
- Orbit #30 (merged 2026-11-16 per handoff notes): the per-job-evidence boundary the wiring must respect
- F11 (drafted): this packet sequences itself after the runnable-by-anyone work, so F11's hermetic-test baseline gates F14's dispatch
- docs/16-acdd-tdd.md §7: the failure-code table the feed must quote verbatim

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge; the smoke test itself needs none because it runs offline on loopback with fixtures
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: deploying anything to the live Orbit host, enabling the Phase 6 observability dashboard (a separate decision in ROADMAP §Observability), making Orbit write evidence, or letting the view imply an acceptance decision

## Next executable action

1. Capture the fixture `tdd-evidence/1` record set for the live smoke (exported from the #26 branch's own fixtures, with one record per phase plus a `unrun` case) so the chip, feed and panel contracts have a stable, offline test target.
