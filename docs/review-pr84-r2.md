APPROVED

# Independent review r2 — PR #84 (docs-sync: coverage for merged campaign PRs 82+83 + the RAILS-R01 backlog adoption)

- PR: mojomast/workflow#84 (open), head `docs-sync/registry-row-82` at `3194a19c17f0e8c0c737bf60b7d9a2e56d863f8b`, base `main` at `c7b5ab3aeca0bc47f7150c7d05c5388f1bb37f5c`.
- Reviewer: independent review bee r2 (zoo/glm-5.3-flash), working tree `/home/cua/work/workflow`, branch `review/pr84-r2`, report committed as `docs/review-pr84-r2.md` only (single-file lease). Nothing pushed; nothing commented on the PR.
- Scope: the FULL PR delta, `merge-base(main, head)..head` = `c7b5ab3..3194a19` — i.e. the branch's three commits `0336e2c` (#82 coverage), `892cc83` (merge main post-#83), `3194a19` (#83 coverage + RAILS-R01 adoption). r1 (att_d44a19f704e54b68, APPROVED 9/9) covered the pre-merge single-#82 delta; this r2 re-audits the extended delta from scratch.
- Blocking findings: **0** (numbered blocking list below is empty). Disclosures are listed after the checks and are DISCLOSURE class, not DEFECT class; the blocking count is defects only.

## Grounding (public refs, before work and immediately before commit)

- First grounding (before any work): `git ls-remote https://github.com/mojomast/workflow` — `refs/heads/docs-sync/registry-row-82` = `3194a19c17f0e8c0c737bf60b7d9a2e56d863f8b` (byte-identical to the brief's expected head), `refs/heads/main` = `c7b5ab3aeca0bc47f7150c7d05c5388f1bb37f5c`, `refs/heads/docs/hindsight-trial-harness` = `dac605ebb7163c94c55a66815e0452e3aa79b296`, `refs/heads/rails/r01-contract` = `ba2a53c7163cc7938d23a9f2dac058a51a6d2f7b`, `refs/heads/review/pr82` = `0ea9318126389829dea910f86980b05c627def2d`, `refs/heads/review/pr83` = `0d3185cab05838322211a34ee02d2ac83e215aeb`. REST `/repos/mojomast/workflow/pulls/84` returned head sha `3194a19…` (branch `docs-sync/registry-row-82`), base sha `c7b5ab3…` (branch `main`), state open, draft false, `mergeable_state: unstable`.
- Re-ground immediately before committing (2026-11-17T06:59:43Z): same ls-remote and REST reads re-run — head, main and both campaign branches byte-identical to the first read; `review/pr84-r2` did not exist upstream at either read. **Head movement: none across the review.** (The movement that DID happen is inside the merged history and is disclosed as D1 below: both campaign branch tips advanced past their verified heads before merging.)
- The local clone is a single parentless snapshot commit whose tree hash (`bd676b289fea8a9dd25ef134b34327b448c011fd`) is byte-identical to the PR head tree, so suites ran in place against the exact head content; real merge history for the guard was exercised in a detached worktree at the head commit (removed after use; `git worktree list` back to the main checkout only).

## Check 1 — Delta exactness: PASS

- `git diff c7b5ab3aeca0bc47f7150c7d05c5388f1bb37f5c..3194a19c17f0e8c0c737bf60b7d9a2e56d863f8b --name-status` (merge-base with main .. head) returns EXACTLY:
  `M CHANGELOG.md`, `M plans/backlog.json`, `M tests/test_docs_parity.py`.
- No additions, deletions or renames; nothing else. Exactly the three expected paths.
- Per-file: `CHANGELOG.md` +4 lines (two numbered bullets, #82 and #83); `tests/test_docs_parity.py` +23/−0 (one EXCLUDED_PRS entry for 84, two MERGED_WINDOW_ROWS rows for 82 and 83); `plans/backlog.json` +20/−2 (the RAILS-R01 adoption, detailed in check 6).

## Check 2 — The #82 bullet, claim by claim: PASS (with D1/D2 disclosure posture)

The bullet: `- #82 (merged at \`056e627\`): the trial-harness PART 1 (workflow #82, branch docs/hindsight-trial-harness): …`.

| Bullet claim | Evidence | Result |
|---|---|---|
| merged at `056e627` | REST `/repos/mojomast/workflow/pulls/82` → `merge_commit_sha: 056e627198dd7ac91e0c41def79de578ed5843b5`, state closed, merged_at 2026-11-17T06:47:49Z | TRUE (full sha match) |
| branch docs/hindsight-trial-harness | same REST record, `head.ref` | TRUE |
| files: `scripts/trial/fixtures.py` + `scripts/trial/evaluator.py` + `tests/test_trial_harness.py` (+ `scripts/trial/__init__.py`) | `git show f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc --stat` → exactly those 4 files, 1000 insertions, 0 deletions | TRUE (exactly the 4 leased files) |
| attempt att_e1f3fb747b354685 | the verified content commit's subject is `bundlebees: apply verified attempt att_e1f3fb747b354685` | TRUE (attempt id recorded on the landed commit) |
| verify PASSED firejail at `f7c9ca7`, exactly the 4 leased files, house secret scan clean | `f7c9ca7…` exists, is the parent of the PR-82 merge head `dac605e` ("Merge branch 'main' into docs/hindsight-trial-harness"), and is an ancestor of merge `056e627` (`git merge-base --is-ancestor` → yes). The firejail verify result itself is a host-held verify record — DISCLOSED under D2, not asserted | Commit verified in-tree; verify verdict = host-held (disclosed) |
| "sat unverified ~34 min … coordinator-reconciled at the campaign record's beat-3 staleness trigger" | the campaign record's Nov-17 beats are not in this repo (`grep -r att_e1f3fb74 / att_016d9b4d / att_affc3ee9` outside this PR's own additions: no hits) — DISCLOSED under D2 | unverifiable from the sandbox (disclosed) |
| "succeeded in-sandbox (4/4 checks including one-commit-per-file)" | host-held sandbox verify record — DISCLOSED under D2; the landed artifact is consistent (single apply-commit, exactly 4 files, attempt id in the subject) | unverifiable from the sandbox (disclosed) |
| "harness suite is 28 passed / 0 failed at the head" | re-run at the PR-84 head: `pytest tests/test_trial_harness.py` → **28 passed, 0 failed, 3 subtests passed** | TRUE (re-verified by this review) |
| review APPROVED zero blocking (att_68fb8f5325e74492, 7/7 checks, both-ways RED-first mutation, house-predicate patch scan with negative control, 3 full-suite failures proven pre-existing via moved-files counterfactual, CI protocol jobs green) | `origin/review/pr82` (= `0ea9318…`, subject `bundlebees: apply verified attempt att_68fb8f5325e74492`) carries `docs/review-pr82.md`: first line APPROVED, exactly 7 `## Check` headings all PASS, Check 3 = both-ways mutations, Check 5 = patch scan with 7/7-tripping negative controls, Check 2 = moved-files counterfactual for the 3 pre-existing failures, Check 6 = CI 14/14 success at the head | TRUE (every element read on the origin review branch) |

## Check 3 — The #83 bullet, claim by claim: PASS (with D1/D2/D3 disclosure posture)

The bullet: `- #83 (merged at \`c7b5ab3\`): the Rails R01 contract layer (workflow #83, branch rails/r01-contract): …`.

| Bullet claim | Evidence | Result |
|---|---|---|
| merged at `c7b5ab3` | REST `/repos/mojomast/workflow/pulls/83` → `merge_commit_sha: c7b5ab3aeca0bc47f7150c7d05c5388f1bb37f5c`, state closed, merged_at 2026-11-17T06:50:38Z; `refs/heads/main` today equals this sha | TRUE (full sha match) |
| branch rails/r01-contract | same REST record, `head.ref` | TRUE |
| files: the 7 `schemas/rails/*.schema.json` + `examples.json` + `fixtures/hash-vectors.json` + README + `tests/test_rails_contract.py` | `git show 5288abb90b4c1130fbd0b622d5a099da898387cf --stat` → exactly those 11 files, 5364 insertions, 5 deletions | TRUE (exactly the 11 leased files) |
| tests enforce: bad hashes fail, duplicate keys fail, wrong-kind payloads fail, PASS without evidence fails; legacy vector matches upstream; freeze digest recorded | re-run at the PR-84 head: `pytest tests/test_rails_contract.py` → **69 passed, 80 subtests, 0 failed**; r83 review Check 4 maps each requirement to named test ids (`test_tampered_hash_fails`, the strict-loader duplicate-key refusal, `test_unknown_payload_field_fails`, `test_pass_requires_nonempty_evidence`, `test_legacy_rows_reproduce_upstream_hashes`, `test_readme_records_freeze_digest`) | TRUE |
| attempt 1 att_fa13d94 was the recorded F1 zero-commit loss (verify refused with the degenerate empty envelope, preserved in the record) | **DISCLOSED, not asserted (D3):** `verify-results/att_fa13d94acc6f4f72.json` lives on the coordinator host and is NOT reachable from this sandbox; the campaign record carrying the Nov-17 beats is likewise not in this repo (no in-repo mention of `att_fa13d94` outside this PR's own additions). This review can neither confirm nor refute the envelope wording; the claim is recorded as unverifiable here | unverifiable from the sandbox (disclosed) |
| attempt 2 att_e0cff87d85a644e5 succeeded with 5/5 checks incl. the coordinator-gate secret scan | the verified content commit's subject is `bundlebees: apply verified attempt att_e0cff87d85a644e5`; the 5/5 check count is a host-held sandbox verify record — DISCLOSED under D2 | commit verified; 5/5 = host-held (disclosed) |
| "sat unverified ~10 min past the actor's largest observed verify-cadence gap … coordinator-reconciled (verify PASSED firejail at `5288abb9`, exactly the 11 leased files, house secret scan clean)" | `5288abb9…` exists, is the parent of the PR-83 merge head `ba2a53c` ("Merge branch 'main' into rails/r01-contract"), is an ancestor of `main`, and carries exactly the 11 leased files. The timing and firejail verdict are host-held — DISCLOSED under D2 | commit verified; timing/verdict = host-held (disclosed) |
| review APPROVED zero blocking (att_2f3801d4091b4589, 8/8 checks incl. spec-conformance spot-check mapping every R01-row requirement to tests, both-ways RED mutation, 2 full-suite failures proven pre-existing at base via base-worktree counterfactual) | `origin/review/pr83` (= `0d3185c…`, subject `bundlebees: apply verified attempt att_2f3801d4091b4589`) carries `docs/review-pr83.md`: first line APPROVED, exactly 8 `## Check` headings all PASS, Check 4 = the 8-requirement spec-conformance mapping, Check 3 = both-ways mutations, Check 2 = base-worktree counterfactual for the 2 pre-existing failures | TRUE (every element read on the origin review branch) |

## Check 4 — MERGED_WINDOW_ROWS keyword coverage: PASS (with D5 observation)

- pr 82 row keywords `("trial-harness", "test_trial_harness", "att_e1f3fb747b354685", "PART 1")` — **all 4 appear in the #82 bullet itself** (verified by exact substring match against the bullet line).
- pr 83 row keywords `("RAILS-R01", "test_rails_contract", "att_e0cff87d85a644e5", "hash-vectors")` — `test_rails_contract`, `att_e0cff87d85a644e5` and `hash-vectors` appear in the #83 bullet itself; the literal `RAILS-R01` does not (the bullet says "the Rails R01 contract layer" / "branch rails/r01-contract" / "the frozen spec's R01 acceptance shape"). `RAILS-R01` IS present in the `## Unreleased` section the guard actually scans — via the #74 bullet ("a live `run_beat` probe shows RAILS-R00's landing making RAILS-R01 eligible") — so `test_merged_campaign_pr_has_discoverable_changelog_coverage[pr-83]` passes.
- D5 (non-blocking): this matches the accepted house precedent — the #80 row's `RAILS-R00` keyword likewise lives outside the #80 bullet (in the same #74 bullet and the wave-2 seed bullet). The guard's enforced scope is the whole Unreleased section (test line 517), and the section-level check passes for both new rows. Recorded as an observation, not a defect.

## Check 5 — EXCLUDED_PRS[84] wording: PASS

- The new entry names exactly the three contents of this PR: "the PR 82 + PR 83 coverage rows, their merged-window bullets and the RAILS-R01 backlog adoption", self-describes as "a registry bookkeeping change whose only content is this exclusion plus the #82/#83 registry rows, bullets and the R01 adoption", and closes with the house formula "it carries its own exclusion so merging it leaves main green".
- Shape match against 81 and 79: both read "docs-sync companion (…the PR N coverage row + its merged-window bullet) - same class: a registry bookkeeping change whose only content is this exclusion plus the #N registry row and bullet; it carries its own exclusion so merging it leaves main green". The 84 entry is the same template extended to two rows plus the adoption — no structural deviation.

## Check 6 — The RAILS-R01 backlog adoption: PASS (with D1/D4 disclosure posture)

- `git diff main..head -- plans/backlog.json` shows ONLY the RAILS-R01 slice changing status `planned` → `dispatched`, with exactly ONE slice-level transition carrying evidence `{attempt: att_e0cff87d85a644e5, pr: 83, merge_commit: c7b5ab3aeca0bc47f7150c7d05c5388f1bb37f5c, verified_head: 5288abb90b4c1130fbd0b622d5a099da898387cf}`, plus `attempt_id: att_e0cff87d85a644e5` and `updated_at: 2026-11-17T06:55:00Z` on the slice, plus exactly ONE appended top-level `transitions` entry (`slice: RAILS-R01, from: planned, to: dispatched`, same attempt and pr in its evidence). No other slice, key or section changed.
- Cross-checks against the REST refs fetched in checks 2/3: `merge_commit` `c7b5ab3…` is byte-identical to PR 83's REST `merge_commit_sha` and to today's `refs/heads/main`. `verified_head` `5288abb9…` is byte-identical to the verified content commit in check 3; it is an ancestor of `main` and the parent of the PR-83 merge head. It is NOT today's branch tip (`ba2a53c…`) — see D1.
- `plans/backlog.json` at the head parses as JSON (`json.loads` clean; top-level keys schema/budget/slices/transitions/decisions/seed_note; **24 slices**, statically counted).
- Loader probe posture (D4, disclosed): the installed `bundlebees_plugin` is NOT importable as real code in this sandbox — the package resolves only as an empty namespace stub and `from bundlebees_plugin import gate_watcher` raises ImportError, so the real `load_backlog` probe cannot run here. The coordinator ran it on the host: ACCEPT 24 slices, `_dependency_state` clears R00 and R01 — accepted as recorded, not re-executed by this review.

## Check 7 — Parity suite at the head: PASS

- Command: `python3 -m pytest tests/test_docs_parity.py` (pytest 9.2.0 in a fresh venv over system Python 3.12.3; system python3 has no pytest — same environment gap the r82 and r83 reviewers disclosed).
- Result: **40 passed, 1 skipped** — byte-for-byte the coordinator's reference count. Re-confirmed at the same count inside the real-history worktree at the head.
- Delivered-suite re-confirmation at the same head: harness 28 passed / 0 failed; contract 69 passed / 0 failed.

## Check 8 — RED-first mutation, BOTH ways: PASS (adoption flip honestly reported as unpinned)

- **Mutation A (remove the pr-83 row).** In the real-history worktree at `3194a19…`, the pr-83 `MERGED_WINDOW_ROWS` entry was deleted (verified `git diff` = exactly that block). RED: `test_registry_covers_every_merged_campaign_pr_in_window` FAILED with `merged campaign PR(s) [83] have no coverage registry entry` — the guard names **[83]** exactly as required — and `test_merged_numbered_bullets_carry_merged_state_not_in_review` FAILED alongside (`bullet #83 claims a state but its PR is neither registered merged nor in review`). Restore (`git checkout --`), tree clean: GREEN, **40 passed, 1 skipped**. Both ways demonstrated.
- **Mutation B (flip the adopted R01 status back to `planned`).** In the same worktree, `plans/backlog.json` RAILS-R01 `status` was flipped `dispatched` → `planned` (attempt_id left in place). The file still parses as JSON (re-loaded clean). The parity suite stays **40 passed, 1 skipped** — and the FULL suite at the mutated tree returns **996 passed, 4 skipped, 0 failed**: no in-repo test catches the flip. Grep confirms `tests/` contains no reader of `plans/backlog.json` beyond the parity guard's keyword rows. Stated honestly, as the brief anticipated: **the adoption is evidence-recorded, not test-pinned** — nothing in the repo fails if the adopted status is reverted; the evidence (transition + attempt id) stays but the status claim would silently contradict it. Restore → tree clean, parity 40/1 again. Both worktrees/mutations fully reverted; `git status` clean apart from this report.

## Check 9 — CI on PR #84: RECORDED (pending is fine)

- `gh pr checks 84` is unavailable here: `gh` is installed but unauthenticated (asks for `gh auth login`), so the CLI path is recorded as refused, same posture as the r83 reviewer's D6.
- Public REST fallback at the exact head `3194a19…`: `/commits/<head>/check-runs` → **14 check runs, all `completed`, conclusion `success`** — `bee-ci/secret-scan`, `gitleaks`, the four required protocol jobs (recovery, bee-landed, feature packet, return manifest), `campaign report protocol`, `observability record tests`, `reference demo + tests`, `cold-start acceptance (light, offline worker)`, both `project-state schemas + reference checker` legs (ubuntu-24.04, windows-latest), `bee-ci/project-state`, `bee-ci/reference`.
- Legacy combined status at the same head: state `pending` with 0 statuses posted — the same artifact the r82 reviewer documented (no legacy statuses exist to aggregate; the modern check-runs carry the signal), consistent with the PR's `mergeable_state: unstable`. Recorded, not blocking.

## Check 10 — Secret-scan of this report: PASS

- The report was scanned after writing against the house predicate families implemented locally (the real `bundlebees_plugin.security.looks_like_secret` is not importable in this sandbox — namespace stub, see check 6): name-ending-in token/secret/password/passwd/pwd/api_key/api-key/authorization followed by colon-or-equals plus a value; bearer ≥6 value chars; the sk-, ghp_, github_pat_ and xox-prefixed literal families; AKIA+16; AIza+20+; eyJ JWT triples.
- Result: **0 trips over every line of this file**. Negative controls (9 synthetic literals, one per family, written only in the throwaway scanner under /tmp, never in this report): 9/9 tripped, proving the scan runs (two of my first control literals were malformed for the exact-length rules and were corrected — the scanner was never wrong, the controls were, the same posture r82 recorded as its D3). Attempt ids (`att_…`), sha prefixes and branch names are not secret-shaped and do not trip any family.

## Disclosures (DISCLOSURE class; the blocking count is DEFECTS only)

- **D1 — campaign branch tips moved past their verified heads before merging (evidence-chain precision).** Today's ls-remote shows `docs/hindsight-trial-harness` = `dac605e…` and `rails/r01-contract` = `ba2a53c…`, NOT the verified heads `f7c9ca7…` / `5288abb9…` the bullets cite. Verified harmless: each tip is exactly one "Merge branch 'main' into …" commit whose parent is the cited verified head (parents read from the merged history), the REST pull records list those tips as the PR heads at merge time, and both verified heads are ancestors of the merge commits (`git merge-base --is-ancestor` → yes for both). The "verify PASSED at …" claims therefore reference real, merged content commits; the tips moved only by absorbing main. No defect — recorded so the evidence chain is read correctly.
- **D2 — host-held verify/campaign-record claims are unverifiable from this sandbox.** The in-sandbox check counts (4/4 for att_e1f3fb747b354685, 5/5 for att_e0cff87d85a644e5), the firejail verify verdicts, the ~34 min / ~10 min staleness windows, the beat-3 trigger, and the two earlier zero-commit losses (att_016d9b4d, att_affc3ee9) all live in the coordinator-host campaign record, which is not in this repo (grep: no mention of any of these attempt ids outside this PR's own additions). This review verified the landed artifacts (commits, file leases, review docs, suites) and discloses the rest as host-record-held rather than asserting it.
- **D3 — the F1 loss claim (att_fa13d94) is unverifiable here.** As prescribed: `verify-results/att_fa13d94acc6f4f72.json` is on the coordinator host, unreachable from the sandbox; the campaign record's account of the degenerate empty-envelope refusal cannot be read from this repo. DISCLOSED, not asserted.
- **D4 — the real loader probe cannot run here.** `bundlebees_plugin` resolves only as an empty namespace package in this sandbox (`gate_watcher` ImportError), so `load_backlog` and `_dependency_state` were not re-executed; the coordinator's host result (ACCEPT 24 slices; R00 and R01 cleared) is accepted as recorded. The static 24-slice count was verified locally from the JSON.
- **D5 — `RAILS-R01` is section-matched, not bullet-matched.** See check 4. Same shape as the accepted #80 precedent; the enforced section-level check passes.
- **D6 — tooling installs.** pytest and jsonschema were absent from the system interpreter and were installed read-only into a fresh venv under /tmp (outside the repo) — the same gap r82/r83 disclosed. No repository file outside this report was modified at commit time; both mutation worktrees were fully reverted (final full-suite at pristine head: 996 passed, 4 skipped, 0 failed).
- **D7 — the top-level transition's evidence carries `{attempt, pr}` only**, without `merge_commit`/`verified_head`. This matches the house shape of the existing R00 top-level entry (also `{attempt, pr}`); the fuller evidence lives on the slice-level transition where the brief requires it. Consistent, noted for completeness.

## Blocking findings

None. (Numbered blocking findings would be listed here as DEFECTs; there are none — every defect-shaped candidate above is a disclosed unverifiable-from-sandbox item or a precedent-consistent observation.)

## Verdict

APPROVED — PR #84 at `3194a19c17f0e8c0c737bf60b7d9a2e56d863f8b` is exact to its three-file delta, both merged-window bullets are truthful claim-by-claim to the extent verifiable from public refs and the origin review branches (host-held verify claims disclosed, not asserted), the RAILS-R01 adoption is a minimal single-transition adoption whose evidence matches the REST-verified merge refs, the guard is RED-first-proven both ways on the pr-83 row, the parity suite is 40/1 at the head, CI is 14/14 success, and the adoption flip is honestly reported as unpinned by any in-repo test.

```json
{"verdict": "APPROVED", "blocking_count": 0, "checks_passed": 10, "checks_total": 10}
```
