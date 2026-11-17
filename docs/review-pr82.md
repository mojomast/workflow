APPROVED

# Independent review of PR #82 — trial-harness: PART 1 fixtures + evaluator + tests

- PR: mojomast/workflow#82 (open), head `docs/hindsight-trial-harness` at `f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc`, base `main` at `d7a2de06e020155d7b3858f468ce0e735ee43bbb`.
- Reviewer: independent review bee (zoo/glm-5.3-flash), working tree `/home/cua/work/workflow`, branch `review/pr82`, report committed as `docs/review-pr82.md` only (single-file lease). Nothing pushed; nothing commented on the PR.
- Blocking findings: **0** (numbered list below is empty). Non-blocking disclosures are listed after the checks.

## Grounding (public refs, before work and immediately before commit)

- First grounding (before any work): `git ls-remote https://github.com/mojomast/workflow.git` — `refs/heads/main` = `d7a2de06e020155d7b3858f468ce0e735ee43bbb`, `refs/heads/docs/hindsight-trial-harness` = `f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc`, `refs/pull/82/head` = `f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc`. REST `/repos/mojomast/workflow/pulls/82` returned the same head/base SHAs and state=open, draft=false, mergeable=true.
- Re-grounding immediately before committing this report (2026-11-17T06:36:08Z): same three refs, byte-identical SHAs. **Head movement: none.**
- The local clone had no `origin`; the two commits were fetched from the public GitHub repo into `refs/remotes/github/*`. The local synthetic HEAD (`89e01db`, message "base f7c9ca7134...") has the same tree hash (`6a4591f780ee48a4dc0d00c6fa9580d104ab4926`) as the PR head, so tests ran in place against the exact head content.
- The single PR commit is `f7c9ca7` "bundlebees: apply verified attempt att_e1f3fb747b354685" (author bundlebees, 2026-11-17 01:31:30 -0500), parent `13d21fd06f5cd851cc71fce31a94acda2d92ae32`.

## Check 1 — Delta exactness: PASS

- The branch's own commit, `git show f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc --stat`:
  `scripts/trial/__init__.py` (new, empty), `scripts/trial/evaluator.py` (+384), `scripts/trial/fixtures.py` (+202), `tests/test_trial_harness.py` (+414) — 4 files changed, 1000 insertions(+), 0 deletions(-). Exactly the 4 leased files, nothing else.
- Equivalently, `git diff $(git merge-base github/main github/head)..github/head --stat` = the same 4 files (merge-base `13d21fd`).
- Disclosure (not a defect): the raw two-dot command requested in the brief, `git diff d7a2de06e020155d7b3858f468ce0e735ee43bbb..f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc --stat`, shows 10 files / +1002 −1673. The 6 extra entries (`CHANGELOG.md` −2, `plans/backlog.json` ±, `schemas/rails/fixtures/source-matrix.json` −1001, `specs/rails-feasibility.md` −215, `tests/test_docs_parity.py` −14, `tests/test_rails_feasibility.py` −413) are main's own advancement **in reverse** (`git log 13d21fd..d7a2de06` = PR #80/#81 merges, which *added* those files after the branch point); they appear as deletions only because two-dot diffing compares main's tip against the older branch tip. Verified: `git diff 13d21fd..d7a2de06 --stat` is exactly those 6 files with matching ± signs. The branch itself adds nothing beyond the lease. GitHub reports the PR mergeable=true (no conflict with current main).

## Check 2 — Harness suite at the head: PASS

- Command: `python3 -m pytest tests/test_trial_harness.py` (run with pytest 9.2.0 in a fresh venv; system python3.12.3 has no pytest — disclosure D1).
- Result: **28 passed, 0 failed, 0 skipped, 3 subtests passed** (0.04s). Matches the coordinator's verify claim of green.
- Full-suite sanity at the same tree: `pytest tests/` = **906 passed, 3 failed, 4 skipped, 38 subtests passed**. The 3 failures (`test_feature_packet.py::PinnedProtocolTests::test_the_examples_pin_one_real_schema_bearing_ancestor`, `test_feature_packet.py::ProtocolRefTests::test_a_commit_that_predates_the_schema_is_refused`, `test_return_manifest.py::ExampleTests::test_the_examples_pin_one_schema_bearing_ancestor`) were re-run with the PR's 4 new files moved out of the tree and failed identically (3 failed, 82 passed) — they are pre-existing and unrelated to this PR; none of the four files is imported by them. (Disclosure D2: those tests shell out to git history; an earlier base-tree extraction outside a git checkout showed extra failures that are extraction artifacts, so the clean counterfactual is the moved-files run above.)

## Check 3 — RED-first mutation counterfactuals, both ways: PASS

Mutation A (evaluator logic). Exact mutation: in `scripts/trial/evaluator.py`, the H1 scrollback gate `if baseline_scrollback > H1_MAX_SCROLLBACK_SOURCED_EVENTS or treatment_scrollback > H1_MAX_SCROLLBACK_SOURCED_EVENTS:` was edited to `>=` (one character, one line; confirmed via `git diff --stat` = 1 file, 1 insertion, 1 deletion).
- RED: `pytest tests/test_trial_harness.py` → **3 failed, 25 passed** — `VerdictTests::test_identical_arms_are_uninformative`, `VerdictTests::test_well_separated_arms_pass_every_hypothesis`, `ConformanceGateTests::test_single_baseline_violation_fails_the_baseline_arm_gate` (the zero-scrollback arms are now wrongly FAILed).
- Restore: `git checkout -- scripts/trial/evaluator.py`; `git diff --stat` empty.
- GREEN: **28 passed, 0 failed, 3 subtests passed**.

Mutation B (fixture expected-answer field). Exact mutation: in `scripts/trial/fixtures.py`, `"recovery_briefs_total": 2,` changed to `3` (one line).
- RED: **1 failed, 27 passed** — `FixtureTests::test_restart_fixture_carries_expected_answers_for_m1_and_m3`.
- Restore: `git checkout -- scripts/trial/fixtures.py`; tree clean (`git status` clean; only an untracked `__pycache__`).
- GREEN: **28 passed, 0 failed, 3 subtests passed**.

Both counterfactuals hold in both directions: the suite fails when the implementation/fixture is broken and passes when restored, so the assertions genuinely pin the code.

## Check 4 — Fixture honesty (upstream/pinned sources): PASS

Scan of all 4 added files for external references: **no URLs, no commit SHAs, no fetchable pins of any kind** — the only `socket` occurrences are the no-network test's own `mock.patch.object` refusals. Every cited source is an in-repo doc. All 6 cited docs exist at the exact head tree (`git cat-file -e f7c9ca71...:<path>` for each): `docs/hindsight-synthesis.md`, `docs/24-autonomy-dogfood.md`, `docs/27-recovery-protocol.md`, `docs/31-campaign-continuity.md`, `docs/m2-canary-runbook.md`, `docs/memory-contract.md`.

Spot-checks of the line/section citations (6 checked, all faithful):
1. `docs/24-autonomy-dogfood.md:44-47` — is exactly the injected-failure declaration rule the fixtures' `declaration_note` claims ("declared in the job file under `injected_failures`, so nobody can mistake it for a real defect").
2. `docs/24-autonomy-dogfood.md:142-156` — the process-crash boundary table; the fixture's `boundary: "tick.after_dispatch"` matches scenario A verbatim (a real, documented boundary class).
3. `docs/27-recovery-protocol.md:32-60` — the five failure classes; the fixture's `expected_classification: "specification"` and `supersede_count: 1` match the table's `specification` row ("supersede (once, if permitted)").
4. `docs/memory-contract.md:63,115-117` — the C1/C3 rule the evaluator cites in its H1 failure reason: line 63 is the `sessions/` digest row, 115-117 the "a raw transcript is never a source; `session-digest` … not the scrollback" rule.
5. `docs/31-campaign-continuity.md:70-75` — the chat-transcript-vs-durable-record discipline passage the fixtures cite for "metrics read only from durable artifacts".
6. `docs/hindsight-synthesis.md` §3.3 — every evaluator constant matches the pre-registered text: ≥50% reduction and zero scrollback-sourced events (line 449-450 and M1 row 519, whose fail column cites exactly `docs/memory-contract.md:63,115-117`), pitfall in ≥2 of 2 probe briefs with ≤1 intrusion per brief (M2 row 520), 100%-conformance gate with any single violation failing the arm (line 458; M5/M6/M7 rows 523-525), ≤2× token cost (line 461; M8 row 526), and M3/M4 as absolute per-arm decision inputs left to the report layer (rows 521-522) exactly as the evaluator docstring states.

Nothing to fetch, nothing unverifiable; no fixture claims an upstream it does not carry in-repo.

## Check 5 — House predicate scan of the patch: PASS

- Predicate source: `bundlebees_plugin/security.py::looks_like_secret`, fetched read-only from the public bundlebees repo at `main` = `17adb52f872a59f7876b08775e18c1d259fb7b2b` ("Merge pull request #69 from mojomast/feat/tool-path-write-back", 2026-11-17T02:35:43Z). This is the deployed rule family (bearer ≥6 chars; name-ending-in token/secret/password/passwd/pwd/api_key/api-key/authorization followed by colon-or-equals plus a value; sk-, ghp_, github_pat_, xox-prefixed literals; AKIA+16; AIza+20+; eyJ JWT triples).
- Run: read-only import of that module; the function was applied to **every ADDED line of the PR commit** (`git show f7c9ca71... -U0`, plus-lines only) = **1000 lines**. Result: **0 hits**.
- Negative controls (the scan must trip to prove it runs): 7 rule-family literals, each written to trip one family. **7/7 tripped** (disclosure D3: my first control batch had 2 of my own literals malformed for the AKIA+16 exact-length rule, which returned false; I corrected my literals and re-proved — all families trip). Scan-runs-proven: true.
- Expectation met: 0 trips over the patch.

## Check 6 — CI on PR #82: PASS (recorded)

`gh` is not authenticated in this environment, so the public REST API was used at the exact head `f7c9ca71...`:
- `/commits/<head>/check-runs`: **14 check runs, all completed, all success** — including the two secret gates `bee-ci/secret-scan` and `gitleaks`, the required protocol checks (`recovery protocol (required)`, `return manifest protocol (required)`, `feature packet protocol (required)`, `bee-landed protocol (required)`), `cold-start acceptance (light, offline worker)`, `reference demo + tests`, `campaign report protocol`, `observability record tests`, and both schema/reference-checker matrix legs (ubuntu-24.04, windows-latest), plus `bee-ci/project-state` and `bee-ci/reference`.
- `/commits/<head>/status` (legacy combined status): state "pending" with 0 statuses — an artifact of the legacy API having no statuses to report; every modern check run is green. CI at the exact head is green, better than the "pending is fine" bar.

## Check 7 — Secret-scan of this report: PASS

The house predicate (`looks_like_secret`, same import and same module as check 5) was run over every line of this file after writing: **0 hits** (the mutation descriptions and negative controls are described by rule family and count only; no name-colon-value auth/token shapes, no bearer+6-char, no sk-/ghp_/github_pat_/xox/AKIA/AIza/eyJ literals appear in this report). The run was committed only after the scan returned 0.

## Non-blocking disclosures (DISCLOSURE class; blockers count DEFECTS only)

- **D1 — pytest not in the system interpreter.** The suite was run under pytest 9.2.0 in a fresh venv over system Python 3.12.3 (`python3 -m pytest` fails in the bare system env). The counts in check 2 are from that venv.
- **D2 — pre-existing full-suite failures.** 3 tests fail in the full suite at this tree, proven unrelated to the PR by the moved-files counterfactual (check 2). No full-suite green claim is made; the leased file is green.
- **D3 — negative-control literals corrected mid-check.** My first control batch included 2 malformed AKIA literals that did not trip the exact-length rule; corrected and re-proven 7/7. The scanner was never wrong; my controls were.
- **D4 — predicate source provenance.** The house path for the installed checkout does not exist in this sandbox, so the predicate was taken from the public bundlebees repo `main` at `17adb52f872a59f7876b08775e18c1d259fb7b2b` (fetched live; the deployed security.py is unchanged per the repo's own records, and the rule set matches the one documented in this repo's failure-evidence file). The scan is therefore rule-equivalent to the deployed gate, not byte-identical to a host checkout.
- **D5 — two-dot diff optics.** As recorded in check 1, the brief's literal two-dot diff shows 10 files; the branch's own commit is exactly the 4 leased files and the extra 6 are main's post-branch advancement in reverse. Disclosed because the brief's command output, taken alone, would look like a lease violation when it is not.

## Blocking findings

None. (Numbered blocking findings would be listed here as DEFECTs; there are none.)

## Verdict

APPROVED — PR #82 at `f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc` is exact to its lease, green under its own suite (28/28) and under mutation counterfactuals both ways, cites only in-repo sources that check out at the head, scans clean under the house predicate with proven-tripping controls, and CI at the exact head is 14/14 success.
