"""Unit tests for beekeeper-guard mid-run park allowlist."""
from __future__ import annotations

import importlib.util, json, os, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load():
    path = HERE / "beekeeper" / "beekeeper-guard.py"
    spec = importlib.util.spec_from_file_location("beekeeper_guard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load()


class ParkAllowlist(unittest.TestCase):
    def test_blocks_waiting_kanban_block_tool(self):
        data = {
            "tool_name": "kanban_block",
            "tool_input": {"reason": "waiting on dispatched bee; no human action needed", "kind": "needs_input"},
        }
        msg = G.park_decision(data, gap=True)
        self.assertIsNotNone(msg)
        self.assertIn("do not park", msg.lower())

    def test_blocks_waiting_even_without_detected_gap(self):
        data = {
            "tool_name": "kanban_block",
            "tool_input": {"reason": "waiting on dispatched bee", "kind": "needs_input"},
        }
        self.assertIsNotNone(G.park_decision(data, gap=False))

    def test_allows_stuck_report(self):
        data = {
            "tool_name": "kanban_block",
            "tool_input": {"reason": "SUSPECT_STUCK att_aaaaaaaa quiet 25m", "kind": "needs_input"},
        }
        self.assertIsNone(G.park_decision(data, gap=True))

    def test_allows_verify_fail(self):
        data = {
            "tool_name": "kanban_block",
            "tool_input": {"reason": "verify fail claimed=pass scope_violation=True", "kind": "needs_input"},
        }
        self.assertIsNone(G.park_decision(data, gap=False))

    def test_blocks_shell_hermes_kanban_block_wait(self):
        data = {
            "tool_name": "terminal",
            "tool_input": {"command": "hermes kanban block --kind needs_input t_abc waiting on dispatched bee"},
        }
        self.assertIsNotNone(G.park_decision(data, gap=True))

    def test_allows_unrelated_shell(self):
        data = {"tool_name": "terminal", "tool_input": {"command": "powershell -File bees.ps1 result t_abc"}}
        self.assertIsNone(G.park_decision(data, gap=True))
        self.assertEqual(G.decide(data), {})

    def test_still_blocks_git_push(self):
        data = {"tool_name": "terminal", "tool_input": {"command": "git push origin HEAD"}}
        d = G.decide(data)
        self.assertEqual(d.get("action"), "block")
        self.assertIn("git push", d["message"])

    def test_owned_gap_detects_short_succeeded_work(self):
        with tempfile.TemporaryDirectory() as d:
            att = Path(d) / "att"
            att.mkdir()
            owned = Path(d) / "owned.json"
            owned.write_text(json.dumps({"task_ids": ["pilot-calc-0116"]}), encoding="utf-8")
            (att / "att_aaaaaaaa.json").write_text(json.dumps({
                "attempt_id": "att_aaaaaaaa", "state": "succeeded",
                "brief": {"task_id": "pilot-calc-0116"},
            }), encoding="utf-8")
            os.environ["BEES_ATT_DIR"] = str(att)
            os.environ["BEES_OWNED_FILE"] = str(owned)
            try:
                self.assertTrue(G.owned_gap())
            finally:
                os.environ.pop("BEES_ATT_DIR", None)
                os.environ.pop("BEES_OWNED_FILE", None)

    def test_owned_gap_false_when_verify_exists(self):
        with tempfile.TemporaryDirectory() as d:
            att = Path(d) / "att"
            att.mkdir()
            owned = Path(d) / "owned.json"
            owned.write_text(json.dumps({"task_ids": ["pilot-calc-0116"]}), encoding="utf-8")
            (att / "att_aaaaaaaa.json").write_text(json.dumps({
                "attempt_id": "att_aaaaaaaa", "state": "succeeded",
                "brief": {"task_id": "pilot-calc-0116"},
            }), encoding="utf-8")
            (att / "att_bbbbbbbb.json").write_text(json.dumps({
                "attempt_id": "att_bbbbbbbb", "state": "succeeded",
                "brief": {"verify_of": "att_aaaaaaaa", "task_id": "pilot-calc-0116"},
            }), encoding="utf-8")
            os.environ["BEES_ATT_DIR"] = str(att)
            os.environ["BEES_OWNED_FILE"] = str(owned)
            try:
                self.assertFalse(G.owned_gap())
            finally:
                os.environ.pop("BEES_ATT_DIR", None)
                os.environ.pop("BEES_OWNED_FILE", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
