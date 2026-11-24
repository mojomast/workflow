# F12 — Connect-GitHub and the repository picker (the spec of Orbit #27)

- packet_id: F12
- wave: 4
- status: drafted, not dispatched
- repository: mojomast/orbitdesktop
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; dogfood-plan-recovery archive)
- drafted: 2026-11-16 (America/Toronto)
- provenance: ROADMAP.md §Orbit onboarding; docs/15-agent-agnostic-and-orbit-start.md; docs/17-orbit-plans.md (wizard step 2); handoff notes 2026-11-16 (Orbit #27 open); the dogfood-plan-recovery archive was not reachable from this checkout, so the scope below is reconstructed from the in-repo chapters and the handoff notes

## Intent

State, as a reviewable spec, what the open Orbit #27 pull request must deliver: an optional
connect-GitHub step (device flow, or a token stored locally) and a repository picker that makes
"which repos are tracked" a user-managed onboarding decision. This packet is the spec of what that
PR should deliver, not a re-implementation: it does not create a second implementation, rebase or
edit #27, or move work out of the PR's owner lane. Its acceptance criteria are the bar the PR must
meet before a merge yes; any gap found in review goes back to the PR's lane as review findings.

## Delivered and remaining

| Delivered | The design text (ROADMAP §Orbit onboarding, docs/17 wizard step 2) and the open Orbit #27 PR itself, whose existence the 2026-11-16 handoff notes record; nothing from #27 is merged |
| Remaining | The review of #27 against this packet's acceptance criteria, the recorded gap list, #27's merge, and orbitdesktop's docs (`QUICKSTART.md`, `CONFIG.md`) becoming the source of truth once it lands |

## Acceptance criteria

- AC-001 The connect-GitHub step is optional and explicitly user-initiated: skipping it leaves a working install, and no network call to GitHub happens before the user starts the connect flow -> proven by orbitdesktop tests/onboarding/connect-github.test.mjs::skipping_connect_leaves_a_working_install_with_no_github_call
- AC-002 The connect step authenticates through the GitHub device flow, or accepts a token the user pastes; whichever path is taken, the credential is stored only in a user-only file under the runtime directory with 0600 permissions, never in the config file, never in git, never logged, never echoed, and never written into the agent registry as a raw secret -> proven by orbitdesktop tests/onboarding/connect-github.test.mjs::credential_lands_only_in_a_0600_runtime_file
- AC-003 The token is masked in the UI, is never sent to agents or workers, and a revocation or re-auth action removes the stored file completely -> proven by orbitdesktop tests/onboarding/connect-github.test.mjs::token_is_masked_and_revocation_removes_the_file
- AC-004 The repository picker makes the tracked-repo list user-managed: it starts empty (no repository is tracked without the user adding it), accepts adds and removes, and persists the list as user data, not as a shipped default -> proven by orbitdesktop tests/onboarding/repo-picker.test.mjs::picker_starts_empty_and_tracks_only_user_added_repos
- AC-005 Device-flow failure states (expired or denied flow, rejected token, rate limit) are shown to the user as named, actionable states and are never silently retried or swallowed -> proven by orbitdesktop tests/onboarding/connect-github.test.mjs::device_flow_failures_are_named_and_not_silently_retried
- AC-006 The connect and picker flows are testable offline with a stubbed GitHub endpoint; no test in the slice talks to github.com -> proven by orbitdesktop tests/onboarding/connect-github.test.mjs::flows_run_offline_against_a_stubbed_endpoint

## Dependencies

- Orbit #27 (open, per handoff notes): the PR this packet specs; review findings go to its owner lane, not into a parallel implementation
- F11 (drafted): the runnable-by-anyone baseline and vendor-neutral registry the onboarding step registers agents into; the picker and connect step are part of the first-run path docs/15 defines
- ROADMAP.md §Orbit onboarding and docs/17-orbit-plans.md wizard step 2: the design sources this packet freezes into criteria
- Orbit #25 (merged): the merged baseline #27 builds on; #27 must not be merged before #25's fixes are validated (ROADMAP merge order)

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes to merge #27; review comments and gap lists need no approval
- Human gates: merge, release, deploy, publish — all four stay human-gated
- Not authorized by this packet: any agent handling the operator's GitHub credential, any test or run that talks to github.com, storing the token anywhere but the 0600 runtime file, or shipping the three repositories named in ROADMAP (`mojomast/workflow`, `mojomast/bundlebees`, `mojomast/orbitdesktop`) as a hard-coded default — those are one operator's current defaults, recorded here as data, never as a shipped default

## Next executable action

1. Review the open Orbit #27 diff against AC-001–AC-006 and record the gap list as review findings on that PR, without implementing anything outside its lane.
