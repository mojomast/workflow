# F19 — Live-host join install, rehearsed on a throwaway target first

- packet_id: F19
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- workflow_ref: d4e6c504884fbf64c86c18033b59484137614646
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/14-networking-and-worker-deploy.md §Worker deploy sketch and §How to revoke a worker; docs/17-orbit-plans.md §SSH hosts (the add-host flow, restricted authorized access line and fully shown bootstrap this recipe rides on); ROADMAP.md §Real-agent dogfood rerun; the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the 2026-11-16 handoff notes

## Intent

Prove the join flow end to end on a real second machine before anyone touches the live host: the
bundlebees-worker recipe installed through Orbit's SSH-hosts flow — a worker pinned by image digest,
started with a fresh pairing code, joined through the relay (F15) with the join command's probe
order (F17) — then one honest brief claimed, verified and integrated, and one revocation drill (F18)
performed, all recorded in a checklist that marks every step run or not run. The live host itself is
out of scope for this packet: the rehearsal runs against a throwaway target, and a live-host install
remains a separately approved action with its own explicit yes.

## Delivered and remaining

| Delivered | The SSH-host add flow in Orbit (in progress per docs/17: restricted authorized-access line or a short fully shown bootstrap, strict host-key pinning after first use, per-agent permission levels); the join flow design in docs/14; the recipe requirement — a worker pinned by digest with a fresh pairing code |
| Remaining | The staged bundlebees-worker recipe, the rehearsal script and checklist, one recorded rehearsal run against a throwaway target (join, one honest brief, one revocation drill, teardown), the go/no-go note for a future live-host install, and the tests below |

## Acceptance criteria

- AC-001 The bundlebees-worker recipe installs a worker pinned by image digest (never a floating tag) and starts it with a fresh single-use pairing code on a throwaway target -> proven by orbitdesktop tests/worker-join/recipe.test.mjs::recipe_installs_a_digest_pinned_worker
- AC-002 The rehearsed worker joins a locally running Orbit through the relay and claims and completes one honest brief end to end — dispatch, verify, accepted wave — with no manual step outside the checklist -> proven by orbitdesktop tests/worker-join/recipe.test.mjs::the_staged_worker_completes_one_honest_brief
- AC-003 The rehearsal includes one revocation drill: the worker is revoked mid-session, its credential stops working, its in-flight attempt is quarantined, and the checklist records the drill as run with its observed behaviour -> proven by orbitdesktop tests/worker-join/recipe.test.mjs::the_rehearsal_records_one_revocation_drill
- AC-004 The rehearsal checklist records, for every step: the image digest, the pairing-code lifetime and single-use behaviour, the transport actually probed, the revocation drill result and the teardown state, with never-run recorded as not run, never as passed -> proven by orbitdesktop tests/worker-join/recipe.test.mjs::the_checklist_records_every_step_and_never_marks_unrun_as_passed
- AC-005 No rehearsal step reads or writes the live host's configuration, worker records or saved pairing material, and the recipe refuses a target that resolves to the live host -> proven by orbitdesktop tests/worker-join/recipe.test.mjs::the_rehearsal_never_touches_the_live_host

## Dependencies

- F15 (drafted): the relay this rehearsal joins through
- F17 (drafted): the join command and its fixed probe order — the rehearsal exercises the real command, not a shortcut
- F18 (drafted): the revocation drill the checklist must include
- docs/17-orbit-plans.md §SSH hosts: the install path this recipe rides on, with its strict host-key pinning and per-agent permission levels
- docs/14-networking-and-worker-deploy.md §How to revoke a worker: "assume the sandbox was hostile" — the rehearsal discards the attempt worktree and ignores any patch that did not pass the combined-branch suite

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge; a separate explicit yes before any live-host install, exactly as ROADMAP requires for changes to the live worker host
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: installing or changing anything on the live host, spending resources beyond the throwaway rehearsal target, pushing to a protected branch, publishing the worker image, or treating a rehearsal result as a live-host claim

## Next executable action

1. Write the recipe tests (AC-001 and AC-005) red against a stub installer, then stage the rehearsal checklist — the throwaway target must exist before the first real join is attempted.
