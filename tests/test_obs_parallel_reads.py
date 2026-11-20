"""The collector's read-only CLI reads run concurrently without changing the snapshot.

A cold /snapshot on moltussy-1 took ~10.5 s (Nov 20 2026 profile): 99% of it was nine
sequential subprocess reads -- the two ``hermes bundlebees`` fleet reads (~3.1 s each) and
one ``gh pr list`` per repo (~0.4-0.7 s each). They are independent, so they now overlap.
These tests pin that (a) the snapshot is byte-identical to the sequential build, (b) the
wall time is bounded by the slowest read rather than their sum, (c) ``cli_workers=1``
restores strictly sequential reads, and (d) fleet failure semantics are unchanged.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests import test_obs_bottlenecks as tb

collector = tb.collector
REPOS = ["mojomast/workflow", "mojomast/bundlebees", "mojomast/hyvv", "mojomast/orbitdesktop"]
DELAY = 0.25


class Recorder:
    def __init__(self, delay: float = DELAY) -> None:
        self.delay = delay
        self.lock = threading.Lock()
        self.live = 0
        self.peak = 0
        self.calls: list[tuple[str, ...]] = []

    def wrap(self, inner):
        def run(argv):
            with self.lock:
                self.calls.append(tuple(argv))
                self.live += 1
                self.peak = max(self.peak, self.live)
            try:
                time.sleep(self.delay)
                return inner(argv)
            finally:
                with self.lock:
                    self.live -= 1
        return run


def build(tmp: Path, rec: Recorder, **overrides):
    c = tb.bottleneck_collector(
        tmp,
        repos=REPOS,
        fleet_runner=rec.wrap(tb.fleet_runner),
        gh_runner=rec.wrap(tb.gh_runner),
        **overrides,
    )
    t0 = time.perf_counter()
    snap = c.build_snapshot()
    return snap, time.perf_counter() - t0


class ParallelReadsTests(unittest.TestCase):
    def test_snapshot_identical_to_sequential_build(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            seq, _ = build(Path(a), Recorder(0.0), cli_workers=1)
            par, _ = build(Path(b), Recorder(0.0))
        self.assertEqual(json.dumps(seq, sort_keys=True), json.dumps(par, sort_keys=True))
        self.assertEqual([r["repo"] for r in par["ci"]["repos"]], REPOS)
        self.assertEqual(par["fleet"]["status"], "live")

    def test_wall_time_is_bounded_by_the_slowest_read(self) -> None:
        rec = Recorder()
        with tempfile.TemporaryDirectory() as tmp:
            snap, elapsed = build(Path(tmp), rec)
        reads = len(rec.calls)
        self.assertGreaterEqual(reads, 6)  # 2 fleet + 4 gh pr list
        self.assertGreater(rec.peak, 1)
        # Sequential would be reads * DELAY (>= 1.5 s); overlapped it is ~2 * DELAY.
        self.assertLess(elapsed, (reads * DELAY) / 2)
        self.assertEqual(snap["ci"]["status"], "live")

    def test_one_worker_is_strictly_sequential(self) -> None:
        rec = Recorder(0.02)
        with tempfile.TemporaryDirectory() as tmp:
            build(Path(tmp), rec, cli_workers=1)
        self.assertEqual(rec.peak, 1)

    def test_fleet_failure_semantics_unchanged(self) -> None:
        def attempts_fail(argv):
            if "attempts" in argv:
                return 124, "", ""
            return tb.fleet_runner(argv)

        for workers in (1, 8):
            with self.subTest(workers=workers), tempfile.TemporaryDirectory() as tmp:
                c = tb.bottleneck_collector(
                    Path(tmp), repos=REPOS, fleet_runner=attempts_fail, cli_workers=workers
                )
                fleet = c.build_snapshot()["fleet"]
                self.assertNotEqual(fleet["status"], "live")
                self.assertIsNone(fleet["bee_cap"])

    def test_gh_failure_for_one_repo_degrades_only_that_row(self) -> None:
        def gh(argv):
            if "--repo" in argv and argv[argv.index("--repo") + 1] == "mojomast/hyvv":
                return 1, "", ""
            return tb.gh_runner(argv)

        with tempfile.TemporaryDirectory() as tmp:
            c = tb.bottleneck_collector(Path(tmp), repos=REPOS, gh_runner=gh)
            ci = c.build_snapshot()["ci"]
        states = {r["repo"]: r["ci_state"] for r in ci["repos"]}
        self.assertEqual(states["mojomast/hyvv"], "unavailable")
        self.assertEqual(ci["status"], "live")
        self.assertEqual([r["repo"] for r in ci["repos"]], REPOS)

    def test_cli_flag_wires_workers(self) -> None:
        args = collector.build_parser().parse_args(["--cli-workers", "1"])
        self.assertEqual(args.cli_workers, 1)
        self.assertEqual(collector.build_parser().parse_args([]).cli_workers, 8)


if __name__ == "__main__":
    unittest.main()
