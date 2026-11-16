"""Conformance tests for the RESEARCH-BEFORE-RETRY rule in the protocol docs.

The owner directive (2026-11-16) makes research a normative step of the
recovery/repair flow: when a verify failure, a CI failure or a blocker is not
understood after the first diagnosis pass, the next action MUST be a research
pass — the exact error signature plus tool/version context, searching for the
error, known issues and version-specific behavior — before another fix
attempt, and the findings, with citations, become part of the repair evidence.

The rule anchors in the existing chapters instead of forking a new one: the
coordinator playbook's Verification chapter (docs/19 §4, with the brief rule
that reaches bees in §2) and the autonomy dogfood chapter's recovery loop
(docs/24 §2). Both cite docs/27-recovery-protocol.md, which stays the
normative recovery source (verify / classify / reject / supersede /
re-dispatch / escalate).
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

PLAYBOOK = DOCS / "19-coordinator-playbook.md"
DOGFOOD = DOCS / "24-autonomy-dogfood.md"
RECOVERY = DOCS / "27-recovery-protocol.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def top_level_section(text: str, number: str) -> str:
    """The ``## <number>. ...`` section, whitespace-normalized so markdown reflow cannot hide a fragment."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and line[3:].startswith(f"{number}. "):
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return " ".join("\n".join(lines[start:end]).split())


class PlacementTests(unittest.TestCase):
    """The rule lives inside the existing chapters; no new normative chapter forks off."""

    def test_the_playbook_verification_chapter_exists(self):
        self.assertTrue(top_level_section(read(PLAYBOOK), "4").startswith("## 4. Verification"))

    def test_the_dogfood_recovery_loop_section_exists(self):
        section_text = top_level_section(read(DOGFOOD), "2")
        self.assertTrue(section_text.startswith("## 2. The controlled failure"))

    def test_the_playbook_keeps_its_chapters_and_gains_no_research_chapter(self):
        headings = [line for line in read(PLAYBOOK).splitlines() if line.startswith("## ")]
        self.assertEqual(len(headings), 11)
        self.assertTrue(all("research" not in heading.lower() for heading in headings))

    def test_the_dogfood_keeps_its_sections_and_gains_no_research_chapter(self):
        headings = [line for line in read(DOGFOOD).splitlines() if line.startswith("## ")]
        self.assertEqual(len(headings), 9)
        self.assertTrue(all("research" not in heading.lower() for heading in headings))

    def test_the_normative_recovery_source_the_rule_anchors_in_exists(self):
        self.assertTrue(RECOVERY.exists())
        self.assertIn("recovery/1", read(RECOVERY))


class PlaybookVerificationRuleTests(unittest.TestCase):
    """The normative rule, as carried by the coordinator playbook's Verification chapter."""

    @classmethod
    def setUpClass(cls):
        cls.section_text = top_level_section(read(PLAYBOOK), "4")

    def test_the_rule_is_named_and_normative(self):
        self.assertIn("### Research before retry", self.section_text)
        self.assertIn("RESEARCH-BEFORE-RETRY", self.section_text)
        self.assertIn("MUST be a research pass", self.section_text)

    def test_the_rule_names_the_triggers_and_the_research_payload(self):
        for fragment in ("verify failure", "CI failure", "blocker",
                         "first diagnosis pass", "exact error signature",
                         "tool/version context", "known issues", "version-specific",
                         "before another fix attempt"):
            self.assertIn(fragment, self.section_text)

    def test_findings_are_recorded_in_the_attempt_record_with_citations(self):
        self.assertIn("citations", self.section_text)
        self.assertIn("attempt record", self.section_text)
        self.assertIn("repair evidence", self.section_text)

    def test_the_rule_covers_bees_and_the_coordinator(self):
        self.assertIn("coordinator", self.section_text)
        self.assertIn("bees", self.section_text)
        self.assertIn("research phase", self.section_text)
        self.assertIn("brief", self.section_text)

    def test_known_upstream_and_tool_issues_are_routed_not_retried(self):
        self.assertIn("known upstream", self.section_text)
        self.assertIn("environment", self.section_text)
        self.assertIn("escalate", self.section_text)

    def test_the_worked_gitleaks_example_is_carried(self):
        for fragment in (".gitleaksignore", "fingerprint", "SHA-pinned",
                         "history rewrite", "upstream gitleaks", "file:rule:line",
                         "gitleaks:allow", "blind fix cycle", "in minutes"):
            self.assertIn(fragment, self.section_text)

    def test_the_rule_anchors_the_recovery_protocol_it_does_not_fork_it(self):
        self.assertIn("27-recovery-protocol.md", self.section_text)


class PlaybookBriefRuleTests(unittest.TestCase):
    """The bee side of the rule: repair dispatch briefs carry a research phase."""

    def test_the_brief_rules_carry_the_research_phase_requirement(self):
        intake = top_level_section(read(PLAYBOOK), "2")
        self.assertIn("research phase", intake)
        self.assertIn("repair", intake)
        self.assertIn("citations", intake)


class DogfoodRecoveryLoopRuleTests(unittest.TestCase):
    """The normative rule, as carried by the dogfood chapter's recovery loop."""

    @classmethod
    def setUpClass(cls):
        cls.section_text = top_level_section(read(DOGFOOD), "2")

    def test_the_rule_is_named_and_normative_in_the_recovery_loop(self):
        self.assertIn("### Research before retry", self.section_text)
        self.assertIn("RESEARCH-BEFORE-RETRY", self.section_text)
        self.assertIn("MUST be a research pass", self.section_text)

    def test_the_rule_names_the_triggers_and_the_research_payload(self):
        for fragment in ("verify failure", "CI failure", "first diagnosis pass",
                         "exact error signature", "tool/version context",
                         "before another fix attempt"):
            self.assertIn(fragment, self.section_text)

    def test_repair_dispatches_carry_a_research_phase_and_findings_become_evidence(self):
        self.assertIn("research phase", self.section_text)
        self.assertIn("citations", self.section_text)
        self.assertIn("repair evidence", self.section_text)

    def test_known_upstream_and_tool_issues_are_routed_not_retried(self):
        self.assertIn("known upstream", self.section_text)
        self.assertIn("environment-class", self.section_text)

    def test_the_rule_anchors_the_recovery_protocol_it_does_not_fork_it(self):
        self.assertIn("27-recovery-protocol.md", self.section_text)


if __name__ == "__main__":
    unittest.main()
