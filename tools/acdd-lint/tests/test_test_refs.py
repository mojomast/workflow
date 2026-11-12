"""Approved tests for slice D1-test-refs (coordinator-written, RED first).

Dogfood lesson 1: contracts named tests that bundlebees could never match. acdd-lint flags malformed
test references (``test_ref_malformed``: empty or whitespace segments) and approved test files that no
criterion references (``test_file_unreferenced``), each with a fix.
"""

from __future__ import annotations

import unittest

from tests.support import contract

from acdd_lint.contracts import check_contract


def codes(c):
    return [p["code"] for p in check_contract(c)]


def with_tests(*tests, test_files=("tests/test_tax.py",)):
    c = contract()
    c["acceptance_criteria"][0]["tests"] = list(tests)
    c["scope"]["test_files"] = list(test_files)
    return c


class TestRefs(unittest.TestCase):
    def test_node_ids_and_class_qualified_ids_are_clean(self):
        self.assertNotIn("test_ref_malformed", codes(with_tests("tests/test_tax.py::test_adds")))
        self.assertNotIn("test_ref_malformed", codes(with_tests("tests/test_tax.py::Tax::test_adds")))

    def test_empty_or_padded_segments_are_malformed(self):
        for bad in ("tests/test_tax.py::", "tests/test_tax.py::Tax::", "tests/test_tax.py:: test_adds", "tests/test_tax.py::::test_adds"):
            with self.subTest(bad=bad):
                problems = [p for p in check_contract(with_tests(bad)) if p["code"] == "test_ref_malformed"]
                self.assertTrue(problems, bad)
                self.assertIn("file::Class::test", problems[0]["message"])

    def test_an_approved_test_file_no_criterion_names_is_reported(self):
        c = with_tests("tests/test_tax.py::test_adds", test_files=("tests/test_tax.py", "tests/test_extra.py"))
        problems = [p for p in check_contract(c) if p["code"] == "test_file_unreferenced"]
        self.assertEqual(len(problems), 1)
        self.assertIn("tests/test_extra.py", problems[0]["message"])

    def test_a_path_only_reference_counts_as_referencing_its_file(self):
        c = with_tests("tests/test_extra.py", "tests/test_tax.py::test_adds",
                       test_files=("tests/test_tax.py", "tests/test_extra.py"))
        self.assertNotIn("test_file_unreferenced", codes(c))


if __name__ == "__main__":
    unittest.main()
