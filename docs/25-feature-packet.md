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
| `contract`, `contract_sha256` | the frozen `acdd/1` contract and its reviewed hash |
| `acceptance_ids`, `tests` | exactly the contract's criteria and approved tests |
| `scope.lease`, `scope.read_only` | write leases and read-only paths |
| `budget` | bees and wall clock |
| `required_evidence` | red, green, regression, gitleaks, integration |
| `prohibited` | actions the worker must not take |
| `human_gates` | merge, release, deploy, publish |

## Validation

`feature_packet.validate(packet, workflow_repo=...)` fails closed on:

* unsupported packet version, or a shape the schema rejects;
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
* missing authorization provenance or dropped human gates.

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
