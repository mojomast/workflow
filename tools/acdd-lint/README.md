# acdd-lint

A zero-dependency checker for ACDD contracts (`acdd/1`) and TDD evidence (`tdd-evidence/1`). It checks them against the [shared schemas](../../schemas/) and the protocol rules in [docs/16](../../docs/16-acdd-tdd.md). It needs only Python 3.12+ and runs from a copy in any repository.

```sh
cd tools/acdd-lint
python3 -m acdd_lint ../../evidence                       # text report
python3 -m acdd_lint ../../evidence --json                # machine-readable
python3 -m acdd_lint STATE_DIR --key-file verifier.key    # also check HMAC signatures
python3 -m unittest discover -s tests -t .                # its own tests (44)
```

**Exit codes:** `0` means clean. `1` means at least one problem. `2` is a usage error: a missing path, schemas not found, or a bad key file.

## What it checks

| Code | Meaning |
|---|---|
| `contract_invalid` / `evidence_invalid` | The file breaks the shared JSON schema. `where` is a JSONPath. |
| `json_invalid` | A `*.contract.json` file, or a file under an `evidence/` folder, is not valid JSON. |
| `ac_id_invalid` / `ac_id_duplicate` | A criterion id is not `AC-NNN`, or it is used twice. |
| `ac_untested` / `test_not_in_scope` | A `test` criterion names no tests, or names a test outside `scope.test_files`. |
| `contract_not_frozen` / `contract_changed` | The contract was never approved, or was edited after its `contract_sha256` was frozen. |
| `contract_duplicate` | Two contracts share an id. |
| `evidence_orphan` / `evidence_stale` | A record names no known contract, or was made against an older contract hash. Stale records never count as RED or GREEN. |
| `red_missing` / `red_invalid` | GREEN has no earlier valid RED from a verifier, or a RED was not `behavioral_failure`. |
| `green_failed` / `tests_tampered` | GREEN did not pass, or its test fingerprints differ from RED's. |
| `order_unproven` | GREEN shares its `at` with a valid RED and no signed sequence orders them; RED-before-GREEN is not proven. |
| `order_invalid` | The signed `sequence`/`prev_sha256` chain is not a gap-free `1..N` history with matching predecessor digests. |
| `evidence_tampered` | The signature does not match (checked only with `--key-file`). |

**Ordering:** when every record in a history carries an integer `sequence`, the history is ordered by sequence and checked as a signed chain: sequences must run `1..N`, the record with sequence 1 must have `prev_sha256: null`, and each later record's `prev_sha256` must equal the digest of the record before it (the digest is canonical JSON with the signature included and private `_` keys excluded). A broken chain is reported as `order_invalid`, and the history is still checked in sequence order. Otherwise records are ordered by `at` then file name only, never by phase: a GREEN that shares its second with a valid RED has no proven RED-before-GREEN and is reported as `order_unproven`, while a RED with a later `at` never counts.

**Discovery skips:** `.git`, `node_modules`, `__pycache__`, `.venv` and `venv`, symlinks, and files over 1 MiB. Without `--key-file`, the report says `signatures: not checked`, and the JSON output lists `signatures` under `unrun`. Key material is never printed.

**Key files:** the key is 32 raw bytes or 64 hex characters. For bundlebees evidence this is the *evidence* key, derived from the lease key with `leases.evidence_key(state_dir)`. It is not `lease.key` itself. With the wrong key, every record is reported as `evidence_tampered`.

## How it was built

acdd-lint was the first project taken through the workflow it checks, as an ACDD contract per slice. The tool works, but the run was not accepted under the protocol (0 accepted changes, 2 rejected waves). Approved tests were committed first, a verifier recorded RED, DeepSeek bees wrote GREEN, and then came REFACTOR, a coordinator review and integration. See [the dogfood evidence and lessons](../../evidence/2026-11-12-acdd-lint-dogfood/README.md).
