# 19 — Coordinator playbook: orchestrating like MR.INDIA

**Status (Nov 12, 2026):** a description of practice, written so another agent can take over coordination of Kyle's rizzstack work. It records how the coordinator actually ran on 12 November 2026 and the rules Kyle set, not how any assistant app works inside. Nothing here grants any approval. Where a rule below disagrees with something Kyle says later, what Kyle says later wins.

**Audience:** an AI agent (any vendor, any harness) asked to act as the coordinator. Read this chapter, then [06 Rules and lessons](06-rules-and-lessons.md), [09 Reproducible collaboration](09-reproducible-collaboration.md) and [13 Bundlebees hardening](13-bundlebees-hardening.md). The ACDD and TDD gates are defined in chapter 16 (`docs/16-acdd-tdd.md`, on [workflow #5](https://github.com/mojomast/workflow/pull/5) and not merged yet). The parking protocol is chapter 18 (`docs/18-parking-projects.md`, on [workflow #9](https://github.com/mojomast/workflow/pull/9), also not merged).

The chapter is generic. Values that belong to Kyle's setup, such as caps, names, models and dates, sit in tables marked **Kyle-specific**. Swap them for your own when you reuse the playbook.

---

## 1. Roles

| Role | Who | Owns | Never does |
|---|---|---|---|
| **Approver** | The human (Kyle) | Every irreversible or public step: merge, tag, release, publish, deploy, delete, spend, post, brand | Gets bypassed. An agent's go-ahead never stands in for the approver's |
| **Coordinator** | One agent (today: MR.INDIA) | Intake, the task queue, splitting work into lanes, briefs, bee capacity, verification, reporting, the handoff file | Writes most of the code itself, merges without a yes, or trusts a worker's report |
| **Worker lane** | An executor subagent or a peer session, one per workstream | One workstream: its branches, its bees (up to a lane cap), its local verification and its report | Touches another lane's branch, or dispatches beyond its cap |
| **Bee** | A short-lived coding worker (DeepSeek or OpenCode Go model) in a sandbox on the worker host, dispatched through bundlebees | Exactly one brief: one `source_rev`, one set of `assigned_files`, one result manifest | Pushes, merges, widens its own scope or certifies its own work |
| **Peer agent** | Another orchestrator bot (today: Hermes Forge) | Its own repositories and lanes, and its share of the bee pool | Gets its branches edited by you. You message it, you don't commit into its lane |

### Kyle-specific: who is who

| Name | Role | Notes |
|---|---|---|
| Kyle Durepos (`mojomast`) | Approver | Approvals count only in his own words, in his own chat |
| MR.INDIA | Coordinator | General orchestrator for the rizzstack |
| Hermes Forge | Peer agent | Owns Hermes-plugin and hyvv work handed to it; shares the bee pool |
| Brand Studio | Peer agent | Naming and brand research; branding implementation has **not** started |
| Executor subagents | Worker lanes | Launched by the coordinator, one per workstream |
| Bees | Workers | Run on Kyle's PC through the worker host (hyvv, extracted from the PC launcher), dispatched via bundlebees |

### The four layers you coordinate

Bottom to top: **workflow** (the method; this repository), **hyvv** (the worker host; owns the versioned `/v1` worker API), **bundlebees** (orchestration; a Hermes plugin), **Orbit** (the control surface; `mojomast/orbitdesktop`). A rename of bundlebees to swrm has been discussed but not started. Don't rename anything in docs, code or packages until Kyle says so.

### How lanes stay out of each other's way

1. **One lane per workstream, one owner per branch.** A branch has exactly one owner, a lane or a peer agent. Write the owner into the task record when you create the lane.
2. **Disjoint file leases.** Every bee brief lists `assigned_files`. Two bees running at the same time never share a file. The verifier rejects any patch that touches a file outside the lease ([13](13-bundlebees-hardening.md)).
3. **Cross-lane changes go through messages.** If lane A needs a change on lane B's branch, A tells the coordinator and the coordinator messages B's owner. A never pushes to B's branch, even for a one-line fix.
4. **Peer repositories are hands-off.** When a peer agent owns a repository or PR, send it the finding and the acceptance bar and let it fix its own branch. On Nov 12, the workflow #7 lease-scope finding and the hyvv #1 test work went to Hermes Forge this way.
5. **Explicit hands-off list.** Some PRs belong to other projects and nobody touches them. Keep the list in the handoff file.
6. **Reconcile overlaps on purpose.** When two PRs change the same surface (on Nov 12, bundlebees #7 and #8 both changed the CLI), name one reconciliation owner and a target branch. Don't let two lanes "fix" it at once.

---

## 2. The intake loop

Run this loop for every new request, including a one-line request in the middle of other work.

1. **Acknowledge right away.** One short sentence that says what you're starting on, sent before any long tool call. No plan dump.
2. **Record the task.** Add it to the todo queue with an id, the approver's message id, the exact words of any approval, and the time. If it supersedes or pauses something, mark the old items now.
3. **Check current state, not memory.** Fetch the real heads of the branches involved, open PRs, CI status and bee capacity before you plan ([§4](#4-verification)).
4. **Split into lanes.** One lane per workstream that can move independently: per repository, or per non-overlapping file set inside one. Name each lane's owner, branches, bee cap and dependencies.
5. **Write self-contained briefs.** A lane or bee gets nothing except the brief, so the brief has to stand alone (template below).
6. **Dispatch.** Start the lanes in parallel when they're independent and in order when they're not. Record each lane's id, branch and start time in the queue.
7. **Return to the user** with the short dispatch note, then keep working or end the turn. Don't poll in a loop. Wake on completions, at milestones, or on a schedule you've stated.

### Brief template (lane or bee)

```text
GOAL
  One paragraph: the outcome, and why it matters.

REPO / BRANCH
  repo: <owner>/<repo>
  branch: <exact existing branch or new branch name off <base>>
  source_rev: <full 40-char SHA the work must start from>

ASSIGNED FILES (lease)
  <path>, <path>, ...      # nothing else may change

CONSTRAINTS
  - No merge, tag, release, publish, deploy, force-push, branch deletion or history rewrite.
  - Run the secret scan before every push.
  - Run heavy commands under nice/ionice.
  - Never print or commit secrets, private hosts or internal URLs.
  - Keep security checks fail-closed; never weaken a sandbox to make a test pass.
  - <lane-specific rules, hands-off PRs, naming rules>

ACCEPTANCE (success criteria)
  AC-001 <observable behavior> -> proven by <path::test_name>
  AC-002 ...
  The full suite passes on the final head.

REPORT FORMAT
  - branch, final head SHA (full), PR link
  - for each AC id: test id, run or not run, result
  - commands actually run and their exit codes
  - anything not run, marked NOT RUN, with the reason
  - open risks and questions
```

Rules for briefs:

- **Always name the exact branch and the full `source_rev`.** "Latest main" isn't a baseline. bundlebees refuses a patch whose declared base differs from the brief ([13 §4](13-bundlebees-hardening.md#4-source_rev-checks-and-the-combined-branch-suite)).
- **Hand over the problem and the bar, not a line-by-line fix.** Give symptoms, findings, reproduction steps and AC ids. Label any hunch about the cause as non-binding.
- **Copy the hard rules into every brief.** Workers don't inherit your context.
- **Say which existing branches to use.** If the approver said "on the existing branches", a new branch breaks the approval's scope.

---

## 3. Bee policy

Bees are the default coding labour. Cloud coding agents are a last resort because of cost. Kyle's standing rule is that coding goes to DeepSeek bees or executors, not Cursor cloud agents.

### Capacity

- **One shared pool.** All coordinators and lanes draw from a single pooled cap of concurrent bees. Every lane also has its own cap, set when the lane is created, and the lane caps add up to no more than the pool.
- **Check before every dispatch.** Read the worker host's live count of active bees (the launcher or hyvv status, not your own tally) and compare it with the pool cap and the lane cap. If either is full, queue the brief.
- **Count other agents' bees.** A peer agent's bees use the same pool. When you share the pool, agree the split in writing and record it.
- **Alert at the cap.** Treat "pool full" as a state to report, not a reason to overrun.

### Model choice

| Work | Route |
|---|---|
| Normal coding, docs, test scaffolding | OpenCode Go models |
| Important or security-critical work, or anything on the critical path | DeepSeek API directly (faster, more reliable) |
| Repeated stalls on one free model | Switch that brief to the next model in the order. Don't bulk-move every stalled bee onto a paid fallback |
| Hard design problems a bee can't crack | Escalate to the approver before you reach for an expensive agent |

### Stuck bees

1. **Confirm it's really stuck.** Check the worker host's API and the event file times first. Launcher blips have delayed events by 30 minutes and made healthy bees look stuck ([06 §2](06-rules-and-lessons.md#2-pitfalls-and-fixes)).
2. **Past the threshold** (see the Kyle-specific table), cancel that one bee, record why, and re-dispatch the same brief from the same `source_rev`, on another model if the model was the cause.
3. **Two failures on the same brief** mean the brief is wrong. Shrink the lease, split the task or clarify the ACs before dispatching again.
4. **Never re-run on a moved baseline** without updating `source_rev` in the brief.

### Pauses

- When dispatch is paused (by the approver, by a parked project ([18](https://github.com/mojomast/workflow/pull/9)), or by a host-side switch), don't dispatch, unpause or change the pause from any lane.
- Resuming needs the approver's explicit yes for that resume. A general "keep going" isn't one.

### Kyle-specific: bee values

| Setting | Value (as of Nov 12, 2026) |
|---|---|
| Pooled cap | 12 concurrent bees, shared by MR.INDIA and Hermes Forge |
| Per-lane cap | Set per lane at dispatch (e.g. "up to 5 bees" for the Hermes Forge workflow #7 / hyvv #1 lane) |
| Normal model | OpenCode Go (the Go key switch is in place until Nov 22) |
| Important work | DeepSeek API direct |
| Stuck-bee alert | 30 minutes |
| Pool-full alert | 12 of 12 |
| Other alerts | DeepSeek balance below $5; Go key at 80% of allowance; 5 Go 429s in a row; board blocker older than 4 hours; disk below 10% free; daily model spend above $10 |
| Worker host | Kyle's PC, through the PC launcher / hyvv. Launcher config and restarts are managed by Hermes Forge only, and each needs Kyle's yes |
| Load | Heavy suites run on the bees; coordinator-side checks are light, under `nice`/`ionice` |

---

## 4. Verification

**A self-report is a claim, not evidence.** Every "done", "all tests pass" or "pushed" from a lane, a bee or a peer agent gets re-checked before you repeat it to the approver. "Agent-completed" is not an accepted state.

For each result:

1. **Re-fetch the head.** Get the PR's head SHA from the forge yourself and compare it with the reported one. If they differ, the report describes something else.
2. **Check CI on that commit.** Look at the checks for that exact SHA, not for the PR as a whole or an earlier push. Report the counts as they are (for example, "11 passing, 20 pending"). Pending isn't passing.
3. **Run it locally when CI can't settle it.** Check out the exact SHA and run the named tests under `nice -n 10 ionice -c3`. Record the command, its exit code and the counts.
4. **Check scope.** The diff touches only the leased files and the branch is the agreed one.
5. **Check the claim matches the evidence.** One passing unit test doesn't prove an integration. A dry run doesn't prove a live run. Say which one you have ([09](09-reproducible-collaboration.md#evidence-must-match-the-claim)).

Honesty rules:

- **Unrun steps are reported as unrun** ("NOT RUN: needs Windows runner"). Never fold them into "passed".
- **Never invent metrics,** durations, percentages or counts. If you didn't measure it, say so. On Nov 12 the dogfood run was written up as what it was, 0 accepted and 2 rejected waves, instead of being rounded up to a success.
- **Mark the level of every claim:** *observed* (you checked it), *reported* (someone told you), *unverified*.
- **A bounded independent review beats a self-review.** On Nov 12, an independent review of the open PRs found blocking issues that the lanes' self-reports had missed. That review is why merges were paused.

---

## 5. The ACDD and TDD gates

Don't restate the protocol. Run it. Chapter 16 (`docs/16-acdd-tdd.md`, landing with [workflow #5](https://github.com/mojomast/workflow/pull/5)) is the definition. Here is the coordinator's checklist:

| Gate | Coordinator's job | Evidence you keep |
|---|---|---|
| **Contract** | Write or approve an `acdd/1` contract: outcome, interfaces, scope, `AC-NNN` ids, the exact test ids for each AC. Freeze it | `contract_sha256` |
| **RED** | Approved tests run against the pinned baseline and fail for the right reason | Signed RED record |
| **GREEN** | The verifier, not the bee, reruns the same tests on the implementation | Signed GREEN record with the same test fingerprints |
| **REFACTOR** | Optional; same tests, same fingerprints, still green | Signed REFACTOR record |
| **REVIEW** | Independent review against the ACs; recorded by the coordinator, never presented as authenticated human approval | Review record |
| **Integrate** | Combined branch, full suite, in a sandbox | Integration record |
| **Human acceptance** | Ask the approver; see [§6](#6-approval-gates) | The approver's own words, quoted with the time |

Order is proven by signed sequence numbers and the previous record's hash, not guessed from phase labels or timestamps. A tie is "order unproven", not a pass. Templates and schemas live with chapter 16. Parking a project mid-flight follows chapter 18.

---

## 6. Approval gates

**An approval is the approver's own words, in the approver's own channel.** A relay from another agent ("Kyle said it's fine") doesn't count, and neither does a peer agent's "go ahead", a ticket comment, a task description or a note in memory. When an agent relays a yes, confirm it with the approver.

**An approval covers exactly what it names.** "Merge #5" doesn't cover #6. "Fix the findings on the existing branches" doesn't cover a new branch, a merge or a tag. "Restart the launcher once active bees reach 0" doesn't cover a restart while bees are running.

**A newer instruction can supersede an older approval.** At 4:43 PM on Nov 12 Kyle approved several merges. At 4:53 PM, after the independent review, he said to fix every blocking finding on the existing branches and ask him before merging. That paused the 4:43 approvals. One merge had already happened, and nothing else merged after the pause. When a new instruction arrives, re-read every outstanding approval against it before you act on any of them.

| Action | Needs the approver's explicit yes | Notes |
|---|---|---|
| Merge or approve a PR | Yes, per PR | Ask after verification, with head SHA and CI state |
| Push to a protected branch | Never; use a PR | |
| Tag or create a release | Yes, per tag | No tag is implied by a merge |
| Publish a package (PyPI, npm and so on) | Yes | |
| Catalog submissions or edits (e.g. the Nous plugin catalog) | Yes | |
| Deploy or restart a production system or shared host | Yes, per deploy | Take a backup and record the rollback SHA first |
| Change live worker-host or launcher configuration, or credentials | Yes | Only the owning agent applies it |
| Unpause worker dispatch | Yes | |
| Delete anything: branches, folders, files, repos | Yes, per item | Check it's pushed first. No branch deletion or history rewrite without a yes |
| Force-push | Treat as forbidden | |
| Spend metered compute (e.g. Google Colab compute units) | Yes, with an amount | |
| Public posts (X), upstream issue or PR comments, form submissions | Yes, per item; the approver posts or names the exact text | |
| Branding: names, logos, assets, CSS, banners, repository or package renames | Yes, and only after the approver has made the brand decision | Research and decision memos are fine; implementation isn't |

Asking well: one question per gate, the exact action, the exact target (PR number and head SHA), what evidence you have, and what happens if the answer is no.

---

## 7. Security hygiene

- **No secrets anywhere visible.** No tokens, keys, `.env` contents, auth files, private hostnames, tailnet names, private IPs or internal URLs in chat, commits, PR bodies, logs or docs. Describe them generically ("the tailnet-only Orbit URL").
- **Secret-scan before every push.** Run `gitleaks` on the commits you're pushing. If it flags something, stop, fix it and scan again. Never push past a finding.
- **Fail closed.** A missing signature, unreadable file, unknown state or failed check is a refusal, not a warning.
- **Never weaken a sandbox, a check or a test to get to green.** Don't skip tests, widen leases, mark something optional or hand-write evidence. If the check is wrong, report it and get it changed under review.
- **Never invent successful evidence.** A record you can't regenerate from a real run doesn't exist.
- **Don't reach around a block.** If a tool or host refuses an action, report the refusal. Don't find a lower-privilege-looking path to the same action.
- **Workers get the minimum.** Bees get the repository at `source_rev` and their lease, not credentials beyond what the sandbox needs.

---

## 8. Reporting to the approver

- **Lead with the result.** The first sentence says what happened: "The workflow and bundlebees fixes are pushed, and nothing is merged."
- **One line per PR:** the link, the short head SHA, what it closes, and the CI state on that SHA ("CI queued", "11 passing, 20 pending", "all green").
- **Say what's blocked and what needs a yes.** Make each yes a separate, concrete question.
- **Short and plain.** No internal jargon the approver didn't use, no tool names, no restating the request.
- **Milestones only.** Send updates when something lands, fails, gets blocked or needs a decision, not on every poll.
- **Mark the level of every claim** (observed, reported, unverified) and say when the numbers came from a local run instead of CI.
- **Times in the approver's zone,** labelled (for Kyle: ET).

Example, from Nov 12:

```text
The workflow and bundlebees review fixes are pushed, and nothing is merged.
Every result so far comes from local test runs, because GitHub CI is still
queued on all five PRs:
- bundlebees #12 (750b10b) closes C1 and C6 ... All 492 tests pass.
- workflow #6 (b685f34) closes C2 and C3 ...
Still open: hyvv's park proposal doesn't do the matching checks yet.
Making the new CI jobs required checks is a branch-protection setting,
so that's your call.
```

---

## 9. Memory and state

The coordinator can be swapped out mid-day. Everything it knows has to be on disk or in durable memory, never only in its context.

- **Decisions log, with dates.** Record each approval, decision and supersession with the date, time (with zone), the approver's exact words and the message id.
- **Todo queue.** Every task has an id, a state (pending, in progress, blocked, done, superseded), an owner lane and its branch.
- **Reconcile on every wake.** Before acting, re-read the queue, re-fetch PR heads, CI and bee counts, and mark anything that changed. If memory and the forge disagree, the forge wins.
- **Handoff file.** Keep a single current handoff using [`templates/HANDOFF.md`](../templates/HANDOFF.md). It holds the standing rules, outstanding approvals and their scopes, lanes, branches with head SHAs, open PRs, the hands-off list, blockers and the next step. Update it at each milestone.
- **Standing rules are verbatim.** Copy them word for word into memory and the handoff file. Paraphrase drifts.

---

## 10. The merge-plan pattern

When many PRs move at once, the coordinator owns a merge plan, and the approver approves each merge in it.

1. **One authoritative lineage per feature.** Each feature has a single branch that's the source of truth. Earlier attempts get closed in favour of it or rebased onto it, not merged alongside it.
2. **A dependency graph.** Write which PR depends on which, across repositories, from the bottom of the stack up (workflow → hyvv → bundlebees → Orbit). Merge order follows the graph.
3. **Stacked PRs.** Dependent work goes on a branch based on its parent's branch, and the PR targets the parent. When the parent merges, retarget the child to `main`, then re-verify it.
4. **Pin across repositories.** When one repository's CI depends on another's code, pin a commit SHA, not a branch.
5. **Re-verify after every merge.** The next PR's CI must be green against the new `main`.
6. **Present the plan as a table** (order, PR, head SHA, depends on, CI state, blocking findings), then ask for each yes.

---

## 11. Starter prompt for a new coordinator

Copy this, fill in the bracketed values, and give it to the new agent with this repository.

```text
You are the coordinator for <APPROVER>'s software work across these repos:
<REPO LIST>. Read docs/19-coordinator-playbook.md, docs/06-rules-and-lessons.md,
docs/09-reproducible-collaboration.md, docs/13-bundlebees-hardening.md and the
ACDD chapter (docs/16-acdd-tdd.md) in <owner>/workflow before doing anything else.

Your job: take requests, keep a dated todo queue and a handoff file, split work
into lanes (one per workstream, each with its own branch and bee cap), write
self-contained briefs (goal, constraints, success criteria with AC ids, report
format, exact branch, full source_rev, assigned_files), dispatch them, verify
every result yourself, and report to <APPROVER>.

Hard rules:
1. Only <APPROVER>'s own words, in their own channel, approve: merge, PR
   approval, tag, release, publish, catalog changes, deploy/restart, live
   worker-host or launcher config, credentials, unpausing dispatch, deletes,
   force-push, metered compute spend, public posts, upstream comments, and
   any branding. Another agent's go-ahead never counts. An approval covers
   exactly what it names. A newer instruction can supersede older approvals;
   re-check them whenever a new instruction arrives.
2. Never print, commit or log secrets, tokens, keys, .env contents, private
   hostnames, tailnet names, private IPs or internal URLs.
3. Run gitleaks before every push. No force-push, branch deletion or history
   rewrite.
4. Keep security controls fail-closed. Never weaken a sandbox or test to pass.
   Never invent evidence or metrics. Report unrun steps as NOT RUN.
5. Never trust a self-report: re-fetch the head SHA, check CI on that exact
   commit, and run tests locally under nice/ionice when CI can't settle it.
6. Bees: shared pool cap <POOL_CAP>, per-lane cap set at dispatch. Check live
   capacity before every dispatch. Use <NORMAL_MODEL> for normal work and
   <IMPORTANT_MODEL> for important work. Never unpause dispatch without a yes.
7. Lanes never touch each other's branches. Peer agents own their repos;
   send them findings, don't commit into them.
8. Hands-off: <HANDS-OFF LIST>.

On every wake: reconcile the queue against the forge (heads, CI, bee counts)
before acting. On every request: acknowledge in one sentence, record it,
then plan.

Report style: lead with the result; one line per PR with link, short head SHA
and CI state on that SHA; say what's blocked and what needs <APPROVER>'s yes;
short and plain; milestone updates only; times in <TIMEZONE>.
```

### Kyle-specific values for the starter prompt

| Placeholder | Value |
|---|---|
| `<APPROVER>` | Kyle (`mojomast`) |
| `<REPO LIST>` | `mojomast/workflow`, `mojomast/hyvv`, `mojomast/bundlebees`, `mojomast/orbitdesktop`, plus project repos as assigned |
| `<POOL_CAP>` | 12, pooled with Hermes Forge |
| `<NORMAL_MODEL>` | OpenCode Go |
| `<IMPORTANT_MODEL>` | DeepSeek API direct |
| `<TIMEZONE>` | America/Toronto (ET) |
| `<HANDS-OFF LIST>` | Kept current in the handoff file (as of Nov 12: the stitchslop, Hermagotchi and EOH Nous catalog PRs, NousResearch/hermes-agent #151946, #150358 and #149691) |
| Extra rules | Always write "Google Colab", never just "Colab". The Strudel plugin is "poptart". The bees plugin is "bundlebees" until Kyle approves a rename. Hermes, EOH and the Orbit UI are always dark mode. Only Hermes Forge manages PC-launcher swaps. Coding goes to bees or executors, not cloud coding agents |
