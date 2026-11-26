# Lease/tamper gate

`lease-tamper` is the required check that makes the slice lease mechanical. It
fails a pull request when a commit after the verify boundary touches:

- a file outside `scope.assigned_files` (the lease), or
- a frozen test file: `scope.test_files`, `scope.prohibited`, or
  `scope.read_only`.

The rule is author-agnostic. Bees, triage lanes, human contributors and the
coordinator all go through the same job; there is no actor allowlist and no
bypass label. A coordinator PR that edits a frozen test fails exactly like a
bee PR.

The check runs as the `lease-tamper` job in each repo's gate workflow
(`.github/workflows/ci.yml`; `gitleaks.yml` in the rizzstack umbrella and
`test.yml` in orbitdesktop) and is listed in `ci-gate.needs`, so the
already-required `ci-gate` context cannot pass without it. The other Rizzstack
repos vendor the same script and job.

## Triage lanes

Triage lanes run under a lease like bees and have **no edit rights on tests**.
A triage pull request must carry a contract whose `scope.assigned_files` lists
only its reports, decision records and other written artefacts. Every test
file it must not edit belongs in `scope.test_files` (or `scope.prohibited`),
even when the lane never intends to touch it. The gate then rejects any
triage commit that edits a test after the verify boundary.

The coordinator is included in "every author": a coordinator cleanup,
docs-sync companion or merge repair is a leased slice too. There is no
coordinator exception in the script.

## Where the contract comes from

The gate resolves the contract path in this order:

1. `--contract` (local runs and tests);
2. a pull-request label `lease-contract:<path>` (`lease:<path>` also works);
3. a pull-request body line:

   ```text
   Lease-Contract: .rizzstack/contracts/my-slice.json
   ```

   `Contract-Path:` is accepted as an alias;
4. the frozen slice store `.rizzstack/leases/*.json` on the **base** branch,
   matched to the pull request by the lease's own `pull_request`/`pr`,
   `branch` or `slice`/`id` field;
5. the repository convention `.rizzstack/lease.json`, read at the base
   revision first and the head revision second.

If none of these resolves the pull request is **not a slice**, and the
independent-review rule below applies. There is no "no lease" pass.

## Slice or non-slice

The classification is explicit and lives on the base branch:

- A pull request is a **slice** when a frozen lease/contract committed on the
  **base** branch names it — by number (`"pull_request": 64`), by branch
  (`"branch": "feat/wave-b-b1"`), by slice name (`"slice"`/`"id"` equal to the
  branch's last path segment, case-insensitively), or by a coordinator
  `lease-contract:` label / `Lease-Contract:` body line that names a lease
  already committed to the base branch.
- The shape of the branch name is **never** a classifier: `feat/`, `fix/` or
  any other prefix proves nothing, and a lease that does not name the pull
  request does not apply to it.
- A lease that exists only on the pull-request branch never classifies it and
  fails closed with `lease_not_on_base`: a pull request may not supply or edit
  the lease it is judged by.
- A lease whose `review.status` is anything other than `approved` or `frozen`
  (a draft) does not classify a slice.

A **non-slice** pull request — a docs fix, a release chore, a gate change with
no slice lease — passes only with an independent review recorded at its exact
head commit:

- a review whose `state` is `APPROVED`, or
- a `COMMENTED` review whose first line is the canonical attestation
  `APPROVE (independent review) at <sha>`. The pre-canonical forms
  `APPROVE — independent review ...` and `APPROVE (independent review at
  <sha>)` are accepted by the same parser, as is markdown bold or a leading
  bullet. `APPROVED` as a word, `APPROVE?`, bare `APPROVE` and `APPROVE (not
  an independent review ...)` do not qualify.

When the line quotes a sha it must be a prefix of the review's `commit_id`.
The parser is one shared policy block vendored byte-identically in this gate and
in the merge lane (`scripts/merge_lane_v5.py`): two parsers drifted once and
rejected review wording the other accepted.

**The newest decisive review governs.** A rejection — `state`
`CHANGES_REQUESTED`, or a `COMMENTED` review whose first line starts
`CHANGES REQUESTED` (canonical `CHANGES REQUESTED (<why>) at <sha>`) —
submitted after the approval being used refuses it when it is recorded at that
approval's commit or at any later commit (the head counts). A later
re-approval supersedes the rejection in its turn; a rejection the approval
supersedes (recorded at an earlier commit) does not block. Without this rule an
approval followed by `CHANGES_REQUESTED` at the same head, or by a rejection at
the new head after a base merge, still passed.

The review's `commit_id` must equal the head being checked, or sit at an
earlier head that **carries forward** (owner rule, 2026-11-25). It carries only
when all three hold:

1. the review commit is an ancestor of the head -- a review whose commit was
   rewritten away judged different code and never carries;
2. every commit after it that is not already on the base is a merge commit
   whose non-first parents are on the base. Merging the base into the branch is
   bookkeeping; an authored commit, or a merge of any other branch, is not;
3. the pull request's diff against the base (`git diff base...head`) is
   byte-identical to the diff the review saw (`git diff base...review_sha`):
   the same paths with the same blob shas (`--raw --no-renames`, so a rename is
   a delete plus an add).

Updating a branch with the base therefore no longer demands a fresh review just
to move `commit_id`, while a real commit, an unrelated merge or any content
change still does. That matters because the workflow ruleset sets
`strict_required_status_checks_policy`, so every merge to `main` makes open
pull requests behind it update their branch; without the carry-forward each
such update forced a re-review of unchanged code. A review at an older head
that fails any condition fails closed under the same top-level reason
`non_slice_requires_independent_review`, and the message names the condition:
`review_not_ancestor`, `review_carry_authored_commit`,
`review_carry_unrelated_merge`, `review_carry_content_changed` or
`review_carry_unreadable`.

With no review at all the job fails closed with the named reason
`non_slice_requires_independent_review`; an approval overridden by a later
rejection fails under the same reason and names `review_changes_requested`.
The job needs `pull-requests: read` to read the reviews; without a token it
fails closed rather than skipping.

On a passing run the gate prints one machine-readable class line —
`lease-tamper: class=slice` or `lease-tamper: class=non-slice` — so the merge
lane takes the class from the trusted gate output instead of re-deriving it
from a branch name. The review line, rejection rule, carry predicate,
sensitive-path list and only-SUCCESS-green rule live in a marked shared block;
`tests/test_lease_tamper.py` pins its sha256 and runs the same review-line and
carry fixtures as the lane's suite.

**Keep the default path out of long-lived `main`.** Once a slice-specific
`.rizzstack/lease.json` is merged, every later pull request inherits it (the
file is present in their head tree) and is judged against the wrong lease. Put
slice leases at a named path such as `.rizzstack/leases/<slice>.json` and name
that path from the PR body or a label. Reserve the default
`.rizzstack/lease.json` for a repository-wide lease policy that genuinely
applies to every pull request, if such a policy is ever adopted.

The contract is an `acdd/1` contract or a lease record with the same shape:

```json
{
  "source_rev": "0123456789abcdef0123456789abcdef01234567",
  "scope": {
    "assigned_files": ["src/slice.py", "docs/slice.md"],
    "test_files": ["tests/test_slice.py"],
    "prohibited": ["tests/**", "schemas/**"],
    "read_only": ["README.md"]
  }
}
```

`scope.assigned_files` is a non-empty list of repository-relative file paths
(globs are accepted by the matcher, but leases should enumerate files).
`test_files`, `prohibited` and `read_only` are exact paths or `fnmatch`
patterns; `tests/**` covers the whole test tree. An empty or missing
`assigned_files` fails closed.

A `.rizzstack/lease.json` file may be a pointer instead of the contract
itself:

```json
{
  "contract_path": ".rizzstack/contracts/my-slice.json",
  "verify_sha": "89abcdef0123456789abcdef0123456789abcdef"
}
```

## The verify boundary

The gate checks commits in `<boundary>..<head>` that are not reachable from
the pull request base. The boundary is resolved, in order:

1. `--verify-sha` (local runs and tests);
2. a `lease-verify:<sha>` label on the pull request;
3. a pull-request body line `Lease-Verify: <sha>`;
4. `verify_sha` / `verified_sha` / `verification.sha` in the lease file;
5. the contract's `source_rev`.

Labels and the pull-request body are coordinator-controlled (a bee cannot set
them); prefer them for the verify SHA. The lease file is also accepted for
repos that do not label PRs, and is committed like any other slice file.

The boundary must be an ancestor of the PR head. If it is not, the gate fails
closed: the lease cannot be applied to a rewritten history. Deviating from a
contract's `source_rev` therefore needs a new/corrected lease, not a silent
pass.

## What is checked

- Non-merge commits after the boundary are inspected one by one with
  `git diff-tree --no-renames`, so a rename is checked as a delete plus an
  add (both paths must be leased).
- Merge commits are not authored changes. A merge whose parent is on the PR
  base is ignored. Conflict resolutions and evil merges are still inspected
  when a path differs from both parents; a resolution that rewrites a frozen
  test fails.
- The contract file, `.rizzstack/lease.json` and every file under
  `.rizzstack/leases/` are metadata and are exempt from the lease check: the
  gate reads the lease store from the base branch, so a branch that edits it
  does not change the verdict, and a lease-landing PR changes no code. Recording
  the verify SHA therefore never fails the slice, and landing a lease never
  needs a lease to cover the lease store.
- A clean history (no commits after the boundary) passes.

## Merge queue

A merge-queue candidate arrives as a `merge_group` event whose `head_sha` is a
synthetic merge commit. It may stack several pull requests
(`max_entries_to_build`), so the gate **does not** run the lease diff against
the combined group: one lease cannot describe several slices. It proves the
queue's property instead, per pull request:

1. every `pr-<N>-<sha>` in the queue branch name
   `refs/heads/gh-readonly-queue/<base>/pr-<N>-<sha>` is resolved with
   `GET /repos/{repo}/pulls/{N}`;
2. the entry heads the group stacks are read from its first-parent merge chain
   and each is resolved to its pull request (a stacked group is checked entry
   by entry, not just the last one);
3. for each pull request, the head the group is testing must be the pull
   request's **current** head, and that exact sha must carry a completed,
   successful `lease-tamper` check run -- the proof that this gate already
   passed on the reviewed head.

Failures are hard failures (`exit 1`) with the named reason
**`merge_group_pr_unresolved`**:

```text
lease-tamper: FAILED (reason=merge_group_pr_unresolved): [head-moved] ...
::error title=lease-tamper merge_group_pr_unresolved::[head-moved] ...
```

It is never a neutral or skipped conclusion. GitHub counts a neutral required
check as passing, so a neutral result would be a way around the gate; a queue
that cannot be proved must not merge. Subtypes in the message identify the
case: `no-pr-in-ref`, `no-credentials`, `api`, `no-pr-for-entry`,
`head-moved`, `not-green-at-head`, `head-not-in-group`, `entry-missing`,
`payload-incomplete`.

The job needs `checks: read` for the check-run lookup. A pull request whose
head moved after its `pull_request` run therefore fails the queue candidate;
the queue drops the stale group and rebuilds on the new head.

## Fail-closed conditions

The job fails, rather than skipping, when:

- no frozen lease on the base branch names the pull request (by number,
  branch, slice, label or body line) **and** no independent review exists at
  the exact head or at an earlier head that carries forward by the rule above
  (`non_slice_requires_independent_review`, with the carry condition named);
- a lease names the pull request only on the head branch
  (`lease_not_on_base`);
- no contract is named and `.rizzstack/lease.json` is absent at head and base;
- the contract is not valid JSON, is not an object, or has no
  `scope.assigned_files`;
- the boundary or a PR SHA is not a full lowercase 40/64-hex commit in the
  fetched history (use `fetch-depth: 0`);
- the boundary is not an ancestor of the PR head;
- `git` cannot answer (timeout or non-zero exit).

## Exact failure messages

A tampered commit gets one line per path and a summary, for example:

```text
lease-tamper: FAILED: 'src/unleased.py' is outside the slice lease (scope.assigned_files); touched after verify sha 667dfe8d39bf7ec649794be6298ba1344fd0655e by commit 29294c4b975d ("touch an unleased file").
lease-tamper: FAILED: frozen test file 'tests/test_frozen.py' (scope.test_files) modified after verify sha 667dfe8d39bf7ec649794be6298ba1344fd0655e by commit 65d521de44e2 ("relax the frozen test").
lease-tamper: FAILED: 2 violation(s) after verify sha 667dfe8d39bf7ec649794be6298ba1344fd0655e; contract my-slice from .rizzstack/lease.json; PR head 29294c4b975df341751a253f401c86f7c945d159. Only scope.assigned_files may change after verify, and frozen tests may never change.
::error::lease-tamper: 2 lease/frozen-test violation(s); see the log above.
```

An unresolvable contract gets:

```text
lease-tamper: FAILED: no frozen lease on base 123456789abc names PR #123 (head abcdef012345, branch feat/x): no 'pull_request'/'branch'/'slice' match in .rizzstack/leases/*.json, no lease-contract label or body line, and no .rizzstack/lease.json at head or base.
```

A non-slice pull request without a review at the head, or with one at an
earlier head that does not carry forward, gets:

```text
lease-tamper: FAILED (reason=non_slice_requires_independent_review): PR #123 is not a slice: no frozen lease on base 123456789abc names it ... A non-slice pull request passes only with an independent review at its exact head abcdef012345, or with one at an earlier head that carries forward. The newest approval (commit 0987654321fe) does not carry: [review_carry_authored_commit] commit 13579bdf0246 ("..." ) was authored after the review; only merges of the base may follow a review. ...
```

## Adding a lease to a pull request

1. Write the contract (or lease record) at a named path such as
   `.rizzstack/leases/<slice>.json` and **commit it to the base branch** in a
   small coordinator PR before the slice PR needs it. Name the pull request in
   the lease (`"pull_request": <N>`, `"branch": "<branch>"` or
   `"slice": "<slice>"`) so the gate can classify the PR without any label.
   A label/body line naming an already-committed lease also works. Do not merge
   a slice-specific `.rizzstack/lease.json`: later PRs inherit it.
2. List every file the slice may change in `scope.assigned_files`.
3. List every test file the slice must not edit in `scope.test_files`; add
   `scope.prohibited` patterns for generated or frozen trees.
4. After verification, record the verify commit with a `lease-verify:<sha>`
   label or a `verify_sha` field in the lease file.
5. Re-run the PR (`synchronize`, or any event that carries the pull request)
   after changing the label or lease; the check reads the event's labels and
   the checkout at the PR head.

A one-commit documentation PR is a **non-slice** pull request: it needs no
lease, but it passes only with an independent review at its head. Land the
review (or a small frozen lease that names the PR) before re-running the check.

## Tests

`tests/test_lease_tamper.py` builds real temporary git repositories and drives
the real CLI. It covers a frozen-test commit, an outside-lease commit, a clean
history, a missing contract (fail closed), a malformed contract, an
unresolvable verify SHA, label/body contract resolution, a base-branch lease,
a merge of the base (ignored), and a conflict resolution that rewrites a
frozen test (fails).

The store is metadata: a branch may add a lease file without a lease covering
it, and such an edit never exempts a code path in the same commit.

Its `SliceClassificationTests` class covers the classification rule: a base
lease naming the PR number, the branch or the slice classifies a slice (and the
lease is then enforced); a `feat/` branch shape alone does not; a lease naming
a different slice does not; a draft lease does not; a lease naming the PR only
on the head fails `lease_not_on_base`; and a non-slice pull request fails
`non_slice_requires_independent_review` without a review at its exact head,
while passing with an `APPROVED` review or an `APPROVE (independent review ...)`
comment at the head, and failing with `CHANGES REQUESTED`.

Its `BaseMergeReviewCarryTests` class covers the owner's carry-forward rule:
a base-merge-only update after the review passes (including two base merges in
a row), while an authored commit, a conflict resolution that changes the
reviewed content, a merge of an unrelated branch, and a review whose commit was
rewritten away each fail closed with their named condition
(`review_carry_authored_commit`, `review_carry_content_changed`,
`review_carry_unrelated_merge`, `review_not_ancestor`).

Its `MergeGroupTests` class covers the queue path against a loopback stand-in
for the GitHub API (real HTTP through urllib): a single-PR group passes, a
stacked group checks every entry, an earlier entry without a green run fails, an
unresolvable branch name fails with `merge_group_pr_unresolved`, a pull request
whose head moved after its `pull_request` run fails, an API 500/502 fails (never
a skip), and a missing token fails. hyvv carries the same focused cases in
`tests/test_lease_tamper_merge_group.py`.
