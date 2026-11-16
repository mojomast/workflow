"""Conformance tests for docs/website-plan.md (the static docs-site plan).

The plan designs a static docs site for the workflow repository: a generator
choice with reasoning (stdlib and no-heavy-deps preferred), a content map
(what, why, how, quickstarts, architecture, protocol, status), hosting options
with a recommendation, the Night Hive theme application gated on the
deferred-branding boundary, a launch checklist and public-safe content rules
(no tokens, no private hosts, no live data). No site is deployed by this
slice.

The hygiene check reuses the repository's own scanners (tools/bee_landed.py)
plus structural value-shape detectors and must find zero hits. Runs under
pytest (python3 -m pytest tests/test_website_plan.py -q) and under unittest
(python3 -m unittest tests.test_website_plan -q); no network, no third-party
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

PLAN_PATH = ROOT / "docs" / "website-plan.md"
SIBLING_PATH = ROOT / "docs" / "rebrand-plan.md"

HEX_RUN_RE = re.compile(r"[0-9a-fA-F]{40,}")
LONG_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{32,}")
PRIVATE_HOST_RE = re.compile(
    r"\b(?:192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})\b"
)
KEYVALUE_TAIL_RE = re.compile(r"s?[ \t]*[:=][ \t]*[^ \t]")

CONTENT_MAP_ROWS = (
    "What",
    "Why",
    "How",
    "Quickstarts",
    "Architecture",
    "Protocol",
    "Status",
)

CONTENT_MAP_SOURCES = (
    "docs/12-three-layer-architecture.md",
    "docs/16-acdd-tdd.md",
    "reference/README.md",
    "acceptance/README.md",
    "ROADMAP.md",
    "docs/31-campaign-continuity.md",
)

HOSTING_OPTIONS = ("GitHub Pages", "VPS", "Cloudflare Pages", "Netlify")

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


class WebsitePlanConformance(unittest.TestCase):
    """Structural, boundary and hygiene checks for the website plan."""

    @classmethod
    def setUpClass(cls):
        cls.text = PLAN_PATH.read_text(encoding="utf-8") if PLAN_PATH.exists() else ""
        cls.lines = cls.text.splitlines()

    def _assert_in(self, needle: str) -> None:
        self.assertIn(needle, self.text)

    def test_plan_exists_and_declares_plan_status(self):
        self.assertTrue(PLAN_PATH.exists(), "docs/website-plan.md must exist")
        self.assertIn("Website plan", self.text)
        self.assertIn("PLAN", self.text)
        self.assertIn("no site deployed", self.text)

    def test_plan_carries_drafted_date_and_provenance(self):
        self.assertIn("Drafted:", self.text)
        self.assertIn("2026-11-16", self.text)
        self.assertIn("Provenance:", self.text)
        self.assertIn("r1", self.text)

    def test_night_hive_theme_gated_on_un_deferral(self):
        self.assertIn("Night Hive", self.text)
        self.assertIn("when branding un-defers", self.text)
        self.assertIn("NOT legally cleared", self.text)

    def test_generator_choice_with_reasoning(self):
        self.assertIn("stdlib-only Python builder", self.text)
        self.assertIn("Reasoning", self.text)
        self.assertIn("Alternatives considered", self.text)
        lowered = self.text.lower()
        for alternative in ("mkdocs", "sphinx", "hand-written html"):
            self.assertIn(alternative, lowered)

    def test_stdlib_no_heavy_deps_preference(self):
        self.assertIn("Python 3", self.text)
        self.assertIn("stdlib", self.text)
        self.assertIn("no third-party", self.text)
        self.assertIn("fail closed", self.text.lower())

    def test_content_map_covers_required_sections(self):
        section = _section(self.text, "## 3.")
        for row in CONTENT_MAP_ROWS:
            self.assertRegex(section, rf"(?m)^\|\s*{row}\s*\|")

    def test_content_map_maps_real_repository_sources(self):
        for source in CONTENT_MAP_SOURCES:
            self._assert_in(source)

    def test_hosting_options_listed(self):
        for option in HOSTING_OPTIONS:
            self._assert_in(option)

    def test_hosting_recommendation_is_explicit(self):
        recommendation = [
            line
            for line in self.lines
            if "Recommendation:" in line and "GitHub Pages" in line
        ]
        self.assertTrue(recommendation, "the recommendation must name GitHub Pages")
        lowered = self.text.lower()
        self.assertIn("free", lowered)
        self.assertIn("already", lowered)

    def test_night_hive_theme_application_section(self):
        self.assertRegex(self.text, r"(?m)^#+ .*Night Hive")
        section = _section(self.text, "## 5.")
        self.assertIn("CSS custom properties", section)
        self.assertIn("unbranded baseline", section)
        self.assertIn("palette swap", section)
        self.assertIn("un-deferral", section)

    def test_launch_checklist_with_human_gate(self):
        section = _section(self.text, "## 6.")
        self.assertIn("Launch checklist", section)
        self.assertGreaterEqual(
            len(re.findall(r"(?m)^\d+\.", section)), 5, "steps must be numbered"
        )
        self.assertTrue(
            any("Kyle" in line and "explicit yes" in line for line in section.splitlines()),
            "the publish step must carry the human approval gate",
        )
        self.assertIn("publish", section.lower())

    def test_public_safe_content_rules_enforced(self):
        for rule in CONTENT_RULES:
            self._assert_in(rule)
        lowered = self.text.lower()
        self.assertIn("fail", lowered)
        self.assertIn("closed", lowered)
        self.assertIn("README", self.text)

    def test_plan_passes_secret_shape_scan(self):
        self.assertTrue(PLAN_PATH.exists(), "docs/website-plan.md must exist")
        self.assertEqual(hygiene_hits(self.text), [])

    def test_rebrand_plan_reference_and_test_declaration(self):
        self.assertTrue(SIBLING_PATH.exists(), "docs/rebrand-plan.md must exist")
        self.assertIn("tests/test_website_plan.py", self.text)
        self.assertIn("RED-first", self.text)


if __name__ == "__main__":
    unittest.main()
