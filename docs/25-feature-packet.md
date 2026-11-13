# 25 — Feature packet protocol (`rizzstack.feature-packet/1`)

Status: draft, normative for workflow-native queue execution.

A **feature packet** is the durable, self-contained description of one queued
development feature. It binds the original request to a frozen `acdd/1` contract,
a pinned workflow protocol revision, an authorization reference and a
source-revision policy. Another coordinator can resume the feature from the packet
alone; no chat history, Kanban text or worker narrative is required.

The packet is **evidence and identity, never authority**. Permission still comes
from the sealed M1 authorization (or an enrolled descendant policy) that the
packet references. Editing a packet cannot authorize anything.

## Shape

Schema: `schemas/feature-packet.schema.json`.
Examples: `schemas/examples/feature-exact.json`, `feature-descendant.json`.
Validator: `tools/feature_packet.py`.

Required content:

| Field | Meaning |
|---|---|
| `packet_version` | `rizzstack.feature-packet/1` |
| `feature_id`, `job_id` | stable queue and job identities |
| `request.summary`, `request.provenance` | the human request and where it came from |
| `repository.identity` | canonical `owner/name` |
| `workflow_ref` | full commit SHA of the protocol used to validate this packet |
| `source_policy` | `exact` revision, or `descendant` with root, one dependency and a `policy_id` |
| `authorization` | reference, approver and time — never a packet-supplied grant |
| `contract`, `contract_sha256` | the frozen `acdd/1` contract and its reviewed hash — **exact packets only** |
| `contract_template` | the unfrozen `acdd/1` template at the authorized root — **descendant packets only** |
| `acceptance_ids`, `tests` | exactly the contract's criteria and approved tests |
| `scope.lease`, `scope.read_only` | write leases and read-only paths |
| `budget` | bees and wall clock |
| `required_evidence` | red, green, regression, gitleaks, integration |
| `prohibited` | actions the worker must not take |
| `human_gates` | merge, release, deploy, publish |

## Validation

`feature_packet.validate(packet, workflow_repo=...)` fails closed on:

* unsupported packet version, or a shape the schema rejects — including an
  `exact` packet that carries `contract_template`, and a `descendant` packet
  that carries `contract`, `contract_sha256` or any resolution pointer (the
  shape rules live in the schema, so a refused shape is always `packet_schema`);
* a `workflow_ref` that is not a commit in the pinned checkout, predates the
  schema, or whose committed schema differs from the enforcing one
  (`validator_mismatch`);
* a contract that is not validly frozen or whose hash disagrees with
  `contract_sha256`;
* acceptance IDs or approved tests that drift from the contract;
* a write lease wider than the contract's assigned files;
* an exact policy whose revision differs from `contract.source_rev`;
* a descendant packet without a policy id, or with more than one dependency
  (multi-dependency support is not claimed);
* a budget that exceeds a ceiling the authorization states, in any dimension it
  states (an omitted ceiling constrains nothing);
* missing authorization provenance or dropped human gates.

`feature_packet.validate_source_resolution(record, packet=..., accepted_commit=...)`
fails closed on: a malformed record; a record that binds another packet digest
(`resolution_packet_digest`), policy id or dependency; an `accepted_commit` that
differs from `derived_source_rev`; a source-bound contract that is not frozen,
whose hash disagrees, or whose `source_rev` is not the accepted commit; and any
contract difference from the intent template other than `source_rev` and the
review block (`resolution_scope_changed`, then `resolution_contract_changed`).
A resolution is refused outright against an exact packet: there is nothing to
derive.

## Source-revision policy

`exact` features run at the authorized revision. `descendant` features cannot name
their revision at intake: the commit does not exist yet. They name the authorized
root and exactly one dependency, plus the enrolled policy id. After the dependency
is accepted, the coordinator resolves the exact commit and freezes the dependent
contract against it. That derivation must prove repository identity, ancestry from
the root, equality with the dependency's accepted integration commit, unchanged
scope and budget, and it must be recorded as a create-only, sealed derived
authorization referencing the enrolled policy and its digest.

A packet must never be rewritten in place to point at the resolved revision. The
resolved revision belongs to the derived authorization and the frozen contract,
which are sealed and durable.

### Two stages, two immutable records

Stage 1 is the **intent packet**: `source_policy.kind = descendant`, an unfrozen
`contract_template` whose `source_rev` is the authorized `root_revision`, and no
`contract` or `contract_sha256`. Stage 2 is a **source-resolution record**
(`schemas/source-resolution.schema.json`, `rizzstack.source-resolution/1`),
created only after the dependency is accepted:

| Field | Meaning |
|---|---|
| `packet_digest` | canonical digest of the intent packet this record resolves |
| `policy_id`, `policy_digest` | the enrolled policy and the digest it was enrolled at |
| `dependency_feature`, `dependency_job` | the accepted dependency and its job |
| `accepted_commit`, `derived_source_rev` | the dependency's accepted integration commit; the two must be equal |
| `contract`, `contract_sha256` | the template frozen against the derived revision, and its hash |
| `at` | when the resolution was recorded |

The link is one way — resolution → `packet_digest` — because the packet is never
rewritten. The canonical digest is sha256 over
`json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`
(`tools/feature_packet.py:packet_digest`). Only `contract.source_rev` and the
review block may differ from the template: the validator compares the whole
contract, not just the scope, so a rewritten title or a widened criteria list is
refused as `resolution_contract_changed`.

`policy_digest` can only be checked for shape here: the enrolled policy is not
readable from the packet, so the coordinator must compare it with the enrollment
record before accepting the resolution. Everything else in the record is checked
against the packet, the accepted commit, or the frozen contract.

### Pinned examples

Both examples carry a `workflow_ref` naming a real ancestor commit that bears
these schemas, so `check_protocol_commit=True` compares real bytes rather than
falling back to an unchecked path. When a schema changes, the pin is bumped in a
follow-up commit to the commit that bears the new schema; until then the examples
fail with `validator_mismatch`, which is the intended alarm. The tests assert
that the pin is a commit, an ancestor of `HEAD`, and byte-identical to the
enforced schema for **both** schemas.

## Coordinator conformance

A conforming coordinator:

1. validates the packet before admitting the job, using the pinned `workflow_ref`;
2. records the packet digest and workflow revision in the job's sealed goal;
3. refuses a resumed job whose protocol revision or packet digest changed;
4. treats a legacy job without a packet as legacy — it never invents packet
   evidence for it;
5. publishes an accepted commit to a governed mirror and records the receipt in
   the return evidence;
6. reports only what durable records prove.

## Relationship to other protocol documents

* `docs/16-acdd-tdd.md` — contracts, tests and RED/GREEN evidence.
* `docs/19-coordinator-playbook.md` — intake, reconciliation, lanes, gates.
* `docs/20-orchestrator-handoff.md` — handoffs between coordinators.
* `templates/RETURN.md` — the human-facing result record.
