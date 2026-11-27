# Observability handoff: feat(observability): SQLite metrics store, v2-aware collector, views and SLOs

Plan-only track. The PR body has the same text.

## Handoff for bees

**Goal:** A stdlib SQLite store on moltussy-1 that ingests every fact record (gen_ai.inference/v1, gen_ai.tool_call/v1, resource.sample/v1, task.outcome/v1, ci.run/v1, bee.usage/v1+v2). It provides the rollup views behind the METRICS.md catalog, applies the retention defaults, and evaluates the starting SLOs.

### Kyle's decisions that apply (2026-11-24)
- Metrics store: stdlib SQLite on moltussy-1 (no new database service).
- `bee.usage/v2` with open provider labels (`provider_label`), plus Nous and Kimi price tables. `bee.usage/v1` stays frozen.
- Per-request data comes from the OpenCode session harvest only. No OTel spans. Prompt text never leaves the sandbox: counts, timings and bounded labels only.
- Retention, starting SLO targets and 10 s container sampling: the defaults in workflow `observability/METRICS.md`.
- `rizzstack.observability/1` is renamed to `rizzstack.observability/chat-card/1` with a compat note (orbit-control-plane#8, merged).
- Weekly digest: a Hive card plus a Hermes chat message.
- Phoenix and VictoriaMetrics: not now. Ask Kyle later.
- Lanes: Kimi for complex slices, Nous for low-risk ones, OpenCode Go by default. Never temperature 0. The Kimi and Nous providers must keep working.
- Process: one branch and PR per track. Contracts before code, approved RED tests before GREEN. Run gitleaks before every push. No force-push. Merge when green. Never weaken a gate or the sandbox. Mock data only in fixtures and demos.

### Done
- Contracts, retention defaults, SLO targets and the 70-row metric catalog in `observability/METRICS.md` (#153). Plan only so far.

### Remaining steps
- [ ] Collector: accept `bee.usage/v2` next to v1 (approved RED test first).
- [ ] Coordinator: freeze a DDL contract (`observability/store/schema.sql`) and approved tests on a temp db.
- [ ] Bee: `observability/store.py` with idempotent ingest (natural keys), WAL mode and retention compaction (raw rows to daily rollups, per the METRICS.md defaults).
- [ ] Bee: SQL views for each catalog row marked have or partial, and p50/p95 histograms using the METRICS.md buckets.
- [ ] Bee: `observability/slo.py` computes the SLO burn from the views and emits JSON for the digest.
- [ ] Verify, run gitleaks and merge. **Installing or restarting the collector/compactor on moltussy-1 needs Kyle's yes.**

### Acceptance criteria
- Every record type round-trips through ingest, and re-ingest is a no-op.
- Retention compaction keeps the totals.
- Views match the hand-computed mock fixtures. No content fields exist in the DDL.

### Test commands
```
timeout 900 python3 -m pytest -q -p no:cacheprovider observability/tests
timeout 1800 python3 -m pytest -q -p no:cacheprovider tests
```

### Dependency order
1. mojomast/workflow#153: record contracts + METRICS.md (**merged**)
2. mojomast/orbit-control-plane#8: chat-card/1 rename (**merged**)
3. mojomast/hyvv#51: bee.usage/v2 contract (open, auto-merge on)
4. hyvv `bees/obs-harvest`: OpenCode session harvest (needs 1)
5. hyvv `bees/obs-resources`: container resource sampler (needs 1)
6. orbitdesktop `bees/usage-v2`: ledger emits/reads bee.usage/v2 + Nous/Kimi prices (needs 3)
7. workflow `bees/ci-runs`: ci.run/v1 builder (needs 1)
8. hyvv `bees/obs-launcher-wiring`: call harvest + sampler from the launcher, metrics outbox (needs 4, 5)
9. workflow `bees/obs-store`: SQLite store, collector v2 accept, views, SLOs (needs 1, 3, 6, 7, 8)
10. bundlebees `bees/obs-task-outcome`: task.outcome/v1 + insights (needs 1; feeds 9)
11. orbit-control-plane `bees/obs-dashboards-digest`: Orbit tabs, Hive Big picture, weekly digest (needs 9, 10)

### Needs Kyle's typed yes (stop and ask, do not do)
- Any tag, release or deploy: the hyvv launcher on brrrrrrrr, the orbitdesktop ingest service, the moltussy-1 collector/compactor, the orbit-control-plane deploy (#8 only takes effect after it), and installing the Orbit app.
- Any restart of Orbit, moltussy-1 services or the launcher.
- Live canaries: a real Nous or Kimi bee run to check harvest end-to-end.
- Any deletion, and any Google Colab spend.
- Phoenix or VictoriaMetrics (deferred: ask later).

