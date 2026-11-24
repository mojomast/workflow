"""Characterization tests for make-verify-brief.py (stdlib only).

Pin every refusal and the rendered output, so the function split that keeps
slop-lint's complexity limit doesn't change behaviour.
"""
from __future__ import annotations

import contextlib, importlib.util, io, json, shutil, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load():
    spec = importlib.util.spec_from_file_location("make_verify_brief", HERE / "make-verify-brief.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AID = "att_0123abcd"
BRIEF = {
    "project": "demo",
    "task_id": "card-1",
    "branch": "feat/x",
    "source_rev": "a" * 40,
    "assigned_files": ["src/x.py"],
    "acceptance": {"criteria": ["x works"], "commands": ["python -m pytest -q"], "tests": ["tests/test_x.py"]},
}


class MakeVerifyBrief(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.att = self.tmp / "attempts"
        self.att.mkdir()
        self.home = self.tmp / "scripts"
        shutil.copytree(HERE / "templates", self.home / "templates")
        self.mod = _load()
        self.mod.ATT = self.att
        self.mod.HERE = self.home

    def write(self, attempt=None, result=None):
        if attempt is not None:
            (self.att / f"{AID}.json").write_text(json.dumps(attempt), encoding="utf-8")
        if result is not None:
            (self.att / f"{AID}.result.json").write_text(json.dumps(result), encoding="utf-8")

    def run_main(self, *argv):
        buf = io.StringIO()
        old = sys.argv
        sys.argv = ["make-verify-brief.py", *argv]
        try:
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as ex:
                self.mod.main()
        finally:
            sys.argv = old
        return ex.exception.code, json.loads(buf.getvalue().strip().splitlines()[0])

    def refused(self, needle, *argv):
        code, out = self.run_main(*argv)
        self.assertEqual(code, 2)
        self.assertFalse(out["ok"])
        self.assertIn(needle, out["error"])

    def test_usage_errors(self):
        self.refused("usage")
        self.refused("usage", "not-an-id")
        self.refused("usage", AID, "--priority")

    def test_missing_attempt(self):
        self.refused("work attempt not found", AID)

    def test_verify_bee_refused(self):
        self.write({"state": "succeeded", "brief": {"verify_of": "att_99999999"}})
        self.refused("itself a verify bee", AID)

    def test_not_succeeded_refused(self):
        self.write({"state": "failed", "brief": dict(BRIEF)})
        self.refused("state is failed", AID)

    def test_missing_result_refused(self):
        self.write({"state": "succeeded", "brief": dict(BRIEF)})
        self.refused("has no result", AID)

    def test_empty_patch_refused(self):
        self.write({"state": "succeeded", "brief": dict(BRIEF)}, {"patch": {"diff": "  "}})
        self.refused("no patch", AID)

    def test_missing_source_rev_refused(self):
        brief = {k: v for k, v in BRIEF.items() if k != "source_rev"}
        self.write({"state": "succeeded", "brief": brief}, {"patch": {"diff": "x"}})
        self.refused("source_rev or assigned_files", AID)

    def test_renders_brief_with_priority(self):
        self.write({"state": "succeeded", "brief": dict(BRIEF)},
                   {"patch": {"diff": "+x"}, "observed": {"local_base_rev": "b" * 40}})
        code, out = self.run_main(AID, "--priority", "high")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["ok"])
        self.assertEqual(out["verify_of"], AID)
        self.assertEqual(out["priority"], "high")
        self.assertEqual(out["brief_file"], f"verify-briefs/verify-{AID}.json")
        vb = json.loads((self.home / "verify-briefs" / f"verify-{AID}.json").read_text(encoding="utf-8"))
        self.assertEqual(vb["priority"], "high")
        self.assertEqual(out["commands"], len(vb.get("commands") or []))
        self.assertEqual(out["project"], vb.get("project"))
        self.assertEqual(vb.get("verify_of"), AID)


if __name__ == "__main__":
    unittest.main(verbosity=2)
