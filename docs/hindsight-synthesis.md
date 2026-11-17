# Hindsight synthesis (Phase 3 of the Hindsight research brief)

**Date: 2026-11-16.** Inputs, all inspected in this checkout on the branch that carries
this document:

- Phase 1 (merged): [`docs/memory-ground-truth-audit.md`](memory-ground-truth-audit.md)
  and its machine-readable companion [`ground_truth.json`](../ground_truth.json).
- Phase 2 (merged): [`docs/hindsight-mechanism-report.md`](hindsight-mechanism-report.md).
- The contract under design: [`docs/memory-contract.md`](memory-contract.md)
  (`rizzstack.memory/1`, chapter 32) with
  [`schemas/memory-schema.v1.json`](../schemas/memory-schema.v1.json) and the
  normative oracle [`tests/test_memory_contract.py`](../tests/test_memory_contract.py).
- Campaign machinery cited for the trial design:
  [`docs/m2-canary-runbook.md`](m2-canary-runbook.md),
  [`docs/24-autonomy-dogfood.md`](24-autonomy-dogfood.md).

**Pinned upstream revision:** Hindsight is assessed at
`b92ceb180e349a456d2b5454575067b6ff0f6306` (`git describe` = `v1.2.1-28-gb92ceb180`),
exactly as anchored in the mechanism report
(`docs/hindsight-mechanism-report.md:3-8`). Every `file:line` citation to a
Hindsight source file in this document is **transcribed from the mechanism report**,
which verified each anchor against that revision. No Hindsight checkout exists in
this environment (audit constraint, `docs/memory-ground-truth-audit.md` §1
constraints list; the same constraint makes the mechanism report's
source-anchoring tests skip: 11 tests, 2 skipped, 9 pass on this clone), so this
document re-verified none of them locally — and claims nothing that would require
it.

**Citation conventions.**

- `docs/memory-contract.md §Name` (with line ranges) — the contract's own normative
  text in this tree.
- `docs/hindsight-mechanism-report.md §N` — the merged mechanism report section,
  always accompanied by the underlying `file:line` anchor at the pinned revision.
- `docs/memory-ground-truth-audit.md §N` and `ground_truth.json → systems[id]` —
  the audit's five-level classifications and evidence.
- The five-level ladder (**SPECIFIED / IMPLEMENTED+TESTED / INTEGRATED / DEPLOYED /
  VERIFIED-IN-OPERATION**) and its operational definitions are the audit's
  (`docs/memory-ground-truth-audit.md` §4, `ground_truth.json →
  classification_levels`). This document applies those definitions without
  redefining them. **Merged is none of these** (audit §4); nothing in this
  document converts a merge, a design chapter, or upstream code into a runtime
  claim.

**Plan-only.** This document is a plan. It implements nothing, deploys nothing, and
changes no memory provider. For the avoidance of doubt: **no memory provider is
active anywhere this audit could observe** (`docs/memory-ground-truth-audit.md` §3
— `~/.hermes` absent, no vault service, nothing serving; the contract's own Gaps
table marks the vault service, retrieval stack and capture/distill runners
design-only, `docs/memory-contract.md:265-275`). Every work package in §4 is gated
and none is authorized by this document; the controlled trial in §3 is *designed*
here, declared before any run, and not executed.

---

## 1. Gap analysis

Two demand sets are mapped against Hindsight at the pinned revision: (a) the
capabilities the memory architecture needs per the contract
(`docs/memory-contract.md`, `rizzstack.memory/1`), and (b) the failure classes the
campaign actually observed and recorded. The audit's five-level ladder classifies
each row honestly.

### 1.1 Capabilities the memory architecture needs

Derived from the contract chapter, cited by section. The contract's own Gaps table
(`docs/memory-contract.md:265-275`) already splits implemented-as-reference-oracle
from design-only; that split is repeated in the "contract side today" column
below, because the oracle
([`tests/test_memory_contract.py`](../tests/test_memory_contract.py), 61 tests, 4
skipped for missing `jsonschema`, green locally on this clone) implements the
*rules* in memory, not the vault service.

| ID | Capability the architecture needs | Contract anchor |
|---|---|---|
| C1 | Capture: hooks write session digests to `sessions/`; digests are source material, never served as knowledge | §The vault layout (`docs/memory-contract.md:53-73`), §Memory types (`:75-117`), worked example `:198-205` |
| C2 | Distill: a documented beat promotes digests into typed memories with named sources, supersedes older ones, or logs keeping nothing; no timer writes, no hook promotes its own capture | §Retention discipline (`docs/memory-contract.md:227-234`) |
| C3 | Provenance: 1–12 `sources[]` entries of kinds `session-digest`/`operator-note`/`pull-request`/`file`/`tool-output`/`external`; a memory with no source is refused; a raw transcript is never a source | §Memory types and frontmatter (`docs/memory-contract.md:112-117`) |
| C4 | Typed memory records: six types (`decision`, `learning`, `pitfall`, `env-fact`, `project-state`, `reference`), one file per memory, type→directory mapping enforced | §The vault layout, §Memory types (`docs/memory-contract.md:53-117`) |
| C5 | Read with drift detection: `read(path, expected_sha)`; mismatching digest warns the reader the file moved | §The contract surface (`docs/memory-contract.md:36-51`) |
| C6 | Query: ranked hits with `id/type/path/title/sha/score/snippet`, `mode_used` naming the engine that actually ran, `include_expired` opt-in | §The contract surface (`docs/memory-contract.md:36-51`), §Retention (`:209-212`) |
| C7 | Write receipts: every accepted write, expiry and promotion recorded in the append-only `log.md` with a sequence number; `vault_rev` changes only when the reconciled view changes | §The vault layout (`docs/memory-contract.md:66`), §Brief injection (`:188` `vault_rev`) |
| C8 | Multi-writer conflict safety: `expected_sha` create/update rules; stale digest refused with `sha_conflict`, `current_sha` named, `reread_required`; self-inconsistent digest refused as `sha_mismatch` | §The digest and the sha guard (`docs/memory-contract.md:119-138`) |
| C9 | Quarantine by default + authority grants: a writer without a grant may only write `.quarantine/<writer-slug>/`; outside writes need a durable `grant_ref`; curated zones require a **human** approver; service-owned paths unwritable through the surface | §The write contract (`docs/memory-contract.md:140-164`) |
| C10 | Brief injection: the dispatch-brief path gains a memory-context step; the worker receives typed, digest-pinned excerpts under hard caps (≤8 items, ≤480 chars/excerpt, ≤4000 total), honest empty when nothing is relevant | §Brief injection (`docs/memory-contract.md:166-196`) |
| C11 | Retention decided at write time: per-type policies (`decision-permanent`, `learning-until-superseded`, `pitfall-until-fixed`, `env-fact-until-fix`, `project-state-until-done`, `reference-refresh`); schema enforces type↔policy pairing both ways; expired hidden unless opted in | §Retention discipline (`docs/memory-contract.md:207-225`) |
| C12 | Hybrid local retrieval: SQLite FTS5 keyword leg + small local embedding leg + RRF fusion at `k = 60` | §Hybrid retrieval (`docs/memory-contract.md:236-248`) |
| C13 | Labeled degradation chain: `hybrid`→`keyword`→`grep` fallback; `mode_used` always names the engine that ran; a degraded result is labelled, never silent | §Hybrid retrieval (`docs/memory-contract.md:249-254`) |
| C14 | Local-only operation: no cloud services, no external calls at query time | §Hybrid retrieval (`docs/memory-contract.md:243-245`) |
| C15 | Vault rulebook: `VAULT.md` states layout, write zones, retention duties and scrubbing in vault-relative terms; maintained by the service, never written through the operation surface | §The rulebook comes first (`docs/memory-contract.md:27-34`) |
| C16 | Scrubbing: no credential, environment file or private endpoint ever stored; scrubbing before write, enforced by the verify gate over the repo itself | §What the vault must never store (`docs/memory-contract.md:256-263`) |

### 1.2 The campaign's observed failure classes

Only classes with recorded observations are listed. This is the demand side that
justifies (or fails to justify) a memory layer.

| ID | Observed failure class | Record |
|---|---|---|
| F1 | **Scheduler/tick stopped; resume by owner nudge.** The Jackpot build had no resident tick; six owner nudges performed the resume, totaling 1 h 9 m 39 s of recorded silence. Pauses were turn-ends, not stuck workers. | `docs/31-campaign-continuity.md:21-32` (§31.1 table), classification `:56-75` |
| F2 | **Campaign-level state had nothing durable to reconcile.** 22 lease files named `mojomast/jackpotsyndicate`; the job directory held 15 `smoke-*` job documents, no Jackpot job document, no campaign entry — so every restart reconstructed progress from leases, Git and chat. | `docs/31-campaign-continuity.md:48-54` (§31.1), counted in the durable store per `ground_truth.json → systems[campaign-records-store]` |
| F3 | **Specification failure: an acceptance selection unusable at the pinned revision** (injected: a named test id that does not exist), classified, superseded once, re-dispatched; the recovery protocol's five classes and sealed envelope govern. | `docs/24-autonomy-dogfood.md:32-47` (§2), `docs/27-recovery-protocol.md:32-60` (five failure classes) |
| F4 | **Visual/evidence-class gap: a DOM assertion is not visual acceptance.** The campaign's authored art was only caught by browser measurement; task-graph 100% was mistaken for acceptance once. | `docs/30-campaign-closeout.md:67-74` (§3.3), `:24-34` (§1 table) |
| F5 | **Workbench crash mid-wave leaves a stale lease**; the next attempt reconstructed state from chat scrollback instead of a durable diagnosis. | worked example, `docs/memory-contract.md:99,198-205` |
| F6 | **Manufactured acceptance / rubber-stamp risk.** Failure modes retained: a verified patch integrated without RED evidence; success reported without running the combined suite; the injected failure "recovered" by editing the contract to match the output. | `docs/24-autonomy-dogfood.md:206-214` (§8) |
| F7 | **In-turn failure knowledge evaporates.** Real build failures were handled inside turns and preserved only in the record — e.g. the reverted symbol-dedupe experiment — with no path back into later briefs. | `docs/31-campaign-continuity.md:66-68` (§31.1 classification) |

### 1.3 What Hindsight at `b92ceb180` provides

The mechanism report is the inventory; only the mechanisms the gap rows below
actually lean on are restated, each with its anchor. Class labels
(deterministic / LLM / specialized-model) are the report's
(`docs/hindsight-mechanism-report.md` §6).

- **Chunking + LLM fact extraction** (turn-boundary for JSONL transcripts,
  5-dimension `what/when/where/who/why` facts, retry-by-bisect):
  `docs/hindsight-mechanism-report.md` §2.1
  (`engine/retain/fact_extraction.py:776-841`, `:1083-1143`, `:2081`, `:318-349`).
- **Fact typing** `world`/`experience` (`assistant→experience`), `observation`
  derived only by consolidation: §2.2 (`fact_extraction.py:1111-1117`, `:2304-2313`,
  `consolidator.py:10-11`).
- **Entity resolution** (deterministic trigram + co-occurrence + recency scoring,
  label taxonomy exempt from fuzzy merge): §2.3
  (`engine/memories/pg/entity_resolver.py:1163-1378`, `:1230-1267`).
- **Event date vs ingest date**: §2.4 (`fact_extraction.py:1120-1131`, `:2457-2459`).
- **Links**: causal (`caused_by`, earlier-facts-only), semantic (ANN), temporal
  (K-nearest with decay): §2.5 (`engine/memories/pg/links.py:445-660`, `:934-1045`).
- **Source association + document identity**: full-replace / delta / append,
  chunk-hash dedup, crash recovery from committed chunk hashes, changed/deleted
  source sweeps: §2.6 (`engine/retain/fact_storage.py:191-321`, `:146-188`,
  `engine/retain/orchestrator.py:3964-3981`).
- **Bad-fact correction**: `invalidate_memory`/`restore_memory` snapshots and
  re-materialization: §2.6 (`engine/memories/pg/writes.py:421-459`).
- **Consolidation** (facts→observations): scope-grouped batches, one LLM call per
  ≤8 facts, per-fact verdicts, time rule (older fact = earlier state, never
  overwrite), exact-text + 0.97-cosine dedup with LLM adjudication, evidence
  history (`proof_count`, bounded `observation_history`), decision-model triage
  (restates/chatter) with fallbacks, staleness as derived signal: §3.1-3.7
  (`consolidator.py:2027-2043`, `:2711-3278`, `:3365-3410`, `:3512-3519`;
  `prompts.py:96-144`; `triage.py:1-246`).
- **Recall**: 4 arms (semantic, BM25, graph, temporal) → RRF (`k=60`) → rerank
  (cross-encoder; decision-model reranker; RRF passthrough for slim deployments) →
  combined scoring (recency/temporal/proof boosts) → rank-ordered token budgets
  with a never-empty floor; citation validation; labeled degradation paths: §4
  (`engine/memories/pg/recall.py:29-114`, `engine/search/fusion.py:29-109`,
  `engine/search/reranking.py:179-309`, `engine/fact_budget.py:43-87`,
  `engine/source_facts.py:31-105`).
- **Reflection**: hierarchical retrieval (mental models → observations → raw
  facts), decision-orchestrated rounds with sufficiency scoring, delta mental-model
  refresh via 8 typed structured ops (unmentioned blocks copied verbatim; parse
  failure ⇒ zero changes), retraction partitioning, staleness computation: §5
  (`engine/reflect/agent.py:1-8`, `engine/reflect/delta_ops.py:133-214`, `:16-39`,
  `engine/reflect/retractions.py:112-134`,
  `engine/memory_engine.py:21553-21610`).
- **Deployment**: Postgres + pgvector required for the API server (managed
  extension set, schema-pinned), or the `hindsight-embed` embedded Postgres
  (`pg0`) daemon on localhost:8888; Hermes memory-provider plugin with
  multibank + retain durability; coding-agents hooks plugin; worker queue with
  backpressure; MIT throughout: §7 (`hindsight_api/_pg_extensions.py:41-52`,
  `hindsight-embed/README.md:1-12`,
  `hindsight-integrations/hermes/__init__.py:416-448`, `:85-91`,
  `worker/poller.py:629-760`, `worker/backpressure.py:1-116`).
- **Cost shape**: extraction is the dominant token consumer (one call per
  ~3000-char chunk); consolidation is the dedup payoff; recall is deterministic
  and budgeted; reflect is the premium path; the decision model is optional and
  everything degrades without it: §8-9 (`config.py:1971-1972`, `:2138-2152`,
  §9 items 1-5).
- **Verified non-goals**: no embedded LLM; observations never written by retain;
  consolidation cannot author text from a triage verdict; delta refresh cannot
  corrupt prose; recall never silently drops the only match: §10
  (`engine/llm_wrapper.py:1060-1092`, `consolidator.py:10-11`, `triage.py:10-14`,
  `delta_ops.py:16-39`, `fact_budget.py:76-85`).

### 1.4 Capability ↔ mechanism gap table

**How to read the level columns.** *Level today* is the highest rung of the
audit's ladder the current evidence supports **for the rizzstack stack** — before
any adoption. *Ceiling after a green trial* is the highest rung §3's trial could
honestly support **for the trial's scope** if every gate passes; anything higher
(fleet-wide DEPLOYED, sustained VERIFIED-IN-OPERATION) needs later, named
deployments. The ladder's INTEGRATED definition is exactly what the trial's
archived cross-component artifacts would satisfy
(`docs/memory-ground-truth-audit.md` §4: "real cross-component artifacts archived
in an inspected repo"). Upstream Hindsight code is *code-verified at a pinned
revision* by the mechanism report — that is evidence about upstream, not about
the stack; it never lifts a stack row above SPECIFIED on its own.

Coverage vocabulary: **direct** = the mechanism supplies the capability as-is;
**adapt** = the mechanism supplies a different-shaped solution that an adapter or
the contract surface must translate; **partial** = covers part of the need;
**none** = no mechanism addresses it.

| Need | Hindsight mechanism (pinned rev) | Coverage | Level today | Ceiling after a green trial |
|---|---|---|---|---|
| C1 capture (hooks → `sessions/`) | SessionStart/Stop hooks inject memory and retain turns automatically; JSONL chat backfill under a `conversation` strategy (`hindsight-integrations/coding-agents/README.md:1-20`, `src/core/chat.ts:48-63`; report §7.4) | adapt (Hindsight retains into its own store; the contract wants files in `sessions/` — a capture shim writes both) | SPECIFIED | INTEGRATED (canary artifacts archived) |
| C2 distill (digest → typed memory) | Consolidation distills raw facts into deduplicated observations with verdicts, triage and history (`consolidator.py:2711-3278`; report §3) | adapt (observations ≠ contract memory records; promotion gate needed, §2 Option C) | SPECIFIED | INTEGRATED |
| C3 provenance | Observations carry `proof_count`, `source_memory_ids`; recall returns `source_fact_ids` resolved under a token budget (`consolidation.py:342-361`, `source_facts.py:31-105`; report §3.5, §4.4) | adapt (ids → the contract's `sources[]` kinds; transcript-derived facts must map to `session-digest` refs, never raw scrollback) | SPECIFIED | INTEGRATED |
| C4 typed records (six types, type→dir) | Fact typing is `world`/`experience` (+ derived `observation`); no decision/pitfall/env-fact taxonomy (`fact_extraction.py:2304-2313`; report §2.2) | partial — typing exists but the taxonomy differs; the contract's types stay contract-side | SPECIFIED | INTEGRATED |
| C5 read with drift detection | Not an operation; Hindsight serves recall results, not file reads. Document identity exists for ingest (`fact_storage.py:191-321`; report §2.6) | none (stays contract-side) | SPECIFIED (contract ops implemented as the reference oracle, `docs/memory-contract.md:270`) | IMPLEMENTED+TESTED (vault service built) |
| C6 query (ranked hits, `mode_used`) | 4-arm retrieval + RRF + rerank + combined scoring with per-strategy boosts (`recall.py:29-114`, `fusion.py:29-109`, `reranking.py:179-309`; report §4.1-4.3) | adapt (richer than the contract requires; `mode_used` must be derived from the strategy actually run) | SPECIFIED | INTEGRATED |
| C7 write receipts (`log.md`, `vault_rev`) | No analog; the store is Postgres, not a receipt log (`engine/memories/pg/retain.py:253-284`; report §2.6) | none (stays contract-side) | SPECIFIED | IMPLEMENTED+TESTED |
| C8 sha guard | No analog at the operation level; consolidation instead resolves contradictions between facts and observations (`prompts.py:102-133`, `:139-144`; report §3.3-3.4) | none (different mechanism for a different problem; both can coexist) | SPECIFIED | IMPLEMENTED+TESTED |
| C9 quarantine + grants | Closest analog is the memory-defense extension, which can reject retain content wholesale (`orchestrator.py:56-72`, `:351-457`; report §2.6) — reject, not zone; no grants, no human-only curated gate | none (stays contract-side) | SPECIFIED | IMPLEMENTED+TESTED |
| C10 brief injection (caps, digest-pinned, honest empty) | Recall budgets are rank-ordered with a never-empty floor; provenance budget fills `source_facts`; token caps per call (`fact_budget.py:1-18`, `:43-87`, `source_facts.py:1-105`; report §4.4) | adapt (budget shape matches the contract's caps; the envelope, honest-empty and digest-pinning are contract-side) | SPECIFIED | INTEGRATED |
| C11 per-type retention duties | No per-type policy table; staleness is derived (`updated_at` edit signal, in-flight batch discard, mental-model staleness computation) (`retain.py:326-331`, `memory_engine.py:21553-21610`; report §3.7, §5.5) | partial (supersession-by-evidence instead of declared duties; expiry semantics differ) | SPECIFIED | IMPLEMENTED+TESTED |
| C12 hybrid retrieval (FTS5 + local embeddings + RRF k=60) | Direct: semantic + BM25 in one UNION query, RRF at k=60, embeddings via pluggable providers incl. local (`recall.py:29-114`, `fusion.py:29-109`, `embeddings.py:2583-2846`; report §4.1, §4.2, §7.6) | direct | SPECIFIED | INTEGRATED |
| C13 labeled degradation chain | Direct in spirit: BM25 failure → semantic-only; missing `pg_trgm` → degraded strategy with warning; temporal failure → no constraint; CE failover chains; RRF passthrough keeps recall alive without neural reranking (`recall.py:235-250`, `entity_resolver.py:733-746`, `temporal_extraction.py:100-115`, `cross_encoder.py:1693-1729`; report §4.6) | direct | SPECIFIED | INTEGRATED |
| C14 local-only query time | Local SentenceTransformers embeddings/rerankers exist; but the default recall path embeds via a configured provider and LLM calls are provider calls (`embeddings.py:2583-2846`, `llm_wrapper.py:1060-1092`; report §7.6, §10) | partial (local-only is achievable with the `local`/`onnx` providers but is not the default posture) | SPECIFIED | INTEGRATED |
| C15 `VAULT.md` rulebook | No analog | none (stays contract-side) | SPECIFIED | IMPLEMENTED+TESTED |
| C16 scrubbing | Retain fact filter extension hook can drop secrets/noise before embedding (`orchestrator.py:1496-1535`; report §6) | adapt (the verify gate stays the normative scrubber per the contract; the filter is defense-in-depth) | SPECIFIED | INTEGRATED |

**Non-coverage statement.** Hindsight supplies no analog for the contract's
operation surface itself (C5, C7), its conflict-safety semantics (C8), its
quarantine/grant authority model (C9), its rulebook (C15), or its per-type
retention *duties* as declared policy (C11, only derived staleness). Any option
that adopts Hindsight must keep those contract-side — this is the structural
argument for the hybrid option in §2.

### 1.5 Failure-class coverage map

| Failure class | What the memory layer must do | Contract mechanism | Hindsight mechanism | Closed by |
|---|---|---|---|---|
| F1 tick stopped / nudge-resume | The last completed action and next action survive the turn in a queryable, non-chat form | `project-state` memories + injection (C10), `docs/memory-contract.md:62,166-196`; what must be durable is enumerated in `docs/31-campaign-continuity.md:77-98` | Retain of campaign checkpoint documents + recall on resume; temporal arm answers "what changed since the last release"-class queries (`links.py:445-660`, `recall.py:382-700`; report §2.5, §4.1) | B and C; A never |
| F2 no durable campaign state (22 leases / 15 job docs) | Distill per-lease evidence into `project-state`/`learning` memories with sources; never serve chat scrollback | C2+C3 (`docs/memory-contract.md:227-234`, `:112-117`) | Consolidation folds N near-identical facts into one evidence-backed observation with history (`consolidator.py:2711-3278`, `:3365-3410`; report §6 "High/high" row) | B (manual beat) and C (engine-backed) |
| F3 specification failure → supersession | The superseded selection and its correction become a `pitfall`/`decision` memory so the failure is not re-introduced | C2+C11 supersession (`docs/memory-contract.md:216-218`) | Contradiction handling: `changes`/`ends` rewrite with a stale-observation guard making older facts "earlier state" (`prompts.py:102-133`, `:139-144`; report §3.4) — the engine-side twin of supersession | B and C; A leaves the knowledge in chat only |
| F4 visual-acceptance gap | The "DOM assertion ≠ visual acceptance" lesson persists and is injected into future visual tasks | `pitfall` memory + injection (C4, C10) | Observations carry evidence history and `proof_count` so a corroborated pitfall ranks up (`reranking.py:289-299`; report §4.3) | B and C |
| F5 stale lease after crash | The recovery digest becomes a durable learning; the recovery brief injects it digest-pinned | worked example, `docs/memory-contract.md:198-205`; recovery protocol INTEGRATED per `ground_truth.json → systems[recovery-digests]` | Crash-adopted retains recover from committed chunk hashes; append/delta keep session turns cheap (`retain.py:87-108`, `orchestrator.py:3964-3981`; report §2.6) | B and C |
| F6 manufactured acceptance / rubber-stamp | Provenance and quarantine make unverifiable "knowledge" structurally hard to write into trusted zones | C3+C9 (`docs/memory-contract.md:112-117`, `:140-164`) | Observation history records every change with sources (`consolidator.py:3365-3410`; report §3.5) — an audit trail, not an authority gate | B (authority is contract-side); C adds the history trail |
| F7 in-turn failure knowledge evaporates | Session-close distillation duty turns in-turn experiments into memories or consciously drops them | C2 (`docs/memory-contract.md:227-234`) | Auto-consolidation after retain (gated by `enable_auto_consolidation`, `config.py:4011`; report §3.1) automates the promotion path — but see §2 Option C's promotion-gate rule | B (manual beat only); C automates upstream of the gate |

### 1.6 Honest limits of the mapping

- Nothing above is evidence of integration. The audit found zero `rizzstack.memory`
  artifacts in any audited default branch at audit time
  (`docs/memory-ground-truth-audit.md` §6.1); in this checkout the contract
  chapter, schema, protocol row and oracle exist (`docs/protocol.md:29,33-41`,
  `schemas/memory-schema.v1.json:20`), and the oracle runs green here (61 tests,
  4 skipped for absent `jsonschema`) — that is IMPLEMENTED+TESTED for the *rules*,
  while the vault service remains design-only (`docs/memory-contract.md:272-274`).
- The audit's stale-head lesson applies to this synthesis too: heads and CI were
  verified on 2026-11-16 and can change (`docs/memory-ground-truth-audit.md` §1,
  §2). The pinned Hindsight revision does not drift; upstream main does.
- The mechanism report's §11 shows upstream docs overclaim relative to code in
  known places (version string vs tag distance; unbounded JSONB history;
  benchmark numbers vendor-reported). This synthesis cites code anchors, not
  marketing, and treats the coding-agents README benchmark numbers as claims, not
  measurements (`docs/hindsight-mechanism-report.md` §11).

---

## 2. Adoption options

Four options, as the brief requires (none / contract-only / hybrid / full). For
each: what ships, integration points, ops cost, justifying evidence, failure
classes closed, the ladder ceiling it could reach after a green trial, and
residual risk. **None of these is authorized by this document.**

### Option A — none

- **What ships:** nothing. `rizzstack.memory/1` stays a draft contract with an
  in-memory oracle; no vault service, no capture, no distillation, no injection.
- **Integration points:** none. The dispatch-brief path keeps no memory-context
  step (`docs/memory-contract.md:166-196` never ships).
- **Ops cost:** zero new infrastructure. The recurring cost is the one the
  campaign already paid: reconstruction from leases, Git and chat on every
  coordinator turn (`docs/31-campaign-continuity.md:48-54`), and failure
  knowledge that lives and dies inside turns (`:66-68`).
- **Justifying evidence:** the audit's `memory-contract` row is SPECIFIED and
  unmerged at audit time (`ground_truth.json → systems[memory-contract]`);
  `~/.hermes` and every rizzstack service are absent in the audited environment
  (`docs/memory-ground-truth-audit.md` §3). With no operator-observed memory
  pain quantified beyond §1.2, "none" is a legitimate default until the trial
  says otherwise.
- **Failure classes closed:** none (F1–F7 all remain open).
- **Ceiling:** n/a — nothing changes, so no row moves.

### Option B — contract-only (the trial's baseline)

- **What ships:** the vault service exactly as the contract specifies:
  read/query/write over a plain markdown vault, `log.md` receipts, `vault_rev`;
  SQLite FTS5 + local embeddings + RRF `k=60`; the labeled
  `hybrid→keyword→grep` fallback; capture hooks writing `sessions/` digests; the
  distillation beat; brief injection with the contract's caps; the sha guard,
  quarantine, grants, `VAULT.md` rulebook and verify-gate scrubbing as
  normatively defined (`docs/memory-contract.md:36-286`).
- **Integration points:** (1) dispatch-brief `memory_context` step
  (`docs/memory-contract.md:166-196`); (2) session-close capture hook writing
  `sessions/` digests (`:63`); (3) the distillation beat at session close and
  campaign closeout (`:227-234`); (4) verify-gate scrubbing over the vault
  itself (`:256-263`); (5) the protocol row (`docs/protocol.md:29`).
- **Ops cost:** one SQLite database and a small local embedding model on the box
  that holds the vault; no always-on service beyond the vault process; LLM spend
  limited to the distillation beat (bounded by digest count per session); no
  Postgres, no worker fleet, no new network surface.
- **Justifying evidence:** the contract defines every shape and duty with a
  normative oracle for the semantic half (`docs/memory-contract.md:270-286`);
  the hybrid stack, caps, fallback chain and per-type retention are already
  specified in the contract text itself (`:207-254`). Feasibility precedent for
  the *shape* (not the code) is the mechanism report's cost analysis: recall at
  this scale is deterministic and budgeted (`docs/hindsight-mechanism-report.md`
  §9 item 3, `fact_budget.py:43-87`).
- **Failure classes closed:** F1–F6 partially (all through a manual distillation
  beat: C1–C16 satisfied as designed); F7 closed by the beat's duty, which is
  only as good as the beat runs.
- **Ceiling:** INTEGRATED for the injection/receipt rows once the trial archives
  cross-component artifacts; VERIFIED-IN-OPERATION only for the canary scope.
- **Residual risk:** distillation quality rests entirely on the beat's judgment
  without engine support — no entity resolution across projects, no
  contradiction handling beyond `superseded_by`, no semantic dedup
  (`docs/memory-contract.md:216-218` has no merge machinery); repeated
  near-identical learnings can accumulate unless the beat is disciplined.

### Option C — hybrid (recommended for trial as treatment)

- **What ships:** two layers. The **contract vault remains the curated,
  agent-agnostic authority** (all of C4–C9, C11, C15, C16 as in Option B).
  Hindsight (`hindsight-api-slim` server + worker, or `hindsight-embed`'s
  embedded Postgres for a first deployment) runs **behind** it as the episodic
  engine: session digests and durable campaign records are retained to a
  per-project bank; consolidation distills them into observations with dedup,
  contradiction handling and evidence history; recall's arms + fusion + scoring
  produce the injection candidates; the contract surface translates them into
  digest-pinned `memory_context` items. Promotion into curated zones
  (`concepts/`, `decisions/`, `hot.md`, `index.md`) happens **only** through the
  contract's grant path — human-approved for curated zones
  (`docs/memory-contract.md:158-164`); Hindsight never writes the vault
  directly.
- **Integration points:** (1) retain source of record = `sessions/` digests and
  the durable campaign checkpoint fields (`docs/31-campaign-continuity.md:77-98`)
  — never raw scrollback (C3's rule, `docs/memory-contract.md:115-117`);
  (2) recall feeds the injection step's candidate pool; `mode_used` is derived
  from the strategy actually run, degrading along the same labeled chain
  (report §4.6); (3) observations' `source_memory_ids`/`source_fact_ids` map to
  the contract's `sources[]` kinds (report §3.5, §4.4); (4) mental-model pages
  (per-project architecture/conventions/in-flight pages, report §7.4) serve as
  **draft material** for promotion, never as the vault's curated files themselves;
  (5) the coding-agents-style hooks pattern is the capture precedent
  (`hindsight-integrations/coding-agents/README.md:1-20`).
- **Ops cost:** a Postgres with pgvector   (or the embedded `pg0` instance under
  `~/.pg0/`, `hindsight-embed/hindsight_embed/cli.py:19`, `:601-608`) plus a worker process;
  extraction is the dominant token cost (one call per ~3000-char chunk,
  `config.py:1972`), consolidation adds one call per ≤8 facts
  (`config.py:2138-2148`); the RRF passthrough reranker and an unset decision model
  keep the recall path cheap (`cross_encoder.py:1693-1729`; report §4.6, §9
  item 5). No cloud is required at query time if the `local`/`onnx` embedding
  providers are chosen (`embeddings.py:2583-2846`).
- **Justifying evidence:** the mechanism classification table scores
  consolidation "High value / high complexity", 4-arm+RRF "High / low", combined
  scoring "High / low", delta refresh "High / medium" for exactly this
  coding-agent-factory workload (`docs/hindsight-mechanism-report.md` §6); the
  dedup payoff analysis (§9 item 2) is the argument that a factory skipping
  consolidation loses cross-session density. The audit supplies the demand side:
  F2's 22-leases/15-jobs mismatch and F7's evaporating in-turn knowledge are the
  exact classes consolidation addresses (`ground_truth.json →
  systems[attempt-records]`, `docs/31-campaign-continuity.md:48-54,66-68`).
- **Failure classes closed:** F1–F7, with F2/F3/F7 materially stronger than B
  (dedup, contradiction handling, entity continuity are engine work the beat
  would otherwise do by hand).
- **Ceiling:** INTEGRATED for adapter rows and the injection row after a green
  trial; VERIFIED-IN-OPERATION for the canary scope itself.
- **Residual risk:** two stores to operate and keep consistent; the promotion
  gate is the single safety hinge (if it loosens, engine output reaches trusted
  zones without a human); Postgres is a new runtime dependency for a stack where
  nothing rizzstack is deployed anywhere observable (`docs/memory-ground-truth-audit.md`
  §6.6); LLM spend becomes continuous rather than beat-bounded (mitigated by
  §3's cost gate).

### Option D — full (Hindsight as the memory layer)

- **What ships:** Hindsight end-to-end via the Hermes memory-provider plugin
  (`local_embedded` or `local_external` mode; `hermes/__init__.py:649-686`,
  `_LOCAL_MODES :84`; report §7.3), with the coding-agents hooks plugin for
  capture (report §7.4). The contract surface is retired or reduced to a shim.
- **Integration points:** Hermes config resolution with secret-scoped
  isolation-critical values (`hermes/__init__.py:416-448`, `:110-131`);
  multibank write/recall banks per project (`:85-91`); retain durability via the
  single-writer queue with backlog limits (`:291-303`, `:566-581`); recall
  shaping knobs (`:811-884`).
- **Ops cost:** highest of the four (same engine infra as C, plus plugin
  lifecycle and per-profile isolation); but it *gives up* normative properties
  the campaign's own governance relies on: the agent-agnostic envelope, the
  sha-guard refusal semantics, quarantine/grants and the human-only curated gate
  (`docs/memory-contract.md:47-51,119-164`), the per-type retention duties
  (`:207-225`), the `log.md` receipt discipline, and the gate-exact scanner
  self-scan culture (`:277-286`). Hindsight's equivalents — consolidation-level
  contradiction resolution, memory-defense rejection, derived staleness — are
  *different mechanisms for adjacent problems* (report §3.4, §2.6, §3.7), not
  drop-ins for refusals the workflow's verify gate and audit culture expect.
- **Justifying evidence:** the mechanism report's §7.3 documents the exact
  integration path and its durability tests (`tests/test_retain_durability.py`,
  `tests/test_multibank.py:140-344`); §5 documents mental-model pages as the
  per-project knowledge surface. The counter-evidence is §1.6: no analog for
  C5/C7/C8/C9/C15, and C11 only partially.
- **Failure classes closed:** F1–F7 engine-side, but F6 *weakens*: authority
  moves from refusals the stack can verify to engine hygiene.
- **Ceiling:** INTEGRATED at best after a trial; and the contract row
  (`rizzstack.memory/1`) would be marked superseded — a normative decision this
  document does not make.
- **Residual risk:** highest governance risk, highest ops cost; rejected as the
  trial's treatment on governance grounds, retained as an option only if the
  trial shows the contract surface itself adds no value at the canary scale.

### 2.5 Comparison and the recommendation the document actually makes

| | A none | B contract-only | C hybrid | D full |
|---|---|---|---|---|
| New infra | none | SQLite + local embeddings | Postgres/pgvector + worker | same as C + plugin lifecycle |
| New token spend | none | distillation beat only | extraction + consolidation (continuous) | same as C |
| F1–F7 closed | none | partial (manual beat) | yes (engine + gate) | yes engine-side, F6 weakened |
| Governance surface preserved | n/a | full contract | full contract + promotion gate | contract retired |
| Ceiling after a green trial | — | INTEGRATED (canary scope) | INTEGRATED (canary scope) | INTEGRATED (canary scope) |

**This document recommends a trial between B (baseline) and C (treatment), with
A as the secondary control — not an adoption.** The recommendation is the trial
itself; the adoption decision belongs to the receiver after §3's evidence exists
(the same always-pending receiver discipline as
[`docs/26-return-manifest.md`](26-return-manifest.md) and the M2 canary's Step 12,
`docs/m2-canary-runbook.md:561-572`). Option D is recorded and declined for the
trial on governance grounds (rejected alternative, per the planning rule in
`docs/24-autonomy-dogfood.md:61-78`).

---

## 3. Controlled trial design

**Declared before any run.** Every threshold in §3.3 was written in this document
and committed on the branch carrying it **before** any canary run exists. At the
time of writing no `evidence/*memory-canary*` directory exists in this tree, no
canary project or packet exists, and no memory provider is active anywhere
observable (`docs/memory-ground-truth-audit.md` §3). Any later change to these
thresholds is a new declaration, never a retroactive one — the campaign's own
rule for injected failures and budgets (`docs/24-autonomy-dogfood.md:32-47`,
`:80-93`) and the closeout rule that a report is a reviewable claim, not proof
(`docs/31-campaign-continuity.md:212-217`).

### 3.1 Question and hypothesis

- **Question:** does a memory layer measurably reduce the campaign's recorded
  failure classes, and does the Hindsight-backed hybrid (C) beat the
  contract-only vault (B) at it?
- **Baseline (fixed by the brief):** Option B — the contract-only vault service,
  complete per `docs/memory-contract.md`, running the same fixtures.
- **Treatment:** Option C — the same contract surface with Hindsight behind it
  as the episodic engine (§2 Option C).
- **Secondary control:** Option A — no memory layer, same fixtures, to test
  whether any memory layer earns its keep at all.
- **H1 (primary):** on the restart fixture, the treatment arm's coordinator
  state-reconstruction cost (tokens + turns, measured from durable records) is
  ≥50% lower than the baseline arm's, with zero reconstruction events sourced
  from raw chat scrollback.
- **H2:** on the supersession-recall fixture, the treatment arm serves the
  corrected-selector pitfall into later-task briefs in ≥2 of 2 runs with ≤1
  wrong-pitfall intrusion per brief; the baseline arm is *not* required to match
  this (its beat may, but the engine's dedup/contradiction handling is the
  claimed difference, `docs/hindsight-mechanism-report.md` §9 item 2).
- **H3 (honesty, both arms, gate not differentiator):** every injected
  `memory_context` payload satisfies the contract's caps and provenance rules
  with 100% conformance — a single violation fails the arm regardless of quality
  metrics (`docs/memory-contract.md:166-196,112-117`).
- **H4 (cost gate):** the treatment arm's memory-layer token spend per canary
  run stays ≤2× the baseline arm's. Failing H4 fails the treatment on cost even
  if H1/H2 pass.

### 3.2 Arms, fixtures and machinery fit

The trial reuses the campaign's proven machinery rather than inventing new:

- **Canary pattern** ([`docs/m2-canary-runbook.md`](m2-canary-runbook.md)): one
  fresh dedicated project (`rizzstack-memory-canary`), one packet
  (`plans/packets/`-style) whose Authorization-needs section the approver signs;
  a prep self-check pinned by a test (M2 pattern:
  `docs/m2-canary-runbook.md:29-41`); blast radius confined to canary-named
  paths with production repos read-only (`:44-50`); a rollback/cleanup path that
  removes only canary-named state and verifies production untouched (`:612+`);
  a RETURN with the receiver decision left pending (`:539-572`).
- **Fixture set** (identical bytes across arms, seeded at the base revision, RED
  scaffolding per M2 Step 2, `docs/m2-canary-runbook.md:94-197`):
  1. A synthetic two-task feature with ACDD contracts, in the M4 dogfood's
     shape (`docs/24-autonomy-dogfood.md:17-30`).
  2. **Injected specification failure** (F3): T2's first contract names a test
     id that does not exist at the pinned revision; the loop must classify
     `specification`, supersede once, re-dispatch (`docs/24-autonomy-dogfood.md:32-47`;
     five classes per `docs/27-recovery-protocol.md:32-60`). Declared under
     `injected_failures` so nobody mistakes it for a real defect (`:44-47`).
  3. **Injected crash** (F5): a coordinator kill at a named boundary
     (`tick.after_dispatch`-class, `docs/24-autonomy-dogfood.md:142-156`) so the
     restart/recovery path runs and the recovery brief is built.
  4. **Injected visual criterion** (F4): an acceptance criterion whose DOM
     assertion passes while a screenshot check fails — reproducing the Jackpot
     lesson as a fixture (`docs/30-campaign-closeout.md:67-74`).
  5. A **later task touching the same surface**, dispatched after the first
     wave closes, to measure pitfall recall (H2) without any hint in its brief
     that the pitfall exists.
- **Proof levels** per `docs/23-autonomy-devplan.md:32-47`: every deterministic
  gate (fixtures, injection honesty checks, caps enforcement, provenance,
  receipt integrity) is **Level A** — mandatory CI, no model call, no network
  beyond committed fixtures. The supervised runs with a real model and the real
  coordinator are **Level B** — recorded outside CI with durable state archived,
  env-gated, never claimed as CI proof (the M4.2/M4.3 discipline,
  `docs/24-autonomy-dogfood.md:117-140`).
- **Measurement discipline:** metrics come only from durable artifacts — tick
  records, brief payloads (`memory_context` fields), `log.md` receipts, the
  RETURN, the campaign checkpoint — never from chat transcripts
  (`docs/31-campaign-continuity.md:70-75` records why chat-derived measurement
  is uncertain). Token counts where the runtime reports them; cost stays
  UNKNOWN without a pricing feed (`docs/24-autonomy-dogfood.md:169`), so H4 is
  a token-budget gate, not a dollar gate.
- **Run shape:** per arm, one authorized canary run of the fixture set (bounded
  dispatch budget in the packet, as M4 authorized 4 dispatches,
  `docs/24-autonomy-dogfood.md:80-93`), then the later-task probe, then the
  restart fixture replay. Arms run on separate canary projects (or one project
  reset to the base revision between arms) so no arm's memory contaminates
  another's.

### 3.3 Metrics and thresholds (pre-registered)

| # | Metric (grounded in) | How measured | Baseline arm pass | Treatment arm pass | Fail (either arm) |
|---|---|---|---|---|---|
| M1 | Resume reconstruction cost (F1, F2) | tokens + coordinator turns spent re-deriving state after the injected crash, from durable tick records and brief payloads | reference measurement (no threshold; it defines the baseline) | ≥50% reduction vs baseline **and** zero reconstruction events citing raw chat scrollback | any reconstruction event sourced from scrollback (violates C1/C3's rule, `docs/memory-contract.md:63,115-117`) |
| M2 | Supersession/pitfall recall (F3) | whether the later-task brief's `memory_context` contains the corrected-selector pitfall; count of wrong-pitfall intrusions | informational (the beat may or may not promote it) | pitfall present in ≥2 of 2 probe briefs; ≤1 intrusion per brief | target pitfall missing in any probe brief, or intrusions >1 |
| M3 | Crash-digest injection (F5) | the recovery brief's `memory_context` contains exactly the recovery-digest-sourced learning, digest-pinned, within caps | 2 of 2 recovery briefs correct | same | any recovery brief without the item, or with an unpinned/wrong-digest item |
| M4 | Evidence-class pitfall injection (F4, F6) | the visual task's brief contains the visual-acceptance pitfall | ≥1 of 1 visual brief | same | pitfall absent |
| M5 | Injection honesty (C10, C3) — **gate** | caps (≤8 items, ≤480 chars/excerpt, ≤4000 total), every item digest-pinned, honest empty when nothing relevant, `mode_used` labels any degraded engine | 100% | 100% | any violation fails the arm outright |
| M6 | Write-path integrity (C7–C9) — **gate** | no unhandled `sha_conflict`, no quarantine escape, every accepted write in `log.md` with sequence number, curated-zone writes carry a human grant | 100% | 100% | any violation fails the arm outright |
| M7 | Provenance (C3) — **gate** | 100% of served memories carry ≥1 source; no raw transcript as source; scrubbing gate green over the vault | 100% | 100% | any violation fails the arm outright |
| M8 | Memory-layer token spend (cost) | tokens per retained session + tokens per recall, from runtime reports | reference measurement | ≤2× baseline per canary run | >2× fails the treatment on cost |

Non-metrics, declared: wall-clock "idle" gaps are **not** a success metric (the
Jackpot silences measured owner silence, not worker idleness,
`docs/31-campaign-continuity.md:30-32,70-75`); no benchmark number from the
coding-agents README may be used as a threshold (vendor-reported claim, report
§11); "task graph reached 100%" is explicitly not acceptance
(`docs/30-campaign-closeout.md:24-34`).

### 3.4 Decision rule

- **Adopt hybrid (C)** only if: M1, M2 pass for the treatment arm **and** M3,
  M4 pass for both arms **and** M5–M7 gates pass for both arms **and** M8 holds.
- **Keep contract-only (B)** if B passes its gates and C fails any of H1/H2/H4.
- **Adopt nothing (A)** if either arm fails a gate (M5–M7): a memory layer that
  violates its own contract is worse than none — the failure classes stay open
  and the options reopen.
- The decision is recorded as a receiver decision on the canary's RETURN, never
  by this document or any agent (`docs/26-return-manifest.md`; M2 Step 12,
  `docs/m2-canary-runbook.md:561-572`).

### 3.5 Blast radius, cleanup and honest failure

Production repositories are read-only for the trial; only canary-named state is
created and only canary-named state is removed, verified untouched otherwise
(M2 blast-radius and rollback sections, `docs/m2-canary-runbook.md:44-50,612+`).
A refusal that happens is a pass of that gate; a refusal that does not happen is
the finding — never invented metrics, never a run rounded up to a success
(`docs/m2-canary-runbook.md:593-605`, `docs/19-coordinator-playbook.md` §4 per
the runbook's citation). If a layer is unmerged or a host unavailable, the step
is recorded NOT RUN with its reason in the RETURN's `unrun` list, never folded
into a pass (`docs/m2-canary-runbook.md:604-605`).

---

## 4. Implementation plan (gated work packages)

**Format.** Each work package declares: the **gate** (the condition that must
already hold before it starts), the **deliverable**, and **proven-by
`path::test`** — the named test that proves it, in the campaign's Level A/B
vocabulary (`docs/23-autonomy-devplan.md:32-47`). A package whose test does not
exist and pass is not delivered, no matter what else merged — the audit's
"nothing is operational because a PR merged" rule applied to ourselves
(`docs/memory-ground-truth-audit.md` §4). **All packages are plan-only until the
§3 trial's receiver decision exists; none is authorized by this document.**

### Wave 1 — contract-only foundation (baseline arm; no Hindsight anywhere)

| WP | Gate | Deliverable | Proven by | Level |
|---|---|---|---|---|
| AC-101 | `rizzstack.memory/1` merged with its oracle green (it is, in this tree: `docs/protocol.md:29`, 61 tests OK/4 skipped) | Vault service core: `read`/`query`/`write` over disk, frontmatter parsing to the schema, refusals with named codes | `tests/test_memory_vault.py::test_read_query_write_round_trip_refuses_unknown_fields` | A |
| AC-102 | AC-101 | Digest + sha guard as a service: create/update rules, `sha_conflict` with `current_sha`+`reread_required`, `sha_mismatch` refusal | `tests/test_memory_vault.py::test_stale_digest_refused_with_reread_required` | A |
| AC-103 | AC-101 | Quarantine, grants and the human-only curated gate enforced by the service, `log.md` receipts with sequence numbers, `vault_rev` | `tests/test_memory_vault.py::test_curated_write_without_human_grant_refused` | A |
| AC-104 | AC-101 | Retrieval stack: SQLite FTS5 leg, local embedding leg, RRF k=60, labeled fallback chain `hybrid→keyword→grep` with `mode_used` | `tests/test_memory_vault.py::test_fallback_chain_labels_mode_used` | A |
| AC-105 | AC-101 | Retention enforcement: per-type policy pairing refused both ways, expiry evaluation, `include_expired` | `tests/test_memory_vault.py::test_type_policy_pairing_refused_both_ways` | A |
| AC-106 | AC-101 + verify-gate hooks available | Capture hook: session close writes a `sessions/` digest; nothing writes on a timer; no hook promotes its own capture | `tests/test_memory_capture.py::test_session_close_writes_digest_and_nothing_else` | A |
| AC-107 | AC-106 | Distillation beat: promote-with-source / supersede / log-keep-nothing; prune only consumed digests | `tests/test_memory_distill.py::test_beat_promotes_with_digest_source_and_logs_keeps` | A |
| AC-108 | AC-104 + brief pipeline accessible | Brief injection: caps (8/480/4000), digest-pinned items, honest empty, `vault_rev` | `tests/test_memory_injection.py::test_caps_honest_empty_and_digest_pinning` | A |
| AC-109 | AC-101–AC-108 | `VAULT.md` rulebook generated and maintained by the service; verify-gate scrubbing over the vault | `tests/test_memory_vault.py::test_rulebook_states_zones_and_scrubbing_holds` | A |

### Wave 2 — hybrid adapter (treatment arm; Hindsight at the pinned revision only)

| WP | Gate | Deliverable | Proven by | Level |
|---|---|---|---|---|
| AC-201 | Wave 1 delivered **and** the §3 trial authorized by the approver | Hindsight adapter, ingest side: `sessions/` digests + campaign checkpoint documents retained to a per-project bank; sources recorded so provenance survives | `tests/test_memory_hindsight_adapter.py::test_retain_maps_digests_to_sources` | A (adapter logic); the retain itself is exercised in the trial |
| AC-202 | AC-201 | Recall translation: 4-arm+RRF results → contract `query` shapes; `mode_used` derived from the strategy actually run; degraded engines labeled | `tests/test_memory_hindsight_adapter.py::test_recall_maps_to_query_result_with_mode_used` | A |
| AC-203 | AC-201 | Provenance translation: `source_memory_ids`/`source_fact_ids` → contract `sources[]` kinds; transcript-derived facts resolve to `session-digest` refs, never scrollback | `tests/test_memory_hindsight_adapter.py::test_sources_never_name_raw_transcripts` | A |
| AC-204 | AC-201 + grants implemented (AC-103) | **Promotion gate:** engine observations become contract memories only via the grant path; curated zones require a human approver; Hindsight never writes the vault directly | `tests/test_memory_hindsight_adapter.py::test_promotion_requires_grant_and_human_for_curated` | A |
| AC-205 | AC-201–AC-204 + local/onnx embedding provider selected | Local-only posture: query-time operation with no external calls; degradation labeled when the embedder is down | `tests/test_memory_hindsight_adapter.py::test_query_time_has_no_external_calls` | A |

### Wave 3 — the controlled trial (harness first, then the run)

| WP | Gate | Deliverable | Proven by | Level |
|---|---|---|---|---|
| AC-301 | §3.3 thresholds committed (this document) | Canary packet + runbook in the M2 pattern: authorization section, blast radius, cleanup, injected-failure declarations | `tests/test_memory_canary_prep.py::test_runbook_matches_packet_and_blast_radius` | A |
| AC-302 | AC-301 | Fixture set: synthetic feature + injected specification failure + crash boundary + visual criterion + later-task probe, byte-identical across arms | `tests/test_memory_canary_prep.py::test_fixtures_identical_across_arms` | A |
| AC-303 | AC-302 | Metric capture reading only durable artifacts (tick records, `memory_context` payloads, `log.md`, RETURN); no chat-derived metric | `tests/test_memory_canary_prep.py::test_metrics_read_durable_records_only` | A |
| AC-304 | AC-301–AC-303 + approver's yes | Level B supervised runs: baseline arm, then treatment arm, then secondary control, each recorded with durable state archived and the raw proposal kept | recorded outside CI in `evidence/<date>-memory-canary/` (Level B is never a CI claim, `docs/23-autonomy-devplan.md:40-47`) | B |
| AC-305 | AC-304 | Post-trial record: metric table filled from durable artifacts, decision rule applied exactly as §3.4 pre-registered, RETURN with pending receiver decision; `NOT RUN` steps disclosed | `tests/test_memory_canary_prep.py::test_report_thresholds_match_the_preregistered_table` | A (record shape); B (the runs it reports) |

### 4.1 Ordering and ownership

Wave 1 → Wave 2 → Wave 3, matching the dependency order: the adapter (Wave 2)
translates to and from the contract surface Wave 1 builds; the trial (Wave 3)
runs both. Bee-assignable work: AC-101, AC-104, AC-105, AC-106, AC-108 and the
adapter's translation tests (AC-202, AC-203) — patterned, lease-sized slices.
Coordinator-owned: AC-103 and AC-204 (authority and the promotion gate encode
who may write where — the exact class of rule the autonomy plan kept out of bee
hands, `docs/23-autonomy-devplan.md:130-133`), and every Level B run.

### 4.2 Explicitly out of scope (plan-only)

- No deployment of Hindsight anywhere; no Postgres/pgvector installation; no
  plugin enablement; **no change to the active memory provider — there is none
  active in any observable environment** (`docs/memory-ground-truth-audit.md` §3).
- No merge, tag, release, deploy or publish by this work; merges and the
  adoption decision are human gates (`docs/24-autonomy-dogfood.md:202-204`).
- No claim conversions: a green oracle stays "the rules are implemented"; only
  the trial manufactures INTEGRATED/VERIFIED-IN-OPERATION evidence, and only for
  the trial's scope.
- Multi-project/multibank operation beyond the canary's single bank,
  cross-machine operation, and fleet-wide rollout are explicitly deferred and
  never claimed (`docs/24-autonomy-dogfood.md:186-200` sets the honesty bar this
  plan keeps).

---

## 5. Sources

- `docs/memory-ground-truth-audit.md` §1 (what was inspected), §3 (runtime
  probes), §4 (the ladder), §5 (classification table; `memory-contract` row),
  §6 (findings), §8 (what Phase 2 must not assume); `ground_truth.json`
  (`classification_levels`, `systems[*]`, `constraints`).
- `docs/hindsight-mechanism-report.md` §1–§11, at pinned revision
  `b92ceb180e349a456d2b5454575067b6ff0f6306` (all `file:line` anchors above are
  transcribed from it).
- `docs/memory-contract.md` (chapter 32, all sections), `schemas/memory-schema.v1.json`,
  `tests/test_memory_contract.py`, `docs/protocol.md`.
- `docs/24-autonomy-dogfood.md`, `docs/23-autonomy-devplan.md`,
  `docs/27-recovery-protocol.md`, `docs/30-campaign-closeout.md`,
  `docs/31-campaign-continuity.md`, `docs/m2-canary-runbook.md`,
  `docs/26-return-manifest.md`.
