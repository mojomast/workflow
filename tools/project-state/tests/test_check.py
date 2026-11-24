import copy
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import check  # noqa: E402

PARKED = json.loads((REPO / "schemas/examples/project-state.parked.json").read_text())
ACTIVE = json.loads((REPO / "schemas/examples/project-state.active.json").read_text())


class Repo:
    def __init__(self, doc=None, snapshot=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        (self.root / ".workflow").mkdir(parents=True)
        if snapshot:
            (self.root / "PARKED.md").write_text("# Parked\n")
        if doc is not None:
            self.write(doc)

    def write(self, doc):
        (self.root / ".workflow/project-state.json").write_text(json.dumps(doc))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()


class SnapshotPath(unittest.TestCase):
    BAD = ["../x.md", "a/../x.md", "a/b/../../x.md", "a/..", "/etc/x", "a//b", "./x.md",
           "a/./b", "a/", "", "a\\..\\b", "..", "."]
    GOOD = ["PARKED.md", "docs/PARKED.md", ".workflow/history/PARKED-2026-11-12.md", "a..b.md", "..x/y.md"]

    def test_schema_and_checker_use_the_same_rule(self):
        for f in ("project-state.schema.json", "project-state-event.schema.json"):
            s = json.loads((REPO / "schemas" / f).read_text())
            prop = s["properties"]["snapshot_path"]
            pat = prop.get("pattern") or prop["oneOf"][1]["pattern"]
            self.assertEqual(pat, check.SAFE_PATH.pattern, f)

    def test_interior_traversal_refused(self):
        for p in self.BAD:
            self.assertIsNone(check.SAFE_PATH.match(p), p)
        for p in self.GOOD:
            self.assertIsNotNone(check.SAFE_PATH.match(p), p)

    def test_symlink_component_refused(self):
        with Repo() as r:
            outside = Path(r.tmp.name) / "outside"
            outside.mkdir()
            (outside / "PARKED.md").write_text("x")
            os.symlink(outside, r.root / "docs")
            with self.assertRaises(check.StateError) as e:
                check.safe_snapshot(r.root, "docs/PARKED.md")
            self.assertEqual(e.exception.code, "snapshot_path_symlink")
            os.symlink(outside / "PARKED.md", r.root / "LINK.md")
            with self.assertRaises(check.StateError):
                check.safe_snapshot(r.root, "LINK.md")

    def test_missing_and_directory_snapshot_refused(self):
        with Repo(snapshot=False) as r:
            with self.assertRaises(check.StateError) as e:
                check.safe_snapshot(r.root, "PARKED.md")
            self.assertEqual(e.exception.code, "snapshot_missing")
            (r.root / "PARKED.md").mkdir()
            with self.assertRaises(check.StateError):
                check.safe_snapshot(r.root, "PARKED.md")


class ReparsePoints(unittest.TestCase):
    """Windows junctions and other reparse points are not caught by is_symlink/S_ISLNK."""

    REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT

    def _fake_lstat(self, flagged):
        real = os.lstat

        class St:
            def __init__(self, st, attrs):
                self.st_mode = st.st_mode
                self.st_size = st.st_size
                self.st_file_attributes = attrs

        def lstat(p, *a, **k):
            st = real(p, *a, **k)
            return St(st, self.REPARSE if Path(p).name == flagged else 0)

        return lstat

    def test_reparse_point_component_refused(self):
        from unittest import mock

        with Repo() as r:
            (r.root / "docs").mkdir()
            (r.root / "docs" / "PARKED.md").write_text("x")
            with mock.patch.object(check.os, "lstat", self._fake_lstat("docs")):
                with self.assertRaises(check.StateError) as e:
                    check.safe_snapshot(r.root, "docs/PARKED.md")
            self.assertEqual(e.exception.code, "snapshot_path_symlink")

    def test_reparse_point_file_refused(self):
        from unittest import mock

        with Repo() as r:
            with mock.patch.object(check.os, "lstat", self._fake_lstat("PARKED.md")):
                with self.assertRaises(check.StateError) as e:
                    check.safe_snapshot(r.root, "PARKED.md")
            self.assertEqual(e.exception.code, "snapshot_path_symlink")

    def test_junction_reported_by_isjunction_refused(self):
        from unittest import mock

        with Repo() as r:
            (r.root / "docs").mkdir()
            (r.root / "docs" / "PARKED.md").write_text("x")
            with mock.patch.object(check.os.path, "isjunction", lambda p: Path(p).name == "docs", create=True):
                with self.assertRaises(check.StateError) as e:
                    check.safe_snapshot(r.root, "docs/PARKED.md")
            self.assertEqual(e.exception.code, "snapshot_path_symlink")

    def test_state_dir_reparse_point_fails_closed(self):
        from unittest import mock

        with Repo(ACTIVE) as r:
            with mock.patch.object(check.os, "lstat", self._fake_lstat(".workflow")):
                self.assertEqual(check.gate(r.root)["code"], "invalid_project_state")

    @unittest.skipUnless(os.name == "nt", "real directory junctions exist only on Windows")
    def test_real_windows_junction_refused(self):
        import subprocess

        with Repo() as r:
            outside = Path(r.tmp.name) / "outside"
            outside.mkdir()
            (outside / "PARKED.md").write_text("x")
            subprocess.run(["cmd", "/c", "mklink", "/J", str(r.root / "docs"), str(outside)],
                           check=True, capture_output=True)
            with self.assertRaises(check.StateError) as e:
                check.safe_snapshot(r.root, "docs/PARKED.md")
            self.assertEqual(e.exception.code, "snapshot_path_symlink")


class Gate(unittest.TestCase):
    def test_examples_valid_and_use_at_by(self):
        for d in (PARKED, ACTIVE):
            check.validate(d)
            self.assertIn("at", d)
            self.assertIn("by", d)
            self.assertNotIn("changed_at", d)
        ev = json.loads((REPO / "schemas/examples/project-state-event.json").read_text())
        self.assertIn("by", ev)
        self.assertEqual(ev["generation"], PARKED["generation"])

    def test_missing_file_defaults_active_and_is_recorded(self):
        with Repo() as r:
            out = check.gate(r.root)
            self.assertTrue(out["allow"])
            self.assertTrue(out["defaulted"])

    def test_parked_refused_with_hyvv_code(self):
        with Repo(PARKED) as r:
            out = check.gate(r.root)
            self.assertFalse(out["allow"])
            self.assertEqual(out["code"], "project_parked")
            self.assertEqual(out["state"], "parked")
            self.assertEqual({k: out[k] for k in ("at", "by")}, {"at": PARKED["at"], "by": PARKED["by"]})

    def test_invalid_file_fails_closed(self):
        cases = []
        d = copy.deepcopy(ACTIVE); d["generation"] = 5; cases.append(d)
        d = copy.deepcopy(ACTIVE); d["state"] = "paused"; cases.append(d)
        d = copy.deepcopy(ACTIVE); d["changed_at"] = d.pop("at"); cases.append(d)
        d = copy.deepcopy(PARKED); d["history"][-1]["reason"] = "different"; cases.append(d)
        d = copy.deepcopy(PARKED); d["snapshot_path"] = "docs/../../x.md"; cases.append(d)
        d = copy.deepcopy(PARKED); del d["snapshot_path"]; cases.append(d)
        for d in cases:
            with Repo(d) as r:
                out = check.gate(r.root)
                self.assertFalse(out["allow"], d)
                self.assertIn(out["code"], ("invalid_project_state", "snapshot_path_invalid"))
        with Repo() as r:
            (r.root / ".workflow/project-state.json").write_text("{not json")
            self.assertEqual(check.gate(r.root)["code"], "invalid_project_state")

    def test_state_file_symlink_fails_closed(self):
        with Repo() as r:
            real = Path(r.tmp.name) / "elsewhere.json"
            real.write_text(json.dumps(ACTIVE))
            os.symlink(real, r.root / ".workflow/project-state.json")
            self.assertEqual(check.gate(r.root)["code"], "invalid_project_state")

    def test_generation_checked_dispatch(self):
        with Repo(ACTIVE) as r:
            first = check.gate(r.root)
            self.assertTrue(first["allow"])
            d = copy.deepcopy(ACTIVE)
            e = {"state": "parked", "at": "2026-11-12T22:00:00Z", "by": "human:owner", "reason": "Set aside."}
            d.update(e, generation=2, snapshot_path="PARKED.md")
            d["history"].append(e)
            r.write(d)
            out = check.gate(r.root, expect_generation=first["generation"])
            self.assertFalse(out["allow"])
            self.assertEqual(out["code"], "project_state_changed")

    def test_resume_must_be_human_and_transitions_valid(self):
        d = copy.deepcopy(PARKED)
        e = {"state": "active", "at": "2026-11-13T15:00:00Z", "by": "agent:hermes-forge", "reason": "Back."}
        d.update(e, generation=3); d["history"].append(e); d.pop("snapshot_path")
        with self.assertRaises(check.StateError):
            check.validate(d)
        d["by"] = d["history"][-1]["by"] = "human:owner"
        check.validate(d)
        bad = copy.deepcopy(ACTIVE)
        e = {"state": "active", "at": "2026-11-02T15:00:00Z", "by": "human:owner", "reason": "noop"}
        bad.update(e, generation=2); bad["history"].append(e)
        with self.assertRaises(check.StateError):
            check.validate(bad)

    def test_cli_exit_codes(self):
        with Repo(PARKED) as r:
            self.assertEqual(check.main([str(r.root)]), 3)
        with Repo(ACTIVE) as r:
            self.assertEqual(check.main([str(r.root)]), 0)


class JsonSchema(unittest.TestCase):
    def test_examples_and_bad_paths_against_schemas(self):
        try:
            import jsonschema
        except ImportError:
            if os.environ.get("CI"):
                raise
            self.skipTest("jsonschema not installed (required in CI)")
        state = json.loads((REPO / "schemas/project-state.schema.json").read_text())
        event = json.loads((REPO / "schemas/project-state-event.schema.json").read_text())
        V = jsonschema.Draft202012Validator
        for d in (PARKED, ACTIVE, json.loads((REPO / "examples/temple-of-hermes/project-state.json").read_text())):
            V(state).validate(d)
        V(event).validate(json.loads((REPO / "schemas/examples/project-state-event.json").read_text()))
        for bad in SnapshotPath.BAD:
            d = copy.deepcopy(PARKED); d["snapshot_path"] = bad
            self.assertFalse(V(state).is_valid(d), bad)
        d = copy.deepcopy(PARKED); d["changed_by"] = d.pop("by")
        self.assertFalse(V(state).is_valid(d))
        d = copy.deepcopy(PARKED); del d["generation"]
        self.assertFalse(V(state).is_valid(d))


if __name__ == "__main__":
    unittest.main()
