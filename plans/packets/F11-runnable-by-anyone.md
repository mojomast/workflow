# F11 — Runnable-by-anyone follow-ups on Orbit

- packet_id: F11
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/15-agent-agnostic-and-orbit-start.md; docs/17-orbit-plans.md; handoff notes 2026-11-16 (Orbit #25/#26/#30 merged, #27 open); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the handoff notes

## Intent

Close the runnable-by-anyone gaps that Orbit #25 left undone, so that a stranger — someone with none
of the maintainer's setup — can clone orbitdesktop, run its tests and start Orbit from a fresh
checkout with no author-machine paths, no maintainer home-directory state and no assumed agent
vendor (docs/15). The slice is deliberately test-and-registry-first: hermetic tests prove the
runnable-by-anyone claim mechanically, the agent registry removes the one-vendor assumption, and
the stranger quickstart documents the path that those two make true. First-run onboarding details
that go beyond this slice are specced in F12 (connect-GitHub and repo picker) and F13 (router);
this packet does not absorb them.

## Delivered and remaining

| Delivered | Orbit #25 (merged, per the 2026-11-16 handoff notes) landed the first runnable-by-anyone slice on orbitdesktop; PR #24 (2026-11-12) had already reconciled `main` with the live tree so later work starts from what actually runs |
| Remaining | Hermetic tests, a vendor-neutral agent registry, the stranger quickstart and the adapter docs that go with it — the follow-ups docs/15 lists as "in progress, not done" and that #25 did not carry |

## Acceptance criteria

- AC-001 The orbitdesktop test suite runs hermetically from a fresh clone on a machine with none of the maintainer's setup: no absolute author paths, no reads or writes outside the repo tree and its own temp dirs, no network beyond committed fixtures -> proven by orbitdesktop tests/runnable-by-anyone/hermetic.test.mjs::suite_runs_from_a_fresh_clone_in_a_scratched_home
- AC-002 No test or fixture depends on the author's home directory, environment variables or machine-local state; a scan for such dependencies is part of the suite and fails loudly on a violation -> proven by orbitdesktop tests/runnable-by-anyone/no-author-machine-paths.test.mjs::no_test_references_an_author_machine_path
- AC-003 The agent registry does not assume one vendor: an agent entry carries its adapter kind explicitly, registering a second kind requires no code change, and no registry code names a single vendor as a default -> proven by orbitdesktop tests/runnable-by-anyone/agent-registry.test.mjs::registry_admits_two_adapter_kinds_without_code_change
- AC-004 A stranger quickstart in orbitdesktop's docs takes a fresh clone to a running Orbit with one documented command, then to a first agent, and every command it names is the command a test or script actually exercises -> proven by orbitdesktop tests/runnable-by-anyone/quickstart.test.mjs::every_quickstart_command_is_exercised

## Dependencies

- Orbit #25 (merged 2026-11-16 per handoff notes): the baseline this packet follows up on; its merged diff must be read before any contract is frozen, because the packet's delivered-vs-remaining split is reconstructed from docs/15 and the handoff notes, not from the PR body
- docs/15-agent-agnostic-and-orbit-start.md ("What is in progress, not done"): the authoritative list of runnable-by-anyone slices this packet implements
- F12 (drafted): the onboarding details that connect-GitHub and the repo picker add; out of scope here, sequenced after this packet's registry slice
- F13 (drafted): the router step of the wizard; out of scope here

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for the merge; an agent's go-ahead never stands in for it
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: deploying anything to the live Orbit host, spending resources, pushing to a protected branch, or turning any documented quickstart claim into a shipped promise before its test exists

## Next executable action

1. Read the merged Orbit #25 diff on mojomast/orbitdesktop and record, in the campaign plan, which of docs/15's runnable-by-anyone slices it actually delivered, before any contract for this packet is frozen.
