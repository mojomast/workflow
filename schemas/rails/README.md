# Rails draft contracts

These files accompany [the implementation spec](../../specs/rizzstack-rails-spec.md). They are draft review artifacts, not frozen production protocols. R01 owns kind-specific closed payload schemas, source/query/view/HTTP/evidence schemas, semantic validation and golden vectors before dependent dispatch. `examples.json` includes synthetic chained events; no live transcripts or host identifiers are included.

Schema checks cannot establish secret absence, producer authority, canonical byte identity, idempotency, source completeness or hash integrity. Those require the semantic checks in the specification. Runtime validation must be standard-library-only; the repository's existing development JSON Schema tooling may validate fixtures.

