"""TDD evidence tests for the reference demo (written before reference/workflow/tdd.py)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFERENCE))

from tests.test_acdd import contract  # noqa: E402

RED_T = "tests/test_pricing.py::PricingTests::test_apply_tax"
REG_T = "tests/test_pricing.py::PricingTests::test_ten_percent_off"
CSHA = "c" * 64


def case(i, outcome, et=None, msg="", stage="call"):
    return {"id": i, "outcome": outcome, "error_type": et or "", "message": msg, "stage": stage}


def result(cases, exit_code=None):
    bad = [c for c in cases if c["outcome"] in ("failed", "error")]
    return {"exit_code": (1 if bad else 0) if exit_code is None else exit_code, "tests": len(cases),
            "failures": sum(c["outcome"] == "failed" for c in cases), "errors": sum(c["outcome"] == "error" for c in cases),
            "skipped": 0, "timed_out": False, "cases": cases}


RED = [case(RED_T, "error", "AttributeError", "module 'shop.pricing' has no attribute 'apply_tax'"), case(REG_T, "passed")]
GREEN = [case(RED_T, "passed"), case(REG_T, "passed")]


class TddTests(unittest.TestCase):
    def setUp(self):
        from workflow import tdd
        self.tdd = tdd
        self.c = contract()

    def rec(self, phase, cases, fp=None, rev="b" * 40, role="verifier", sha=CSHA):
        return self.tdd.make_record(self.c, sha, phase=phase, revision=rev,
                                    test_fingerprints=fp or {"tests/test_pricing.py": "d" * 64},
                                    command=["python3", "-m", "unittest"], result=result(cases),
                                    produced_by={"role": role, "name": "reference verifier"}, test_first=True)

    def test_classification_table(self):
        t = self.tdd
        self.assertEqual(t.classify(result(RED), [RED_T], ["apply_tax"]), "behavioral_failure")
        self.assertEqual(t.classify(result([case(RED_T, "failed", "AssertionError")]), [RED_T], []), "behavioral_failure")
        self.assertEqual(t.classify(result([case(RED_T, "error", "SyntaxError", "bad", "collection")]), [RED_T], []), "syntax_error")
        self.assertEqual(t.classify(result([case(RED_T, "error", "TypeError", "x")]), [RED_T], ["apply_tax"]), "environment_error")
        self.assertEqual(t.classify(result([case("tests/test_pricing.py", "error", "ModuleNotFoundError", "No module named 'yaml'", "collection")]), [RED_T], ["apply_tax"]), "collection_error")
        self.assertEqual(t.classify(result([case(RED_T, "failed", "AssertionError"), case(REG_T, "failed", "AssertionError")]), [RED_T], []), "unrelated_failure")
        self.assertEqual(t.classify(result(GREEN), [RED_T], []), "passed")
        self.assertEqual(t.classify(None, [RED_T], []), "not_run")
        timed = result(GREEN)
        timed["timed_out"] = True
        self.assertEqual(t.classify(timed, [RED_T], []), "timeout")

    def test_red_green_refactor_rules(self):
        t = self.tdd
        red, green = self.rec("red", RED, rev="e" * 40), self.rec("green", GREEN)
        t.check_red(self.c, CSHA, red)
        t.check_green(self.c, CSHA, red, green)
        t.check_refactor(self.c, CSHA, red, green, self.rec("refactor", GREEN, rev="f" * 40))
        for bad, code in [
            (lambda: t.check_red(self.c, CSHA, self.rec("red", GREEN)), "red_incomplete"),
            (lambda: t.check_red(self.c, CSHA, self.rec("red", RED, sha="9" * 64)), "stale_revision"),
            (lambda: t.check_red(self.c, CSHA, self.rec("red", RED, role="worker")), "red_invalid"),
            (lambda: t.check_green(self.c, CSHA, None, green), "red_missing"),
            (lambda: t.check_green(self.c, CSHA, red, self.rec("green", GREEN, fp={"tests/test_pricing.py": "0" * 64})), "tests_tampered"),
            (lambda: t.check_green(self.c, CSHA, red, self.rec("green", RED)), "green_failed"),
        ]:
            with self.assertRaises(t.TddError) as cm:
                bad()
            self.assertEqual(cm.exception.code, code)

    def test_records_validate_against_the_shared_schema(self):
        rec = self.rec("red", RED, rev="e" * 40)
        self.tdd.validate_evidence(rec)
        rec["classification"] = "made_up"
        with self.assertRaises(self.tdd.TddError) as cm:
            self.tdd.validate_evidence(rec)
        self.assertEqual(cm.exception.code, "evidence_invalid")

    def test_criteria_status_and_report_never_show_unrun_as_passed(self):
        rep = self.tdd.acceptance_report(self.c, CSHA, [self.rec("red", RED, rev="e" * 40), self.rec("green", GREEN)])
        self.assertEqual(rep["phases"], {"red": "valid", "green": "valid", "integration": "unrun"})
        self.assertFalse(rep["accepted"])
        rep = self.tdd.acceptance_report(self.c, CSHA, [self.rec("red", RED, rev="e" * 40), self.rec("green", GREEN), self.rec("integration", GREEN, rev="1" * 40)])
        self.assertTrue(rep["accepted"])
        self.assertEqual(rep["criteria"]["AC-001"]["status"], "passed")
        self.assertTrue(rep["test_first"])

    def test_unittest_runner_reports_cases_with_error_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("")
            (root / "tests" / "test_x.py").write_text(
                "import unittest\n\nclass T(unittest.TestCase):\n"
                "    def test_ok(self):\n        self.assertTrue(True)\n"
                "    def test_fail(self):\n        self.assertEqual(1, 2)\n"
                "    def test_missing(self):\n        import os\n        os.no_such_thing\n"
            )
            (root / "tests" / "test_broken.py").write_text("def oops(:\n")
            out = self.tdd.run_unittest(root, ["tests/test_x.py", "tests/test_broken.py"])
            ids = {c["id"]: c for c in out["cases"]}
            self.assertEqual(ids["tests/test_x.py::T::test_ok"]["outcome"], "passed")
            self.assertEqual(ids["tests/test_x.py::T::test_fail"]["outcome"], "failed")
            self.assertEqual(ids["tests/test_x.py::T::test_missing"]["error_type"], "AttributeError")
            self.assertEqual(ids["tests/test_broken.py"]["error_type"], "SyntaxError")
            self.assertEqual(ids["tests/test_broken.py"]["stage"], "collection")
            self.assertEqual(out["exit_code"], 1)
            self.assertFalse(out["timed_out"])

    def test_class_setup_errors_are_attributed_to_the_test_class(self):
        # Found while recording the workflow repo's own RED: a setUpClass ImportError
        # was reported as "setUpClass (tests.py::...)" and so matched no test.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("")
            (root / "tests" / "test_s.py").write_text(
                "import unittest\n\nclass S(unittest.TestCase):\n"
                "    @classmethod\n    def setUpClass(cls):\n        from os import no_such_name\n"
                "    def test_a(self):\n        pass\n"
            )
            out = self.tdd.run_unittest(root, ["tests/test_s.py"])
            (case,) = out["cases"]
            self.assertEqual(case["id"], "tests/test_s.py::S")
            self.assertEqual(case["stage"], "setup")
            self.assertEqual(case["error_type"], "ImportError")
            self.assertTrue(self.tdd.matches(case["id"], "tests/test_s.py::S::test_a"))
            self.assertEqual(self.tdd.classify(out, ["tests/test_s.py::S::test_a"], ["no_such_name"]), "behavioral_failure")

    def test_fingerprints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text("x = 1\n")
            fp = self.tdd.fingerprint_files(root, ["tests/test_a.py"])
            self.assertEqual(len(fp["tests/test_a.py"]), 64)
            with self.assertRaises(self.tdd.TddError):
                self.tdd.fingerprint_files(root, ["tests/missing.py"])


if __name__ == "__main__":
    unittest.main()
