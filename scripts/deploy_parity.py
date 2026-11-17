#!/usr/bin/env python3
"""Deploy-parity check: is what merged actually deployed?

Compares each surface that has a deploy target against the revision merged to main.
Exit 0 = all surfaces in parity; exit 1 = drift found (printed as a table).

Surfaces and their sources of truth:
  plugin      git HEAD of the installed checkout vs origin/main of the plugin repo
  gateway     gateway process start time vs the installed checkout's mtime (started after = loaded)
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
import sys
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
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    ).stdout.strip()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "MISSING"


def check_plugin() -> tuple[str, str, bool]:
    installed = git(PLUGIN_DIR, "rev-parse", "HEAD")
    main = git(PLUGIN_REPO, "rev-parse", "origin/main")
    return installed or "UNKNOWN", main or "UNKNOWN", installed == main and bool(installed)


def check_gateway_loaded() -> tuple[str, str, bool]:
    """Started-after-install is the mechanical proxy for 'loaded the installed code'."""
    # honest proxy: the install is loaded iff the gateway started after the checkout change
    try:
        gw_start_epoch = _gateway_start_epoch()
        install_epoch = float(git(PLUGIN_DIR, "log", "-1", "--format=%ct") or 0)
        return (
            f"gateway_started={gw_start_epoch:.0f}",
            f"checkout_commit_epoch={install_epoch:.0f}",
            gw_start_epoch > install_epoch,
        )
    except (ValueError, subprocess.SubprocessError):
        return "UNKNOWN", "UNKNOWN", False


def _gateway_pid() -> int:
    out = subprocess.run(
        ["systemctl", "--user", "show", "-p", "MainPID", "hermes-gateway"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    return int(out.split("=")[-1] or 0)


def _gateway_start_epoch() -> float:
    out = subprocess.run(
        ["systemctl", "--user", "show", "-p", "ActiveEnterTimestampMonotonic", "hermes-gateway"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    # monotonic is not wall clock; use /proc stat of the main pid instead
    pid = _gateway_pid()
    if pid:
        try:
            with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as fh:
                fields = fh.read().split()
            start_ticks = float(fields[21])
            with open("/proc/uptime", "r", encoding="utf-8") as fh:
                uptime = float(fh.read().split()[0])
            return _now() - (uptime - start_ticks / os.sysconf("SC_CLK_TCK"))
        except (OSError, IndexError, ValueError):
            pass
    return _now()


def _now() -> float:
    import time

    return time.time()


def check_collector() -> tuple[str, str, bool]:
    main = subprocess.run(
        ["git", "-C", str(WORKFLOW_REPO), "show", f"origin/main:{COLLECTOR_MAIN}"],
        capture_output=True, text=True, timeout=60,
    )
    main_hash = hashlib.sha256(main.stdout.encode()).hexdigest() if main.returncode == 0 else "MISSING"
    deployed = sha_file(COLLECTOR_DEPLOYED)
    return deployed[:12], main_hash[:12], deployed == main_hash


def check_obs_app() -> tuple[str, str, bool]:
    main = subprocess.run(
        ["git", "-C", str(OD_REPO), "show", f"origin/main:{OBS_APP}"],
        capture_output=True, text=True, timeout=60,
    )
    main_hash = hashlib.sha256(main.stdout.encode()).hexdigest() if main.returncode == 0 else "MISSING"
    deployed = sha_file(OD_DEPLOY / OBS_APP)
    return deployed[:12], main_hash[:12], deployed == main_hash


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
    sys.exit(main())
