# Rails: 100,000-event offline Linux benchmark

The local-only query initially missed the spec's 500 ms warm p95 target. After a bounded primary-key scan replaced an unnecessary sort, **`query_events` measured 368.038 ms p95 and `query_view_page` 186.972 ms p95**. These measurements establish the result on this guest, for the workload below.

| Shared Python read, serialized to JSON | Before, p95 | After, p95 | Items or marks returned per page (both runs) |
| --- | ---: | ---: | ---: |
| Events | 925.901 ms | 368.038 ms | 50–51 |
| View projection | 1,246.636 ms | 186.972 ms | 154–155 |

**Raw evidence:** [before: reads + long stream run](rails-bench-100k.json), [after: reads + short stream run](rails-bench-100k-local-seek.json). Each series contains all latency samples, output counts, byte counts, guest/runtime configuration, module SHA-256s and RSS measurements. The harness replaces its report atomically; only a `completed` status is a completed run.

## Workload and attribution

* Linux `6.12.113+deb13-cloud-amd64`, x86-64 KVM, AMD EPYC 7742 exposed as 4 vCPUs, 16,777,064,448 bytes guest RAM. `/var/tmp` was on `/dev/sda1` ext4. The guest sees `QEMU HARDDISK` with `rotational=1`; the physical backing medium is **unknown**. Python 3.13.5, SQLite 3.46.1, WAL, page size 4096, reader cache `-2000` KiB, `query_only=1`. This was a shared development guest; other jobs, including some overlapping benchmark phases, can introduce noise.
* Each run builds a fresh 452,161,536-byte SQLite database from 100,000 real, synthetic `tool.finish` appends: 10 interleaved lane/attempt IDs in one job and campaign; 10,000 events per attempt. One writer calls the ledger's regular validation, dedupe and hash path in 200-row fixture transactions. The timing excludes fixture construction. There are **ten represented lanes, one writer**, not ten contending producers.
* Each surface gets ten discarded warm-ups followed by 100 serial timed queries over all ten attempts. `limit=500`, 32 KiB response cap, JSON; each selector walks five pages and then resets. There are no cold-cache resets. Timings include checking selected event hashes, projecting events (including building lanes for the view), page sizing, and serializing the complete result. Nearest-rank p95 = sorted sample 95 of 100. The 32 KiB cap binds before 500 rows for this data. Only the selected page is projected with bounded-context warnings; these timings do not measure full-history reducers.
* The reader's before → after RSS was 25,748 → 33,320 KiB (peak 33,320) for the old query, 25,892 → 33,408 KiB (peak 33,684) for the optimized query. Those are Linux process measurements; database/OS page-cache RAM is not included. Seeding ran in another process.
* `EXPLAIN QUERY PLAN` before: union co-routine → `SCAN arrivals` → `USE TEMP B-TREE FOR ORDER BY`. Even the local-only case filtered the whole ledger before stopping at `LIMIT`. With no import receipts the query now uses `SEARCH event_rows USING INTEGER PRIMARY KEY (rowid>? AND rowid<?)` and stops at the limit. The imported-arrival path and filter/permission checks remain in place; there are no new indexes or data migrations. All 13 query tests passed, including the new regression for a local-only snapshot whose first import commits between pages.

## Stream and resume

The harness starts a private, short-lived R12 loopback HTTP server in its own subprocess with a fresh credential. Each window receives `ready`, appends a probe through the writer API, consumes `invalidate`, then reads the exact event mark back through `/v1/view`. It disconnects, commits a second probe offline, reconnects with the last consumed ID, checks that the cursor advances, and refetches the second mark. The polling interval is the service default (1 s). The sleep between cycles is capped at 10 s. RSS/HWM is sampled from `/proc/<server-pid>/status` after each cycle. Only sample numbers/timings are recorded, not credentials or database paths.

The completed **61.000 s** run exercised six cycles. Append-start → notification p95 was **1,002.448 ms**; append-start → matching HTTP mark **1,005.965 ms**; reconnect-start → matching replayed HTTP mark **5.373 ms**. These are end-to-end server/client measurements with a known event ID. A browser paint, human-visible latency, accumulated 2,000-mark viewport, remote worker, parallel readers, physical SSD, and production coordinator were not measured. SQLite supports sparse selectors and mixed local/imported queries; those perf workloads were **skipped** here. A full 500-item response for these particular rows is **not supported at this wire cap**; increasing the cap to claim one would change the tested contract.

The **30-minute soak completed in 1,800.001 s**. All 164 connected appends and all 164 disconnected appends were observed as matching HTTP marks. With 164 samples per metric, p95 was **1,009.298 ms** from append-start to notification, **1,017.344 ms** from append-start to matching HTTP mark, and **20.737 ms** from reconnect-start to matching replayed HTTP mark. The baseline read process loaded the pre-fix query. The HTTP child was spawned after reads and used the local-seek implementation.

Server RSS started at 25,628 KiB, peaked at an observed 29,492 KiB, and measured 25,440 KiB after the final cycle. Median RSS for consecutive five-minute windows was 28,942, 23,372, 22,224, 22,348, 25,456, and 25,516 KiB. The final ten minutes spanned 704 KiB. No sustained RSS increase was observed over these 164 reconnect cycles; this is process-resident memory on this guest, not a general leak guarantee. The raw per-cycle RSS, HWM, and latency samples are in `rails-bench-100k.json`.

## Reproduce

From `workflow/`, with sibling `bundlebees/` and `orbitdesktop/` checkouts and a local temporary volume with ~1 GiB free:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/bench_rails.py \
  --temp-parent /var/tmp --events 100000 --samples 100 \
  --soak-seconds 1800 --output /var/tmp/rails-bench-new-result.json
```

Use a fresh report filename. `--soak-seconds 61` reproduces the short workload; `0` deliberately skips streaming. The benchmark uses source checkouts (including canonical BundleBees modules in the Orbit child); it is not a packaging or deployment test. The temporary ledger, WAL, and ephemeral credential are cleaned up when the run exits.
