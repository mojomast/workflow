# Parked project snapshot

Copy this file to `PARKED.md` at the root of the project's primary repository when the project is parked or archived. Replace every placeholder. Do not delete queued work to make the snapshot shorter. If a section does not apply, keep the heading and write `none`, with a reason.

Do not put secrets, keys, tokens, environment-file contents, patches, prompts, private URLs, IP addresses, or hostnames in this file. Repositories are `owner/name` slugs only. Commit identifiers are full SHAs. Actors are kind-prefixed ids such as `human:owner`, not emails.

Machine-readable state lives in [`.workflow/project-state.json`](../schemas/project-state.schema.json). This file is the human-readable resume snapshot that file points at with `snapshot_path`.

## Identity

- Project id (`project` join key):
- Display name:
- Primary repository (`owner/name`):
- State: parked / archived
- Parked on (UTC, RFC 3339):
- Parked by (kind-prefixed id):
- Reason (already-scrubbed, in the human's own words when the human set it aside):

## Last SHAs

Record the last known full SHA for each repository in the project, and which ref it was on (usually the default branch, plus any in-flight branch that should be resumed).

| Repository (`owner/name`) | Ref | Full SHA | Notes |
|---|---|---|---|
| | | | |

## Open pull requests

| Repository | PR number | Title | Head SHA | Base ref | State when parked |
|---|---|---|---|---|---|
| | | | | | |

## Pending approvals

Write these in the human owner's own words, or quote them verbatim. Each row is something that still needs a human yes (merge, tag, release, deploy, publish, a cancel, or another held action). Do not invent approvals.

| Item | In the human's words | Status when parked |
|---|---|---|
| | | |

## Queued cards

These move to the board's Parked column. They are never deleted. Record enough to restore them to their previous column on unpark.

| Card id | Title | Previous column | Owner or assignee (kind-prefixed id) |
|---|---|---|---|
| | | | |

## In-flight bees and agents

In-flight work is allowed to finish and push its branch. Cancellation requires an explicit human yes and is not implied by parking.

| Bee or agent id | Card id | Branch | Status when parked | Disposition (finish-and-push / cancel-awaiting-yes / cancelled) |
|---|---|---|---|---|
| | | | | |

## Paused routines and watchers

Each entry is paused by the bot that owns it. List the owner so unpark can ask that bot to resume, after a human yes.

| Routine or watcher id | Owner (bot or agent id) | What it does (scrubbed) | Paused |
|---|---|---|---|
| | | | |

## Next steps

Numbered, verbatim, in the order work should resume. Include the first human decision that unpark must ask for.

1.
2.
3.

## Drift notes (fill on unpark, not on park)

Unpark re-checks SHAs and pull request states against this snapshot and writes the drift report here, or in a follow-up section dated on the unpark day. Do not leave this blank after an unpark attempt.

- SHA drift:
- Pull request drift:
- Human decision on drift:
