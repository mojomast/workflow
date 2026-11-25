VERDICT: APPROVE
# Independent review — T1-SEED (PR #136)

Scope reviewed: `scripts/seed_memory_from_lessons.py` (new), the
`## Seeding from the agent lessons` section at the end of
`docs/memory-retention.md`, and the read-only approved test
`tests/test_memory_seed_lessons.py`. I read every line of those files plus the
`DiskVault.write`/`read`, `validate_frontmatter`, `memory_sha`,
`quarantine_prefix` and `parse_memory` paths they depend on.

## Acceptance criteria

| Criterion | Evidence |
|---|---|
| Every `### L-NN · Title` becomes one `learning` with id `lesson-l-nn` | `test_every_lesson_becomes_one_learning_in_quarantine` |
| Records are written only under `quarantine_prefix("agent:lessons-seed")` | same test's `written` path assertion; manual `find` on a seeded vault |
| Record shape: `created=modified=--now`, `TYPE_POLICY["learning"]`, null expiry/supersession, file source, `memory_sha(record, body)` | `scripts/seed_memory_from_lessons.py:70-92`, inspected output of a run |
| Re-running with the same `--now` is idempotent and counts unchanged | `test_rerun_is_idempotent`, `test_output_is_a_json_summary` |
| `--dry-run` lists every id, creates nothing, does not construct `DiskVault` | `test_dry_run_touches_nothing_and_lists_ids` (`scripts/...:127`) |
| Last stdout line is the JSON summary with `writer`/`written`/`unchanged`/`dry_run` | `test_output_is_a_json_summary` |
| Queryable first records | `test_seeded_lessons_are_queryable` (`lesson-l-20` in top 3) |
| Docs section with placeholder vault path and human-promotion note | `docs/memory-retention.md:105-120` |

No gate, sandbox, check or test was weakened: the seeder always calls the
gated `DiskVault.write` with `authority: None`, never constructs a grant, never
calls `promote`, and the write path independently re-checks zone, sha, type
directory and the secret scanner. `tests/test_memory_write_quarantine.py` is
intact and its 17 checks pass.

## Findings

1. **minor — `scripts/seed_memory_from_lessons.py:107-113`.** In `--dry-run`,
   `existing_sha` parses an existing file but skips `validate_frontmatter`; a
   malformed quarantine file (for example one without `sha`) raises `KeyError`
   and exits 1 with a traceback, whereas the real run exits 2 with
   `schema_invalid`. Concrete fix: call `validate_frontmatter(record)` before
   returning `record["sha"]` (or catch the missing key and re-raise a
   `ContractError`).
2. **minor — `scripts/seed_memory_from_lessons.py:119-121`.** `--now` is only
   validated indirectly by the write path, so `--dry-run --now not-a-time`
   prints "would write" for every lesson and exits 0, while the same real run
   exits 2. Concrete fix: validate `--now` before branching on `--dry-run`.
3. **minor — `docs/memory-retention.md:112` (with `scripts/...:45-46,131-144`).**
   "Re-running is idempotent" is only true when `--now` is pinned. With the
   default current-UTC timestamp, `created`/`modified` and therefore the sha
   change on every run, so two default runs rewrite all 24 records (verified:
   `written: 24` on both runs). The approved test pins `--now`, so this is a
   documentation precision issue, not a test failure. Concrete fix: say
   "re-running with the same `--now`", or preserve the stored `created` on an
   update if the spec permits it.
4. **minor (review limitation) — repository history.** This checkout is one
   squashed commit (`b006a84`, message `base 7260fa4a...`); the task's
   `ae9c0802...` and `7260fa4a...` objects are absent, so no base-to-head diff
   could be produced. The review is against the final tree, the brief/spec, the
   approved test and the quarantine suite. No evidence of touches outside the
   expected files was found.

## Commands and exit codes

- `timeout 900 python3 -m pytest -q -p no:cacheprovider tests/test_memory_seed_lessons.py tests/test_memory_write_quarantine.py` — exit 1 (pytest is not installed in this review image; `No module named pytest`).
- `timeout 900 python3 -m unittest -v tests.test_memory_seed_lessons tests.test_memory_write_quarantine` — exit 0, 17 tests OK.
- `timeout 900 python3 -m unittest discover -s tests -p 'test_*.py'` — exit 1; 621 tests run, 0 failures and 28 skips, 15 import errors, all `No module named pytest` / `No module named jsonschema` (missing review-image dependencies, unrelated to this PR).
- `timeout 300 python3 -m unittest discover -s reference/tests -p 'test_*.py'` — exit 0, 54 tests OK.
- `timeout 300 python3 -m unittest discover -s observability/tests -p 'test_*.py'` — exit 0, 54 tests OK.
- `cd tools/slop-lint && timeout 300 python3 -m unittest discover -s tests -t . -p 'test_*.py'` — exit 0, 19 tests OK.
- `cd tools/lessons-check && timeout 300 python3 -m unittest discover -s tests -t . -p 'test_*.py'` — exit 0, 12 tests OK.
- `cd tools/acdd-lint && timeout 300 python3 -m unittest discover -s tests -t . -p 'test_*.py'` — exit 0, 56 tests OK.
- `cd tools/project-state && timeout 300 python3 -m unittest discover -s tests -t . -p 'test_*.py'` — exit 0, 18 tests OK, 2 skipped.
- `timeout 300 python3 -m unittest discover -s contrib/hermes-bees/scripts -p 'test_*.py'` — exit 0, 31 tests OK.
- `cd contrib/bee-ci && PYTHONPATH=. timeout 600 python3 -m unittest discover -s tests -p 'test_*.py'` — exit 1, 25 tests run, 9 import errors, all `No module named pytest` (environmental).

Manual behaviour checks (exit 0): same `--now` twice gave `written: 24` then
`unchanged: 24`; `--dry-run` against a nonexistent target left it nonexistent;
all seeded markdown with a slash in its path was under
`.quarantine/agent-lessons-seed/`.
