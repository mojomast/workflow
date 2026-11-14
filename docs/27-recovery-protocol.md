# 27 — Bounded recovery protocol (`rizzstack.recovery/1`)

Status: draft, normative for M4 bounded recovery.

A failure inside an authorized job has exactly three honest outcomes: try the
same contract again, correct a contract that cannot be satisfied, or stop and
ask the human who authorized the work. This chapter defines the two durable
documents that record that choice — a **request** written mechanically by the
orchestrator, and a **decision** written by an agent adapter and validated
mechanically by bundlebees — plus the optional `recovery` array a RETURN
manifest carries.

The pair exists so recovery is **agent-agnostic** and **bounded**:

* the request states what failed and what the approved envelope allows, before
  any agent reasons about it;
* the decision names the adapter that reasoned, and may only choose among the
  options the envelope already permits;
* neither document grants authority. The envelope restates an existing
  authorization; a decision can use it, not enlarge it.

Schema: `schemas/recovery.schema.json`.
Validator: `tools/recovery.py`.
Examples: `schemas/examples/recovery-request.json`,
`schemas/examples/recovery-decision.json`.
Tests: `tests/test_recovery_protocol.py` (required CI job
`recovery-protocol`). Runtime conformance: `tests/test_runtime_conformance.py`
with `tests/fixtures/runtime/` — the archived pre-conformance bundlebees
records and the canonical pair derived from them, see
[Runtime conformance and migration](#runtime-conformance-and-migration).

## The five failure classes

A class is decided from evidence, never from what would be convenient to retry.

| Class | Meaning | Required evidence | Legal decisions |
|---|---|---|---|
| `implementation` | the patch did not satisfy the approved tests | a `test` or `command` record | retry (within budget), escalate |
| `specification` | the acceptance selection itself is unusable, so no patch can satisfy it | a `test` or `log` record | supersede (once, if permitted), escalate |
| `environment` | the worker host lacked a tool, dependency or route | an `environment` record | escalate |
| `infrastructure` | the launcher, scheduler or storage failed | an `infrastructure` record | escalate |
| `integration` | verified patches did not combine | a `conflict` record naming the conflicted paths | retry (bounded repair), escalate |

Codes are class-specific:

| Class | Codes |
|---|---|
| `implementation` | `test_failed`, `suite_failed`, `lease_violation`, `gitleaks_failed` |
| `specification` | `acceptance_uncovered`, `test_not_found`, `missing_test` |
| `environment` | `toolchain_missing`, `dependency_unavailable`, `network_blocked` |
| `infrastructure` | `launcher_unavailable`, `scheduler_stalled`, `storage_full` |
| `integration` | `merge_conflict`, `combined_suite_failed`, `wave_rejected` |

`specification` is the narrow class. Its three codes are the three ways an
acceptance selection can be unusable: a criterion no test covers, a named test
that does not exist, or a test file missing at the pinned revision. A failing
test is **not** a specification failure — that is `implementation`
(`test_failed`). The validator refuses a code that does not belong to the
request's class (`failure_code_mismatch`), so this distinction cannot be blurred
by a mislabelled document.

## Request

Written by the orchestrator from recorded evidence, before any adapter is asked
to reason.

| Field | Meaning |
|---|---|
| `schema` | `rizzstack.recovery/1` |
| `request_id` | stable identity; the decision and the RETURN entry name it |
| `job_id`, `feature_id`, `task_id` | the durable queue identities |
| `attempt_id` | the failed attempt; its record is preserved, never rewritten |
| `failure` | `class`, `code`, `evidence[]`, `rationale` |
| `contract` | the frozen `acdd/1` contract `id` and reviewed `sha256` the attempt ran under |
| `supersession_permitted` | `true` only for a specification failure whose correction was pre-authorized |
| `envelope` | `max_attempts_per_task`, `contract_corrections_allowed`, `corrected_tests_allowed[]` |
| `outstanding_question` | the question the decision answers, stated before the decision exists |
| `request_digest` | sha256 of the canonical request body (below) |

Every field is required; the schema refuses unknown fields at every level.

### Evidence

`failure.evidence` is a non-empty array of records:

```json
{"kind": "log", "reference": "evidence/.../verify-att-0007.log", "sha256": "<64 hex>"}
{"kind": "conflict", "reference": "evidence/.../integrate-wave.log", "paths": ["tools/acdd-lint/acdd_lint/cli.py"]}
```

| Field | Meaning |
|---|---|
| `kind` | `test`, `command`, `log`, `conflict`, `environment` or `infrastructure` |
| `reference` | path or durable reference to the record; the record stays authoritative |
| `sha256` | optional content hash, when the producer recorded one |
| `paths` | required on `conflict`, refused on every other kind: the conflicted paths |

Rules:

* at least one evidence entry is required — a classified failure with no record
  is a claim;
* the class requires its own kind (`evidence_missing`) and refuses a `conflict`
  record unless the class is `integration` (`evidence_forbidden`);
* an `integration` failure must carry at least one `conflict` record with a
  non-empty `paths` list (`conflict_evidence_incomplete`). That is the
  **distinct repair evidence**: an integration repair is not a renamed retry of
  the implementation failure, and the repair is bounded by the same attempt
  budget as any other retry.

### Envelope

The envelope is the only place a widening can come from, and it is written from
the authorization that already exists — not by the adapter.

| Field | Type | Meaning |
|---|---|---|
| `max_attempts_per_task` | integer 1–5 | total attempts allowed for this task, **counting the failed attempt**. `2` means one retry. v1 caps every envelope at five attempts, even if the authorization states more. |
| `contract_corrections_allowed` | integer 0–1 | contract revisions this task may consume. v1 allows one specification supersession, so the maximum is 1. |
| `corrected_tests_allowed` | array of test ids | the only tests a decision may add or substitute. Populated for a specification correction (when permitted) or an integration repair, and empty otherwise. |

Coherence is enforced at request time (`envelope_widened`,
`supersession_not_permitted`):

* `supersession_permitted` is `true` only for a `specification` failure;
* a permitted supersession needs `contract_corrections_allowed >= 1`, and a
  correction budget requires the permission;
* `corrected_tests_allowed` may be populated only for a `specification` failure
  that permits the correction, or for an `integration` failure whose bounded
  repair may add a regression test. Every other class refuses a test list.

### Sealing

`request_digest` is sha256 over

```
json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
```

where `body` is the request without `request_digest`. The request has no
volatile field, so sealing is deterministic: the same request always produces
the same digest. `tools/recovery.py:seal_request` recomputes it and
`validate_request` refuses a mismatch (`request_digest_mismatch`). The digest is
an integrity and binding check, **not a signature**.

## Decision

Written by one agent adapter. Reasoning lives here; authority does not.

| Field | Meaning |
|---|---|
| `schema` | `rizzstack.recovery/1` |
| `request_id` | the request answered; must match exactly |
| `request_digest` | the binding: the request's digest, recomputed from the request body |
| `adapter` | the agent adapter that reasoned (`codex-cli`, `claude-code`, …) |
| `decision` | `retry`, `supersede` or `escalate` |
| `corrected_tests` | the corrected selection; required for `supersede`, optional inside the allowed list for an integration repair, otherwise empty |
| `supersedes` | `null`, or `contract_id`, `contract_sha256`, `new_contract_id`, `new_contract_sha256` |
| `rationale` | why this decision answers the outstanding question inside the envelope |
| `decided_at` | when the adapter decided; a historical record |

### Decision matrix

| Class | `retry` | `supersede` | `escalate` |
|---|---|---|---|
| `implementation` | yes, if an attempt remains | no | yes |
| `specification` | no | yes, if permitted and a correction remains | yes |
| `environment` | **no** | **no** | yes, and it is the only option |
| `infrastructure` | **no** | **no** | yes, and it is the only option |
| `integration` | yes, if an attempt remains; distinct conflict evidence required | no | yes |

`environment` and `infrastructure` never authorize a worker dispatch: no patch
can install a missing toolchain or restart a dead launcher, so the validator
refuses any `retry` or `supersede` for those classes
(`failure_class_no_dispatch`). The only path is escalation to the human who owns
the host. This is M4 AC-004, enforced rather than documented.

`specification` may not retry (`decision_class_mismatch`): re-dispatching a patch
against a contract that cannot be satisfied burns budget and manufactures
failures. It supersedes once, or escalates.

`integration` retries only as a bounded repair: the attempt budget bounds it,
and the request must already carry the conflict record and paths.

### Budgets and exhaustion

The validator takes two durable ledger counts, because they are facts of the job,
not fields an adapter may state:

| Argument | Meaning |
|---|---|
| `attempts_used` | attempts already consumed for this task, **including the failed attempt the request names** |
| `corrections_used` | contract corrections already consumed for this task |

A `retry` or `supersede` requires `attempts_used < max_attempts_per_task`
(`budget_exhausted`). A `supersede` also requires
`corrections_used < contract_corrections_allowed` (`budget_exhausted`).
`escalate` needs no budget and is always legal.

Exhaustion therefore never ends in a silent success: once the budget is spent,
the only decision that validates is `escalate`, and every escalation in M4 ends
at `awaiting_approval`, never `done`.

### Supersession

One specification supersession per task, matching the devplan and the B3b
pattern (`supersedes` + `supersedes_sha256`).

```json
"supersedes": {
  "contract_id": "SMOKE-R",
  "contract_sha256": "<the failed contract's reviewed hash>",
  "new_contract_id": "SMOKE-R",
  "new_contract_sha256": "<the corrected contract's reviewed hash>"
}
```

Rules, all mechanical:

* `contract_id` and `contract_sha256` must equal the request's `contract.id` and
  `contract.sha256` (`supersedes_mismatch`) — a decision replaces exactly the
  contract that failed, not one it prefers;
* `new_contract_id` must equal `contract_id` (`decision_scope_widened`) — a
  correction revises the same contract; a different id is a new feature, which
  needs its own packet and authorization;
* `new_contract_sha256` must differ from `contract_sha256`
  (`supersedes_mismatch`) — an unchanged contract is not a correction;
* `corrected_tests` must be non-empty (`corrected_tests_required`) and every
  entry must be inside `envelope.corrected_tests_allowed`
  (`corrected_tests_not_allowed`) — the adapter selects from the pre-authorized
  replacements, it does not invent acceptance;
* `supersession_permitted` must be true (`supersession_not_permitted`) and one
  correction must remain (`budget_exhausted`).

The corrected contract is a new, separately frozen `acdd/1` revision. The old
attempt and its evidence stay on disk. A supersession never edits history.

### No self-approved widening

A decision is refused when:

* it carries any field the schema does not define — including an envelope, a
  scope, a budget or a lease (`recovery_schema`). The decision has no vocabulary
  for widening;
* `adapter` names a mechanical component (`adapter_reserved`). `bundlebees`,
  `reconciler` and `validator` validate; they do not reason, so they cannot
  decide their own recovery;
* it supersedes a different contract, changes the contract id, keeps the same
  hash, or names a test outside `corrected_tests_allowed` (above);
* it retries or supersedes a `specification`, `environment` or
  `infrastructure` failure where the matrix forbids it
  (`decision_class_mismatch`, `failure_class_no_dispatch`);
* it reports corrected tests on an implementation retry or on an escalation
  (`corrected_tests_unexpected`) — neither changes acceptance;
* its `request_digest` or `request_id` does not bind the exact request
  (`decision_binding_mismatch`). A decision cannot be replayed against another
  failure, and a request edited after the decision no longer validates
  (`request_digest_mismatch`).

The only widening path is `supersede`, and its bounds all come from the request.

### Digest binding

A decision has no digest field of its own. It binds the request through
`request_digest`, which must equal both the request's field and a recomputation
from the request body. That is what makes the pair durable: bundlebees can store
the request once, hand it to any adapter, and refuse a decision that answers a
different request — however plausible its text.

`tools/recovery.py:decision_digest` hashes the whole canonical decision so a
coordinator can journal the bytes it stored. It is not part of the document and
proves nothing about authorship.

## Validation

`tools/recovery.py`:

```
validate_request(request) -> request
validate_decision(decision, request=..., attempts_used=N, corrections_used=M) -> decision
validate_pair(request, decision, attempts_used=N, corrections_used=M) -> {"request": ..., "decision": ...}
recovery_entry(request, decision) -> RETURN manifest entry
```

`validate_decision` validates the request first, so an inadmissible request
cannot carry a valid decision.

| Code | Refusal |
|---|---|
| `recovery_schema` | wrong shape, unknown field, bad pattern or enum |
| `recovery_version_unsupported` | a version other than `rizzstack.recovery/1` |
| `recovery_ambiguous` | a document carrying both request and decision fields |
| `request_digest_mismatch` | the request body does not hash to `request_digest` |
| `failure_class_unknown` | not one of the five classes |
| `failure_code_mismatch` | a code that does not belong to the class |
| `evidence_missing` | no evidence of a kind the class requires |
| `evidence_forbidden` | a conflict record on a non-integration failure, an environment record on an integration failure, or `paths` on a non-conflict record |
| `conflict_evidence_incomplete` | an integration failure without a conflict record naming paths |
| `supersession_not_permitted` | a supersession permit on a class that may not supersede, or a decision against a request that does not permit one |
| `envelope_widened` | corrections or corrected tests granted without a permission |
| `decision_binding_mismatch` | the decision names another request or another digest |
| `adapter_reserved` | a mechanical component named as the deciding adapter |
| `decision_class_mismatch` | a (class, decision) pair the matrix forbids |
| `failure_class_no_dispatch` | retry or supersede for `environment` / `infrastructure` |
| `budget_exhausted` | no remaining attempt or correction |
| `supersedes_required` / `supersedes_unexpected` | a supersede without a block, or a block without a supersede |
| `supersedes_mismatch` | the superseded contract or the corrected hash is wrong |
| `decision_scope_widened` | the correction changes the contract id |
| `corrected_tests_required` / `corrected_tests_not_allowed` | no corrected tests on a supersede, or a test outside the allowed list |
| `corrected_tests_unexpected` | corrected tests on an implementation retry or an escalation |
| `recovery_argument` | a ledger count that is not a non-negative integer |

Command line:

```
python3 tools/recovery.py request schemas/examples/recovery-request.json
python3 tools/recovery.py decision schemas/examples/recovery-decision.json \
    --request schemas/examples/recovery-request.json --attempts-used 1
python3 tools/recovery.py seal path/to/request.json > sealed.json
python3 tools/recovery.py entry --request r.json --decision d.json --attempts-used 1
```

`request` and `decision` print `ok <id>`; `seal` prints the request with a
recomputed digest and does **not** validate; `entry` prints the RETURN manifest
entry for a validated pair.

## The RETURN manifest's recovery array

`rizzstack.return/1` gained an **optional** `recovery` array. A manifest that
omits it stays valid. Each entry is one recovery the return depends on:

```json
{
  "request_id": "recovery-feature-a-t1-0001",
  "request_digest": "<the request's digest>",
  "failure_class": "specification",
  "decision": "supersede",
  "adapter": "codex-cli",
  "supersession": {
    "contract_id": "SMOKE-R",
    "contract_sha256": "<failed contract hash>",
    "supersedes": "SMOKE-R",
    "supersedes_sha256": "<corrected contract hash>"
  }
}
```

`supersession` is `null` unless the decision is `supersede`. The naming is the
B3b naming: `contract_*` is the replaced contract, `supersedes` and
`supersedes_sha256` are the replacement. `tools/return_manifest.py` refuses:

* a duplicate `request_id` (`recovery_entry_invalid`);
* `supersede` without a supersession block, a block on any other decision, or a
  "correction" whose new hash equals the old one
  (`recovery_supersession_mismatch`);
* `retry` for `specification`, `environment` or `infrastructure`, `supersede`
  for anything but `specification`, or any non-`escalate` decision for
  `environment` / `infrastructure` (`recovery_decision_class_mismatch`).

The entries are a summary. The request and decision documents are the authority,
and `recovery_entry(request, decision)` produces the entry from validated
documents so the field names cannot drift.

## What bundlebees must emit

The lane is agent-agnostic: any adapter may answer, and bundlebees never writes
the decision. Mechanically it does five things.

1. **Classify and record.** `reconcile.classify_failure` maps the verify or
   integration record to one class and one code, preserving the record:

   | Observation | Class | Code |
   |---|---|---|
   | named test absent / collection error | `specification` | `test_not_found` |
   | criterion has no test | `specification` | `acceptance_uncovered` |
   | test file missing at the pinned revision | `specification` | `missing_test` |
   | the named test ran and failed | `implementation` | `test_failed` |
   | the suite beyond the named test failed | `implementation` | `suite_failed` |
   | the patch touched a path outside the lease | `implementation` | `lease_violation` |
   | gitleaks found a secret | `implementation` | `gitleaks_failed` |
   | a tool, dependency or route is absent on the host | `environment` | `toolchain_missing` / `dependency_unavailable` / `network_blocked` |
   | the launcher, journal writer or disk failed | `infrastructure` | `launcher_unavailable` / `scheduler_stalled` / `storage_full` |
   | `integrate_wave` reported a conflict | `integration` | `merge_conflict` |
   | the combined suite failed after integration | `integration` | `combined_suite_failed` |
   | the wave record rejected the patch set | `integration` | `wave_rejected` |

   A classification that cannot name its evidence is not written as a request;
   it escalates with the raw record.

2. **Write the request.** Emit exactly:
   `schema`, `request_id`, `job_id`, `feature_id`, `task_id`, `attempt_id`,
   `failure` (`class`, `code`, `evidence[]` with `kind`, `reference`, optional
   `sha256`, optional `paths` on `conflict`; `rationale`), `contract` (`id`,
   `sha256`), `supersession_permitted`, `envelope` (`max_attempts_per_task`,
   `contract_corrections_allowed`, `corrected_tests_allowed`),
   `outstanding_question`, `request_digest`.

   The envelope is copied from the approved authorization and can only narrow
   it. If the authorization grants two bee dispatches for a task,
   `max_attempts_per_task` is at most 2.

3. **Seal and persist** with `seal_request`, then validate with
   `validate_request` before the adapter ever sees it. The request is the
   durable record: the adapter receives its bytes, not a summary.

4. **Validate the decision** with
   `validate_pair(request, decision, attempts_used=<ledger>, corrections_used=<ledger>)`
   before acting. Refused decisions are recorded with their code and do not
   dispatch. `attempts_used` counts the failed attempt; a task's first failure
   with `max_attempts_per_task: 2` leaves one attempt.

5. **Act, then record.** `retry` re-dispatches the same contract; `supersede`
   freezes the corrected contract, records `supersedes`/`supersedes_sha256`, and
   re-dispatches once; `escalate` moves the task to `awaiting_approval` with the
   decision's rationale and the request's evidence. Append the event, then add
   the `recovery_entry(...)` to the return.

No step lets an adapter set a budget, choose a contract other than the one that
failed, add an unapproved test, or dispatch for a host or launcher failure.

## Runtime conformance and migration

`rizzstack.recovery/1` is unchanged by the M4.1 conformance work. The schema,
the enums and the validator rules in this chapter are the ones bundlebees must
meet; where the runtime's output and the protocol disagree, the runtime's output
is refused. Nothing here narrows or relaxes a rule to fit a producer.

The first real runtime pair — `bundlebees` at `191dc85`, the M4 dogfood of
2026-11-14 (`job_m4_dogfood`, task `T2`, attempt `att_m4_2`) — did not meet the
protocol. Its documents are archived byte-for-byte in
`tests/fixtures/runtime/captured-*.json`, with their sha256s pinned in
`tests/test_runtime_conformance.py` and recorded in that directory's README.
They stay there unmodified and **non-authoritative**:

* they are the evidence that a working runtime produced documents the protocol
  refuses; editing them into conformance would erase the defect and leave the
  conformance test asserting nothing;
* no RETURN manifest may cite them as a validated pair, no dispatch may be made
  from them, and nothing outside the conformance tests reads them;
* the representation that validates is the canonical pair derived from the same
  evidence (`canonical-request.json`, `canonical-decision.json`). The captures
  are history, not input.

### What the runtime wrote and what the protocol requires

Each row is refused on its own by the pinned schema or validator, so a refusal
names the exact rule. The canonical column is the one representation chosen for
that mismatch, derived from the same evidence.

| Runtime shape | Refusal | Canonical representation | Why that representation |
|---|---|---|---|
| request carries `number` | `recovery_schema`, `<root>: Additional properties are not allowed` | field dropped | per-run attempt numbering is job bookkeeping, not part of the sealed failure statement; v1's request has no numeric counter and must not gain one |
| request carries `attempts_used` | `recovery_schema`, `<root>` | field dropped; the count is passed to `validate_decision` | an attempt ledger is a validation *argument*, not a document field: a request that states its own count could claim budget it does not have |
| request carries `created_at` | `recovery_schema`, `<root>` | field dropped | a volatile field inside the sealed body would make resealing non-deterministic; v1 keeps wall-clock out of the request and the decision's `decided_at` is the only timestamp |
| `envelope.contract_corrections_allowed` is `true` | `recovery_schema`, `envelope.contract_corrections_allowed: True is not of type 'integer'` | `1` | the envelope's bound is a count in `0..1`, and "true" means "uncounted"; an uncountable correction budget is exactly the widening the envelope exists to prevent. The schema gate has to make this refusal: the validator's own `int()` cast would have accepted the bool |
| `failure.evidence` is a string | `recovery_schema`, `failure.evidence: ... is not of type 'array'` | `[{"kind": "test", "reference": "tests/fixtures/runtime/captured-request.json", "sha256": "<capture hash>"}]` | a prose summary is not a reference and cannot be checked. The canonical entry names the durable record that carries the verifier's observation — the archived capture, because the run directory is not durable — and `test` is a kind the `specification` class requires |
| `failure.code` is `test_unresolved` | `recovery_schema`, `failure.code: ... is not one of [...]` | `test_not_found` | the observation is "no test was collected for the named node id": the selector does not resolve at the pinned revision, which is one of the three unusable-acceptance codes. A free-text code would make the class/code check bypassable, so the runtime maps its internal code at the boundary |
| decision carries `decision_digest` | `recovery_schema`, `<root>` | field dropped | a v1 decision has no digest of its own: it proves nothing about authorship and invites replay confusion. The binding is `request_digest`, recomputed from the request body; `decision_digest()` stays a journaling helper, not a field |
| `supersedes.new_contract_id` is `T2-REACHABILITY-r1` | `decision_scope_widened` (shape is legal; the rule is semantic) | `T2-REACHABILITY`, with `new_contract_sha256` for the re-frozen revision | a correction revises the same contract; a different id is a new feature needing its own packet. `contract_sha256` covers the id, so the same body is re-frozen under the canonical id and its hash necessarily changes: the captured `-r1` hash cannot be cited |
| envelope allows the file and `::Reachability::test_ancestor_ok`, while the decision substitutes `::Reachability::test_reachable_commit_is_silent` | `corrected_tests_not_allowed` (found by the migration, after the fixes above) | envelope allows the test file and the replacement the corrected contract names | the runtime's own envelope did not authorise the runtime's own decision. The authorization existed — the approved corrected contract names that method — but the request recorded the selector that does not exist instead. Listing an unusable selector as "allowed" would authorise re-creating the failure |

Two consequences of the rules are worth stating, because they shape any
migration:

* **The request digest cannot be carried over.** The captured
  `request_digest` (`cb79fa54…`) is a correct seal of a body the schema cannot
  express. Removing the three bookkeeping fields changes the canonical body, so
  the canonical request has its own digest (`6d57b980…`) and the decision is
  rebound to it. A derived pair that kept the old digest would be a decision
  pointing at bytes that no longer exist.
* **A supersession forces a re-freeze when the runtime revisioned the id.**
  Keeping both `new_contract_id: T2-REACHABILITY` and the captured `-r1` hash is
  impossible, because the frozen hash covers the id. The corrected contract is
  re-approved under the unchanged id at the same timestamp by the same adapter,
  and the decision names the resulting hash
  (`52d17e65…`). This is a document change, not a schema change.

### What this means for bundlebees

1. Emit the canonical shape: the fields listed under [Request](#request) and
   [Decision](#decision), nothing else at any level. Internal bookkeeping —
   attempt numbers, ledger counts, timestamps — stays in the job and event
   records.
2. Map internal failure codes to the canonical enums at the boundary, in the
   one place that classifies (`reconcile.classify_failure`), and never emit a
   code outside them.
3. Record the correction budget as the integer `0..1`, and populate
   `corrected_tests_allowed` with the selectors the correction may actually
   use: the file or node ids that exist or that the review approved, never the
   selector that failed to resolve.
4. Keep a decision's own digest, if the journal needs one, outside the document.
5. When a pre-conformance pair must be cited, archive it and derive a canonical
   pair, as `tests/fixtures/runtime/` does. Never rewrite the capture, and never
   cite it as validated.

The tests are `tests/test_runtime_conformance.py`; the required CI job
`recovery-protocol` runs them by name and again through the `tests/` discovery
step, so a schema change that starts accepting a runtime shape, or a capture
edited in place, fails the build.

## Worked example

`schemas/examples/recovery-request.json` and `recovery-decision.json` are built
from two real frozen `acdd/1` contracts: the failed one names
`tests/test_smoke.py::AnswerTests::test_answer_is_42`, which does not exist at
the pinned revision; the corrected one names `tests/test_smoke.py`. The request
classifies `specification` / `test_not_found` with the verify log as evidence,
permits one correction, allows only the file-level test, and asks whether that
test replaces the missing node id without changing AC-001's meaning. The
decision answers `supersede` with the exact old and new contract hashes and the
one allowed test.

The pair is the M4 dogfood case: T2's first contract names a test that does not
exist, the loop classifies `specification`, supersedes once, re-dispatches, and
accepts the corrected patch — with the failed attempt and its evidence preserved.
The tests recompute both contract hashes from the fixtures, so the example
cannot drift into a story about contracts that do not exist.

## Limits

* No automatic re-planning: a supersession corrects the selection, it does not
  decompose the feature differently.
* One supersession per task, five attempts maximum, in v1.
* `adapter` is a name, not an authentication. The digest proves the decision
  answers this request, not who wrote it; durable attempt and event records
  carry that.
* `environment` and `infrastructure` recovery is a human act. The protocol
  records the escalation, it does not repair a host.
* Cost stays `UNKNOWN`. A recovery record has no pricing field and must not
  invent one.

## Relationship to other protocol documents

* `docs/23-autonomy-devplan.md` — M4, the milestone this protocol implements.
* `docs/24-autonomy-dogfood.md` — the injected T2 specification failure this
  pair records.
* `docs/16-acdd-tdd.md` — contracts, acceptance criteria, freezing by hash and
  the failure classification this protocol refines.
* `docs/25-feature-packet.md` — the packet and contract a failing task runs
  under.
* `docs/26-return-manifest.md` — the return whose optional `recovery` array
  summarises these documents.
