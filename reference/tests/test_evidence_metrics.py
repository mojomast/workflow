"""Approved acceptance tests: optional `metrics` object in schemas/tdd-evidence.schema.json (synced from bundlebees evidence.schema.json). Coordinator-written; do not edit."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFERENCE))

from workflow import tdd  # noqa: E402

SHA = "a" * 40
FULL = {"lines_added": 10, "lines_removed": 2, "reedited_lines": 0, "attempts": 3, "retries": 2,
        "max_chain": 3, "review_findings": 1}


def record(**over):
    r = {"evidence_version": "tdd-evidence/1", "contract_id": "W1-x", "contract_sha256": "b" * 64,
         "phase": "green", "revision": SHA, "base_rev": SHA, "test_fingerprints": {"t.py": "c" * 64},
         "command": ["pytest"],
         "result": {"exit_code": 0, "tests": 1, "failures": 0, "errors": 0, "skipped": 0, "timed_out": False},
         "classification": "passed", "criteria": {"AC-001": "passed"},
         "produced_by": {"role": "verifier"}, "test_first": True, "at": "2026-11-23T10:00:00Z"}
    r.update(over)
    return r


def ok(r):
    try:
        tdd.validate_evidence(r)
        return True
    except tdd.TddError:
        return False


class MetricsSyncTests(unittest.TestCase):
    def test_ac001_baseline_record_without_metrics_is_valid(self):
        self.assertTrue(ok(record()))

    def test_ac002_full_and_partial_metrics_are_valid(self):
        self.assertTrue(ok(record(metrics=FULL)))
        self.assertTrue(ok(record(metrics={"retries": 1})))
        self.assertTrue(ok(record(metrics={})))

    def test_ac003_malformed_metrics_are_rejected(self):
        for bad in ({"retries": -1}, {"lines_added": "10"}, {"retries": 1.5}, {"retries": True},
                    {"unknown_field": 1}, [], "x", None):
            with self.subTest(bad=bad):
                self.assertFalse(ok(record(metrics=bad)))

    def test_ac004_metrics_do_not_relax_existing_requirements(self):
        r = record(metrics=FULL)
        del r["classification"]
        self.assertFalse(ok(r))

    def test_ac005_existing_enums_unchanged_and_metrics_keys_match_bundlebees(self):
        schema = json.loads((REFERENCE.parent / "schemas" / "tdd-evidence.schema.json").read_text())
        self.assertEqual(schema["properties"]["phase"]["enum"], ["red", "green", "refactor", "integration", "review"])
        props = schema["properties"]["metrics"]["properties"]
        self.assertEqual(sorted(props), sorted(FULL))
        self.assertIs(schema["properties"]["metrics"]["additionalProperties"], False)


if __name__ == "__main__":
    unittest.main()
