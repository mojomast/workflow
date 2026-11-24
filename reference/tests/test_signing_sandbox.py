"""Signed evidence, sandboxed runs and REVIEW in the reference demo (written before the change, RED).

The demo stays teaching code (scripted workers, a scripted reviewer, a demo key
in the run directory), but its evidence is now HMAC-signed like bundlebees',
tampering is detected, and tests run under bubblewrap when it is available.
When bwrap is missing the record says so instead of claiming a sandbox.
"""

from __future__ import annotations

import json
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFERENCE))

NET_TEST = '''import socket, unittest


class NetTests(unittest.TestCase):
    def test_network_is_blocked(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            with self.assertRaises(OSError):
                s.connect(("1.1.1.1", 53))
        finally:
            s.close()
'''


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_key_is_private_stable_and_32_bytes(self):
        from workflow import tdd
        path = self.tmp / "keys" / "verifier.key"
        key = tdd.ensure_key(path)
        self.assertEqual(len(key), 32)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(tdd.ensure_key(path), key)

    def test_sign_and_verify_round_trip_and_detect_edits(self):
        from workflow import tdd
        key = b"k" * 32
        rec = {"evidence_version": "tdd-evidence/1", "phase": "green", "classification": "passed", "_path": "x"}
        signed = tdd.sign_record(rec, key)
        self.assertRegex(signed["signature"], r"^[0-9a-f]{64}$")
        self.assertNotIn("signature", rec)
        self.assertTrue(tdd.verify_signature(signed, key))
        self.assertTrue(tdd.verify_signature({**signed, "_path": "elsewhere"}, key))
        self.assertFalse(tdd.verify_signature({**signed, "classification": "behavioral_failure"}, key))
        self.assertFalse(tdd.verify_signature(signed, b"o" * 32))
        self.assertFalse(tdd.verify_signature(rec, key))


class SandboxTests(unittest.TestCase):
    def test_detect_backend_is_bwrap_or_none(self):
        from workflow import sandbox
        self.assertIn(sandbox.detect_backend(), ("bwrap", None))

    def test_sandboxed_run_blocks_network_and_labels_isolation(self):
        from workflow import sandbox, tdd
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "tests").mkdir()
            (tmp / "tests" / "test_net.py").write_text(NET_TEST, encoding="utf-8")
            result = tdd.run_unittest(tmp, ["tests/test_net.py"], sandbox=True)
            env = tdd.isolation_environment()
            if sandbox.detect_backend() == "bwrap":
                self.assertEqual(result["sandbox"], "bwrap")
                self.assertEqual(result["exit_code"], 0, result)
                self.assertEqual(env["sandbox"], "bwrap")
            else:
                self.assertEqual(result["sandbox"], "none")
                self.assertIn("no sandbox", env["isolation"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SignedDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from workflow import lifecycle
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = lifecycle.run_acdd(Path(cls.tmp.name) / "run")
        cls.run_dir = Path(cls.result["run_dir"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _key(self):
        from workflow import tdd
        return tdd.ensure_key(self.run_dir / "keys" / "verifier.key")

    def test_demo_still_ok_and_reports_signing_and_sandbox(self):
        self.assertTrue(self.result["ok"], json.dumps(self.result, indent=1)[:2000])
        self.assertTrue(self.result["evidence_signed"])
        self.assertIn(self.result["sandbox"], ("bwrap", "none"))

    def test_every_saved_record_is_signed(self):
        from workflow import tdd
        key = self._key()
        paths = sorted((self.run_dir / "evidence").glob("*/[a-z]*.json"))
        records = [p for p in paths if p.name in ("red.json", "green.json", "refactor.json", "integration.json", "review.json")]
        self.assertGreaterEqual(len(records), 9)
        for p in records:
            self.assertTrue(tdd.verify_signature(json.loads(p.read_text()), key), p.name)

    def test_records_name_their_isolation(self):
        green = json.loads((self.run_dir / "evidence" / "W1-pricing" / "green.json").read_text())
        self.assertIn(green["environment"].get("sandbox"), ("bwrap", "none"))

    def test_w1_has_a_scripted_review_and_is_accepted(self):
        review = json.loads((self.run_dir / "evidence" / "W1-pricing" / "review.json").read_text())
        self.assertEqual(review["phase"], "review")
        self.assertEqual(review["produced_by"]["role"], "reviewer")
        self.assertIn("scripted", review["produced_by"]["name"])
        self.assertEqual(review["classification"], "passed")
        report = json.loads((self.run_dir / "evidence" / "W1-pricing" / "report.json").read_text())
        self.assertEqual(report["phases"].get("review"), "valid")
        self.assertTrue(report["accepted"])

    def test_tampered_record_is_detected_by_the_report(self):
        from workflow import tdd
        key = self._key()
        cid = "W2-labels"
        contract = json.loads((self.run_dir / "contracts" / f"{cid}.contract.json").read_text())
        sha = contract["review"]["contract_sha256"]
        recs = [json.loads((self.run_dir / "evidence" / cid / f"{p}.json").read_text()) for p in ("red", "green", "integration")]
        self.assertTrue(tdd.acceptance_report(contract, sha, recs, key=key)["accepted"])
        recs[1] = {**recs[1], "test_fingerprints": {k: "0" * 64 for k in recs[1]["test_fingerprints"]}}
        report = tdd.acceptance_report(contract, sha, recs, key=key)
        self.assertEqual(report["phases"]["green"], "evidence_tampered")
        self.assertFalse(report["accepted"])


if __name__ == "__main__":
    unittest.main()
