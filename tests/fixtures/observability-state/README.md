# observability-state fixtures

Synthetic plugin local state for `tests/test_obs_snapshot.py`. Every value is
fabricated for tests only; nothing here is measured from a live host and no
field carries credential-shaped material (identifiers, revision hashes, check
names, and model labels are all invented).

| Path | Stands in for |
| --- | --- |
| `state/jobs/job_20261113_a.json` | coordinator job document: one accepted task, one failed task, one escalation |
| `state/jobs/job_20261113_b.json` | job document with a rejected task and an awaiting approval gate |
| `state/queue.json` | feature queue pointer layer |
| `state/verify-results/att_1.json` | verify record with a passing suite (never becomes a failure row) |
| `state/verify-results/att_2.json` | verify record with a failing suite (becomes a `regression` failure row) |
| `state/metrics/run-1.jsonl` | hash-chained style metrics JSONL; newest `ts` drives scheduler liveness |
| `usage/usage.jsonl` | `bee.usage/v1`-shaped ledger, including unknown-token and unknown-cost records and one deliberately malformed line |
