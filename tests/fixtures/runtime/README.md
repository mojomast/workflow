# Pre-conformance runtime records (`bundlebees` 191dc85)

One real recovery pair, captured from the M4 dogfood run and kept unmodified,
next to the canonical pair derived from the same evidence. Read with
[`docs/27-recovery-protocol.md`](../../../docs/27-recovery-protocol.md#runtime-conformance-and-migration)
and [`tests/test_runtime_conformance.py`](../../test_runtime_conformance.py).

## Provenance

| | |
|---|---|
| Producer | `bundlebees` at commit `191dc85` (the pin the M4.1 conformance work was measured against) |
| Run | M4 dogfood, `job_m4_dogfood`, feature `acdd-source-rev`, task `T2`, attempt `att_m4_2` |
| Date | 2026-11-14 (requests and decisions stamped `2026-11-14T01:49:12Z` / `2026-11-13T20:00:00Z`) |
| Decision adapter | `deterministic-agent` (the dogfood's scripted adapter) |
| Copied from | the run's state directory, `recovery/job_m4_dogfood/T2.1.request.json`, `T2.1.decision.json` and `T2.1.contract.json` |
| Copied | byte-for-byte, 2026-11-13, for the workflow M4.1 verification packet |

The copies were verified with `cmp` against the source files before the digests
below were taken.

## Files

| File | Role | sha256 |
|---|---|---|
| `captured-request.json` | what the runtime wrote as the request | `da6f6300812052314fa959a101de2b6e02b2a3c06e41d4ee31f7346dfbf2cd72` |
| `captured-decision.json` | what the runtime wrote as the decision | `bc95fe8c76fec2406a1379006e3060fd84c4603a97f940bb0f4182de450b216f` |
| `captured-corrected-contract.json` | the `acdd/1` revision the runtime froze for the supersession | `f528c32436e9fb181adb7a6d57714c7b82e3839e43261289f06fbb1a72c01692` |
| `canonical-request.json` | the same failure as a `rizzstack.recovery/1` request | derived |
| `canonical-decision.json` | the same reasoning as a `rizzstack.recovery/1` decision | derived |
| `canonical-corrected-contract.json` | the same corrected contract, re-frozen under the same contract id | derived |

The three `canonical-*.json` files are the migration output, not independent
hand-written documents: `tests/test_runtime_conformance.py` derives them from
the captures with `migrate_request`, `migrate_decision` and `migrate_contract`
and asserts the files are exactly that. Do not hand-edit them; change the
migration and regenerate.

## Why the captures are preserved unmodified

* They are the evidence. The pair demonstrates that a real runtime, on a real
  dogfood, wrote documents the protocol refuses. A canonicalised copy of the
  runtime's output would destroy the only record of the defect and turn the
  conformance test into an assertion about a file this repository wrote for
  itself.
* The refusals are asserted one divergence at a time against these bytes, so
  the test proves the pinned schema and validator refuse the runtime's shapes
  rather than a paraphrase of them.
* The digests above are pinned in the test. If a capture is edited, the test
  fails: the archive cannot be quietly repaired to match a later schema.
* They are **not authoritative**. No RETURN manifest may cite them as a
  validated recovery pair, no dispatch may be made from them, and no tool reads
  them outside these tests. The `canonical-*` pair is the representation that
  validates; the captures are history.

Three divergences are worth naming here because the archive is where they stay
visible: the runtime's request carries orchestration bookkeeping (`number`,
`attempts_used`, `created_at`) the request schema has no vocabulary for, its
`request_digest` seals that non-canonical body (so the canonical request cannot
reuse the digest), and the decision ends `supersedes` with a new contract id
(`T2-REACHABILITY-r1`) rather than a revision of the same contract.

## Limits of this archive

* The failed contract's bytes are not in this repository. The capture records
  its identity and hash (`T2-REACHABILITY`,
  `b30fdd670282a097701bae2841177f99ccefcc9243055ac2696766dd6a1e249b`); the body
  lives in the bundlebees run that produced it, so only the hash can be cited.
* The verifier's own record for `att_m4_2` lived in the run directory too. The
  canonical request therefore names this directory's `captured-request.json` as
  its evidence reference: it is the durable, byte-pinned record that carries the
  verifier's observation ("no test was collected for
  `...::Reachability::test_ancestor_ok`", "no tests ran in 0.01s"), and its
  hash is the one recorded in the evidence entry.
* The canonical corrected contract is the captured body re-approved under the
  contract id `T2-REACHABILITY` at the same timestamp by the same adapter. Its
  hash is `52d17e65714343bcb86547309454beea9aca95944ce76a3732d3fd0fede3df72`,
  not the captured `5d2fa3d77465420090ef157250ad0a7f37b8b2d52f61177ff6e44adaef7172d4`:
  `contract_sha256` covers the contract id, so a supersession that keeps the id
  cannot cite a contract frozen under a different one.
