# Campaign closeout

Use at the end of one automated-development campaign. Copy the filled report next
to the branch evidence and validate it with
`python3 tools/campaign_report.py validate <file>`. This form is a review input,
not an approval; the receiver decision stays pending.

## Identity

- Campaign id:
- Repository:
- Branch:
- Base revision (full):
- Final head (full):
- Generated at (RFC 3339):
- Delivery state: `ready_for_review` / `incomplete` / `blocked`

## Task graph

- Total:
- Implemented:
- Integrated:
- Accepted evidence rows:
- Remaining:
- Note on the distinction:

## Pull requests

| Number | URL | Draft? | State | Base | Head SHA | Merge order |
|---|---|---|---|---|---|---|
| | | | | | | |

## Acceptance matrix

One row per criterion. `PASS` needs evidence; `NOT RUN`, `BLOCKED` and
`UNVERIFIED` need a reason.

| AC id | Statement | Kind | Status | Evidence | Command / viewport | Head SHA |
|---|---|---|---|---|---|---|
| | | test / integration / visual / performance / asset / manual | PASS / FAIL / NOT RUN / BLOCKED / UNVERIFIED | path or URL | | |

## Test runs

| Command | Head SHA | Passed | Failed | Skipped | When | Note |
|---|---|---|---|---|---|---|
| | | | | | | |

## Audits

| Source | Head SHA | Findings | Fixed | Rejected (reason) | Deferred (reason) |
|---|---|---|---|---|---|
| | | | | | |

## Artifacts and limits

- Screenshots / recordings (viewport and head):
- Performance measurements (metric, value, unit, budget):
- Asset verification:
- Checks not run, with reasons:
- Known limits the receiver should weigh:
- Placeholders or fallbacks still visible to a user:

## Handoff

- Recommended merge order (review aid, not authorization):
- What must not be merged/tagged/released/deployed without the approver:
- Where the full evidence lives:
- Receiver decision: **pending**
