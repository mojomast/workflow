# Changelog fragments and retiring docs-sync companion PRs

Status: accepted direction (Kyle, chat t1650u); implementation not started.

## Problem

`tests/test_docs_parity.py` here and `tests/test_changelog_coverage.py` in bundlebees require every merged
campaign PR to have a registry row (`MERGED_WINDOW_ROWS`) whose keywords appear in `CHANGELOG.md` `## Unreleased`.
The PR number is only known once the PR is open, and the merge commit only exists after it merges. So each
wave has ended with "docs-sync companion" PRs, and the exclusion list in `test_docs_parity.py` holds dozens of
them. Every PR also edits the same `## Unreleased` block, so parallel PRs conflict on `CHANGELOG.md`. The
rizzstack run merge queue has code that resolves those conflicts by keeping both sides and adds the registry
row itself.

## Decision

1. **One fragment per branch.** A PR adds `changelog.d/<branch-slug>.md`, where the slug is the branch name with
   `/` replaced by `--`. Front matter carries `section:` (Added, Changed, Fixed or Removed) and `keywords:`
   (two or more backticked terms). The body is the bullet text. Two PRs never touch the same file.
2. **Coverage without a PR number.** The parity guards read `Merge pull request #N from <owner>/<branch>` from
   the git log, map the branch to its fragment, and count the fragment as coverage for #N. Keywords are checked
   in the fragment. The registry row and the companion PR are no longer needed. Existing rows and exclusions stay
   valid during the transition, so both forms pass.
3. **Assembly at release.** `scripts/changelog_assemble.py` folds fragments into `CHANGELOG.md` under the
   release heading and deletes them. Only the owner cuts releases. `--check` mode prints the assembled
   `## Unreleased` without writing anything, so it is easy to review.
4. **Both repos.** workflow (`test_docs_parity.py`) and bundlebees (`test_changelog_coverage.py`) switch the same
   way. Each is one test-first slice: RED tests for the slug mapping, fragment-as-coverage, keyword checks and
   assembly. Bees on the rizzstack Hermes board build them.

## Coordination with the rizzstack run (MI-29), proposed and not made here

The rizzstack-t1634 run owns its run skill and merge queue. Once both slices merge, the proposed changes are:

- The run skill's worker step "add a `CHANGELOG.md` bullet" becomes "add `changelog.d/<branch-slug>.md`".
- The merge queue drops the CHANGELOG-only conflict resolution and the `MERGED_WINDOW_ROWS` insertion. It keeps
  everything else: CLEAN plus green checks, and `--match-head-commit`.
- No new docs-sync companion PRs after the switch.

This is written here and in the implementation PR descriptions for the run owner to adopt. Nobody edits the live
run skill from this workstream.
