"""Arm B fills every live selector to the shared view cap before its probes.

These tests stub ``rizzstack_rails`` so they run without the four-checkout tuple.
"""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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

    def test_seed_count_fills_the_live_view_after_gap_and_probes(self):
        for cycles in (0, 1, 30, self.b.LIVE_CYCLES_MAX):
            with self.subTest(cycles=cycles):
                seeded = self.b.fixed_history_seed(cycles)
                self.assertEqual(seeded, self.b.LIVE_VIEW_LIMIT - 1 - 2 * cycles)
                self.assertEqual(seeded + 1 + 2 * cycles, self.b.LIVE_VIEW_LIMIT)

    def test_seed_count_refuses_impossible_cycle_counts(self):
        for cycles in (-1, self.b.LIVE_CYCLES_MAX + 1):
            with self.subTest(cycles=cycles), self.assertRaises(ValueError):
                self.b.fixed_history_seed(cycles)

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


class FakeSoak:
    def __init__(self, bench):
        self.b = bench
        self.reader = mock.Mock(pid=1201)
        self.js = mock.Mock(pid=1202)
        self.js.wait.return_value = 0
        self.writer = mock.Mock()
        self.writer.append.side_effect = self.append
        self.appended = []
        self.commands = []
        self.selected = []
        self.replies = []
        self.browser_started = False

    @staticmethod
    def number(candidate):
        return int(candidate['source']['record_id'].rsplit('-', 1)[1])

    def append(self, **candidate):
        event_id = f'event-{len(self.appended)}'
        self.appended.append((candidate, event_id))
        return {'event_id': event_id, 'duplicated': False}

    def send(self, proc, data):
        if proc is not self.js:
            return
        self.commands.append(data)
        if not isinstance(data, dict):
            return
        if data.get('op') == 'select':
            self.selected = data.get('seeded', [])
            self.replies.append('armed')
        elif data.get('op') in ('connected', 'replay'):
            self.replies.extend(['armed', 'http', 'visible', 'ack'])

    def get_message(self, proc, timeout=30):
        if proc is self.reader:
            return 3210
        if not self.browser_started:
            self.browser_started = True
            return {'fixture': 'ok'}
        reply = self.replies.pop(0)
        if reply != 'ack':
            return reply
        candidate, event_id = self.appended[-1]
        selector = candidate['scope']['job_id']
        n = sum(1 for item, _ in self.appended
                if item['scope']['job_id'] == selector and self.number(item) < self.b.FIXED_HISTORY_INDEX_BASE)
        return {'id': event_id, 'count': len(self.selected) + n, 'chromium_pss_kib': 1}

    def run(self, fixed_history):
        args = SimpleNamespace(fixed_history=fixed_history, node_modules=Path('modules'), chromium=Path('chrome'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.sqlite'
            with (mock.patch.object(self.b.subprocess, 'Popen', side_effect=[self.reader, self.js]),
                  mock.patch.object(self.b, 'RailsLedger', return_value=self.writer),
                  mock.patch.object(self.b, 'get_message', side_effect=self.get_message),
                  mock.patch.object(self.b, 'send', side_effect=self.send),
                  mock.patch.object(self.b, 'stop'),
                  mock.patch.object(self.b, 'rss', return_value={'VmRSS': 1, 'VmHWM': 1}),
                  mock.patch.object(self.b, 'schedule', return_value=[(0, 0.0), (1, 0.0)]),
                  mock.patch.object(self.b.time, 'sleep')):
                return self.b.soak(path, 0, {}, args, lambda _: None)

    def entries(self, window):
        selector = f'live-{window}'
        return [(candidate, event_id) for candidate, event_id in self.appended
                if candidate['scope']['job_id'] == selector]

    def select(self, window):
        return next(command for command in self.commands if isinstance(command, dict)
                    and command.get('op') == 'select' and command.get('window') == window)


class FixedHistorySoakTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load_bench()

    def setUp(self):
        self.fixture = FakeSoak(self.b)

    def test_each_window_is_filled_to_the_live_view_cap_before_its_gap(self):
        report = self.fixture.run(True)
        expected_seeds = self.b.LIVE_VIEW_LIMIT - 1 - 2
        self.assertEqual(report['fixed_history_seeded'], expected_seeds)
        for window in range(2):
            with self.subTest(window=window):
                entries = self.fixture.entries(window)
                seeds = [entry for entry in entries if self.fixture.number(entry[0]) >= self.b.FIXED_HISTORY_INDEX_BASE]
                gaps = [entry for entry in entries if entry[0]['kind'] == 'source.gap']
                probes = [entry for entry in entries if entry not in seeds and entry not in gaps]
                self.assertEqual(len(seeds), expected_seeds)
                self.assertEqual(len(gaps), 1)
                self.assertEqual(len(probes), 2)
                self.assertEqual(len(entries), self.b.LIVE_VIEW_LIMIT)
                self.assertEqual(entries[:expected_seeds], seeds)
                self.assertEqual(entries[expected_seeds], gaps[0])

    def test_select_sends_the_seeded_ids_before_the_gap_id(self):
        self.fixture.run(True)
        for window in range(2):
            with self.subTest(window=window):
                entries = self.fixture.entries(window)
                seeds = [event_id for candidate, event_id in entries
                         if self.fixture.number(candidate) >= self.b.FIXED_HISTORY_INDEX_BASE]
                gap = next(event_id for candidate, event_id in entries if candidate['kind'] == 'source.gap')
                command = self.fixture.select(window)
                self.assertEqual(command.get('seeded'), seeds)
                self.assertEqual(command['id'], gap)

    def test_arm_a_sends_an_empty_seed_list(self):
        self.fixture.run(False)
        for window in range(2):
            with self.subTest(window=window):
                self.assertEqual(len(self.fixture.entries(window)), 3)
                self.assertEqual(self.fixture.select(window).get('seeded'), [])

    def test_browser_expects_seeded_ids_then_the_gap(self):
        source = BENCH.with_suffix('.mjs').read_text(encoding='utf-8')
        self.assertIn('expected=[...cmd.seeded,cmd.id]', source)


if __name__ == '__main__':
    unittest.main()
