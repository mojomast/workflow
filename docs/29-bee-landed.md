# 29 — Bee Landed (`rizzstack.bee-landed/1`)

Status: draft, normative for the terminal landing event.

A **Bee Landed** event says one thing: a worker attempt reached a terminal state
(`succeeded`, `failed` or `cancelled`) under a named lease and backend. It is the
canonical CloudEvents 1.0 announcement of that transition, not a review.

The event is intentionally narrower than the RETURN manifest. It is small,
transport-friendly and safe to publish to a queue, an event bus or a durable log.
The artifact, the verification record and the acceptance decision stay outside
it and are addressed by digest or reference.

- Wire schema: `rizzstack.bee-landed/1`
- CloudEvents type: `rizzstack.bee.landed.v1`
- Schema: `schemas/bee-landed.schema.json`
- Validator: `tools/bee_landed.py`
- Tests: `tests/test_bee_landed.py`

## LANDED is not VERIFIED is not ACCEPTED

| Claim | Who can make it | What it means | Where it lives |
|---|---|---|---|
| **LANDED** | the coordinator or adapter that observed the worker exit | one attempt reached a terminal state; the lease is closed | this event |
| **VERIFIED** | a receiver that reproduced the checks | the named checks ran at the named revision and produced a result | verification evidence and the RETURN manifest |
| **ACCEPTED** | the human receiver | the work is accepted into the integration line | the RETURN document's receiver decision |

A producer may emit LANDED. A producer may not emit VERIFIED or ACCEPTED, and the
validator refuses the attempt: fields such as `verified`, `accepted`,
`verification`, `acceptance`, `approved` and `decision` are rejected when they
carry a claim, and `state` is limited to the three terminal states. A landed
`succeeded` event is evidence that the attempt ended, not evidence that its
output is correct.

The ordering is therefore:

```
LANDED (delivery fact) -> VERIFIED (reproduced result) -> ACCEPTED (human decision)
```

Skipping a step is a protocol violation, not a shortcut. A failed or cancelled
landing is still a LANDED event: terminal delivery is recorded even when the work
did not succeed.

## Envelope

The event is a CloudEvents 1.0 envelope. Required attributes:

| Attribute | Meaning |
|---|---|
| `specversion` | exactly `1.0` |
| `id` | UUID text form or URN, unique per emitted event |
| `source` | URI-reference naming the emitting coordinator or adapter |
| `type` | exactly `rizzstack.bee.landed.v1` |
| `time` | RFC 3339 timestamp of the terminal transition |
| `subject` | the worker task or attempt in the emitter's stable naming |
| `data` | the `rizzstack.bee-landed/1` payload below |

CloudEvents extension attributes are permitted at the envelope root. The `data`
object is closed: producer-defined payload fields are refused. An extension must
not be used to smuggle a receiver-side claim, a credential or a patch body.

## Payload

Required fields:

| Field | Meaning |
|---|---|
| `schema` | exactly `rizzstack.bee-landed/1` |
| `feature_id`, `job_id`, `task_id`, `attempt_id` | stable ids for the unit of work |
| `coordinator.identity` | who observed and emitted the transition |
| `coordinator.session` | optional coordinator session id (an id, never a credential) |
| `backend.harness` | the agent harness or runner that executed the attempt |
| `backend.model` | optional model id reported by the harness |
| `state` | `succeeded`, `failed` or `cancelled`; no other value is terminal here |
| `source_rev` | lowercase 40-hex git revision or 64-hex sha256 revision |
| `lease.sha256` | digest of the lease the coordinator granted |
| `lease.assigned_files` | repository-relative paths the lease assigned |
| `result.available` | whether a result artifact exists |
| `result.artifact_sha256` | optional digest of the artifact |
| `result.reference` | optional portable pointer to the artifact |

Optional fields: `terminal_transition_id`, `correlation_id`, `causation_id`.

When `result.available` is true, at least one of `artifact_sha256` or `reference`
must be present. When it is false, the event says no artifact exists; it does not
imply that the attempt succeeded.

### Dedupe key

Consumers dedupe on:

```
sha256(attempt_id + ":" + state + ":" + terminal_transition_id)
```

`terminal_transition_id` is the durable id of the transition. If the producer
omits it, `tools/bee_landed.py:dedupe_key` uses the CloudEvents `id` as the
transition id. Redelivering the same terminal landing, or observing it through a
second transport, therefore collapses to one key. A retry with a new attempt id
or a new transition id is a distinct landing.

## Delivery semantics

Bee Landed is **at-least-once delivery with idempotent consumption**.

- The producer emits after the worker lease is closed and after the transition is
  durable. It does not emit an optimistic event before the outcome is known.
- The event may be delivered more than once. It may arrive out of order relative
  to other events in the same correlation.
- The event is immutable. A correction is a new event with a new `id` and a new
  `terminal_transition_id`, not a mutation of the old one.
- `time` is the terminal transition time, not the delivery time. Subscribers must
  tolerate a late delivery carrying an old `time`.
- A consumer that cannot process an event must not acknowledge it as accepted;
  it should retry or route to a dead-letter record, where the same dedupe key
  still applies.

The event carries no authority. A subscriber that needs authorization, a
verification result or an acceptance decision must obtain it from the governed
record, not from this envelope.

## Subscriber obligations

A subscriber that receives a Bee Landed event must:

1. Validate the envelope and payload with `tools/bee_landed.py:validate`.
2. Compute `dedupe_key` and refuse to process the same key twice.
3. Treat `succeeded`, `failed` and `cancelled` as terminal. Never reinterpret a
   failed or cancelled landing as a success because an artifact happens to exist.
4. Reject credentials, private filesystem paths, full patches and oversized
   payloads. These are protocol violations, not merely suspicious input.
5. Never treat LANDED as VERIFIED or ACCEPTED. If the subscriber needs either,
   it must run the appropriate verification or escalate to the human receiver.
6. Resolve `result.reference` through an approved transport and check
   `artifact_sha256` when present. The event proves delivery, not artifact
   integrity by itself.
7. Keep the original event bytes or canonical JSON alongside the dedupe key so a
   later audit can recompute the key.

A subscriber must not rewrite the event, add a receiver-side status to it, or use
it as a substitute for the RETURN document.

## Adapter portability

The envelope is deliberately portable across agent harnesses:

- `backend.harness` names the runner and `backend.model` is optional. An adapter
  for a different harness maps its own exit information into the same fields.
- `coordinator.identity` is the stable adapter identity, and
  `coordinator.session` is optional because not every harness exposes a session.
- `source` is a URI-reference chosen by the adapter, not a local path.
- `source_rev` accepts both 40-hex git revisions and 64-hex sha256 revisions, so
  git-backed and content-addressed adapters can emit the same event type.
- `lease.assigned_files` is repository-relative, so the event does not leak the
  host layout and remains meaningful on another machine.
- A harness that cannot supply an artifact sets `result.available` to false and
  omits both artifact fields; it still emits a terminal landing.

Adapters must not invent a `verified` or `accepted` state to fit a richer native
API. They translate their native terminal state into `succeeded`, `failed` or
`cancelled` and leave receiver-side judgements out of the envelope.

## Refusal rules

`tools/bee_landed.py` raises a `BeeLandedError` with a stable code for:

- a CloudEvents version other than `1.0` (`bee_cloud_events_version`);
- an `id` that is neither UUID nor URN (`bee_event_id`);
- a wrong `type`, malformed `time`, bad `source` or missing required field;
- a `data.schema` other than `rizzstack.bee-landed/1`;
- a non-terminal or unknown `state`;
- an uppercase or wrong-length `source_rev`;
- a malformed lease digest, path or duplicate assigned file;
- an available result that names no artifact;
- a credential-like field or value (`bee_secret`);
- a private filesystem path (`bee_private_path`);
- an embedded full patch (`bee_patch`);
- an event larger than 64 KiB (`bee_oversized`);
- a client claim of `verified`, `accepted`, `approved` or similar
  (`bee_client_claim`).

The schema and the validator enforce the same shape. `jsonschema` is used by the
test suite when available to cross-check positives against the schema, but the
validator itself only needs the Python standard library.
