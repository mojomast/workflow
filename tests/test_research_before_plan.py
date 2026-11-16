"""Conformance tests for the RESEARCH-BEFORE-PLAN rule in the protocol docs.

The owner directive (2026-11-16) gives the planning phase the discipline the
RESEARCH-BEFORE-RETRY rule already gives recovery: a spec, a work-package
breakdown, or a non-trivial brief MUST be the product of a prior-art plus
known-pitfalls research pass, the findings live in the artifact itself as a
required prior-art-and-pitfalls section, at least one alternative is documented
as rejected, and a documented trivial-task threshold exempts trivial tasks.

The rule cross-references — it does not fork — the RESEARCH-BEFORE-RETRY rule
this branch already carries in the coordinator playbook's Verification chapter
(docs/19 §4) and in the dogfood chapter's recovery loop (docs/24 §2). Tests
here assert the contract by stable fragments on whitespace-normalized text;
per the known pitfalls recorded in the rule's own disclosure, they do not pin
prose byte for byte.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

PLAYBOOK = DOCS / "19-coordinator-playbook.md"
DOGFOOD = DOCS / "24-autonomy-dogfood.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize(text: str) -> str:
    return " ".join(text.split())


def top_level_section(text: str, number: str) -> str:
    """The ``## <number>. ...`` chapter, whitespace-normalized."""
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
    return normalize("\n".join(lines[start:end]))


def sub_section(text: str, heading: str) -> str:
    """The ``### ...<heading>...`` subsection through its next heading, normalized."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("### ") and heading in line:
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## ") or lines[index].startswith("### "):
            end = index
            break
    return normalize("\n".join(lines[start:end]))


def sub_heading_line(text: str, heading: str) -> int | None:
    for index, line in enumerate(text.splitlines()):
        if line.startswith("### ") and heading in line:
            return index
    return None


def chapter_headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


class PlacementTests(unittest.TestCase):
    """The plan rule is a subsection beside the retry rule; no new chapter forks off."""

    def test_the_playbook_gains_the_plan_subsection_inside_the_verification_chapter(self):
        section_text = top_level_section(read(PLAYBOOK), "4")
        self.assertIn("### Research before plan", section_text)
        self.assertIn("RESEARCH-BEFORE-PLAN", section_text)

    def test_the_playbook_plan_subsection_is_adjacent_to_the_retry_subsection(self):
        lines = read(PLAYBOOK).splitlines()
        retry = sub_heading_line("\n".join(lines), "Research before retry")
        plan = sub_heading_line("\n".join(lines), "Research before plan")
        self.assertIsNotNone(retry, "retry subsection missing from the playbook")
        self.assertIsNotNone(plan, "plan subsection missing from the playbook")
        self.assertLess(retry, plan)
        between = [line for line in lines[retry + 1 : plan]]
        self.assertFalse(
            [line for line in between if line.startswith("## ")],
            "a chapter heading separates the retry and plan subsections",
        )

    def test_the_dogfood_gains_the_plan_record_inside_the_controlled_failure_chapter(self):
        section_text = top_level_section(read(DOGFOOD), "2")
        self.assertIn("### Research before plan", section_text)
        self.assertIn("RESEARCH-BEFORE-PLAN", section_text)

    def test_the_dogfood_plan_record_is_adjacent_to_the_retry_record(self):
        lines = read(DOGFOOD).splitlines()
        retry = sub_heading_line("\n".join(lines), "Research before retry")
        plan = sub_heading_line("\n".join(lines), "Research before plan")
        self.assertIsNotNone(retry, "retry subsection missing from the dogfood chapter")
        self.assertIsNotNone(plan, "plan subsection missing from the dogfood chapter")
        self.assertLess(retry, plan)
        between = [line for line in lines[retry + 1 : plan]]
        self.assertFalse(
            [line for line in between if line.startswith("## ")],
            "a chapter heading separates the retry and plan records",
        )

    def test_no_top_level_chapter_forks_off_for_the_plan_rule(self):
        for path in (PLAYBOOK, DOGFOOD):
            headings = chapter_headings(read(path))
            for heading in headings:
                self.assertNotIn("research before plan", heading.lower(), f"{path.name}: {heading}")
                self.assertNotIn("research-before-plan", heading.lower(), f"{path.name}: {heading}")

    def test_the_retry_rule_survives_unweakened(self):
        playbook_section = top_level_section(read(PLAYBOOK), "4")
        for fragment in ("RESEARCH-BEFORE-RETRY", "MUST be a research pass", "27-recovery-protocol.md"):
            self.assertIn(fragment, playbook_section)
        dogfood_section = top_level_section(read(DOGFOOD), "2")
        for fragment in ("RESEARCH-BEFORE-RETRY", "MUST be a research pass", "environment-class"):
            self.assertIn(fragment, dogfood_section)


class PlaybookPlanRuleTests(unittest.TestCase):
    """The normative rule, as carried by the coordinator playbook's Verification chapter."""

    @classmethod
    def setUpClass(cls):
        cls.rule_text = sub_section(read(PLAYBOOK), "Research before plan")

    def test_the_rule_is_named_and_normative(self):
        self.assertIn("RESEARCH-BEFORE-PLAN", self.rule_text)
        self.assertIn("MUST", self.rule_text)
        self.assertIn("prior-art plus known-pitfalls research pass", self.rule_text)

    def test_the_rule_names_the_artifact_classes_it_covers(self):
        for fragment in ("a spec", "work-package breakdown", "non-trivial brief"):
            self.assertIn(fragment, self.rule_text)

    def test_findings_live_in_the_artifact_itself_as_a_required_section(self):
        self.assertIn("in the artifact itself", self.rule_text)
        self.assertIn("prior-art-and-pitfalls section", self.rule_text)

    def test_at_least_one_documented_rejected_alternative_is_required(self):
        self.assertIn("at least one documented rejected alternative", self.rule_text)

    def test_the_exemplars_are_named(self):
        self.assertIn("rails-spec and Hive-spec research digests", self.rule_text)
        self.assertIn("F6/V1 fencing/RCV research", self.rule_text)

    def test_the_trivial_task_threshold_is_documented(self):
        self.assertIn("Trivial-task threshold", self.rule_text)
        self.assertIn("exempt", self.rule_text)
        self.assertIn("when in doubt", self.rule_text)

    def test_the_rule_cross_references_the_retry_rule_instead_of_forking_it(self):
        self.assertIn("RESEARCH-BEFORE-RETRY", self.rule_text)
        self.assertIn("does not fork", self.rule_text)
        self.assertIn("24-autonomy-dogfood.md", self.rule_text)

    def test_the_disclosure_names_the_prior_art_actually_read(self):
        self.assertIn("tests/test_research_before_retry.py", self.rule_text)

    def test_the_disclosure_documents_the_rejected_mechanism(self):
        self.assertIn("mechanical pre-dispatch checklist gate", self.rule_text)
        self.assertIn("rubber-stamp", self.rule_text)

    def test_the_disclosure_carries_the_known_pitfalls(self):
        self.assertIn("scope_violation", self.rule_text)
        self.assertIn("assigned_files", self.rule_text)
        self.assertIn("assert the contract", self.rule_text)


class DogfoodPlanRuleTests(unittest.TestCase):
    """The planning-phase directive, as recorded by the dogfood chapter."""

    @classmethod
    def setUpClass(cls):
        cls.record_text = sub_section(read(DOGFOOD), "Research before plan")

    def test_the_record_is_named_and_normative(self):
        self.assertIn("RESEARCH-BEFORE-PLAN", self.record_text)
        self.assertIn("MUST", self.record_text)
        self.assertIn("prior-art-and-pitfalls section", self.record_text)

    def test_the_record_names_the_artifact_classes_it_covers(self):
        for fragment in ("a spec", "work-package breakdown", "non-trivial brief"):
            self.assertIn(fragment, self.record_text)

    def test_the_record_documents_a_rejected_alternative(self):
        self.assertIn("documented rejected alternative", self.record_text)
        self.assertIn("rubber-stamp", self.record_text)

    def test_the_record_names_the_exemplars(self):
        for fragment in ("rails-spec", "Hive-spec", "F6/V1", "fencing/RCV"):
            self.assertIn(fragment, self.record_text)

    def test_the_record_documents_the_trivial_task_threshold(self):
        self.assertIn("Trivial-task threshold", self.record_text)
        self.assertIn("exempt", self.record_text)
        self.assertIn("when in doubt", self.record_text)

    def test_the_record_cross_references_the_playbook_rule_instead_of_forking_it(self):
        self.assertIn("19-coordinator-playbook.md", self.record_text)
        self.assertIn("RESEARCH-BEFORE-RETRY", self.record_text)
        self.assertIn("instead of forking", self.record_text)


if __name__ == "__main__":
    unittest.main()
