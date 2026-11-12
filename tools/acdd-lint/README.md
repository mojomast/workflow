# acdd-lint

A zero-dependency checker for ACDD contracts (`acdd/1`) and TDD evidence (`tdd-evidence/1`). It checks them against the [shared schemas](../../schemas/) and the protocol rules in [docs/16](../../docs/16-acdd-tdd.md). It needs only Python 3.12+ and runs from a copy in any repository.

```sh
cd tools/acdd-lint
python3 -m acdd_lint ../../evidence                       # text report
python3 -m acdd_lint ../../evidence --json                # machine-readable
python3 -m acdd_lint STATE_DIR --key-file verifier.key    # also check HMAC signatures
python3 -m unittest discover -s tests -t .                # its own tests (35)
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
| `evidence_tampered` | The signature does not match (checked only with `--key-file`). |

**Ordering:** records are ordered by `at`, then by phase (red, green, refactor, integration, review), then by file name. So records written in the same second still read in protocol order.

**Discovery skips:** `.git`, `node_modules`, `__pycache__`, `.venv` and `venv`, symlinks, and files over 1 MiB. Without `--key-file`, the report says `signatures: not checked`, and the JSON output lists `signatures` under `unrun`. Key material is never printed.

**Key files:** the key is 32 raw bytes or 64 hex characters. For bundlebees evidence this is the *evidence* key, derived from the lease key with `leases.evidence_key(state_dir)`. It is not `lease.key` itself. With the wrong key, every record is reported as `evidence_tampered`.

## How it was built

acdd-lint was the first project built end to end with the workflow it checks, as an ACDD contract per slice. Approved tests were committed first, a verifier recorded RED, DeepSeek bees wrote GREEN, and then came REFACTOR, a coordinator review and integration. See [the dogfood evidence and lessons](../../evidence/2026-11-12-acdd-lint-dogfood/README.md).
