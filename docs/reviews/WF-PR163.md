VERDICT: APPROVE

# Independent review — workflow PR #163 (docs-sync companion for #153)

Reviewed head: `df882a425f469783ebddc67c73f953ffabb53284`
Head parent: `c7f3433393731e275201578ab9f539272364c8bd`
Review diff base: `0194003dec061a1cb3bf367e3a1d226744df04b9` (the merge of PR #153)

The change has two commits on top of `0194003d`:

- `c7f3433` — adds `EXCLUDED_PRS[163]` and the `MERGED_WINDOW_ROWS` row for #153.
- `df882a42` — adds the `## Unreleased` bullet for #153.

I did not merge anything. I changed no file other than this review and did not push. The coordinator merges.

## Diff under review

`git diff --name-status 0194003d df882a42`:

```
M	CHANGELOG.md
M	tests/test_docs_parity.py
```

`git diff --numstat 0194003d df882a42`:

```
1	0	CHANGELOG.md
11	0	tests/test_docs_parity.py
```

The diff is 12 insertions and 0 deletions. No existing row, exclusion, assertion or test was modified, skipped or removed. The only `CHANGELOG.md` change is the new #153 bullet at `CHANGELOG.md:5`; the only test change is the new `EXCLUDED_PRS[163]` entry and the new #153 registry row.

The empty working tree at the checkout was a single squashed commit whose message names `df882a42`. The stated commit objects were not present locally, so I fetched `0194003d` and `df882a42` read-only from the repository at `https://github.com/mojomast/workflow` to obtain the literal diff. Fetching added loose objects only; it added no remote and changed no tracked file.

## Findings

1. **INFO** — The head is not a direct child of the review base: `df882a42`'s parent is `c7f3433`, whose parent is `0194003d`. Both commits belong to this docs-sync change, and the two-commit diff against `0194003d` is exactly the three claimed artifacts (row, bullet, exclusion). A one-argument `git diff --name-status df882a42` cannot be a valid diff command; the reviewed command was `git diff --name-status 0194003d df882a42`.
2. **INFO** — The Unreleased bullet is accurate but not exhaustive. PR #153 also added 5 lines to `observability/README.md` and 5 lines to `observability/tests/test_schemas.py` (`git show --stat 0194003d`); the bullet names only `observability/METRICS.md`, the five record schemas, the examples and the RED-first test suites. Omitting those two small supporting edits is not a false claim.
3. **INFO** — The registration test's coverage is history-driven. In the squashed review checkout, `_merged_pr_numbers()` returns `None` and the pinned fallback `SNAPSHOT_MERGED_PRS = (35..40)` is used, so the local run does not exercise the #153 row. In a detached worktree at `df882a42` with the real merge history, `test_registry_covers_every_merged_campaign_pr_in_window` reads 82 merged PRs at or above `FIRST_COVERED_PR = 35`, finds no unregistered PR, and the #153 row is actually exercised; the full file and both single tests still pass there (same tails below). This is a property of the squashed checkout, not a defect of this diff.
4. **INFO** — The one skipped test is the pre-existing `test_in_review_pr_has_changelog_representation` parametrization over an empty `IN_REVIEW_ROWS` set (`tests/test_docs_parity.py:813`); the diff neither introduces nor weakens it.
5. **INFO** — The bullet's “RED-first” claim is supported by the merged branch history: `57aaefd` is the test-only RED commit (“test(observability): RED contract tests for metrics fact records”), and `a76a0b0` is the implementation GREEN commit. No assertion in this diff depends on that process claim.

No BLOCKING findings.

## Registry row for #153

The row is inside `MERGED_WINDOW_ROWS` (`tests/test_docs_parity.py:608-613`):

```python
{
    # row rides in its own PR so the merge leaves main green (docs-sync for #153, which merged at 0194003d without one).
    "pr": 153,
    "name": "OBS-METRICS: metric fact-record contracts + observability/METRICS.md catalog",
    "keywords": ("observability/METRICS.md", "resource-sample.schema.json", "inference-step.json",),
},
```

Verified mechanics at the head:

- `pr` is 153, which is `>= FIRST_COVERED_PR` (35).
- `name` is non-empty after stripping.
- There are three keywords, all non-empty strings (`>= 2` required).
- No duplicate PR number exists in `MERGED_WINDOW_ROWS` (62 rows), and no row overlaps an exclusion.
- All three keywords are exact substrings of `_unreleased_section()` at this head: `observability/METRICS.md`, `resource-sample.schema.json`, `inference-step.json`.
- With the real merge history at `df882a42`, every merged PR `>= 35` has a row or an exclusion; the unregistered list is empty.

## Unreleased bullet for #153

`CHANGELOG.md:5` (the first bullet under `## Unreleased`):

```
- Observability metric fact-record contracts (workflow #153): `observability/METRICS.md` now catalogs the metrics, and JSON Schemas define the ci-run, inference, resource-sample, task-outcome and tool-call records (`observability/schemas/ci-run.schema.json`, `inference.schema.json`, `resource-sample.schema.json`, `task-outcome.schema.json`, `tool-call.schema.json`). The `observability/examples/*.json` examples, including `inference-step.json` and `inference-unknown-usage.json`, are validated against their schemas by the RED-first `observability/tests` suites.
```

Factual checks against PR #153's merged content (`git show --stat 0194003d`, 16 files, +1562/−0):

- `observability/METRICS.md` was added (162 lines) and catalogs the fact records, privacy rules, label allowlist, histogram buckets, retention, SLOs and the metric catalog. Supported.
- `observability/schemas/ci-run.schema.json`, `inference.schema.json`, `resource-sample.schema.json`, `task-outcome.schema.json` and `tool-call.schema.json` were all added. Their record discriminators are `ci.run/v1`, `gen_ai.inference/v1`, `resource.sample/v1`, `task.outcome/v1` and `gen_ai.tool_call/v1`. Supported.
- `observability/examples/inference-step.json` and `inference-unknown-usage.json` were added, and `observability/tests/test_metrics_records.py` (also added, 272 lines) validates them against `inference.schema.json`; every example file in `observability/examples/` is referenced by the observability tests. Supported.
- The RED-first test commit `57aaefd` precedes the GREEN implementation commit `a76a0b0` in the merged branch. Supported.
- The merged PR did not add a changelog bullet or registry row of its own (hence this companion), and `0194003d --stat` shows no `CHANGELOG.md` or `tests/test_docs_parity.py` change. Supported.

I ran the observability suite at this head: `python3 -B -m unittest discover -s observability/tests -t .` -> `Ran 82 tests ... OK`. No claim in the bullet is contradicted by the merged files.

## Exclusion for #163

`tests/test_docs_parity.py:49-53`:

```python
163: (
    "docs-sync companion (the workflow #153 coverage row + its Unreleased bullet: "
    "observability metric fact-record contracts): a registry bookkeeping change; it "
    "carries its own exclusion so merging it leaves main green"
),
```

This follows the established 131/138/140 docs-sync-companion precedent, for example #131:

```python
131: (
    "docs-sync companion (the workflow #130 coverage row + its Unreleased bullet: the "
    "ci-gate aggregate check): a registry bookkeeping change; it carries its own "
    "exclusion so merging it leaves main green"
),
```

The reason is non-empty, names the covered PR (#153), the artifact class (coverage row plus Unreleased bullet), and the reason for self-exclusion (registry bookkeeping; keep main green after merge). It is the same class as 131/138/140 and does not hide feature work.

## Guard integrity

- The diff contains only insertions; `git diff --numstat` reports `11 0` for the test file, so no assertion, test, row or exclusion was deleted, edited or skipped.
- `EXCLUDED_PRS` now has 24 entries (oldest 37, newest 163); all reasons are non-empty. The added exclusion is required only after #163 merges; until then it is inert.
- The #153 row is a normal registry row, not an exclusion, so the merged work must remain discoverable in `## Unreleased`.
- There is no `pytest.skip`, `xfail`, `skipif` or `importorskip` anywhere in `tests/test_docs_parity.py`. The single skip is the empty `IN_REVIEW_ROWS` parameter set noted above.
- The guard does not weaken `FIRST_COVERED_PR`, `SNAPSHOT_MERGED_PRS`, the well-formedness assertions or the keyword-substring assertion; the diff does not touch them.

## Tests run

System Python has no `pytest` (`/usr/bin/python3: No module named pytest`). I created an ephemeral venv at `/tmp/opencode/venv` (outside the repository) with `pytest 9.2.0` and ran the required commands with that venv first on `PATH`, which makes `python3 -B -m pytest` the literal command:

`python3 -B -m pytest tests/test_docs_parity.py -q`

```
.................................................................s...... [100%]
71 passed, 1 skipped in 0.13s
```

`python3 -B -m pytest tests/test_docs_parity.py -q -k test_registry_covers_every_merged_campaign_pr_in_window`

```
.                                                                        [100%]
1 passed, 71 deselected in 0.03s
```

`python3 -B -m pytest tests/test_docs_parity.py -q -k test_merged_campaign_pr_has_discoverable_changelog_coverage`

```
..............................................................           [100%]
62 passed, 10 deselected in 0.12s
```

The same three commands were also run in a detached worktree at `df882a42` with the real merge history; the tails were identical (`71 passed, 1 skipped`; `1 passed, 71 deselected`; `62 passed, 10 deselected`). The detached worktree was removed afterwards.

## Working tree

`git status --porcelain` was empty before this review file was written. After writing it, the only change was `?? docs/reviews/WF-PR163.md`. Nothing else was modified, and nothing was pushed.
