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
record each audit finding with a stable id and exactly one disposition:
**fixed**, **rejected** or **deferred**. Rejected and deferred findings need a
reason. The same finding cannot appear twice or in two buckets. An attempted fix
that broke another invariant is evidence, not something to erase: removing the
inline symbol data made the zero-runtime-network test fail, so the change was
reverted and the 283 KB cost was recorded.

Every audit also carries a `status` so that "found nothing" and "did not look"
are different records:

- **`clean`** — the review ran on a named head and found nothing. `findings` is
  empty and `head_sha` is required. A clean audit needs a head because the claim
  is revision-bound; it does not need an invented `AF-###` row.
- **`findings`** — the review ran and found something; `findings` is nonempty.
- **`not_run`** — the review did not happen. `findings` is empty and a reason is
  required. A ready report must also disclose it in `known_limits`, and it needs
  at least one audit that actually ran, so `not_run` cannot be used as a silent
  pass.

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
   contract. Use `PASS` only with evidence; use `NOT RUN` with a reason, name the
   criterion id in `not_run`, and put the item in `known_limits`.
4. **Triage the audits.** Give each audit a `status`. Every finding has a stable
   `AF-###` id and exactly one disposition: fixed, rejected with a reason, or
   deferred with a reason. A finding cannot disappear, appear twice, or appear in
   two buckets. A review that found nothing is `clean` with an empty `findings`
   list; a review that did not run is `not_run` with a reason and appears in
   `known_limits`.
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
| `campaign_acceptance_head` / `campaign_acceptance_revision` | a passing test, integration, visual, performance or asset criterion with no head, or a head other than the reported final head |
| `campaign_test_head` | a `ready_for_review` report whose recorded test runs are not at the reported final head |
| `campaign_evidence` | a bare label, placeholder, path traversal or absolute path instead of a repository-relative artifact or public `https` URL |
| `campaign_evidence_kind` | a `visual` PASS with no image or recording evidence |
| `campaign_ready_without_pass` | `ready_for_review` with no passing acceptance criterion |
| `campaign_acceptance_reason` | `NOT RUN`, `BLOCKED` or `UNVERIFIED` without a reason |
| `campaign_ready_with_blocker` | `ready_for_review` while a criterion is `FAIL`, `BLOCKED` or `UNVERIFIED` |
| `campaign_test_failed` / `campaign_test_runs` | a ready campaign whose recorded suite failed, or no run at all |
| `campaign_audit_id` | a finding id that is not stable-looking (`AF-###`) |
| `campaign_audit_status` | an audit whose `status` is missing or not `clean`, `findings` or `not_run` |
| `campaign_audit_clean` | a `clean` audit that reports findings |
| `campaign_audit_findings` | a `findings` audit with an empty findings list |
| `campaign_audit_not_run` | a `not_run` audit that reports findings |
| `campaign_audit_missing` | a ready report with no audit that actually ran |
| `campaign_audit_disposition` | a finding with no valid single disposition |
| `campaign_audit_reason` | a rejected or deferred finding without a reason, or a `not_run` audit without one |
| `campaign_audit_head` | a `clean` audit without a head, or a ready report whose audit that ran was not performed at the final head |
| `campaign_audit_duplicate` | the same finding id appears more than once in the report |
| `campaign_audit_legacy` | old free-text fixed/rejected/deferred arrays instead of traceable findings |
| `campaign_revision` | `base_rev` equals `head_rev` in a ready report |
| `campaign_limits_required` | a ready campaign with unrun checks or a `not_run` audit but no `known_limits` |
| `campaign_not_run_consistency` | a `NOT RUN` criterion that no `not_run` entry names by id |
| `campaign_task_graph` | counts that imply accepted > integrated > implemented, or a wrong `remaining` |
| `campaign_acceptance_test_run` | a passing `test` criterion whose command a recorded run reports as failing |
| `campaign_merge_order` | a recommended order that is not the open PRs in ascending `merge_order` position (reversed, partial, padded, or naming a closed PR) |
| `campaign_merge_order_position` | `merge_order` positions that are not exactly 1..N over the open PRs |
| `campaign_merge_order_duplicate` | a repeated `merge_order` position or a repeated PR number |
| `campaign_merge_order_missing` | an open PR with no `merge_order` |
| `campaign_merge_order_state` | a merged or closed PR carrying a `merge_order` |
| `campaign_metric` | a non-numeric or non-finite performance `value` or `budget` |
| `campaign_secret` | credentials or private host paths copied into the report |
| `campaign_invalid` | an unknown field, a wrong type, an empty optional string, or an unparseable timestamp |

`NOT RUN` is intentionally allowed in a `ready_for_review` campaign when it is
also disclosed in `known_limits` and named in `not_run` by criterion id. The
status is not a pass; it is a limit the receiver can weigh. The same is true of a
`not_run` audit: it needs a reason and a `known_limits` entry, and the campaign
still needs at least one audit that actually ran.

## 5.1 What the validator can and cannot prove

The validator proves the report has the required shape, that its counts do not
contradict one another, that a ready campaign's recorded runs and revision-bound
evidence name the reported head, and that a finding has at least one disposition.
It cannot prove that an evidence file exists, that a URL returns the claimed
bytes, that the command was actually run, or that the human reviewer's judgment
was sound. A valid report is a reviewable claim, not proof of the underlying
work. The reviewer must open the evidence and reproduce what matters.

## 6. Closeout is not a merge plan

`recommended_merge_order` is a review aid, not authorization. The report keeps
the receiver's decision pending and does not call a forge API. The campaign may
end with every PR still a draft, which is the correct outcome when the approver
has said "feature branches and draft PRs only".

### 6.1 Merge-order semantics

Two fields describe one plan, and they must agree as sequences:

- `pull_requests[].merge_order` is the **1-based position** of that PR in the
  merge sequence. It is not the PR number and it is not a second copy of the
  recommended list.
- `recommended_merge_order` is the **list of PR numbers**, ordered by that
  position: `[pr.number for pr in open PRs sorted by merge_order]`.

The validator derives that list and compares it with `recommended_merge_order`
exactly. A set comparison is wrong here: it rejects a normal report whose first
PR is `#2` in position `1`, and it accepts a list that contradicts the positions
(`#1` in position 1, `#2` in position 2, recommended `[2, 1]`).

| Case | Handling |
|---|---|
| Nonconsecutive PR numbers (`#2`, `#7`) | Allowed. Forge numbers are not dense; only positions are consecutive. |
| Reversed or shuffled order | Refused (`campaign_merge_order`) with the derived order in the message. |
| Duplicate positions | Refused (`campaign_merge_order_duplicate`). |
| Position gap (`1`, `3`) | Refused (`campaign_merge_order_position`): positions are exactly `1..N` over the open PRs. |
| Open PR with no position | Refused (`campaign_merge_order_missing`): the order would be ambiguous. |
| Merged or closed PR with a position | Refused (`campaign_merge_order_state`): it is not in the merge sequence. |
| Merged or closed PR in `recommended_merge_order` | Refused (`campaign_merge_order`). |
| No open PRs | `recommended_merge_order` must be empty. |

The JSON Schema carries the same state rule (`merge_order` required when
`state` is `open`, forbidden otherwise) and the validator carries the sequence
rule, which a schema cannot express.

### 6.2 Not implemented here

Recorded rather than hidden:

- `recommended_merge_order` must name **every** open PR. A campaign that wants to
  recommend only a ready subset would need an explicit field for the rest; today
  the order is the whole open set, which keeps the plan unambiguous.
- `artifacts.performance` rows are not bound to a head revision. The number can
  therefore come from an older commit than `head_rev`; a `head_sha` per row is
  the obvious next step.
- A `manual` acceptance criterion is not revision-bound, because a human review
  may legitimately happen without a checkout. Only `test`, `integration`,
  `visual`, `performance` and `asset` PASS rows must name the final head.

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
