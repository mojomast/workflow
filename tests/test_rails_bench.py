"""Fail closed on plausible-looking aggregate benchmark results."""
import importlib.util
from pathlib import Path
import unittest


BENCH = Path(__file__).resolve().parents[1] / 'scripts' / 'bench_rails.py'


class RailsBenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BENCH.parents[2] / 'bundlebees/contrib/rizzstack_rails').exists():
            raise unittest.SkipTest('requires the offline four-checkout benchmark tuple')
        spec = importlib.util.spec_from_file_location('bench_rails', BENCH)
        cls.b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.b)

    def test_exact_ids_reject_duplicate_omission_and_wrong_origin(self):
        for actual in [['a:1', 'a:1'], ['a:1'], ['a:1', 'b:2']]:
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                self.b.check_ids(actual, ['a:1', 'a:2'])

    def test_six_fixed_windows_not_six_successes(self):
        slots = list(self.b.schedule(1800))
        self.assertEqual(len(slots), 180)
        self.assertEqual(slots[30], (1, 300.0))
        self.assertEqual(slots[-1], (5, 1790.0))
        self.assertEqual(list(self.b.schedule(60)), [(i, i * 10.) for i in range(6)])
