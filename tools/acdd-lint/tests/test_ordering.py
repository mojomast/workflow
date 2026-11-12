"""Approved tests for evidence ordering and stale RED (slice L4, written first, RED).

Found while dogfooding acdd-lint on the workflow reference demo: records
written in the same second (same "at") were ordered by file name, so
green.json sorted before red.json and a valid history reported red_missing.
The independent review (C2) then showed that ordering same-second records by
phase label lets a GREEN written first pass as RED-before-GREEN, so ties are
now unproven unless a signer-controlled sequence and predecessor digest order
them.
Also from review: a RED recorded against an older contract hash is stale
and must not satisfy RED-before-GREEN for the current contract.
"""

from __future__ import annotations

import unittest

from tests.support import frozen, record


def codes(problems):
    return sorted({p["code"] for p in problems})


class OrderingTests(unittest.TestCase):
    def setUp(self):
        from acdd_lint import evidence
        self.m = evidence
        self.c = frozen()

    # Review C2: phase labels are not evidence of order. When RED and GREEN share
    # a timestamp and there is no signer-controlled sequence, RED-before-GREEN is
    # unproven, never inferred from the phase name or the file name.
    def test_same_second_red_and_green_without_sequence_is_unproven(self):
        at = "2026-11-12T18:00:00Z"
        red = record(self.c, "red", "behavioral_failure", at=at)
        green = record(self.c, "green", "passed", at=at)
        refactor = record(self.c, "refactor", "passed", at=at)
        history = [("green.json", green), ("red.json", red), ("refactor.json", refactor)]
        got = codes(self.m.check_history(self.c, history))
        self.assertIn("order_unproven", got)
        self.assertNotIn("red_missing", got)

    def test_same_second_unproven_even_when_file_names_sort_red_first(self):
        at = "2026-11-12T18:00:00Z"
        red = record(self.c, "red", "behavioral_failure", at=at)
        green = record(self.c, "green", "passed", at=at)
        got = codes(self.m.check_history(self.c, [("0001-red.json", red), ("0002-green.json", green)]))
        self.assertEqual(got, ["order_unproven"])

    def test_signed_sequence_orders_same_second_records(self):
        at = "2026-11-12T18:00:00Z"
        red = record(self.c, "red", "behavioral_failure", at=at, sequence=1, prev_sha256=None)
        green = record(self.c, "green", "passed", at=at, sequence=2, prev_sha256=self.m.record_digest(red))
        history = [("b.json", green), ("a.json", red)]
        self.assertEqual(self.m.check_history(self.c, history), [])

    def test_sequence_wins_over_timestamp_and_file_name(self):
        green = record(self.c, "green", "passed", at="2026-11-12T18:00:00Z", sequence=1, prev_sha256=None)
        red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:00:05Z", sequence=2,
                     prev_sha256=self.m.record_digest(green))
        got = codes(self.m.check_history(self.c, [("0001-red.json", red), ("0002-green.json", green)]))
        self.assertIn("red_missing", got)

    def test_duplicate_sequence_is_invalid_order(self):
        at = "2026-11-12T18:00:00Z"
        red = record(self.c, "red", "behavioral_failure", at=at, sequence=1, prev_sha256=None)
        green = record(self.c, "green", "passed", at=at, sequence=1, prev_sha256=None)
        got = codes(self.m.check_history(self.c, [("a.json", red), ("b.json", green)]))
        self.assertIn("order_invalid", got)

    def test_sequence_gap_is_invalid_order(self):
        red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:01:00Z", sequence=1, prev_sha256=None)
        green = record(self.c, "green", "passed", at="2026-11-12T18:02:00Z", sequence=3,
                       prev_sha256=self.m.record_digest(red))
        got = codes(self.m.check_history(self.c, [("a.json", red), ("b.json", green)]))
        self.assertIn("order_invalid", got)

    def test_broken_predecessor_chain_is_invalid_order(self):
        at = "2026-11-12T18:00:00Z"
        red = record(self.c, "red", "behavioral_failure", at=at, sequence=1, prev_sha256=None)
        green = record(self.c, "green", "passed", at=at, sequence=2, prev_sha256="a" * 64)
        got = codes(self.m.check_history(self.c, [("a.json", red), ("b.json", green)]))
        self.assertIn("order_invalid", got)

    def test_first_record_must_have_null_predecessor(self):
        red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:01:00Z", sequence=1, prev_sha256="b" * 64)
        green = record(self.c, "green", "passed", at="2026-11-12T18:02:00Z", sequence=2,
                       prev_sha256=self.m.record_digest(red))
        got = codes(self.m.check_history(self.c, [("a.json", red), ("b.json", green)]))
        self.assertIn("order_invalid", got)

    def test_mixed_sequenced_and_unsequenced_history_falls_back_to_time(self):
        red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:00:00Z", sequence=1, prev_sha256=None)
        green = record(self.c, "green", "passed", at="2026-11-12T18:00:00Z")
        got = codes(self.m.check_history(self.c, [("a.json", red), ("b.json", green)]))
        self.assertIn("order_unproven", got)

    def test_record_digest_is_canonical_sha256_of_the_signed_record(self):
        import hashlib
        import json
        red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:01:00Z")
        body = {k: v for k, v in red.items() if not k.startswith("_")}
        want = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(self.m.record_digest(red), want)
        self.assertEqual(self.m.record_digest(dict(red, _path="x")), want)

    def test_time_still_wins_over_phase(self):
        green = record(self.c, "green", "passed", at="2026-11-12T18:00:00Z")
        red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:00:05Z")
        problems = self.m.check_history(self.c, [("0001-red.json", red), ("0002-green.json", green)])
        self.assertIn("red_missing", codes(problems))

    def test_stale_red_does_not_satisfy_red_before_green(self):
        stale_red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:01:00Z", contract_sha256="f" * 64)
        green = record(self.c, "green", "passed", at="2026-11-12T18:02:00Z")
        problems = self.m.check_history(self.c, [("0001-red.json", stale_red), ("0002-green.json", green)])
        self.assertIn("evidence_stale", codes(problems))
        self.assertIn("red_missing", codes(problems))

    def test_stale_failed_red_is_reported_once_as_stale(self):
        stale_bad = record(self.c, "red", "unrelated_failure", at="2026-11-12T18:00:00Z", contract_sha256="f" * 64)
        red = record(self.c, "red", "behavioral_failure", at="2026-11-12T18:01:00Z")
        green = record(self.c, "green", "passed", at="2026-11-12T18:02:00Z")
        problems = self.m.check_history(self.c, [("0001-red.json", stale_bad), ("0002-red.json", red), ("0003-green.json", green)])
        self.assertEqual(codes(problems), ["evidence_stale"])


if __name__ == "__main__":
    unittest.main()
