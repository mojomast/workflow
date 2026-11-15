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
- Remaining (unimplemented; total − implemented):
- Note on the distinction:

## Pull requests

`Merge order` is a **1-based position**, not the PR number: one row per open PR,
positions exactly 1..N. Merged and closed PRs leave it blank. The recommended
order at the end of this form is the open PR numbers in that position order.

| Number | URL | Draft? | State | Base | Head SHA | Merge order (1..N) |
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

One audit block per independent review; each needs a `status`:

- `clean` — the review ran and found nothing. `findings` is empty and `head_sha`
  is required. Do not invent an `AF-###` finding to satisfy a shape.
- `findings` — the review ran and found something. `findings` is nonempty and
  each finding has exactly one `fixed`, `rejected` or `deferred` disposition;
  `rejected` and `deferred` require a reason.
- `not_run` — the review did not happen. `findings` is empty and a reason is
  required. It is a disclosed limit, not a pass: a ready report also names it in
  `known_limits`, and a ready report needs at least one audit that actually ran.

The id is stable across reports.

| Source | Status | Head SHA | Finding id | Finding | Disposition | Reason / evidence |
|---|---|---|---|---|---|---|
| | clean / findings / not_run | | AF-001 | | fixed / rejected / deferred | |

## Artifacts and limits

- Screenshots / recordings (viewport and head):
- Performance measurements (metric, value, unit, budget):
- Asset verification:
- Checks not run, with reasons (name each `NOT RUN` criterion by its `AC-###` id):
- Known limits the receiver should weigh:
- Placeholders or fallbacks still visible to a user:

## Handoff

- Recommended merge order (open PR numbers in merge-order position; review aid, not authorization):
- What must not be merged/tagged/released/deployed without the approver:
- Where the full evidence lives:
- Receiver decision: **pending**
