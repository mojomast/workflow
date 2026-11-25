"""Conformance tests for the FACTORY-BALANCE rule (BEST-PRACTICE item 13, option A).

Owner decision 2026-11-24 15:04 ET: adopt memo 31's rule as coordinator-playbook
text with these thresholds, make it visible through feature_share / lane_streak
metrics, review after two waves, and enforce only after a week of data with an
owner override. The rule lives in the playbook's Bee policy chapter (docs/19 §3).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "docs" / "19-coordinator-playbook.md"


def subsection(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = re.search(r"^#{2,3} ", rest, re.MULTILINE)
    return " ".join((heading + (rest[: end.start()] if end else rest)).split())


class FactoryBalanceRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        text = PLAYBOOK.read_text(encoding="utf-8")
        self.assertIn("### Factory balance (FACTORY-BALANCE)", text)
        bee_policy = text[text.index("## 3. Bee policy"):text.index("## 4. Verification")]
        self.assertIn("### Factory balance (FACTORY-BALANCE)", bee_policy, "the rule belongs in §3 Bee policy")
        self.rule = subsection(text, "### Factory balance (FACTORY-BALANCE)")

    def test_capacity_shares(self) -> None:
        for fragment in ("at least 50%", "at most 30%", "at most 20%", "named incident or an outside finding"):
            self.assertIn(fragment, self.rule)

    def test_lane_parks_after_three_shrinking_prs(self) -> None:
        for fragment in ("3 consecutive merged PRs", "no product-source change",
                         "fewer than 30 changed product-source lines", "review-chain depth"):
            self.assertIn(fragment, self.rule)

    def test_residuals_item_and_resume_conditions(self) -> None:
        self.assertIn("one residuals backlog item", self.rule)
        self.assertRegex(self.rule, r"resumes only on the owner's yes, a new outside finding, or an incident")

    def test_lane_rate_cap(self) -> None:
        self.assertIn("at most 5 PRs per lane per 24 h", self.rule)

    def test_metrics_review_and_enforcement_stage(self) -> None:
        for fragment in ("feature_share", "lane_streak", "after two waves", "a week of data", "owner override"):
            self.assertIn(fragment, self.rule)


if __name__ == "__main__":
    unittest.main()
