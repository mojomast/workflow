"""End-to-end tests for the contract-first, test-first demo (written before lifecycle.py)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFERENCE))


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from workflow import lifecycle
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = lifecycle.run_acdd(Path(cls.tmp.name) / "run")
        cls.run_dir = Path(cls.result["run_dir"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_overall_ok(self):
        self.assertTrue(self.result["ok"], json.dumps(self.result, indent=1)[:2000])

    def test_invalid_contract_rejected_before_dispatch(self):
        self.assertEqual(self.result["rejected_contracts"]["W0-invalid"], "contract_invalid")
        self.assertFalse((self.run_dir / "workers" / "W0-invalid").exists())

    def test_red_evidence_is_behavioural_and_against_tests_only(self):
        for tid in ("W1-pricing", "W2-labels"):
            red = json.loads((self.run_dir / "evidence" / tid / "red.json").read_text())
            self.assertEqual(red["classification"], "behavioral_failure")
            self.assertEqual(red["phase"], "red")
            self.assertNotEqual(red["revision"], red["base_rev"])
            self.assertEqual(red["produced_by"]["role"], "verifier")
            self.assertTrue(red["test_fingerprints"])

    def test_green_and_refactor_keep_the_same_tests(self):
        red = json.loads((self.run_dir / "evidence" / "W1-pricing" / "red.json").read_text())
        green = json.loads((self.run_dir / "evidence" / "W1-pricing" / "green.json").read_text())
        refactor = json.loads((self.run_dir / "evidence" / "W1-pricing" / "refactor.json").read_text())
        self.assertEqual(green["classification"], "passed")
        self.assertEqual(refactor["classification"], "passed")
        self.assertEqual(red["test_fingerprints"], green["test_fingerprints"])
        self.assertEqual(green["test_fingerprints"], refactor["test_fingerprints"])
        self.assertNotEqual(green["revision"], refactor["revision"])

    def test_negative_workers_get_explicit_failure_states(self):
        self.assertEqual(self.result["rejected"]["W3-out-of-scope"], "scope_violation")
        self.assertEqual(self.result["rejected"]["W4-weakened-tests"], "tests_tampered")

    def test_parallel_contracts_accepted_and_integrated(self):
        self.assertEqual(sorted(self.result["accepted"]), ["W1-pricing", "W2-labels"])
        self.assertTrue(self.result["integration"]["passed"])
        for tid in ("W1-pricing", "W2-labels"):
            report = json.loads((self.run_dir / "evidence" / tid / "report.json").read_text())
            self.assertTrue(report["accepted"], report)
            self.assertTrue(report["test_first"])

    def test_acceptance_report_links_evidence_and_marks_unrun(self):
        text = (self.run_dir / "ACCEPTANCE.md").read_text()
        self.assertIn("AC-001", text)
        self.assertIn("evidence/W1-pricing/", text)
        self.assertIn("not run", text.lower())
        self.assertIn("human gates", text.lower())

    def test_worker_self_reports_are_not_authority(self):
        manifest = json.loads((self.run_dir / "evidence" / "W4-weakened-tests.manifest.json").read_text())
        self.assertEqual(manifest["worker_claims"]["result"], "all tests pass")
        self.assertIn("W4-weakened-tests", self.result["rejected"])

    def test_legacy_demo_still_runs(self):
        from workflow.orchestrator import run
        with tempfile.TemporaryDirectory() as tmp:
            legacy = run(Path(tmp) / "legacy")
        self.assertTrue(legacy["ok"])

    def test_demo_cli_defaults_to_acdd_and_keeps_legacy_flag(self):
        import run_demo
        self.assertTrue(hasattr(run_demo, "main"))
        args = run_demo.parse_args(["--legacy"])
        self.assertTrue(args.legacy)
        self.assertFalse(run_demo.parse_args([]).legacy)


if __name__ == "__main__":
    unittest.main()
