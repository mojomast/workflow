"""DEPLOY-CADENCE for the single Hermes host (BEST-PRACTICE item 15) and its receipt check.

Owner decision 2026-11-24 15:04 ET: at most one batched deploy window per day, only
from green main or tagged SHAs (never branch heads), rehearsed on a Hermes test
profile, with backup + ROLLBACK.sh + a post-deploy /v1/health receipt check recorded
as evidence. Each deploy is still the owner's typed yes; any rollback freezes deploys
until a written cause; security fixes may go out of window with the owner's yes.

scripts/check_deploy_receipt.py checks a saved /v1/health response offline against
the SHA the deploy plan named, and fails closed on anything it cannot confirm.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "deployment-runbook.md"
SPEC = importlib.util.spec_from_file_location("check_deploy_receipt", ROOT / "scripts" / "check_deploy_receipt.py")
REV = "a" * 40


def load():
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    return mod


class CadenceRule(unittest.TestCase):
    def test_runbook_states_the_cadence_rule(self) -> None:
        text = " ".join(RUNBOOK.read_text(encoding="utf-8").split())
        for fragment in ("DEPLOY-CADENCE", "at most one batched deploy window per day",
                         "green `main` or tagged SHAs", "never branch heads", "Hermes test profile",
                         "ROLLBACK.sh", "/v1/health", "scripts/check_deploy_receipt.py",
                         "freezes deploys until a written cause", "typed yes", "one day's merges",
                         "Security fixes may go out of window"):
            self.assertIn(fragment, text)


class ReceiptCheck(unittest.TestCase):
    def health(self, **receipt) -> dict:
        body = {"ok": True, "version": "0.1.18"}
        if receipt.get("omit"):
            return body
        body["deployment_receipt"] = {"deployed_at": "2026-11-24T21:00:00Z", "version": "0.1.18", "rev": REV}
        body["deployment_receipt"].update({k: v for k, v in receipt.items()})
        return body

    def check(self, health, **kw):
        kw.setdefault("expect_rev", REV)
        return load().check(health, **kw)

    def test_matching_receipt_passes_and_records_evidence(self) -> None:
        out = self.check(self.health(), expect_version="0.1.18", not_before="2026-11-24T20:30:00Z")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["schema"], "rizzstack.deploy-receipt-check/1")
        self.assertEqual((out["rev"], out["version"], out["deployed_at"]), (REV, "0.1.18", "2026-11-24T21:00:00Z"))
        self.assertEqual(out["problems"], [])

    def test_fails_closed(self) -> None:
        cases = {
            "no_receipt": self.health(omit=True),
            "receipt_invalid": {"deployment_receipt": {"status": "invalid", "reason": "receipt_malformed"}},
            "rev_mismatch": self.health(rev="b" * 40),
            "rev_missing": {"deployment_receipt": {"deployed_at": "2026-11-24T21:00:00Z", "version": "0.1.18"}},
            "not_json_object": [],
        }
        for problem, health in cases.items():
            with self.subTest(problem=problem):
                out = self.check(health)
                self.assertFalse(out["ok"])
                self.assertIn(problem, out["problems"])

    def test_stale_receipt_and_version_mismatch(self) -> None:
        out = self.check(self.health(), expect_version="0.1.19", not_before="2026-11-24T22:00:00Z")
        self.assertFalse(out["ok"])
        self.assertEqual(set(out["problems"]), {"version_mismatch", "deployed_before_window"})

    def test_expected_rev_must_be_a_full_sha(self) -> None:
        with self.assertRaises(ValueError):
            self.check(self.health(), expect_rev="abc1234")

    def test_cli_exit_codes_and_output(self) -> None:
        mod = load()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "health.json")
            path.write_text(json.dumps(self.health()))
            self.assertEqual(mod.main(["--health", str(path), "--expect-rev", REV]), 0)
            path.write_text(json.dumps(self.health(rev="c" * 40)))
            self.assertEqual(mod.main(["--health", str(path), "--expect-rev", REV]), 1)
            path.write_text("not json")
            self.assertEqual(mod.main(["--health", str(path), "--expect-rev", REV]), 1)
            self.assertEqual(mod.main(["--health", str(Path(tmp, "missing.json")), "--expect-rev", REV]), 1)


if __name__ == "__main__":
    unittest.main()
