#!/usr/bin/env python3
"""Deploy-parity check: is what merged actually deployed?

Compares each surface that has a deploy target against the revision merged to main.
Exit 0 = all surfaces in parity; exit 1 = drift found (printed as a table).

Surfaces and their sources of truth:
  plugin      git HEAD of the installed checkout vs origin/main of the plugin repo
  gateway     process start vs local HEAD reflog / install symlink mtime (restart proxy only)
  collector   sha256 of the running collector file vs `git show origin/main:<path>` of the workflow repo
  obs_app     sha256 of the deployed app.js vs the same file at orbitdesktop origin/main
  hyvv        reported DEPLOYED_SHA (env or deploy marker file) vs origin/main of the hyvv repo

The hyvv surface needs a recorded deployed sha; set DEPLOY_PARITY_HYVV_SHA or write the sha
that apply-update reported into <state>/hyvv-deployed-sha. Without it the row reports UNKNOWN
(never assumed in parity).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

PLUGIN_DIR = Path.home() / ".hermes" / "plugins" / "bundlebees"
PLUGIN_REPO = Path.home() / "rizzstack" / "bundlebees"
WORKFLOW_REPO = Path.home() / "rizzstack" / "workflow-closeout"
OD_REPO = Path.home() / "rizzstack" / "orbitdesktop"
OD_DEPLOY = Path.home() / "orbitdesktop-deploy"
COLLECTOR_DEPLOYED = Path.home() / ".local" / "share" / "rizzstack-obs" / "collector.py"
COLLECTOR_MAIN = "contrib/rizzstack-observability/collector.py"
OBS_APP = "apps/rizzstack-observatory/app.js"
STATE = Path.home() / ".hermes" / "plugin-data" / "bundlebees"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def check_plugin() -> tuple[str, str, bool]:
    installed = git(PLUGIN_DIR, "rev-parse", "HEAD")
    main = git(PLUGIN_REPO, "rev-parse", "origin/main")
    return installed or "UNKNOWN", main or "UNKNOWN", installed == main and bool(installed)


def check_gateway_loaded() -> tuple[str, str, bool]:
    """Started-after-install is the mechanical proxy for 'loaded the installed code'."""
    try:
        gw_start_epoch = _gateway_start_epoch()
        # A commit can be months older than its installation. Git's local HEAD
        # log follows checkouts and fast-forwards, including in linked worktrees.
        log = git(PLUGIN_DIR, "rev-parse", "--path-format=absolute", "--git-path", "logs/HEAD")
        if not log or not Path(log).is_file():
            return "UNKNOWN", "UNKNOWN", False
        install_epoch = Path(log).stat().st_mtime
        if PLUGIN_DIR.is_symlink():
            install_epoch = max(install_epoch, PLUGIN_DIR.lstat().st_mtime)
        return (
            f"gateway_started={gw_start_epoch:.0f}",
            f"checkout_updated={install_epoch:.0f}",
            gw_start_epoch > install_epoch,
        )
    except (ValueError, IndexError, OSError, subprocess.SubprocessError):
        return "UNKNOWN", "UNKNOWN", False


def _gateway_pid() -> int:
    out = subprocess.run(
        ["systemctl", "--user", "show", "-p", "MainPID", "hermes-gateway"],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout.strip()
    return int(out.split("=")[-1] or 0)


def _gateway_start_epoch() -> float:
    pid = _gateway_pid()
    if pid <= 0:
        raise ValueError("gateway has no main process")
    # Field 2 (the parenthesized process name) may itself contain spaces or ')'.
    stat = Path(f"/proc/{pid}/stat").read_text()
    start_ticks = int(stat.rsplit(")", 1)[1].split()[19])  # field 22
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    return time.time() - (uptime - start_ticks / os.sysconf("SC_CLK_TCK"))


def _file_parity(repo: Path, path: str, deployed: Path) -> tuple[str, str, bool]:
    main = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", f"origin/main:{path}"],
        capture_output=True, timeout=60,
    )
    expected = hashlib.sha256(main.stdout).hexdigest() if main.returncode == 0 else None
    actual = hashlib.sha256(deployed.read_bytes()).hexdigest() if deployed.is_file() else None
    return (actual or "MISSING")[:12], (expected or "MISSING")[:12], actual is not None and actual == expected


def check_collector() -> tuple[str, str, bool]:
    return _file_parity(WORKFLOW_REPO, COLLECTOR_MAIN, COLLECTOR_DEPLOYED)


def check_obs_app() -> tuple[str, str, bool]:
    return _file_parity(OD_REPO, OBS_APP, OD_DEPLOY / OBS_APP)


def check_hyvv() -> tuple[str, str, bool]:
    main = git(Path.home() / "rizzstack" / "hyvv", "rev-parse", "origin/main")
    deployed = os.environ.get("DEPLOY_PARITY_HYVV_SHA", "").strip()
    marker = STATE / "hyvv-deployed-sha"
    if not deployed and marker.exists():
        deployed = marker.read_text(encoding="utf-8").strip()
    if not deployed:
        return "UNKNOWN", main or "UNKNOWN", False
    return deployed, main or "UNKNOWN", deployed == main


CHECKS = (
    ("plugin", check_plugin),
    ("gateway_loaded", check_gateway_loaded),
    ("collector", check_collector),
    ("obs_app", check_obs_app),
    ("hyvv", check_hyvv),
)


def main() -> int:
    rows = []
    drift = False
    for name, fn in CHECKS:
        try:
            left, right, ok = fn()
        except Exception as exc:  # a check must never pretend parity
            left, right, ok = f"ERROR:{type(exc).__name__}", "?", False
        rows.append((name, left, right, "OK" if ok else "DRIFT"))
        drift = drift or not ok
    width = max(len(n) for n, *_ in rows)
    print(f"{'surface'.ljust(width)}  {'deployed'.ljust(24)}  {'merged'.ljust(24)}  verdict")
    for name, left, right, verdict in rows:
        print(f"{name.ljust(width)}  {left.ljust(24)}  {right.ljust(24)}  {verdict}")
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
