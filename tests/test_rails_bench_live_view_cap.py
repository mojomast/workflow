"""P2 soak fix (Kyle 15:02 ET): the live Rails view answers at most 100 marks per
selector (the shared query's default limit), so a soak window may never plan more
marks than that. Each window holds one gap mark plus two probe marks per cycle
(connected + replay). A 4 h soak used to plan 240 cycles per window and failed at
cycle 49, when the browser expected 101 marks and the view returned 100.

These tests stub ``rizzstack_rails`` so they run without the four-checkout tuple.
"""
import collections
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
        spec = importlib.util.spec_from_file_location('bench_rails_live_view_cap', BENCH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop('rizzstack_rails', None)
        else:
            sys.modules['rizzstack_rails'] = saved


class LiveViewCapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load_bench()

    def per_window(self, duration):
        return collections.Counter(w for w, _ in self.b.schedule(duration))

    def test_live_view_limit_is_one_hundred_marks(self):
        self.assertEqual(self.b.LIVE_VIEW_LIMIT, 100)
        self.assertEqual(self.b.LIVE_CYCLES_MAX, 49)

    def test_four_hour_window_stays_inside_the_live_view(self):
        counts = self.per_window(14400)
        self.assertEqual(sorted(counts), list(range(6)))
        for window, cycles in counts.items():
            self.assertEqual(cycles, 49, window)
            self.assertLessEqual(1 + 2 * cycles, self.b.LIVE_VIEW_LIMIT)

    def test_short_soaks_keep_their_ten_second_spacing(self):
        self.assertEqual(set(self.per_window(1800).values()), {30})
        self.assertEqual(set(self.per_window(60).values()), {1})

    def test_capped_cycles_spread_over_the_whole_window(self):
        planned = [t for w, t in self.b.schedule(14400) if w == 5]
        self.assertEqual(planned[0], 5 * 2400)
        self.assertLess(planned[-1], 6 * 2400)
        self.assertGreater(planned[-1], 6 * 2400 - 60)


if __name__ == '__main__':
    unittest.main()
