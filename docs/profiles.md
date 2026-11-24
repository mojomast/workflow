# Install profiles

Each profile is a documented bundle: exact components, env (names and where they are set — values are
read from the environment at runtime, never written here), ports, auth posture, and an explicit
cannot-do list. The shared element registry with the dependency graph and recorded pins is
[profiles/repos.json](../profiles/repos.json). The audit behind all of this is
[modularity.md](modularity.md); one copy-paste quickstart per profile lives under
[quickstarts/](quickstarts/contracts.md).

| Profile | What it gives you | Manifest | Quickstart |
|---|---|---|---|
| **contracts** | protocol only: author and check ACDD contracts, lint TDD evidence, run the reference demo — offline, no workers | [contracts.json](../profiles/contracts.json) | [contracts.md](quickstarts/contracts.md) |
| **full** | all four elements (workflow, hyvv, bundlebees, orbitdesktop) at recorded revisions | [full.json](../profiles/full.json) | [full.md](quickstarts/full.md) |
| **observer** | watch only: Orbit boards, sessions and activity with no execution system attached | [observer.json](../profiles/observer.json) | [observer.md](quickstarts/observer.md) |
| **orchestrator** | dispatch, verify, integrate, recover, report: bundlebees plus its pinned workflow and hyvv checkouts | [orchestrator.json](../profiles/orchestrator.json) | [orchestrator.md](quickstarts/orchestrator.md) |
| **worker** | serve attempts: hyvv alone on its host, coordinator elsewhere | [worker.json](../profiles/worker.json) | [worker.md](quickstarts/worker.md) |

Read order: pick a profile from the table, skim its manifest (every referenced path is either checked
into this repo or cited to the chapter that recorded it), then follow its quickstart. Every quickstart
ends with a cannot-do section so nobody mistakes a partial install for the whole loop.

Related: [chapter 12](12-three-layer-architecture.md) (the three-layer split),
[chapter 15](15-agent-agnostic-and-orbit-start.md) (first-run goal, honestly marked in progress),
[chapter 19](19-coordinator-playbook.md) (roles and the stack bottom to top).
