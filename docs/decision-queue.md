# Decision queue (`rizzstack.owner-decision/1`)

Status: draft, normative for the owner-decision lane.

The autonomy architecture reserves a set of acts for the owner alone
(docs/22-autonomy-architecture.md, section 16): resolving a gate, spending
beyond the authorized budget, widening the file or test scope, enrolling or
revoking a grant, and the merge, push, release and deploy acts themselves.
Silence is not consent and a relayed answer is not approval; the reconciler
writes `awaiting_approval` and then does nothing at all.

What that chapter never had was a durable place where such asks live. The
campaign-continuity study (docs/31-campaign-continuity.md) shows why that
matters: the pauses classified as *genuine decision needed* left no durable
record of the question, the evidence behind it, or the answer, so every
restart reconstructed the decision from chat. This chapter defines that
missing surface: a **decision queue** — one durable request per owner gate, a
mechanically validated answer, and exactly-once consumption on the next tick.

It mirrors the bounded recovery protocol (docs/27-recovery-protocol.md) in
shape and discipline. A recovery request asks an agent adapter to reason about
a classified failure inside a sealed envelope; an owner-decision request asks
the owner to resolve a gate the pipeline may not resolve itself. Neither
document grants authority, and neither is ever applied before it validates.

Schema: the owner-decision record contract, `owner-decision.schema.json`,
under the observability schemas directory.
Queue: `bundlebees_plugin/decision_queue.py`.
Snapshot wiring: the optional `decisions` section of the snapshot schema.
Tests: `tests/test_decision_queue.py`, plus the owner-decision cases in
`observability/tests/test_schemas.py`.

## The two documents

One queue entry holds two documents, exactly like a recovery pair.

**A request** is written mechanically by the pipeline — never by an agent —
when work reaches a point the owner must decide:

| Field | Meaning |
|---|---|
| `request_id` | stable identity; names the queue record on disk |
| `kind` | `gate`, `budget`, `scope` or `grant` (closed in v1) |
| `subject` | what the decision governs: a gate name, a job or feature id, or a grant id |
| `question` | the question the owner answers, stated before the owner sees it |
| `evidence` | 1 to 8 durable references (`record`, `report` or `metric`) the owner can inspect |
| `raised_by` / `raised_at` | the mechanical component that raised it, and when |
| `decision_nonce` | 32 hex characters generated at seal time; the decision must echo it |
| `request_digest` | sha256 over the canonical request without the digest field |

Each kind carries exactly its own payload and nothing else: a `budget` request
states `spend_ceiling_usd` and `requested_addition_usd`; a `scope` request
states `proposed_paths` (repository-relative, at most 32, never traversing
upward); a `grant` request states `grant_id` and `grant_action` (`enroll` or
`revoke`); a `gate` request carries no payload at all.

**A decision** is recorded by or for the owner:

| Field | Meaning |
|---|---|
| `request_id` / `request_digest` / `decision_nonce` | the binding: the decision answers exactly one sealed request |
| `decided_by` / `decided_at` | who recorded the answer, and when |
| `outcome` | `approve`, `deny` or `defer` |
| `approval_receipt_ref` | durable reference to the receipt proving the owner's act; required for an approval, refused otherwise |
| `rationale` | why this outcome answers the question, 8 to 500 characters |
| `decision_digest` | sha256 over the canonical decision without the digest field |

An approval without a receipt reference is refused (`missing_receipt`): the
record preserves `decided_by`, but the receipt is the proof of a direct human
act. A deferral records that the owner saw the question and is not deciding
yet; it never closes the request.

## Queue semantics

The queue derives one state per entry: `pending`, `decided`, `applied` or
`withdrawn`.

- **pending** — raised, awaiting the owner. Deferrals may accumulate; the
  request stays pending through every one of them.
- **decided** — a final answer (`approve` or `deny`) is recorded but not yet
  consumed. The next `apply_ready` pass applies it.
- **applied** — consumed exactly once. A second pass skips it; a second
  decision is refused.
- **withdrawn** — retracted while pending. A withdrawn request is never
  decided.

The rules the queue enforces mechanically:

1. The pipeline raises at most one open request per kind and subject
   (`duplicate_open_request`); after an entry is applied or withdrawn, a new
   request for the same subject may be raised.
2. A decision binds its request by digest and echoes its nonce
   (`binding_mismatch`, `nonce_mismatch`), so a decision cannot be replayed
   against a different request even by copy error.
3. `record_decision` and `withdraw` act only on pending entries
   (`not_pending`); duplicate or conflicting final decisions are impossible.
4. `apply_ready` re-validates every pair from disk before applying it; a
   record that no longer validates stops the pass with `record_tampered` and
   nothing after it is applied.
5. No timeout ever turns silence into approval. A pending request is pending
   until a human answers or the pipeline withdraws it.

## Decision receipts

An approval may be accompanied by a frozen **owner-decision receipt**
(`rizzstack.owner-decision-receipt/1`) signed on a trusted route. The receipt
is evidence only; the queue validates it and never persists it in the queue
entry.

The shape is exactly these fields and nothing else. `RECEIPT_FIELDS` is the
canonical field list and order; it is not an input-order requirement, and
the order of keys in a JSON object is irrelevant:

| Field | Meaning |
|---|---|
| `schema` | the literal `rizzstack.owner-decision-receipt/1` |
| `request_id` | the request the receipt answers |
| `request_digest` | the request's sealed digest |
| `decision_nonce` | the request's nonce, echoed by the receipt |
| `outcome` | `approve` or `deny` |
| `decided_by` | the literal `owner` |
| `decided_at` | RFC 3339 UTC timestamp with second precision, ending in `Z`; numeric offsets are refused |
| `decision_digest` | the sealed decision's digest |
| `signature` | 64 lowercase hex characters |

A valid signed `approve` or `deny` receipt is accepted as evidence and verifies
exactly the same way. The legacy `approval_receipt_ref` on a decision remains
approve-only: a `deny` decision that carries it is still refused with
`unexpected_receipt`. A receipt's `decided_at` must be a UTC timestamp ending
in `Z`; a numeric offset is refused with `receipt_bad_timestamp`.

The canonical signing domain is `canonical_json` of the receipt **without**
the `signature` field: sorted keys, compact separators, ASCII escapes. The
signature is HMAC-SHA256 over those canonical bytes, keyed with the
owner-held `BUNDLEBEES_APPROVAL_SECRET`. The key is supplied by the caller,
for example from that environment variable; the queue never reads the secret
itself and never writes it to disk.

`verify_receipt` checks the shape first, then the signature with a
constant-time comparison, then the request and decision bindings. Refusals
name the rule:

- shape: `receipt_unknown_field`, `receipt_missing_field`,
  `receipt_bad_version`, `receipt_bad_id`, `receipt_bad_digest`,
  `receipt_bad_timestamp`, `receipt_bad_outcome`, `receipt_not_owner`;
- key and signature: `receipt_key_missing`, `receipt_signature_invalid`;
- bindings: `receipt_binding_mismatch` (the request id, request digest or
  nonce differs) and `receipt_decision_mismatch` (the decision digest,
  outcome, decision time or `decided_by` differs).

`DecisionQueue.record_decision` accepts an optional `receipt` and `key`. It
validates the decision first, then verifies the receipt against that decision
and its request, and raises before any write if verification fails; the
on-disk record stays byte-identical. A verified receipt is mechanical
evidence, not authority: the queue never performs the human act, and neither
recording nor verifying a receipt applies a decision. Applying remains the
consumer's act.

## What the queue deliberately does not do

It never performs the human act. Applying an approved gate request records
that the gate is resolved; merging, pushing, releasing, deploying and
restarting remain the acts that consume that record, executed by whatever
mechanism already holds the authority to do them. The queue cannot widen a
request either: a budget approval permits exactly the requested addition, a
scope approval admits exactly the proposed paths, and a decision document has
no field with which to ask for more.

Agents never raise owner decisions and never decide them. An agent adapter
that hits a wall writes a recovery request (docs/27-recovery-protocol.md);
only the mechanical pipeline raises an owner request, and only the owner
answers one.

## Storage and integrity

One file per entry, atomically written and fsynced:

```text
<state>/decisions/<request_id>.json
```

The record holds the sealed request, the final decision (when one exists),
every recorded deferral, the applied marker and the withdrawn marker. Request
ids are opaque identifiers and name the file directly, so a hostile id cannot
escape the directory. Digests are recomputed on every read (`get`, `apply_ready`),
which is what makes tampering fail loudly instead of silently applying.

## Observability

The record contract lives next to the other observability schemas and the
snapshot gains an optional `decisions` section: same section header shape as
every other section, with one row per queue entry carrying the queue state,
the final outcome and the decision timestamps. The section is additive and
backward compatible: it is not in the snapshot's required list, the `degraded`
vocabulary is unchanged, and a collector that knows nothing about the queue
still emits a validating snapshot. A newer producer may report kinds beyond
the recognized four as extension labels, exactly as `resource_kind` does.

Scrutiny rules apply as everywhere else in the observability family: a
question is scrubbed bounded text, evidence entries are references rather than
copies, and no entry ever carries credential material, prompts or transcripts.

## Command-line surface

The module is primarily a library for the plugin's reconciler and tick paths.
A small read-and-record surface exists for operators:

```text
python3 bundlebees_plugin/decision_queue.py --state-dir DIR pending
python3 bundlebees_plugin/decision_queue.py --state-dir DIR show --request-id ID
python3 bundlebees_plugin/decision_queue.py --state-dir DIR record --request-id ID --file decision.json
python3 bundlebees_plugin/decision_queue.py --state-dir DIR record --request-id ID --file decision.json --receipt receipt.json --key-env BUNDLEBEES_APPROVAL_SECRET
python3 bundlebees_plugin/decision_queue.py --state-dir DIR verify-receipt --request-id ID --file receipt.json --key-env BUNDLEBEES_APPROVAL_SECRET
python3 bundlebees_plugin/decision_queue.py --state-dir DIR apply
```

`record` takes a decision document as JSON, validates it against the stored
request and refuses anything the queue would refuse; refusals exit 2 with the
error code on stderr as JSON. `--receipt` and `--key-env` must be supplied
together; the receipt is read as JSON and passed to `record_decision`.
`verify-receipt` loads the stored final decision, reads the key from the named
environment variable, verifies the receipt, and prints
`{"ok": true, "request_id": ..., "outcome": ...}` on success.

## Tests

`tests/test_decision_queue.py` covers sealing and digest tamper-evidence,
request and decision validation, kind payload rules, the full queue lifecycle
(raise, defer, decide, apply, withdraw, tamper), the observability section
inside a real collector snapshot, schema agreement between the queue and
`owner-decision.schema.json`, collector compatibility, the receipt canonical
vector, signing, tamper and binding refusals, and the CLI.
`observability/tests/test_schemas.py` covers the record contract and the
optional snapshot extension, including extension labels. The required local
check is:

```text
python3 -m pytest tests/test_decision_queue.py observability/tests/test_schemas.py -q
```
