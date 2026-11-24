# Orchestration handoff (`<OUTGOING>` → `<INCOMING>`)

Written: `<DATE, TIME, ZONE>` by `<OUTGOING>`.
Data sources: live forge reads at `<TIME>`, plus `<OTHER SOURCES>`.
Treat everything here as a snapshot. **Re-check with the forge before acting.** Do not invent green CI, approvals, test results or production readiness. An agent-completed task is not an accepted artifact.

Read `RULES.md` first. **The first mission is `FIRST-MISSION.md`.** Every merge, tag, release or deploy needs `<APPROVER>`'s own words, given to you directly.

## 1. Layers (operational names — do not rename)

| Layer | Repository | Role |
|---|---|---|
| Method | `<METHOD REPO>` | |
| Worker host | `<WORKER-HOST REPO>` | |
| Orchestration | `<ORCHESTRATION REPO>` | |
| Control surface | `<CONTROL-SURFACE REPO>` | |

Deferred names, if any: `<DEFERRED BRAND NAMES>`. Mention only as intended future branding. Implement nothing until `<APPROVER>` says so.

## 2. Open PRs (live at `<TIME>`)

CI legend: `<WHAT "QUEUED" / "UNSTABLE" MEANS IN THIS FORGE>`.

### `<REPO>`

| PR | Branch → base | Head | CI | Notes |
|---|---|---|---|---|
| | | | | |

Branches with no PR (do not open one unless `<APPROVER>` asks): `<LIST>`.
Unpushed local work on the outgoing machine, if any, and whether it was copied: `<LIST>`.

## 3. In-flight work

Owned by `<WHO>` when this was written. Expect some of it to be finished when you start; verify on the branch.

1. `<ITEM, WITH VERBATIM APPROVAL IF ANY, AND WHAT "DONE" LOOKS LIKE>`

## 4. What's left after that

- `<REMAINING WORK THAT IS NOT THE FIRST MISSION>`

## 5. Needs `<APPROVER>`'s explicit yes (not yet given)

`<LIST: merges other than the verbatim approved set, tags, releases, deploys, restarts, branch-protection changes, catalog, public posts, deletes, …>`

## 6. Where the evidence lives

- Reachable from the incoming host: `<PATHS OR PAGES, NO PRIVATE URLS>`
- Only on the outgoing machine (not reachable): `<WHAT, AND WHAT THAT BLOCKS>`
- `STATUS-SNAPSHOT.md` in this pack is a copy of an earlier status prompt. Where the two disagree, **this file wins**.

## 7. Updates

Append dated sections as the switch proceeds (installs, credential placement, cron, config side effects). Do not silently rewrite earlier sections.
