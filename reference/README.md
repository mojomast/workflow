# Reference workflow

A miniature, offline run of the protocol described in this repository. By default it runs the contract-first, test-first loop of [chapter 16](../docs/16-acdd-tdd.md): ACDD contracts validated and frozen by hash, approved tests committed on their own, RED on the baseline, GREEN and REFACTOR by scripted workers inside an immutable file lease, independent verification in a throwaway checkout, a combined integration suite, `tdd-evidence/1` records and an acceptance report. `--legacy` runs the original lease-and-verify demo (two workers, an out-of-scope rejection, handoff and return packets, and a metrics log).

> **Teaching only — not a security harness.** The demo's evidence records are unsigned JSON and its tests run as plain subprocesses, not in a sandbox; bundlebees signs and sandboxes the real ones. The demo's lease fingerprints (`lease_sha256`) are plain, unkeyed SHA-256 hashes stored in the same file as the leases. They catch accidental edits, but anyone who can edit the store can change a lease and recompute the hash (a test, `test_teaching_fingerprint_is_not_tamper_proof`, shows exactly that). Do not copy this lease code into a real system. For real use, [bundlebees](https://github.com/mojomast/bundlebees) writes coordinator leases that are HMAC-SHA256 signed with a separate `0600` key and created read-only with `O_EXCL`; see [13 §3](../docs/13-bundlebees-hardening.md#3-immutable-coordinator-lease).

This is not production [bundlebees](https://github.com/mojomast/bundlebees) and it does not talk to Orbit, a model, or the network. The "workers" are scripted patch generators. The [measurement fields](../docs/12-three-layer-architecture.md#4-measurement) are recorded here so the schema is visible; they are not a production baseline. The same fields are now logged by bundlebees on `main` (untagged); see [13](../docs/13-bundlebees-hardening.md).

## Requirements

- Python 3 (stdlib only)
- `git` on `PATH`

## Commands

From the repository root:

```bash
python3 reference/run_demo.py            # ACDD + TDD (default)
python3 reference/run_demo.py --legacy   # original lease-and-verify demo
python3 -m unittest discover -s reference/tests -v
```

Or from this directory:

```bash
make demo
make test
```

`python3 reference/run_demo.py --out /tmp/workflow-reference-demo` writes the toy repo, contracts, evidence, `ACCEPTANCE.md` and `summary.json` to that folder (with `--legacy`: contracts, packets, evidence and `metrics.jsonl`).

`--out` is guarded so a typo cannot erase unrelated files:

- The folder must be new or empty. The demo writes a `.workflow-reference-demo` marker file into every run folder it creates.
- A non-empty folder is refused (exit 2). `--force` replaces it **only** if it already holds that marker as a regular file; otherwise nothing is deleted. Symlinks inside a replaced run are unlinked, never followed.
- `/`, your home directory, the repository root, the current directory and any of their parents are always refused, even with `--force`, as is an `--out` that is a symlink or resolves through one onto those paths.

To rerun into the same folder: `python3 reference/run_demo.py --out /tmp/workflow-reference-demo --force`. Exit status is 0 only when the invalid contract is refused, both in-scope workers are accepted with valid RED and GREEN evidence, the out-of-scope and test-weakening workers are rejected, and the combined test suite passes (with `--legacy`: both in-scope workers accepted, the out-of-scope worker rejected, the combined suite passing).

## What the default (ACDD + TDD) demo does

1. Creates a tiny `toy-shop` git repo (`shop/pricing.py`, `shop/labels.py`) with a green unittest suite.
2. Validates five contracts against [`schemas/acdd-contract.schema.json`](../schemas/acdd-contract.schema.json) and the extra checks in [16 §2](../docs/16-acdd-tdd.md#2-the-contract-acdd1). `W0-invalid` is refused with `contract_invalid` before any work starts. The others are frozen by `contract_sha256`.
3. For each contract, commits the approved tests on their own (`acdd/tests-<id>`) and runs them on the baseline. That is RED: every RED-set test must fail because the declared interface is missing (classified `behavioral_failure`), and the test files are fingerprinted.
4. Scripted workers patch only their assigned files. The verifier re-checks the lease and the test fingerprints in a fresh checkout and reruns the approved tests: GREEN. `W1-pricing` also does a REFACTOR that must stay green under the same checks.
5. `W3-out-of-scope` touches a file outside its lease and is rejected with `scope_violation`. `W4-weakened-tests` edits an approved test to make it pass and is rejected with `tests_tampered`. Neither gets GREEN; their GREEN and integration rows say **not run**, never passed.
6. Integration applies every accepted change on the baseline plus all approved tests and runs the full suite.
7. Writes `evidence/<id>/{red,green,refactor,integration}.json` (`tdd-evidence/1`, see [`schemas/tdd-evidence.schema.json`](../schemas/tdd-evidence.schema.json)), `ACCEPTANCE.md` (each AC id with its status and evidence file) and `summary.json`.

## Expected output

SHAs and the run directory change every run. The decisions should not:

```
Reference workflow demo (contract-first, test-first)
  source_rev:     ed0f5417479e1802458c7e71459accc7d858d40c
  accepted:       W1-pricing, W2-labels
  rejected at contract review:
    - W0-invalid: contract_invalid
  rejected at verification:
    - W3-out-of-scope: scope_violation
    - W4-weakened-tests: tests_tampered
  evidence:
    - W1-pricing: red valid, green valid, refactor valid, integration valid; test-first yes; accepted yes
    - W2-labels: red valid, green valid, integration valid; test-first yes; accepted yes
    - W3-out-of-scope: red valid, green not run, integration not run; test-first yes; accepted no
    - W4-weakened-tests: red valid, green not run, integration not run; test-first yes; accepted no
  integration:    passed (combined test suite passed)
  acceptance:     /tmp/workflow-reference-demo/ACCEPTANCE.md
  artifacts:      /tmp/workflow-reference-demo
  result:         OK
```

`make test` (and `python3 -m unittest discover -s reference/tests -v`) runs 38 tests: the 15 legacy tests (including `test_out_of_scope_patch_is_rejected`, the `--out` guard tests and the teaching-fingerprint limit) plus 23 ACDD/TDD tests in `test_acdd.py`, `test_tdd.py` and `test_lifecycle.py`. Those 23 were committed before the implementation and failed first (all with `cannot import name`); all 38 should pass now.

## What the legacy demo does (`--legacy`)

1. Creates a tiny `toy-shop` git repo with two modules (`shop/pricing.py`, `shop/labels.py`) and a green unittest suite.
2. The orchestrator records a brief for each task with `source_rev`, `assigned_files` and `acceptance`, and writes a lease the API refuses to change. The (teaching-only, recomputable) lease hash is stored by the coordinator; worker claims cannot widen it.
3. Two scripted workers each patch a separate slice (`apply_tax` and `format_receipt_line`), starting from the same baseline.
4. A third worker also touches a file outside its lease and claims a wider file list. Verification ignores that claim and rejects the patch.
5. Each accepted or rejected result is verified in a fresh clone at the exact `source_rev`. Only the evidence comes back.
6. [HANDOFF.md](../templates/HANDOFF.md) and [RETURN.md](../templates/RETURN.md) packets are filled from the templates in this repository.
7. Accepted patches are applied on a combined branch and the full unittest suite is run.
8. A JSONL summary records the six measurement fields listed in chapter 12. Cost is a synthetic unit of 1 per scripted worker, not currency or model tokens.

### Legacy expected output

SHAs, the run directory and the elapsed time change every run. The decisions and counts should not. A successful `--legacy` run looks like this:

```
Reference workflow demo
  source_rev:     9f44bea9b01645d4c39534682568a12596ccfd2e
  accepted:       W1-pricing, W2-labels
  rejected:
    - W3-out-of-scope: patch touches files outside the coordinator lease
  integration:    passed (combined test suite passed)
  integration_rev:c328ebd8ceb1c6361968630dc726831006836cad
  metrics:
    cost_per_accepted_change:      1.0
    first_pass_verification_rate:  0.6666666666666666
    human_interventions:           0
    plan_to_accepted_seconds:      0.2173
    regression_escapes:            0
    failed_worker_recovery:        {"note": "the out-of-scope worker was rejected and not redispatched in this demo", "redispatched": 0, "rejected": 1}
  artifacts:      /tmp/workflow-reference-demo
  metrics log:    /tmp/workflow-reference-demo/metrics.jsonl
  result:         OK
```

## Layout

| Path | Role |
|---|---|
| `run_demo.py` | One-command entry point |
| `workflow/lifecycle.py` | ACDD + TDD lifecycle (default demo): contracts, RED, GREEN, REFACTOR, integration, acceptance report |
| `workflow/acdd.py` | `acdd/1` contract validation, canonical hash, freezing, RED set |
| `workflow/tdd.py` | Per-test runner, failure classification, `tdd-evidence/1` records, RED/GREEN/REFACTOR checks |
| `workflow/schema.py` | Small stdlib JSON Schema subset used to validate contracts and evidence |
| `workflow/toy.py` | The generated toy repository |
| `check_schemas.py` | CI cross-check of the schemas, the example contract and the demo evidence with the `jsonschema` package |
| `workflow/orchestrator.py` | Legacy demo: contracts, leases, dispatch, packets, integration |
| `workflow/contract.py` | Brief validation and lease store (teaching-only SHA-256 fingerprints) |
| `workflow/workers.py` | Scripted patch generators, including the out-of-scope case |
| `workflow/verify.py` | Throwaway checkout, baseline and lease checks, slice tests |
| `workflow/integrate.py` | Combined branch and full suite |
| `workflow/packets.py` | Fills the repository HANDOFF and RETURN templates |
| `workflow/metrics.py` | JSONL log of the chapter 12 fields |
| `tests/test_reference.py` | Legacy demo, including the out-of-scope rejection test |
| `tests/test_acdd.py`, `tests/test_tdd.py`, `tests/test_lifecycle.py` | Approved ACDD/TDD tests (written first) |
