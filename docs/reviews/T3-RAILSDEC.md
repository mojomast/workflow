VERDICT: APPROVE

## Scope and method

The checkout is the single squashed commit `1f340ad` ("base 75992615bc76f27c547c09b3f91b9a884ead7d4e"). The stated base object `ae9c080262ab593e7643e2fba79cd51a018f25df` is not present in this repository, so `git diff ae9c080262ab593e7643e2fba79cd51a018f25df..HEAD` cannot be computed (`fatal: bad revision`). I reviewed the PR content as it exists in the tree and checked every claim against the files it cites:

- `evidence/rails-rc/release/DECISION-2026-11-24-index-default.md` (new addendum)
- `evidence/rails-rc/README.md:5` (one-line evidence-index pointer)
- `CHANGELOG.md:5` (Unreleased bullet)

`DECISION.md` is not edited: it still carries the old "opt-in" wording (`evidence/rails-rc/release/DECISION.md:27`), and its sha256 (`baf8a1112a18b6508cb425928443cce44dc74d9a9a7c10a6502bd91cf5ffdcef`) matches the dated capture in `evidence/rails-rc/release/published.sha256`. The change is documentation-only; it touches no test, gate, sandbox, check or fail-closed path.

## Findings

1. Minor - `evidence/rails-rc/release/DECISION-2026-11-24-index-default.md:26` - "No committed record in this repository names the live Hermes-host ledger ..." is literally self-refuting: this addendum is itself such a record, and the tree already refers to "the Hermes host" / `hermes-host` (`observability/README.md:284`, `observability/examples/resource-snapshot.json:84-85`). The intended meaning (no record identifies the *live* ledger or its migration state) is correct and the SPEC-mandated fact is present. Fix: "No other committed record identifies the live ledger or says whether the #84 directory migration was applied to it." Non-blocking.

2. Minor - `evidence/rails-rc/release/DECISION-2026-11-24-index-default.md:7` - "creates ... at ledger creation" is supported only indirectly by `ROADMAP.md:58-63` ("made the index the default for new ledgers"); the BundleBees #84 source is not in this repository. Optional fix: say "the index is the default for new ledgers" or cite bundlebees #84 directly. The SPEC mandates the fact and ROADMAP corroborates both the default and the migration, so this is not a correctness defect.

No blocker or major finding.

## Fact check (verified in the tree)

- p95 values and rounding: `release/http-indexed.json` `events_p95_ms` 499.716 -> 499.7; `performance/indexed-100.json` 470.575 -> 470.6; `performance/indexed.json` 631.511 -> 631.5; `performance/coordinator-replay-100.json` 670.749 -> 670.7. Two exceed the 500 ms target; 499.716 leaves 0.284 ms. All four table links resolve.
- Index: `performance/index-cost.json` `sql` contains `CREATE INDEX rails_local_attempt_scan ON event_rows (...)`; `release/http-indexed.json:30` and `performance/indexed.json:30` show `USING INDEX rails_local_attempt_scan`.
- Soak: `release/soak.json` has `config.attempt_index: true`, `soak_seconds: 1800`, `elapsed_s: 1800.0`; Node RSS medians rise 110664 -> 130228 KiB and Chromium PSS medians rise 144207 -> 246743 KiB across the six windows. `DECISION.md` keeps memory unqualified.
- Multi-host: `DECISION.md:27` (multi-host outstanding) and `ROADMAP.md:63` ("multi-host runs are untested") record no multi-machine run.
- Evidence index: the only index file under `evidence/rails-rc/` that lists `DECISION.md` is `evidence/rails-rc/README.md` (`published.sha256` is a checksum manifest, not an index), so the pointer is in the correct single file and is exactly one line.
- CHANGELOG bullet matches the addendum: same four 500 ms figures and borderline/not-qualified conclusion, memory unqualified, multi-host untested, live-ledger migration unconfirmed, and the P1/P2/P3 order.
- Hygiene: the new document has no absolute private paths, no IPv4 literals and no URLs; all links are relative and resolve. "Hermes-host" is the SPEC-mandated ledger description, not a DNS name or IP.

## Test commands and exit codes

| Command | Exit | Result |
|---|---:|---|
| `timeout 900 python3 -m pytest -q -p no:cacheprovider tests/test_docs_parity.py` | 1 | Not executed: `/usr/bin/python3: No module named pytest`. pytest is not installed and, with no network, cannot be installed. |
| `timeout 900 python3 -m pytest -q -p no:cacheprovider tests` | 1 | Full suite not executed for the same missing-module reason. The PR has no code/test files, so no test behaviour changes. |
| `timeout 300 python3 /tmp/opencode/run_docparity.py` | 0 | Executed the `tests/test_docs_parity.py` test bodies against this tree with a minimal local `pytest` stub (the real module is absent): 54 invocations, 0 failures. |
| `timeout 120 python3 /tmp/opencode/verify_claims.py` | 0 | 33 assertions covering every cited p95, the soak config and memory medians, the index SQL/planner, the `DECISION.md` hash, all relative links, the README pointer and the CHANGELOG values. |

Caveat: because the base commit is absent and pytest is unavailable, the required `git diff`-based and full-suite comparisons could not be reproduced in this checkout. Within that limitation, the PR content is accurate, in scope, and keeps the HOLD unchanged.
