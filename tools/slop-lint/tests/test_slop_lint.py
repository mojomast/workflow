"""Approved acceptance tests for tools/slop-lint (slop_lint). Coordinator-written; the implementer must not edit.

Run: cd tools/slop-lint && python3 -m unittest discover -s tests -t . -v
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from slop_lint import baseline as bl  # noqa: E402
from slop_lint import engine  # noqa: E402


def rules_of(src, path="m.py"):
    return sorted({f.rule for f in engine.scan_source(textwrap.dedent(src), path)})


COMPLEX = "def f(x):\n" + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(12)) + "    return -1\n"


class RuleTests(unittest.TestCase):
    def test_ac001_complexity_over_10_is_flagged(self):
        self.assertEqual(rules_of(COMPLEX), ["complexity"])

    def test_ac001_simple_function_is_clean(self):
        self.assertEqual(rules_of("def f(x):\n    if x:\n        return 1\n    return 2\n"), [])

    def test_ac002_swallowed_exception_is_flagged(self):
        self.assertEqual(rules_of("try:\n    g()\nexcept Exception:\n    pass\n"), ["swallowed-exception"])
        self.assertEqual(rules_of("try:\n    g()\nexcept:\n    pass\n"), ["swallowed-exception"])

    def test_ac002_handled_exception_is_clean(self):
        self.assertEqual(rules_of("try:\n    g()\nexcept ValueError as e:\n    log(e)\n"), [])

    def test_ac003_mutable_default_is_flagged(self):
        self.assertEqual(rules_of("def f(a=[]):\n    return a\n"), ["mutable-default-arg"])
        self.assertEqual(rules_of("def f(a=None):\n    return a\n"), [])

    def test_ac004_findings_carry_path_line_rule(self):
        fs = engine.scan_source("def f(a=[]):\n    return a\n", "pkg/x.py")
        self.assertEqual((fs[0].path, fs[0].line, fs[0].rule), ("pkg/x.py", 1, "mutable-default-arg"))

    def test_ac004_syntax_error_is_reported_not_crashed(self):
        fs = engine.scan_source("def (:\n", "bad.py")
        self.assertEqual([f.rule for f in fs], ["syntax-error"])


class BaselineTests(unittest.TestCase):
    def F(self, path, rule, n=1):
        return [engine.Finding(path, i + 1, rule, "m") for i in range(n)]

    def test_ac005_counts_per_file_and_rule(self):
        fs = self.F("a.py", "complexity", 2) + self.F("b.py", "swallowed-exception")
        self.assertEqual(bl.counts(fs), {"a.py": {"complexity": 2}, "b.py": {"swallowed-exception": 1}})

    def test_ac006_same_counts_pass(self):
        cur = bl.counts(self.F("a.py", "complexity", 2))
        r = bl.compare(cur, cur)
        self.assertEqual((r.new, r.fixed), ([], []))

    def test_ac006_a_higher_count_fails(self):
        r = bl.compare(bl.counts(self.F("a.py", "complexity", 3)), {"a.py": {"complexity": 2}})
        self.assertEqual([(p, rule) for p, rule, *_ in r.new], [("a.py", "complexity")])

    def test_ac006_a_new_file_or_rule_fails(self):
        r = bl.compare(bl.counts(self.F("n.py", "complexity")), {})
        self.assertEqual(len(r.new), 1)

    def test_ac007_a_lower_count_is_reported_fixed(self):
        r = bl.compare(bl.counts(self.F("a.py", "complexity", 1)), {"a.py": {"complexity": 2}})
        self.assertEqual((r.new, len(r.fixed)), ([], 1))

    def test_ac008_load_rejects_missing_or_malformed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(bl.BaselineError):
                bl.load(Path(d) / "nope.json")
            p = Path(d) / "b.json"
            p.write_text("{not json")
            with self.assertRaises(bl.BaselineError):
                bl.load(p)
            p.write_text(json.dumps({"a.py": {"complexity": -1}}))
            with self.assertRaises(bl.BaselineError):
                bl.load(p)
            p.write_text(json.dumps({"a.py": {"complexity": "x"}}))
            with self.assertRaises(bl.BaselineError):
                bl.load(p)


class CliTests(unittest.TestCase):
    def run_cli(self, cwd, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        return subprocess.run([sys.executable, "-m", "slop_lint", *args], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=60)

    def project(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        Path(d.name, "m.py").write_text("def f(a=[]):\n    return a\n")
        return d.name

    def test_ac009_baseline_write_then_check_passes(self):
        d = self.project()
        r = self.run_cli(d, "baseline", ".", "--write", "base.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(Path(d, "base.json").read_text()), {"m.py": {"mutable-default-arg": 1}})
        r = self.run_cli(d, "check", ".", "--baseline", "base.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ac010_new_finding_fails_and_names_file_and_rule(self):
        d = self.project()
        self.run_cli(d, "baseline", ".", "--write", "base.json")
        Path(d, "n.py").write_text("try:\n    g()\nexcept Exception:\n    pass\n")
        r = self.run_cli(d, "check", ".", "--baseline", "base.json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("n.py", r.stdout)
        self.assertIn("swallowed-exception", r.stdout)

    def test_ac011_missing_baseline_fails_closed(self):
        d = self.project()
        r = self.run_cli(d, "check", ".", "--baseline", "absent.json")
        self.assertEqual(r.returncode, 2)

    def test_ac012_stale_baseline_fails_unless_allowed_and_prune_fixes_it(self):
        d = self.project()
        self.run_cli(d, "baseline", ".", "--write", "base.json")
        Path(d, "m.py").write_text("def f(a=None):\n    return a\n")
        self.assertEqual(self.run_cli(d, "check", ".", "--baseline", "base.json").returncode, 1)
        self.assertEqual(self.run_cli(d, "check", ".", "--baseline", "base.json", "--pass-on-unpruned").returncode, 0)
        self.assertEqual(self.run_cli(d, "prune", ".", "--baseline", "base.json").returncode, 0)
        self.assertEqual(json.loads(Path(d, "base.json").read_text()), {})
        self.assertEqual(self.run_cli(d, "check", ".", "--baseline", "base.json").returncode, 0)

    def test_ac013_report_only_never_fails_on_findings_but_still_fails_on_bad_baseline(self):
        d = self.project()
        Path(d, "base.json").write_text("{}")
        r = self.run_cli(d, "check", ".", "--baseline", "base.json", "--report-only")
        self.assertEqual(r.returncode, 0)
        self.assertIn("mutable-default-arg", r.stdout)
        r = self.run_cli(d, "check", ".", "--baseline", "absent.json", "--report-only")
        self.assertEqual(r.returncode, 2)

    def test_ac014_skips_hidden_and_vendored_dirs(self):
        d = self.project()
        os.makedirs(Path(d, ".git"))
        os.makedirs(Path(d, "node_modules"))
        Path(d, ".git", "x.py").write_text("def f(a=[]):\n    return a\n")
        Path(d, "node_modules", "y.py").write_text("def f(a=[]):\n    return a\n")
        self.run_cli(d, "baseline", ".", "--write", "base.json")
        self.assertEqual(json.loads(Path(d, "base.json").read_text()), {"m.py": {"mutable-default-arg": 1}})


if __name__ == "__main__":
    unittest.main()
