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
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

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


class SurfaceTests(unittest.TestCase):
    """Exercise real check functions against a disposable local Git repo."""

    def setUp(self) -> None:
        self.mod = load_module()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.mod.WORKFLOW_REPO = self.mod.OD_REPO = self.mod.PLUGIN_DIR = self.repo
        self.mod.COLLECTOR_MAIN = self.mod.OBS_APP = "artifact"
        self.mod.OD_DEPLOY = self.root / "deploy"
        self.mod.OD_DEPLOY.mkdir()
        self.mod.COLLECTOR_DEPLOYED = self.mod.OD_DEPLOY / "artifact"

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def create_main(self, data: bytes) -> None:
        (self.repo / "artifact").write_bytes(data)
        self.git("-c", "core.autocrlf=false", "add", "artifact")
        self.git("-c", "user.name=test", "-c", "user.email=test@example.org",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def test_absent_on_both_sides_is_drift(self) -> None:
        for check in (self.mod.check_collector, self.mod.check_obs_app):
            with self.subTest(check=check.__name__):
                self.assertFalse(check()[2])

    def test_compare_git_blob_and_deployment_as_bytes(self) -> None:
        data = b"line\r\n"
        self.create_main(data)
        for deployed, matches in ((data, True), (b"line\n", False)):
            self.mod.COLLECTOR_DEPLOYED.write_bytes(deployed)
            for check in (self.mod.check_collector, self.mod.check_obs_app):
                with self.subTest(check=check.__name__, matches=matches):
                    self.assertEqual(check()[2], matches)

    def test_stopped_gateway_is_not_loaded(self) -> None:
        self.create_main(b"test")
        with patch.object(self.mod, "_gateway_pid", return_value=0):
            self.assertFalse(self.mod.check_gateway_loaded()[2])

    def test_restart_must_postdate_local_install_not_commit(self) -> None:
        self.create_main(b"test")
        # Model a checkout made well after the commit was authored and a later
        # switch of the plugin symlink back to that older checkout.
        link = self.root / "installed"
        link.symlink_to(self.repo, target_is_directory=True)
        self.mod.PLUGIN_DIR = link
        reflog = self.repo / ".git" / "logs" / "HEAD"
        base = int(reflog.stat().st_mtime)
        os.utime(reflog, (base + 200, base + 200))
        os.utime(link, (base + 300, base + 300), follow_symlinks=False)
        for start, matches in ((base + 100, False), (base + 250, False), (base + 400, True)):
            with self.subTest(start=start), patch.object(self.mod, "_gateway_start_epoch", return_value=start):
                self.assertEqual(self.mod.check_gateway_loaded()[2], matches)


if __name__ == "__main__":
    unittest.main()
