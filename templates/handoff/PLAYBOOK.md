# Playbook pointer

Your operating method is the coordinator playbook in the method repository:

- `<METHOD REPO>` `docs/19-coordinator-playbook.md`, on `<BRANCH / PR / HEAD SHA>` if it is not on `main` yet.
- How to read an unmerged chapter without cloning guesswork: the forge's contents API at that ref, or the PR's file view.
- Related method chapters, including ones still in open PRs: `<ACDD, PARKING, OBSERVABILITY, …>`.

Core loop (summary; the playbook wins if they differ): freeze a contract → approved failing tests first → dispatch scoped workers → verify each attempt (signed report, scope check, tests) → integrate in a sandbox → record evidence honestly → ask `<APPROVER>` before merge.

## First mission and backlog

- **FIRST-MISSION.md**: `<SHORT NAME>`.
- Backlog: **PROPOSED-STEPS.md**.
