"""Tests for the miniature reference workflow.

Includes the required check that an out-of-scope patch is rejected.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

REFERENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFERENCE))

from workflow.contract import ContractError, LeaseStore, lease_fingerprint, lease_record, validate_brief
from workflow.orchestrator import MARKER_NAME, UnsafeOutputDir, prepare_run_dir, run
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


    def test_teaching_fingerprint_is_not_tamper_proof(self):
        """Documents the limit: an editor who recomputes SHA-256 wins.

        That is why real systems need bundlebees' keyed (HMAC) leases.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leases.json"
            store = LeaseStore(path)
            store.put(lease_record("W1", "a" * 40, ["shop/pricing.py"]))
            data = json.loads(path.read_text())
            data["W1"]["assigned_files"].append("shop/labels.py")
            path.write_text(json.dumps(data))
            with self.assertRaises(ContractError):
                store.get("W1")  # naive edit is caught
            data["W1"]["lease_sha256"] = lease_fingerprint(data["W1"])
            path.write_text(json.dumps(data))
            widened = store.get("W1")  # recomputed hash is accepted
            self.assertIn("shop/labels.py", widened["assigned_files"])

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


class OutputDirTests(unittest.TestCase):
    """--out never deletes a folder the demo did not create."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        # Neutral cwd/home/repo so the guard checks only what each test sets.
        self.kw = {
            "cwd": self.root / "elsewhere" / "cwd",
            "home": self.root / "elsewhere" / "home",
            "repo_root": self.root / "elsewhere" / "repo",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_and_empty_folders_are_claimed_with_a_marker(self):
        new = prepare_run_dir(self.root / "new" / "run", **self.kw)
        self.assertTrue((new / MARKER_NAME).is_file())
        empty = self.root / "empty"
        empty.mkdir()
        prepare_run_dir(empty, **self.kw)
        self.assertTrue((empty / MARKER_NAME).is_file())

    def test_non_empty_folder_is_refused_and_untouched(self):
        target = self.root / "mine"
        target.mkdir()
        (target / "important.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(UnsafeOutputDir):
            prepare_run_dir(target, **self.kw)
        with self.assertRaises(UnsafeOutputDir) as ctx:
            prepare_run_dir(target, force=True, **self.kw)
        self.assertIn("marker", str(ctx.exception))
        self.assertEqual((target / "important.txt").read_text(encoding="utf-8"), "keep")

    def test_force_replaces_only_a_marked_demo_run(self):
        target = prepare_run_dir(self.root / "run", **self.kw)
        (target / "old.txt").write_text("old", encoding="utf-8")
        (target / "sub").mkdir()
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        (target / "link").symlink_to(outside)
        with self.assertRaises(UnsafeOutputDir):
            prepare_run_dir(target, **self.kw)
        prepare_run_dir(target, force=True, **self.kw)
        self.assertEqual(sorted(p.name for p in target.iterdir()), [MARKER_NAME])
        # The symlink was unlinked, its target left alone.
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_symlinked_marker_does_not_count(self):
        target = self.root / "fake"
        target.mkdir()
        (target / "data.txt").write_text("keep", encoding="utf-8")
        real_marker = self.root / "real-marker"
        real_marker.write_text("x", encoding="utf-8")
        (target / MARKER_NAME).symlink_to(real_marker)
        with self.assertRaises(UnsafeOutputDir):
            prepare_run_dir(target, force=True, **self.kw)
        self.assertTrue((target / "data.txt").exists())

    def test_protected_paths_are_always_refused(self):
        kw = dict(self.kw)
        for key in ("cwd", "home", "repo_root"):
            kw[key].mkdir(parents=True, exist_ok=True)
        for path in (
            Path("/"),
            kw["home"],
            kw["repo_root"],
            kw["cwd"],
            kw["cwd"].parent,
            kw["cwd"].parent.parent,
        ):
            with self.subTest(path=str(path)):
                with self.assertRaises(UnsafeOutputDir):
                    prepare_run_dir(path, force=True, **kw)
        # Real defaults: the actual repo root, cwd and home.
        for path in (REFERENCE.parent, Path.cwd(), Path.home()):
            with self.subTest(default=str(path)):
                with self.assertRaises(UnsafeOutputDir):
                    prepare_run_dir(path, force=True)

    def test_symlink_tricks_are_refused(self):
        home = self.kw["home"]
        home.mkdir(parents=True)
        (home / "precious.txt").write_text("keep", encoding="utf-8")
        link = self.root / "looks-harmless"
        link.symlink_to(home)
        with self.assertRaises(UnsafeOutputDir):
            prepare_run_dir(link, force=True, **self.kw)
        # A path that resolves through a symlinked parent onto home.
        parent_link = self.root / "parent-link"
        parent_link.symlink_to(home.parent)
        with self.assertRaises(UnsafeOutputDir):
            prepare_run_dir(parent_link / "home", force=True, **self.kw)
        self.assertTrue((home / "precious.txt").exists())

    def test_cli_refuses_non_empty_out_with_exit_2(self):
        target = self.root / "cli-target"
        target.mkdir()
        (target / "keep.txt").write_text("keep", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(REFERENCE / "run_demo.py"), "--out", str(target)],
            capture_output=True, text=True, cwd=str(self.root),
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("not empty", proc.stderr)
        self.assertTrue((target / "keep.txt").exists())

    def test_demo_rerun_with_force_succeeds(self):
        target = self.root / "rerun"
        first = run(target)
        self.assertTrue(first["ok"])
        with self.assertRaises(UnsafeOutputDir):
            run(target)
        second = run(target, force=True)
        self.assertTrue(second["ok"])
        self.assertTrue((target / MARKER_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
