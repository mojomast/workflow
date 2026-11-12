"""Unit tests for replay_verify lease decisions. Stdlib only, no network, no I/O.

The lease is coordinator-owned: only the work attempt record's brief.assigned_files.
Verifier briefs, in_assigned_scope flags and patch paths must never widen it.
"""
from __future__ import annotations

import unittest
from pathlib import Path

# Import the module under test from the same folder.
HERE = Path(__file__).resolve().parent


def _load():
    import importlib.util
    path = HERE / "replay_verify.py"
    spec = importlib.util.spec_from_file_location("replay_verify_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RV = _load()


def work_attempt(assigned_files=None, include_key=True, state="succeeded"):
    brief = {}
    if include_key:
        brief["assigned_files"] = assigned_files if assigned_files is not None else []
    return {"attempt_id": "att_work", "state": state, "brief": brief}


def verify_attempt(assigned_files=None, state="succeeded"):
    brief = {"verify_of": "att_work"}
    if assigned_files is not None:
        brief["assigned_files"] = assigned_files
    return {"attempt_id": "att_verify", "state": state, "brief": brief}


def patch(*entries):
    return {"patch": {"files": [
        {"path": p, "sha256": s} for p, s in entries
    ]}}


def claims(verdict="pass", commands=None, secret=True):
    c = {"verdict": verdict, "commands": commands if commands is not None else [{"rc": 0}]}
    if secret:
        c["secret_scan"] = {"hits": []}
    return {"worker_claims": c}


class LeaseFrom(unittest.TestCase):
    def test_only_work_assigned_files(self):
        lease, missing = RV.lease_from(work_attempt(["src/a.py", "src/"]))
        self.assertEqual(lease, {"src/a.py", "src/"})
        self.assertFalse(missing)

    def test_missing_brief_key(self):
        lease, missing = RV.lease_from(work_attempt(include_key=False))
        self.assertEqual(lease, set())
        self.assertTrue(missing)


class Decide(unittest.TestCase):
    def decide(self, wa, va, wr, vr):
        return RV.decide(wa, va, wr, vr)

    def test_normal_pass(self):
        d = self.decide(
            work_attempt(["src/a.py"]),
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa")), **claims()},
        )
        self.assertEqual(d["verdict"], "pass")
        self.assertFalse(d["lease_missing"])
        self.assertTrue(d["patch_matches"])
        self.assertEqual(d["mismatch"], [])
        self.assertFalse(d["scope_violation"])
        self.assertEqual(d["scope_extras"], [])
        self.assertEqual(d["telemetry_extras"], [])
        self.assertEqual(d["failed_cmds"], 0)
        self.assertEqual(d["secret_hits"], 0)

    def test_hash_mismatch_fails(self):
        d = self.decide(
            work_attempt(["src/a.py"]),
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "bbb")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertFalse(d["patch_matches"])
        self.assertEqual(d["mismatch"], ["src/a.py"])

    def test_scope_extra_fails(self):
        d = self.decide(
            work_attempt(["src/a.py"]),
            verify_attempt(),
            patch(("src/a.py", "aaa"), ("src/b.py", "bbb")),
            {**patch(("src/a.py", "aaa"), ("src/b.py", "bbb")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertTrue(d["scope_violation"])
        self.assertEqual(d["scope_extras"], ["src/b.py"])

    def test_telemetry_progress_log_stays_pass(self):
        d = self.decide(
            work_attempt(["src/a.py"]),
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa"), ("PROGRESS.log", "ccc"),
                     ("shots/screen.png", "ddd")), **claims()},
        )
        self.assertEqual(d["verdict"], "pass")
        self.assertFalse(d["scope_violation"])
        self.assertEqual(d["scope_extras"], [])
        self.assertEqual(d["telemetry_extras"], ["PROGRESS.log", "shots/screen.png"])

    def test_lease_missing_key_fails_closed(self):
        d = self.decide(
            work_attempt(include_key=False),
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertTrue(d["lease_missing"])
        self.assertIn("assigned_files", d["note"])

    def test_missing_work_attempt_record_fails_closed(self):
        d = self.decide(
            None,
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertTrue(d["lease_missing"])
        self.assertIn("assigned_files", d["note"])

    def test_empty_assigned_files_fails_closed(self):
        d = self.decide(
            work_attempt([]),
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertTrue(d["lease_missing"])
        self.assertNotIn("src/a.py", d["lease"])

    def test_in_assigned_scope_flag_does_not_widen(self):
        wr = patch(("src/a.py", "aaa"), ("src/evil.py", "eee"))
        wr["patch"]["files"][1]["in_assigned_scope"] = True
        d = self.decide(
            work_attempt(["src/a.py"]),
            verify_attempt(),
            wr,
            {**patch(("src/a.py", "aaa"), ("src/evil.py", "eee")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertTrue(d["scope_violation"])
        self.assertEqual(d["scope_extras"], ["src/evil.py"])
        self.assertNotIn("src/evil.py", d["lease"])
        self.assertNotIn("src/evil.py", d["leased_files"])

    def test_verify_brief_assigned_files_does_not_widen(self):
        d = self.decide(
            work_attempt(["src/a.py"]),
            verify_attempt(["src/b.py"]),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa"), ("src/b.py", "bbb")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertTrue(d["scope_violation"])
        self.assertEqual(d["scope_extras"], ["src/b.py"])
        self.assertNotIn("src/b.py", d["lease"])

    def test_directory_prefix_lease(self):
        d = self.decide(
            work_attempt(["src/"]),
            verify_attempt(),
            patch(("src/a.py", "aaa"), ("src/sub/b.py", "bbb")),
            {**patch(("src/a.py", "aaa"), ("src/sub/b.py", "bbb")), **claims()},
        )
        self.assertEqual(d["verdict"], "pass")
        self.assertFalse(d["lease_missing"])
        self.assertFalse(d["scope_violation"])
        self.assertEqual(d["mismatch"], [])
        self.assertEqual(d["leased_files"], ["src/a.py", "src/sub/b.py"])

    def test_directory_prefix_does_not_cover_sibling_name(self):
        d = self.decide(
            work_attempt(["src/"]),
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa"), ("src2/b.py", "bbb")), **claims()},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertEqual(d["scope_extras"], ["src2/b.py"])

    def test_missing_secret_scan_fails(self):
        d = self.decide(
            work_attempt(["src/a.py"]),
            verify_attempt(),
            patch(("src/a.py", "aaa")),
            {**patch(("src/a.py", "aaa")), **claims(secret=False)},
        )
        self.assertEqual(d["verdict"], "fail")
        self.assertEqual(d["secret_hits"], -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
