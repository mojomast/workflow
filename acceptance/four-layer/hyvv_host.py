#!/usr/bin/env python3
"""Boot the real hyvv runtime (launcher.py from a hyvv checkout) on loopback for the component run.

The worker backend is hyvv's own scripted FakeBackend, extended with ``patch()``
so the launcher's real ``_manifest`` writes a result with a diff. This is a
SCRIPTED worker: results produced here are component evidence only and can never
satisfy a final-scenario step (see README). No sandboxes, no model calls, no keys.

usage: hyvv_host.py HYVV_SRC DATA_DIR PATCH_DIR
Prints one JSON line {"url": ..., "token_file": ..., "version": ...}; the token is never printed.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path


def main() -> int:
    src, data, patches = (Path(p).resolve() for p in sys.argv[1:4])
    spec = importlib.util.spec_from_file_location("hyvv_launcher_acceptance", src / "launcher.py")
    L = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(L)
    data.mkdir(parents=True, exist_ok=True)
    for name in ("go.key", "deepseek.key"):  # the launcher insists these exist; never real keys here
        (data / name).write_text("fake-key-not-real", encoding="utf-8")

    class ScriptedBackend(L.FakeBackend):
        """FakeBackend + a scripted diff chosen by the brief objective tag, e.g. "[A1] ..."."""

        async def start(self, a, key):
            # The real backend seeds the project at brief.source_rev and records it as local_base_rev.
            a["local_base_rev"] = a["brief"].get("source_rev")
            return await super().start(a, key)

        async def environment(self, a):
            return {"backend": "scripted"}

        async def patch(self, a):
            m = re.match(r"\[([A-Za-z0-9_-]+)\]", str(a["brief"].get("objective") or ""))
            f = patches / f"{m.group(1)}.patch" if m else None
            if not f or not f.exists():
                return None
            diff = f.read_text(encoding="utf-8")
            files = [{"path": p, "change": "changed"} for p in re.findall(r"^\+\+\+ b/(\S+)", diff, re.M)]
            return {"diff": diff, "files": files}

    cfg = {"bind": "127.0.0.1", "port": 0, "max_concurrent": 4, "data_dir": str(data), "backoff_s": [0.2],
           "model": "deepseek-v4.1-flash", "base_url": "http://fake.invalid", "wire": "openai",
           "image": "cua-bee:acceptance", "runtime": "runc", "memory_mb": 1024,
           "projects": {"toy-shop": {}}}
    launcher = L.Launcher(cfg, ScriptedBackend(cfg))
    threading.Thread(target=launcher.loop.run_forever, daemon=True).start()
    token = secrets.token_hex(32)
    token_file = data / "launcher.token"
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(token)
    server = ThreadingHTTPServer(("127.0.0.1", 0), L.make_handler(launcher, token))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}", "token_file": str(token_file),
                      "version": getattr(L, "VERSION", None)}), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
