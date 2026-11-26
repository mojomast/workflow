"""FTS5 keyword index tests for the rizzstack.memory/1 vault.

These tests pin the slice's acceptance criteria onto a real tempfile vault:

- AC-1: one query returns the same item set with the index present and removed.
- AC-2: ``mode_used`` names the engine that actually ran (keyword vs grep).
- AC-3: a missing or corrupt index degrades to grep without raising.
- AC-4: the index rebuilds from markdown only and leaves the markdown untouched.
- AC-5: an accepted write is findable through an incremental refresh.

Frontmatter, digest and expiry helpers come from the normative oracle; nothing
is forked here. Every vault is a ``tempfile`` directory.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rizzstack_memory import DiskVault  # noqa: E402
from rizzstack_memory.index import INDEX_DIR, Index  # noqa: E402
from tests.test_memory_contract import (  # noqa: E402
    NOW,
    TYPE_POLICY,
    WORKED_BODY,
    base_record,
    grant,
    sealed,
    write_op,
)

QUERY = "workbench crash lease"

BODIES = {
    "workbench-crash-resume": (
        "# Workbench crash resume\n"
        "\n"
        "The workbench crash leaves a stale lease behind.\n"
        "\n"
        "- Resume from the recovery digest, never from scrollback.\n"
    ),
    "lease-recovery-notes": (
        "# Lease recovery notes\n"
        "\n"
        "Re-read the lease file before the next wave; the workbench resumes cleanly.\n"
    ),
    "naming-conventions": (
        "# Naming conventions\n"
        "\n"
        "A quiet note about naming conventions for receipts.\n"
    ),
}


def record_for(memory_type: str, memory_id: str, body: str = None, **retention) -> dict:
    record = base_record(
        id=memory_id,
        type=memory_type,
        retention={"policy": TYPE_POLICY[memory_type], "expires": None, "superseded_by": None, **retention},
    )
    return sealed(record, body if body is not None else WORKED_BODY)


def build_vault(root) -> DiskVault:
    vault = DiskVault(root)
    # Recall only sees promoted zones: seed through a grant so the fixture is a
    # published memory rather than an unpublished quarantine file.
    for memory_id, body in BODIES.items():
        vault.write(
            write_op(
                path="learnings/" + memory_id + ".md",
                record=record_for("learning", memory_id, body),
                body=body,
                authority=grant(approved_by="orbit:coordinator"),
            )
        )
    return vault


def hit_ids(result: dict) -> list:
    return [hit["id"] for hit in result["hits"]]


def markdown_snapshot(root) -> dict:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(Path(root).rglob("*.md"))
    }


class SameHitsAndHonestModeTests(unittest.TestCase):
    def test_same_hits_with_index_present_and_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)

            index = Index(tmp).create()
            self.assertTrue(index.healthy())
            keyword = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)
            self.assertEqual(keyword["mode_used"], "keyword")

            shutil.rmtree(Path(tmp) / INDEX_DIR)
            self.assertFalse(Index(tmp).healthy())
            grep = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)
            self.assertEqual(grep["mode_used"], "grep")

            self.assertEqual(hit_ids(keyword), hit_ids(grep))
            self.assertEqual(set(hit_ids(keyword)), {"workbench-crash-resume", "lease-recovery-notes"})

    def test_grep_request_wins_over_a_healthy_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)
            Index(tmp).create()

            keyword = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)
            forced = vault.query({"op": "query", "q": QUERY, "k": 5, "mode": "grep"}, now=NOW)

            self.assertEqual(keyword["mode_used"], "keyword")
            self.assertEqual(forced["mode_used"], "grep")
            self.assertEqual(hit_ids(keyword), hit_ids(forced))

    def test_semantic_without_embeddings_falls_to_the_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)
            Index(tmp).create()

            result = vault.query({"op": "query", "q": QUERY, "k": 5, "mode": "semantic"}, now=NOW)

            self.assertEqual(result["mode_used"], "keyword")


class CorruptIndexTests(unittest.TestCase):
    def test_corrupt_index_degrades_to_grep(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)
            index = Index(tmp).create()
            baseline = hit_ids(vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW))
            self.assertEqual(baseline, ["workbench-crash-resume", "lease-recovery-notes"])

            Path(index.db_path).write_bytes(b"this is not a sqlite database")

            self.assertFalse(Index(tmp).healthy())
            degraded = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)
            self.assertEqual(degraded["mode_used"], "grep")
            self.assertEqual(hit_ids(degraded), baseline)

    def test_create_repairs_a_corrupt_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_vault(tmp)
            index = Index(tmp).create()
            Path(index.db_path).write_bytes(b"broken bytes")
            self.assertFalse(Index(tmp).healthy())

            repaired = Index(tmp).create()
            self.assertTrue(repaired.healthy())


class RebuildTests(unittest.TestCase):
    def test_rebuild_reproduces_hits_and_leaves_markdown_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)
            before = markdown_snapshot(tmp)
            grep = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)
            self.assertEqual(grep["mode_used"], "grep")

            Index(tmp).create()
            first = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)
            self.assertEqual(first["mode_used"], "keyword")
            self.assertEqual(hit_ids(first), hit_ids(grep))

            Index(tmp).rebuild()
            Index(tmp).rebuild()
            second = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)
            self.assertEqual(second["mode_used"], "keyword")
            self.assertEqual(hit_ids(second), hit_ids(grep))

            self.assertEqual(markdown_snapshot(tmp), before)

    def test_rebuild_after_removal_reproduces_the_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)
            Index(tmp).create()
            first = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)

            shutil.rmtree(Path(tmp) / INDEX_DIR)
            Index(tmp).create()
            second = vault.query({"op": "query", "q": QUERY, "k": 5}, now=NOW)

            self.assertEqual(second["mode_used"], "keyword")
            self.assertEqual(hit_ids(second), hit_ids(first))


class IncrementalUpdateTests(unittest.TestCase):
    def test_accepted_write_is_findable_without_a_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)
            Index(tmp).create()

            memory_id = "fresh-incremental-note"
            body = "# Fresh incremental note\n\nThe incremental refresh finds this new lease note.\n"
            vault.write(
                write_op(
                    path="learnings/" + memory_id + ".md",
                    record=record_for("learning", memory_id, body),
                    body=body,
                    authority=grant(approved_by="orbit:coordinator"),
                )
            )

            self.assertIn(memory_id, Index(tmp).search(["fresh", "incremental"]))
            result = vault.query({"op": "query", "q": "fresh incremental", "k": 5}, now=NOW)
            self.assertEqual(result["mode_used"], "keyword")
            self.assertEqual(hit_ids(result), [memory_id])


class RetentionIsNotIndexAuthoritativeTests(unittest.TestCase):
    def test_expired_and_superseded_items_stay_hidden_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = build_vault(tmp)

            stale_body = "# Stale lease reference\n\nThe stale lease reference points at an old workbench.\n"
            vault.write(
                write_op(
                    path="concepts/stale-reference.md",
                    record=record_for(
                        "reference",
                        "stale-reference",
                        stale_body,
                        expires="2026-01-01T00:00:00Z",
                    ),
                    body=stale_body,
                    authority=grant(),
                )
            )
            old_body = "# Superseded lease learning\n\nThis superseded lease learning is hidden until asked for.\n"
            vault.write(
                write_op(
                    path="learnings/superseded-learning.md",
                    record=record_for(
                        "learning",
                        "superseded-learning",
                        old_body,
                        superseded_by="workbench-crash-resume",
                    ),
                    body=old_body,
                    authority=grant(approved_by="orbit:coordinator"),
                )
            )

            index = Index(tmp).create()
            self.assertIn("stale-reference", index.search(["stale"]))
            self.assertIn("superseded-learning", index.search(["superseded"]))

            hidden_stale = vault.query({"op": "query", "q": "old", "k": 5}, now=NOW)
            hidden_old = vault.query({"op": "query", "q": "hidden", "k": 5}, now=NOW)
            shown_stale = vault.query(
                {"op": "query", "q": "old", "k": 5, "include_expired": True}, now=NOW
            )
            shown_old = vault.query(
                {"op": "query", "q": "hidden", "k": 5, "include_expired": True}, now=NOW
            )

            self.assertEqual(hidden_stale["mode_used"], "keyword")
            self.assertEqual(hit_ids(hidden_stale), [])
            self.assertEqual(hit_ids(hidden_old), [])
            self.assertEqual(hit_ids(shown_stale), ["stale-reference"])
            self.assertEqual(hit_ids(shown_old), ["superseded-learning"])


if __name__ == "__main__":
    unittest.main()
