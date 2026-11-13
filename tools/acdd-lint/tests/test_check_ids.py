"""Approved tests for the standalone duplicate acceptance-criteria id check."""

from __future__ import annotations

import unittest

from acdd_lint.checks_ids import check_duplicate_ac_ids


def contract(*criteria, contract_id="T1-tax") -> dict:
    return {"id": contract_id, "acceptance_criteria": list(criteria)}


class DuplicateAcIds(unittest.TestCase):
    def test_duplicate_ids_are_reported(self):
        c = contract(
            {"id": "AC-001"},
            {"id": "AC-002"},
            {"id": "AC-001"},
            {"id": "AC-001"},
        )
        problems = check_duplicate_ac_ids(c)
        self.assertEqual(len(problems), 1)
        problem = problems[0]
        self.assertEqual(set(problem), {"code", "where", "message"})
        self.assertEqual(problem["code"], "contract_duplicate_ac")
        self.assertEqual(problem["where"], "T1-tax")
        self.assertIn("AC-001", problem["message"])
        self.assertIn("3", problem["message"])

        no_id = contract({"id": "AC-001"}, {"id": "AC-001"}, contract_id=None)
        no_id.pop("id")
        self.assertEqual(check_duplicate_ac_ids(no_id)[0]["where"], "acceptance_criteria")

    def test_unique_and_malformed_contracts_are_silent(self):
        self.assertEqual(
            check_duplicate_ac_ids(contract({"id": "AC-001"}, {"id": "AC-002"})),
            [],
        )
        self.assertEqual(check_duplicate_ac_ids({}), [])
        self.assertEqual(check_duplicate_ac_ids({"acceptance_criteria": []}), [])
        self.assertEqual(check_duplicate_ac_ids({"acceptance_criteria": "AC-001"}), [])
        self.assertEqual(check_duplicate_ac_ids({"acceptance_criteria": None}), [])
        self.assertEqual(
            check_duplicate_ac_ids(
                {"acceptance_criteria": [None, 1, "AC-001", ["AC-001"], {"id": "AC-001"}]}
            ),
            [],
        )
        self.assertEqual(
            check_duplicate_ac_ids({"acceptance_criteria": [{}, {"id": None}]}),
            [],
        )
