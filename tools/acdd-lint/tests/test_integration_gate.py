"""Approved tests for slice D2-integration-gate (coordinator-written, RED first).

A contract's evidence history is not accepted while its latest verifier integration record is not
``passed``: acdd-lint reports ``integration_failed``. A later passing integration supersedes an earlier
failure. Stale (other contract hash) integration records are ignored.
"""

from __future__ import annotations

import unittest

from tests.support import frozen, record

from acdd_lint.evidence import check_history


def codes(problems):
    return [p["code"] for p in problems]


class IntegrationGate(unittest.TestCase):
    def setUp(self):
        self.c = frozen(evidence_required=["red", "green", "integration"])
        self.red = ("0001-red.json", record(self.c, "red", "behavioral_failure", at="2026-11-12T18:00:00Z"))
        self.green = ("0002-green.json", record(self.c, "green", "passed", at="2026-11-12T18:05:00Z"))

    def test_failed_integration_is_reported(self):
        failed = ("0003-integration.json", record(self.c, "integration", "unrelated_failure", at="2026-11-12T18:10:00Z"))
        problems = check_history(self.c, [self.red, self.green, failed])
        self.assertIn("integration_failed", codes(problems))
        where = [p["where"] for p in problems if p["code"] == "integration_failed"][0]
        self.assertIn("0003-integration.json", where)

    def test_passed_integration_is_clean(self):
        ok = ("0003-integration.json", record(self.c, "integration", "passed", at="2026-11-12T18:10:00Z"))
        self.assertNotIn("integration_failed", codes(check_history(self.c, [self.red, self.green, ok])))

    def test_a_later_pass_supersedes_an_earlier_failure(self):
        failed = ("0003-integration.json", record(self.c, "integration", "unrelated_failure", at="2026-11-12T18:10:00Z"))
        ok = ("0004-integration.json", record(self.c, "integration", "passed", at="2026-11-12T18:20:00Z"))
        self.assertNotIn("integration_failed", codes(check_history(self.c, [self.red, self.green, failed, ok])))

    def test_a_later_failure_after_a_pass_is_reported(self):
        ok = ("0003-integration.json", record(self.c, "integration", "passed", at="2026-11-12T18:10:00Z"))
        failed = ("0004-integration.json", record(self.c, "integration", "unrelated_failure", at="2026-11-12T18:20:00Z"))
        self.assertIn("integration_failed", codes(check_history(self.c, [self.red, self.green, ok, failed])))

    def test_stale_integration_records_do_not_count(self):
        stale = record(self.c, "integration", "unrelated_failure", at="2026-11-12T18:10:00Z", contract_sha256="0" * 64)
        problems = check_history(self.c, [self.red, self.green, ("0003-integration.json", stale)])
        self.assertNotIn("integration_failed", codes(problems))
        self.assertIn("evidence_stale", codes(problems))


if __name__ == "__main__":
    unittest.main()
