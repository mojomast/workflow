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
4. the repository convention `.rizzstack/lease.json`, read at the base
   revision first and the head revision second.

If none of these resolves, the job fails closed. There is no "no lease" pass.

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
- The contract file and `.rizzstack/lease.json` are metadata and are exempt
  from the lease check, so recording the verify SHA does not fail the slice.
- A clean history (no commits after the boundary) passes.

## Fail-closed conditions

The job fails, rather than skipping, when:

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
lease-tamper: FAILED: no slice contract for PR #123 (head abcdef012345): no 'lease-contract:<path>' label, no 'Lease-Contract: <path>' body line, and no .rizzstack/lease.json at head or base. Add the lease before opening the pull request.
```

## Adding a lease to a pull request

1. Write the contract (or lease record) at a named path such as
   `.rizzstack/leases/<slice>.json` and either commit it to the base branch,
   commit it in the slice, or keep it in the slice branch and name it from the
   PR body with `Lease-Contract: <path>`. Do not merge a slice-specific
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
