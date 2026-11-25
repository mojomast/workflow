# Rails contracts (rizzstack.rails/1 family)

These files accompany [the implementation spec](../../specs/rizzstack-rails-spec.md). R01 froze the contract set for the `rizzstack.rails/1` family here: the event envelope, the closed kind payload schemas, the source adapter interface, the shared query request/result, the view projection, the HTTP surface, the RETURN evidence companion, synthetic examples with computed origin hashes, and hash vectors for both the origin algorithm and the legacy upstream compatibility algorithm. Everything is synthetic; no live transcripts or host identifiers are included.

Schema checks cannot establish credential absence, producer authority, canonical byte identity in a running system, idempotency, source completeness or hash integrity of a real ledger. Those require the semantic checks in the specification and the runtime packages (R02+). Runtime validation must be standard-library-only; the repository's existing development JSON Schema tooling may validate fixtures.

## Freeze digest

```
freeze-digest: a82b9489a78e7b578ac6f43fe7a66d383e7ee4be437725db42a1eaa362e48bc6
```

- Covered set (sorted paths, exactly these ten bytes each fed as `name + "\n" + file bytes + "\n"` into one SHA-256): `event.schema.json`, `evidence.schema.json`, `examples.json`, `fixtures/hash-vectors.json`, `http.schema.json`, `payload.schema.json`, `query.schema.json`, `source.schema.json`, `view.schema.json` — nine artifact files; this README is excluded from its own digest. `tests/test_rails_contract.py` recomputes and compares this digest (`TestFreezeDigestRecorded`).
- A consumer that does not recognize a version refuses it; there is no silent widening of `/1`. Any change to a covered file requires a new recorded digest with a recorded rationale (spec D6 discipline).

## Canonical bytes and hashes (spec section 4)

- Canonicalization `C(x)` = `json.dumps(x, sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False).encode("ascii")`, applied only to the envelope value domain: strings, booleans, null, lists, objects and integers within ±(2^53−1). Floats, duplicate JSON keys, non-finite constants and lone Unicode surrogates are rejected before serialization. No Unicode normalization occurs.
- Origin hash = `SHA256(b"rizzstack.rails/1\n" + prev_hash.encode("ascii") + b"\n" + C(envelope without hash))`. The envelope without `hash` still contains `prev_hash` (this reading reproduces the committed examples; `prev_hash` is therefore committed twice, once in the preimage and once in the canonical bytes). `prev_hash` is `genesis` only for seq 1, otherwise 64 lowercase hex. `event_id = chain_id + ":" + decimal seq`, seq contiguous from 1.
- `fixtures/hash-vectors.json` (`rizzstack.rails-hash-vectors/1`) carries canonicalization vectors (Unicode escaping, nulls, reorder invariance, integer boundaries), a synthetic three-event origin chain, negative vectors (tampered byte, wrong prev, unexpected field, changed seq, changed case), and the legacy vector below.

## Legacy compatibility vector (upstream vibeline)

For unmodified vibeline readers, the append table keeps compatibility columns (`id`, `ts`, `task_id`, `actor`, `parent`, `kind`, `ac_id`, `result`, `why`, `tokens_in`, `tokens_out`, `sha`, `prev_hash`, `hash`) and the legacy hash follows the pinned upstream algorithm exactly:

```
SHA256(prev.encode() + json.dumps({k: row.get(k) for k in _CHAIN_KEYS}, sort_keys=True, default=str).encode())
```

with `json.dumps` defaults (`', '`/`': '` separators, `ensure_ascii=True`) and `prev` starting at `genesis`, chaining in local ingest order. The hashed projection `_CHAIN_KEYS` is the upstream tuple at the pinned revision — `ts, task_id, actor, parent, kind, ac_id, result, why, tokens_in, tokens_out, sha, prev_hash` — so `sha` and `prev_hash` ARE inside the hashed bytes while `id` and `hash` are not. Compatibility `why` is deterministic: `C(envelope).decode("ascii")`, which commits every extension field under the legacy hash too. Legacy fields are stored at append time and never regenerated differently on read.

- Upstream pin: vibeline `ledger.py` at revision `d5d0f425a64906ae1a50c1222314a5420da404d5` (MIT, copyright 2026 ListeningPost). Only the algorithm and the `_CHAIN_KEYS` projection are taken from upstream; every vector value in the fixture is synthetic. Rails reads must use `mode=ro` plus `query_only` (the upstream `connect()` is a writable connection — see the adaptation table in the spec).
- The legacy hash checks local stored order only; the origin hash independently checks each imported stream. A filtered query is not a full-chain verification: report the checked range and trusted head.

## What each frozen file contains

| File | Contract id | Contents |
|---|---|---|
| `event.schema.json` | `rizzstack.rails/1` | Closed envelope: identity/topology fields, kind enum, timestamps, timing quality, authority vocabulary, payload constraints, redaction policy, chain linkage. |
| `payload.schema.json` | `rizzstack.rails-payload/1` | One closed payload schema per core kind (23 kinds). See semantic notes below. |
| `source.schema.json` | `rizzstack.rails-source/1` | Adapter wire objects: descriptor, read-batch request/result, health, Candidate (ledger-assigned fields refused). Caps: limit ≤ 500, batch ≤ 1 MiB, record ≤ 64 KiB. |
| `query.schema.json` | `rizzstack.rails-query/1` + `rizzstack.rails-result/1` | Shared query request (exactly one selector, opaque ids, include allowlist, caps) and the eleven-field result envelope with completeness/integrity. |
| `view.schema.json` | `rizzstack.rails-view/1` | Lane tree with explicit parents, orphan placeholders, per-lane source status, marks as event references with timing honesty, ghost visibility; bounded marks. |
| `http.schema.json` | `rizzstack.rails-http/1` | Route table, closed error-code vocabulary, typed error envelope, append request/response, export page, limits and transport rules. |
| `evidence.schema.json` | `rizzstack.rails-evidence/1` | RETURN companion: aliases and ledger UUIDs, origin heads, imported checkpoints, source coverage and gaps, selected events, revisions, intervention count, verification links; `receiver_decision` is `pending`. |
| `examples.json` | — | Four synthetic chained events: worker `tool.finish`, verifier `PASS`, owner feedback, and a `source.checkpoint` import receipt. |
| `fixtures/hash-vectors.json` | `rizzstack.rails-hash-vectors/1` | Canonicalization, origin-chain and legacy vectors with provenance. |

Note on bundle-style files: `source.schema.json` and `query.schema.json` each bundle several wire objects in one file. The root object is a document, not an instance schema; validate an instance against the `anyOf` branch whose `properties.schema` const matches the instance's `schema` tag. `http.schema.json` carries `routes` and `transport_rules` as document data next to the wire-object schemas.

## Semantic rules frozen here (summary)

- Pair tool calls only by same origin/lane/`call_id`; never by adjacency. `tool.start` outcome is `pending`; `tool.finish` outcome is never `pending` — an interrupted call stays open without a finish, or a real finish records `unknown`/`cancelled` (see TODO T2).
- Verification/acceptance: `PASS` requires nonempty `evidence_refs`; any non-pass verdict requires a nonempty `reason`; `EXPECTED_RED` additionally requires `expected_intent_ref` naming a frozen test intent, not a prose prefix.
- `review.result` with `independent: true` requires a nonempty `basis` describing distinct execution evidence, not a different display name.
- Queue/lease/state events carry `from_state` (nullable for a first observation), `to_state`, `operation_id`, `fencing_epoch`, `code` and a nullable safe `evidence_ref`. `fencing_epoch` is a public nonnegative ordinal, not a capability credential; fencing secrets never enter Rails.
- Usage: `usage_basis` is `delta|cumulative|final`; counters are required but nullable — unknown stays null and is never inferred; the final receipt is recorded once per scope; money calculations stay in the existing usage ledger.
- Feedback/intervention: rating −1|0|1|null with note ≤ 2000 characters; only `intervention`/`both` categories count in intervention reporting; rating never grants action authority.
- `history.superseded` keeps ledger history intact and ghosts only the UI; `source.gap` is explicit missing evidence, never an empty successful source.

## Explicit unresolved items (honest UNKNOWNs)

- **T1 — R00 inputs absent from this snapshot.** The dispatch context says R00 landed (PR #80, merged `b0cd15a`), but this workspace's seed tree contains neither `schemas/rails/fixtures/source-matrix.json` nor `tests/test_rails_feasibility.py` nor `specs/rails-feasibility.md`, and the git history here has a single seed commit. The spec's own section-2 pins were therefore used for provenance. Before the reviewed freeze merge, recheck the R00 outputs at admission and reconcile any observed-path findings into this directory (spec section 9 requires exactly that for R17's leases).
- **T2 — interrupted-call finish semantics.** "Interrupted start remains open/unknown" is encoded as: no `tool.finish` exists until a real conclusion, and a finish that does exist never carries `pending`. If R00's native-log fixture shows interrupted runs emitting a terminal record with outcome `unknown`, this stays compatible; if it emits other outcomes, revise before the reviewed freeze.
- **T3 — provisional minimal shapes.** `lane.open`/`lane.close` (status), `lane.spawn` (`child_lane_id`), `decision.recorded` (`summary`), and `integration.result`/`merge.result` (`status` + `summary` + optional refs) are minimal closed shapes chosen because the spec names the kinds as closed for `/1` without detailing their payloads. They are marked `$comment` "provisional" in `payload.schema.json`. Revise with a recorded rationale if the bundlebees/Hermes fixtures disagree, before dependent dispatch consumes them.
- **T4 — `attempt.state`/`job.state` field set.** Grouped with queue/lease per the spec sentence "queue/lease/state: from_state, to_state, operation_id, fencing_epoch, code and safe evidence_ref". If the action-queue contract (Q2) shows state events without fencing epochs, relax with a recorded rationale rather than fabricating epochs.
- **T5 — freeze-digest ceremony.** The digest above is recorded at this working-tree revision; the "reviewed workflow revision" freeze happens when the coordinator's review merges this branch. The digest must be recomputed and re-recorded if review amends any covered file.

## Test entry point

```
python -m unittest discover -s tests -p test_rails_contract.py
```

The suite is RED-first by construction (committed before the artifacts existed) and validates with a standard-library subset validator; an optional `jsonschema` cross-check runs when the development package is installed.
