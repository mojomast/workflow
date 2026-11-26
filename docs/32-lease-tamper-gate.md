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

## Where the lease comes from

The gate reads **one** source of truth: `.rizzstack/leases/*.json` on the base
branch. There is no `lease-contract:` label, no `Lease-Contract:` body line and
no head-revision fallback — a pull request cannot supply, point at or edit the
lease it is judged by.

A lease is usable only when it names an **approved frozen contract** that is
already committed to the base branch:

1. the lease declares `review.status` `approved` or `frozen` **and** a non-empty
   `review.approved_by` — a lease with no review block is not frozen;
2. the lease declares `contract_sha256`;
3. `.rizzstack/contracts/<contract_sha256>.json` exists at the base tip, and
   its own canonical hash (compact, key-sorted JSON with the `review` block
   removed) equals the hash in its file name and in the lease;
4. that contract's `review.status` is `approved`/`frozen` with a non-empty
   `review.approved_by`;
5. the contract's `source_rev` and all four scope lists equal the lease's.

Any mismatch fails closed with a named reason (`lease_contract_missing`,
`lease_contract_not_approved`, `lease_contract_hash_mismatch`,
`lease_contract_mismatch`). The hash pins the exact approved text, and the
field comparison makes a widened or narrowed lease unusable, so the lease can
never say more than the contract the owner approved.

If nothing names the pull request it is **not a slice**, and the
independent-review rule below applies. There is no "no lease" pass.

## Slice or non-slice

The classification is explicit and lives on the base branch:

- A pull request is a **slice** when a frozen lease committed on the **base**
  branch names it — by number (`"pull_request": 64`), by branch
  (`"branch": "feat/wave-b-b1"`), or by slice name (`"slice"`/`"id"` equal to
  the branch's last path segment, case-insensitively).
- The shape of the branch name is **never** a classifier: `feat/`, `fix/` or
  any other prefix proves nothing, and a lease that does not name the pull
  request does not apply to it.
- **Any change to `.rizzstack/leases/**`, `.rizzstack/contracts/**` or
  `.rizzstack/lease.json` in the pull request's own commits makes it
  non-slice.** Landing a lease or a contract is gate-metadata work: it always
  needs an independent review at its head, and the gate prints
  `NOT A SLICE: it changes gate metadata (…)`. A pull request therefore cannot
  grant itself a scope, and it cannot land the contract it will be judged by.
- A lease whose `review.status` is anything other than `approved` or `frozen`
  (a draft) does not classify a slice.

A **non-slice** pull request — a docs fix, a release chore, a gate change, a
lease or contract landing — passes only with an independent review recorded at
its exact head commit:

- a review whose `state` is `APPROVED`, or
- a `COMMENTED` review whose first line starts `APPROVE`, names an
  `independent review`, and (when it quotes a sha) quotes the head.

The review's `commit_id` must equal the head being checked: an approval at an
older head proves nothing about the code that would merge. With no such review
the job fails closed with the named reason
`non_slice_requires_independent_review`. The job needs `pull-requests: read`
to read the reviews; without a token it fails closed rather than skipping.

**Every slice lease lives at `.rizzstack/leases/<slice>.json` on `main`.** A
lease that names no pull request is inert, so a stale file cannot mis-judge a
later pull request; a file named `.rizzstack/lease.json` is now only a
metadata change to review, never an automatic lease. Land a lease (and the
contract it names) in a small non-slice pull request with an independent
review at its head; never in the slice's own pull request.

**Every lease is derived from an approved contract in `.rizzstack/contracts/`.**
The contract is an `acdd/1` contract; the lease copies its `scope` and
`source_rev` verbatim and names it by hash:

```json
{
  "id": "wave-b-b3",
  "lease_version": "rizzstack.lease/1",
  "slice": "wave-b-b3",
  "pull_request": 177,
  "branch": "feat/wave-b-b3",
  "contract_sha256": "9b971bd3e91f138af656c06c4f49f7edcbd85dcde0d8c82964b2d48f7a10f7ae",
  "source_rev": "a330f7d3fa7a817cb3e8a5a3465048890d2d07a6",
  "scope": {
    "assigned_files": ["validators/python/rizzstack_validators.py", "validators/js/rizzstack-validators.mjs"],
    "test_files": ["tests/test_wave_b_validators.py"],
    "prohibited": ["tests/test_wave_b_validators.py", "bundlebees_plugin", ".github/workflows/ci.yml"],
    "read_only": ["schemas/rizzstack-brief.schema.json"]
  },
  "review": {"status": "frozen", "approved_by": "owner directive 2026-11-25"}
}
```

`scope.assigned_files` is a non-empty list of **concrete** repository-relative
file paths. A wildcard entry (`*`, `**`, `?`, `[`) in `assigned_files` is
rejected with `lease_glob_scope`: the allow-list must enumerate files, because
`*` grants the whole tree. `test_files`, `prohibited` and `read_only` remain
exact paths or `fnmatch` patterns — a glob there is a deny pattern and is
strictly safer. An empty or missing `assigned_files` fails closed.

## The verify boundary

The gate checks commits in `<boundary>..<head>` that are not reachable from
the pull request base. The boundary is resolved, in order:

1. `--verify-sha` (a local/test argument; never read from the event payload);
2. `verify_sha` / `verified_sha` / `verification.sha` in the **base-branch**
   lease;
3. the approved contract's `source_rev`.

Labels and the pull-request body are **never** read as a boundary. A pull
request that could set `Lease-Verify: <head>` (body or `lease-verify:` label)
would move the boundary to its own head and have zero commits checked — a
complete bypass of the lease.

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
- The lease/contract store (`.rizzstack/leases/**`, `.rizzstack/contracts/**`)
  and `.rizzstack/lease.json` are metadata. A commit that changes them makes
  the pull request **non-slice** before any scope check runs (see above), so
  metadata changes always need an independent review at the head; the
  exemption only keeps base-merge history from raising a false violation.
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
  the exact head (`non_slice_requires_independent_review`);
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

A non-slice pull request without a review at the head gets:

```text
lease-tamper: FAILED (reason=non_slice_requires_independent_review): PR #123 is not a slice: no frozen lease on base 123456789abc names it ... A non-slice pull request passes only with an independent review at its exact head abcdef012345 ...
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
comment at the head, and failing with that review at an older head or with
`CHANGES REQUESTED`.

Its `MergeGroupTests` class covers the queue path against a loopback stand-in
for the GitHub API (real HTTP through urllib): a single-PR group passes, a
stacked group checks every entry, an earlier entry without a green run fails, an
unresolvable branch name fails with `merge_group_pr_unresolved`, a pull request
whose head moved after its `pull_request` run fails, an API 500/502 fails (never
a skip), and a missing token fails. hyvv carries the same focused cases in
`tests/test_lease_tamper_merge_group.py`.
