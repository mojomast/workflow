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

**A pull request never supplies the lease it is judged by.** The branch can be
edited by the PR author, so a lease committed only on the branch (or a lease
edited on the branch) could widen itself. The gate resolves the lease only from
trusted sources, in this order:

1. `--contract` / `--contract-sha256` (local runs and tests);
2. a pull-request label `lease-contract:<path>` (`lease:<path>` also works) or
   `lease-contract-sha256:<64-hex>` (`contract-sha256:<64-hex>` also works);
3. a pull-request body line:

   ```text
   Lease-Contract: .rizzstack/leases/my-slice.json
   Lease-Contract-Sha256: <64-hex contract hash>
   ```

   `Contract-Path:` / `Contract-SHA256:` are accepted aliases;
4. by contract hash: a lease under `.rizzstack/leases/*.json` on the **base
   branch** (the base tip, then the merge-base), or a frozen contract in a
   contract store keyed by hash — `BUNDLEBEES_CONTRACT_STORE` (path-separator
   separated), `--contract-store`, `~/.hermes/plugin-data/bundlebees/contracts`
   and `rizzstack-t1634/contracts`. A store entry is
   `<root>/<sha256>.json` or any `*.json` under the root whose
   `contract_sha256`/computed hash matches;
5. the repository convention `.rizzstack/lease.json` on the base branch.

A lease that exists only on the pull-request branch fails closed with the named
reason `lease_not_on_base`:

```text
lease-tamper: FAILED (reason=lease_not_on_base): contract
'.rizzstack/leases/my-slice.json' (from PR body) exists only on PR head abcdef012345,
not on base 123456abcdef or its merge-base. A pull request may not supply or edit
the lease it is judged by; land the lease on the base branch (or in the frozen
contract store) first.
```

**Bootstrap exception.** A repository whose base branch does not contain
`.github/scripts/lease_tamper.py` yet is introducing the gate with this pull
request; there is no gate on the base to weaken, so the branch lease is
accepted and the run prints `lease-tamper: NOTE: ... (bootstrap mode)`. Once
the script is on the base branch, every later pull request must name a lease
that already exists there.

If no trusted source resolves, the job fails closed. There is no "no lease"
pass.


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
  base brings base content, not a slice edit: it passes when the paths it
  brings are neither leased nor frozen. A frozen test, `scope.prohibited` or
  `scope.read_only` path that the merge introduces still fails, because a
  frozen test may never change in the PR's history. Conflict resolutions and
  evil merges are inspected as well: a path that differs from both parents
  (a resolution that rewrites a frozen test, or adds an unleased file) fails.
- The contract file, `.rizzstack/lease.json` and `.rizzstack/leases/**` are
  metadata and are exempt from the lease check. That is safe because the gate
  reads the lease from the base branch or the frozen store, never from the
  branch: editing a lease on the branch cannot change the lease that applies.
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

- no contract is named and no lease is found on the base branch or in the
  frozen contract store;
- the contract is named or found only on the pull-request branch
  (`lease_not_on_base`);
- the lease the branch names does not hash to the contract hash the pull
  request names;
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
lease-tamper: FAILED: no slice contract for PR #123 (head abcdef012345): no 'lease-contract:<path>' label, no 'Lease-Contract: <path>' body line, and no .rizzstack/lease.json at head or base. Add the lease before opening the pull request.
```

## Adding a lease to a pull request

1. Write the contract (or lease record) at a named path such as
   `.rizzstack/leases/<slice>.json` and **land it on the base branch before
   the slice pull request**. The gate reads only trusted storage: a lease that
   exists only on the slice branch fails `lease_not_on_base`. The one
   exception is the pull request that introduces the gate into a repository
   whose base has no `.github/scripts/lease_tamper.py` yet (bootstrap).
   Alternatively put the contract in the frozen contract store and name its
   `Lease-Contract-Sha256`. Do not merge a slice-specific
   `.rizzstack/lease.json`: later PRs inherit it.
2. List every file the slice may change in `scope.assigned_files`.
3. List every test file the slice must not edit in `scope.test_files`; add
   `scope.prohibited` patterns for generated or frozen trees.
4. After verification, record the verify commit with a `lease-verify:<sha>`
   label or a `verify_sha` field in the lease file.
5. Re-run the PR (`synchronize`, or any event that carries the pull request)
   after changing the label or lease; the check reads the event's labels and
   the checkout at the PR head.

A one-commit documentation PR still needs a lease. The minimal form is a named
lease file (for example `.rizzstack/leases/<slice>.json`) in the PR with
`source_rev` set to the base commit and `assigned_files` listing the files the
PR adds or edits, named from the PR body with `Lease-Contract: <path>`.

## Tests

`tests/test_lease_tamper.py` builds real temporary git repositories and drives
the real CLI. It covers a frozen-test commit, an outside-lease commit, a clean
history, a missing contract (fail closed), a malformed contract, an
unresolvable verify SHA, label/body contract resolution, a base-branch lease,
a merge of the base (ignored), and a conflict resolution that rewrites a
frozen test (fails).

Its `MergeGroupTests` class covers the queue path against a loopback stand-in
for the GitHub API (real HTTP through urllib): a single-PR group passes, a
stacked group checks every entry, an earlier entry without a green run fails, an
unresolvable branch name fails with `merge_group_pr_unresolved`, a pull request
whose head moved after its `pull_request` run fails, an API 500/502 fails (never
a skip), and a missing token fails. hyvv carries the same focused cases in
`tests/test_lease_tamper_merge_group.py`.
