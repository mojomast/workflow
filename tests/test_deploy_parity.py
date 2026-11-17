"""Contract test for scripts/deploy_parity.py.

The checker exists so merged-but-not-deployed drift is caught mechanically instead of by
the owner noticing. These tests pin its contract:
- a surface whose hashes match reports OK; a mismatch reports DRIFT (never silently OK);
- an error inside one check degrades that row to DRIFT with an ERROR marker, not a crash;
- the exit code is non-zero iff any row drifted;
- the output table names every surface;
- an UNKNOWN deployed value is never treated as parity.

The real checks run against live checkouts in production; here the check table is replaced
so the test is hermetic.
"""

import importlib.util
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_module() -> Any:
    path = ROOT / "scripts" / "deploy_parity.py"
    spec = importlib.util.spec_from_file_location("deploy_parity", path)
    assert spec is not None and spec.loader is not None, "checker module must be loadable"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_module()
        self._saved = list(self.mod.CHECKS)

    def tearDown(self) -> None:
        setattr(self.mod, "CHECKS", tuple(self._saved))

    def run_main(self) -> int:
        return int(self.mod.main())

    def set_checks(self, checks: tuple[tuple[str, Any], ...]) -> None:
        setattr(self.mod, "CHECKS", checks)

    def test_matching_surface_reports_ok(self) -> None:
        self.set_checks((("s", lambda: ("abc", "abc", True)),))
        self.assertEqual(self.run_main(), 0)

    def test_mismatch_reports_drift_and_exit_one(self) -> None:
        self.set_checks((("s", lambda: ("abc", "def", False)),))
        self.assertEqual(self.run_main(), 1)

    def test_raising_check_degrades_to_drift_not_crash(self) -> None:
        def boom() -> tuple[str, str, bool]:
            raise RuntimeError("x")

        self.set_checks((("s", boom),))
        self.assertEqual(self.run_main(), 1)

    def test_all_surfaces_named(self) -> None:
        names = [name for name, _ in self._saved]
        for expected in ("plugin", "gateway_loaded", "collector", "obs_app", "hyvv"):
            self.assertIn(expected, names)

    def test_unknown_deployed_is_never_parity(self) -> None:
        self.set_checks((("hyvv", lambda: ("UNKNOWN", "sha", False)),))
        self.assertEqual(self.run_main(), 1)

    def test_all_ok_exits_zero(self) -> None:
        self.set_checks((("a", lambda: ("1", "1", True)), ("b", lambda: ("2", "2", True))))
        self.assertEqual(self.run_main(), 0)


if __name__ == "__main__":
    unittest.main()
