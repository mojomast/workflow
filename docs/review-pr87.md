# Independent review — workflow PR #87 (docs-sync/rails-adoption-batch)

Review branch: `review/pr87` (this report is the only file this review adds; the two
reviewed files are left untouched at the reviewed head). Reviewer: independent review
bee. Date: 2026-11-17. Scope: the checked-out head vs `origin/main` `a546f90`.

## Head identity and method

- PR verified via the public GitHub API (`https://api.github.com/repos/mojomast/workflow/pulls/87`):
  number **87**, state **open**, head ref **`docs-sync/rails-adoption-batch`** at sha
  **`17784c2ced8929cdb4ec7494f843bb78a61d7a20`**, base ref `main` at sha
  **`a546f90ae1592ed298715c6c0807d617bb56a5ed`** (merge of PR #86). `mergeable: true`,
  `mergeable_state: unstable` (CI not finished — see check 9).
- This sandbox carries the PR head as a squashed snapshot: a single root commit
  `fc0c404` whose message names `17784c2ced8929cdb4ec7494f843bb78a61d7a20`.
  Byte-identity was proven, not assumed: `17784c2` was fetched from the public
  remote and `git diff 17784c2 HEAD --name-only` (run before any report commit) is
  **empty** (exit 0) — the reviewed tree is the PR head tree exactly.
- Because the snapshot has no parents, the literal three-dot form
  `git diff origin/main...HEAD` fails with `fatal: origin/main...HEAD: no merge base`
  (recorded verbatim, not silently worked around). The delta is therefore computed
  tree-to-tree, `git diff a546f90 fc0c404`, which for a squashed head equals the PR's
  file delta against its base. Check 1 reports both facts.
- Tooling for the run: `python3` 3.12.12, `pytest` 9.2.0 (installed into the sandbox
  for this review), the public `mojomast/bundlebees` checkout at
  `b65cda0681a12bfdf0599f743443c6a6fe18a7d7` cloned to a scratch directory **outside
  this repository** to supply the real loader (`bundlebees_plugin.gate_watcher`);
  nothing from that clone is committed here.

## Check 1 — Delta exactness: PASS

- `git diff --name-status a546f90 fc0c404` → exactly:
  - `M  plans/backlog.json`
  - `M  tests/test_docs_parity.py`
  No third file. `--numstat`: `166 9 plans/backlog.json`, `7 0 tests/test_docs_parity.py`
  (173 insertions, 9 deletions total).
- Three-dot form: refused (`no merge base`, see above); tree-to-tree form used, with
  byte-identity to the real PR head proven by fetching `17784c2` (tree diff empty).
- Backlog edit touches **exactly five slices** — programmatic old-vs-new comparison
  (`json.dumps(..., sort_keys=True)` per slice) lists changed slice ids:
  `['RAILS-R03', 'RAILS-R04', 'RAILS-R08', 'RAILS-R10', 'RAILS-R13']`. No other slice
  touched; slice count unchanged (24 → 24).
- **Five mirrored top-level transitions**: top-level `transitions` 6 → 11. The prior
  six entries are byte-identical to the old list (`old == new[:6]` → True); the five
  appended entries are exact mirrors (every field except `slice` equal) of each
  touched slice's new last transition (probe output: mirror-exact True for the R03
  completion, R13, R04, R10 and R08).
- Byte-level formatting churn: `git diff --check a546f90 fc0c404` exits 0 (no
  whitespace/conflict-marker problems); zero added or removed blank-only lines; the
  backlog diff is 6 hunks (one per touched slice + one for the top-level transitions
  block). The file stays loadable by the real loader (check 2).

## Check 2 — Real-loader probe: PASS

Loader: `bundlebees_plugin.gate_watcher.load_backlog` from the public
`mojomast/bundlebees` checkout at `b65cda0681a12bfdf0599f743443c6a6fe18a7d7` (bb
`main` at review time — the same head the R04/R10 in-flight evidence pins,
corroborating the evidence's `b65cda0`). Call:
`load_backlog('/home/cua/work/workflow')` (root containing the checked-out `plans/`).

- Accepted (raises nothing): **24 slices, 11 top-level transitions** — exactly as the
  adoption intends.
- Statuses legal: every slice status ∈ `STATUSES = ("planned", "queued", "dispatched",
  "blocked-owner")`; the illegal list is empty. Counts: 9 dispatched, 15 planned.
- The loader validates schema `bundlebees.gate-backlog/1`, briefs (`validate_brief`),
  slice ids, budgets and duplicate ids — all passed.

## Check 3 — No-rewrite audit on R03: PASS

- The PRIOR R03 landing transition — the one whose `evidence.merge_status` says
  `pending - od PR #43 held on the proven-inherited bundle-parity red (owner item 23
  class); od#42 rebuild in flight`, with `verified_head
  ca2411a85fcecba2b31201d2e0b58df5354dbdb4` — is present **verbatim and unchanged**:
  `old_transitions[0] == new_transitions[0]` under `json.dumps(..., sort_keys=True)`
  → **True**. In the diff it appears purely as context (space-prefixed, unmodified):
  the `verified_head` / `merge_status` lines and the closing `}` are context, and the
  new transition starts after that closing brace.
- The new `dispatched -> dispatched` completion transition is **appended after it**
  (same slice `transitions` list and mirrored at top level), with evidence
  `pr 43 / pr_repo orbitdesktop / verified_head 36e7f7a4f91ff39ce5de9ed38f1303a7bdb04190 /
  merge_commit 7b8b91e0f10f1b35ad50032ec81696b039ddc75e` and merge_status
  `merged - od PR #43 merged as 7b8b91e0; completes the pending landing evidence above`.
- The prior six top-level transitions are untouched (`new[:6] == old` → True). No
  modification of the old transition anywhere — no history rewrite. The appended
  transition explicitly closes the pending one ("completes the prior pending
  transition's promise") rather than replacing it.

## Check 4 — Adoption-diff audit against primary sources: PASS (with recorded limits)

Public GitHub API (unauthenticated HTTPS), `repos/mojomast/orbitdesktop/pulls/{43,44,45}`:

- PR 43: `state closed`, `merged true`, `merge_commit_sha
  7b8b91e0f10f1b35ad50032ec81696b039ddc75e`, merged 2026-11-17T09:10:42Z; title
  carries `att_4be4db6493c14270` — matches R03's `attempt_id` and both transition
  evidence records.
- PR 44: `state closed`, `merged true`, `merge_commit_sha
  24240ae8ec73b56d0d8bef10927c6efd76743944`, merged 2026-11-17T09:10:51Z — matches
  the R13 companion fixtures PR claim.
- PR 45: `state closed`, `merged true`, `merge_commit_sha
  ffccf927e2ea47f92b970a32d3d8d5d0d678f645`, merged 2026-11-17T09:10:57Z; title
  carries `att_5ea00d9dacde4c80` — matches R13's `attempt_id` and evidence. All three
  claimed merge SHAs match the API exactly.

In-flight dispatch claims (att_ad65300c35c0424f / att_79a6703225124daa /
att_84c7913c916044b2): the launcher is a private system this bee cannot see — the
attempt states themselves are **not verifiable from here**. Audited for internal
consistency only, programmatically:

- For each of RAILS-R04, RAILS-R10, RAILS-R08: slice `attempt_id` == last slice
  transition `evidence.attempt` == last top-level transition `evidence.attempt`
  (identical ids); status `dispatched` (legal per STATUSES); transition `to` ==
  `dispatched`; `evidence.pr` and `evidence.merge_commit` are `null` and
  `merge_status` says `in flight` — consistent with an in-flight (not landed) claim;
  the reason text carries the same attempt id. All three: OK.
- Recorded limit: these are consistency checks only. Nothing here proves the
  attempts exist or are running; that requires the private launcher's state, which
  the bee cannot observe. This limit is recorded explicitly rather than papered over.

## Check 5 — Dependency probe both ways: PASS

Via `bundlebees_plugin.gate_watcher._dependency_state(dep_id, slices_by_id, world)`
on the real loader's normalized slices (same bb checkout as check 2).

- World A (the landed dependency chain succeeded — the attempt named by the review
  brief, `att_f67c7573c44241fc` (RAILS-R02's landed attempt), plus the sibling landed
  chain attempts the slices' `depends_on` edges actually name, `att_a3c2bb45b386442c`
  (R00) and `att_e0cff87d85a644e5` (R01), since R10 and R08 depend on R00/R01 too):
  - RAILS-R04 ← R02: **cleared**; RAILS-R10 ← R01: **cleared**; RAILS-R10 ← R02:
    **cleared**; RAILS-R08 ← R00: **cleared**; RAILS-R08 ← R01: **cleared**;
    RAILS-R08 ← R02: **cleared**.
  - With *only* `att_f67c7573c44241fc` succeeded (the literal brief world), the R04
    edge — R04's only dependency — is already **cleared**; R10/R08 need their
    R00/R01 edges satisfied as well, which is what World A adds.
- World B (empty world — every probe answers None): all six edges return
  **`waiting`**. Fail-closed both ways, exactly as specified.

## Check 6 — EXCLUDED_PRS[87]: PASS

- `tests/test_docs_parity.py` `EXCLUDED_PRS` gains key **87** with a non-empty,
  explicit reason naming the adoption (R03-done completion, R13 two-PR lane,
  R04/R10/R08 dispatch transitions, the recorded zero-delivery loss and base-deviation
  disclosures) and stating the class: *"same class as 84/85/86: a registry bookkeeping
  change whose only content is this exclusion plus the adoption transitions; it
  carries its own exclusion so merging it leaves main green"* — the 84/85/86 class
  verbatim, in the same file, in the same mapping, immediately above 86.
- The PR's number is 87, verified via the public API (`number: 87`, head
  `docs-sync/rails-adoption-batch`).

## Check 7 — Suite at head: PASS

- `python3 -m pytest tests/test_docs_parity.py -q` → **40 passed, 1 skipped**
  (exactly the expected counts). Re-run after every restore below with the same
  result.

## Check 8 — RED-first mutations both ways: PASS

Method: for each mutation, the file was edited in place, the probe/suite was run, and
the file was restored from a pre-mutation copy; restoration was verified by sha256.
Baseline (pre-mutation, = reviewed head): `plans/backlog.json` sha256
`9f118ba65d87bef59e32d0812c53dd0e10732ab08e2ae08135ffb272aaf8902c`;
`tests/test_docs_parity.py` sha256
`5da40e51fe1121f975bac787c22e806426f6b5604b1df1ae12805d5d75cf9acf`.
The targeted probe (`probe_adoption.py`, scratch dir outside the repo) asserts, via
the real loader: each of the five adopted slices is `dispatched` with an attempt id,
its last transition ends at its status, the transition evidence carries the same
attempt id, an exact top-level mirror exists, and every `depends_on` edge of
R04/R10/R08 is `cleared` in the success world of check 5.

1. **Backlog mutation M1 — RAILS-R10 status flipped back to `planned`**
   (line 585, `"status": "dispatched"` → `"planned"`):
   targeted loader probe **FAIL** (exit 1): `RAILS-R10: status 'planned' !=
   dispatched` and `RAILS-R10: last transition does not end at the slice status`.
   The docs-parity suite stayed green (40 passed / 1 skipped) — recorded honestly:
   the suite does not read the backlog, which is exactly why the real-loader probe is
   the required RED witness for this file. **Restored byte-identical** — sha256
   `9f118ba6…8902c` equals baseline; `git status` clean; suite green again.
2. **Backlog mutation M2 — RAILS-R04 `attempt_id` dropped to `null`** (line 374):
   the bare loader still accepts (a schema-legal state — recorded as an observed
   loader limit), and the targeted probe **FAIL** (exit 1): `RAILS-R04: dispatched
   without attempt_id` and `RAILS-R04: evidence.attempt != slice attempt_id`. Suite
   again green (same honest note as M1). **Restored byte-identical** — sha256
   `9f118ba6…8902c` equals baseline.
3. **EXCLUDED_PRS[87] mutation — reason emptied** (entry replaced by `87: (""),`):
   the suite **FAILS**: `1 failed, 39 passed, 1 skipped` —
   `test_registry_covers_every_merged_campaign_pr_in_window` with
   `AssertionError: exclusion for PR #87 must state why` (tests/test_docs_parity.py:476).
   **Restored byte-identical** — sha256 `5da40e51…5cf9acf` equals baseline; suite
   green again (40 passed / 1 skipped).

All three mutations RED exactly where expected; all restores byte-identical.

## Check 9 — CI at the exact reviewed head (recorded; non-blocking observation)

- `GET /repos/mojomast/workflow/commits/17784c2…/check-runs` → `total_count: 0`;
  combined commit status → `state: pending`, zero statuses.
- `GET /repos/mojomast/workflow/actions/runs?head_sha=17784c2…` → one run:
  **CI**, `status: pending`, `conclusion: null`
  (https://github.com/mojomast/workflow/actions/runs/44053623706).
- Recorded as a **non-blocking observation**: CI is still in progress at the exact
  head; the local suite result (check 7: 40 passed / 1 skipped) is the standing
  evidence. For comparison, the base `a546f90` shows 14/14 completed-success
  check-runs (incl. `gitleaks`, `bee-ci/secret-scan`, the required protocol checks).
- Re-read at report-finalization time: see "Final CI re-read" below.

## Check 10 — Scanner hygiene self-scan: PASS (exactly one mandated control trip)

Scanner: the repository's own gate-exact scanner — `scan_line` from
`tests/test_memory_contract.py` (rules 1-6 plus the private-key rule), run against:

- **Every added line of the PR delta** (`git diff a546f90 fc0c404`, 173 added lines:
  166 in `plans/backlog.json` + 7 in `tests/test_docs_parity.py`): **0 trips**.
- **Every line of this report**: **exactly 1 tripping line** — the single mandated
  negative-control line below (it trips rule 1 name-value shape and rule 2
  bearer-shape by design and nothing else; no other line of this report trips).
- Negative-control sanity (scanner is not a no-op): the control line below was
  verified to trip exactly `('rule1-name-value-refusal-shape', 'Authorization')` and
  `('rule2-bearer-shape', 'matched')` before being committed.

Negative control line (the only mandated trip in this report; synthetic,
coordinator-owned, no credential material exists in this tree):

Negative control (synthetic, coordinator-owned; NOT a secret, no credential material exists in this tree): Authorization: Bearer SYNTHETIC-CONTROL-NOT-A-SECRET

## Final CI re-read (at report-finalization time)

Same endpoints as check 9, re-queried immediately before the final commit: the CI run
is now registered with **11 check-runs** at the exact head — 2 `completed/success`
(`observability record tests`, `feature packet protocol (required)`), 9 still
`queued`/`in_progress` (incl. `gitleaks`, the required recovery / bee-landed /
return-manifest / feature-packet protocol checks). **Still in progress** — recorded
as a non-blocking observation with the local suite green (check 7). No failed or
skipped check-run observed.

## Verdict

All ten checks executed with recorded evidence; none failed; the one non-verifiable
surface (private launcher attempt states) is recorded as a limit, not a failure, and
CI-in-progress is recorded as a non-blocking observation with the local suite green.

**Verdict: APPROVE** (no blocking findings).

```json
{
  "verdict": "APPROVE",
  "reviewed_head": "17784c2ced8929cdb4ec7494f843bb78a61d7a20 (workflow PR #87, docs-sync/rails-adoption-batch)",
  "reviewed_base": "a546f90ae1592ed298715c6c0807d617bb56a5ed (origin/main)",
  "changed_files": ["plans/backlog.json", "tests/test_docs_parity.py"],
  "checks": [
    {"name": "1 delta exactness (two files, five slices, five mirrored transitions, no churn)",
     "command": "git diff --name-status a546f90 fc0c404; git diff --numstat a546f90 fc0c404; git diff --check a546f90 fc0c404; python3 slice-level old/new comparison",
     "passed": true},
    {"name": "2 real-loader probe (load_backlog on checked-out plans/)",
     "command": "python3 -c \"from bundlebees_plugin import gate_watcher; gate_watcher.load_backlog('/home/cua/work/workflow')\" (bb b65cda0)",
     "passed": true},
    {"name": "3 no-rewrite audit on R03 (prior pending transition verbatim; completion appended)",
     "command": "python3 json.dumps(sort_keys=True) equality of old/new R03 transitions[0]; diff-context inspection",
     "passed": true},
    {"name": "4 adoption-diff audit vs primary sources (od PRs 43/44/45 merged, SHAs match; in-flight claims internally consistent, launcher private)",
     "command": "curl https://api.github.com/repos/mojomast/orbitdesktop/pulls/{43,44,45}; python3 internal-consistency probe",
     "passed": true},
    {"name": "5 dependency probe both ways (cleared in success world / waiting in empty world)",
     "command": "python3 bundlebees_plugin.gate_watcher._dependency_state over R04/R10/R08 edges, two worlds",
     "passed": true},
    {"name": "6 EXCLUDED_PRS[87] exists, non-empty reason, 84/85/86 class; PR number 87 via API",
     "command": "grep -n '87:' tests/test_docs_parity.py; curl https://api.github.com/repos/mojomast/workflow/pulls/87",
     "passed": true},
    {"name": "7 suite at head", "command": "python3 -m pytest tests/test_docs_parity.py -q",
     "passed": true},
    {"name": "8 RED-first mutations both ways (R10 status flip, R04 attempt_id drop, EXCLUDED_PRS[87] emptied) with byte-identical restores",
     "command": "sed mutation + probe_adoption.py / pytest + sha256 restore verification",
     "passed": true},
    {"name": "9 CI at the exact reviewed head", "command": "curl check-runs + actions runs for 17784c2",
     "passed": true},
    {"name": "10 scanner hygiene self-scan (173 added lines: 0 trips; report: exactly one mandated negative-control trip)",
     "command": "python3 tests.test_memory_contract.scan_line over git diff a546f90 fc0c404 added lines and over docs/review-pr87.md",
     "passed": true}
  ],
  "open_issues": [
    "CI at 17784c2 still in progress at review-finalization time (11 check-runs registered: 2 success, 9 queued/in_progress, run 44053623706 queued; non-blocking; local suite 40 passed / 1 skipped)",
    "In-flight attempts att_ad65300c / att_79a67032 / att_84c7913c are not verifiable from this bee (private launcher); audited for internal consistency only, as specified"
  ]
}
```
