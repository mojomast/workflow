# 18 — Parking and setting a project aside

A project can be set aside without throwing away its work. This chapter is the protocol for that: three states, a machine-readable source of truth in the repo, a drain so in-flight work can finish safely, a resume snapshot, and a one-command unpark that checks for drift.

It is a **spec**. Nothing in this pull request implements enforcement in hyvv, bundlebees, or Orbit. Interface proposals for those layers are listed as proposals. Implementation work is split at the end of this chapter. Merging, tagging, releasing, or deploying any of that still needs the human owner's yes.

This chapter is numbered 18 so it can sit after the contract-first chapters that land in [workflow pull request #5](https://github.com/mojomast/workflow/pull/5). It does not edit those files, and it does not edit the observability records in [workflow pull request #8](https://github.com/mojomast/workflow/pull/8).

Related chapters: [07](07-projects.md) is how projects are described; [09](09-reproducible-collaboration.md) is the portable loop this snapshot has to be enough to resume; [12](12-three-layer-architecture.md) is the three-layer split; [15](15-agent-agnostic-and-orbit-start.md) is the agent-agnostic goal this file format has to serve.

## 1. Goal

The human owner can say "set this project aside" and have every agent, bee, board, and worker host honor that, without deleting cards, losing branches, or needing a unique procedure per project.

The same mechanism works in reverse: one unpark command validates the snapshot, reports drift, restores queued work, and resumes paused routines only after a human yes.

The mechanism is **agent-agnostic**. The source of truth is a file in the project's primary repository, not a setting inside Orbit, hyvv, bundlebees, a Grok Bot, or Hermes. Those systems read the file. They do not each keep a second, competing state.

## 2. States

A project is in exactly one of three states:

| State | Meaning |
|---|---|
| `active` | Normal work. New bees, new cards, routines and watchers are allowed, subject to the rest of the workflow. |
| `parked` | Set aside, intended to be resumed. New bees and new work cards are refused. In-flight bees drain. Queued cards sit on the Parked column. Routines and watchers for the project are paused. History is kept. |
| `archived` | Set aside with no current plan to resume. The same drain rules as `parked` apply. The project stays in history and out of in-flight and spend views. Unarchive uses the same unpark command, and still needs a human yes. |

Every change of state records:

- `state` — the new state
- `changed_at` — an RFC 3339 UTC timestamp at second precision
- `changed_by` — a kind-prefixed actor id, such as `human:owner` or `agent:hermes-forge` (not an email, hostname, or secret)
- `reason` — already-scrubbed text. When the human set the project aside, this is the human's own words, or a faithful short paraphrase the human has accepted.

Allowed transitions are `active → parked`, `active → archived`, `parked → active`, `parked → archived`, and `archived → active`. A no-op write that does not change `state` is not a transition and must not append history. There is no `parking` state: the project becomes `parked` (or `archived`) immediately, and drain is a consequence of that state, not a fourth value.

## 3. Source of truth

The source of truth is `.workflow/project-state.json` in the **primary repository** of the project. The JSON Schema is [`schemas/project-state.schema.json`](../schemas/project-state.schema.json) (`schema`: `workflow.project-state/v1`).

Orbit, the board, hyvv, and bundlebees all read that file (or a locally cached copy that is refreshed before a dispatch or a state-changing action). They do not invent a parallel store. A cache that cannot be refreshed is not authority for starting new work.

For a project that spans several repositories, one repository is primary and holds the file. The resume snapshot lists the others. Other repositories may carry a pointer or a copy, but if they disagree, the primary file wins, and the disagreement is reported as drift.

### Missing or invalid files

| Condition | New bees and new work cards | In-flight work |
|---|---|---|
| File is absent | Treat the project as `active` (backward compatible). Record that the state was defaulted, not read. | Unchanged. |
| File is present but invalid or unreadable | **Refuse** new bees and new work cards (fail closed). Report that the state file is invalid. | Unchanged. Do not cancel in-flight work because the file is invalid. |
| File is valid | Honor `state`. | Drain rules in [§4](#4-parking-is-a-drain) when `state` is `parked` or `archived`. |

The current state's `state`, `changed_at`, `changed_by`, and `reason` are also the last entry in `history`. `history` is append-only, oldest first. `snapshot_path` is required when the state is `parked` or `archived`, and is a repo-relative path, usually `PARKED.md`.

The file, the snapshot, and any `project.state/v1` event must not contain secrets, keys, tokens, environment-file contents, patches, prompts, private URLs, IP addresses, or hostnames.

## 4. Parking is a drain

Parking (and archiving) is not a hard stop of work already running. It is a drain.

1. **No new bees** for that project. hyvv and bundlebees refuse a dispatch, as in [§7](#7-enforcement-interface-proposals).
2. **No new work cards** for that project. A note that only records the park itself, or a card moved onto the Parked column as part of the drain, is not a new work card.
3. **In-flight bees finish** their current lease and **push their branches**. They must not start a follow-on card or a new lease on the same project.
4. **Cancellation of in-flight work** happens only with an **explicit human yes** for the named bees or agents. Parking does not imply cancellation.
5. **Queued cards move to a Parked column.** They are never deleted. Each card keeps its id and a record of the column it came from, so unpark can restore it.
6. **Routines and watchers** tied to the project are **paused by the bot that owns them**. The park action records the owner and the item in the snapshot; it does not reach inside another bot. Owners are responsible for honoring the state file. Resume needs a human yes ([§6](#6-unpark)).

A board that has no Parked column yet must create one before moving cards, or it must refuse the park until it can do so without deleting or dropping cards.

## 5. Resume snapshot (`PARKED.md`)

The human-readable resume snapshot is [`templates/PARKED.md`](../templates/PARKED.md). When a project is parked or archived, a filled copy lives at the path in `snapshot_path` (by default `PARKED.md` at the root of the primary repository).

The snapshot must include:

- project id, display name, primary repository as `owner/name`, state, parked-on, parked-by, and the reason
- last known full SHA and ref for every repository in the project
- open pull requests (repository, number, title, head SHA, base ref, state when parked)
- pending approvals **in the human's own words**
- queued cards and the column they came from
- in-flight bees and agents, with branch and disposition
- paused routines and watchers, with the owning bot
- numbered next steps, in resume order
- a drift section, left to be filled on unpark

A worked skeleton for Temple of Hermes is in [`examples/temple-of-hermes/`](../examples/temple-of-hermes/README.md). It is marked **to be filled by Hermes Forge** and is not itself the source of truth in those repositories.

On a successful unpark, the snapshot is kept under `.workflow/history/PARKED-<UTC date>.md` (or the same path with a unique suffix). The root `PARKED.md` is removed or replaced with a short pointer to that history file so the repository does not look parked. History is not deleted.

## 6. Unpark

Unpark is **one command** (an Orbit action, or a documented command that does the same steps). It applies to both `parked → active` and `archived → active`. It does not start work on its own. It:

1. Reads `.workflow/project-state.json` and the snapshot at `snapshot_path`.
2. **Validates** the state file against `workflow.project-state/v1`, and checks that the snapshot has every required section from the template, with no `TBD` or empty required cells left over from a skeleton.
3. **Re-checks SHAs and pull request states** against the snapshot and writes a drift report:
   - **Informational:** the recorded ref has moved forward along the same history (new commits after the recorded SHA).
   - **Blocking until a human decides:** a recorded SHA is no longer on that ref (rewrite or delete); a recorded open pull request is merged, closed, or has a different head SHA; a recorded in-flight branch is missing; the primary state file disagrees with a copy in another repository.
4. If validation fails, or blocking drift has no human decision, **stop**. Do not change `state`, do not move cards, do not resume routines.
5. After a clean check, or after the human accepts the drift report, write `state: active` with a reason, timestamp, and actor, and append `history`.
6. **Restore queued cards** from the Parked column to the previous column recorded in the snapshot.
7. **Resume routines and watchers only after a human yes**, item by item or as a named group the human has approved. The owning bot performs the resume. A missing yes leaves that item paused and is reported, not ignored.

The command may be invoked by an agent, but the human yes for drift, and the human yes for resuming routines, cannot be supplied by the agent that wants to continue the work.

## 7. Enforcement (interface proposals)

These are proposals for other repositories. This pull request does not change hyvv or bundlebees.

### hyvv `/v1`

The hyvv `/v1` operation that starts a bee or attempt for a project (dispatch) **refuses** a project whose primary `.workflow/project-state.json` is `parked` or `archived`.

Proposed error:

- HTTP **409**
- machine-readable code `project_parked` or `project_archived`
- body includes `project`, `state`, and a short message, with no secrets or hosts

Proposed override: a request field such as `park_override` with a required non-empty `reason`. The override is attributable (`changed_by` or the authenticated dispatcher) and is persisted in the attempt or audit log. A missing reason is not an override. This spec recommends that production deployments also require a human yes for an override; the minimum contract is flag plus reason, persisted.

`GET /v1/version` (or the equivalent capabilities document) should advertise `project_state: v1` once this is implemented, so clients can detect the refusal instead of treating it as a generic conflict.

Cancelling an in-flight bee remains a separate operation and still requires an explicit human yes. A park override does not cancel anything.

### bundlebees

The beekeeper refuses to dispatch a brief or bee for a parked or archived project, with the same codes, unless the same override (flag plus reason, persisted) is present.

bees.ps1 (or its successor in hyvv) also refuses to start work for that project when it can read the state file, so a bee that is launched around the beekeeper still stops.

A bundlebees check (tests or a coordinator pre-dispatch gate) confirms that those refusals hold, including the invalid-file fail-closed case in [§3](#3-source-of-truth).

## 8. Observability

Parked and archived projects **drop out of in-flight and spend views**. They **remain in history**. A view that cannot tell the project's state must not invent one; it should show the project as state unknown rather than treat a missing filter as "active and in spend."

This chapter does **not** edit `agent.lifecycle/v1` or any file under `observability/` from [workflow pull request #8](https://github.com/mojomast/workflow/pull/8). Alignment is by reference:

- The project id in `.workflow/project-state.json` is the same `project` join key used by `agent.lifecycle/v1`.
- A new event, `project.state/v1`, is defined in [`schemas/project-state-event.schema.json`](../schemas/project-state-event.schema.json). It uses the same RFC 3339 timestamps, the same `project` join key, and the same scrubbed-text rule as `agent.lifecycle/v1`.
- In-flight and spend views include a project only when its latest `workflow.project-state/v1` (or latest `project.state/v1` event) is `active`. History views include all states.
- A later, additive field such as `project_state` on `agent.lifecycle/v1` or `board.snapshot/v1` may be proposed in a follow-up to pull request #8. It is not added here.

Token and cost figures stay in the Hermes Forge usage record (`bee.usage/v1`, draft on [workflow pull request #7](https://github.com/mojomast/workflow/pull/7)). Filtering spend by project state does not create a second usage schema.

## 9. Acceptance criteria

These criteria are ACDD-ready. Each has a stable id. Implementation work in Orbit, hyvv, and bundlebees should map each `test` or `review` criterion to a collected test id when those changes are built. This pull request is documentation and schema only, so the criteria are the contract, not a claim that tests already exist.

### AC-PARK-01 — Source of truth

- **Given** a project's primary repository contains a valid `.workflow/project-state.json`
- **When** Orbit, the board, hyvv, or bundlebees need the project's state
- **Then** they use that file as the source of truth and do not start new work from a second, disagreeing store

### AC-PARK-02 — Default when the file is missing

- **Given** a project repository has no `.workflow/project-state.json`
- **When** a dispatcher reads project state
- **Then** the project is treated as `active`, and the system records that the state was defaulted, not read from a file

### AC-PARK-03 — Invalid file fails closed

- **Given** `.workflow/project-state.json` is present but invalid or unreadable
- **When** a new bee or new work card is requested
- **Then** the request is refused, in-flight work is not cancelled, and the failure says the state file is invalid

### AC-PARK-04 — Transitions are audited

- **Given** a project changes between `active`, `parked`, and `archived`
- **When** the state file is written
- **Then** the write includes `state`, `changed_at`, `changed_by`, and `reason`, and those same values are appended as the last `history` entry

### AC-PARK-05 — No new bees while set aside

- **Given** a project's state is `parked` or `archived`
- **When** a bee or attempt is dispatched for that project without a valid override
- **Then** the dispatch is refused

### AC-PARK-06 — No new work cards while set aside

- **Given** a project's state is `parked` or `archived`
- **When** a new work card is requested for that project
- **Then** the card is refused, and existing cards are not deleted

### AC-PARK-07 — In-flight work drains

- **Given** one or more bees are in flight for a project that has just become `parked` or `archived`
- **When** no human has approved cancellation of those bees
- **Then** those bees may finish their current lease and push their branches, and they must not start a new lease or a follow-on card on that project

### AC-PARK-08 — Cancel in-flight only with a human yes

- **Given** a bee is in flight on a parked or archived project
- **When** someone asks to cancel that bee
- **Then** the bee is cancelled only after an explicit human yes that names it

### AC-PARK-09 — Queued cards move, never deleted

- **Given** queued cards exist for a project being parked or archived
- **When** the park action completes
- **Then** those cards are on the Parked column, each keeps its id and previous-column record, and none are deleted

### AC-PARK-10 — Routines are paused by their owner

- **Given** routines or watchers are tied to a project being parked or archived
- **When** the park action records them in the snapshot
- **Then** the bot that owns each item pauses it, and a routine with no recorded owner is reported as unpaused-unknown rather than silently left running or silently dropped

### AC-PARK-11 — Snapshot required fields

- **Given** a project is `parked` or `archived`
- **When** the resume snapshot at `snapshot_path` is checked
- **Then** it contains last SHAs, open pull requests, pending approvals in the human's own words, next steps, parked-on, and parked-by, and it does not omit a required section

### AC-PARK-12 — No secrets or hosts

- **Given** a state file, a `PARKED.md`, or a `project.state/v1` event
- **When** it is written or validated
- **Then** it contains no secrets, keys, tokens, environment-file contents, patches, prompts, private URLs, IP addresses, or hostnames

### AC-PARK-13 — Observability filter

- **Given** a project's latest state is `parked` or `archived`
- **When** in-flight or spend views are rendered
- **Then** that project is omitted from those views and is still present in history views

### AC-PARK-14 — State event aligns with `agent.lifecycle/v1`

- **Given** a project state changes
- **When** a `project.state/v1` event is emitted
- **Then** it uses the same `project` join key and timestamp rule as `agent.lifecycle/v1`, and `agent.lifecycle/v1` itself is not modified

### AC-PARK-15 — hyvv refuses with 409

- **Given** a project is `parked` or `archived` and no valid override is present
- **When** hyvv `/v1` dispatch is called for that project
- **Then** the response is HTTP 409 with code `project_parked` or `project_archived`

### AC-PARK-16 — Override needs a reason

- **Given** a dispatch to a parked or archived project includes an override flag
- **When** the reason is missing or empty
- **Then** the dispatch is still refused; when the reason is present, the override is persisted with an actor

### AC-PARK-17 — bundlebees refuses too

- **Given** a project is `parked` or `archived` and no valid override is present
- **When** the beekeeper or bees.ps1 would start work for that project
- **Then** the work is refused with the same codes as hyvv

### AC-PARK-18 — Unpark validates and reports drift

- **Given** a parked or archived project and a filled snapshot
- **When** unpark runs
- **Then** it validates the state file and the snapshot, re-checks SHAs and pull request states, and writes a drift report; on failed validation or unresolved blocking drift it does not change `state`

### AC-PARK-19 — Unpark restores cards

- **Given** unpark has a valid snapshot and any blocking drift has a human decision
- **When** the state becomes `active`
- **Then** queued cards are restored from the Parked column to their recorded previous columns

### AC-PARK-20 — Resume routines need a human yes

- **Given** unpark is restoring a parked project that had paused routines or watchers
- **When** those items would be resumed
- **Then** each item (or a named group) resumes only after a human yes, performed by the owning bot

### AC-PARK-21 — Agent-agnostic and portable

- **Given** a person or agent other than the original maintainers has the primary repository
- **When** they read `.workflow/project-state.json` and `PARKED.md`
- **Then** they can tell the state and how to resume without a hardcoded machine, path, agent name, or provider

## 10. Who does what

| Work | Owner | Notes |
|---|---|---|
| This workflow spec, schemas, `templates/PARKED.md`, and the Temple of Hermes skeleton folder | MR.INDIA | This pull request. Docs and schemas only. |
| Orbit board state, the Parked column, and card restore on unpark | MR.INDIA | Later, in orbitdesktop. Needs the human owner's yes to merge. |
| Orbit observability filter (in-flight and spend omit parked and archived projects; history keeps them) | MR.INDIA | Later, in the official Orbit observability view. Consumes `project.state/v1` and the state file. Does not redefine token usage. |
| bundlebees check (coordinator gate and/or tests that refusals hold) | MR.INDIA | Later, in bundlebees. Complements, and does not replace, the beekeeper work below. |
| hyvv `/v1` dispatch refusal (409 `project_parked` / `project_archived`, override with reason, capabilities advertisement) | Hermes Forge | Interface proposed in [§7](#7-enforcement-interface-proposals). |
| bees.ps1 and beekeeper refusal | Hermes Forge | Same codes and override rules. |
| Temple of Hermes `PARKED.md` and the real `.workflow/project-state.json` in that project's primary repository | Hermes Forge | Fill in [`examples/temple-of-hermes/`](../examples/temple-of-hermes/README.md); do not include secrets or hosts. |

No implementation in hyvv, bundlebees, or Orbit, and no merge of this pull request, happens without the human owner's yes.

## 11. Examples and schemas

| Path | What it is |
|---|---|
| [`schemas/project-state.schema.json`](../schemas/project-state.schema.json) | `workflow.project-state/v1` for `.workflow/project-state.json` |
| [`schemas/project-state-event.schema.json`](../schemas/project-state-event.schema.json) | `project.state/v1` event, aligned with `agent.lifecycle/v1` by reference |
| [`schemas/examples/project-state.active.json`](../schemas/examples/project-state.active.json) | Valid active example |
| [`schemas/examples/project-state.parked.json`](../schemas/examples/project-state.parked.json) | Valid parked example |
| [`schemas/examples/project-state-event.json`](../schemas/examples/project-state-event.json) | Valid event example |
| [`templates/PARKED.md`](../templates/PARKED.md) | Resume snapshot template |
| [`examples/temple-of-hermes/`](../examples/temple-of-hermes/README.md) | Worked skeleton, to be filled by Hermes Forge |
