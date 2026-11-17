# Independent review — workflow PR #85 (docs-sync: RAILS-R03 backlog adoption)

APPROVED

- PR: mojomast/workflow#85 — "docs-sync: RAILS-R03 backlog adoption (att_4be4db64 -> od PR #43, coordinator-apply chain)"
- Reviewed head: `fe424e57251d3450886e1d9b3df754d8a3b15270` (branch `docs-sync/rails-r03-adoption`, 2 commits)
- Base: `main` at `330515398a638a30c241e6217b1269d962f1f80a`
- Verdict: **APPROVED** — blocking findings (DEFECT-class only): **0**
- Checks: 9 passed / 9 total

## Grounding (verified twice; no head movement disclosed)

- `git ls-remote https://github.com/mojomast/workflow` at review start:
  `refs/pull/85/head = fe424e57251d3450886e1d9b3df754d8a3b15270`, `refs/heads/main = 330515398a638a30c241e6217b1269d962f1f80a` — both match the brief exactly.
- REST `/repos/mojomast/workflow/pulls/85`: `head.sha = fe424e57251d…`, `base.sha = 330515398a6…`, state open, 2 commits, `changed_files = 2`, mergeable true / `mergeable_state: unstable` (CI verdicts all green — check 8).
- The head commit is `fe424e57…` "docs-sync: EXCLUDED_PRS[85] self-exclusion for the R03 adoption companion" (parent `6b51d82f…` "docs-sync: adopt RAILS-R03 landing into the backlog …", parent of that = base). Tree at head: `8e2998c1b9ebfa93e1e65bcf9800570f2f97ba5d`.
- The local checkout used for this review is **byte-identical to the head tree**: all 414 tracked files compared by git blob SHA against the head tree — zero missing, zero extra, zero mismatched.
- Re-ground immediately before committing this report: `ls-remote` again returned `refs/pull/85/head = fe424e57251…`, `refs/heads/main = 330515398a6…` — **no head movement**.

## Environment deviations (disclosed; not DEFECTs)

1. The prescribed loader path `/home/clanker01/rizzstack/bundlebees` does not exist on this machine. The real loader was taken from the public source of record instead: `github.com/mojomast/bundlebees` cloned at `main = 17adb52f872a59f7876b08775e18c1d259fb7b2b`, file `bundlebees_plugin/gate_watcher.py` (1719 lines), imported exactly as prescribed (`from bundlebees_plugin import gate_watcher as gw`). The module exports `load_backlog`, `_dependency_state`, `World`, `SUCCESS_ATTEMPT_STATES`, `FAILED_ATTEMPT_STATES`.
2. The prescribed pytest venv (`/home/clanker01/.hermes/installs/…`) does not exist; pytest 9.2.0 was installed into a fresh venv on Python 3.12.3 and used for check 6.
3. `gh` CLI is installed but unauthenticated (`gh auth login` demanded); check 8 used the anonymous REST check-runs endpoint at the head instead. Same information, different transport.
4. The hyvv attempt store is not reachable from this machine, so the review-child claim (`att_15d1c1fd… APPROVED 9/9`) and the attempt's full store history could not be probed independently. The store-state claim (`failed`) was taken as disclosed; it is consistent with everything observable in check 4 and does not change the verdict either way.

## Check 1 — delta exactness: PASS

`git diff 330515398a638a30c241e6217b1269d962f1f80a..fe424e57251d3450886e1d9b3df754d8a3b15270 --name-status` (real objects from a scratch clone of the public repo):

```
M	plans/backlog.json
M	tests/test_docs_parity.py
```

`--stat`: `plans/backlog.json | 1902 ++++--` (966 insertions / 936 deletions per the PR file view), `tests/test_docs_parity.py | 6 +`, total `2 files changed, 972 insertions(+), 936 deletions(-)`. Nothing else — exactly the two expected paths, matching the PR's own `changed_files: 2`. The large line churn on the JSON is re-serialization (indentation/formatting), not content change — proven semantically in check 2.

## Check 2 — adoption diff audit: PASS

Semantic audit: both revisions of `plans/backlog.json` parsed and recursively diffed (dict/list/value walk). **Total semantic deltas: exactly 5**, all on RAILS-R03 or its mirror:

1. `slices[RAILS-R03].status`: `"planned"` → `"dispatched"`
2. `slices[RAILS-R03].attempt_id`: added = `att_4be4db6493c14270`
3. `slices[RAILS-R03].updated_at`: added = `2026-11-17T07:31:00Z`
4. `slices[RAILS-R03].transitions`: 0 → 1 (the single new transition)
5. `transitions` (top-level list): 4 → 5 (the mirror)

The new transition (embedded form):

- `from: "planned"` → `to: "dispatched"`, `at: 2026-11-17T07:31:00Z`
- `evidence = {attempt: "att_4be4db6493c14270", pr: 43, pr_repo: "orbitdesktop", verified_head: "ca2411a85fcecba2b31201d2e0b58df5354dbdb4", merge_status: "pending - od PR #43 held on the proven-inherited bundle-parity red (owner item 23 class); od#42 rebuild in flight"}`
- The `reason` prose names the attempt, the coordinator-apply at od PR 43 head `ca2411a`, the scan-refusal provenance, the pristine-byte proof against upstream pin `d5d0f425`, the review child, and the merge-pending state. Exactly **one** new transition in the slice.
- Mirror check: `transitions[4]` at top level equals the embedded transition **exactly** after removing its `"slice": "RAILS-R03"` key (the key `_record_transition` adds) — mirrored exactly once.
- **No other change**: all 23 other slices byte-equal after parse; `budget = {lanes: 7, bees: 8}` unchanged; `decisions` unchanged; `seed_note` unchanged; `schema = bundlebees.gate-backlog/1` unchanged.
- External claims independently verified against the live repos:
  - od PR #43: `state = open`, `merged = false`, head `ca2411a85fcecba2b31201d2e0b58df5354dbdb4` — the merge-pending disclosure is **true** at review time (13 added files, +3148, vendored under `contrib/vibeline/` plus its own test file).
  - od PR #42 (the bundle rebuild): `state = open` — "in flight" is true.
  - Upstream pin `d5d0f425a64906ae1a50c1222314a5420da404d5` exists in `github.com/listeningpost/vibeline` (the vendor source; commit "Trust loopback only with a loopback Host header …").
  - **Byte-identity spot-check reproduced independently**: the three secret-scan-tripped files (`contrib/vibeline/README.md`, `contrib/vibeline/web.py`, `contrib/vibeline/web/index.html`) fetched from the pin and from the od#43 head are sha256-identical (`7c4dd60e…`, `3160139f…`, `2a3974a5…`). The "applied unmodified / pristine bytes" claim holds.

## Check 3 — the REAL loader at the head: PASS

Run in the head-identical checkout:

```
PYTHONPATH=<bundlebees main checkout> python3 - <<'EOF'
from bundlebees_plugin import gate_watcher as gw
bl = gw.load_backlog('.')
EOF
```

Result: **ACCEPTED — 24 slices**; `RAILS-R03` status `dispatched`, attempt `att_4be4db6493c14270`; schema `bundlebees.gate-backlog/1`; budget `{lanes: 7, bees: 8}`; R03 embedded transitions `[planned -> dispatched]`; top-level transitions 5.

## Check 4 — live dependency probe, BOTH ways: PASS (matches the disclosed gap)

A world stub implementing all five `World` members (`pr_state`, `attempt_state`, `fact_state`, `active_bee_leases`, `active_bee_count`), driving only `attempt_state`:

- **Real store state** (`attempt_state('att_4be4db6493c14270') = 'failed'`, the verify-refusal vocabulary):
  `('stale', {'dep': 'RAILS-R03', 'attempt': 'att_4be4db6493c14270', 'state': 'failed', 'reason': 'dependency_failed'})`
- **Counterfactual** (`'verified'`):
  `('cleared', {'dep': 'RAILS-R03', 'attempt': 'att_4be4db6493c14270', 'state': 'verified'})`
- Consequence confirmed live: the RAILS-R13 `depends_on` edge onto R03 evaluates `stale` under the real store state, so **R13's mechanical gate stays shut** — exactly the PR body's disclosure ("the coordinator-apply landing path has no store representation, so RAILS-R13's mechanical gate stays shut until the fact adapter (or a store-state remedy) reads adoption evidence. Counterfactual probe with state=verified clears. No silent assumption: this PR adopts the record; it does not claim the R13 gate is open."). **No mismatch.**

## Check 5 — EXCLUDED_PRS[85] audit: PASS

- `tests/test_docs_parity.py` adds exactly one entry: `85`, reason "docs-sync companion (the RAILS-R03 backlog adoption: planned->dispatched with the att_4be4db64 / od PR 43 coordinator-apply evidence chain) - same class as 81/84: a registry bookkeeping change whose only content is this exclusion plus the adoption transition; it carries its own exclusion so merging it leaves main green".
- **Truthful**: the delta is exactly the backlog adoption plus this exclusion (checks 1–2), and the exclusion lets the companion merge without carrying a changelog duty of its own.
- **Same class as 81/84**: the adjacent entries 84 and 81 use the same docs-sync-companion wording pattern ("registry bookkeeping change whose only content is this exclusion plus …; it carries its own exclusion so merging it leaves main green").
- `test_registry_covers_every_merged_campaign_pr_in_window` passes with 85 excluded: `1 passed` run by name, and included in the full-suite result below.

## Check 6 — suite at the head: PASS

```
venv/bin/pytest tests/test_docs_parity.py -q
→ 40 passed, 1 skipped in 0.06s
```

(pytest 9.2.0 on Python 3.12.3.) Exactly the expected counts; 41 tests collected.

## Check 7 — RED-first mutation counterfactual, BOTH ways: PASS

Scratch copy of the head tree (`/tmp/opencode/mut`). **Mutation = the exact inverse of the PR delta**: R03 `status → "planned"`, `attempt_id` and `updated_at` removed, embedded `transitions` emptied, top-level RAILS-R03 mirror removed (top-level transitions 5 → 4).

- **RED**: `load_backlog` still ACCEPTS (24 slices — the reverted file remains valid), but R03 is `planned` with no attempt and no transition; the probe in **both** worlds returns `('waiting', {'dep': 'RAILS-R03', 'state': 'planned'})` — the adoption and its stale-gate signal are both absent.
- **Restore** (head file copied back): ACCEPTED, 24 slices; R03 `dispatched` / `att_4be4db6493c14270`; embedded transitions 1; top-level 5; probe back to `('stale', … 'reason': 'dependency_failed')` / `('cleared', …)` — identical to check 4. Green restored.

## Check 8 — CI at the head: PASS (recorded; nothing pending-blocking)

`gh pr checks 85` refused (unauthenticated CLI). Anonymous REST `commits/fe424e57251…/check-runs`: **14/14 completed, conclusion success** — bee-ci/reference, bee-ci/project-state, bee-ci/secret-scan, recovery protocol (required), feature packet protocol (required), reference demo + tests, project-state schemas + reference checker (windows-latest and ubuntu-24.04), return manifest protocol (required), observability record tests, bee-landed protocol (required), cold-start acceptance (light, offline worker), campaign report protocol, gitleaks. No pending or failing check observed at the reviewed head.

## Check 9 — report self-scan with the house predicate: PASS (0 findings; negative control trips)

Predicate set applied over this committed report (house classes): (1) name-colon-value credential shapes — credential-family keywords (api-key/secret/token/password/authorization/credential and near variants) followed by a colon or equals and a value; (2) the bearer rule — the scheme word, whitespace, then six or more token-alphabet characters; (3) credential-literal families — the OpenAI-style key, GitHub CLI and fine-grained personal-access-token, Slack token, AWS access-key-id, Google API key, and JWT-header prefixes (raw prefixes intentionally **not reproduced** in this report so the self-scan of the file itself stays clean).

- **Result on the report (the marked negative-control block excluded): 0 matches.**
- **Negative control** (in the block below, excluded from the file scan and scanned alone to prove the scanner runs):

<!-- BEGIN NEGATIVE CONTROL — fake value, not a real credential; intentionally trips the scan -->
NEGATIVE-CONTROL: Authorization: Bearer NOTAREALSECRET000000
<!-- END NEGATIVE CONTROL -->

- **Control result: 2 matches** (rule 1 — credential-name colon value; rule 2 — bearer + 6+ characters). The scan demonstrably runs.
- Method note: the scan was executed as a Python heredoc applying rules 1–3 line-wise over the file with the two `NEGATIVE CONTROL` marker lines and the line between them stripped; the control line was then scanned alone. Attempt ids (`att_…`), head SHAs, PR numbers and file paths are not credential shapes under the predicate. The underlying PR files are additionally covered by the house CI itself: `bee-ci/secret-scan` and `gitleaks` are green at the head (check 8).

## Blocking findings

None. DEFECT count = 0. Disclosure-class observations are recorded under "Environment deviations" (machine-local path substitutions, unreachable hyvv store) and check 4 confirms the PR's own disclosure matches observed behavior. No disclosure mismatch found.

## JSON summary

```json
{"verdict": "APPROVED", "blocking_count": 0, "checks_passed": 9, "checks_total": 9}
```
