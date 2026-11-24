"""Approved tests (T1-SEED): scripts/seed_memory_from_lessons.py seeds a
rizzstack.memory/1 vault from docs/28-agent-lessons.md.

Every ``### L-NN · Title`` section becomes one ``learning`` memory with id
``lesson-l-NN``, written through DiskVault into the seed writer's QUARANTINE
zone (writer ``agent:lessons-seed``); promotion to curated dirs still needs a
human grant, so the seeder never writes outside quarantine. Re-running is
idempotent. ``--dry-run`` lists what it would write and touches nothing.
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

SCRIPT = ROOT / "scripts" / "seed_memory_from_lessons.py"
LESSONS = ROOT / "docs" / "28-agent-lessons.md"
WRITER = "agent:lessons-seed"
NOW = "2026-11-24T15:00:00Z"


def lesson_ids() -> list:
    ids = []
    for line in LESSONS.read_text(encoding="utf-8").splitlines():
        if line.startswith("### L-"):
            ids.append("lesson-" + line[4:8].lower())
    return ids


def run(args):
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=120,
                          cwd=str(ROOT), env=env)


def files(root: str) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


class TestSeedMemoryFromLessons(unittest.TestCase):
    def test_every_lesson_becomes_one_learning_in_quarantine(self):
        ids = lesson_ids()
        self.assertGreaterEqual(len(ids), 20)
        with tempfile.TemporaryDirectory() as root:
            proc = run(["--vault", root, "--now", NOW])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            vault = DiskVault(root)
            prefix = quarantine_prefix(WRITER)
            for memory_id in ids:
                entry = vault.read(prefix + memory_id + ".md")
                self.assertEqual(entry["record"]["id"], memory_id)
                self.assertEqual(entry["record"]["type"], "learning")
                self.assertTrue(any(s.get("ref") == "docs/28-agent-lessons.md" for s in entry["record"]["sources"]))
                self.assertIn(memory_id[len("lesson-"):].upper(), entry["body"])
            written = [p for p in files(root) if p.endswith(".md") and "/" in p]
            for path in written:
                self.assertTrue(path.startswith(prefix), f"seeder wrote outside quarantine: {path}")

    def test_seeded_lessons_are_queryable(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(run(["--vault", root, "--now", NOW]).returncode, 0)
            result = DiskVault(root).query({"op": "query", "q": "manufacture human gesture", "k": 3}, now=NOW)
            self.assertIn("lesson-l-20", [h["id"] for h in result["hits"]])

    def test_rerun_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(run(["--vault", root, "--now", NOW]).returncode, 0)
            before = {k: v for k, v in files(root).items() if not k.endswith("log.md")}
            proc = run(["--vault", root, "--now", NOW])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            after = {k: v for k, v in files(root).items() if not k.endswith("log.md")}
            self.assertEqual(after, before)

    def test_dry_run_touches_nothing_and_lists_ids(self):
        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "vault")
            proc = run(["--vault", target, "--now", NOW, "--dry-run"])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(os.path.exists(target))
            for memory_id in lesson_ids():
                self.assertIn(memory_id, proc.stdout)

    def test_output_is_a_json_summary(self):
        with tempfile.TemporaryDirectory() as root:
            proc = run(["--vault", root, "--now", NOW])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertEqual(summary["written"] + summary["unchanged"], len(lesson_ids()))
            self.assertEqual(summary["writer"], WRITER)


if __name__ == "__main__":
    unittest.main()
