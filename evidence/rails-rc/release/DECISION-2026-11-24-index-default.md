# Release decision addendum (2026-11-24): attempt index is the default

**Status: HOLD (unchanged).** This addendum does not change the release disposition in [`DECISION.md`](DECISION.md). It supersedes only that document's **"opt-in index"** wording, which was accurate when it was written at the four draft heads but is stale after BundleBees #84.

## What changed

BundleBees #84 merged on 2026-11-17. It creates the `rails_local_attempt_scan` index when a ledger is created, so the index is the default for new ledgers, and it adds a directory migration so existing ledgers can be moved onto the same layout. [`ROADMAP.md`](../../../ROADMAP.md) records this at lines 58–63 ("made the index the default for new ledgers"; "Existing ledgers need the directory migration from #84"). The index definition is `CREATE INDEX rails_local_attempt_scan ON event_rows (...)` in [`performance/index-cost.json`](../performance/index-cost.json), and the indexed reports show the planner selecting it (`USING INDEX rails_local_attempt_scan`) in [`release/http-indexed.json`](http-indexed.json) and [`performance/indexed.json`](../performance/indexed.json).

## Indexed performance is borderline, not qualified

The recorded indexed events p95 values are all near the 500 ms target, and two of the four exceed it. Rounded to one decimal, as recorded:

| Indexed report | Events p95 |
|---|---:|
| [`release/http-indexed.json`](http-indexed.json) | 499.7 ms |
| [`performance/indexed-100.json`](../performance/indexed-100.json) | 470.6 ms |
| [`performance/indexed.json`](../performance/indexed.json) | 631.5 ms |
| [`performance/coordinator-replay-100.json`](../performance/coordinator-replay-100.json) | 670.7 ms |

Against the **500 ms p95** target, 499.7 ms leaves only 0.284 ms of headroom and 631.5/670.7 ms miss it. Indexed runs are therefore **borderline, not qualified**. Being the default configuration for new ledgers does not convert any of these runs into a deployment-wide pass; the dated figures in `DECISION.md` keep their original meaning.

## What remains open

- **Memory is still unqualified.** The 30-minute (1,800 s) indexed soak in [`soak.json`](soak.json) completed with `config.attempt_index` set to `true`, but Node RSS and Chromium PSS rose across the six windows; [`DECISION.md`](DECISION.md) keeps memory unqualified.
- **Multi-host transport is untested.** Neither [`DECISION.md`](DECISION.md) nor [`ROADMAP.md`](../../../ROADMAP.md) (line 63) records a multi-machine run.
- **The live ledger's index state is unconfirmed.** No committed record in this repository names the live Hermes-host ledger or says whether the #84 directory migration was applied to it. Treat that state as unknown.

## Next steps

1. **P1 — pagination:** three arms × 5 runs on throwaway local infrastructure.
2. **P2 — soak:** repeat the soak with a fixed-history control to separate retained history or caches from a leak.
3. **P3 — multi-machine:** exercise transport across more than one machine.

The release disposition remains **HOLD** until these clear.
