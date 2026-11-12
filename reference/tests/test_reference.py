"""Tests for the miniature reference workflow.

Includes the required check that an out-of-scope patch is rejected.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

REFERENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFERENCE))

from workflow.contract import ContractError, LeaseStore, lease_record, validate_brief
from workflow.orchestrator import run
from workflow.packets import templates_dir, write_handoff
from workflow.toy import create_toy_repo
from workflow.verify import VerifyRejected, verify_manifest
from workflow.workers import work_out_of_scope, work_pricing, work_wrong_revision


class ContractTests(unittest.TestCase):
    def test_brief_requires_source_rev_assigned_files_and_acceptance(self):
        with self.assertRaises(ContractError):
            validate_brief({"title": "x", "assigned_files": ["a.py"], "acceptance": ["y"]})
        with self.assertRaises(ContractError):
            validate_brief({
                "title": "x",
                "source_rev": "abcd",
                "assigned_files": ["a.py"],
                "acceptance": ["y"],
            })

    def test_lease_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LeaseStore(Path(tmp) / "leases.json")
            rec = lease_record("W1", "a" * 40, ["shop/pricing.py"])
            store.put(rec)
            with self.assertRaises(ContractError):
                store.put(rec)
            with self.assertRaises(ContractError):
                store.try_replace("W1", lease_record("W1", "a" * 40, ["shop/labels.py"]))
            got = store.get("W1")
            self.assertEqual(got["assigned_files"], ["shop/pricing.py"])


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.toy = self.root / "toy"
        self.source_rev = create_toy_repo(self.toy)
        self.leases = LeaseStore(self.root / "leases.json")
        self.leases.put(lease_record(
            "W3-out-of-scope",
            self.source_rev,
            ["shop/pricing.py"],
        ))
        self.leases.put(lease_record(
            "W1-pricing",
            self.source_rev,
            ["shop/pricing.py", "tests/test_pricing.py"],
        ))

    def tearDown(self):
        self.tmp.cleanup()

    def test_out_of_scope_patch_is_rejected(self):
        manifest = work_out_of_scope(
            self.toy, self.source_rev, self.root / "workers",
            "W3-out-of-scope", ["shop/pricing.py"],
        )
        # The worker claims a wider lease than the coordinator recorded.
        self.assertIn("shop/labels.py", manifest["worker_claims"]["assigned_files"])
        with self.assertRaises(VerifyRejected) as ctx:
            verify_manifest(self.toy, self.leases, manifest, self.source_rev)
        self.assertIn("outside the coordinator lease", ctx.exception.reason)
        self.assertIn("shop/labels.py", ctx.exception.evidence["out_of_scope"])
        # Worker claims must not widen the lease.
        self.assertEqual(ctx.exception.evidence["assigned_files"], ["shop/pricing.py"])

    def test_in_scope_pricing_patch_is_accepted(self):
        manifest = work_pricing(
            self.toy, self.source_rev, self.root / "workers",
            "W1-pricing", ["shop/pricing.py", "tests/test_pricing.py"],
        )
        evidence = verify_manifest(self.toy, self.leases, manifest, self.source_rev)
        self.assertEqual(evidence["decision"], "accepted")
        self.assertTrue(evidence["tests"]["passed"])

    def test_wrong_source_rev_is_rejected(self):
        fake = "b" * 40
        manifest = work_wrong_revision(
            self.toy, self.source_rev, self.root / "workers",
            "W1-pricing",
            ["shop/pricing.py", "tests/test_pricing.py"],
            fake,
        )
        with self.assertRaises(VerifyRejected) as ctx:
            verify_manifest(self.toy, self.leases, manifest, self.source_rev)
        self.assertIn("source_rev", ctx.exception.reason)


class DemoTests(unittest.TestCase):
    def test_full_demo_accepts_two_and_rejects_out_of_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(Path(tmp) / "run")
            self.assertTrue(result["ok"], msg=json.dumps({k: result[k] for k in result if k != "integration"}, indent=2))
            self.assertEqual(result["accepted"], ["W1-pricing", "W2-labels"])
            self.assertIn("W3-out-of-scope", result["rejected"])
            self.assertIn("outside the coordinator lease", result["rejected"]["W3-out-of-scope"])
            self.assertTrue(result["integration"]["passed"])
            metrics = result["metrics"]
            self.assertEqual(metrics["first_pass_verification_rate"], 2 / 3)
            self.assertEqual(metrics["human_interventions"], 0)
            self.assertEqual(metrics["regression_escapes"], 0)
            self.assertEqual(metrics["cost_per_accepted_change"], 1)
            self.assertEqual(metrics["failed_worker_recovery"]["rejected"], 1)
            # Packets came from the repo templates, not a free-form substitute.
            run_dir = Path(result["run_dir"])
            handoff = (run_dir / "packets" / "W1-pricing.HANDOFF.md").read_text(encoding="utf-8")
            ret = (run_dir / "packets" / "W3-out-of-scope.RETURN.md").read_text(encoding="utf-8")
            template_h = (templates_dir() / "HANDOFF.md").read_text(encoding="utf-8")
            template_r = (templates_dir() / "RETURN.md").read_text(encoding="utf-8")
            self.assertTrue(handoff.startswith("# Handoff\n"))
            self.assertTrue(ret.startswith("# Work return and review\n"))
            self.assertIn("Use for one reviewable outcome", handoff)
            self.assertIn(template_h.splitlines()[0], handoff)
            self.assertIn(template_r.splitlines()[0], ret)
            self.assertIn("request changes", ret)
            log = Path(result["metrics_path"]).read_text(encoding="utf-8").strip().splitlines()
            self.assertTrue(any(json.loads(line)["event"] == "summary" for line in log))
            # Combined lease store stayed immutable and unwidened.
            leases = json.loads((run_dir / "contracts" / "leases.json").read_text())
            self.assertEqual(leases["W3-out-of-scope"]["assigned_files"], ["shop/pricing.py"])


if __name__ == "__main__":
    unittest.main()
