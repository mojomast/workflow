"""Approved tests (T4-FIXHIST): the Rails bench harness gets the P2 soak controls from
workflow 27-rails-qualification-plan: a soak of up to 4 h (14,400 s) and a
``--fixed-history`` mode (Arm B) that saturates the live viewport to its 2,000-mark
renderer cap before t=0, so memory that still grows in that arm is a leak.

These tests stub ``rizzstack_rails`` so they run without the four-checkout tuple.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1] / 'scripts' / 'bench_rails.py'


def load_bench():
    stub = types.ModuleType('rizzstack_rails')
    stub.RailsLedger = object
    stub.query = types.SimpleNamespace(MAX_BYTES=32 * 1024)
    saved = sys.modules.get('rizzstack_rails')
    sys.modules['rizzstack_rails'] = stub
    try:
        spec = importlib.util.spec_from_file_location('bench_rails_fixed_history', BENCH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop('rizzstack_rails', None)
        else:
            sys.modules['rizzstack_rails'] = saved


class TestRailsBenchFixedHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load_bench()

    def parser(self):
        return self.b.build_parser()

    def parse(self, *argv):
        return self.parser().parse_args(['--output', 'report.json', *argv])

    def test_soak_accepts_up_to_four_hours(self):
        self.assertEqual(self.parse('--soak-seconds', '14400').soak_seconds, 14400)
        self.assertEqual(self.parse('--soak-seconds', '0').soak_seconds, 0)
        self.assertEqual(self.parse().soak_seconds, 1800)

    def test_soak_above_four_hours_is_refused(self):
        with self.assertRaises(SystemExit):
            self.parse('--soak-seconds', '14401')

    def test_fixed_history_flag(self):
        self.assertFalse(self.parse().fixed_history)
        self.assertTrue(self.parse('--fixed-history').fixed_history)

    def test_renderer_cap_is_two_thousand_marks(self):
        self.assertEqual(self.b.RENDERER_CAP, 2000)

    def test_seed_count_saturates_the_cap(self):
        seed = self.b.fixed_history_seed
        self.assertEqual(seed(0), 2000)
        self.assertEqual(seed(1500), 500)
        self.assertEqual(seed(2000), 0)
        self.assertEqual(seed(2500), 0)
        with self.assertRaises(ValueError):
            seed(-1)

    def test_fixed_history_needs_a_soak(self):
        p = self.parser()
        with self.assertRaises(SystemExit):
            self.b.check_fixed_history(p, p.parse_args(['--output', 'r.json', '--fixed-history', '--soak-seconds', '0']))
        self.assertIsNone(self.b.check_fixed_history(p, p.parse_args(['--output', 'r.json', '--fixed-history'])))
        self.assertIsNone(self.b.check_fixed_history(p, p.parse_args(['--output', 'r.json', '--soak-seconds', '0'])))

    def test_report_config_records_the_mode(self):
        source = BENCH.read_text(encoding='utf-8')
        self.assertIn('fixed_history=args.fixed_history', source)
        self.assertIn('check_fixed_history(p, args)', source)


if __name__ == '__main__':
    unittest.main()
