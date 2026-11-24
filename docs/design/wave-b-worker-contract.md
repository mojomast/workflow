# Wave B design: one worker contract

Status: **proposed** (design only; no code changes). Source: the Nov 24 next-level review, wave B
([rizzstack #17](https://github.com/mojomast/rizzstack/pull/17)). Plan: rizzstack `NEXT.md`.

## Problem

A bee brief is described three times and an attempt's state four times, and they disagree:

| Thing | Where it is defined today | Notes |
|---|---|---|
| Brief | bundlebees `bundlebees_plugin/schemas/brief.schema.json` (`additionalProperties: true`) | `risk`, `tests`, `deps`, `wave`, `contract` |
| Brief | hyvv `contract/v1/openapi.yaml` attempt request + `launcher.validate_brief` | drops fields it does not know, silently |
| Brief | orbitdesktop local-workers route | its own shape |
| Attempt state | hyvv `launcher.py` (`queued`, `provisioning`, `running`, `backoff`, `rate_limited`, `succeeded`, `failed`, `cancelled`) | `TERMINAL` at `launcher.py:41` |
| Attempt state | bundlebees `tools.py:65-69` (`running`/`working`/`active`/`started`; `interrupted` as terminal) | accepts states hyvv never emits |
| Attempt state | orbitdesktop `server/local-workers.mjs:63` and `local-worker-artifact.mjs:16-17` (`launcher_queued`, `dispatching`, `starting`, `reconnecting`, `outcome_unknown`, `cancel_requested`, `accepted`, `rejected`) | adds its own states |
| bee-landed ids | the `rizstack.dev` typo dataschema in hyvv; the schema `$id` in workflow | fixed by wave A slices A12a and HY-3 |

Also found while checking: hyvv `contract/v1/openapi.yaml` does not parse as YAML on `main`
(line 347, a plain scalar that starts with a backtick). Nothing in CI parses the file, so it was
not caught; any OpenAPI or YAML tool fails to load it. Wave B's first slice should fix that, with a parse test in hyvv CI.

## Decision (proposed)

1. Publish two schemas in this repo, next to the other cross-repo contracts:
   - `schemas/rizzstack-brief.schema.json`: `rizzstack.brief/1`
   - `schemas/rizzstack-attempt.schema.json`: `rizzstack.attempt/1`, with one state enum
   Both are added as drafts in this PR (`"x-status": "draft"`). Nothing validates against them yet.
2. One state enum: `queued, provisioning, running, backoff, succeeded, failed, cancelled`, plus a
   `reason` for `backoff` (`rate_limited`, `transient`) and for `failed`. Orbit's UI-only states
   (`dispatching`, `reconnecting`, `outcome_unknown`, `cancel_requested`) become a separate
   `client_state` the UI owns, not attempt states. `accepted`/`rejected` are verify outcomes, not
   attempt states.
3. Generate validators from the schemas: Python (`jsonschema`, vendored like `rizzstack_rails`) and
   JS (a generated standalone validator, no runtime dependency).
4. hyvv refuses fields it would drop: an unknown top-level brief field is a 400 `brief_field_unknown`
   once a project opts in, and always after the migration window.
5. Unify the bee-landed ids on the workflow schema `$id` (A12a and HY-3 start this).

## Migration note

| Step | Change | Compatibility |
|---|---|---|
| B1 | fix the openapi.yaml parse error; add a parse test | none |
| B2 | land the draft schemas (this PR) | none: not referenced |
| B3 | bundlebees validates outgoing briefs against `rizzstack.brief/1` in **report-only** mode; logs `brief_schema_drift` | none |
| B4 | hyvv accepts `rizzstack.brief/1`; maps old field names; reports unknown fields in the attempt record | additive to /v1 |
| B5 | Orbit and the control plane send `rizzstack.brief/1` and read `rizzstack.attempt/1` states; Orbit keeps `client_state` | Orbit release |
| B6 | after two weeks of zero drift reports: unknown fields become 400 in hyvv; report-only becomes enforce in bundlebees | owner date |

Exit (from the review): the three brief schemas become one, and all four dispatch clients
(bundlebees, Orbit, control plane, bee-ci) validate against it.

## Decisions for the owner

- The B6 enforcement date.
- Whether `rizzstack.attempt/1` is a /v2 of hyvv's API or an additive /v1 change (recommended:
  additive /v1 with a `schema` field, because the state names already match hyvv's).
