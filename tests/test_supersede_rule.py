"""Conformance tests for SUPERSEDE-DONT-AMEND (BEST-PRACTICE item 14).

Owner decision 2026-11-24 15:04 ET: dated evidence and decision records stay
byte-for-byte; a correction is a new dated record, and the old one is pointed to
it from ROADMAP and the evidence index ("superseded by"), never edited. The Rails
release decision is the worked example, and its published checksum must still hold.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "docs" / "19-coordinator-playbook.md"
RELEASE = ROOT / "evidence" / "rails-rc" / "release"
NEW = "DECISION-2026-11-24-index-default.md"


class SupersedeRuleTests(unittest.TestCase):
    def test_rule_in_memory_and_state_chapter(self) -> None:
        text = PLAYBOOK.read_text(encoding="utf-8")
        chapter = text[text.index("## 9. Memory and state"):text.index("## 10. The merge-plan pattern")]
        chapter = " ".join(chapter.split())
        for fragment in ("SUPERSEDE-DONT-AMEND", "byte-for-byte", "new dated record", "superseded by", NEW):
            self.assertIn(fragment, chapter)

    def test_rails_decision_is_byte_for_byte_its_published_checksum(self) -> None:
        line = (RELEASE / "published.sha256").read_text(encoding="utf-8").splitlines()[0]
        digest, name = line.split()
        self.assertEqual(name, "./DECISION.md")
        self.assertEqual(hashlib.sha256((RELEASE / "DECISION.md").read_bytes()).hexdigest(), digest)

    def test_superseding_record_and_pointers(self) -> None:
        self.assertIn("DECISION.md", (RELEASE / NEW).read_text(encoding="utf-8"))
        for path in (ROOT / "ROADMAP.md", ROOT / "evidence" / "rails-rc" / "README.md"):
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, r"(?i)supersed", path.name)
            self.assertIn(NEW, text, path.name)


if __name__ == "__main__":
    unittest.main()
