# Bee token observability

Draft design for a first-class usage record across the PC launcher, `bees.ps1`, the beekeeper coordinator, bundlebees, and (later) Orbit. This document is the schema the wider dashboard should link to; it is not a second, competing format.

**Schema status: draft v1; freezes when slice 1 lands.**

Decisions already taken (12 November 2026):

- Daily dollar cap is **$5**, **warn only**. Hitting the cap never blocks dispatch.
- Go-routed bees show **both** list-price dollars and Go allowance percent.
- Phoenix is set up **now** as the local dashboard on the Windows bee host, reachable on **loopback only**, with no prompt or response text stored.
- Slices 1–3 run as bees. The bundlebees usage-parse fix is a separate pull request and waits for an explicit yes before merge. Surfacing numbers in Orbit is a later step and also waits for a yes before deploy.

## What exists today

Bees already report a usable token split on each attempt, but it never leaves the per-attempt result file, nothing prices it, and bundlebees silently drops it. The coordinator, not the bees, is where the money goes.

| Field | Launcher | `bees.ps1` | Hermes coordinator | bundlebees | Orbit |
| --- | --- | --- | --- | --- | --- |
| Uncached input | yes | yes | yes | dropped | no |
| Cached read | yes | yes | yes | dropped | no |
| Cache write | no | no | column, often 0 | no | no |
| Output | yes | yes | yes | dropped | no |
| Reasoning | if non-zero | yes | yes | no | no |
| Model | yes | no | yes | no | no |
| Provider / route | implied by model | no | yes | no | no |
| Fallback | yes | no | n/a | no | no |
| 429 / retries | state file only | fail-fast scan | no | no | no |
| Latency | created/updated | no | start/end | duration_s | no |
| Dollar cost | no | no | estimate | field, empty | null |
| Role / project | brief | yes | no | run id | card |
| Card id | no | yes | no | no | yes |
| Aggregate | none | none | per session | per run | none |

Gaps that matter:

- The launcher sends usage as a JSON string with camelCase keys (`inputTokens`, `cachedReadTokens`, …). bundlebees v0.1.1 keeps usage only if it is a dict; main reads `tokens` or `total_tokens` from a dict. Both end up with `tokens: None`.
- No dollar figure for any bee, and no price table in the launcher or `bees.ps1`.
- Cache semantics differ by source. OpenCode's `inputTokens` excludes cached reads; DeepSeek's `prompt_tokens` includes `prompt_cache_hit_tokens`. Summing them naively double-counts. Normalize once, keep the raw block.
- Go's per-response `opencode.allowance` is not captured, so the next monthly-limit 429 cannot be predicted.
- 429 and retry counts are not in the result or any rollup; fallback to DeepSeek is recorded on the attempt but not counted in a ledger.
- Timing is two epoch stamps, with no queued-versus-running split.
- No shared trace or card id joins the coordinator, the work bee, and the verify bee.
- Coordinator spend is invisible to `bees.ps1` and Orbit, though it is about 99% of a recent day's spend.
- Hermes prices DeepSeek at off-peak rates. Peak is Monday–Friday 01:00–04:00 and 06:00–10:00 UTC (8–11 PM and 1–5 AM ET) and is double.
- Orbit workbench metrics currently hard-code `token_usage: null, cost: null`.

### Numbers from 12 November 2026 (ET, off-peak list price)

Estimates use DeepSeek's published off-peak rates. Reasoning is counted as output, not priced twice. A recomputation of the coordinator total matched Hermes's own estimate to four decimals.

| Run | Cached read | Uncached input | Output + reasoning | Est. USD |
| --- | ---: | ---: | ---: | ---: |
| Pilot 3:18 PM | 48,512 | 339 | 689 | 0.00061 |
| Pilot 3:20 PM | 55,552 | 200 | 200 | 0.00032 |
| Work bee 3:43 PM | 44,800 | 235 | 91 | 0.00022 |
| Verify bee 3:50 PM | 49,536 | 140 | 1,029 | 0.00079 |
| Coordinator, last 24 h | 15,634,560 | 688,947 | 135,272 | 0.2314 |

Cache-hit share on the bee attempts was above 99%. See the README for the later 0.1.14 and 0.1.15 pilot timings.

## Best practice (late 2026)

- **OpenTelemetry GenAI conventions** are still Development, not Stable (semantic-conventions-genai, v1.42). Pin the version you emit. Use `gen_ai.usage.input_tokens`, `output_tokens`, `cache_read.input_tokens`, `cache_write.input_tokens`, `reasoning.output_tokens`, plus `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`. **Subset rule:** input includes cached tokens; cache read/write are subsets of input; reasoning is a subset of output. Consumers that sum buckets double-count. Agent spans use `invoke_agent`. Content capture stays off (`NO_CONTENT`). There is no official OTel cost attribute; keep cost in our own namespace.
- **DeepSeek** reports `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens` that sum to `prompt_tokens`. Off-peak / peak per 1M for `deepseek-flash`: cache hit $0.003 / $0.006, miss $0.15 / $0.30, output $0.60 / $1.20.
- **OpenCode Go** limits are dollar allowances per model (5-hour is 20% and weekly 50% of the monthly limit). Each response may report `opencode.allowance`. DeepSeek V4.1 Flash is listed at the same per-token rates with a $100 monthly allowance.
- A missing count stays **unknown, never zero**.
- **Phoenix** is the right local dashboard: one container, SQLite, OTLP, converts `gen_ai.*` on ingest. Langfuse is heavier than this setup needs. When Bifrost later lands in Orbit, turn content logging off and label spans with card and role.

## Canonical usage record

One JSON line per work or verify attempt, and per coordinator session-model. OTel names where they exist; plain `bee.*` / cost fields where they do not. **Every key below is always present.** Unknown numeric usage is `null` with `usage_status` set to `"unknown"` or `"partial"` — never `0` for a missing count.

Join keys: `attempt_id`, `card_id`, `run_id`, `project`, `role`. Shared IDs let a wider dashboard join bees, cards, and projects without defining a second schema.

```json
{
  "schema_version": "bee.usage/v1",
  "key": "attempt:att_example",
  "attempt_id": "att_example",
  "card_id": "t_example",
  "run_id": "pilot-calc-0115",
  "project": "calc",
  "role": "verify",
  "join_complete": true,
  "verify_of": "att_work_example",
  "retry_of": null,
  "ts_start": "2026-11-12T21:04:42Z",
  "ts_end": "2026-11-12T21:05:08Z",
  "duration_s": 26.0,
  "queue_s": 0.0,
  "trace_id": "<32 lowercase hex, or null>",
  "requested_model": "deepseek-v4.1-flash",
  "served_model": "deepseek-flash",
  "served_model_source": "explicit",
  "provider": "deepseek",
  "route": "deepseek",
  "route_source": "explicit",
  "fallback": null,
  "fallback_reason": null,
  "http_429_count": 0,
  "retry_count": 0,
  "error_type": null,
  "stop_reason": "end_turn",
  "tool_calls": 7,
  "usage_status": "known",
  "input_tokens": 49582,
  "cache_read_tokens": 49280,
  "cache_write_tokens": 0,
  "output_tokens": 860,
  "reasoning_tokens": 31,
  "usage_raw": {
    "source": "cua.usage_json",
    "cachedReadTokens": 49280,
    "inputTokens": 302,
    "outputTokens": 829,
    "thoughtTokens": 31,
    "totalTokens": 50442
  },
  "cost_usd_list": 0.0008,
  "cost_status": "estimated",
  "billing_mode": "metered",
  "price_table_version": "deepseek-pricing-2026-09-10",
  "price_period": "off_peak",
  "go_allowance": null,
  "gen_ai.operation.name": "invoke_agent",
  "gen_ai.agent.name": "bee-verify",
  "gen_ai.provider.name": "deepseek",
  "gen_ai.request.model": "deepseek-v4.1-flash",
  "gen_ai.response.model": "deepseek-flash",
  "gen_ai.usage.input_tokens": 49582,
  "gen_ai.usage.cache_read.input_tokens": 49280,
  "gen_ai.usage.cache_write.input_tokens": 0,
  "gen_ai.usage.output_tokens": 860,
  "gen_ai.usage.reasoning.output_tokens": 31,
  "launcher": "0.1.15",
  "harness": "opencode"
}
```

Field rules:

- **Join keys** are always non-null strings. Use `"unknown"` only when nothing can be derived, and then set `join_complete` to false. Coordinator rows use `attempt_id` `coord:<session_id>`, `project` `beekeeper`, and `role` `coordinator`. `role` is `"work"`, `"verify"`, or `"coordinator"`.
- **Normalization from OpenCode:** `input_tokens` = `inputTokens` + `cachedReadTokens`; `cache_read_tokens` = `cachedReadTokens`; `output_tokens` = `outputTokens` + `thoughtTokens`; `reasoning_tokens` = `thoughtTokens`.
- **Normalization from DeepSeek raw:** `input_tokens` = `prompt_tokens`; `cache_read_tokens` = `prompt_cache_hit_tokens`.
- **Route.** `route` is `"go"`, `"deepseek"`, or `"unknown"`. Keep `requested_model` as sent (prefixes kept) and `served_model` as the resolved model without a route prefix. Record `fallback` (`null` or `"deepseek"`) and `fallback_reason`, plus `http_429_count` and `retry_count` (integer, or `null` when the attempt state is unavailable).
- **Cost.** `cost_usd_list` is the list-price estimate (float, or `null`), priced from a versioned table. Store `price_table_version`, `cost_status` (`estimated` / `actual` / `unknown`), `billing_mode`, and `price_period` (`peak` / `off_peak` / `null`).
- **Go allowance.** `go_allowance` is `null` unless `route` is `"go"`. For Go records it is `{ "raw": <opencode.allowance or null>, "pct_used": <float or null>, "pct_source": "opencode.allowance" | "derived_list_price" | null, "allowance_usd": <monthly allowance from prices.json> }`. `pct_used` comes from the provider object when it has a usable fraction or percent; otherwise it is `cost_usd_list / allowance_usd * 100`. UIs show both `cost_usd_list` and `go_allowance.pct_used`.
- **Forbidden fields:** prompt or objective text, completions, tool arguments, file contents, hostnames, URLs, IPs, absolute paths, keys or tokens. Paths, if any, are repo-relative only.

### `prices.json`

Versioned; one entry per provider snapshot, never edited in place.

```json
{
  "deepseek-pricing-2026-09-10": {
    "source": "https://api-docs.deepseek.com/quick_start/pricing/",
    "models": ["deepseek-flash", "deepseek-v4.1-flash", "deepseek-v4-flash"],
    "usd_per_1m": {
      "off_peak": {"cache_hit": 0.003, "cache_miss": 0.15, "output": 0.60},
      "peak":     {"cache_hit": 0.006, "cache_miss": 0.30, "output": 1.20}
    },
    "peak_utc": "Mon-Fri 01:00-04:00, 06:00-10:00 (excl. Chinese public holidays)"
  },
  "opencode-go-2026-11-12": {
    "source": "https://opencode.ai/docs/console/go/",
    "billing_mode": "subscription_allowance",
    "deepseek-v4.1-flash": {
      "usd_per_1m": "same as deepseek-pricing-2026-09-10",
      "monthly_allowance_usd": 100,
      "window_share": {"5h": 0.2, "week": 0.5, "month": 1.0}
    }
  }
}
```

## Storage, rollups, alerts, Phoenix

- **Ledger.** Append-only JSONL at `%USERPROFILE%\.orbit-launcher\usage\usage-YYYY-MM.jsonl`, user-only ACL, hash-chained like bundlebees metrics. This is the source of truth a wider dashboard should read.
- **Rollups.** `usage-daily.json` by day × role × card × project × model × route: tokens per bucket, list-price cost, attempts, 429s, fallbacks, p50/p95 duration, cache-hit share, and Go allowance percent where applicable.
- **Budget alert.** Warn at a **$5 / day** list-price cap. Warn only; never block dispatch. Also warn when the Go 5-hour, weekly, or monthly allowance passes 80%, and when three or more 429s land in an hour. Alerts land in `bees.ps1 usage` / `status`, the beekeeper's reply, and (later) a note on the Orbit card. Nothing external.
- **`bees.ps1 usage [--day|--card]`.** The same rollup in the terminal, with both dollars and Go allowance percent for Go-routed rows.
- **Optional OTLP.** A tailer exports the ledger as `invoke_agent` spans and `gen_ai.client.inference.usage.*` counters. Off by default; `NO_CONTENT`.
- **Phoenix.** One container with SQLite on the Windows bee host, bound to loopback only. No prompt text, completions, tool arguments, hosts, or keys. Data stays on that host.

## Where each piece emits

| Component | Emits | Joins on |
| --- | --- | --- |
| Hermes beekeeper | Coordinator rows read from `session_model_usage` | card id in the session title or task |
| `bees.ps1` | Mints `trace_id` per card, passes `traceparent` in the brief; rollups and alerts | card, run id |
| PC launcher | Writes the record at finish; adds queue time, 429s, retries, fallback, allowance | attempt, `traceparent` |
| Bee sandbox | `TRACEPARENT` env so later spans can join | trace id |
| bundlebees | Parses usage string or camelCase; keeps the full split in metrics | run, attempt |
| Orbit adapter | Copies usage and cost onto the board card; fills workbench metrics | card |

## Rollout

Restart means a launcher idle-swap with backup and rollback, each needing an explicit yes.

| # | Slice | Restart? | Notes |
| --- | --- | --- | --- |
| 1 | `prices.json` plus a ledger script that derives records from existing result files and the beekeeper `state.db`, read-only, with tests | No | Freezes this draft schema. In flight as a bee. |
| 2 | `bees.ps1 usage` rollups, $5/day warn-only cap, Go allowance percent, peak-hour pricing | No | In flight as a bee. |
| 3 | bundlebees: parse string or camelCase usage, carry the full split and cost into metrics | No | Feature-branch PR; wait for an explicit yes before merge. |
| 4 | Launcher 0.1.16: write the record at finish; add queue time, 429s, retries, fallback, `traceparent`, Go allowance if reachable | Yes | Code can land first; the swap waits. |
| 5 | Orbit adapter and workbench metrics show usage | No | Code can land; deploy waits for a yes. |
| 6 | Hermes Desktop pane usage view | No | |
| 7 | Optional OTLP tailer plus Phoenix; Hermes OTLP export for the coordinator | No | Phoenix setup on the Windows host is already approved and should bind loopback only. |
| 8 | When Bifrost lands in Orbit: content logging off, card and role labels, reconcile with the ledger | No | |

Slices 1–3 give per-bee and per-card dollars, coordinator share, and budget warnings without touching the running launcher.

## Sources

- [GenAI client inference spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md)
- [GenAI token metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-token-metrics.md)
- [GenAI attribute registry](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/registry/attributes/gen-ai.md)
- [Usage buckets: additive vs subset (issue 487)](https://github.com/open-telemetry/semantic-conventions-genai/issues/487)
- [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [OpenCode Go plans and limits](https://opencode.ai/docs/console/go/)
- [Phoenix Docker self-hosting](https://arize.com/docs/phoenix/self-hosting/deployment-options/docker)
- [Hermes usage pricing](https://github.com/NousResearch/hermes-agent/blob/main/agent/usage_pricing.py)
- [bundlebees](https://github.com/mojomast/bundlebees)
