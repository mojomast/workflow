# 26 — RETURN manifest (`rizzstack.return/1`)

Status: draft, normative for the machine-readable half of a work return.

`templates/RETURN.md` is the human result document: what changed, what was
verified, what remains, and the receiver's decision. This chapter defines its
machine-readable companion, the **RETURN manifest**: one JSON record in which a
producer states the same result against the immutable packet, contract and
protocol revision, with an integrity digest a coordinator can recompute.

The manifest is **evidence, never authority**. It carries no grant, no
acceptance and no human decision. A receiver reads it, reproduces the evidence it
names, and records their own decision in the RETURN document.

Schema: `schemas/return-manifest.schema.json`.
Validator: `tools/return_manifest.py`.
Examples: `schemas/examples/return-exact.json`, `return-dependent.json`.
Tests: `tests/test_return_manifest.py` (required CI job `return-manifest`).

## Shape

Every field below is required except `generated_at`. The schema refuses unknown
fields at every level (`additionalProperties: false`).

| Field | Meaning |
|---|---|
| `schema` | `rizzstack.return/1`; the validator refuses any other version |
| `feature_id`, `job_id` | the packet's stable queue and job identities |
| `packet_digest` | canonical digest of the immutable feature packet this return answers |
| `workflow_ref` | full commit SHA of the protocol revision the producer ran under |
| `repository` | `identity` (`owner/name`) and `source_rev`, the authorized revision the work started from |
| `authorization` | `reference`, `approved_by`, `approved_at`, `authority` (`m1-authorization` or `descendant-policy`) |
| `descendant` | `null` for an exact feature; otherwise the six resolution fields (below) |
| `contract` | the frozen `acdd/1` contract `id` and reviewed `sha256` |
| `acceptance` | one entry per criterion: `id`, `statement`, `tests[]`, `status`, `evidence[]` |
| `red_green` | `test_first`, and the `red`/`green` evidence references or `null` |
| `verification` | `commit`, `files[]`, `base_rev`, `suite`, `gitleaks`, `record_path` |
| `integration` | `commit`, `wave`, `evidence`, `accepted_wave_digest` — all four or all `null` |
| `transport` | `null`, or `mirror_ref`, `source_sha`, `receipt_path` |
| `attempts` | `attempt_id`, `state`, `project`, `source_rev` per attempt |
| `limitations` | known defects, unproven claims and honest scope limits |
| `unrun` | checks that never executed, and why |
| `pending_approvals` | human gates still awaiting an explicit yes |
| `receiver_decision` | always `{status: "pending", decided_by: null, decided_at: null, note: null}` |
| `evidence_digest` | sha256 of the canonical manifest body (below) |
| `generated_at` | optional volatile generation time; the only field outside the digest |

`repository.source_rev` is the revision the packet authorized. For an exact
feature that is `source_policy.revision`; for a dependent feature it is the
derived accepted commit. `verification.commit` is the candidate the checks ran
at, and `integration.commit` is the result after an authorized integration — the
three form a chain, not synonyms.

## The digest

`evidence_digest` is sha256 over

```
json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
```

where `body` is the manifest without `evidence_digest` and without every
`generated_at` field, at any depth. `tools/return_manifest.py:evidence_digest`
implements it and `seal()` returns a copy with the value recomputed.

There are no volatile timestamps in the digested body. `approved_at` is a
historical approval record and belongs inside the digest; `generated_at` is the
only generation-time field and is excluded. Re-sealing an otherwise identical
manifest must not change the digest. Both examples omit `generated_at`
entirely.

The digest is an integrity and binding check, **not a signature**. Anyone can
recompute it. It detects an edited or mis-assembled manifest; it proves nothing
about who wrote it. A receiver who needs authorship must rely on the durable
records the manifest points at.

## Receiver decision

A generated manifest always carries:

```json
{"status": "pending", "decided_by": null, "decided_at": null, "note": null}
```

The schema pins those values and the validator refuses any other status, a
named decider, a decision time or a note (`receiver_decision_not_pending`). The
human decision is recorded in `templates/RETURN.md` (accept / request changes /
blocked), not by editing the manifest. A producer cannot accept its own work by
changing a field, and a consumer cannot mistake producer evidence for a review.

## Acceptance

`status` is exactly one of:

| Status | Meaning |
|---|---|
| `PASS` | the check ran and the criterion holds; **at least one evidence entry is required** |
| `FAIL` | the check ran and the criterion does not hold; evidence should name the failure |
| `NOT RUN` | the check never executed |
| `UNVERIFIED` | a result exists but has not been independently reproduced |
| `BLOCKED` | the check could not be attempted (missing dependency, authorization or environment) |

The validator refuses `PASS` with an empty `evidence` array
(`pass_without_evidence`). It also refuses two entries with the same AC id
(`acceptance_duplicate`). The other statuses may carry evidence or leave it
empty; an empty array is honest for a check that produced no result.

`tests[]` lists the approved tests for that criterion and may be empty for a
review or manual criterion. `statement` is the contract's criterion text.

## RED/GREEN

`red_green.test_first` is true exactly when a RED record exists and is named in
`red_green.red`. The validator refuses a true claim without a RED record, and a
RED record under `test_first: false` (`red_green_inconsistent`). `red`/`green`
are `null` or a reference to a `tdd-evidence/1` record:

```json
{"record_path": "evidence/.../0001-red.json", "sha256": "<64 hex>",
 "revision": "<40 or 64 hex>", "phase": "red"}
```

`phase` is `red` or `green` respectively. The record itself carries the
timestamp; the manifest carries only its path, hash and revision, so the digest
stays stable.

## Dependent features

`descendant` is `null` for an exact feature, whose authority is
`m1-authorization`. A dependent feature names:

| Field | Meaning |
|---|---|
| `policy_id`, `policy_digest` | the enrolled descendant policy and the digest it was enrolled at |
| `source_resolution_digest` | canonical digest of the `rizzstack.source-resolution/1` record (computed like `packet_digest`) |
| `dependency_feature`, `dependency_job` | the accepted dependency and its job |
| `accepted_commit` | the dependency's accepted integration commit |

The authority for a dependent feature is `descendant-policy`. The validator
refuses a mismatch between the authority and the presence of the block
(`descendant_authority_mismatch`), and refuses a dependent return whose
`accepted_commit` differs from `repository.source_rev`
(`descendant_revision_mismatch`): a dependent feature runs at the derived
revision, not at the intent's root.

`source_resolution_digest` is the digest of the resolution **record**, not the
contract hash; `contract.sha256` carries the source-bound contract hash. The
dependent example's fixtures are cross-checked against
`feature_packet.validate_source_resolution`, so the packet → resolution → return
chain is exercised by real records in the tests.

## Integration, transport and attempts

`integration` is all four fields or none. A partially populated block is refused
(`integration_incomplete`): an integration either happened and is recorded with
its commit, wave, evidence and accepted wave digest, or it did not happen in this
return. `null` is the honest value for work still waiting on the merge gate.

`transport` is `null` or a complete receipt: `mirror_ref` (the governed mirror
ref), `source_sha` (the published commit) and `receipt_path`. A partial receipt is
a schema error.

`attempts[].state` is the producer's exact recorded attempt state. This protocol
does not normalize states or invent a state machine; a consumer compares against
the bundlebees attempt record the id names. `source_rev` is the revision the
attempt was briefed against.

## Validation

`tools/return_manifest.py:validate(manifest)` checks the schema, the supported
version, the digest, the pending receiver decision, every acceptance entry, the
RED/GREEN claim, the descendant block and the integration block. It fails
closed with a stable code:

| Code | Refusal |
|---|---|
| `return_schema` | wrong shape, unknown field, bad pattern or enum |
| `return_version_unsupported` | a version other than `rizzstack.return/1` |
| `receiver_decision_not_pending` | a filled or edited receiver decision |
| `evidence_digest_mismatch` | the body does not hash to `evidence_digest` |
| `pass_without_evidence` | `PASS` with an empty evidence array |
| `acceptance_duplicate` | the same AC id reported twice |
| `red_green_inconsistent` | `test_first` and the RED record disagree |
| `descendant_authority_mismatch` | authority and descendant block disagree |
| `descendant_revision_mismatch` | `accepted_commit` is not `repository.source_rev` |
| `integration_incomplete` | only part of the integration block is populated |

Command line:

```
python3 tools/return_manifest.py schemas/examples/return-exact.json
python3 tools/return_manifest.py --seal path/to/manifest.json > sealed.json
```

The first validates one or more files and prints `ok <digest>`. `--seal` prints
the manifest with a recomputed digest and does **not** validate; always validate
the result.

## Pinned examples

Both examples pin the same protocol commit in `workflow_ref`, and the tests
require that commit to be a real ancestor of `HEAD` that bears this schema byte
for byte. When the schema changes, the examples are repinned to the commit that
bears the new schema; until then the pin test fails, which is the intended
alarm. Pinning a commit that predates the schema would make the manifest
unvalidatable by the revision it names.

The two examples are deliberately a pair:

* `return-exact.json` — an exact feature: `descendant: null`, authority
  `m1-authorization`, no integration and no transport yet, merge/deploy pending.
* `return-dependent.json` — a dependent feature: a complete `descendant` block,
  authority `descendant-policy`, an integration record and a mirror receipt, with
  release/deploy still pending.

The fixtures bind the existing packet examples: `packet_digest` is computed from
`feature-exact.json` / `feature-descendant.json`, the exact contract hash matches
the frozen example, and the dependent contract hash matches the source-bound
contract in the reconstructed resolution record.

## Relationship to other protocol documents

* `templates/RETURN.md` — the human result and receiver decision this manifest
  accompanies.
* `docs/25-feature-packet.md` — the packet, its digest and the two-stage source
  policy this manifest answers.
* `docs/16-acdd-tdd.md` — contracts, acceptance criteria and RED/GREEN evidence.
* `docs/20-orchestrator-handoff.md` — what a resumed coordinator must reproduce
  before accepting a return.
