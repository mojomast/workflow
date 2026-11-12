# Dogfood run: acdd-lint built with ACDD + TDD (Nov 12, 2026)

This is the first full run of the workflow on a small new project: [`tools/acdd-lint`](../../tools/acdd-lint/README.md), a zero-dependency checker for ACDD contracts and TDD evidence. Each slice ran the full protocol:

contract with AC ids → approved tests committed alone (RED) → verifier records RED → bee writes GREEN → independent verify → REFACTOR → review → integrate → metrics.

The work was built in `mojomast/bundlebees` on the branch `dogfood/acdd-lint`, because this repository is not on the bee launcher's allow-list. It was then ported here unchanged with `git am`, which keeps the RED-before-GREEN commit order. Times below are UTC; ET is UTC-5.

| Slice | Contract (sha256, first 12) | Approved tests | RED commit (bundlebees / here) | RED | Bee attempt | GREEN commit (bundlebees / here) | GREEN | REFACTOR | Review | Integration |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 schema validator | `L1-schema` v2 `919323d1cccd` | 7 | `bfd9f30` / `887825a` | valid (7/7 fail: missing module) | `att_b6eb71c8ab4754b7`, 1 try, 67 s | `c24bed6` / `aeab8f9` | 7/7, verified by `verify.sh` (unsigned) | not recorded | coordinator, in LESSONS | coordinator suite run |
| L2 protocol checks | `L2-checks` v2 `51e747dfde59` | 14 | `bfd9f30` / `887825a` | valid (14/14 fail) | `att_0ca334a51c5eef3b`, 1 try, 68 s | `37e454d` / `88dd3c2` | 14/14, verified by `verify.sh` (unsigned); the bee's empty out-of-lease `__init__.py` was dropped | not recorded | coordinator, in LESSONS | coordinator suite run |
| L3 CLI | `L3-cli` `3dfa46007c58` | 10 | `37e454d` / `88dd3c2` | valid (10/10 fail) | `att_8b2b9d705b4e8bb6`, 1 try, 118 s | `886be5f` / `b88729e` | **signed GREEN** from `hermes bundlebees verify` (bwrap sandbox) | signed, `297785c` / `3151bc8` | signed, coordinator (not Kyle) | signed **integration_failed** (see LESSONS §4); coordinator full run 469/0 |
| L4 ordering fix | `L4-ordering` `51b11c09a159` | 4 (1 regression guard) | `e06fd8d` / `a17f993` | valid (3/4 fail) | `att_60ea6c73daae0bb1`, 1 try, 25 s | `6a9da01` / `55f0ac7` | **signed GREEN** from `bundlebees verify` | signed `--none` | signed, coordinator (not Kyle) | signed **integration_failed** (same cause) |

**L4 came out of the dogfood run itself.** When acdd-lint was run on the [reference demo](../../reference/README.md) output, it reported a false `red_missing`. The demo writes `red.json` and `green.json` in the same second, and acdd-lint broke ties by file name, which puts `green` before `red`. The fix followed the full protocol: a new contract, RED tests, a bee, then verify.

## Results

- **Tests:** 35/35 acdd-lint tests pass with `python3 -m unittest`. bundlebees' own suite on the final branch is 469 passed, 0 failed (coordinator run outside the sandbox).
- **Bees:** 4 attempts, 4 first-try passes, 0 redispatches, all `deepseek-v4.1-flash`. L1 and L2 ran in parallel. Bee claims were not used as evidence: every GREEN was re-run independently.
- **Lint of this folder** ([LINT.txt](LINT.txt), with the evidence key): 4 contracts, 13 signed records, 1 problem. The problem is real: `L1-schema/0001-red.json` is the RED made against the superseded v1 contract (`evidence_stale`). It is kept on purpose as history; see LESSONS §1.
- **Lint of the reference demo** (with its verifier key): 4 contracts, 10 records, 0 problems after L4. It reported 2 false `red_missing` problems before L4.
- **Acceptance:** `hermes bundlebees tdd report` shows `accepted: no` for L3 and L4, because the bundlebees integration step failed inside its own sandbox. That outcome is reported as it happened, not overridden.
- **Metrics:** see [metrics.json](metrics.json). It holds the bundlebees `metrics --json` output for the run and the per-bee numbers the launcher reported, with notes on which numbers are misleading.

## Files

- **`contracts/`**: the frozen contracts used for verification. **`contracts/superseded/`**: the v1 L1 and L2 contracts the bees actually received (renamed so the linter does not treat them as live contracts).
- **`evidence/<contract>/NNNN-<phase>.json`**: HMAC-signed `tdd-evidence/1` records written by bundlebees (`tdd red`, `verify`, `tdd refactor`, `integrate`, `tdd review`). The key is not published.
- **`LINT.txt`**, **`metrics.json`**, and **[LESSONS.md](LESSONS.md)**: the honest friction write-up.
