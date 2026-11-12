# Observability record formats

This directory is the agent-agnostic contract for environment observability
records other than LLM token and cost usage. It is Phase 1 of that work:
schemas, examples, documentation, and validation tests. It does not collect
data, draw a dashboard, or define a usage schema.

## Records

| Schema const | File | Purpose |
| --- | --- | --- |
| `agent.lifecycle/v1` | `schemas/lifecycle.schema.json` | Agent or bee start, phase, block, finish, or route change |
| `failure/v1` | `schemas/failure.schema.json` | Classified failure (environmental, regression, rate-limit, auth, unavailable, cancelled, unknown) |
| `vcs.snapshot/v1` | `schemas/vcs-snapshot.schema.json` | Commits, open pull requests, and CI for allowlisted repos |
| `board.snapshot/v1` | `schemas/board-snapshot.schema.json` | Board status counts and blocker age |
| `resource.snapshot/v1` | `schemas/resource-snapshot.schema.json` | Credits, allowances, compute units, in-flight bees, host capacity |

JSON Schema is draft 2020-12. Shared join-key and timestamp definitions live in
`schemas/common.schema.json`. Examples that validate against these schemas are
in `examples/`.

## Hermes Forge usage record (not defined here)

Token, cost, route totals, 429 and retry counts, Go allowance, and list-price
dollars belong to the Hermes Forge usage record. The draft is
[`contrib/hermes-bees/OBSERVABILITY.md`](https://github.com/mojomast/workflow/blob/contrib/hermes-bees/contrib/hermes-bees/OBSERVABILITY.md)
on [workflow pull request #7](https://github.com/mojomast/workflow/pull/7).
The draft identifier is `schema_version: "bee.usage/v1"`. It freezes when
Hermes Forge slice 1 lands; final field names come with that freeze notice.
The ledger path is published then, and must not be guessed.

Join keys, on both that usage record and these records, are `attempt_id`,
`card_id`, `run_id`, `project`, and `role` (`work`, `verify`, or
`coordinator`). On a usage record, missing numeric usage is `null` with
`usage_status` of `"unknown"` or `"partial"`, never `0`. On these snapshot
records, join keys may be `null` when the snapshot is not about a single
attempt.

This package does not ship a usage schema, and collectors must not invent a
second one. Planned usage fields (route, requested and served model, fallback
and reason, HTTP 429 and retry counts, Go allowance, list-price cost and
price table version) are described only in the Hermes Forge document.

## Privacy

Records are JSONL-ready objects. Free text is already-scrubbed and length
limited. Do not put secrets, keys, tokens, environment-file contents, patches,
prompts, private URLs, IP addresses, or hostnames in a record. Repository
fields are `owner/name` slugs only. OpenCode Go keys are two rows with local
labels such as `go-1` and `go-2`, never key material.

Unknown resource values use `status: "unavailable"` and `null` for `value`
and `remaining`. A genuine zero (for example, no Cursor cloud agents in
flight) is allowed only with `status: "ok"`.

## Tests

The validator in `validate.py` is stdlib-only so this folder can be checked
without adding a dependency or editing `.github/` workflows.

```bash
python3 -m unittest discover -s observability/tests -v
```

Run it from the repository root. Until a later change adds a CI job (out of
scope for this pull request, which does not edit `.github/`), this suite is
run locally and in review.

## Defaults for one operator, options for every operator

Nothing in the schemas hard-codes a repository list or a host. Documentation
and examples may show one operator's current defaults:

- Tracked repositories: `mojomast/workflow`, `mojomast/bundlebees`,
  `mojomast/orbitdesktop`. For other operators, the set is user-managed and
  belongs in Orbit onboarding, including an optional connect-GitHub step
  (device-flow or a locally stored token, never logged).
- Shared bee cap: 12.
- Version 1 resource kinds include DeepSeek credit, both OpenCode Go
  allowances, Google Colab compute units, Grok Bot usage, Cursor cloud
  agents, the Hermes host, and box or PC disk, CPU, and RAM. A later version
  can add the Temple of Hermes BBS.

The official dashboard is a new Orbit view. That work is not in this
repository.
