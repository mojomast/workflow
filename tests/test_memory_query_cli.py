"""Approved tests (T1-MEMQ): ``python3 -m rizzstack_memory query`` answers one
bundlebees lease-time recall request (docs: bundlebees docs/memory-recall.md).

Request on stdin: {"contract": "rizzstack.memory/1", "query": ..., "caps": {...}};
the query text is also the last argv word. Response on stdout:
{"contract": "rizzstack.memory/1", "vault_rev": str, "items": [{id,type,sha,path,title,excerpt}]}.
The CLI is read-only: it never writes into the vault.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rizzstack_memory import DiskVault, quarantine_prefix  # noqa: E402
from tests.test_memory_contract import TYPE_POLICY, WRITER, base_record, sealed, write_op  # noqa: E402

BODIES = (
    ("lease-recovery", "# Lease recovery\n\nRe-read the lease file before the next wave; a stale lease blocks dispatch.\n"),
    ("naming", "# Naming conventions\n\nA quiet note about naming conventions for receipts.\n"),
)


def seeded_vault(root: str) -> None:
    vault = DiskVault(root)
    prefix = quarantine_prefix(WRITER)
    for memory_id, body in BODIES:
        record = sealed(base_record(id=memory_id, type="learning",
                                    retention={"policy": TYPE_POLICY["learning"], "expires": None, "superseded_by": None}), body)
        vault.write(write_op(path=prefix + f"{memory_id}.md", record=record, body=body))


def run_cli(args, stdin=None, env_extra=None):
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT)}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "rizzstack_memory", *args], input=stdin, capture_output=True,
                          text=True, timeout=60, cwd=str(ROOT), env=env)


def request(query: str, max_items=8, max_excerpt=480, max_total=4000) -> str:
    return json.dumps({"contract": "rizzstack.memory/1", "query": query,
                       "caps": {"max_items": max_items, "max_excerpt_chars": max_excerpt, "max_total_chars": max_total}})


def tree_digest(root: str) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


class TestMemoryQueryCli(unittest.TestCase):
    def test_answers_recall_request_with_contract_items(self):
        with tempfile.TemporaryDirectory() as root:
            seeded_vault(root)
            proc = run_cli(["query", "--vault", root, "stale lease wave"], stdin=request("stale lease wave"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(out["contract"], "rizzstack.memory/1")
            self.assertIsInstance(out["vault_rev"], str)
            self.assertTrue(out["items"], "a matching memory must be returned")
            first = out["items"][0]
            self.assertEqual(set(first), {"id", "type", "sha", "path", "title", "excerpt"})
            self.assertEqual(first["id"], "lease-recovery")
            self.assertEqual(first["type"], "learning")
            self.assertTrue(all(isinstance(first[k], str) for k in first))

    def test_respects_request_caps(self):
        with tempfile.TemporaryDirectory() as root:
            seeded_vault(root)
            proc = run_cli(["query", "--vault", root, "lease naming receipts"],
                           stdin=request("lease naming receipts", max_items=1, max_excerpt=20))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertLessEqual(len(out["items"]), 1)
            for item in out["items"]:
                self.assertLessEqual(len(item["excerpt"]), 20)

    def test_empty_vault_returns_no_items(self):
        with tempfile.TemporaryDirectory() as root:
            proc = run_cli(["query", "--vault", root, "anything"], stdin=request("anything"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(out["items"], [])
            self.assertEqual(out["contract"], "rizzstack.memory/1")

    def test_works_without_stdin_request(self):
        with tempfile.TemporaryDirectory() as root:
            seeded_vault(root)
            proc = run_cli(["query", "--vault", root, "stale lease"], stdin="")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["items"][0]["id"], "lease-recovery")

    def test_wrong_contract_or_missing_vault_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            bad = json.dumps({"contract": "other/9", "query": "x", "caps": {}})
            proc = run_cli(["query", "--vault", root, "x"], stdin=bad)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")
            missing = os.path.join(root, "does-not-exist")
            proc = run_cli(["query", "--vault", missing, "x"], stdin=request("x"))
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")
            self.assertFalse(os.path.exists(missing), "query must never create a vault")

    def test_query_never_writes(self):
        with tempfile.TemporaryDirectory() as root:
            seeded_vault(root)
            before = tree_digest(root)
            proc = run_cli(["query", "--vault", root, "lease"], stdin=request("lease"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(tree_digest(root), before)


if __name__ == "__main__":
    unittest.main()
