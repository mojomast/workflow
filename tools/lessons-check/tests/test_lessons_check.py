"""Approved acceptance tests for tools/lessons-check (lessons_check): recurring review findings as deterministic checks.
Coordinator-written; the implementer must not edit.

Run: cd tools/lessons-check && python3 -m unittest discover -s tests -t . -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from lessons_check import registry, runner  # noqa: E402

IDS = {"contract-test-ref", "evidence-absolute-path", "brief-may-create"}


def write(d, name, obj):
    p = Path(d) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)
    return p


class RegistryTests(unittest.TestCase):
    def test_ac001_registry_lists_the_seed_lessons_with_provenance(self):
        lessons = registry.load()
        self.assertEqual({l["id"] for l in lessons}, IDS)
        for l in lessons:
            for k in ("id", "source", "summary", "fix"):
                self.assertIsInstance(l.get(k), str)
                self.assertTrue(l[k].strip(), (l["id"], k))

    def test_ac002_registry_file_is_json_in_the_package(self):
        data = json.loads((ROOT / "lessons_check" / "lessons.json").read_text())
        self.assertIsInstance(data, list)

    def test_ac003_malformed_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            bad = write(d, "l.json", "[{\"id\": \"x\"}]")
            with self.assertRaises(registry.RegistryError):
                registry.load(bad)
            with self.assertRaises(registry.RegistryError):
                registry.load(Path(d) / "missing.json")
            dup = write(d, "d.json", [{"id": "a", "source": "s", "summary": "m", "fix": "f"}] * 2)
            with self.assertRaises(registry.RegistryError):
                registry.load(dup)


class RuleTests(unittest.TestCase):
    def check(self, d):
        return runner.check([d])

    def test_ac004_contract_test_reference_without_double_colon_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.contract.json", {"contract_version": "acdd/1", "id": "X", "acceptance_criteria": [
                {"id": "AC-001", "tests": ["tests/test_a.py", "tests/test_a.py::T::test_ok"]}]})
            f = [x for x in self.check(d) if x.rule == "contract-test-ref"]
            self.assertEqual(len(f), 1)
            self.assertIn("a.contract.json", f[0].path)
            self.assertIn("tests/test_a.py", f[0].message)

    def test_ac005_clean_contract_has_no_findings(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.contract.json", {"contract_version": "acdd/1", "id": "X", "acceptance_criteria": [
                {"id": "AC-001", "tests": ["tests/test_a.py::T::test_ok"]}]})
            self.assertEqual(self.check(d), [])

    def test_ac006_evidence_record_with_absolute_path_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "evidence/X/0001-red.json", {"evidence_version": "tdd-evidence/1",
                  "result": {"failure_message": "File \"/home/someone/venv/lib/x.py\" line 1"}})
            write(d, "evidence/X/0002-green.json", {"evidence_version": "tdd-evidence/1",
                  "result": {"failure_message": "tests/test_a.py:3 AssertionError"}})
            f = [x for x in self.check(d) if x.rule == "evidence-absolute-path"]
            self.assertEqual(len(f), 1)
            self.assertIn("0001-red.json", f[0].path)

    def test_ac007_evidence_windows_and_workspace_paths_are_flagged_too(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "evidence/X/0001-red.json", {"evidence_version": "tdd-evidence/1", "notes": "ran in /workspace/job"})
            write(d, "evidence/X/0002-red.json", {"evidence_version": "tdd-evidence/1", "notes": "ran in C:\\\\Users\\\\bob\\\\job"})
            self.assertEqual(len([x for x in self.check(d) if x.rule == "evidence-absolute-path"]), 2)

    def test_ac008_brief_telling_a_bee_it_may_create_a_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "briefs/W.json", {"objective": "Do it. You may create an empty __init__.py locally.", "assigned_files": ["a.py"]})
            write(d, "briefs/V.json", {"objective": "Create a.py exactly.", "assigned_files": ["a.py"]})
            f = [x for x in self.check(d) if x.rule == "brief-may-create"]
            self.assertEqual(len(f), 1)
            self.assertIn("W.json", f[0].path)

    def test_ac009_unreadable_or_non_json_files_are_skipped_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "evidence/X/0001.json", "{not json")
            write(d, "x.contract.json", "{not json")
            self.assertEqual(self.check(d), [])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "lessons_check", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)

    def test_ac010_exit_codes_and_report_only(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.contract.json", {"acceptance_criteria": [{"id": "AC-001", "tests": ["tests/x.py"]}]})
            p = self.run_cli("check", d)
            self.assertEqual(p.returncode, 1)
            self.assertIn("contract-test-ref", p.stdout)
            self.assertIn("a.contract.json", p.stdout)
            self.assertEqual(self.run_cli("check", d, "--report-only").returncode, 0)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_cli("check", d).returncode, 0)

    def test_ac011_missing_path_is_a_usage_error_even_with_report_only(self):
        self.assertEqual(self.run_cli("check", "/nonexistent-path-xyz", "--report-only").returncode, 2)

    def test_ac012_list_prints_every_lesson_id(self):
        p = self.run_cli("list")
        self.assertEqual(p.returncode, 0)
        for i in IDS:
            self.assertIn(i, p.stdout)


if __name__ == "__main__":
    unittest.main()
