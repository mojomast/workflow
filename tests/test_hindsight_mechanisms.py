"""Conformance tests for docs/hindsight-mechanism-report.md (Phase 2 Hindsight brief).

The report must be a mechanisms report on the PINNED upstream revision
b92ceb180e349a456d2b5454575067b6ff0f6306 (v1.2.1) with file:line citations for every
required question. These tests validate the report structurally (sections present,
every section carries citations, classification and cost levers present, pinned
revision recorded) and — when an upstream checkout is available — verify that a
sample of citations resolves to real files with matching content anchors.

The checkout is located via, in order: $HINDSIGHT_CHECKOUT, the research brief's
canonical path, or ~/.hermes/cache/scratch/hindsight-research. When none exists the
source-anchoring checks SKIP rather than fail: the report itself is still fully
validated offline.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "hindsight-mechanism-report.md"

PINNED_REVISION = "b92ceb180e349a456d2b5454575067b6ff0f6306"

REQUIRED_SECTIONS = [
    "Architecture map",
    "Ingestion (retain): how a document becomes a fact graph",
    "Consolidation: facts → observations",
    "Retrieval (recall): 4 arms → fusion → rerank → budgets",
    "Reflection: the agent, mental models, delta refresh, retractions",
    "Mechanism classification and marginal value",
    "Deployment facts",
    "Cost analysis: what spends tokens, what doesn't",
    "Code vs docs claims",
]

# Per-question coverage the brief demands: each of these topics must be cited with
# at least one file:line reference inside the report text (anywhere, since sections
# cross-reference).
REQUIRED_CITED_TOPICS: dict[str, tuple[str, ...]] = {
    "retain fact extraction": ("fact_extraction.py:1083", "fact_extraction.py:2081"),
    "experience/world/observation typing": ("fact_extraction.py:2304", "consolidator.py:10"),
    "entity resolution + aliases": ("entity_resolver.py:1163", "entity_resolver.py:1370"),
    "event-date vs ingest-date": ("fact_extraction.py:2457", "fact_extraction.py:1120"),
    "causal/semantic link creation": ("links.py:934", "links.py:569"),
    "source association": ("fact_storage.py:191", "retain.py:253"),
    "dedup + changed/deleted sources": ("fact_storage.py:146", "fact_storage.py:266"),
    "bad-fact correction": ("writes.py:421", "causal_links.py:30"),
    "extraction cost/concurrency controls": ("memory_budget.py:92", "config.py:2022"),
    "observation grouping": ("consolidator.py:2027", "prompts.py:96"),
    "consolidation update rules": ("consolidator.py:3413", "consolidation.py:297"),
    "contradiction handling": ("consolidator.py:2900", "prompts.py:139"),
    "duplicate reconciliation": ("consolidator.py:3010", "consolidator.py:2883"),
    "evidence-history preservation": ("consolidator.py:3365", "consolidation.py:342"),
    "staleness detection": ("memory_engine.py:21553", "consolidator.py:3142"),
    "discard rules": ("consolidator.py:2190", "triage.py:193"),
    "triggers": ("config.py:4011", "consolidator.py:2602"),
    "decision-model triage routing": ("triage.py:103", "consolidator.py:2823"),
    "BM25 + embeddings + RRF fusion": ("recall.py:29", "fusion.py:29"),
    "graph_retrieval": ("graph_retrieval.py:19", "link_expansion"),
    "temporal extraction/filtering": ("temporal_extraction.py:79", "recall.py:382"),
    "cross_encoder": ("cross_encoder.py:1693", "reranking.py:179"),
    "decision_reranker": ("decision_reranker.py:1", "decision_reranker.py:39"),
    "jina_mlx_reranker": ("cross_encoder.py:2346",),
    "recency/evidence scoring": ("reranking.py:40", "reranking.py:289"),
    "token budgets": ("fact_budget.py:43", "source_facts.py:31"),
    "citation validation": ("agent.py:2333", "agent.py:2416"),
    "degradation when index/model unavailable": ("recall.py:235", "entity_resolver.py:733"),
    "hierarchical retrieval order": ("agent.py:1", "agent.py:86"),
    "multi-round evidence gathering": ("agent.py:604", "cross_encoder.py:1515"),
    "delta vs full mental-model refresh": ("memory_engine.py:18511", "delta_ops.py:133"),
    "structured delta ops + retractions": ("delta_ops.py:16", "retractions.py:112"),
    "decision-model cost avoidance": ("decision_model.py:262", "agent.py:1114"),
    "citation guarantees (reflect)": ("mental_model_refresh.py:179", "retractions.py:44"),
    "Postgres+pgvector requirement": ("_pg_extensions.py:41", "pyproject.toml"),
    "embedded mode (hindsight-embed)": ("hindsight-embed/pyproject.toml", "cli.py:19"),
    "Hermes memory-provider integration": ("hermes/__init__.py:416", "hermes/__init__.py:893"),
    "multibank": ("test_multibank.py:140", "hermes/__init__.py:85"),
    "coding-agents hooks plugin": ("coding-agents/README.md", "git.ts:1"),
    "DeepSeek native provider": ("llm_wrapper.py:1060", "llm_wrapper.py:1114"),
    "supported embedding providers": ("embeddings.py:2583",),
    "worker/backpressure model": ("poller.py:629", "backpressure.py:36"),
    "multi-tenant extensions": ("tenant.py:15",),
    "telemetry": ("metrics.py:28", "llm_trace.py:1"),
    "license/dependency implications": ("pyproject.toml:5", "LICENSE"),
}

# file:line pattern used throughout the report (markdown backticked or plain).
CITATION_RE = re.compile(r"([A-Za-z0-9_./\-]+\.(?:py|toml|md|json)):(\d+)")

# Repo-relative prefix of the slim package as cited in the report.
SLIM_PREFIX = "hindsight-api-slim/hindsight_api/"


def report_text() -> str:
    return REPORT.read_text(encoding="utf-8")


def find_checkout() -> Path | None:
    candidates = []
    env = os.environ.get("HINDSIGHT_CHECKOUT")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / ".hermes" / "cache" / "scratch" / "hindsight-research")
    for candidate in candidates:
        if (candidate / "hindsight-api-slim" / "hindsight_api" / "config.py").is_file():
            return candidate
    return None


def resolve_cited_path(checkout: Path, cited: str) -> Path | None:
    """Map a report citation to a file inside the checkout, tolerating both the
    repo-root form (hindsight-api-slim/...) and the shorthand form used after the
    first mention (engine/..., worker/...)."""
    for candidate in (cited, f"{SLIM_PREFIX}{cited}"):
        path = checkout / candidate
        if path.is_file():
            return path
    return None


class TestReportExists(unittest.TestCase):
    def test_report_file_exists(self) -> None:
        self.assertTrue(REPORT.is_file(), f"missing {REPORT}")

    def test_pinned_revision_recorded(self) -> None:
        text = report_text()
        self.assertIn(PINNED_REVISION, text)
        # The report must state the tag relationship honestly, not parrot "v1.2.1".
        self.assertIn("v1.2.1-28", text, "report must note HEAD is 28 commits past the v1.2.1 tag")


class TestSectionsAndCitations(unittest.TestCase):
    def setUp(self) -> None:
        self.text = report_text()

    def test_required_sections_present(self) -> None:
        for section in REQUIRED_SECTIONS:
            self.assertIn(section, self.text, f"missing report section: {section}")

    def test_every_section_has_citations(self) -> None:
        """Split the report on ## headings and require citations inside each."""
        chunks = re.split(r"\n## ", self.text)
        self.assertGreater(len(chunks), 8)
        empty: list[str] = []
        for chunk in chunks:
            title = chunk.splitlines()[0] if chunk else ""
            if title.startswith("Hindsight Mechanism Report"):
                continue  # front matter is followed by cited sections
            if not CITATION_RE.search(chunk):
                empty.append(title)
        self.assertEqual(empty, [], f"sections without file:line citations: {empty}")

    def test_citation_format_is_file_and_line(self) -> None:
        citations = CITATION_RE.findall(self.text)
        self.assertGreaterEqual(len(citations), 120, "report is expected to be citation-dense")
        for path, line in citations:
            self.assertTrue(line.isdigit())
            self.assertGreater(int(line), 0, f"non-positive line in citation {path}:{line}")
            self.assertFalse(path.startswith("http"), f"URL passed off as a citation: {path}")

    def test_each_required_topic_is_cited(self) -> None:
        missing: list[str] = []
        for topic, anchors in REQUIRED_CITED_TOPICS.items():
            if not any(anchor in self.text for anchor in anchors):
                missing.append(topic)
        self.assertEqual(missing, [], f"topics without citations: {missing}")

    def test_mechanism_classification_present(self) -> None:
        for klass in ("deterministic", "LLM", "specialized-model"):
            self.assertIn(klass, self.text, f"missing classification class: {klass}")
        self.assertIn("Marginal value", self.text)
        # The factory workload framing must be explicit.
        self.assertIn("coding-agent factory", self.text)

    def test_cost_levers_table_present(self) -> None:
        for lever in (
            "retain_chunk_size",
            "consolidation_llm_batch_size",
            "reflect_max_iterations",
            "recall_max_tokens",
            "llm_max_concurrent",
            "consolidation_dedup_threshold",
        ):
            self.assertIn(lever, self.text, f"missing cost lever: {lever}")

    def test_code_vs_docs_section_distinguishes_claims(self) -> None:
        self.assertIn("Code vs docs claims", self.text)
        # The table must carry at least one docs-vs-code disagreement.
        self.assertIn("28 commits", self.text)
        self.assertIn("observation_history", self.text)


class TestCitationsResolveAgainstUpstream(unittest.TestCase):
    """When the pinned checkout is available, verify a sample of citations actually
    point at real lines in real files (guards against fabricated line numbers)."""

    checkout: Path | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.checkout = find_checkout()

    def test_checkout_found_or_skipped(self) -> None:
        if self.checkout is None:
            self.skipTest("no upstream checkout available (set HINDSIGHT_CHECKOUT to enable)")

    def test_sampled_citations_resolve(self) -> None:
        if self.checkout is None:
            self.skipTest("no upstream checkout available")
        # Hand-verified anchors: (cited path, line, substring that must appear on
        # or near that line in the pinned revision).
        anchors = [
            ("engine/retain/fact_extraction.py", 1083, "Extract SIGNIFICANT facts"),
            ("engine/retain/fact_extraction.py", 2304, "assistant"),
            ("engine/retain/memory_budget.py", 92, "class RetainMemoryBudget"),
            ("engine/memories/pg/entity_resolver.py", 1163, "_resolve_from_candidates"),
            ("engine/memories/pg/links.py", 569, "compute_semantic_links_ann"),
            ("engine/retain/fact_storage.py", 191, "handle_document_tracking"),
            ("engine/consolidation/consolidator.py", 2711, "_process_memory_batch"),
            ("engine/consolidation/triage.py", 193, "def triage_facts"),
            ("engine/consolidation/prompts.py", 96, "_RULES"),
            ("engine/decision_model.py", 262, "async def ask"),
            ("engine/search/fusion.py", 29, "def reciprocal_rank_fusion"),
            ("engine/search/reranking.py", 179, "def apply_combined_scoring"),
            ("engine/search/decision_reranker.py", 69, "class DecisionModelReranker"),
            ("engine/cross_encoder.py", 1693, "RRFPassthroughCrossEncoder"),
            ("engine/memories/pg/recall.py", 29, "retrieve_semantic_bm25_combined_sql"),
            ("engine/reflect/agent.py", 2333, "_cited_ids"),
            ("engine/reflect/delta_ops.py", 133, "AppendBlockOp"),
            ("engine/reflect/retractions.py", 112, "partition_retracted"),
            ("engine/mental_model_refresh.py", 27, "RefreshMode"),
            ("config.py", 2147, "DEFAULT_CONSOLIDATION_DEDUP_THRESHOLD"),
            ("engine/memory_engine.py", 21553, "compute_mental_model_is_stale"),
            ("worker/backpressure.py", 36, "_BACKPRESSURE_MARKERS"),
            ("extensions/tenant.py", 54, "class TenantExtension"),
            ("engine/llm_wrapper.py", 1114, "deepseek"),
            ("engine/embeddings.py", 2583, "def _create_embeddings"),
            ("_pg_extensions.py", 41, "MANAGED_EXTENSIONS"),
        ]
        failures: list[str] = []
        for path, line, needle in anchors:
            file_path = resolve_cited_path(self.checkout, path)
            if file_path is None:
                failures.append(f"{path}: file not found in checkout")
                continue
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not (1 <= line <= len(lines)):
                failures.append(f"{path}:{line} out of range (file has {len(lines)} lines)")
                continue
            window = "\n".join(lines[max(0, line - 4) : min(len(lines), line + 2)])
            if needle not in window:
                failures.append(f"{path}:{line} does not contain {needle!r}")
        self.assertEqual(failures, [], "citation anchors failed: " + "; ".join(failures))


if __name__ == "__main__":
    unittest.main()
