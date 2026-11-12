# Dogfood rerun: two acdd-lint slices through the full ACDD loop (Nov 12, 2026)

> **Outcome, stated plainly.** Both slices were **accepted** under the protocol's own rules this time, in the sandbox, with real bees. That means test-first RED recorded by the verifier, signed GREEN from `bundlebees verify` in bwrap, `tdd refactor --none`, and a sandboxed `bundlebees integrate` that passed the full acdd-lint suite (53 tests, 0 failures). `tdd report` says `accepted: true` for both. Orbit's ACDD verifier (orbitdesktop #26, `60f0ca0`) verified both signed reports and all 8 records, and rejected a tampered copy. A scripted out-of-scope patch was refused (`scope_violation`) before anything was applied. The previous run ([../2026-11-12-acdd-lint-dogfood](../2026-11-12-acdd-lint-dogfood/README.md)) had `waves_accepted: 0`. This rerun has `waves_accepted: 1`. Caveats are listed below, and none of them is hidden.

## What ran

| Slice | Contract (sha256, first 12) | Approved tests | RED | Bee attempt (deepseek-flash, 1 try) | GREEN commit | GREEN | REFACTOR | Integration | Report |
|---|---|---|---|---|---|---|---|---|---|
| D1 test refs | `D1-test-refs` `8e6112c9a59b` | `tests/test_test_refs.py` (AC-003 is a regression guard) | valid, `behavioral_failure`, bwrap | `att_bcb8fb1b3442408b`, 38 s, 15 tool calls | `d7c5675` | **signed**, bwrap | signed `--none` | signed **valid** | `accepted: true`, signed |
| D2 integration gate | `D2-integration-gate` `9f60a91a1136` | `tests/test_integration_gate.py` (AC-003 is a regression guard) | valid, `behavioral_failure`, bwrap | `att_d8defecd976b9e5a`, 35 s, 18 tool calls | `daed0be` | **signed**, bwrap | signed `--none` | signed **valid** | `accepted: true`, signed |
| Scope probe (scripted, not a bee) | uses the D1 lease | n/a | n/a | `att_scope00000000000` | none | **rejected**: `scope_violation` (touched `acdd_lint/cli.py`), nothing applied | n/a | n/a | n/a |

- **Base:** `4a7cdad` on `dogfood/acdd-lint-rerun-20261112`. It is a direct child of the `tools/acdd-lint` head `9aa6df7` (PR #6) and adds only the two approved test files, so RED could be recorded at `source_rev`. The launcher (0.1.15) fetched that branch and `source_rev`; both bees report `local_base_rev = 4a7cdad`.
- **Integrated wave `dogfood-rerun`:** `daed0be`. The suite ran via bwrap: 53 tests, 0 failures. The regression category was 53 passed and the contract category 9 passed. Security tests were `not_run` (none configured for this repo).
- **Verifier:** bundlebees `hardening/metrics-accounting` at `988b858` (PR #11 lineage), run by the coordinator with the bees' patches read from the launcher's stored results. The patches are in `patches/` and are byte-identical to `git diff` of the GREEN commits.
- **Independent re-run:** the coordinator ran `python3 -m pytest tools/acdd-lint/tests` on `daed0be` outside the sandbox: 53 passed.

## Caveats (unrun or imperfect)

- **`source_rev` deviation:** the brief asked for `source_rev = 9aa6df7`, `branch = tools/acdd-lint`. Test-first RED needs the approved tests to exist at `source_rev`, and #6's branch belongs to another executor, so a child commit on a new branch was used instead.
- **Leases were recorded by the coordinator shortly after dispatch, before any result was read.** Dispatch went through the Orbit API, not `bundlebees_dispatch`. This is why `metrics.bundlebees.json` shows `attempts_dispatched: 0`.
- **Metrics include the scope probe:** `attempts_verified: 3` and `first_pass` 2/3 both count it. Excluding it, real bees went 2/2 first-pass. The launcher-reported tokens were about 62.4k and 62.6k total per bee (mostly cached reads), and bundlebees saw no usage (`usage.source: unavailable`). Cost is unknown.
- **Bee self-reports:** each bee said its "full suite" check failed. That is expected, because each bee's isolated worker still had the other slice's RED tests. The claims were not used as evidence.
- **Artifact transport:** the patches were not fetched through Orbit's worker artifact API, because orbitdesktop #28 is not deployed.
- **Report paths:** the signed reports carry absolute scratch paths in `criteria.*.evidence`. These are coordinator scratch paths, not hosts or secrets. They are left as signed, since editing them would break the signature, and are recorded as a follow-up for bundlebees.
- **Not done:** no review phase (`tdd review`) was recorded, and nothing was merged into `tools/acdd-lint` or main.

## Files

- `contracts/`: the frozen contracts.
- `evidence/<contract>/NNNN-<phase>.json`: HMAC-signed `tdd-evidence/1` records. The key is not published.
- `reports/<contract>.json`: signed `acceptance_report/1`.
- `reports/*.orbit26-verify.json`: output of Orbit #26's verifier.
- `steps.jsonl`: every coordinator command, with its exit code and output.
- `patches/`: the bee diffs.
- `metrics.bundlebees.json`: the bundlebees metrics output.
- `LINT.txt`: acdd-lint at `daed0be` on this folder with the evidence key: 2 contracts, 8 records, 0 problems.
- `LINT.tamper-probe.txt`: the same run on a copy with one integration record edited. It reports `evidence_tampered` and exits 1.
