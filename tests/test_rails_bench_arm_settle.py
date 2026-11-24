"""Approved tests (T4-NOIDXFIX): the none/migrated P1 arms must really be unindexed /
migrated when reads start.

Found by the coordinator's P1 smoke on the four-checkout tuple (5k events): every
RailsLedger writer open runs ``CREATE INDEX IF NOT EXISTS rails_local_attempt_scan``,
so the index dropped before seeding is back after the ten producers open the ledger.
The none arm then reported ``index_present_after_seed: true`` and the migrated arm
failed ("index was not installed": the installer said "already installed").

The fix settles the arm *after* the producers join: drop the re-created index for
none/migrated, run the pinned installer for migrated, and fail closed through
``check_arm`` if the index state does not match the arm. These tests stub
``rizzstack_rails`` (no tuple needed); the real path is re-checked by the P1 smoke.
"""
import inspect
import tempfile
import unittest
from pathlib import Path

import importlib.util

_ARMS = Path(__file__).resolve().parent / 'test_rails_bench_index_arms.py'
_spec = importlib.util.spec_from_file_location('rails_bench_index_arms_helpers', _ARMS)
_arms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_arms)
ledger_like, load_bench = _arms.ledger_like, _arms.load_bench


class TestRailsBenchArmSettle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load_bench()

    def test_check_arm_accepts_matching_state(self):
        self.assertIsNone(self.b.check_arm('default', True))
        self.assertIsNone(self.b.check_arm('migrated', True))
        self.assertIsNone(self.b.check_arm('none', False))

    def test_check_arm_fails_closed_on_mismatch(self):
        for mode, present in (('none', True), ('default', False), ('migrated', False)):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.b.check_arm(mode, present)

    def test_check_arm_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            self.b.check_arm('bogus', True)

    def test_drop_recreated_index_before_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'l.sqlite'
            ledger_like(path)  # as after the producers re-created it
            self.b.unindex_after_seed(path)
            self.assertFalse(self.b.has_attempt_index(path))
            self.b.unindex_after_seed(path)  # idempotent when already absent
            self.assertFalse(self.b.has_attempt_index(path))

    def test_seed_settles_after_producers_and_checks_the_arm(self):
        src = inspect.getsource(self.b.seed)
        join = src.index('proc.join()')
        self.assertIn('unindex_after_seed(path)', src)
        self.assertGreater(src.index('unindex_after_seed(path)'), join)
        self.assertIn("check_arm(index_mode, stats['index_present_after_seed'])", src)
        self.assertGreater(src.index('check_arm('), src.index('unindex_after_seed(path)'))


if __name__ == '__main__':
    unittest.main()
