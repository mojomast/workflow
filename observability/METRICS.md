# Metrics catalog

Status: **contract** (v1). This file names every metric rizzstack collects or plans to collect, the fact record it is computed from, its unit, the labels it may carry and how long it is kept. Producers and dashboards must use these names. Adding a metric is additive; renaming or relabelling one is a new major version.

Metrics are **queries over fact records**, not separately stored counters. Producers write small append-only facts; the metrics store (stdlib SQLite on the Hermes host) compacts them into fact tables and hourly/daily rollups.

## Fact records

| Record (`schema`) | Schema file | Grain | Producer |
| --- | --- | --- | --- |
| `gen_ai.inference/v1` | `schemas/inference.schema.json` | one model call (one harness step) | worker host, harvested from the harness session storage inside the sandbox at attempt end |
| `gen_ai.tool_call/v1` | `schemas/tool-call.schema.json` | one tool call | worker host (bees); coordinator snapshot (Hermes insights) |
| `resource.sample/v1` | `schemas/resource-sample.schema.json` | one container or host sample, or a per-attempt rollup | worker host sampler (default every 10 s); host samplers |
| `task.outcome/v1` | `schemas/task-outcome.schema.json` | one task at a terminal state | bundlebees task-terminal hook |
| `ci.run/v1` | `schemas/ci-run.schema.json` | one CI job (and shard) | read-only gh reader |
| `bee.usage/v1` (frozen), `bee.usage/v2` | worker-host contract | one attempt | existing usage ledger |
| `agent.lifecycle/v1`, `failure/v1`, `resource.snapshot/v1`, `board.snapshot/v1`, `vcs.snapshot/v1` | this folder | events and snapshots | existing |

Every fact carries the join keys (`attempt_id`, `card_id`, `run_id`, `project`, `role`, and where known `task_id`, `job_id`, `trace_id`). Timestamps are UTC; time-of-day and weekday are derived at query time in the operator's zone.

## Privacy

- Allowlist projection at the producer. Only the fields in the schemas are written; every schema sets `additionalProperties: false`.
- Never written: prompts, completions, reasoning text, tool arguments, tool results, commands, file contents, paths, URLs, hostnames, addresses, keys or tokens.
- Per-request data is harvested from the harness's own session files inside the sandbox; no prompt text ever leaves the sandbox. OpenTelemetry spans from the harness are **not** enabled (they carry prompt text).
- `host_alias` is an operator alias (for example `brrrrrrrr`, `moltussy-1`, `box`), never a hostname.
- Free text anywhere passes through the producer's scrubber. Demo and test data is mock data only.

## Label allowlist

Metric labels (dimensions) come only from these bounded sets. Identifiers (`attempt_id`, `task_id`, SHAs, branch names) are **never** labels; dashboards reach them through exemplars and drill-down.

| Label | Values |
| --- | --- |
| `model` | served model id (bounded by the router's model table) |
| `provider`, `route` | `provider_label` tokens: `opencode`, `go`, `deepseek`, `nous`, `kimi`, `zoo`, `agy`, `free`, others as extensions |
| `role` | `work`, `verify`, `coordinator` |
| `risk_tier` | `low`, `medium`, `high` |
| `model_lane` | `nous`, `go`, `kimi` (low-risk, default, complex) |
| `repo` | allowlisted repos only |
| `outcome` | attempt: lifecycle terminal states; task: `merged`, `abandoned`, `superseded`, `blocked`, `failed` |
| `failure_class` | `failure/v1` classes |
| `tool_name` | harness tool names, `mcp:<server>`, else `other` |
| `phase` | attempt: `queue`, `provision`, `work`, `collect`, `verify`; task: the `task.outcome/v1` phase keys |
| `host_alias` | operator aliases |
| `hour_local`, `weekday_local`, `price_period` | derived at query time |

## Histogram buckets

Following the OpenTelemetry GenAI conventions:

| Metric family | Buckets |
| --- | --- |
| request and attempt durations (s) | 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92, then 300, 900, 1800, 3600 for attempts |
| time to first token (s) | 0.001, 0.005, 0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, then 30, 60 |
| time per output chunk (s) | 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1, 2.5 |
| tokens per request | 1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576 |
| task lead time (s) | 300, 900, 1800, 3600, 7200, 14400, 28800, 86400, 172800, 604800 |

Rollups store count, sum, min, max, p50, p95 and p99 per hour and per day for each label combination.

## Retention

| Tier | Where | Keep |
| --- | --- | --- |
| Raw per-attempt sidecars | worker host data directory | 14 days |
| Ingest ledgers (JSONL) | Hermes host plugin data | 90 days, gzip after 7 |
| SQLite fact tables | Hermes host metrics store | 180 days |
| Hourly rollups | same store | 90 days |
| Daily rollups and task outcomes | same store | forever |
| Resource samples | raw 14 days; 1-minute rollups 180 days | |

## SLOs

Starting targets, to be reset from a two-week baseline. Burn-rate alerts (1 h and 6 h windows) are warn-only and land in the snapshot `alerts` section.

| SLI | Target | Window |
| --- | --- | --- |
| Attempt success, excluding `environmental` failures | >= 85% | 7 d |
| First-pass verify rate | >= 70% | 7 d |
| Low-risk task lead time p50 | <= 4 h | 7 d |
| Time to first token p95, per route | <= 10 s | 1 d |
| Worker host health OK | >= 99% | 30 d |
| Every metrics source fresher than 10 min | >= 99% of samples | 7 d |
| Records priced | >= 98% | 7 d |

## Metric catalog

Status is what is collected as of this contract: `have`, `partial` or `missing`. Names follow the OpenTelemetry GenAI semantic conventions (Development status, pinned to the `semantic-conventions-genai` main branch of November 2026) where one exists, and `rizzstack.*` otherwise.

| Group | Metric | Name | Type | Computed from | Status | View |
| --- | --- | --- | --- | --- | --- | --- |
| Request | Time to first token | `gen_ai.client.inference.time_to_first_chunk` | histogram, s | `gen_ai.inference/v1`: OpenCode part timing harvested in sandbox (hyvv launcher.py result path); AI SDK msToFirstChunk if spans on | missing | Performance |
| Request | Output tokens per second | `rizzstack.inference.output_tokens_per_s` | histogram, tok/s | `gen_ai.inference/v1`: derived: output_tokens / (step end - first chunk) | missing | Performance |
| Request | Request latency | `gen_ai.client.inference.duration` | histogram, s | `gen_ai.inference/v1`: OpenCode step start/finish parts | missing | Performance |
| Request | Time per output chunk | `gen_ai.client.inference.time_per_output_chunk` | histogram, s | `gen_ai.inference/v1`: AI SDK spans, opt-in only | missing | Performance |
| Request | Input tokens per request | `gen_ai.client.inference.operation.input_tokens` | histogram, tok | `gen_ai.inference/v1`: per-step usage (today only attempt totals in bee.usage/v1) | partial | Tokens |
| Request | Output tokens per request | `gen_ai.client.inference.operation.output_tokens` | histogram, tok | `gen_ai.inference/v1`: per-step usage | partial | Tokens |
| Request | Input tokens (total) | `gen_ai.client.inference.usage.input_tokens` | counter, tok | `gen_ai.inference/v1`: per-step usage; `bee.usage` input_tokens per attempt today | partial | Tokens |
| Request | Output tokens (total) | `gen_ai.client.inference.usage.output_tokens` | counter, tok | `gen_ai.inference/v1`: per-step usage; `bee.usage` output_tokens per attempt today | partial | Tokens |
| Request | Cache-read tokens | `gen_ai.client.inference.usage.cache_read.input_tokens` | counter, tok | `gen_ai.inference/v1`: bee.usage/v1 cache_read_tokens (attempt level) | partial | Tokens |
| Request | Reasoning tokens | `gen_ai.client.inference.usage.reasoning.output_tokens` | counter, tok | `gen_ai.inference/v1`: bee.usage/v1 reasoning_tokens (attempt level) | partial | Tokens |
| Request | Cache hit ratio | `rizzstack.inference.cache_hit_ratio` | ratio | `gen_ai.inference/v1`: derived: cache_read / input | missing | Tokens |
| Request | Cost per request | `rizzstack.inference.cost_usd` | counter, USD | `gen_ai.inference/v1`: prices.json repricing in usage_ledger.py; no Nous or Kimi price table | partial | Cost |
| Request | Finish reason | `gen_ai.response.finish_reasons` | label | `gen_ai.inference/v1`: step finish; today stop_reason per attempt | partial | Reliability |
| Request | Context window fill | `rizzstack.inference.context_fill_ratio` | histogram, ratio | `gen_ai.inference/v1`: input tokens / model context size (launcher MODELS table) | missing | Performance |
| Request | Context compactions | `rizzstack.inference.compactions` | counter | `gen_ai.inference/v1`: OpenCode summary/compaction parts | missing | Reliability |
| Provider | HTTP 429s | `rizzstack.provider.http_429` | counter | `gen_ai.inference/v1`, `bee.usage`: hyvv error events; bee.usage/v1 http_429_count | partial | Reliability |
| Provider | Provider errors by class | `rizzstack.provider.errors` | counter by error.type | `gen_ai.inference/v1`, `bee.usage`: hyvv error events, failure/v1 class | partial | Reliability |
| Provider | Fallback hops | `rizzstack.route.fallback_hops` | counter by from, to, reason | `gen_ai.inference/v1`, `bee.usage`: hyvv model_history in receipt; bee.usage/v1 fallback enum only knows deepseek | partial | Reliability |
| Provider | Backoff wait time | `rizzstack.route.backoff_s` | histogram, s | `gen_ai.inference/v1`, `bee.usage`: hyvv backoff_s schedule per model | missing | Reliability |
| Provider | Nous pacing wait | `rizzstack.route.pacing_wait_s` | histogram, s | `gen_ai.inference/v1`, `bee.usage`: hyvv Nous max_active and start_spacing_s | missing | Resources |
| Provider | Quota and allowance | `rizzstack.quota.used_ratio` | gauge by resource | `gen_ai.inference/v1`, `bee.usage`: resource.snapshot/v1, go_allowance, DeepSeek balance, Google Colab CU | partial | Big picture |
| Attempt | Phase durations | `rizzstack.attempt.phase_duration` | histogram, s by phase | `bee.usage`, lifecycle: hyvv events and bundlebees leases; today duration_s and queue_s only | partial | Flow |
| Attempt | Outcome | `rizzstack.attempt.outcome` | counter by outcome | `bee.usage`, lifecycle: agent.lifecycle/v1 and failure/v1 | partial | Reliability |
| Attempt | Model calls per attempt | `gen_ai.invoke_agent.inference_calls` | histogram | `bee.usage`, lifecycle: harvested steps | missing | Performance |
| Attempt | Tool calls per attempt | `gen_ai.invoke_agent.tool_calls` | histogram | `bee.usage`, lifecycle: receipt observed.tool_calls (count only) | partial | Tools |
| Attempt | Tokens per attempt | `rizzstack.attempt.tokens` | histogram, tok | `bee.usage`, lifecycle: bee.usage/v1 via usage_ingest_service.py | have | Tokens |
| Attempt | Cost per attempt | `rizzstack.attempt.cost_usd` | histogram, USD | `bee.usage`, lifecycle: usage_report.py costs.attempts (Go and DeepSeek only) | partial | Cost |
| Attempt | Patch size | `rizzstack.attempt.patch_lines` | histogram, lines | `bee.usage`, lifecycle: receipt patch (files present, line counts not) | partial | Flow |
| Attempt | No-progress time | `rizzstack.attempt.idle_s` | gauge, s | `bee.usage`, lifecycle: heartbeat gaps in hyvv events; stuck_bee_no_progress_s alert | partial | Reliability |
| Task | Lead time (created to merged) | `rizzstack.task.lead_time` | histogram, s | `task.outcome/v1`: bundlebees job + gh; metrics.py plan_to_accepted_s | partial | Flow |
| Task | Phase waterfall | `rizzstack.task.phase_duration` | histogram, s by phase | `task.outcome/v1`: contract, RED, GREEN, verify, review, CI, merge queue | missing | Flow |
| Task | Attempts per accepted task | `rizzstack.task.attempts` | histogram | `task.outcome/v1`: metrics.py summarize() | partial | Reliability |
| Task | Tokens per accepted task | `rizzstack.task.tokens_per_accepted` | gauge, tok | `task.outcome/v1`: metrics.py tokens_per_accepted | have | Tokens |
| Task | Cost per accepted task | `rizzstack.task.cost_usd` | histogram, USD | `task.outcome/v1`: usage_report.py costs.jobs (keyed by card_id) | partial | Cost |
| Task | Wasted tokens and cost | `rizzstack.task.tokens_wasted` | counter by cause | `task.outcome/v1`: attempts not accepted, retry_of chains, fallbacks | missing | Cost |
| Task | First-pass verify rate | `rizzstack.task.first_pass_rate` | ratio | `task.outcome/v1`: metrics.py first_pass_rate | have | Reliability |
| Task | RED then GREEN compliance | `rizzstack.task.tdd_result` | counter by result | `task.outcome/v1`: tdd.py and ACDD evidence | partial | Reliability |
| Task | Review rounds | `rizzstack.task.review_rounds` | histogram | `task.outcome/v1`: reviewers.py, gh PR reviews | missing | Flow |
| Task | Rework within 14 days | `rizzstack.task.rework` | counter | `task.outcome/v1`: rework_metrics.py | have | Reliability |
| Task | Regressions and interventions | `rizzstack.task.regressions` | counter | `task.outcome/v1`: metrics.py summarize() | have | Reliability |
| Task | Blocked time and blocker age | `rizzstack.task.blocked_s` | histogram, s | `task.outcome/v1`: board.snapshot/v1 (source stale since Nov 18) | partial | Flow |
| Task | Throughput | `rizzstack.campaign.tasks_merged` | counter per day | `task.outcome/v1`: campaign_report.py | partial | Big picture |
| Tool | Tool calls by name | `gen_ai.execute_tool (count)` | counter by tool | `gen_ai.tool_call/v1`: bees: count only; coordinator: hermes insights --json | partial | Tools |
| Tool | Tool latency | `gen_ai.execute_tool.duration` | histogram, s | `gen_ai.tool_call/v1`: OpenCode tool part state.time | missing | Tools |
| Tool | Tool errors | `rizzstack.tool.errors` | counter by tool, class | `gen_ai.tool_call/v1`: OpenCode tool part status=error | missing | Tools |
| Tool | Denied tool calls | `rizzstack.tool.denied` | counter | `gen_ai.tool_call/v1`: agy denied_actions; OpenCode permission events | partial | Tools |
| Tool | Skill loads | `rizzstack.skill.loads` | counter by skill | `gen_ai.tool_call/v1`: hermes insights skills | partial | Tools |
| Model | Success rate by model and route | `rizzstack.model.success_ratio` | ratio | joins: join attempt outcome with served_model | partial | Models |
| Model | Accepted changes per dollar | `rizzstack.model.accepted_per_usd` | ratio | joins: join task outcome with cost | missing | Models |
| Model | Quality proxies by model | `rizzstack.model.quality` | ratios | joins: first-pass, review findings, slop-lint delta, rework | missing | Models |
| Model | Fallback rate by model | `rizzstack.model.fallback_ratio` | ratio | joins: model_history | partial | Models |
| Resource | Container memory peak and average | `rizzstack.container.memory` | gauge, bytes | `resource.sample/v1`: Docker stats API or cgroup memory.peak per bee | missing | Resources |
| Resource | Container CPU | `rizzstack.container.cpu_ratio` | gauge, ratio of 2 CPUs | `resource.sample/v1`: Docker stats API | missing | Resources |
| Resource | OOM kills | `rizzstack.container.oom_kills` | counter | `resource.sample/v1`: docker inspect State.OOMKilled | missing | Resources |
| Resource | Sandbox start time | `rizzstack.container.start_s` | histogram, s | `resource.sample/v1`: hyvv start to first event | missing | Resources |
| Resource | Host CPU, RAM, disk, load | `system.* (OTel host metrics)` | gauge | `resource.sample/v1`: orbit-live-telemetry (Linux, not stored); PC not covered | partial | Resources |
| Resource | Concurrency vs cap | `rizzstack.fleet.in_flight` | gauge | `resource.sample/v1`: snapshot fleet section (source stale) | partial | Big picture |
| Flow | CI duration per check and shard | `rizzstack.ci.check_duration` | histogram, s | `ci.run/v1`: gh run and job timings (collector reads names only) | missing | Flow |
| Flow | CI flake rate | `rizzstack.ci.flake_ratio` | ratio | `ci.run/v1`: re-run passed on same SHA | missing | Flow |
| Flow | Merge queue wait | `rizzstack.mq.wait_s` | histogram, s | `ci.run/v1`: merge-queue poller logs | missing | Flow |
| Flow | PR open to merge | `rizzstack.pr.time_to_merge` | histogram, s | `ci.run/v1`: gh pr list --json | missing | Flow |
| Flow | Gate findings | `rizzstack.gate.findings` | counter by gate | `ci.run/v1`: gitleaks, slop-lint, lessons-check reports | partial | Flow |
| Coordinator | Coordinator tokens and cost | `rizzstack.coordinator.tokens` | counter by model, platform | coordinator snapshot: hermes insights --json; hermes-token-stats app | partial | Tokens |
| Coordinator | Gateway latency and errors | `rizzstack.gateway.request_duration` | histogram, s | coordinator snapshot: Hermes gateway logs | missing | Performance |
| Coordinator | Kanban WIP and throughput | `rizzstack.board.wip` | gauge | coordinator snapshot: Hermes kanban (collector cannot read it yet) | missing | Flow |
| Coordinator | Memory recall and writes | `rizzstack.memory.ops` | counter by op | coordinator snapshot: rizzstack.memory/1 vault (MEMORY_ENABLED now on) | missing | Performance |
| Meta | Feed freshness | `rizzstack.obs.source_age_s` | gauge, s by source | collector: snapshot section status and collected_at | partial | Big picture |
| Meta | Collector health | `rizzstack.obs.collect_duration` | histogram, s | collector: collector.py run timing and errors | missing | Big picture |
| Meta | Unpriced and unparsed records | `rizzstack.obs.unknown_records` | counter | collector: usage parse_errors and unknown_cost_records | partial | Big picture |
| Meta | Rails ledger lag | `rizzstack.rails.lag_s` | gauge, s | collector: Rails ledger producer (in progress elsewhere) | missing | Big picture |
