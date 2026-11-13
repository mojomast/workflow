"""Tests for acdd_lint.checks_report (written first, RED)."""

from __future__ import annotations

import unittest

from tests.support import clone, contract as make_contract, frozen


def report(contract, **over):
    r = {
        "contract_id": contract["id"],
        "contract_sha256": contract["review"]["contract_sha256"],
        "phases": {"red": "valid", "green": "valid"},
        "criteria": {
            "AC-001": {"status": "passed", "evidence": None},
            "AC-002": {"status": "passed", "evidence": None},
        },
        "accepted": True,
    }
    r.update(over)
    return r


class ReportTotals(unittest.TestCase):
    def setUp(self):
        from acdd_lint import checks_report
        self.m = checks_report
        self.c = frozen()

    def test_missing_extra_and_hash_mismatch_are_reported(self):
        r = report(self.c)
        del r["criteria"]["AC-002"]
        r["criteria"]["AC-999"] = {"status": "passed", "evidence": None}
        r["contract_sha256"] = "0" * 64
        problems = self.m.check_report_totals(self.c, r)
        self.assertEqual([p["code"] for p in problems], ["report_mismatch"] * 3)
        for p in problems:
            self.assertEqual(set(p), {"code", "where", "message"})
            self.assertTrue(p["message"])
        text = " ".join(p["where"] for p in problems)
        self.assertIn("AC-002", text)
        self.assertIn("AC-999", text)

    def test_accepted_must_follow_the_criteria(self):
        self.assertEqual(self.m.check_report_totals(self.c, report(self.c)), [])

        r = report(self.c, phases={"red": "invalid", "green": "valid"})
        problems = self.m.check_report_totals(self.c, r)
        self.assertEqual(sorted({p["code"] for p in problems}), ["report_mismatch"])

        r = report(self.c)
        r["criteria"]["AC-002"]["status"] = "not_run"
        problems = self.m.check_report_totals(self.c, r)
        self.assertEqual(sorted({p["code"] for p in problems}), ["report_mismatch"])

        r = report(self.c, accepted=False, phases={"red": "invalid", "green": "pending"})
        r["criteria"]["AC-002"]["status"] = "not_run"
        self.assertEqual(self.m.check_report_totals(self.c, r), [])

    def test_consistent_and_malformed_reports_are_silent(self):
        self.assertEqual(self.m.check_report_totals(self.c, report(self.c)), [])
        self.assertEqual(self.m.check_report_totals(self.c, None), [])

        unfrozen = make_contract()
        r = report(self.c, contract_sha256="0" * 64)
        self.assertEqual(self.m.check_report_totals(unfrozen, r), [])

        for bad in (
            "not a mapping",
            [],
            {},
            {"criteria": []},
            {"criteria": None},
            {"criteria": {"AC-001": "passed", "AC-002": None}, "accepted": True},
            {
                "criteria": {"AC-001": {"status": {"odd": 1}}, "AC-002": {"status": None}},
                "phases": {"red": {"odd": 1}},
                "accepted": True,
            },
        ):
            with self.subTest(bad=bad):
                self.assertEqual(self.m.check_report_totals(self.c, bad), [])

        c = clone(self.c)
        c["review"].pop("contract_sha256")
        r = report(self.c, contract_sha256="0" * 64)
        self.assertEqual(self.m.check_report_totals(c, r), [])


if __name__ == "__main__":
    unittest.main()


class ReviewAwareAcceptance(unittest.TestCase):
    """The reference demo records a review-gated criterion; acceptance must honour it."""

    def setUp(self):
        from acdd_lint import checks_report
        self.m = checks_report
        self.c = frozen(
            evidence_required=["red", "green", "review"],
            acceptance_criteria=[
                {"id": "AC-001", "given": "a price of 1000 cents", "when": "apply_tax(1000, 10) is called",
                 "then": "it returns 1100", "verification": "test", "tests": ["tests/test_tax.py::test_adds"]},
                {"id": "AC-005", "statement": "a reviewer reads the change", "verification": "review"},
            ],
        )

    def _report(self, **over):
        r = {
            "contract_id": self.c["id"],
            "contract_sha256": self.c["review"]["contract_sha256"],
            "phases": {"red": "valid", "green": "valid", "review": "valid"},
            "criteria": {"AC-001": {"status": "passed", "evidence": None},
                         "AC-005": {"status": "review_required", "evidence": None}},
            "accepted": True,
        }
        r.update(over)
        return r

    def test_reference_demo_shape_is_consistent(self):
        problems = self.m.check_report_totals(self.c, self._report())
        self.assertEqual(problems, [])
        # A report matching its contract is a document check only. It is never
        # evidence of authenticated human approval or permission to merge.
        for p in problems:
            self.assertNotIn("approve", p["message"].lower())
            self.assertNotIn("merge", p["message"].lower())

    def test_review_required_without_a_valid_review_is_refused(self):
        for phases in ({"red": "valid", "green": "valid"},
                       {"red": "valid", "green": "valid", "review": "failed"}):
            problems = self.m.check_report_totals(self.c, self._report(phases=phases))
            codes = [p["code"] for p in problems]
            self.assertIn("report_mismatch", codes, phases)
            self.assertTrue(any("review" in p["where"] or "review" in p["message"] for p in problems), phases)

    def test_review_required_must_match_the_declared_verification(self):
        c = frozen(
            evidence_required=["red", "green", "review"],
            acceptance_criteria=[
                {"id": "AC-001", "statement": "suite passes", "verification": "test", "tests": ["tests/test_tax.py::test_adds"]},
                {"id": "AC-002", "statement": "suite passes", "verification": "integration"},
            ],
        )
        r = {
            "contract_id": c["id"], "contract_sha256": c["review"]["contract_sha256"],
            "phases": {"red": "valid", "green": "valid", "review": "valid"},
            "criteria": {"AC-001": {"status": "passed"}, "AC-002": {"status": "review_required"}},
            "accepted": True,
        }
        problems = self.m.check_report_totals(c, r)
        self.assertTrue(problems)
        self.assertTrue(any("verification" in p["message"] or "review" in p["message"] for p in problems))
