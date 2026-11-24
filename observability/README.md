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
| `gen_ai.inference/v1` | `schemas/inference.schema.json` | One model call inside a bee attempt: timings (TTFT, duration, output tok/s), token counts, route, cost. See [METRICS.md](METRICS.md) |
| `gen_ai.tool_call/v1` | `schemas/tool-call.schema.json` | One tool call: bounded tool name, duration, status. No arguments or results |
| `resource.sample/v1` | `schemas/resource-sample.schema.json` | Container or host resource sample (memory, CPU, OOM) or a per-attempt rollup |
| `task.outcome/v1` | `schemas/task-outcome.schema.json` | One finished task: phase timestamps, attempts, tokens and cost incl. wasted, outcome |
| `ci.run/v1` | `schemas/ci-run.schema.json` | One CI job and shard: queue and run time, conclusion, flake flag |
| `rizzstack.observability/snapshot/1` | `schemas/snapshot.schema.json` | One assembled point-in-time view across fleet, usage, pipeline, backlog, ci, failures, health, alerts, and bottlenecks sections, emitted by the read-only collector in `contrib/rizzstack-observability/` |

## Envelope discriminator

Most records name their type as `<name>/v<major>`, so a consumer reading a mixed
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

A record whose two fields contradict each other is refused. The assembled
snapshot keeps its published discriminator verbatim and has no `schema_version`.

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
work is piling up. It is computed read-only from records in the plugin state
directory (job documents, the feature queue file, the live claim records,
the recorded approval decisions, verify results, scheduler metrics) and from
the fleet and pull-request sections the collector already reads — no new
external data source. Every metric reads the record shapes the producers
actually write: job documents are stored as HMAC envelopes
(`{"body": {...}, "mac": ...}`, `job.py` `_seal`) and are unwrapped
read-only and keylessly — the body is parsed as the document and the MAC is
**not** verified here, because a read-only dashboard holds no state key; the
reconciler, which holds the key, is the verifier of record. An envelope
whose body is not an object counts as an unreadable job (an owner message),
never a silent zero, and a record that cannot yield a timing value degrades
to null with a status marker, never to a fabricated zero.

Under the `rizzstack.observability/snapshot/1` discriminator the section,
and the ci pull-request `created_at` field, are optional rather than
required: both are new in this revision, no document emitted before this
change contains them, and snapshots emitted earlier must keep validating
without a discriminator bump. No old consumer expects the section, so
optionality is the compatible path; the collector always emits both when it
runs.

Per pipeline stage, one row each for `verify`, `review`, `integrate` and
`deploy`:

| Stage | Queue depth counts | Oldest-item age from |
| --- | --- | --- |
| `verify` | job tasks in the `verifying` state | the recorded transition into `verifying`, else the scheduler dispatch record for the task's attempt |
| `review` | action-queue features in `ready_for_review` | the newest passing verify record among the linked job's attempts |
| `integrate` | job tasks in the `verified` or `integrating` states | the recorded transition into `verified`, else the task's verify record, else the dispatch record |
| `deploy` | open pull requests | the pull request `createdAt` reported by the CLI |

Each row also carries dwell-time median and p95 over completed stays
reconstructed from recorded job transitions: a stay opens on a transition
into the stage and closes on the next transition out of the stage's states,
and a recorded transition to a state past the stage counts as an advance
even when the stage entry was never recorded (once per passage). Throughput
is items advanced per hour over the last hour and the last day, for verify
and integrate. Throughput reads `known` only when job documents were read
and at least one recorded transition parsed; with tasks present and no
parsed transition it reads `unknown` — unknown is never folded into 0.0.
Review and deploy have no record of completed stays, so their dwell and
throughput stay `unknown`; the only timing observable there is
`oldest_item_age_s`, and the row's `state` still reflects dwell against the
target, so it stays `unknown` for those stages too — a dashboard that wants
an age-based signal reads `oldest_item_age_s` directly. The verify stage
carries the bees at work (`wip`) against the shared bee cap (`capacity`,
with `capacity_source` of `bee_cap`).

The `invariant` object mirrors the coordinator reconciler's invariant
(`bundlebees_plugin/reconcile.py`), not a parallel formula, with one
declared exception below. `ready` counts only eligible queue items: status
`queued`, the feature itself not done, and every recorded dependency done —
a dependency is done when its linked job is accepted, which the queue checks
against the tasks' verify records and an accepted integration wave, never
against status strings. `claimed` counts job tasks in the `dispatching` and
`dispatched` states, exactly the reconciler's source;
`active_workers` counts job tasks in the `running` state, as the reconciler
counts them; `awaiting_verify` counts `verifying` tasks, and
`awaiting_integrate` counts `verified` and `integrating` tasks. Live claim
records (`queue/<feature_id>.json`, states claimed or running) are reported
separately as `active_claims` — the reconciler's `features.active_claims` —
and are never added to the in-flight task they are the claim of: a running
claim and its running task are one unit of work, and stale claim records
left by finished work must not pin `available` to zero. Then
`in_use` is claimed plus active workers plus awaiting verify, `available`
is the work scheduler's max-active (4) minus `in_use` floored at zero — the
scheduler's slot budget, not the shared bee cap — and the three numbers are
reported under `capacity`. `owner_messages` counts pending approvals plus
blocked items. A pending approval is a declared gate with no recorded
decision file: a gate stays in the `waiting` state by design even after its
decision is recorded (see the recovery protocol), so the recorded file is
what counts and a job with a recorded grant counts zero pending approvals.
Blocked items are rejected, failed or superseded tasks, jobs whose
integration wave is terminal, accepted jobs whose acceptance evidence is
incomplete (the queue's own acceptance check, so a finished-looking job
cannot pass silently), tasks in an unrecognized state, unreadable job
documents, and an unreadable claim store — the store is refused whole, one
message, exactly as `QueueStore.active()` refuses it. Blocked queue
features are **not** owner messages: an approval- or task-caused block is
already counted at its source, and a dependency-blocked feature advances
when its dependency completes, exactly as the reconciler treats it. Two
reconciler blocked-causes are outside this reader's sources and therefore
absent here, declared rather than hidden: campaign-checkpoint blockers and
an unreadable scheduler queue (`coordinator/work.json`); the reconciler's
report remains the complete count. The headline
`waiting_despite_capacity` is true exactly when the reconciler would expect
advancement — `ready` > 0, `available` > 0, and `owner_messages` == 0 —
false when the invariant genuinely does not hold, and null when any input
it needs is unknown; unknown is never resolved into a confident answer.
Supporting counts: `total_outstanding` (non-terminal features, or
non-terminal job tasks when the queue is unreadable), `awaiting_review`,
`awaiting_deploy`, `blocked_with_reason` plus `blocked_reasons`,
`last_auto_progress_at` and its age (the newest recorded transition whose
destination is an automatic forward state, or a dispatch, verify, or
integrate scheduler event; human interventions and recovery decisions do
not count), and the worker-completion-to-next-action median and p95 (the
gap between a recorded `->verifying` transition and the next recorded event
of the same job, in document order — the reconciler's own latency pair).

Degradation follows the house rules: every unknown stays null with an
`agg_status` marker (`known`, `partial`, `unknown`, `unavailable`); a
numeric zero appears only when the source was read this run and is
genuinely zero. The section is `live` when any contributing source was read
this run, `stale` when every readable source is older than the freshness
threshold, and `unavailable` (`no_bottleneck_sources`) when none are.

Dwell-time targets per stage are configuration, not constants: the
collector ships defaults (`verify_dwell_target_s` 3600,
`review_dwell_target_s` 14400, `integrate_dwell_target_s` 7200,
`deploy_dwell_target_s` 86400) and accepts overrides through its own
threshold configuration. The versioned alert-thresholds contract does not
accept these dwell keys yet — its thresholds object is closed, so an
override document containing a dwell target is refused by that contract
today; extending the versioned threshold schema is recorded as pending
work, and until then the override lives only in the collector's own
configuration. The section echoes the effective targets under `thresholds`
so the dashboard can draw threshold lines and color stages (`state`: `ok`,
`over` when median or p95 dwell exceeds the target, `unknown` when not
observable).

### Pending follow-ups from the review of this section

- Extend the versioned alert-thresholds schema to accept the per-stage
  dwell targets (the threshold schema files are outside this change; until
  then the operator override is accepted only by the collector's own
  configuration, as stated above).
- The collector's own README under `contrib/rizzstack-observability/` does
  not document the bottlenecks section yet; updating it is a follow-up.

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
