"""Unit tests for bee-watch level-triggered reconcile. Stdlib only."""
from __future__ import annotations

import json, os, sys, tempfile, time, unittest
from pathlib import Path

# Import the module under test from the same folder.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
def _load():
    import importlib.util
    path = HERE / "bee-watch.py"
    spec = importlib.util.spec_from_file_location("bee_watch_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BW = _load()


def _row(aid, state, task_id="", verify_of="", role=""):
    brief = {}
    if task_id:
        brief["task_id"] = task_id
    if verify_of:
        brief["verify_of"] = verify_of
        brief["role"] = "verify"
    if role:
        brief["role"] = role
    return {"attempt_id": aid, "state": state, "brief": brief}


class Reconcile(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.memo = {"attempts": {}, "wakes": {}}

    def ev(self, rows, leased=None, tasks=None, memo=None, stuck=None):
        ev, running, seen, wakes = BW.reconcile(
            rows, set(leased or []), set(tasks or []), self.now,
            memo if memo is not None else self.memo, stuck_fn=stuck,
        )
        return ev, running, seen, wakes

    def test_short_succeeded_never_seen_running_wakes(self):
        # The original bug: a short bee already succeeded, no lease, never in prev memo.
        ev, _, _, _ = self.ev(
            [_row("att_aaaaaaaa", "succeeded", task_id="pilot-calc-0116")],
            leased=[],
            tasks=["pilot-calc-0116"],
        )
        whys = [e["why"] for e in ev]
        self.assertEqual(whys, ["WORK_NEEDS_VERIFY"])

    def test_unowned_attempt_is_ignored(self):
        ev, _, _, _ = self.ev(
            [_row("att_bbbbbbbb", "succeeded", task_id="someone-elses-card")],
            leased=[],
            tasks=["pilot-calc-0116"],
        )
        self.assertEqual(ev, [])

    def test_lease_still_owns_without_task_id_file(self):
        ev, _, _, _ = self.ev(
            [_row("att_cccccccc", "succeeded")],
            leased=["att_cccccccc"],
            tasks=[],
        )
        self.assertEqual([e["why"] for e in ev], ["WORK_NEEDS_VERIFY"])

    def test_existing_verify_is_idempotent_no_second_dispatch_gap(self):
        ev, _, _, _ = self.ev(
            [
                _row("att_dddddddd", "succeeded", task_id="pilot-calc-0116"),
                _row("att_eeeeeeee", "running", verify_of="att_dddddddd"),
            ],
            tasks=["pilot-calc-0116"],
        )
        self.assertNotIn("WORK_NEEDS_VERIFY", [e["why"] for e in ev])

    def test_verify_terminal_wakes(self):
        ev, _, _, _ = self.ev(
            [
                _row("att_ffffffff", "succeeded", task_id="pilot-calc-0116"),
                _row("att_11111111", "succeeded", verify_of="att_ffffffff"),
            ],
            tasks=["pilot-calc-0116"],
        )
        self.assertIn("VERIFY_TERMINAL", [e["why"] for e in ev])
        self.assertNotIn("WORK_NEEDS_VERIFY", [e["why"] for e in ev])

    def test_failed_work_wakes_terminal_not_verify(self):
        ev, _, _, _ = self.ev(
            [_row("att_22222222", "failed", task_id="pilot-calc-0116")],
            tasks=["pilot-calc-0116"],
        )
        self.assertEqual([e["why"] for e in ev], ["WORK_TERMINAL"])

    def test_cooldown_suppresses_repeat_wake(self):
        rows = [_row("att_33333333", "succeeded", task_id="pilot-calc-0116")]
        ev1, _, _, wakes = self.ev(rows, tasks=["pilot-calc-0116"])
        self.assertTrue(ev1)
        ev2, _, _, _ = self.ev(rows, tasks=["pilot-calc-0116"], memo={"wakes": wakes})
        self.assertEqual(ev2, [])

    def test_stuck_running_owned_wakes(self):
        ev, running, _, _ = self.ev(
            [_row("att_44444444", "running", task_id="pilot-calc-0116")],
            tasks=["pilot-calc-0116"],
            stuck=lambda a: True,
        )
        self.assertEqual(running, 1)
        self.assertEqual([e["why"] for e in ev], ["SUSPECT_STUCK"])

    def test_stuck_unowned_does_not_wake(self):
        ev, running, _, _ = self.ev(
            [_row("att_55555555", "running", task_id="other")],
            tasks=["pilot-calc-0116"],
            stuck=lambda a: True,
        )
        self.assertEqual(running, 1)
        self.assertEqual(ev, [])


class OwnedCards(unittest.TestCase):
    def test_owned_task_ids_accepts_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "owned-cards.json"
            p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"task_ids": ["pilot-calc-0116"]}).encode("utf-8"))
            mod = _load()
            mod.OWNED = p
            self.assertEqual(mod.owned_task_ids(), {"pilot-calc-0116"})

    def test_owned_task_ids_reads_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "owned-cards.json"
            p.write_text(json.dumps({"task_ids": ["a", "b"]}), encoding="utf-8")
            old = os.environ.get("BEE_WATCH_OWNED")
            os.environ["BEE_WATCH_OWNED"] = str(p)
            try:
                # re-bind path on a fresh load
                mod = _load()
                # after load, override the module constant
                mod.OWNED = p
                self.assertEqual(mod.owned_task_ids(), {"a", "b"})
            finally:
                if old is None:
                    os.environ.pop("BEE_WATCH_OWNED", None)
                else:
                    os.environ["BEE_WATCH_OWNED"] = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
