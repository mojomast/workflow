"""Approved tests (T4-NOIDX): the Rails bench harness gets three index arms for
P1 (workflow 27-rails-qualification-plan): default (a new ledger creates the
index itself since bundlebees #84), none (unindexed control: the throwaway
ledger's index is dropped before seeding) and migrated (dropped, seeded, then
installed with bundlebees scripts/rails_attempt_index.py).

These tests stub ``rizzstack_rails`` so they run without the four-checkout
tuple; the real seeding path stays covered by tests/test_rails_bench.py.
"""
import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1] / 'scripts' / 'bench_rails.py'
INDEX = 'rails_local_attempt_scan'


def load_bench():
    stub = types.ModuleType('rizzstack_rails')
    stub.RailsLedger = object
    stub.query = types.SimpleNamespace(MAX_BYTES=32 * 1024)
    saved = sys.modules.get('rizzstack_rails')
    sys.modules['rizzstack_rails'] = stub
    try:
        spec = importlib.util.spec_from_file_location('bench_rails_arms', BENCH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop('rizzstack_rails', None)
        else:
            sys.modules['rizzstack_rails'] = saved


def ledger_like(path, with_index=True):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE event_rows (event_id TEXT, ingest_seq INTEGER, rails_hash TEXT, envelope_json TEXT)')
        if with_index:
            db.execute(f"CREATE INDEX {INDEX} ON event_rows (json_extract(envelope_json,'$.scope.attempt_id'), ingest_seq)")


class TestRailsBenchIndexArms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load_bench()

    def parse(self, *argv):
        return self.b.build_parser().parse_args(['--output', 'report.json', *argv])

    def test_default_arm_is_the_ledger_default(self):
        self.assertEqual(self.b.index_mode(self.parse()), 'default')
        self.assertEqual(self.b.index_mode(self.parse('--attempt-index')), 'default')

    def test_no_attempt_index_selects_the_unindexed_control(self):
        self.assertEqual(self.b.index_mode(self.parse('--no-attempt-index')), 'none')

    def test_migrate_arm(self):
        self.assertEqual(self.b.index_mode(self.parse('--migrate-attempt-index')), 'migrated')

    def test_arms_are_mutually_exclusive(self):
        for pair in (['--no-attempt-index', '--attempt-index'], ['--no-attempt-index', '--migrate-attempt-index'],
                     ['--attempt-index', '--migrate-attempt-index']):
            with self.subTest(pair=pair), self.assertRaises(SystemExit):
                self.parse(*pair)

    def test_drop_index_removes_it_and_fails_closed_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'l.sqlite'
            ledger_like(path)
            self.assertTrue(self.b.has_attempt_index(path))
            self.b.drop_attempt_index(path)
            self.assertFalse(self.b.has_attempt_index(path))
            with self.assertRaises(ValueError):
                self.b.drop_attempt_index(path)

    def test_existing_soak_cap_unchanged_by_this_slice(self):
        with self.assertRaises(SystemExit):
            self.parse('--soak-seconds', '1801')


if __name__ == '__main__':
    unittest.main()
