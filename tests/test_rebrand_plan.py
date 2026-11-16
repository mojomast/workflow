"""Conformance tests for docs/rebrand-plan.md (the PLAN-ONLY rebrand plan).

The plan maps the selected names onto the operational repositories: the
rizzstack umbrella, the four product names (flww, hyvv, bzzq, orbt) and the
Night Hive theme. The plan must stay a reviewable document — nothing is
renamed by this slice — and every branding-adjacent claim must cite the
deferred-branding boundary (names not legally cleared; operational names stay
until un-deferral).

The hygiene checks reuse the repository's own scanners (tools/bee_landed.py)
plus structural value-shape detectors, and must find zero hits in this plan
and in its sibling website plan. Runs under pytest
(python3 -m pytest tests/test_rebrand_plan.py -q) and under unittest
(python3 -m unittest tests.test_rebrand_plan -q); no network, no third-party
imports beyond the repository's own tools.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bee_landed  # noqa: E402

PLAN_PATH = ROOT / "docs" / "rebrand-plan.md"
SIBLING_PATH = ROOT / "docs" / "website-plan.md"

HEX_RUN_RE = re.compile(r"[0-9a-fA-F]{40,}")
LONG_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{32,}")
PRIVATE_HOST_RE = re.compile(
    r"\b(?:192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})\b"
)
KEYVALUE_TAIL_RE = re.compile(r"s?[ \t]*[:=][ \t]*[^ \t]")

SELECTED_NAMES = ("rizzstack", "flww", "hyvv", "bzzq", "orbt", "Night Hive")

MAPPING_ROWS = (
    ("workflow", "flww"),
    ("bundlebees", "bzzq"),
    ("orbitdesktop", "orbt"),
    ("hyvv", "hyvv"),
)

CODE_REFERENCE_TARGETS = (
    "contrib/bee-ci/manifest.py",
    "templates/handoff/HANDOFF.md",
    "README.md",
    "ROADMAP.md",
    "docs/08-repositories.md",
    "docs/06-rules-and-lessons.md",
    "contrib/rizzstack-observability",
)

CONTENT_RULES = ("no tokens", "no private hosts", "no live data")


def hygiene_hits(text: str) -> list:
    """Return line-numbered scanner hits for secret-shaped or private content."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in bee_landed.SECRET_VALUE_PATTERNS:
            if pattern.search(line):
                hits.append((number, "secret-shape"))
                break
        for pattern in bee_landed.PRIVATE_PATH_PATTERNS:
            if pattern.search(line):
                hits.append((number, "private-path"))
                break
        if HEX_RUN_RE.search(line):
            hits.append((number, "hex-run"))
        elif LONG_BASE64_RE.search(line):
            hits.append((number, "long-base64-run"))
        if PRIVATE_HOST_RE.search(line):
            hits.append((number, "private-host"))
        match = bee_landed.SENSITIVE_KEY_RE.search(line)
        if match and KEYVALUE_TAIL_RE.match(line, match.end()):
            hits.append((number, "credential-key-value-shape"))
    return hits


def _section(text: str, start_marker: str, stop_prefix: str = "## ") -> str:
    """Return the text from the line holding start_marker to the next heading."""
    begin = text.find(start_marker)
    if begin < 0:
        return ""
    line_start = text.rfind("\n", 0, begin) + 1
    rest = text[line_start:]
    stop = rest.find("\n" + stop_prefix)
    return rest if stop < 0 else rest[: stop + 1]


def _line_with_all(lines: list, words: tuple) -> bool:
    lowered = [line.lower() for line in lines]
    return any(all(word.lower() in line for word in words) for line in lowered)


class RebrandPlanConformance(unittest.TestCase):
    """Structural, boundary and hygiene checks for the rebrand plan."""

    @classmethod
    def setUpClass(cls):
        cls.text = PLAN_PATH.read_text(encoding="utf-8") if PLAN_PATH.exists() else ""
        cls.lines = cls.text.splitlines()

    def _assert_in(self, needle: str) -> None:
        self.assertIn(needle, self.text)

    def test_plan_exists_and_declares_plan_only_status(self):
        self.assertTrue(PLAN_PATH.exists(), "docs/rebrand-plan.md must exist")
        self.assertIn("Rebrand plan", self.text)
        self.assertIn("PLAN-ONLY", self.text)
        self.assertIn("no renames executed", self.text)

    def test_plan_carries_drafted_date_and_provenance(self):
        self.assertIn("Drafted:", self.text)
        self.assertIn("2026-11-16", self.text)
        self.assertIn("Provenance:", self.text)
        self.assertIn("r1", self.text)
        self.assertIn("rebuilt", self.text)

    def test_selected_names_all_present(self):
        for name in SELECTED_NAMES:
            self._assert_in(name)

    def test_mapping_table_covers_all_four_products(self):
        mapping = _section(self.text, "## 2.")
        lines = mapping.splitlines()
        for current, selected in MAPPING_ROWS:
            self.assertTrue(
                _line_with_all(lines, (current, selected)),
                f"the mapping table must map {current} to {selected}",
            )

    def test_umbrella_rationale_uses_existing_protocol_namespace(self):
        self.assertIn("rizzstack.", self.text)
        self.assertTrue(
            _line_with_all(self.lines, ("rizzstack", "namespace")),
            "the umbrella rationale must cite the existing rizzstack namespace",
        )

    def test_deferred_branding_boundary_cited(self):
        self.assertIn("NOT legally cleared", self.text)
        self.assertIn("operational names stay", self.text)
        self.assertIn("un-deferral", self.text)
        self.assertIn("templates/handoff/HANDOFF.md", self.text)

    def test_migration_checklist_covers_repo_renames_and_redirects(self):
        section = _section(self.text, "### 3.1", stop_prefix="### ")
        self.assertIn("Repo renames", section)
        self.assertIn("redirect", section.lower())
        self.assertIn("settings", section.lower())

    def test_migration_checklist_covers_catalog(self):
        section = _section(self.text, "### 3.2", stop_prefix="### ")
        self.assertIn("Catalog", section)
        self.assertIn("Nous", section)
        self.assertIn("catalog keys and titles stay", section)
        self.assertIn("docs/06-rules-and-lessons.md", section)

    def test_migration_checklist_covers_docs_and_code_references(self):
        for target in CODE_REFERENCE_TARGETS:
            self._assert_in(target)

    def test_umbrella_repo_element_table_lists_all_repos(self):
        section = _section(self.text, "### 3.5", stop_prefix="### ")
        for name in SELECTED_NAMES[:5]:
            self.assertIn(name, section)
        self.assertGreaterEqual(section.lower().count("redirect"), 3)

    def test_campaign_records_preserve_historical_names(self):
        section = _section(self.text, "### 3.6", stop_prefix="### ")
        self.assertIn("historical", section.lower())
        self.assertIn("campaign records", section.lower())
        self.assertIn("names in effect", section.lower())
        self.assertIn("sealed", section.lower())

    def test_sequencing_is_at_once_with_the_umbrella_launch(self):
        section = _section(self.text, "## 4.")
        self.assertIn("at-once", section.lower())
        self.assertIn("single", section.lower())
        self.assertIn("mixed state", section.lower())
        self.assertIn("umbrella launch", section.lower())

    def test_rollback_story_present(self):
        section = _section(self.text, "## 5.")
        self.assertIn("Rollback", section)
        self.assertIn("rename back", section.lower())
        self.assertIn("re-used", section.lower())
        self.assertIn("tags and releases", section.lower())
        self.assertIn("revert", section.lower())

    def test_owner_decision_checklist_items_need_explicit_yes(self):
        section = _section(self.text, "## 6.")
        self.assertIn("decision checklist", section.lower())
        for index in range(1, 9):
            self.assertIn(f"D{index}", section)
        self.assertIn("explicit yes", section.lower())
        self.assertIn("docs/06-rules-and-lessons.md", section)

    def test_plan_states_public_safe_content_rules(self):
        for rule in CONTENT_RULES:
            self._assert_in(rule)

    def test_plan_passes_secret_shape_scan(self):
        self.assertTrue(PLAN_PATH.exists(), "docs/rebrand-plan.md must exist")
        self.assertEqual(hygiene_hits(self.text), [])

    def test_website_plan_also_passes_secret_shape_scan(self):
        self.assertTrue(SIBLING_PATH.exists(), "docs/website-plan.md must exist")
        sibling = SIBLING_PATH.read_text(encoding="utf-8")
        self.assertEqual(hygiene_hits(sibling), [])


if __name__ == "__main__":
    unittest.main()
