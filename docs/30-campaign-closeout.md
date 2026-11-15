# 30 — Campaign closeout: turning implementation into reviewable evidence

**Status (Nov 15, 2026):** the closeout contract and validator are new. The first
campaign used as the design input is the Jackpot Syndicate game build; its
numbers below are the recorded campaign result, not a claim that the repository
has since stayed at that head. Nothing here grants an approval or changes a
human gate.

**Audience:** a coordinator finishing an automated-development campaign, the
reviewer receiving it, and the next agent asked to continue it.

Part of the method set: [19 Coordinator playbook](19-coordinator-playbook.md) ·
[20 Orchestrator handoff](20-orchestrator-handoff.md) · [24 Autonomy dogfood](24-autonomy-dogfood.md) ·
[26 RETURN manifest](26-return-manifest.md) · [28 Agent lessons](28-agent-lessons.md).

---

## 1. Why a campaign report exists

A task graph says what was attempted. It does not say what the product does,
what a reviewer can reproduce, or what remains unproven. The first Jackpot
Syndicate campaign made the gap concrete:

| Recorded at the campaign close | What it did **not** mean |
|---|---|
| **27/27 task rows implemented** | 27/27 acceptance criteria passed |
| **226 tests passing** on the final head | every user-visible journey was tested |
| **10 draft PRs open** (#2–#11) | the work was integrated or accepted |
| **Chromium and Firefox 10/10**, golden replay on all three browsers | full WebKit journeys, accessibility or coverage were proven |
| **67/71 assets locked** | the four placeholder assets were acceptable to the receiver |
| **1.90 MB gzip** of the 3.00 MB budget | the UI was finished or visually reviewed |

The campaign produced useful, reviewable work. The failure mode to prevent is
calling that work *accepted* because the task graph reached 100%.

## 2. The closeout rule

Keep four states separate:

1. **Implemented** — the task's files exist on the declared branch.
2. **Integrated** — the combined branch builds and its full suite passes.
3. **Accepted evidence** — each acceptance criterion has observed evidence at the
   final head, or is explicitly `FAIL`, `BLOCKED`, `NOT RUN` or `UNVERIFIED`.
4. **Receiver decision** — a human's own decision. An agent cannot fill it in.

The machine-readable closeout record is `rizzstack.campaign-report/1`:
[`schemas/campaign-report.schema.json`](../schemas/campaign-report.schema.json).
The semantic validator is [`tools/campaign_report.py`](../tools/campaign_report.py).
The human form is [`templates/CAMPAIGN-REPORT.md`](../templates/CAMPAIGN-REPORT.md).

## 3. What the first campaign taught

### 3.1 Task completion is not product acceptance

The graph reached **27/27 implemented**, while the acceptance report still had
UI, accessibility, coverage and asset gaps. A coordinator must produce a
criterion-level matrix before saying "done". The report's `task_graph` and
`acceptance` sections are deliberately separate.

### 3.2 Unit tests cannot stand in for the product

The root test command initially omitted the application tests. Once included,
the count moved from 218 to 223, and later to 226 after the audit fixes. A
green package suite was not a green product. Record the command, the exact head
and the counts; never carry a count across a rebase.

### 3.3 Visual work needs visual evidence

A DOM assertion that an `<image>` element exists is not evidence that the art
is visible, correctly framed or usable. The campaign needed browser measurement
and screenshots to find:

- the reel window sitting above the cabinet's transparent opening;
- a 3×3 board letterboxed inside a 1.72:1 window;
- a nine-slice border painting over content;
- authored art that existed in the manifest but never appeared on a screen.

Every `visual` acceptance criterion must name a screenshot or recording at a
stated viewport and a head revision. The report validator refuses `PASS`
without evidence; the human reviewer still decides whether the picture is good.

### 3.4 A second audit is part of delivery

The first pass was green and still had real defects. A second independent,
read-only review found save-safety gaps, a frozen-cell scoring gap, a stale
`ROUND_RESULT`, UI specificity bugs and a stale test count. The closeout must
record audit findings as **fixed**, **rejected** or **deferred**, with a reason
for each rejected or deferred item. An attempted fix that broke another
invariant is evidence, not something to erase: removing the inline symbol data
made the zero-runtime-network test fail, so the change was reverted and the
283 KB cost was recorded.

### 3.5 Deterministic fixtures change with behavior

When boss-freeze preservation and frozen-cell scoring changed, the old golden
replay hash no longer described the engine. The campaign re-recorded the fixture
and preserved the pre-audit fixture as history. Do not "fix" a golden by hiding
the mismatch; record the new seed, command count, tick count and hash, and keep
the old one where a reviewer can compare it.

### 3.6 Push state is part of the result

"Done" is not "on my machine". Before handoff:

- the branch is clean and the remote head equals the local head;
- every changed file is committed;
- the PR list, draft state, exact head SHA and merge order are recorded;
- generated output (`dist`, local evidence, browser traces) is either
  reproducible and committed intentionally, or ignored and named as not shipped.

### 3.7 Known limits are a feature of an honest handoff

At closeout the campaign still had four placeholders, an accessibility audit
that was not run, a coverage target that was not measured and a full WebKit
journey suite that was not run. Those belong in the report. A reviewer can
accept a known limit; they cannot accept a hidden one.

## 4. Required closeout sequence

1. **Freeze the head.** Record the full 40- or 64-hex `head_rev`; fetch the
   remote branch and require local == remote.
2. **Re-run the final checks on that head.** At minimum the full test command,
   the browser/application acceptance command and the asset/perf checks that the
   contract names. Record commands, exit codes, counts and timestamps.
3. **Fill the acceptance matrix.** One row per criterion from the plan or
   contract. Use `PASS` only with evidence; use `NOT RUN` with a reason and put
   the same item in `not_run` and `known_limits`.
4. **Triage the audits.** Every finding is fixed, rejected with a reason, or
   deferred with a reason. A finding cannot disappear.
5. **Write the report.** Use the template, then validate it:

   ```bash
   python3 tools/campaign_report.py validate path/to/campaign-report.json
   ```

6. **Hand over for review.** The `receiver_decision` stays `pending`. Report the
   PRs and the recommended merge order; do not merge, tag, release, deploy or
   publish without the approver's own words.

## 5. Validator refusals

The validator names the rule that failed. The important ones:

| Code | Refuses |
|---|---|
| `campaign_receiver_decision` | an agent-written acceptance; the field must be `pending` |
| `campaign_acceptance_pass_without_evidence` | `PASS` with an empty evidence list |
| `campaign_acceptance_command` | a passing `test` criterion without the command that ran |
| `campaign_acceptance_reason` | `NOT RUN`, `BLOCKED` or `UNVERIFIED` without a reason |
| `campaign_ready_with_blocker` | `ready_for_review` while a criterion is `FAIL`, `BLOCKED` or `UNVERIFIED` |
| `campaign_test_failed` / `campaign_test_runs` | a ready campaign whose recorded suite failed, or no run at all |
| `campaign_limits_required` | a ready campaign with unrun checks but no `known_limits` |
| `campaign_task_graph` | counts that imply accepted > integrated > implemented, or a wrong `remaining` |
| `campaign_merge_order` | a merge order naming a PR that is not open |
| `campaign_secret` | credentials or private host paths copied into the report |

`NOT RUN` is intentionally allowed in a `ready_for_review` campaign when it is
also disclosed in `known_limits`. The status is not a pass; it is a limit the
receiver can weigh.

## 6. Closeout is not a merge plan

`recommended_merge_order` is a review aid, not authorization. The report keeps
the receiver's decision pending and does not call a forge API. The campaign may
end with every PR still a draft, which is the correct outcome when the approver
has said "feature branches and draft PRs only".

## 7. First-use caveats

The Jackpot Syndicate figures in this chapter were observed in the campaign
record at the stated head. They are not a template and must not be copied into a
different campaign. In particular:

- the four placeholders were retained and named, not silently accepted;
- the accessibility audit was not run and was not described as passed;
- the performance number is the restored build (the lower number came from a
  reverted change);
- the browser coverage was Chromium and Firefox journeys plus golden replay on
  three engines, not a full three-engine journey matrix.

The next campaign should use this chapter to make the same distinctions, not to
copy the numbers.
