VERDICT: changes_requested
BLOCKING: 2

# Independent review of PR #88 — Hindsight trial harness PART 2 (arms + report)

Reviewed head: `93060b6381c2d7c0c41724592e6963b524fbd357`, verified equal to
`gh pr view 88 -R mojomast/workflow --json headRefOid` **before any PR content was
read** (grounding timestamp 2026-11-17T13:32Z; see Disclosures D1/D2 for the gh→REST
substitution and what was listed pre-verification). Base: main
`7976a947ea563b6a4f76f247fcd07f99a5276508`; three-dot merge-base
`f7c9ca7134fcd24dfdcdb6807d1648115c6cd3bc` (= the PR head's parent). The local
snapshot tree `74c8c8f90010b701cbaee5a7c10cca8ddc0522a0` is SHA-1-equal to the
GitHub tree of `93060b6`, so every local observation below is byte-grounded to the
reviewed head. Head did not move during the review (re-checked at report-finalize
time, see Disclosure D6).

## Findings

### B1 (blocking) — H1/H2/H3 pairing a-vs-c contradicts the pre-registered baseline (B), and under the pre-registered pairing the stub H1 is FAIL, not PASS

Spec, `docs/hindsight-synthesis.md` (all on main):

- :413 "This document recommends a trial between B (baseline) and C (treatment), with
  A as the secondary control"
- :441-443 "Baseline (fixed by the brief): Option B — the contract-only vault service,
  complete per docs/memory-contract.md, running the same fixtures."
- :445-446 "Secondary control: Option A — no memory layer, same fixtures, to test
  whether any memory layer earns its keep at all."
- :447-450 (H1): "the treatment arm's coordinator state-reconstruction cost … is
  ≥50% lower than **the baseline arm's**, with zero reconstruction events sourced
  from raw chat scrollback."
- :277 "### Option B — contract-only (the trial's baseline)"; AC-304 :603 runs
  "baseline arm, then treatment arm, then secondary control".
- :430-431 "Any later change to these thresholds is a new declaration, never a
  retroactive one."

Code, `scripts/trial/report.py:49-52`: `H123_BASELINE = arms.ARM_A`,
`H123_TREATMENT = arms.ARM_C`, `H4_BASELINE = arms.ARM_B`,
`H4_TREATMENT = arms.ARM_C`. The report layer justifies this with "§3.3 does not
pair A/B/C by name" (`report.py:16`), but §3.1 does: the baseline is fixed as B.

Consequence (demonstrated at the reviewed head, scratch clone): with the
pre-registered pairing, `evaluator.evaluate_trial(arm-b, arm-c)["verdicts"]["H1"]
== "FAIL"` — arm-c cost 292 (290 tokens + 2 turns) vs arm-b 548 (545 + 3) is a
46.7% reduction, below the 0.5 threshold. The shipped a-vs-c pairing turns that
into H1 PASS (912 → 292, 67.7%). The stub numbers do not satisfy the
pre-registered H1; re-pairing the comparison instead of adjusting the stub cost
model (or declaring a new threshold set) is exactly the retroactive change §3
forbids. A human reading the rendered report sees `H1: PASS` under a pairing the
pre-registered brief does not authorize. H4 = b-vs-c **does** match the spec
(:460-462 "≤2× the baseline arm's" with baseline = B, the only other memory arm).

### B2 (blocking) — an arm-b conformance violation is invisible to the report (all PASS, exit 0)

`report.py:98-105` takes H3 from pair1 (a-vs-c) and keeps only pair2's H4 —
pair2's H3 (which gates b and c) is computed and discarded. §3.3 M5–M7 rows
(:523): "100% … any violation fails the arm outright"; §3.4 :540 "Adopt nothing
(A) if either arm fails a gate (M5–M7)". Arm-b is a trial arm (the pre-registered
baseline), so its gate must gate the report.

Demonstrated at the reviewed head: set arm-b `M5.violations = 1`, rebuild →
`verdicts {'H1': 'PASS', 'H2': 'PASS', 'H3': 'PASS', 'H4': 'PASS'}`,
`exit_code: 0`. No test covers an arm-b violation, so the suite's mutation
coverage misses this class entirely (see check 9).

### N1 (followup) — `render()` crashes on the missing-metric input that `build_report()` classifies as UNINFORMATIVE

With arm-c's M1 deleted, `build_report()` returns exit 2 correctly, but
`render()` raises `KeyError: 'M1'` (`report.py:163`) when printing the arm table.
Consequence: `python -m scripts.trial.report` (which always replays the complete
stub arms) can only ever exit 0; the exit-1/2 paths are reachable only through
the dict API, and a future real-data run with an incomplete record would crash
the renderer instead of printing UNINFORMATIVE. Exit contract itself verified
(see check 5).

### N2 (followup) — §3.4 absolute checks are inferred from M8 spend, not scored from captured metrics, and arm-a is scored as failing M3/M4

`report.py:62-84` scores M3/M4 as `has_memory = M8 tokens > 0`. The stub arms
emit no M3/M4 metrics, so nothing captured is scored against the fixture
`expected` blocks (e.g. `RESTART_FIXTURE.expected.recovery_brief_reject`, the
wrong-digest case, is never exercised); M3's expected crash digest
(`recovery_brief_item.source_digest`) is never surfaced — only M4's
(`M4_expected_digest`). Also, §3.3 scopes M3/M4 to the baseline (B) and treatment
(C) arms; the report marks arm-a (secondary control, no memory layer by design)
as failing M3/M4, which is informational-only today but misleading in a
human-readable report.

### N3 (observation) — legacy commit-status endpoint vs checks API

At the reviewed head the combined commit-status endpoint reports state `pending`
with 0 statuses while the checks API reports 14/14 `success`. The checks API is
the authoritative surface for Actions checks; noted so nobody misreads the
legacy endpoint.

### N4 (observation) — spec-pointer clarification

`docs/hindsight-mechanism-report.md` §3.3 (:246, "Observation grouping and update
rules") and §3.4 (:263, "Contradiction handling and duplicate reconciliation") are
the Hindsight engine's consolidation sections; the trial's pre-registered
thresholds and decision rule live in `docs/hindsight-synthesis.md` §3.3 (:515-533)
and §3.4 (:535-546). The code cites the synthesis doc (`evaluator.py:52`
THRESHOLDS_SOURCE, module docstrings) — the citation is correct; the
mechanism-report sections matter here as the claimed engine-side difference
behind H2 (synthesis :453, mechanism-report §9 item 2) and as the supersession
twin (synthesis :225).

## Check evidence

1. **Delta exactness — PASS.** GitHub three-dot compare (`main...93060b6`, merge-base
   `f7c9ca7`): exactly `scripts/trial/arms.py` (added, +127/-0), `scripts/trial/report.py`
   (added, +191/-0), `tests/test_trial_harness.py` (modified, +93/-0). Independently
   re-derived locally from tarballs of `f7c9ca7` and `93060b6`: reconstructed trees hash
   to `6a4591f7…` and `74c8c8f9…` (identical to GitHub's tree SHAs), and
   `git diff --numstat` shows `127 0`, `191 0`, `93 0` with zero `-` lines in the tests
   file (additions-only confirmed). No other files, no mode changes.
2. **PART-1 interface conformance — PASS.** In the scratch clone at the head: imported
   `arms` + `report` and ran one full arms→evaluator→report pass over the PART-1
   fixtures (`scripts/trial/fixtures.py`, `evaluator.py` on main). Output recorded in
   this review's evidence run: per-arm M1/M2/M5-M8 records; pair1
   `{'H1': 'PASS', 'H2': 'PASS', 'H3': 'PASS', 'H4': 'UNINFORMATIVE'}` (mirrored-M8
   discard working as documented); pair2 `{'H1': 'FAIL', 'H2': 'PASS', 'H3': 'PASS',
   'H4': 'PASS'}` (see B1); report `exit_code: 0`.
3. **Determinism audit — PASS.** Grep-audit of `arms.py` + `report.py` for
   time/random/seed/open/write/socket/requests/subprocess: all hits are prose
   ("every time a brief is built", "no randomness, no clock, no I/O", "no filesystem
   writes", "unknown" matching `now`), an in-memory dict read
   (`RESTART_RECORD_READS = len(fixtures…)`, no filesystem), and `sys.stdout` in
   `render()`. AST scan confirms: arms.py imports only `__future__` + `scripts.trial`;
   report.py imports `__future__`, `copy`, `scripts.trial`, `sys`; flagged calls are
   `print(...)` only (stdout rendering, not a filesystem write). Determinism tests pass
   (`-k "deterministic or no_network or emits_every_metric"` → 4 passed).
4. **Spec conformance — FAIL (2 blocking).** See B1 and B2. Threshold constants
   themselves match §3.3 exactly: `H1_MIN_REDUCTION_FRACTION = 0.5` ↔ :448 "≥50%
   reduction"; `H1_MAX_SCROLLBACK_SOURCED_EVENTS = 0` ↔ :449-450 and the M1 fail
   column :519; `H2_PROBE_BRIEFS_REQUIRED = 2`, `H2_MAX_INTRUSIONS_PER_BRIEF = 1` ↔
   :520 "pitfall present in ≥2 of 2 probe briefs; ≤1 intrusion per brief";
   `H3_MAX_CONFORMANCE_VIOLATIONS = 0` ↔ :523 "100% … any violation fails the arm
   outright"; `H4_MAX_COST_RATIO = 2.0` ↔ :526 "≤2× baseline per canary run".
5. **Exit contract — PASS.** Exit 0: CLI `python -m scripts.trial.report` → exit 0,
   all four hypotheses PASS (output recorded). Exit 1: arm-c M5 violation →
   H1/H2/H3/H4 all FAIL, exit 1 (output recorded). Exit 2 (missing-metric): arm-c M1
   deleted → H1 UNINFORMATIVE, exit 2 (output recorded). Exit 2
   (indistinguishable-arms): arm-c record == arm-a record → H1+H2 UNINFORMATIVE,
   exit 2 (output recorded). Caveat N1: render() cannot print the exit-2 shapes.
6. **RED re-derivation — PASS.** At the reviewed head (scratch clone), disclosed
   mutation "remove arm-c's cost saving" applied (arm-c M1 cost set equal to arm-a's):
   exactly 3 failed — `ArmReplayTests::test_hybrid_arm_reconstruction_cost_is_at_least_half_below_no_memory`,
   `ReportTests::test_default_report_passes_every_hypothesis_with_exit_zero`,
   `ReportTests::test_render_prints_thresholds_arms_and_verdicts` — 35 passed.
   sha256 before: `577b38678e62b57cd879914c60b0b094639d1c20f4ed2d1c8bef895cebd0f10f`;
   after restore: identical (byte-identical restore verified); rerun → 38 passed.
7. **Tests gate — PASS.** `pytest tests/test_trial_harness.py
   tests/test_hindsight_mechanisms.py -q` → `47 passed, 2 skipped, 3 subtests passed`.
   Separately: trial harness `38 passed, 3 subtests passed`; mechanisms `9 passed,
   2 skipped`. PART-1 battery green.
8. **CI at the exact reviewed head — PASS (confirmed unchanged).** Checks API at
   `93060b6381c2d7c0c41724592e6963b524fbd357`: 14 check runs, all `completed/success`
   (bee-ci/project-state, bee-ci/reference, bee-ci/secret-scan, bee-landed protocol,
   campaign report protocol, cold-start acceptance, feature packet protocol, gitleaks,
   observability record tests, project-state schemas + reference checker
   ubuntu-24.04 + windows-latest, recovery protocol, reference demo + tests, return
   manifest protocol). Matches the dispatch-time 14×SUCCESS claim.
9. **Disclosure assessment — see "Disclosure assessment" below.**
10. **Scanner hygiene — see "Scanner hygiene" below.**

## Disclosure assessment (check 9)

The PR body discloses that the coordinator wrote PART 2 directly after four worker
attempts ended in design without committing, and that "tests are behavioural and
mutation-checked rather than written before the code". The mutation evidence is real
and reproduces exactly (check 6), and the tests do pin behaviour the harness needs
(determinism, metric-shape completeness, conformance demotion, missing-metric
inconclusiveness, indistinguishable arms, exit codes, no-network). For the arms
layer that is adequate for the harness's stated purpose.

For the report layer it is not sufficient: the mutation set leaves the arm-b gate
bypass (B2) completely uncovered — a mutation that injects an arm-b violation
changes no test outcome — and nothing pins the pairing against the pre-registered
baseline (B1), because the tests encode the PR's own pairing choice. Both gaps sit
exactly where the harness's decision-making lives. Followups required: add an
arm-b-violation test, pin the pairing to §3.1 (or re-declare it), and guard
`render()` for incomplete records (N1). The disclosure itself is honest, but the
behavioural net has two holes in the gate logic.

## Disclosures

- D1: `gh` in this environment has no authentication ("gh auth login" required), so the
  grounding check used GitHub's unauthenticated public REST API
  (`api.github.com/repos/mojomast/workflow/pulls/88` → `head.sha`), which is the same
  datum `gh pr view --json headRefOid` returns; likewise `gh pr checks` was substituted
  by the commits/{sha}/check-runs API (check 8). Everything else was done locally.
- D2: Before the grounding call, the working directory's file listing and `git show
  --stat HEAD` were read (local snapshot metadata only; no PR diff/content was read
  before the head was verified).
- D3: The mandated scratch dir `/home/clanker01/.hermes/cache/scratch/review-wf88/`
  did not exist; it was created (sudo mkdir + chown) since the working user is `cua`.
  All clones, tarballs and synthetic runs live there; the working repo itself was only
  touched for the branch `review/pr88` and `docs/review-pr88.md`.
- D4: pytest 9.2.0 was installed into the user site (`pip --user
  --break-system-packages`) to run the mandated pytest commands; the repo ships no
  pytest config and the default unittest-based tests run under it unchanged.
- D5: The RED mutation was applied only in the scratch clone; the working tree's
  `scripts/trial/arms.py` was never modified.
- D6: Head re-check at finalize time (2026-11-17T13:36:16Z): headRefOid still
  `93060b6381c2d7c0c41724592e6963b524fbd357`; the head did not move during review.

## Unproven

- That a real (Level B) run's numbers would satisfy the pre-registered H1 under the
  c-vs-b pairing — untestable here; the stub numbers demonstrably do not (B1).
- That `render()` is the only crash path on incomplete records — audited the two added
  modules only; `evaluator.py`/`fixtures.py` are PART-1 code on main and were not
  audited beyond the interface use.
- That no other commit-status providers exist at the head — only the checks API and the
  legacy status endpoint were queried.
- CI recomputation from source: checks were read from the API at the exact sha; the
  workflows were not re-executed locally.

## Scanner hygiene

Every added line of this report was self-scanned two ways:

1. **gitleaks 8.24.3** (`gitleaks detect --no-git --source docs/review-pr88.md`,
   default rules): **0 findings**.
2. **Naive regex self-scan** (aws/github/private-key/generic-secret/bearer/slack/jwt
   plus a broad 32+-hex pattern): exactly one secret-shaped trip — the mandated
   negative-control line below, whose synthetic marker is labeled NOT a secret in the
   same line — plus 7 benign `hex32` hits, all public git object identifiers this
   review is required to record (head/base/merge-base/tree SHAs and the recorded
   sha256 of check 6): lines 6, 10, 11, 12, 150, 157, 205. No real secret-shaped
   content appears anywhere in the report.

negative-control: SYNTHETIC-SCANNER-MARKER api_key="NOT-A-SECRET-0000000000000000-deadbeef" (synthetic negative control, NOT a secret)

## Summary block

```json
{
  "verdict": "changes_requested",
  "changed_files": ["docs/review-pr88.md"],
  "checks": [
    {"name": "grounding (head == 93060b6, verified first)", "command": "GET api.github.com/repos/mojomast/workflow/pulls/88 (gh unauth; same datum as gh pr view --json headRefOid)", "passed": true},
    {"name": "delta exactness (three-dot vs main)", "command": "compare API + local tarball re-derivation: git diff --numstat <merge-base> <head>", "passed": true},
    {"name": "PART-1 conformance (arms->evaluator->report)", "command": "scratch-clone import + full pass over scripts/trial fixtures", "passed": true},
    {"name": "determinism audit", "command": "grep + AST scan of arms.py/report.py; pytest -k deterministic/no_network", "passed": true},
    {"name": "spec conformance (pairing/thresholds/absolute checks)", "command": "spec quotes vs code constants + empirical pairing/gate probes", "passed": false},
    {"name": "exit contract 0/1/2", "command": "python -m scripts.trial.report; synthetic metrics via build_report", "passed": true},
    {"name": "RED re-derivation (3 new-test failures, byte-identical restore, 38 passed)", "command": "mutation in scratch clone + sha256 before/after + pytest", "passed": true},
    {"name": "tests gate at head", "command": "pytest tests/test_trial_harness.py tests/test_hindsight_mechanisms.py -q", "passed": true},
    {"name": "CI at reviewed head (14 checks)", "command": "GET api.github.com/repos/mojomast/workflow/commits/93060b6.../check-runs (gh unauth)", "passed": true},
    {"name": "scanner hygiene", "command": "gitleaks 8.24.3 --no-git on the report (0 findings) + regex self-scan (1 mandated negative control + 7 benign public-SHA hex32 hits, justified)", "passed": true}
  ],
  "open_issues": [
    "B1: H1/H2/H3 pairing a-vs-c contradicts the pre-registered baseline (B, synthesis.md:441-443); under c-vs-b the stub H1 is FAIL (46.7% < 50%) — pairing must be fixed or newly declared",
    "B2: arm-b conformance violation leaves the report at all-PASS/exit 0 (report.py keeps pair1's H3; pair2's H3 discarded) — violates §3.3 M5-M7 'any violation fails the arm outright' / §3.4 'Adopt nothing if either arm fails a gate'",
    "N1: render() KeyError on missing-metric input; CLI can only exit 0 with stub arms",
    "N2: absolute checks scored from M8>0 heuristic; M3 expected digest never surfaced; arm-a misleadingly scored",
    "followup tests: arm-b-violation mutation test + pairing pin + render guard"
  ]
}
```
