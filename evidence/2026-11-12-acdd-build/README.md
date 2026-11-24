# Evidence: building ACDD + TDD test-first (Nov 12, 2026)

The ACDD + TDD work was built with its own protocol. For every slice, the coordinator committed the approved tests on their own first (RED), confirmed they failed for the right reason, and only then had the implementation written. DeepSeek bees did that where dispatch was available; the coordinator did it while dispatch was paused. Every result below was re-run by the coordinator on the box. Worker claims were not used as evidence.

## This repository (reference implementation)

The `tdd-evidence/1` records in this folder were produced by `reference/workflow/tdd.py`. They come from running the approved tests in throwaway worktrees at each commit, so they are unsigned (teaching only).

| Contract | RED (tests only) | RED result | GREEN | GREEN result | Records |
|---|---|---|---|---|---|
| WF1-reference | `8045df0` | 29 tests, 14 errors, every one a missing declared interface (`cannot import name acdd/tdd/lifecycle`) → `behavioral_failure`; the 15 legacy tests pass | `41af7d7` | 38/38 passed | [contract](WF1-reference.contract.json), [red](WF1-reference.red.json), [green](WF1-reference.green.json), [report](WF1-reference.report.json) |
| WF2-setupclass | `0f8c306` | 1 new test fails (a `setUpClass` error got an id that matched no test) | `6adbbbd` | 39/39 passed | [contract](WF2-setupclass.contract.json), [red](WF2-setupclass.red.json), [green](WF2-setupclass.green.json), [report](WF2-setupclass.report.json) |

**Exact test ids (re-frozen after the independent review).** The first versions of these contracts named whole test files in `acceptance_criteria[].tests` (for example `tests/test_acdd.py`), so any test in the file could stand in for a criterion. Both contracts are now re-frozen with exact `path::Class::method` ids. The ids come from a unittest loader run over the approved test files at the GREEN commit, saved as [WF1-reference.collected.json](WF1-reference.collected.json) and [WF2-setupclass.collected.json](WF2-setupclass.collected.json). The files are byte-identical at RED and GREEN (same `test_fingerprints`). WF1's files can't be loaded at its RED commit, because the modules they import don't exist yet; that's the point of that RED. RED and GREEN were then re-run on the same commits, with the same results as before: WF1 29 tests / 14 errors → 38/38, and WF2 1 failure → 39/39. The file-level versions are in git history at `55b39a6`.

WF2 exists because recording WF1's own RED first gave `unrelated_failure`: the runner gave a class-setup ImportError an id that matched no test. That bug was found by dogfooding and fixed test-first. Pairing WF1's RED with WF2's GREEN correctly fails with `tests_tampered`, because `tests/test_tdd.py` changed in between.

## bundlebees ([PR #5](https://github.com/mojomast/bundlebees/pull/5))

| Slice | RED commit | RED | GREEN commit | GREEN (approved tests) | Implemented by |
|---|---|---|---|---|---|
| BC1 contract + dispatch gate | `84aff4e` | 45 of 46 fail (missing interfaces); the schema-budget regression passes | `d780b6d` | 46/46 | DeepSeek bee |
| BC2 tdd + sandbox cases | `84aff4e` | 42/42 fail | `a0199a1` | 42/42 | DeepSeek bee |
| BC3 CLI + verify | `dce3fae` | 11/11 fail | `4662e5e` | 11/11 | coordinator (dispatch paused) |
| BC4 integrate | `ccb3a4f` | 3/3 fail | `3165fc3` | 3/3 | coordinator (dispatch paused) |
| BC5 tdd refactor | `7125085` | 6/6 fail | `3b62162` | 6/6 (+4 bee tests) | bee `att_262feeef193f7e04`, re-run by coordinator |
| LK1 lease-key race (regression) | `50bd936` | 1/1 fail | `427c116` | 1/1 | coordinator; reproduces a cold-start CI failure |

At `868ed11`, the full suite was 442 passed and 0 failed. At `427c116`, it was 453 passed and 0 failed. bundlebees records real evidence as HMAC-signed records in the coordinator's state directory. The table above is the coordinator's junit re-run, not those records.

## orbitdesktop ([PR #26](https://github.com/mojomast/orbitdesktop/pull/26))

| Slice | RED commit | RED | GREEN commit | GREEN | Implemented by |
|---|---|---|---|---|---|
| OR1 evidence view (model + panel) | `20eadb9` | the test file fails: module not found | `a2f2ac8` | 9/9 | DeepSeek bee |

Orbit's full suite on the box: 1230 tests, 5 failures. The same 5 fail on orbitdesktop `main` on the same box, none involving the new files.
