"""Exercise the four sibling working trees using a synthetic receipt and local files only.

From workflow: python3 -B contrib/core-review/test_core_usage_roundtrip.py
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


class UsageHandoff(unittest.TestCase):
    def test_terminal_event_to_one_ledger_row_on_replay(self):
        paths = [ROOT / name for name in (
            "hyvv", "workflow/tools", "workflow/contrib/rizzstack-observability", "bundlebees")]
        if __name__ != "__main__" and not all(p.is_dir() for p in [*paths, ROOT / "orbitdesktop"]):
            self.skipTest("requires the four sibling checkouts")
        with patch.object(sys, "path", [*map(str, paths), *sys.path]):
            import launcher
            import landing_export
            import bee_landed
            from collector import Collector
            from bundlebees_plugin import bee_events
        attempt = {"attempt_id": "audit-sample", "state": "succeeded", "updated_at": 1000,
                   "model": "deepseek-v4.1-flash", "brief": {"assigned_files": ["sample.py"],
                   "source_rev": "1" * 40, "task_id": "task-1", "job_id": "job-1", "feature_id": "feature-1"}}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"WORKFLOW_SRC": str(ROOT / "workflow")}):
            state = Path(tmp)
            receipt = state / "receipt.json"
            receipt.write_text(json.dumps({"schema": "orbit.local-worker.result/v1", "attempt_id": "audit-sample",
                                          "observed": {"stop_reason": "generation completed normally",
                                                       "usage": {"input": 10, "output": 5, "cache_read": 0, "total": 18}}}))
            event = launcher.build_landed_event(attempt, result_path=receipt)
            self.assertNotIn("stop_reason", event["rizzstackusage"])
            self.assertEqual(event["rizzstackusage"]["input"], 10)
            # Use separate data directories as the launcher and coordinator do.
            worker = state / "worker"
            launcher.write_landed_event(landing_export.landed_outbox(worker), event)
            page = landing_export.export_events(worker, limit=1)
            [exported] = page["events"]
            self.assertEqual(exported["event"], event)
            self.assertFalse(landing_export.export_events(worker, after=page["next_cursor"])["events"])
            event = exported["event"]
            self.assertEqual(bee_landed.validate(event), event)
            self.assertTrue(bee_events.validate_event(event))
            self.assertTrue(bee_events.record_landing(state, event)["created"])
            self.assertFalse(bee_events.record_landing(state, event)["created"])
            ledger = state / "usage.jsonl"
            cmd = [sys.executable, str(ROOT / "orbitdesktop/pc-launcher/scripts/usage_ingest_service.py"),
                   "once", "--outbox", str(state / "events/outbox"), "--ledger", str(ledger)]
            for expected_added in (1, 0):
                status = json.loads(subprocess.check_output(cmd, text=True))
                self.assertEqual(status["added"], expected_added, status)
            [row] = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual((row["key"], row["input_tokens"], row["output_tokens"], row["cache_read_tokens"]),
                             ("attempt:audit-sample", 10, 5, 0))
            self.assertEqual(row["route"], "go")
            totals = Collector(usage_path=ledger).usage_section()[0]["totals"]
            self.assertEqual((totals["requests"], totals["total_tokens"]), (1, 18))
            self.assertIsNone(totals["cost_usd"])


if __name__ == "__main__":
    unittest.main()
