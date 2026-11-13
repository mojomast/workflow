# Handoff

Use for one reviewable outcome. Replace placeholders; omit irrelevant fields with a reason. This is a task brief, not an approval record by itself.

## Outcome

- Project and receiving owner:
- User-visible result:
- Why this matters:
- Acceptance criteria, each with an observable check:
- ACDD contract id and `contract_sha256` (see [CONTRACT.md](CONTRACT.md)), or "none (legacy: no ACDD contract; TDD evidence not required)":
- Approved test files and the tests-only RED commit, when the contract is test-first:

## Baseline and inputs

- Repository and full base commit, or source-pack version and checksum:
- Target branch or destination:
- Current spec and revision:
- Required inputs with accessible links or archive-relative paths:
- Relevant prior findings and evidence:

## Decisions and scope

- Chosen direction and constraints:
- Superseded decisions and their replacements:
- Work already authorized by Kyle, with original instruction reference:
- Actions not authorized or explicitly held:
- Assigned files/interfaces and dependencies:
- Budget, tools/environment and stop conditions:
- Assumptions that could materially change the result:

## Production and validation

- Deliverable format and editable source requirements:
- Checks to run, inputs/settings and expected outcomes:
- Failure cases and invariants to preserve:
- Visual or real-host acceptance, when relevant:
- Checks unavailable in this environment:

## Return

Return the artifact/patch, exact revision, changed paths and a completed [RETURN.md](RETURN.md). Include a reproduction for unresolved findings and the next action needed. Report what happened separately from what is proposed. Integration or publication requires the scope already established for the project.
