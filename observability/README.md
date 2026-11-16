# Observability record formats

This directory is the agent-agnostic contract for environment observability
records other than LLM token and cost usage. It is Phase 1 of that work:
schemas, examples, documentation, and validation tests. It does not collect
data, draw a dashboard, or define a usage schema.

> **Status: frozen record formats, not a working pipeline.** Nothing here
> collects, stores, or sends anything yet. The collectors, the Orbit
> Observability dashboard, alert delivery, board notes, and the lifecycle
> visualization are all **planned** (see [ROADMAP.md](../ROADMAP.md)). The
> alert thresholds below are versioned defaults for those future consumers.
> They do not fire today.

## Records

| Schema const | File | Purpose |
| --- | --- | --- |
| `agent.lifecycle/v1` | `schemas/lifecycle.schema.json` | Agent or bee start, phase, block, finish, or route change |
| `failure/v1` | `schemas/failure.schema.json` | Classified failure (environmental, regression, rate-limit, auth, unavailable, cancelled, unknown) |
| `vcs.snapshot/v1` | `schemas/vcs-snapshot.schema.json` | Commits, open pull requests, and CI for allowlisted repos |
| `board.snapshot/v1` | `schemas/board-snapshot.schema.json` | Board status counts and blocker age |
| `resource.snapshot/v1` | `schemas/resource-snapshot.schema.json` | Credits, allowances, compute units, in-flight bees, host capacity |
| `rizzstack.observability/snapshot/1` | `schemas/snapshot.schema.json` | One assembled point-in-time view across fleet, usage, pipeline, backlog, ci, failures, health, alerts, and bottlenecks sections, emitted by the read-only collector in `contrib/rizzstack-observability/` |

## Envelope discriminator

Every record names its type as `<name>/v<major>`, so a consumer reading a mixed
JSONL stream can tell records apart. These records carry it in `schema`
(`agent.lifecycle/v1`) and keep `schema_version: "v1"` as a version-only field.
The Hermes Forge usage record is **frozen** as `bee.usage/v1` with its type in
`schema_version` and no `schema` field. To avoid breaking that frozen schema,
ingestion normalizes both shapes with `envelope.record_type()` /
`envelope.normalize()`:

| Record | `schema` | `schema_version` | Discriminator |
| --- | --- | --- | --- |
| this package (lifecycle, failure, vcs, board, resource) and the assembled snapshot | `agent.lifecycle/v1` …; `rizzstack.observability/snapshot/1` for the snapshot | `v1`; absent for the snapshot (the rizzstack.* family carries its major version in the discriminator itself) | `schema` |
| Hermes Forge usage (frozen) | absent | `bee.usage/v1` | `schema_version` |

A record whose two fields contradict each other is refused.

## Stable vocabulary vs provider labels

| Kind | Fields | Rule |
| --- | --- | --- |
| **Stable vocabulary** (closed enums, changing them is a new major version) | `role`, lifecycle `state`, failure `class`, resource `unit` and `status`, VCS `ci_state`, alert `destinations` | Only the listed values validate. |
| **Provider labels** (open, extensible) | lifecycle `source`, lifecycle `route`, failure `fallback_to`, resource `kind` | The listed values are *recognized* (for example `go`, `deepseek`, `hyvv`). Any other lower-case token matching `common.schema.json#/$defs/provider_label` (`^[a-z0-9][a-z0-9._-]{0,63}$`) is a valid extension, such as `openrouter`. URLs, paths, upper case and hostnames are refused. |

Consumers should display unrecognized labels as they are, not drop them.

JSON Schema is draft 2020-12. Shared join-key and timestamp definitions live in
`schemas/common.schema.json`. Examples that validate against these schemas are
in `examples/`.

## The bottlenecks section

The snapshot carries a `bottlenecks` section so a dashboard can show where
work is piling up. It is computed read-only from the records the collector
already reads — no new data source, no second collection pass over anything
the other sections do not already touch.

Per pipeline stage, one row each for `verify`, `review`, `integrate` and
`deploy`:

| Stage | Queue depth counts | Oldest-item age from |
| --- | --- | --- |
| `verify` | job tasks in the `verifying` state | the recorded transition into `verifying`, else the newest attempt timestamp |
| `review` | action-queue features in `ready_for_review` | the newest completion record (attempt or review report) of the linked job |
| `integrate` | job tasks in the `verified` state | the transition into `verified`, else the review-report timestamp, else the newest attempt |
| `deploy` | open pull requests | the pull request `createdAt` reported by the CLI |

Each row also carries dwell-time median and p95 (completed waiting stays,
reconstructed from recorded state transitions), throughput as items
advanced per hour over the last hour and the last day (verify and integrate
count recorded advancing transitions; review and deploy have no record of
completed stays, so their dwell and throughput stay `unknown`), and
WIP versus capacity where a cap exists — the verify stage carries the bees
at work (`wip`) against the shared bee cap (`capacity`, with
`capacity_source` of `bee_cap`).

The `invariant` object carries the reconciliation headline: authorized and
eligible work waiting despite available capacity. `ready` counts queued
features, `waiting_despite_capacity` is decided only when both the ready
count and the bee headroom (`bee_cap` minus bees in flight) are known —
unknown on either side leaves it null, never a confident false. Supporting
counts: `total_outstanding` (non-terminal features, or non-terminal job
tasks when the queue is unreadable), `claimed`, `active_workers`,
`awaiting_verify` / `awaiting_review` / `awaiting_integrate` /
`awaiting_deploy`, `blocked_with_reason` plus `blocked_reasons` (reasons
resolved from recorded gate states, task blockers, or unmet dependencies —
unresolvable ones are not counted), `human_approvals_required` (job
approval gates waiting on a human decision), `last_auto_progress_at` and
its age (newest dispatch, verify, recovery, or recorded state transition;
human interventions do not count), and the worker-completion-to-next-action
median and p95 (gap between a verify event and the next dispatch or
recovery for the same task).

Degradation follows the house rules: every unknown stays null with an
`agg_status` marker (`known`, `partial`, `unknown`, `unavailable`); a
numeric zero appears only when the source was read this run and is
genuinely zero. The section is `live` when any contributing source was read
this run, `stale` when every readable source is older than the freshness
threshold, and `unavailable` (`no_bottleneck_sources`) when none are.

Dwell-time targets per stage are configuration, not constants: the collector
ships defaults (`verify_dwell_target_s` 3600, `review_dwell_target_s`
14400, `integrate_dwell_target_s` 7200, `deploy_dwell_target_s` 86400) and
operators override them like any other threshold key. The section echoes
the effective targets under `thresholds` so the dashboard can draw
threshold lines and color stages (`state`: `ok`, `over` when median or p95
dwell exceeds the target, `unknown` when not observable).

## Alert thresholds

Versioned defaults live in `alerts.defaults.json` (`schema`: `alert.thresholds/v1`).
They were set on 12 November 2026, 4:34 PM America/Toronto:

| Key | Default | Meaning |
| --- | --- | --- |
| `deepseek_balance_below_usd` | `5` | Warn when a DeepSeek balance is below $5 |
| `go_allowance_pct_used` | `80` | Warn when an OpenCode Go key has used 80% of its monthly allowance |
| `go_429_streak` | `5` | Warn after 5 Go HTTP 429 errors in a row |
| `stuck_bee_no_progress_s` | `1800` | Warn when a bee is stuck with no progress for 30 minutes |
| `blocker_age_s` | `14400` | Warn when a board blocker is older than 4 hours |
| `disk_free_pct` | `10` | Warn when free disk space is below 10% |
| `bees_in_flight_warn_at` | `12` | Warn when bees in flight reach the shared cap of 12 |
| `daily_model_spend_above_usd` | `10` | Warn when daily model spend is above $10 |

Destinations are the Orbit dashboard and a board note only. At the bee cap,
the v1 action is `warn` (not pause). The $10/day spend threshold supersedes
a Hermes Forge draft of $5/day.

Operators override individual keys with an `alert.thresholds.override/v1`
document (see `examples/alerts.override.json`). Omitted keys keep the
defaults. Load and merge with the stdlib helper:

```python
from observability.alerts import load_thresholds
thresholds = load_thresholds("/path/to/alerts.override.json")  # or None for defaults
```

Schemas: `schemas/alert-thresholds.schema.json` and
`schemas/alert-thresholds-override.schema.json`. Collectors and the dashboard
are still later phases; this is the contract only.

## Hermes Forge usage record (not defined here)

Token, cost, route totals, 429 and retry counts, Go allowance, and list-price
dollars belong to the Hermes Forge usage record. The draft is
[`contrib/hermes-bees/OBSERVABILITY.md`](https://github.com/mojomast/workflow/blob/contrib/hermes-bees/contrib/hermes-bees/OBSERVABILITY.md)
on [workflow pull request #7](https://github.com/mojomast/workflow/pull/7).
Its identifier is `schema_version: "bee.usage/v1"`, now frozen by Hermes
Forge (`pc-launcher/usage-schema.v1.json` and `usage_ledger.py` on orbitdesktop
`feat/bee-usage-observability`, `1617ae0`). Its `route` is `go`, `deepseek` or
`unknown`. See the envelope table above for how it joins these records. The
ledger path is Hermes Forge's to publish and must not be guessed.

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
  agents, the Hermes host, hyvv (the worker-host runtime that owns the
  versioned `/v1` worker API), and box or PC disk, CPU, and RAM. A later
  version can add the Temple of Hermes BBS.

hyvv (`mojomast/hyvv`) is the fourth layer next to this workflow,
bundlebees, and Orbit. Hermes Forge is building it. It owns the versioned
`/v1` worker API contract. Lifecycle `source` and example `platform` values
use `hyvv` for that worker-host; `launcher` remains accepted as a
transitional alias for the current 0.1.15 line.

The official dashboard is a new Orbit view. That work is not in this
repository.
