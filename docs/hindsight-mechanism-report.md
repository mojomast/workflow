# Hindsight Mechanism Report (Phase 2 of the Hindsight research brief)

**Pinned upstream revision:** `b92ceb180e349a456d2b5454575067b6ff0f6306` (research checkout:
`hindsight-research`; `git describe` = `v1.2.1-28-gb92ceb180`, i.e. 28 commits after the `v1.2.1`
tag, whose tree is `b5e6d3d2b2a841d0615e853c8a9f691cfb623874`). Package `hindsight-api-slim`
declares `version = "1.2.1"` and `license = "MIT"`
(`hindsight-api-slim/pyproject.toml:5-7`). All `file:line` citations below are against that
revision. Paths are relative to the repo root unless they start with `hindsight-api-slim/…`.

**Method note (code over docs).** Every claim below is sourced from the pinned code with a
`file:line` citation. Where the marketing/docs story and the code disagree, the discrepancy is
called out in [§11](#11-code-vs-docs-claims). The report never repeats a docs claim without a code
anchor.

---

## 1. Architecture map

Four layers in `hindsight-api-slim/hindsight_api`:

1. **Ingestion ("retain")** — `engine/retain/` (orchestrator, fact extraction, entity processing,
   link creation, memory budget) + the Postgres store statements in `engine/memories/pg/retain.py`
   and `engine/memories/pg/entity_resolver.py`.
2. **Consolidation** — `engine/consolidation/{consolidator,triage,prompts}.py` + store statements
   in `engine/memories/pg/consolidation.py`.
3. **Retrieval ("recall")** — `engine/search/*` (retrieval, fusion, reranking, decision reranker,
   temporal extraction) over the store's SQL arms in `engine/memories/pg/recall.py` and the graph
   arm in `engine/memories/pg/link_expansion.py`; the recall entry point is
   `MemoryEngine.recall_async` (`engine/memory_engine.py:9573`).
4. **Reflection** — `engine/reflect/{agent,delta_ops,retractions,observations}.py` plus the
   mental-model refresh executor `MemoryEngine._execute_mental_model_refresh`
   (`engine/memory_engine.py:18511`).

Cross-cutting: a DB-backed task queue polled by `worker/` (`worker/poller.py`), typed decision-model
calls (`engine/decision_model.py`), per-operation LLM concurrency buckets (`engine/llm_wrapper.py`),
multi-tenant schemas (`extensions/tenant.py`), and OpenTelemetry/Prometheus + a per-bank
`llm_requests` cost ledger (`metrics.py:28-32`, `engine/llm_trace.py:1-58`).

---

## 2. Ingestion (retain): how a document becomes a fact graph

### 2.1 Chunking → atomic-fact extraction (LLM)

- Documents are chunked by `iter_chunks` (`engine/retain/fact_extraction.py:776-841`): JSON
  conversation arrays are split at turn boundaries (`:817-820`), JSONL logs at line boundaries
  (`:836-838`), plain text by recursive sentence-aware splitting (`:841`); idempotency is a stated
  contract — re-chunking a returned chunk yields itself (`:860-863`). Default chunk budget is
  3000 chars (`config.py:1972`, `DEFAULT_RETAIN_CHUNK_SIZE`).
- The extraction prompt is prebuilt once per bank (`ExtractionPrompt`,
  `fact_extraction.py:1586-1748`) to avoid per-chunk `create_model()` cost (`:1587-1591`). Four
  modes share one base prompt: concise (default), verbose, verbatim, custom
  (`:1629-1640`). The base prompt (`_BASE_FACT_EXTRACTION_PROMPT`, `:1083-1143`) mandates the
  5-dimension fact shape `what/when/where/who/why` (`:1091-1095`), coreference resolution
  (`:1103-1105`), entity arrays as plain strings (`:1137-1143`), and selectivity rules with
  examples (`:1146-1166`, `:1169-1202`).
- One LLM call per chunk via `_extract_facts_from_chunk` (`fact_extraction.py:2081`). The system
  prompt is deliberately bank-agnostic so one provider-side prompt cache serves every bank; the
  bank's "retain mission" rides in the user message instead (`:1611-1619`, mission preamble built
  at `:1813-1830`, user message assembled at `_build_user_message`, `:1858-1958` — Event Date,
  Context, metadata, narrator attribution and attachment sections).
- The combined stored fact text is `what | When: … | Where: … | Involving: … | why`
  (`:2320-2343`); in verbatim mode the original chunk text is stored instead
  (`:2326-2327`, guidelines `:1220-1229`).
- Output-length failures bisect the chunk instead of giving up: below a 500-char floor a chunk is
  split for retry (`_MIN_SPLIT_CHUNK_CHARS`, `:318-325`, `_split_chunk_for_output_retry`,
  `:328-349`).

### 2.2 Fact typing: experience vs world vs observation

- The extraction schema asks the model for `fact_kind` (`event`/`conversation`) and `fact_type`
  (`world`/`assistant`) with the semantics spelled out: `world` = objective/user facts including
  preferences, rules, corrections, constraints; `assistant` = actions/experiences/observations the
  agent itself performed (`fact_extraction.py:1111-1117`, schema field `:284-289`).
- The stored model maps `assistant → experience` and everything else → `world`
  (`fact_extraction.py:2304-2313`); the persisted `Fact.fact_type` is `Literal["world",
  "experience"]` (`:180`). A caller can override the whole batch (`_extract_and_embed`,
  `engine/retain/orchestrator.py:1474-1476`).
- `observation` is a *derived* type written only by consolidation
  (`engine/consolidation/consolidator.py:10-11`); retain never writes it. Recall validates fact
  types against a fixed set (`VALID_RECALL_FACT_TYPES`, `engine/memory_engine.py:9727-9732`).

### 2.3 Entity resolution + alias handling (deterministic, Postgres-backed)

- Entity mentions are collected per fact with a `resolve` flag: extractor names always resolve,
  caller-supplied names carry the caller's intent, and a collision lets the caller's literalness win
  (`engine/retain/entity_processing.py:89-137`).
- Resolution is batched per retain: strategy dispatch trigram → auto-detected
  `pg_trgm` fallback to "full" → Oracle `UTL_MATCH` (`engine/memories/pg/entity_resolver.py:694-752`,
  trigram probe `:733-746`). Candidate sets are capped (`:1216-1228`).
- Scoring is deterministic: trigram-similarity floor gate (`:1318-1320`), token-compatibility veto
  (`:1322-1325`), then a 0–1 score of name similarity ×0.5 (`:1337-1339`) + co-occurring-entity
  overlap ×0.3 weighted by inverse hub degree (`:1275-1281`, `:1341-1345`) + 7-day temporal
  proximity ×0.2 (`:1347-1357`), merged at a rounded ≥0.6 threshold (`:1370-1372`). Identical
  trigram sets ("Wren 🎵" vs "Wren") score 1.0 outright (`:1327-1333`). In-batch near-duplicates are
  clustered before insert (`:219-358`).
- "Aliases" are handled as (a) case-insensitive canonical-name matching — the registry matches on
  `LOWER(canonical_name)` and display case is deliberately preserved
  (`entity_processing.py:57-67`), (b) fuzzy merges via the scoring above, and (c) label-taxonomy
  entities, which are exempt from fuzzy merge and match exactly only
  (`entity_resolver.py:1230-1267`, "a label row can never be a fuzzy-match target" `:1294-1300`).
- Name intake hard-caps at 512 chars to protect the `(bank_id, canonical_name)` btree from
  extraction artifacts like base64/SVG paths (`entity_processing.py:41-54`, rationale `:44-53`).
- Mention counts/last-seen stats are deferred out of the write transaction
  (`entity_resolver.py:1380-1382`, `flush_pending_stats` `:545`).

### 2.4 Event date vs ingest date

- Extraction is handed an **Event Date** (the document's/turn's event time) and instructed to
  resolve *all* relative expressions into absolute dates inside the fact text and to set
  `occurred_start`/`occurred_end` for `event`-kind facts, spanning the whole period for coarse
  dates ("in 2015" → 2015-01-01…2015-12-31) (`fact_extraction.py:1120-1131`).
- Deterministic fallback: when the LLM leaves dates empty, `_infer_temporal_date` maps relative
  phrases ("yesterday", "last week") to day-offsets from the event date
  (`fact_extraction.py:98-134`, call site `:2352-2353`); point events default `occurred_end` to
  `occurred_start` (`:2357-2361`).
- **Ingest date** is stored separately as `mentioned_at` = the event date the caller supplied
  (`fact_extraction.py:2457-2459`), and documents/chunks keep their own timestamps
  (`documents.updated_at` upsert, `engine/memories/pg/retain.py:253-284`). Recency scoring later
  distinguishes a *coarse calendar period* (scored from period end, capped at neutral) from a
  genuine interval (`engine/search/reranking.py:86-176`).

### 2.5 Link creation: causal, semantic, temporal (mostly deterministic)

- **Causal** — the LLM emits `caused_by` edges to *earlier* facts only; index references are
  validated (`target_index < i`) and invalid ones dropped (`fact_extraction.py:2422-2455`, schema
  `:252-267`). Retain writes only the canonical `caused_by` type; legacy `causes/enables/prevents`
  are readable but restorable only by transfer import
  (`engine/causal_links.py:8-14`, `engine/memories/pg/links.py:934-945`). Edges get weight 1.0
  (`links.py:1001`).
- **Semantic** — one ANN (HNSW) probe per fact type on a temp seed table via LATERAL join, run on
  a separate connection *outside* the write transaction; links above a cosine threshold
  (`engine/memories/pg/links.py:569-660`, fact-type-split indexes rationale `:579-585`).
- **Temporal** — per-fact event dates drive a bidirectional B-tree index scan for the K nearest
  neighbors in each direction (120× faster than a window scan at 164k units, per the comment) plus
  within-batch linking, weight `max(0.3, 1 − Δt/window)` (`links.py:535`, `links.py:142`), capped
  top-N per unit (`links.py:445-560`, within-batch bounded generation `:85-146`, cap `:55-82`).
- Bulk link inserts sort on a direction-normalized key so concurrent writers can't deadlock
  (`links.py:149-204`).

### 2.6 Source association, document identity, dedup, changed/deleted sources

- Every fact is associated with its source document and chunk (`memory_units.document_id`,
  `chunk_id` columns selected throughout, e.g. `engine/memories/pg/recall.py:116-119`), plus tags,
  metadata and `observation_scopes` carried from the retain request
  (`relabel_document_memories`, `engine/memories/pg/retain.py:287-386`).
- **Full-replace semantics:** retaining the same `document_id` deletes the old document row and
  cascades to its chunks/units on the first batch, preserving `created_at`
  (`engine/retain/fact_storage.py:191-321`, delete-for-replace `:300-307`; `delete_document_for_replace`
  `engine/memories/pg/retain.py:221-250`). Content hash is SHA-256 of the sanitized body
  (`fact_storage.py:230-232`).
- **Delta retain** diffs chunk hashes and only re-extracts changed chunks
  (`_classify_chunk_diff`, `engine/retain/orchestrator.py:3964-3981`; `_try_delta_retain`
  `:3983+`; metadata-only fast path `:4673+`). **Append** mode strictly verifies the new body is a
  continuation of the stored one (`append_document_body` `:257-267`,
  `assert_append_extends_stored_body` `:295-349`).
- **Dedup / idempotency:** chunk rows upsert `ON CONFLICT` on chunk_id so re-submission is
  idempotent (`engine/memories/pg/retain.py:511-536`); a crashed retain of the *same* content is
  recovered from committed chunk hashes (`recovery_chunk_hashes`, `:87-108`), and a new content
  hash is treated as a new version, not a retry (`:90-94`).
- **Changed/deleted sources:** before the cascade, observations derived from the outgoing facts are
  deleted and the survivors' `consolidated_at` reset (`delete_stale_observations_for_memories`,
  `fact_storage.py:146-188`, sweep call `:266-280`); downstream relink/prune victims are enqueued
  for graph maintenance (`enqueue_relink_victims`/`enqueue_entity_prune_candidates`,
  `:286-296`, `engine/graph_maintenance.py`). A relabel that changes nothing writes nothing, because
  `updated_at` is the "edited" signal consolidation races on
  (`engine/memories/pg/retain.py:326-331`).
- **Bad-fact correction** is a curation surface: `invalidate_memory` snapshots entity postings and
  causal-edge descriptors into `invalidated_memory_units`, removes the fact and its links, and a
  matching `restore_memory` re-materializes them
  (`engine/memories/pg/writes.py:421-459`, restore `:459+`, causal descriptor rationale
  `engine/causal_links.py:30-42`). A separate memory-defense extension can reject retain content
  wholesale (`BlockedViolation`/`MemoryDefenseAllBlockedError`,
  `engine/retain/orchestrator.py:56-72`, webhook `:351-457`).

### 2.7 Extraction cost / concurrency controls

- Producer/consumer streaming retain: extraction tasks run ahead of DB writes, bounded by
  `retain_chunk_batch_size` and a **byte budget** (`RetainMemoryBudget`) that reserves estimated
  bytes per chunk (facts + embeddings + chunk text) and flushes at half-budget
  (`engine/retain/memory_budget.py:1-23`, `estimate_chunk_bytes` `:64-88`, class `:92-203`,
  `should_flush` `:167-177`). Defaults: `DEFAULT_RETAIN_CHUNK_BATCH_SIZE` (`config.py:1993`) and
  `DEFAULT_RETAIN_MEMORY_BUDGET_MB = 128` (`config.py:2022`).
- Retain's own LLM semaphore bucket (`retain`) is composed with the global one
  (`engine/llm_wrapper.py:75-108`, scope mapping `:120-138`); document-group concurrency is 8
  (`_GROUP_CONCURRENCY`, `orchestrator.py:1764`) and ANN chunks capped at 4
  (`_ANN_PARALLELISM`, `:2279`).
- Extraction retries: N+1 outer attempts (`fact_extraction.py:2148-2174`), re-ask with corrective
  hints on malformed envelopes (`:2225-2246`) and on ≥20% malformed facts (`:2473-2479`); retry
  knobs are retain-specific overridable (`retain_llm_max_retries` etc., `:2154-2183`).
- Prompt-cache opt-in per chunk (`PromptCachePrefix`, `:2145-2150`); vision model used only for
  chunks that actually contain images (`:2128-2143`).
- Token ceiling for extraction output: `retain_max_completion_tokens`, default 64000
  (`config.py:1971`, sent at `fact_extraction.py:2200`).

---

## 3. Consolidation: facts → observations

### 3.1 Grouping, batching, triggers

- Triggered after retain as a queued task (`enable_auto_consolidation`, `config.py:4011`; an
  explicit `/consolidate` drains regardless, `consolidator.py:1843-1844`). The job loops over
  unconsolidated `experience`/`world` facts, capped by `consolidation_batch_size` (50),
  `consolidation_max_memories_per_round` and `consolidation_llm_batch_size` (8 facts per LLM call)
  (`consolidator.py:1899-1901`, `config.py:2138-2148`).
- **Scope grouping is a security invariant:** facts are grouped by their target observation scope
  before batching so facts of different scopes never share an LLM call
  (`consolidator.py:2027-2043`, `_consolidation_batch_key` `:655-693`); a mixed sub-batch is split
  defensively with one extra LLM call (`:2098-2113`). Distinct scope groups run concurrently;
  groups sharing a write scope serialise on per-scope locks (`:2045-2056`).
- Per-bank/tenant config resolution happens at job start (`:1849-1854`); per-scope strategy
  overrides exist (`_config_for_scope`, `:1443+`).

### 3.2 The per-batch pipeline (one LLM call per ≤8 facts)

`_process_memory_batch` (`consolidator.py:2711-3278`):

1. **Recall related observations** per fact, in parallel, with one shared embedder call for all
   query vectors (`:2764-2792`). A failed recall *fails the batch* rather than degrading to "no
   related observations" — proceeding would hide an existing twin and turn an UPDATE into a
   duplicate CREATE (`:2786-2790`).
2. **Observation-capacity cap** per scope (`max_observations_per_scope`): at the limit only
   updates/deletes are allowed (`:2804-2821`).
3. **Decision-model triage** (`triage_model(config)`, `:2823-2832`) — see §3.6.
4. **One LLM call** over the surviving facts + the unioned observations
   (`_consolidate_batch_with_llm`, `:2834-2856`). The prompt (see §3.3) returns per-fact verdicts
   (`kind`: momentary/lasting; `effect`: repeats/changes/ends/unrelated; `new`; `same_as_fact`) and
   rare `deletes` with `merged_into`.
5. **Prepare connection-free, then apply in ONE transaction** (`:2863-2877`): every action is
   checked (sources resolvable, security: observation must be in the recall pool `:2915-2927`,
   liveness preflight `:2941-2943`), embedded in one batch (`:3084-3091`), optionally
   dedup-adjudicated, extension-reviewed (`:3100-3105`), and only then written in a single
   transaction with a pre-declared lock order and a bank-liveness check (`:3121-3141`).
6. Facts the response consumed are stamped `consolidated_at` **in the same transaction** as the
   observations derived from them — a stamp and its writes can never commit apart (#3876,
   `:3240-3253`). A failed LLM call yields no actions and no stamps; the caller bisects the
   sub-batch (adaptive halving to size 1) and re-runs (`consolidator.py:2190-2199`), marking
   single-memory failures `consolidation_failed_at` (`:2197-2203`). Discard rules: an unacted fact
   is re-asked, "skipped while alone" is honored as chatter, and unresolved citations are counted
   and discarded (`consolidator.py:2205-2234`, `_settle_skips` `:3621-3627`; triage entry point
   `triage.py:193`).
7. Facts the response ignored get re-asked (up to twice, then alone) so a small model's oversight
   doesn't silently drop evidence (`:2205-2234`).

### 3.3 Observation grouping and update rules (prompt-level, LLM)

The consolidation system prompt (`engine/consolidation/prompts.py:224-238`, rules `_RULES`
`:96-136`) encodes the merge policy:

- **One observation = one subject × one facet** — never join facets (`:98-100`).
- Per-fact verdicts: `momentary` (chatter; record nothing) vs `lasting`; `effect` ∈
  `unrelated`/`repeats`/`changes`/`ends`, with "changes" restricted to the exact facet and an
  explicit **never-calculate** rule ("2 dogs" + "a dog named Rex" must not become 2→1)
  (`:102-133`).
- `deletes` are rare and only for two *existing* observations saying exactly the same thing
  (`:136`).
- **Time rule:** facts arrive out of order; the most recently *stated* value wins, and the code
  pre-marks observations stated after the fact (`_TIME_RULE`, `:139-144`; the marks are computed
  in `consolidator.py` and shown as `(stated after this fact)` / `"newer_than_input_facts"`) — an
  older fact becomes an earlier state, never an overwrite.

### 3.4 Contradiction handling and duplicate reconciliation

- Contradiction = the `changes`/`ends` effects above; the LLM rewrites the observation text and
  `mentioned_at`/bounds widen from the new evidence (`_apply_update_action`,
  `consolidator.py:3413-3545`; SQL `rewrite_observation`, `engine/memories/pg/consolidation.py:297`
  area). A stale-observation guard makes older facts "earlier state" additions instead of
  overwrites (prompt `prompts.py:139-144`; triage cross-check `triage.py:219-228`).
- **Exact-text duplicate guard (deterministic):** a CREATE that reproduces the normalized text of
  an observation the model was shown (or of an UPDATE in the same response) is dropped before any
  cost (`consolidator.py:3010-3048`).
- **Semantic dedup (specialized-model + LLM adjudication, opt-in):** a create/update whose
  embedding is ≥ `consolidation_dedup_threshold` (default 0.97, `config.py:2147`) cosine to a
  different observation triggers a focused 1-by-1 LLM merge verdict
  (`_dedup_adjudicate`, `consolidator.py:2890-2895`, adjudication+folds `:301-486`), folded in the same transaction
  (`:3192-3221`). The recall for dedup uses round-robin *interleave* fusion instead of RRF so the
  semantic-rank-1 twin cannot be buried (`engine/search/fusion.py:112-130`).
- Merge deletes fold the deleted observation's sources and dates into the survivor
  (`_fold_deleted_evidence`, `consolidator.py:3236-3238`, `:3657+`; SQL fold with `proof_count`
  recompute, `engine/memories/pg/consolidation.py:160-260`).
- An UPDATE+DELETE of the same observation in one response resolves in favor of the update
  (`:2900-2914`).

### 3.5 Evidence-history preservation

- Observations carry `proof_count`, `source_memory_ids`, and JSONB `history` (module docstring,
  `consolidator.py:5-16`). `proof_count` is written as `len(source_memory_ids)` on create
  (`engine/memories/pg/consolidation.py:342-361`) and recomputed as the distinct union on every
  fold/rewrite (`:174-176`, `:245-247`).
- Every UPDATE appends a pre-update snapshot (`previous_text/tags/dates` + `new_source_memory_ids`)
  to the `observation_history` table as one JSONB row, trimmed to
  `observation_history_max_entries` (`_append_observation_history`, `consolidator.py:3365-3410`;
  why it moved out of an unbounded JSONB column that hit Postgres's 256 MB limit, `:3512-3515`).
- Source id lists are merged and de-duplicated (`:3476-3478`); tags merge as a union for scope
  security (`:3480-3483`).
- Document-level change history (retain/append/retag/fact_edited/fact_invalidated/…) is recorded as
  id/count events on the async operations log, bounded by operation retention
  (`engine/document_history.py:1-22`, event kinds `:48-61`).

### 3.6 Degradation prevention and the decision-model triage

- **Triage** (`engine/consolidation/triage.py`) settles the two easy cases with a *typed decision
  model* before the LLM sees them: a fact that **restates** an existing observation (attach as
  evidence, text unchanged) and **chatter** (record nothing). One System One request per fact in
  parallel, top-10 candidates (`MAX_CANDIDATES`, `triage.py:34-35`); a verdict stands only when the
  answers cross-check (a "touches" yes beats a "restates"), and under a bank mission nothing is
  dropped (`:200-246`, agreement guard `:219-228`, mission override `:229-235`). Restatements are
  folded into the LLM's own update of the same observation, or become a text-preserving UPDATE
  (`_apply_triage`, `consolidator.py:3586-3614`). If the LLM call later fails, triage verdicts are
  *not* applied so the bisection re-run sees the facts again (`:2858-2861`).
- **Degradation prevention elsewhere:** `_gather_or_cancel` cancels sibling tasks on failure so no
  orphan batch writes after the worker re-queues the operation (`consolidator.py:98-134`); batch
  failures are classified and bisection-rescued (`:3862-3918`); unresolved `source_fact_ids`
  citations are counted and discarded, not silently applied (#5273, `:1979-1982`); a batch whose
  source facts were edited since the read is dropped wholesale including stamps (#4831,
  `:3142-3150`).

### 3.7 Observation staleness detection

- Consolidation does not run on a timer per observation; staleness is *derived*:
  `updated_at` on a source fact is the edit signal (`engine/memories/pg/retain.py:326-331`), and
  consolidation discards in-flight batches whose sources changed under them
  (`consolidator.py:3142-3150`). Re-ingest of a document sweeps derived observations
  (`fact_storage.py:146-188`). For *mental models*, staleness is computed explicitly (§5.5).

---

## 4. Retrieval (recall): 4 arms → fusion → rerank → budgets

### 4.1 Arms

- The recall pipeline is: retrieval → RRF merge → rerank → MMR diversity → chunk fetch → token
  filter (`engine/memory_engine.py:10104-10119`).
- Four arms per fact type through one store call (`recall_unified`,
  `engine/search/retrieval.py:129-272`): **semantic** (dense), **BM25**, **graph** (link
  expansion), **temporal**.
- **Semantic + BM25 in one UNION query** with per-fact-type `ORDER BY … LIMIT` arms so the partial
  per-fact-type HNSW indexes are usable; the BM25 half is *omitted from the SQL* when text search
  is off or the query has no word tokens
  (`engine/memories/pg/recall.py:29-114`, conditional BM25 `:93-96`, per-arm limits `:55-71`).
  Graph seeds come from the same ordered rows when a threshold covers them (`:104-114`).
- **Graph arm** is an abstracted retriever supplied by the store
  (`engine/search/graph_retrieval.py:19-68`; the Postgres implementation walks entity/temporal/
  causal links via `engine/memories/pg/link_expansion.py`).
- **Temporal arm** (`engine/memories/pg/recall.py:382-700`): similarity-ranked, window-filtered ANN
  pool of 60 per fact type (`_TEMPORAL_POOL_SIZE`, `:310`), narrowed to 10 coverage-spread entry
  points over 8 time buckets (`:311-312`, `_select_with_temporal_coverage` `:335-380`), then
  multi-hop spreading through temporal/causal links with per-hop decay 0.7 and causal boost
  (`:317-318`, spread loop `:573-690`). Out-of-window neighbors are excluded during spreading
  (`:602-609`).
- **Temporal extraction** from the query text is dateparser-based CPU work run on a dedicated
  single-thread executor so it can't stall the event loop; on parser failure it degrades to "no
  temporal signal" rather than failing recall
  (`engine/search/temporal_extraction.py:79-121`, executor rationale `:18-49`). A caller-supplied
  `temporal_window` bypasses extraction entirely (`engine/search/retrieval.py:100-126`).

### 4.2 Fusion

- **RRF** (k=60, `score(d) = Σ 1/(k+rank)`) merges the arms, keeping per-arm raw scores and ranks
  (`engine/search/fusion.py:29-109`, formula `:33`).
- **Interleave fusion** is the alternative used for consolidation-dedup recall: RRF averages away
  the semantic-rank-1 twin, so round-robin guarantees every arm's top hits a slot
  (`fusion.py:112-130`, assignment `:152-176`).
- Strategy selection: `cross_encoder` (default), `rrf`, `interleave` (`engine/memory_engine.py:835-840`).

### 4.3 Rerankers and scoring

- **Cross-encoder** (specialized model): pluggable providers — local SentenceTransformers
  (`engine/cross_encoder.py:263`), remote TEI (`:520`), Cohere (`:855`), ZeroEntropy (`:986`),
  SiliconFlow (`:1028`), NVIDIA (`:1089`), TypeSafe (`:1225`), FlashRank (`:1731`), ONNX
  (`:1929`), LiteLLM (`:2125`/`:2235`), **Jina MLX** (`:2346-2400`, `jinaai/jina-reranker-v3-mlx`
  0.6B listwise for Apple Silicon), Google (`:2477`), Alibaba (`:2633`), multi-member failover
  chains (`:2675-2825`), and an **RRF passthrough** for slim deployments that returns neutral 0.5s
  (`:1693-1729`). Factory: `create_cross_encoder_from_env` (`:3061`).
- **Decision-model reranker** (`engine/search/decision_reranker.py`): when a decision model is
  configured for recall it replaces the cross-encoder; one Noul question per candidate ("would
  showing this help or distract?"), scores are rank positions 1.0→0.0, the order is final, and
  optional `prune`/`dedup` drop no-help/repeat candidates (doc `decision_reranker.py:1-11`, options
  `decision_reranker.py:39-56`, scoring semantics `decision_reranker.py:69-83`, embedding-alike
  prefilter for dedup `:130-153`).
- **Jina MLX** is the Apple-Silicon reranker: `jinaai/jina-reranker-v3-mlx`, a 0.6B listwise
  reranker downloaded from HuggingFace on first use, requiring the `mlx`/`mlx-lm` extras
  (`engine/cross_encoder.py:2346-2400`).
- **Combined scoring** (`engine/search/reranking.py:179-309`):
  `combined = CE_norm × recency_boost × temporal_boost × proof_count_boost` with α = 0.2 / 0.2 /
  0.1 (`reranking.py:40-42`); recency decay is linear (365-day window, 0.1 floor) or exponential (90-day
  half-life) or none (`:44-58`, `:61-83`); coarse calendar-period dates are scored from period end
  and capped at neutral (`:128-176`); proof_count is log-normalized from observations only
  (`reranking.py:289-299`). A decision-model rerank **skips** these boosts — its order is final
  (`engine/memory_engine.py:10848`), as does interleave (`:10856`).
- Passthrough rerankers get CE scores seeded from RRF rank so boosts modulate a real base
  (`reranking.py:232-266`); per-strategy boosts (`recall_strategy_boosts`) apply after scoring
  (`engine/memory_engine.py:10877-10886`, `engine/search/recall_boost.py:1-245`).

### 4.4 Token budgets and floors

- Fact budget: results are spent in rank order, an oversized fact skips only itself, and a
  non-empty match never returns empty — the top-ranked fact is returned over-budget as a floor
  (`engine/fact_budget.py:1-18`, selection `fact_budget.py:43-87`).
- Provenance budget: each observation's `source_fact_ids` resolve through a `source_facts` map
  filled to a global or per-observation token budget, in observation-rank order
  (`engine/source_facts.py:1-105`, selection `source_facts.py:31-105`).
- Chunks budget is independent of the facts budget (`engine/memory_engine.py:9649-9656`,
  default 8192 at `:9591`); entity-observation budget default 500 tokens (`:9589`). Query length
  is capped at `recall_max_query_tokens` (500) at ingress — a degenerate extraction once wedged
  Postgres with a 54k-term tsquery (`engine/memory_engine.py:9713-9716`, `config.py:1928`).
- Post-rank `min_scores` floors (reranker/final) are opt-in and inclusive; a rank-score provider
  rejects a reranker floor because its scores are positions, not confidences
  (`engine/memory_engine.py:10895-10933`, entry validation `:9738-9760`).

### 4.5 Citation validation and observability

- Recall returns observations with their `source_fact_ids` (`source_facts` map above); the caller
  sees truncation explicitly (`source_facts.py:53-58`).
- Consolidation's own recalls prefer raw facts (never dedup away what it folds) —
  `prefer_observations` defaults False for internal callers (`engine/memory_engine.py:9584-9586`,
  `:9635-9639`).
- Recall phases are always traced for metrics; payloads only under `enable_trace`
  (`:10133-10142`).

### 4.6 Degradation when index/model is unavailable

- BM25 backend failure falls back to semantic-only (Oracle Text DRG-10599 path,
  `engine/memories/pg/recall.py:235-250`); missing `pg_trgm` degrades entity resolution to the
  "full" strategy with a warning (`engine/memories/pg/entity_resolver.py:733-746`).
- Temporal-analysis failure degrades to no constraint (`temporal_extraction.py:100-115`).
- Cross-encoder chains fail over to the next member, and a configured decision model can fall back
  to the environment reranker (`recall_decision_model_fallback`, `engine/search/reranking.py:320-347`,
  `:392-407`); lazy model init is bounded by `model_init_timeout` with a clear error (`:371-380`).
- If no vector index applies, `RRFPassthroughCrossEncoder` keeps recall working without neural
  reranking and combined scoring re-seeds from RRF (`engine/cross_encoder.py:1693-1729`,
  `engine/search/reranking.py:232-266`).
- Missing recall-bank rows answer 404 instead of a misleading empty 200
  (`engine/memory_engine.py:9790-9797`).

---

## 5. Reflection: the agent, mental models, delta refresh, retractions

### 5.1 Hierarchical retrieval order

Reflect's agent loop uses three layers in strict quality order — user-curated mental models
(`search_mental_models`/`read_mental_models`), consolidated observations
(`search_observations`), then raw facts (`recall`), plus `expand` for source text
(`engine/reflect/agent.py:1-8`, tool wiring `agent.py:658-668`). Tool token defaults are
bank-resolved
(`ReflectToolTokenLimits`, `:86-104`); per-call token asks are bounded to [1000, 16000] and shared
across concurrent calls from the remaining context budget (`:68-77`, `:106-113`).

### 5.2 Multi-round evidence gathering

- Two modes: **agent turns** (LLM picks tools per turn, up to `reflect_max_iterations` = 10,
  `config.py:2303`) and **decision-orchestrated rounds** when a decision model is configured:
  each round runs the retrieval layers in parallel with one query each, a decision-model
  **sufficiency score** ends retrieval early, and per-round pruning precedes reading
  (`agent.py:604-612`, sufficiency wiring `:1114-1120`, round handling `:1233-1235`, `:1529+`,
  pruning `_prune_round` `:1928+`). The sufficiency check is a Score question answered at the
  most-likely level, not a rounded expectation (`engine/cross_encoder.py:1515-1560`).
- Context budget `reflect_max_context_tokens` (default 100k, `config.py:2315`) forces the final
  synthesis; a forced `search_mental_models` result is trusted without an extra LLM call only when
  every page is explicitly fresh (`is_stale == False`) and non-empty
  (`agent.py:483-502`).

### 5.3 Delta vs full mental-model refresh

- `MemoryEngine._execute_mental_model_refresh` (`engine/memory_engine.py:18511+`) resolves the
  model's scope from its trigger (tags/tag_groups/fact_types, exclusions), then decides mode:
  delta requires existing content and an unchanged `source_query`; otherwise it falls back to full
  with a typed reason (`no_baseline_content`, `source_query_changed`, …
  `engine/mental_model_refresh.py:27-46`, decision `memory_engine.py:18597-18624`).
- Delta scopes recall to a **watermark window**: `created_after` = the newest memory the previous
  refresh saw (`last_memory_seen_at`), `created_before` = a DB-time snapshot so late arrivals stay
  for the next round (`memory_engine.py:18693-18700`;
  window model `mental_model_refresh.py:152-176`; the window filters `updated_at`, so edited
  memories re-enter — `engine/memories/pg/recall.py:149-155`).
- Delta applies **structured operations** to the existing document instead of regenerating it:
  8 typed ops (`append_block`, `insert_block`, `replace_block`, `remove_block`, `add_section`,
  `remove_section`, `replace_section_blocks`, `rename_section`) addressed by ids, never indexes
  (`engine/reflect/delta_ops.py:133-214`, why-not-indexes `:28-34`). Unmentioned sections/blocks
  are copied through verbatim, so prose drift is structurally impossible (`:16-24`). Shape errors
  refuse the whole reply and re-ask with the errors quoted; reference errors (unknown ids) are
  skipped individually (`:7-15`, strict schema `:71-79`, `parse_delta_operation_list` `:364`,
  `request_delta_operations` `:491`, `apply_operations` `:614`). Failure modes are conservative:
  parse failure ⇒ zero changes (`:36-39`).
- A dry run runs the identical pipeline and reports outcome/failure reason/delta ops/retraction
  without persisting (`mental_model_refresh.py:314-377`; "deliberately no way to make this run
  behave differently for a preview", `memory_engine.py:18535-18539`).

### 5.4 Retractions and citation guarantees

- A mental model records its grounding under `reflect_response.based_on` keyed by fact type.
  `engine/reflect/retractions.py` turns *absence* of a cited row into a value: memory-backed types
  are allowlisted (`:44`), `partition_retracted` splits cited vs live ids (`:112-134`), and the
  "everything missing" case is treated as broken provenance, not a retraction, so a whole-bank
  import can't trigger mass deletion (`:67-84`). Retracted facts keep their recorded text — the
  archive row is the only surviving copy (`:50-56`). Removal is deferred while consolidation is
  pending (re-ingested facts return under new ids), reported as `deferred_reason`
  (`mental_model_refresh.py:206-236`).
- Citation validation in the agent: the final `done` tool call's id fields are intersected with
  what was actually retrieved (`_cited_ids`, `engine/reflect/agent.py:2333-2343`), and ids are
  validated **after** the length rewrite, which can garble them (`:2415-2420`); unseen ids are
  stripped from the answer text by the presenter (`agent.py:2416-2419`). The refresh reports facts
  *retrieved vs used* per type so a disappointed refresh is diagnosable
  (`mental_model_refresh.py:179-192`). The `done` call itself is the trusted answer carrier
  (`agent.py:2377-2420`); a post-hoc length rewrite may itself issue one more LLM call
  (`agent.py:2399-2406`).

### 5.5 Mental-model staleness and refresh triggers

- `compute_mental_model_is_stale` (`engine/memory_engine.py:21553-21610`): stale when a memory in
  the model's scope was written since `last_memory_seen_at`, **or** when the document still cites a
  fact that no longer exists (removal raises no watermark, so only the cited-ids check can see it).
  The batch variant backs polling surfaces in one round-trip.
- Refreshes are triggered by the consolidation flush and a cron loop, plus retraction-driven nudges
  for auto-refreshing documents (`_submit_refreshes_for_retracted_grounding`, `:21653+`), and
  consolidation enqueues refreshes for affected tags (`_trigger_mental_model_refreshes`,
  `engine/consolidation/consolidator.py:2602+`).
- Observation *trend* staleness is computed deterministically from evidence timestamps:
  STABLE/STRENGTHENING/WEAKENING/NEW/STALE over 30/90-day windows
  (`engine/reflect/observations.py:115-186`).

### 5.6 Decision-model cost avoidance in reflection

- The sufficiency check replaces "keep searching?" LLM turns with a typed Score call
  (`engine/cross_encoder.py:1515-1560`); decision-orchestrated reflect does retrieval in parallel
  rounds with one query each instead of one LLM turn per layer (`agent.py:604-612`, check wiring
  `agent.py:1114-1120`). The generic `DecisionModel.ask` client that both use
  (`engine/decision_model.py:262-295`) retries transient failures and splits oversized question
  sets (`:281-295`).
- Decision calls are retried independently (a rate limit read as "not enough evidence" used to buy
  two extra LLM turns) and traced under `decision_*` scopes next to the LLM calls they save
  (`cross_encoder.py:1533-1540`, `engine/decision_model.py:181-207`).

---

## 6. Mechanism classification and marginal value for a coding-agent factory workload

Workload assumed: a factory of coding agents producing worker briefs, recovery logs, planning
notes and review transcripts across many project banks (the exact scenario the coding-agents
integration targets — see §9.3).

| Mechanism | Class | Where | Marginal value (factory) vs complexity |
|---|---|---|---|
| Chunking (turn/JSONL aware, idempotent) | deterministic | `fact_extraction.py:776-887` | **High / low.** Session transcripts are JSONL/turn arrays; turn-boundary chunking keeps speaker context in one extraction unit. |
| LLM fact extraction (5-dimension, typed) | LLM | `fact_extraction.py:1083-1143`, `:2081+` | **High / medium.** Turns messy transcripts into `world`/`experience` facts; the `assistant→experience` split is exactly the agent-vs-user distinction a factory needs. Cost: one call per ~3000-char chunk. |
| Retain fact filter (extension hook) | deterministic (host code) | `orchestrator.py:1496-1535` | **Medium / low.** Lets a factory drop secrets/noise before embedding. |
| Entity resolution (trigram + co-occurrence + recency) | deterministic | `entity_resolver.py:1163-1378` | **High / medium.** Cross-project entity continuity (same service name across banks' facts) without LLM cost; label taxonomy keeps enum values from merging. |
| Temporal/semantic/causal link creation | deterministic (+1 LLM pass for causal) | `links.py:445-660, 934-1045` | **Medium / low.** Graph expansion recalls recovery-relevant neighbors ("what happened right before the failure"); causal edges cost one prompt section only when enabled. |
| Full-replace / delta / append document semantics | deterministic | `fact_storage.py:191-321`, `orchestrator.py:3936-4930` | **High / low.** Re-ingesting a repo's docs or appending session turns is cheap and idempotent; delta re-extracts only changed chunks. |
| Memory byte budget (producer/consumer) | deterministic | `memory_budget.py:92-203` | **High / low.** Bounds worker RSS against dense extraction bursts — the difference between a sized worker and an OOM-killed one. |
| Consolidation batch LLM (facts→observations) | LLM | `consolidator.py:2711-3278`, `prompts.py:96-144` | **High / high.** This is the deduplication layer: N near-identical "build failed then passed" facts become one evidence-backed observation. Biggest token consumer after extraction. |
| Decision-model triage (restates/chatter) | specialized-model | `triage.py:1-246` | **High / low.** Skips the LLM for the two most common facts in agent transcripts (restatements and chatter) at sub-second typed-call cost. |
| Semantic dedup adjudication | specialized-model + LLM | `consolidator.py:2890-2895`, adjudication+folds `:301-486` | **Medium / medium.** Only needed at scale; threshold 0.97 keeps it rare. |
| Observation history (JSONB snapshots) | deterministic | `consolidator.py:3365-3410` | **Medium / low.** Audit trail for review workflows; bounded rows. |
| 4-arm retrieval + RRF | deterministic (SQL+embed) | `recall.py:29-114`, `fusion.py:29-109` | **High / low.** Standard hybrid recall; BM25 matters for exact identifiers (error codes, symbol names). |
| Temporal arm + extraction | deterministic | `recall.py:382-700`, `temporal_extraction.py` | **Medium / low.** "What changed since the last release" queries; off-loop execution keeps it safe. |
| Cross-encoder rerank | specialized-model | `cross_encoder.py`, `reranking.py` | **Medium / medium.** Quality boost; the RRF passthrough exists precisely to skip it on constrained deployments. |
| Decision-model rerank (+prune/dedup) | specialized-model | `decision_reranker.py` | **Medium / medium.** Cheaper than a CE cluster if a decision endpoint is already deployed; order is final so no boost stack. |
| Combined scoring (recency/temporal/proof) | deterministic | `reranking.py:179-309` | **High / low.** Free ranking signal; proof_count surfaces well-corroborated project rules. |
| Token budgets + floors | deterministic | `fact_budget.py`, `source_facts.py` | **High / low.** Deterministic context cost for agent prompts — predictable per-turn injection size. |
| Reflect agent (hierarchical tools) | LLM | `agent.py:547+` | **High / high.** Answers "why did the build break last time" style synthesis; the most expensive per-query path (multi-turn). |
| Decision-orchestrated reflect | specialized-model | `agent.py:604-612`, `cross_encoder.py:1515+` | **High / low.** Cuts reflect turns materially — direct token savings on every auto-recall. |
| Delta mental-model refresh (structured ops) | LLM (delta call) + deterministic apply | `delta_ops.py:1-40, 133-214` | **High / medium.** Keeps per-project "pages" (architecture, conventions, in-flight work) current without regenerating them — the coding-agents premise (§9.3). |
| Retraction handling | deterministic | `retractions.py` | **Medium / low.** Prevents pages asserting deleted facts; cheap set arithmetic. |
| Worker queue + backpressure deferrals | deterministic | `poller.py`, `backpressure.py` | **High / low.** Sustained factory ingest survives embedder 429s and store shedding without losing the tail. |
| Prompt caching (bank-agnostic prefixes) | deterministic | `fact_extraction.py:1611-1619`, `prompts.py:224-238` | **High / low.** One cache for every bank slashes per-call input cost — multiplied by factory fan-out. |

---

## 7. Deployment facts

### 7.1 Postgres + pgvector requirement

- The engine's managed extension set is `vector` (pgvector), `vectorscale`, `vchord`,
  `alloydb_scann`, `pg_trgm`, `btree_gin`, `vchord_bm25`, `pg_textsearch`, `pg_search`,
  `pgroonga` — installed with schema-pinned `CREATE EXTENSION IF NOT EXISTS`
  (`hindsight-api-slim/hindsight_api/_pg_extensions.py:41-52`, `:73-96`). pgvector is a hard
  dependency (`pyproject.toml` `"pgvector>=0.4.1"`); BM25 backends and ANN indexes are selectable
  via config (`text_search_extension`, partial HNSW indexes per fact type —
  `engine/memories/pg/recall.py:60-62`). An Oracle backend exists as a port but PG is the
  reference (dialect layer `engine/sql/`, store splits `engine/memories/pg/`).
- `hindsight-embed` ships an **embedded Postgres ("pg0")**: the daemon defaults to
  `pg0://hindsight-embed` and data lands under `~/.pg0/instances/<name>`
  (`hindsight-embed/hindsight_embed/cli.py:19`, `:601-608`; per-profile isolation
  `daemon_embed_manager.py:321-333`).

### 7.2 Embedded vs external service

- **hindsight-embed** (MIT, deps: aiohttp + rich only — `hindsight-embed/pyproject.toml:5-16`)
  manages a background daemon on localhost:8888 with auto-shutdown after inactivity
  (`hindsight-embed/README.md:1-12`).
- **Hermes plugin** composes `hindsight_client.Hindsight` + the embed manager itself rather than
  importing the heavy `hindsight-all` package, keeping Hermes' venv clean
  (`hindsight-integrations/hermes/__init__.py:893-934`). Three modes: `cloud`,
  `local_embedded`, `local_external` (`:649-686` schema; `_LOCAL_MODES` `:84`).
- External/self-hosted: `hindsight-api-slim` server + worker against your own Postgres
  (`hindsight-api-slim/pyproject.toml`, `worker/main.py`).

### 7.3 Hermes memory-provider integration

- Config resolution: profile-scoped `$HERMES_HOME/hindsight/config.json` → legacy
  `~/.hindsight/config.json` → env vars, with isolation-critical values (mode/apiKey/bankId) read
  through the secret scope so a multiplexed profile never inherits the default profile's partition
  (`hermes/__init__.py:1-9`, `_load_config` `:416-448`, scoped-read rationale `:110-131`).
- **Multibank:** write banks and recall-only banks with per-bank budgets; recall dedupes across
  banks, writes go to every write bank, a failing extra bank is skipped with a 300 s cooldown while
  a primary failure raises (`:85-91`, `:536-541`; tests `tests/test_multibank.py:140-344`).
- **Retain durability:** a single writer thread drains a queue; transient failures are re-sent
  (backlog ≤100, ≤5 attempts), async ops the server accepted-but-failed are re-queued server-side
  up to 3×, and the next-turn prefetch can wait for the just-completed retain to become
  recall-visible before recalling (`__init__.py:291-303`, `:566-581`, `:1004-1024`, `:1045-1072`;
  tests `tests/test_retain_durability.py`, 8 tests).
- `update_mode='append'` is probed against the server version per (URL, key) with an
  unreachable-probe cooldown; old servers fall back to per-process document ids
  (`:172-183`, `:190-282`).
- Recall shaping knobs ship in the config schema (observation-only default recall, min-score
  floors, tags/tag-match, budget low/mid/high, hybrid context/tools mode)
  (`:811-884`).

### 7.4 Coding-agents hooks plugin

- `hindsight-integrations/coding-agents` is one package with per-agent entry points (Claude Code,
  Codex CLI, opencode, Cursor CLI, Copilot CLI, Factory Droid, and ~20 more), wired via hooks:
  SessionStart/Stop hooks inject memory and retain turns automatically — "no setup command"
  (`hindsight-integrations/coding-agents/README.md:1-20`; hook files
  `src/{claude,codex,cursor,copilot,droid,…}-{hook,sessionstart-hook,stop-hook}.ts`, `hooks/hooks.json`).
- Ingestion is two-path: per-commit full message+diff (opt-in, one extraction op per commit) vs the
  default aggregated last-N commit-messages document (one extraction op total), plus raw-JSONL
  chat backfill under a `conversation` strategy
  (`src/core/git.ts:1-10`, `:117`, `:219`, `:310`; `src/core/chat.ts:48-63`).
- Bank naming is worktree-aware and path-spelling-proof so all worktrees of a repo share one bank
  (`src/core/git.ts:41-49`); pages (`architecture`, `conventions`, `in-flight initiatives`) are
  read via `hindsight_search_pages`/`hindsight_read_page` tools (`README.md:13-16`).

### 7.5 DeepSeek as a native LLM provider

- `deepseek` is a first-class provider in the provider list with default base URL
  `https://api.deepseek.com` (`engine/llm_wrapper.py:1060-1092`, `:1114-1115`); the
  OpenAI-compatible transport documents the model routes (v4-flash/v4-pro/chat/reasoner) and
  treats v4-flash as the non-thinking route
  (`engine/providers/openai_compatible_llm.py:896-976`, `:1148-1165`). It is also reachable
  through LiteLLM (`engine/providers/litellm_llm.py:101`) and Nous slugs
  (`engine/providers/nous_llm.py:16`).

### 7.6 Supported embedding providers

`tei`, `local` (SentenceTransformers), `onnx`, `openai`, `openai-codex`, `openrouter`,
`requesty`, `hindsight`, `zeroentropy`, `nvidia`, `cohere`, `litellm`, `litellm-sdk`, `google`
— dispatch in `engine/embeddings.py:2583-2846` (`elif provider` chain `:2613-2816`), with
asymmetric query/passage prefixes and a `SplitEmbeddings` for different query/passage models
(`:2557-2581`, `:2409+`).

### 7.7 Worker / backpressure model

- Tasks are claimed `FOR UPDATE SKIP LOCKED` across tenant schemas with round-robin fairness (pass
  1: one claim per pool per schema; pass 2: backfill), so one busy tenant cannot starve others
  (`worker/poller.py:1-10`, claim cycle `worker/poller.py:629-760`).
- Wall-clock ceilings: retain has an absolute ceiling; consolidation has an *idle* ceiling that
  restarts on every committed batch (a stall detector, not a runtime cap)
  (`worker/poller.py:98-144`).
- **Backpressure:** a store shedding writes ("fold behind", "write bound", gRPC UNAVAILABLE) is
  *deferred* without burning a retry; too many deferrals (180 at 120 s ≈ 6 h) fail the task so a
  never-recovering store surfaces; append-race losses defer with jittered exponential backoff;
  knowledge-ingest embedder 429s defer too (`worker/backpressure.py:1-116`,
  constants `worker/poller.py:69-97`).
- Background tasks are marked via contextvar so **live HTTP requests win LLM slots over background
  work** (`worker/background.py:1-29`, LLM semaphore read `engine/llm_wrapper.py:75-108`).
- Task dispatch covers `batch_retain`, `file_convert_retain`, import/export, consolidation,
  reflect/refresh children (`engine/memory_engine.py:5149-5240`); crashed workers reclaim their own
  claimed tasks at startup (`worker/poller.py:1571-1748`).

### 7.8 Multi-tenant extensions

- Tenants resolve to Postgres schemas; `TenantExtension.authenticate` returns a `TenantContext`
  with `schema_name`, `list_tenants` drives per-schema worker polling, per-tenant config
  restrictions and extra bank tables are extension points
  (`extensions/tenant.py:15-205`, worker note `:105-109`). The poller scans active schemas with an
  EXISTS probe before the expensive claim (`worker/poller.py:509-553`).

### 7.9 Telemetry & cost ledger

- OpenTelemetry SDK with a Prometheus reader and OTLP exporter (`metrics.py:28-32`);
  per-bank LLM request tracing (calls, embeddings, failures) into a PostgreSQL-only `llm_requests`
  table (`engine/llm_trace.py:1-58`), decision-model calls traced alongside under `decision_*`
  scopes (`engine/decision_model.py:181-207`).

### 7.10 License / dependency implications for self-hosting

- MIT throughout (`LICENSE`; `hindsight-api-slim/pyproject.toml:7`, `hindsight-embed/pyproject.toml:8`).
- The slim server's runtime deps are ordinary OSS (fastapi, asyncpg, sqlalchemy<2.1, alembic,
  pgvector, litellm, openai/anthropic/google SDKs, opentelemetry, dateparser, toktok-rs —
  `hindsight-api-slim/pyproject.toml:10-120`), but *optional* features pull heavier extras: local
  models (sentence-transformers/flashrank/MLX — the "local-ml" extra), ONNX, and the full
  `hindsight-all` bundle. Self-hosting needs a Postgres with pgvector (plus optional
  pg_trgm/vectorscale/pg_search class extensions) and an LLM/embedding endpoint; the decision model
  is optional and everything degrades without it (§4.6, §3.6).

---

## 8. Cost analysis: what spends tokens, what doesn't

**LLM-token consumers:**
1. **Extraction** — one call per ~3000-char chunk, output up to `retain_max_completion_tokens`
   (64k default) with N+1 retries on malformed output (`config.py:1971`,
   `fact_extraction.py:2148-2174`, `:2200`). The dominant ingest cost; mitigated by prompt caching
   (`:2145-2150`) and by chunk-level delta retains (`orchestrator.py:3936+`).
2. **Consolidation merges** — one call per ≤8 facts plus the observations pool
   (`consolidator.py:2834-2856`, `config.py:2142`), plus dedup adjudication calls when semantic
   dedup fires (`:2883-2895`), plus re-asks for ignored facts (`:2205-2234`).
3. **Reflection** — multi-turn agent loop (or decision-orchestrated rounds) with per-tool token
   budgets and a 100k context ceiling (`agent.py:86-113`, `config.py:2303/2315`), plus a possible
   final length-rewrite call (`agent.py:2399-2406`).
4. **Decision-model calls** — *not* chat tokens: typed System One/Decisions-API requests with
   input-token accounting only, split by request-token ceilings
   (`engine/decision_model.py:1-20`, `:78-86` usage, `:314-329` splitting). These *replace* LLM
   calls (triage §3.6, sufficiency §5.6, rerank §4.3).
5. **Embeddings** — local (free, `local`/`onnx`) or API-billed (`openai`, `cohere`, …); one batch
   call per retain/consolidation/recall via coalescers (`engine/retain/embedding_coalescer.py`,
   one-call-per-batch `consolidator.py:2768-2773`, `memory_engine.py:10261-10270`).

**Token-cost levers in `config.py`:**

| Lever | Default | Effect |
|---|---|---|
| `retain_chunk_size` | 3000 chars (`:1972`) | cost per extraction call scales with chunk size |
| `retain_max_completion_tokens` | 64000 (`:1971`) | extraction output ceiling |
| `retain_chunk_batch_size` / `retain_memory_budget_mb` | see `:1993` / 128 (`:2022`) | in-flight cost/RSS bound, not token cost |
| `llm_max_concurrent` + per-op `retain/reflect/consolidation/mental_model_refresh_llm_max_concurrent` | 32 global (`:1376`), per-op unset (`:3697-3747`) | spend *rate* control per pipeline |
| `llm_max_retries` (+ retain/reflect overrides) | 3 (`:1377`) | worst-case retry spend |
| `consolidation_batch_size` / `consolidation_llm_batch_size` / `consolidation_llm_parallelism` / `consolidation_max_memories_per_round` | 50 / 8 / dyn / capped (`:2138-2152`) | consolidation call count and fan-out |
| `consolidation_max_tokens` (recall budget inside consolidation) | 512 (`:2152`) | recall context fed to the merge LLM |
| `consolidation_source_facts_max_tokens[_per_observation]` (`:4027-4028`) | — | provenance text budget in the merge prompt |
| `consolidation_use_decision_model` / `decision_model_config("consolidation")` | off unless set (`triage.py:103-114`) | replaces LLM verdicts with typed calls |
| `consolidation_dedup_threshold` | 0.97 (`:2147`) | how often dedup LLM adjudication fires |
| `enable_auto_consolidation` (`:4011`) / `consolidation_max_memories_per_round` (`:2139`) | on / capped | background spend throttle |
| `recall_max_tokens` / `recall_chunks_max_tokens` | 2048 (`:2328`) / chunk default | answer-size cost on every recall |
| `recall_max_query_tokens` | 500 (`:1928`) | query-side embed+BM25 cost |
| `reflect_max_iterations` / `reflect_max_context_tokens` / `reflect_max_completion_tokens` | 10 (`:2303`) / 100k (`:2315`) / uncapped | reflect turn and context spend |
| `reranker_max_candidates[_low/mid/high]` (`:1840-1845`) | — | rerank-pair cost |
| prompt-cache opt-ins (`PromptCachePrefix` at extraction/consolidation) | on for Gemini-style caching | per-call input cost |
| `recall_decision_model_prune/_dedup/_fallback` (`memory_engine.py:9588-9592`) | bank-resolved | extra decision calls vs smaller answers |

---

## 9. Where the money is for a coding-agent factory (synthesis)

1. **Ingest is chunk-bound, not fact-bound.** Cost tracks `retain_chunk_size` × document volume;
   session-transcript append + delta retains keep re-ingestion near-free for unchanged chunks
   (`orchestrator.py:3964-3981`, `fact_storage.py:191-321`).
2. **Consolidation is where dedup pays for itself.** Triage (decision model) removes the two most
   common fact classes from the LLM path; the 8-fact batch amortizes the observations pool; exact
   + 0.97-cosine dedup keeps the observation layer from bloating. A factory that skips
   consolidation loses exactly the cross-session density the coding-agents integration sells
   (README §"Does it work?").
3. **Recall cost is deterministic and budgeted** (rank-ordered token budgets, per-call tool caps),
   which makes per-turn memory injection predictable in agent prompts.
4. **Reflect is the premium path** and should be reserved for synthesis (mental-model pages,
   postmortems); decision-orchestrated rounds + sufficiency cuts its turn count.
5. **The decision model is the only sub-LLM "reasoning" tier** — typed, input-token-only, retried
   independently — and it is optional: every consumer degrades to the LLM or deterministic path
   when unset.

---

## 10. Non-goals / things the code does NOT do (verified)

- It does **not** embed any LLM: all generation is provider calls (`engine/llm_wrapper.py:1060-1092`
  provider list; local model classes exist for embeddings/rerankers only).
- Observations are never written by retain; `observation` rows come only from consolidation
  (`consolidator.py:10-11`).
- Consolidation never writes an observation's text from a triage verdict — the decision model
  cannot author text (`triage.py:10-14`).
- Delta refresh cannot corrupt prose: unmentioned blocks are copied verbatim and failed op lists
  produce zero changes (`delta_ops.py:16-39`).
- Recall never silently drops the only match to a token budget (`fact_budget.py:76-85`).

---

## 11. Code vs docs claims

| Docs/docs-adjacent claim | What the code shows |
|---|---|
| "v1.2.1" pinned | The tag `v1.2.1` is `b5e6d3d2`; the pinned HEAD `b92ceb180` is **28 commits later** (`git describe` = `v1.2.1-28-gb92ceb180`), while the package version string still reads 1.2.1 (`pyproject.toml:6`). |
| "Memories that learn" / auto-consolidation | True but gated: consolidation only runs when `enable_auto_consolidation` is on (or an explicit call), and per bank `enable_observations` (`consolidator.py:1903-1906`, `config.py:4011`). |
| "Observations include history JSONB" | Partially superseded in code: history now lives in a separate bounded `observation_history` table (one JSONB row per change, trimmed to `observation_history_max_entries`) precisely *because* the unbounded JSONB column hit Postgres's 256 MB limit (`consolidator.py:3512-3519`, `:3365-3410`). |
| "Knowledge graph" marketing | The graph is concrete: `memory_links` rows of types temporal/semantic/`caused_by` (+legacy) with weights, maintained by graph_maintenance and expanded at recall (`links.py`, `graph_maintenance.py`, `link_expansion.py`). |
| "Works without extra infra" | Postgres+pgvector (+ optional pg_trgm and a text-search extension) is required for the API server; the *client-side* embed daemon is the piece that makes it feel infra-free by shipping pg0 (`_pg_extensions.py:41-52`, `hindsight-embed/README.md:8-12`). |
| coding-agents README benchmark numbers (corrections/cost) | Vendor-reported, not reproducible from this repo's code; the code only shows the mechanisms (hooks, git ingestion, pages) cited in §7.4. Treated as claim, not measurement. |
| "Multi-tenant" | Real but schema-per-tenant via extensions, not row-level security: `TenantContext.schema_name` + per-schema polling (`extensions/tenant.py:25-109`). |
| "Decision model speeds up consolidation/reflection" | Code-verified mechanisms (triage, sufficiency, rerank) with explicit fallbacks; the *magnitude* is only evidenced by inline experiment notes (e.g. `decision_reranker.py:74-82` recall@1 0.94 vs 0.87) — internal, not a public benchmark. |
