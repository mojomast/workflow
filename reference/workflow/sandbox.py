"""Optional bubblewrap sandbox for the reference demo's test runs.

Teaching code. When ``bwrap`` is installed and usable, approved tests run with
no network, a private /tmp, /home and /root hidden, and the rest of the host
read-only; only the checkout and the runner's scratch folder are writable.
When it is not available the caller runs without a sandbox and every record
says ``sandbox: none``. The demo never claims isolation it did not have.
bundlebees is the production implementation (bwrap or firejail, fail closed).
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import sys
from pathlib import Path

_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}


@functools.lru_cache(maxsize=1)
def detect_backend() -> str | None:
    """Return ``"bwrap"`` if a bubblewrap sandbox can start here, else ``None``."""
    exe = shutil.which("bwrap")
    if not exe:
        return None
    try:
        proc = subprocess.run([exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                               "--unshare-all", "--die-with-parent", "true"],
                              capture_output=True, env=_ENV, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return "bwrap" if proc.returncode == 0 else None


def wrap(argv: list[str], workdir: Path, scratch: Path) -> list[str]:
    """Wrap *argv* so it runs in bwrap with only *workdir* and *scratch* writable."""
    exe = shutil.which("bwrap") or "bwrap"
    out = [exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
           "--tmpfs", "/tmp", "--tmpfs", "/home", "--tmpfs", "/root"]
    # The interpreter may live under /home (a venv); keep it readable.
    for prefix in sorted({sys.prefix, sys.base_prefix, str(Path(sys.executable).resolve().parent)}):
        out += ["--ro-bind-try", prefix, prefix]
    for path in (scratch, workdir):
        out += ["--bind", str(path), str(path)]
    out += ["--unshare-all", "--die-with-parent", "--new-session", "--chdir", str(workdir), "--", *argv]
    return out
