# Reference workflow

A miniature, offline run of the protocol described in this repository: a contract and an immutable file lease, two isolated workers, a deliberately out-of-scope patch, independent verification in a throwaway checkout, handoff and return packets filled from the repo templates, a combined integration suite, and a metrics log.

This is not production [bundlebees](https://github.com/mojomast/bundlebees) and it does not talk to Orbit, a model, or the network. The "workers" are scripted patch generators. The [measurement fields](../docs/12-three-layer-architecture.md#4-measurement) are recorded here so the schema is visible; they are not a production baseline. The same fields are now logged by bundlebees on `main` (untagged); see [13](../docs/13-bundlebees-hardening.md).

## Requirements

- Python 3 (stdlib only)
- `git` on `PATH`

## Commands

From the repository root:

```bash
python3 reference/run_demo.py
python3 -m unittest discover -s reference/tests -v
```

Or from this directory:

```bash
make demo
make test
```

`python3 reference/run_demo.py --out /tmp/workflow-reference-demo` writes the toy repo, contracts, packets, evidence and `metrics.jsonl` to that folder (replaced if it already exists). Exit status is 0 only when both in-scope workers are accepted, the out-of-scope worker is rejected, and the combined test suite passes.

## What the demo does

1. Creates a tiny `toy-shop` git repo with two modules (`shop/pricing.py`, `shop/labels.py`) and a green unittest suite.
2. The orchestrator records a brief for each task with `source_rev`, `assigned_files` and `acceptance`, and writes an immutable lease. The lease hash is stored by the coordinator; workers cannot widen it.
3. Two scripted workers each patch a separate slice (`apply_tax` and `format_receipt_line`), starting from the same baseline.
4. A third worker also touches a file outside its lease and claims a wider file list. Verification ignores that claim and rejects the patch.
5. Each accepted or rejected result is verified in a fresh clone at the exact `source_rev`. Only the evidence comes back.
6. [HANDOFF.md](../templates/HANDOFF.md) and [RETURN.md](../templates/RETURN.md) packets are filled from the templates in this repository.
7. Accepted patches are applied on a combined branch and the full unittest suite is run.
8. A JSONL summary records the six measurement fields listed in chapter 12. Cost is a synthetic unit of 1 per scripted worker, not currency or model tokens.

## Expected output

SHAs, the run directory and the elapsed time change every run. The decisions and counts should not. A successful run looks like this:

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

`make test` (and `python3 -m unittest discover -s reference/tests -v`) runs six tests, including `test_out_of_scope_patch_is_rejected`. All six should pass.

## Layout

| Path | Role |
|---|---|
| `run_demo.py` | One-command entry point |
| `workflow/orchestrator.py` | Contracts, leases, dispatch, packets, integration |
| `workflow/contract.py` | Brief validation and immutable lease store |
| `workflow/workers.py` | Scripted patch generators, including the out-of-scope case |
| `workflow/verify.py` | Throwaway checkout, baseline and lease checks, slice tests |
| `workflow/integrate.py` | Combined branch and full suite |
| `workflow/packets.py` | Fills the repository HANDOFF and RETURN templates |
| `workflow/metrics.py` | JSONL log of the chapter 12 fields |
| `tests/test_reference.py` | Including the out-of-scope rejection test |
