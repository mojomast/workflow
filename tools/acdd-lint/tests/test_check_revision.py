"""Tests for acdd_lint.checks_revision (written first, RED)."""

from __future__ import annotations

import unittest

from acdd_lint.checks_revision import check_revision_drift

PINNED = "8045df0008cfcba949600755f4184ac5eb31163f"
GREEN = "41af7d7ef27501074b7a53e70df07111d6bc7c89"


class RevisionDrift(unittest.TestCase):
    def test_base_revision_drift_is_reported(self):
        contract = {"source_rev": PINNED}
        records = [
            ("drifted.json", {"base_rev": GREEN, "revision": GREEN}),
            ("fallback.json", {"revision": GREEN}),
        ]

        problems = check_revision_drift(contract, records)

        self.assertEqual(len(problems), 2)
        for problem, where in zip(problems, ("drifted.json", "fallback.json")):
            self.assertEqual(set(problem), {"code", "where", "message"})
            self.assertEqual(problem["code"], "evidence_revision_mismatch")
            self.assertEqual(problem["where"], where)
            self.assertIn(PINNED[:12], problem["message"])
            self.assertIn(GREEN[:12], problem["message"])

    def test_legitimate_green_and_missing_fields_are_silent(self):
        contract = {"source_rev": PINNED}
        legitimate = {"base_rev": PINNED, "revision": GREEN}

        self.assertEqual(check_revision_drift(contract, [("green.json", legitimate)]), [])
        self.assertEqual(check_revision_drift(contract, []), [])
        self.assertEqual(check_revision_drift({}, [("green.json", {"revision": GREEN})]), [])
        self.assertEqual(check_revision_drift({"source_rev": None}, [("green.json", legitimate)]), [])
        self.assertEqual(check_revision_drift(contract, [("broken.json", "not a mapping")]), [])
        self.assertEqual(
            check_revision_drift(
                contract,
                [
                    ("empty-base.json", {"base_rev": "", "revision": PINNED}),
                    ("missing-base.json", {"revision": PINNED}),
                    ("numeric-base.json", {"base_rev": 42, "revision": PINNED}),
                    ("missing-revision.json", {}),
                ],
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
