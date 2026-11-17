# Review: workflow PR 86 — docs-sync/rails-r02-adoption

Independent review of the RAILS-R02 backlog-adoption companion at the checked-out
head, mirroring the #81/#84/#85 pattern. This run is the retry of review attempt
att_762c7e5cefc14180, which completed all nine checks but lost its payload
collection because the workspace then contained a changed path that was a
DIRECTORY. Workspace rules honored this time: the only new path in the workspace
is this file (a regular file; the docs/ directory already existed), zero new
directories were created anywhere in the workspace, and every scratch, worktree,
clone and evidence file lives under /tmp/opencode (upstream clones of workflow
and bundlebees, the venv, the gitleaks binary, mutation scripts, extracted
blobs).

- PR: https://github.com/mojomast/workflow/pull/86 (open, not draft, not merged)
- Head: branch docs-sync/rails-r02-adoption at ec3e293 (full sha in the PR
  payload and in the local snapshot's base line; 8-hex forms used throughout
  this report to keep the scanner surface minimal)
- Base main: ca97847 (same sha as the PR payload's base ref and the local
  merge-base, so the three-dot and two-dot deltas coincide)
- Local checkout identity: the workspace tree hash equals the PR head tree hash
  (both 71f2ed5), so everything below was measured on the exact reviewed head.
- Head commits: f0c1090 (the adoption) and ec3e293 (the EXCLUDED_PRS row).

## Verdict

**APPROVE.** All nine checks pass; two non-blocking observations are disclosed
(the legacy commit-status gitleaks row at the head, and the fact that the
docs-parity suite itself does not pin the backlog slice state, so the RED proof
for the backlog mutation rides the targeted real-loader probe).

## Checks

| # | Check | Result | Core evidence |
|---|---|---|---|
| 1 | Delta exactness | PASS | merge-base = main tip; exactly 2 files; one slice transition mirrored once; deep-compare clean; loader accepts |
| 2 | Adoption-diff audit | PASS | bb PR 70 merged at 9287d91 with head 2f8ba10; attempt id in the head commit message; 7-file payload consistent |
| 3 | Real-loader probe | PASS | gw.load_backlog accepts: 24 slices, 6 transitions |
| 4 | Dependency probe both ways | PASS | cleared with the attempt succeeded; waiting with an empty world; pre-adoption edge permanently no_attempt |
| 5 | EXCLUDED_PRS row audit | PASS | entry 86 with a non-empty reason in the 81/84/85 class; number 86 confirmed via the API |
| 6 | Suite at head | PASS | 40 passed, 1 skipped |
| 7 | RED-first mutations | PASS | both backlog mutations and the emptied exclusion reason each turn RED; byte-identical restores |
| 8 | CI at the reviewed head | PASS | 14 of 14 check-runs success; one legacy status row contradicted and classified non-blocking (disclosed below) |
| 9 | Scanner hygiene | PASS | no secret-shaped trip in the 40 added lines; the single negative-control line below is the report's only trip |

### 1. Delta exactness

- Three-dot diff (merge-base of main and the PR head = ca97847, the main tip
  itself) over the upstream clone in /tmp: exactly
  `plans/backlog.json` (+34 -2) and `tests/test_docs_parity.py` (+6 -0); the
  public files endpoint for the PR lists the same two files with the same
  counts. No third path, no renames, no deletions.
- The backlog edit is one slice transition. Deep JSON comparison of the base
  and head documents: top-level key order unchanged; the 24-slice id list
  unchanged; the only deep-unequal slice is RAILSR02, and within it exactly
  four things changed — status planned to dispatched, the per-slice
  transitions list filled with one entry, attempt_id added, updated_at added.
  The appended top-level transition equals the slice-level entry minus the
  slice key (compared field by field), the two transition timestamps equal the
  updated_at value, and the attempt id in attempt_id equals the evidence
  attempt in both copies — mirrored exactly once each, never twice.
- Every other top-level member (schema, budget, decisions, seed_note) is
  deep-equal to main's. No formatting churn: the git diff has only the two
  expected hunks, and the real loader accepts the file unchanged (check 3).
- The tests edit appends one exclusion entry for PR 86 to EXCLUDED_PRS and
  nothing else.

### 2. Adoption-diff audit against primary sources

Primary record demanded by the transition: attempt att_f67c7573c44241fc, PR 70
in bundlebees, verified head 2f8ba10 (40-hex in the transition), merge commit
9287d91 (40-hex in the transition).

- Public API for mojomast/bundlebees PR 70: state closed, merged true,
  merged_at 2026-11-17T07:58:34Z, head sha 2f8ba10 (rails/r02-ledger), merge
  commit 9287d91 — all three hashes match the transition's evidence chain
  exactly.
- In the bundlebees clone: the merge commit 9287d91 has parents 17adb52 (the
  PR base) and 2f8ba10 (the PR head), its subject names PR 70 from
  rails/r02-ledger, and it is contained in bundlebees origin/main; the head
  2f8ba10 is an ancestor of the merge commit.
- The head commit's message is "bundlebees: apply verified attempt
  att_f67c7573c44241fc" — the attempt id in the transition's evidence is the
  one the landing commit itself names. The payload is the 7-file
  contrib/rizzstack_rails ledger set (ledger.py, contracts.py, privacy.py,
  __init__.py, vendor-manifest.json, scripts/vendor_rails.py,
  tests/test_rails_ledger.py), matching the transition reason's "7-file
  payload" claim including the acceptance suite name.
- Transition-reason cross-checks: "CI 4/4 SUCCESS at the exact head" and the
  merged timestamp agree with the API; the bb docs-sync companion 2b6289c is
  the bb main commit adding the merged-window coverage rows for PRs 68, 69
  and 70, exactly as the reason states.
- Honest scope note: the review-child approval (att_87b7215d796c41c7, 8 of 8)
  and the r1/r2 zero-delivery losses (att_7021e06e, att_2e8118ca) are
  launcher-side records and are not independently verifiable from the public
  surface; the four independently verifiable anchors (attempt-named landing
  commit, PR number, verified head, merge commit + merged state) all check
  out.

### 3. Real-loader probe

With bundlebees_plugin imported from the pinned bb checkout in /tmp
(gate_watcher 8.21.2-era main), `gw.load_backlog` on the checked-out
`plans/` directory returns cleanly:

- schema bundlebees.gate-backlog/1 accepted; 24 slices; 6 top-level
  transitions; budget lanes 7, bees 8.
- The normalized RAILSR02 record: status dispatched, attempt_id
  att_f67c7573c44241fc, updated_at 2026-11-17T08:05:00Z.
- Five slices depend on RAILSR02 (R04, R08, R10, R11, R17C), so this edge is
  live wave-front plumbing, not decoration.

### 4. Dependency probe, both ways, and the pre-adoption asymmetry

`gw._dependency_state('RAILS-R02', by_id, world)`:

- World where att_f67c7573c44241fc is succeeded: **cleared**, evidence names
  the dep, the attempt and state succeeded.
- Empty world (attempt_state answers None): **waiting**, evidence state null
  — fail-closed, never cleared on an unprovable probe.
- Pre-adoption tree (git show of main's plans/backlog.json loaded through the
  same real loader): the RAILSR02 slice carries NO attempt_id and status
  planned. The edge answers waiting with state planned; and if the status is
  force-set to dispatched on that tree (a thought experiment, not the PR's
  content), the edge answers waiting with state **no_attempt** — with no
  attempt to probe, the edge could never clear. **The asymmetry this PR
  removes: before the adoption the R02 edge was permanently no_attempt (a
  dispatched-status R02 would still block every dependent forever); after it,
  the edge is probeable and clears on the real succeeded attempt.** That is
  the mechanical meaning of the adoption: five downstream slices can now
  advance on a verifier-backed signal instead of stalling on an unfillable
  field.

### 5. EXCLUDED_PRS[86] audit

- tests/test_docs_parity.py carries an EXCLUDED_PRS entry keyed 86 with a
  non-empty reason that states the class: a docs-sync companion whose only
  content is the exclusion plus the adoption transition, "same class as
  81/84/85", carrying its own exclusion so merging it leaves main green.
- The three cited siblings verified via the public API as docs-sync
  companions: PR 81 (coverage for PR 80 + R00 adoption), PR 84 (PRs 82+83
  rows + R01 adoption), PR 85 (R03 adoption) — same class, same shape.
- The reviewed number is really 86: the API pull record for
  mojomast/workflow number 86 has the title "docs-sync: adopt the RAILS-R02
  landing (bb PR 70 merged as 9287d91)" on the reviewed head branch — the
  same number the test file excludes.

### 6. Suite at head

`python3 -m pytest tests/test_docs_parity.py -q` in the workspace, venv with
pytest 9.2.0, bytecode and cache writes suppressed so the run creates nothing
in the workspace: **40 passed, 1 skipped in 0.06s** — exactly the expected
green. `git status` before and after: clean.

### 7. RED-first mutations, both ways

Baseline sha256 recorded before any mutation and re-verified after each
restore:

- plans/backlog.json — 297ac953 (24-hex prefix shown; full values in
  /tmp/opencode/sha_head.txt)
- tests/test_docs_parity.py — 6aa94fe7 (24-hex prefix shown)

- Mutation A1 (drop attempt_id from the RAILSR02 slice, one surgical line
  deletion): the targeted real-loader probe —
  `_dependency_state('RAILS-R02', by_id, succeeded-world)` — flips from
  **cleared** to **waiting** with state no_attempt. RED. Restored
  byte-identical (sha256 matches the baseline).
- Mutation A2 (flip the RAILSR02 status back to planned, one surgical line
  edit): the same probe flips to **waiting** with state planned. RED.
  Restored byte-identical.
- Mutation B (empty the EXCLUDED_PRS[86] reason in
  tests/test_docs_parity.py): the suite FAILS — 1 failed, 39 passed, 1
  skipped; the failing test is
  test_registry_covers_every_merged_campaign_pr_in_window at its
  reason-must-state-why assertion. RED. Restored byte-identical.
- Instrument note (disclosed, non-blocking): the docs-parity suite asserts
  the registry and coverage rows but does not pin the RAILSR02 slice state,
  so for the backlog mutations the targeted real-loader probe is the RED
  instrument, as the review brief allows. The two mutations land on exactly
  the fields the adoption introduced, proving both are load-bearing.

### 8. CI at the exact reviewed head (public API)

- Check-runs API at ec3e293: **14 of 14 completed, all success**, including
  both gitleaks-class gates (`gitleaks` and `bee-ci/secret-scan`) plus
  reference, project-state (two OS jobs), observability, return-manifest,
  recovery, feature-packet, bee-landed, campaign-report, cold-start and
  demo/reference jobs. Nothing in progress at read time, so the non-blocking
  in-progress clause never engages; the local suite result (check 6) stands
  beside a fully green check-run surface.
- Wrinkle, disclosed and classified non-blocking: the legacy commit-status
  API at the same sha shows three posted statuses — bee-ci/reference success,
  bee-ci/project-state success, and bee-ci/secret-scan **failure**
  ("gitleaks reported findings at ec3e293", no target url). Three independent
  measurements contradict that failure row for THIS head's content: (a) both
  Actions gitleaks check-runs at the same sha are success; (b) a local
  gitleaks 8.21.2 (downloaded checksum-verified) full-history run with
  `--all` over the upstream clone containing the head reports **no leaks
  found** across 250 commits, and the workspace snapshot is also clean; (c)
  the reviewer's own per-line scan of the 40 added diff lines (check 9) finds
  no secret-shaped token. The failure row's shape matches the remedy main
  itself documents at 88e7b00: a coordinator-run default all-refs gitleaks
  probe tripping on local side branches that are NOT ancestors of the
  scanned head, not on the head's content. The bee-ci/secret-scan check-run
  posted later the same minute-window (08:06) is success, consistent with the
  mechanical gate re-running clean. Carried as open issue OI-1, not a merge
  blocker.

### 9. Scanner hygiene (self-scan of every added line)

Instrument: the six gate rules as recorded in the backlog's own gate text —
(1) the name-colon-value trap, (2) the Bearer+6 shape, (3) the sk-/ghp_/
github_pat_/xox prefixes, (4) AKIA/AIza prefixes, (5) the eyJ JWT shape,
(6) the 32-plus mixed-alphanumeric run — plus the private-key regex. Each of
the 40 added lines (34 in plans/backlog.json, 6 in tests/test_docs_parity.py)
was tested against all six rules and the private-key regex:

- Rules 1, 2, 3, 4, 5 and the private-key regex: **zero hits** across all 40
  added lines.
- Rule 6: 4 hits, all the same two values mirrored twice (the evidence chain
  records each hash once in the slice transition and once in the top-level
  transition): the 40-hex verified head and the 40-hex merge commit. Both are
  public git object identifiers verified live against the GitHub API in check
  2 — commit hashes, not credentials, and the same identifiers main's own
  changelog prints in short form. Classified benign, no rewrite needed; any
  reviewer can re-derive them from the API record.
- This report contains exactly one mandated negative-control line (below) and
  the scanner run over this report after writing returns exactly that one
  trip and nothing else.

Negative control (mandated single trip; coordinator-owned synthetic marker, NOT a secret, carries no credential value and exists only to prove the scanner's Bearer+6 rule is live): the string Authorization: Bearer SYNTHETIC-NEGATIVE-CONTROL-0000 appears on this line and nowhere else in this report.

## Post-commit verification (update commit)

Re-ran the full battery against the committed state on review/pr86 after the
early commit:

- Suite: 40 passed, 1 skipped again (bytecode and cache writes suppressed;
  the run creates nothing in the workspace).
- Real-loader dependency probe: still **cleared** with the succeeded-world —
  the workspace is back on the exact reviewed content.
- sha256 re-verification: plans/backlog.json and tests/test_docs_parity.py
  match the pre-mutation baseline values exactly (the RED mutations left no
  residue); this report hashes fa318fc9 (24-hex prefix shown).
- `git status --porcelain` empty; `git clean -nd` empty — the working tree
  contains exactly one added path relative to the seed commit (this report)
  and zero added directories, so the payload-collection failure mode of the
  prior attempt (a changed path that was a DIRECTORY) cannot recur from this
  review's output.
- Report self-scan after the commit: exactly one trip, the mandated
  negative-control line; no other line trips any rule.

## Open issues (non-blocking)

- OI-1: the legacy commit-status row bee-ci/secret-scan = failure at the
  reviewed head (see check 8). Contradicted by both Actions gitleaks
  check-runs at the same sha, by a local full-history gitleaks run, and by
  the per-line scan; matches the false-attribution class main documents at
  88e7b00. Non-blocking; worth the coordinator re-running the probe scoped to
  the head's ancestry to retire the stale row.
- OI-2: the docs-parity suite does not pin the RAILSR02 slice state, so the
  backlog RED proof rides the targeted real-loader probe (see check 7). A
  future companion could add a suite-level assertion over the transition
  record; not a defect of this PR.

## Summary

```json
{
  "summary": "APPROVE - all nine checks pass on the exact reviewed head (tree hash equal to the PR head tree); one slice transition mirrored once, loader-accepted, primary-source chain verified live (bb PR 70 merged at 9287d91 from head 2f8ba10, attempt-named landing commit), dependency edge probeable both ways, exclusion row in the 81/84/85 class, suite green 40 passed 1 skipped, RED-first proven both ways with byte-identical restores, CI 14/14 check-runs success with one disclosed non-blocking legacy status row, and scanner hygiene clean with exactly one mandated negative-control line; retry of att_762c7e5cefc14180 with the workspace rules honored (one new regular file, zero new directories, all scratch under /tmp)",
  "changed_files": [
    "plans/backlog.json (PR delta, reviewed; restored byte-identical after the RED mutation)",
    "tests/test_docs_parity.py (PR delta, reviewed; restored byte-identical after the RED mutation)",
    "docs/review-pr86.md (this review - the only path created by the reviewer, a regular file, no directories)"
  ],
  "checks": [
    {"name": "delta-exactness", "command": "git diff --name-status merge-base..pr86 in /tmp clone + JSON deep-compare + pulls/86/files API", "passed": true},
    {"name": "adoption-diff-audit", "command": "curl pulls of bb PR 70 + git log/merge-base in the bb clone", "passed": true},
    {"name": "real-loader-probe", "command": "python3 gw.load_backlog(workspace) from the bb checkout in /tmp", "passed": true},
    {"name": "dependency-probe-both-ways", "command": "gw._dependency_state('RAILS-R02', by_id, world) succeeded-world vs empty-world + pre-adoption tree", "passed": true},
    {"name": "excluded-prs-86-audit", "command": "read tests/test_docs_parity.py + pulls/81,84,85,86 API", "passed": true},
    {"name": "suite-at-head", "command": "python3 -m pytest tests/test_docs_parity.py -q (venv pytest 9.2.0)", "passed": true},
    {"name": "red-first-both-ways", "command": "mutation A1 attempt_id drop, A2 status flip (targeted loader probe), B reason emptied (pytest), sha256 before/after", "passed": true},
    {"name": "ci-at-reviewed-head", "command": "curl commits/ec3e293.../check-runs + /status + local gitleaks --all", "passed": true},
    {"name": "scanner-hygiene", "command": "six-rule + private-key regex scan of all 40 added lines + report self-scan", "passed": true}
  ],
  "open_issues": [
    "OI-1 non-blocking: legacy commit-status bee-ci/secret-scan failure row at the reviewed head, contradicted by both Actions gitleaks check-runs (success), a local full-history gitleaks --all run (no leaks, 250 commits), and the per-line scan; matches the false-attribution class documented on main at 88e7b00",
    "OI-2 non-blocking: the docs-parity suite does not pin the RAILS-R02 slice state, so the backlog RED proof rides the targeted real-loader probe; a suite-level transition assertion is a possible follow-up"
  ]
}
```
