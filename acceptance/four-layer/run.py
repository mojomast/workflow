#!/usr/bin/env python3
"""rizzstack four-layer acceptance runner (workflow + hyvv + bundlebees + Orbit).

Builds the pinned merge candidates from matrix.json (local merges only, never
pushed), then walks the mission's 14 acceptance steps. Every step gets two
verdicts:

* component  real code from all four repos on loopback, but the worker is
             hyvv's scripted backend (no model). Evidence of wiring only.
* final      the acceptance verdict. Only a run with real-agent workers
             (--real-agents) can pass a worker-dependent step; a scripted
             worker result is never accepted as final evidence.

Statuses are passed | failed | unrun | blocked, each with a reason. A step
whose capability is not shipped in the pinned revisions is blocked, never
passed. Nothing here merges, pushes, tags, deploys or touches a live Orbit.

usage: run.py --out DIR [--matrix matrix.json] [--src repo=PATH ...] [--real-agents]
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STATUSES = ("passed", "failed", "unrun", "blocked")
GIT_ID = {"GIT_AUTHOR_NAME": "four-layer acceptance", "GIT_AUTHOR_EMAIL": "acceptance@example.invalid",
          "GIT_COMMITTER_NAME": "four-layer acceptance", "GIT_COMMITTER_EMAIL": "acceptance@example.invalid"}
LEAK_MARKERS = ("/home/", "/workspace/", "/tmp/", "C:\\Users", "launcher.token", "collab-board.key")
SCRIPTED = "scripted worker (hyvv FakeBackend + diff): component evidence only, never final"


def git(cwd: Path, *args: str, check: bool = True) -> str:
    env = {**os.environ, **GIT_ID}
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()[-400:]}")
    return p.stdout.strip()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
class Report:
    def __init__(self, out: Path, matrix: dict) -> None:
        self.out = out
        self.matrix = matrix
        self.revisions: dict[str, Any] = {}
        self.steps: dict[int, dict] = {s["n"]: {**s, "component": None, "final": None} for s in matrix["steps"]}
        self.findings: list[dict] = []
        self.started = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    def set(self, n: int, which: str, status: str, reason: str, **evidence: Any) -> None:
        assert status in STATUSES, status
        self.steps[n][which] = {"status": status, "reason": reason, **({"evidence": evidence} if evidence else {})}

    def finding(self, fid: str, text: str, severity: str) -> None:
        self.findings.append({"id": fid, "severity": severity, "text": text})

    def write(self) -> dict:
        for s in self.steps.values():
            for which in ("component", "final"):
                if s[which] is None:
                    s[which] = {"status": "unrun", "reason": "not reached in this run"}
        doc = {"report_version": "rizzstack.four-layer-report/1", "started": self.started,
               "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "revisions": self.revisions,
               "steps": [self.steps[k] for k in sorted(self.steps)], "findings": self.findings,
               "final_accepted": all(self.steps[k]["final"]["status"] == "passed" for k in self.steps)}
        (self.out / "four-layer-report.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        lines = ["# Four-layer acceptance report", "", f"Run {doc['started']} to {doc['finished']}.",
                 f"**Final acceptance: {'ACCEPTED' if doc['final_accepted'] else 'NOT ACCEPTED'}**", "", "## Revisions", ""]
        for name, r in self.revisions.items():
            lines.append(f"- {name}: `{r.get('head')}` ({r.get('built')}) {r.get('note', '')}".rstrip())
        lines += ["", "## Steps", "", "| # | Step | Component (real code, scripted worker) | Final |", "|---|---|---|---|"]
        for k in sorted(self.steps):
            s = self.steps[k]
            c, f = s["component"], s["final"]
            lines.append(f"| {k} | {s['title']} | **{c['status']}**: {c['reason']} | **{f['status']}**: {f['reason']} |")
        if self.findings:
            lines += ["", "## Findings raised by this run", ""]
            lines += [f"- **{x['id']}** ({x['severity']}): {x['text']}" for x in self.findings]
        (self.out / "four-layer-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return doc


# ---------------------------------------------------------------------------
# Building the merge candidates
# ---------------------------------------------------------------------------
def build_repo(name: str, spec: dict, root: Path, override: str | None) -> dict:
    dest = root / name
    if override:
        src = Path(override).resolve()
        info = {"head": git(src, "rev-parse", "HEAD"), "built": "local override (as checked out)", "path": str(src)}
        if name == "bundlebees" and src.name != "bundlebees":
            raise RuntimeError("the bundlebees checkout directory must be named 'bundlebees'")
        return info
    if not dest.exists():
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", spec["url"], str(dest)], check=True)
    git(dest, "fetch", "-q", "origin", "+refs/pull/*/head:refs/remotes/pr/*")
    base = spec["base"]
    git(dest, "checkout", "-q", "--detach", base if len(base) >= 7 and base != "main" else f"origin/{base}")
    built, conflicts = [f"base {git(dest, 'rev-parse', '--short', 'HEAD')}"], []
    for m in spec.get("merges", []):
        p = subprocess.run(["git", "merge", "--no-edit", "-q", m], cwd=dest, capture_output=True, text=True, env={**os.environ, **GIT_ID})
        if p.returncode != 0:
            files = git(dest, "diff", "--name-only", "--diff-filter=U", check=False).split()
            git(dest, "merge", "--abort", check=False)
            conflicts.append({"merge": m, "files": files})
            built.append(f"merge {m[:7]} CONFLICT {files}")
            if not spec.get("fallback_without_merges"):
                break
        else:
            built.append(f"merge {m[:7]} ok")
    return {"head": git(dest, "rev-parse", "HEAD"), "built": "; ".join(built), "conflicts": conflicts, "path": str(dest)}


# ---------------------------------------------------------------------------
# Toy project and plugin host
# ---------------------------------------------------------------------------
PRICING = '"""Prices in integer cents."""\n\n\ndef apply_discount(cents: int, percent: int) -> int:\n    return cents - cents * percent // 100\n'
PRICING_TEST = "from shop.pricing import apply_discount\n\n\ndef test_discount():\n    assert apply_discount(1000, 10) == 900\n"
# Imports inside the tests so RED is a behavioral failure (missing apply_tax), not a collection error.
TAX_TEST = ("import pytest\n\nimport shop.pricing as pricing\n\n\ndef test_apply_tax_adds_the_rate():\n    assert pricing.apply_tax(1000, 10) == 1100\n\n\n"
            "def test_apply_tax_rejects_a_negative_rate():\n    with pytest.raises(ValueError):\n        pricing.apply_tax(100, -1)\n")
TAX_IMPL = ("\n\ndef apply_tax(cents: int, rate_percent: int) -> int:\n    if rate_percent < 0:\n        raise ValueError(\"rate_percent must not be negative\")\n"
            "    return cents * (100 + rate_percent) // 100\n")
LABELS = "LABEL = 'price'\n"


def make_project(root: Path) -> tuple[Path, str, dict[str, str]]:
    repo = root / "shop"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for rel, text in (("shop/__init__.py", ""), ("shop/pricing.py", PRICING), ("shop/labels.py", LABELS),
                      ("tests/__init__.py", ""), ("tests/test_pricing.py", PRICING_TEST), ("conftest.py", "")):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "baseline")
    (repo / "tests/test_tax.py").write_text(TAX_TEST, encoding="utf-8")
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "approved tests (RED, tests only)")
    red_rev = git(repo, "rev-parse", "HEAD")
    remote = root / "shop.git"
    git(root, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "branch", "wave/four-layer"); git(repo, "push", "-q", "-u", "origin", "wave/four-layer")
    patches = {}
    (repo / "shop/pricing.py").write_text(PRICING + TAX_IMPL, encoding="utf-8")
    patches["A1"] = git(repo, "diff") + "\n"
    (repo / "shop/labels.py").write_text(LABELS + "OUT_OF_SCOPE = True\n", encoding="utf-8")
    patches["A2"] = git(repo, "diff") + "\n"  # in-scope change plus an edit outside the lease
    git(repo, "checkout", "-q", "--", ".")
    return repo, red_rev, patches


def contract(red_rev: str) -> dict:
    t = "tests/test_tax.py::"
    return {
        "contract_version": "acdd/1", "id": "FL-apply-tax", "title": "apply_tax (four-layer acceptance)",
        "outcome": {"summary": "Callers can add a tax rate to a price in cents.", "observable_behavior": ["apply_tax(1000, 10) == 1100"]},
        "interfaces": [{"name": "apply_tax", "kind": "function", "change": "add"}],
        "acceptance_criteria": [
            {"id": "AC-001", "given": "1000 cents", "when": "apply_tax(1000, 10)", "then": "1100", "verification": "test", "tests": [t + "test_apply_tax_adds_the_rate"]},
            {"id": "AC-002", "given": "a negative rate", "when": "apply_tax(100, -1)", "then": "ValueError", "verification": "test", "tests": [t + "test_apply_tax_rejects_a_negative_rate"]},
            {"id": "AC-003", "statement": "the combined branch passes the full suite", "verification": "integration"},
            {"id": "AC-004", "statement": "a reviewer read the change", "verification": "review"},
        ],
        "scope": {"assigned_files": ["shop/pricing.py"], "test_files": ["tests/test_tax.py"], "prohibited": ["shop/labels.py"]},
        "source_rev": red_rev, "tdd": {"applicable": True, "test_first": True},
        "verification": {"independent": True, "integration": True},
        "evidence_required": ["red", "green", "refactor", "integration", "review"],
        "authorization": {"human_gates": ["merge", "tag", "release", "deploy", "publish"]},
    }


class Host:
    """The PluginContext surface bundlebees uses in Hermes (documented injection seams only)."""

    def __init__(self, state: Path, client: Any | None) -> None:
        self.tools: dict[str, Any] = {}
        self.cli_commands: dict[str, Any] = {}
        self.bundlebees_state_dir = state
        if client is not None:
            self.bundlebees_client = client

    def register_tool(self, name, toolset, schema, handler, description="", emoji="", **_):
        self.tools[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli_commands[name] = (setup_fn, handler_fn)

    def register_hook(self, *a, **k): pass
    def register_skill(self, *a, **k): pass
    def get_config(self, key, default=None): return default

    def cli(self, argv: list[str]) -> tuple[int, str]:
        import argparse as ap
        setup, handler = self.cli_commands["bundlebees"]
        parser = ap.ArgumentParser(prog="hermes bundlebees")
        setup(parser)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                rc = handler(parser.parse_args(argv))
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 2
        return int(rc or 0), buf.getvalue()

    def has_flag(self, argv: list[str], flag: str) -> bool:
        rc, text = self.cli([*argv, "--help"])
        return flag in text


def load_bundlebees(clone: Path):
    sys.path[:0] = [str(clone.parent), str(clone)]
    for mod in [m for m in sys.modules if m == "bundlebees" or m.startswith("bundlebees_plugin")]:
        sys.modules.pop(mod)
    return importlib.import_module("bundlebees")


def http_json(url: str, body: dict | None, key: str, method: str = "POST") -> tuple[int, Any, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw or "{}"), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}"), raw
        except ValueError:
            return e.code, {}, raw


def start_line(cmd: list[str], env: dict, log: Path) -> tuple[subprocess.Popen, dict]:
    fh = open(log, "w")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=fh, env=env, text=True)
    line = proc.stdout.readline()
    if not line:
        proc.kill()
        raise RuntimeError(f"{cmd[0]} did not start; see {log.name}")
    return proc, json.loads(line)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def step1_orbit(rep: Report, orbit: Path, work: Path) -> None:
    probe = HERE / "probes" / "orbit_host_authority.mjs"
    p = subprocess.run(["node", "--experimental-strip-types", str(probe), str(orbit)], capture_output=True, text=True, timeout=120)
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        rep.set(1, "component", "failed", f"host-authority probe crashed: {p.stderr.strip()[-300:]}")
        rep.set(1, "final", "blocked", "authority probe did not run")
        return
    unsafe = [k for k, v in res.items() if v == "EXECUTED"]
    if unsafe:
        rep.set(1, "component", "failed", f"host authority unsafe: {', '.join(unsafe)} (S1/S5)", probe=res)
        rep.set(1, "final", "blocked", "S1/S5 reproduce on the pinned Orbit")
        return
    rep.set(1, "component", "passed", "S1/S5 probes refused every unauthenticated approval and default grant", probe=res)
    rep.set(1, "final", "unrun", "fresh container deployment + first-agent onboarding not executed by this runner "
            "(needs the docker compose path of Orbit #25 on a clean host); routes were run from the checkout instead")


def step2_hyvv(rep: Report, hyvv_url: str, token: str, version: str | None) -> None:
    code_h, health, raw_h = http_json(hyvv_url + "/v1/health", None, token, "GET")
    code_v, ver, _ = http_json(hyvv_url + "/v1/version", None, token, "GET")
    leaks = [m for m in LEAK_MARKERS if m in raw_h]
    if code_h != 200:
        rep.set(2, "component", "failed", f"/v1/health returned {code_h}")
    elif code_v != 200:
        rep.set(2, "component", "blocked", f"hyvv {health.get('version')} answers /v1/health but /v1/version is {code_v}: "
                "capability advertisement is specified, not implemented", health_version=health.get("version"))
    else:
        rep.set(2, "component", "passed" if not leaks else "failed", f"/v1/version {ver}" + (f"; leaks {leaks}" if leaks else ""))
    rep.set(2, "final", rep.steps[2]["component"]["status"] if rep.steps[2]["component"]["status"] != "passed" else "unrun",
            rep.steps[2]["component"]["reason"] if rep.steps[2]["component"]["status"] != "passed" else "needs the live host in --real-agents mode")


def scenario(rep: Report, srcs: dict[str, Path], work: Path, real_agents: bool) -> None:
    import secrets
    bb_src, orbit_src, hyvv_src = srcs["bundlebees"], srcs["orbitdesktop"], srcs["hyvv"]
    plugin = load_bundlebees(bb_src)
    from bundlebees_plugin import client as bbclient  # type: ignore
    from bundlebees_plugin import metrics as bbmetrics  # type: ignore

    root = work / "scenario"
    root.mkdir()
    state = root / "state"
    state.mkdir(mode=0o700)
    repo, red_rev, patches = make_project(root)
    pdir = root / "patches"; pdir.mkdir()
    for tag, diff in patches.items():
        (pdir / f"{tag}.patch").write_text(diff, encoding="utf-8")

    # hyvv (real runtime, scripted backend) and Orbit (real routes) on loopback.
    env = {"PATH": os.environ["PATH"], "HOME": str(root)}
    hproc, h = start_line([sys.executable, str(HERE / "hyvv_host.py"), str(hyvv_src), str(root / "hyvv-data"), str(pdir)], env, work / "hyvv.log")
    token = Path(h["token_file"]).read_text().strip()
    runtime = root / "orbit-runtime"; runtime.mkdir()
    key = secrets.token_hex(32)
    (runtime / "collab-board.key").write_text(key)
    os.chmod(runtime / "collab-board.key", 0o600)
    oproc, o = start_line(["node", "--experimental-strip-types", str(HERE / "orbit_stack.mjs")],
                          {**env, "ORBIT_SRC": str(orbit_src), "ORBIT_RUNTIME": str(runtime), "LAUNCHER_URL": h["url"],
                           "LAUNCHER_TOKEN_FILE": h["token_file"], "BB_STATE": str(state)}, work / "orbit.log")
    try:
        step2_hyvv(rep, h["url"], token, h.get("version"))
        host0 = Host(state, None)
        plugin.register(host0)

        # 4. frozen contract with collected test ids --------------------------------------
        draft = root / "contract.json"; draft.write_text(json.dumps(contract(red_rev), indent=2))
        frozen = root / "contract.frozen.json"
        freeze = ["contract", "freeze", str(draft), "--approved-by", "acceptance reviewer", "--out", str(frozen)]
        collects = host0.has_flag(["contract", "freeze"], "--workdir")
        if collects:
            freeze += ["--workdir", str(repo), "--state-dir", str(state)]
        rc, text = host0.cli(freeze)
        (work / "freeze.log").write_text(text)
        if rc != 0 or not frozen.exists():
            rep.set(4, "component", "failed", f"freeze exited {rc}"); rep.set(4, "final", "failed", "freeze failed")
            return
        fc = json.loads(frozen.read_text())
        if not collects:
            rep.set(4, "component", "blocked", "pinned bundlebees freezes without collecting test ids (C1 lives in bundlebees #12, not in this build)")
        else:
            bogus = json.loads(draft.read_text()); bogus["id"] = "FL-bogus"
            bogus["acceptance_criteria"][0]["tests"] = ["tests/test_tax.py::test_does_not_exist"]
            bd = root / "bogus.json"; bd.write_text(json.dumps(bogus))
            rc_b, t_b = host0.cli(["contract", "freeze", str(bd), "--approved-by", "x", "--out", str(root / "bogus.frozen.json"),
                                   "--workdir", str(repo), "--state-dir", str(state)])
            ok = rc_b != 0 and ("test_unresolved" in t_b or "not_collected" in t_b)
            rep.set(4, "component", "passed" if ok else "failed",
                    "frozen with a signed collected-id manifest; an uncollected test id was refused" if ok else f"uncollected id not refused (rc {rc_b})")
        rep.set(4, "final", rep.steps[4]["component"]["status"], rep.steps[4]["component"]["reason"] + " (contract step needs no worker)")

        # 5. RED -------------------------------------------------------------------------
        rc, text = host0.cli(["tdd", "red", str(frozen), "--workdir", str(repo), "--state-dir", str(state)])
        (work / "red.log").write_text(text)
        rep.set(5, "component", "passed" if rc == 0 else "failed", "verifier recorded signed behavioral RED at source_rev in the sandbox" if rc == 0 else f"tdd red exited {rc}: {text.strip()[-200:]}")
        rep.set(5, "final", rep.steps[5]["component"]["status"], rep.steps[5]["component"]["reason"] + " (RED needs no worker)")

        # 3. dispatch through bundlebees -> Orbit -> hyvv ---------------------------------
        orbit = bbclient.OrbitAdapterClient(o["url"], token_provider=lambda: key, coordinator="four-layer",
                                            capability_dir=state / "artifact-caps", allow_loopback=True) \
            if "capability_dir" in bbclient.OrbitAdapterClient.__init__.__code__.co_varnames else None
        if orbit is None:
            rep.set(3, "component", "blocked", "pinned bundlebees has no capability-bound Orbit client")
            return
        host = Host(state, orbit)
        plugin.register(host)
        def dispatch(tag: str) -> dict:
            brief = {"objective": f"[{tag}] add apply_tax to shop/pricing.py", "assigned_files": ["shop/pricing.py"],
                     "acceptance": {"criteria": ["AC-001", "AC-002"], "tests": ["tests/test_tax.py"]}, "tests": ["tests/test_tax.py"],
                     "source_rev": red_rev, "branch": "wave/four-layer", "project": "toy-shop", "run_id": "four-layer", "wave": "fl1", "contract": fc}
            return json.loads(host.tools["bundlebees_dispatch"]({"brief": brief, "model": "deepseek-v4.1-flash"}))

        def wait(attempts: dict[str, str], timeout: float = 60) -> dict[str, str]:
            deadline, st = time.time() + timeout, {}
            while time.time() < deadline:
                st = {t: http_json(o["url"] + "/api/local-workers", {"op": "get", "attempt_id": a}, key)[1].get("state") for t, a in attempts.items()}
                if all(x in ("succeeded", "failed", "superseded", "not_started", "cancelled") for x in st.values()):
                    break
                time.sleep(0.3)
            return st

        ids: dict[str, str] = {}
        for tag in ("A1", "A2"):  # dispatched back to back: the parallel case
            reply = dispatch(tag)
            ids[tag] = reply.get("attempt_id")
            if not (reply.get("ok") and reply.get("lease_recorded")):
                rep.set(3, "component", "failed", f"dispatch {tag} refused: {json.dumps(reply)[:300]}")
                return
        states = wait(ids)
        parallel_states = dict(states)
        superseded = [t for t, x in states.items() if x == "superseded"]
        if superseded:
            rep.finding("FL-2", "Parallel dispatch through Orbit is impossible from bundlebees: OrbitAdapterClient sends no task_id "
                        "(only kanban_task_id), Orbit keys attempts by task_id, so every task-less attempt shares task_id=undefined and "
                        f"each new dispatch supersedes and cancels the previous active one (here {superseded}). Owners: bundlebees #9 client + Orbit #28 create.", "high")
            for t in superseded:  # continue the component run sequentially so later steps still get evidence
                reply = dispatch(t)
                ids[t] = reply.get("attempt_id")
                states.update(wait({t: ids[t]}))
        caps_ok = all((state / "artifact-caps" / f"{a}.cap").exists() and ((state / "artifact-caps" / f"{a}.cap").stat().st_mode & 0o777) == 0o600 for a in ids.values())
        _, listing, raw_list = http_json(o["url"] + "/api/local-workers", {"op": "list"}, key)
        leaked = [m for m in ("artifact_capability", "capability_sha256") if m in raw_list]
        ok3 = caps_ok and not leaked and all(x == "succeeded" for x in states.values())
        status3 = "passed" if ok3 and not superseded else "failed"
        rep.set(3, "component", status3,
                f"bundlebees -> Orbit (board key) -> hyvv (bearer); signed leases, 0600 capabilities; parallel states {parallel_states}"
                + (f"; re-dispatched sequentially -> {states}" if superseded else "") + (f"; list leaks {leaked}" if leaked else ""))
        rep.set(3, "final", "blocked" if superseded else "unrun", "parallel dispatch supersedes attempts (FL-2)" if superseded else "needs --real-agents (live hyvv host, real workers)")
        if not ok3:
            return
        rep.set(6, "component", "unrun", SCRIPTED)
        rep.set(6, "final", "unrun" if not real_agents else "blocked", "real-agent mode not run: see README 'When to run --real-agents'")

        # 8/9. artifact auth + integrity ---------------------------------------------------
        a1 = ids["A1"]
        code_n, body_n, raw_n = http_json(o["url"] + "/api/local-workers", {"op": "artifact", "attempt_id": a1, "coordinator": "four-layer"}, key)
        code_f, body_f, raw_f = http_json(o["url"] + "/api/local-workers", {"op": "artifact", "attempt_id": a1, "capability": "x" * 43}, key)
        art = orbit.artifact(a1)
        art_raw = json.dumps(art)
        sha = hashlib.sha256(patches["A1"].encode()).hexdigest()
        got_sha = (art.get("patch") or {}).get("sha256") if isinstance(art.get("patch"), dict) else art.get("patch_sha256")
        path_leaks = [m for m in LEAK_MARKERS if m in art_raw]
        ok8 = code_n == 403 and code_f == 403 and "+" not in raw_n and "apply_tax" not in raw_f
        rep.set(8, "component", "passed" if ok8 else "failed",
                f"shared board key without capability -> {code_n} {body_n.get('error') or body_n.get('code')}; forged capability -> {code_f}; owner capability -> artifact")
        if path_leaks:
            rep.finding("FL-1", f"Orbit artifact response for a hyvv result carries host path markers {path_leaks} (hyvv observed.result_file/workdir are passed through); verifier-only, but not model-safe", "medium")
        rep.set(8, "final", "unrun", "needs --real-agents")

        # 7/10/11. verify (GREEN), scope refusal, refactor, integrate, review ---------------
        rc1, t1 = host.cli(["verify", a1, "--workdir", str(repo), "--branch", "wave/four-layer", "--state-dir", str(state)])
        rc2, t2 = host.cli(["verify", ids["A2"], "--workdir", str(repo), "--branch", "wave/four-layer", "--state-dir", str(state)])
        (work / "verify.log").write_text(t1 + "\n----\n" + t2)
        rep.set(9, "component", "passed" if rc1 == 0 and sha in t1 else "failed",
                f"verify fetched A1 via Orbit, patch_sha256 matches the scripted diff, source_rev pinned" if rc1 == 0 and sha in t1 else f"verify A1 rc {rc1}: {t1.strip()[-200:]}")
        rep.set(9, "final", "unrun", "needs --real-agents")
        scope_ok = rc2 != 0 and "scope_violation" in t2
        rep.set(7, "component", "passed" if scope_ok else "failed",
                "A2 edited shop/labels.py outside its lease and was refused with scope_violation" if scope_ok else f"A2 not refused for scope (rc {rc2})")
        rep.set(7, "final", "unrun", "needs --real-agents")
        git(repo, "fetch", "-q", "origin"); git(repo, "checkout", "-q", "wave/four-layer"); git(repo, "reset", "-q", "--hard", "origin/wave/four-layer")
        rc_r, t_r = host.cli(["tdd", "refactor", str(frozen), "--workdir", str(repo), "--state-dir", str(state), "--none", "--note", "already minimal"])
        rc_i, t_i = host.cli(["integrate", "--wave", "fl1", "--attempts", a1, "--workdir", str(repo), "--branch", "wave/four-layer", "--state-dir", str(state)])
        (work / "integrate.log").write_text(t_i)
        rc_v, t_v = host.cli(["tdd", "review", str(frozen), "--state-dir", str(state), "--reviewer", "acceptance reviewer", "--approve",
                              "--note", "scripted approval by the acceptance runner (not a human decision)"])
        rep.set(11, "component", "passed" if rc_i == 0 else "failed", "combined branch integrated in the sandbox" if rc_i == 0 else f"integrate rc {rc_i}: {t_i.strip()[-240:]}")
        rep.set(11, "final", "unrun", "needs --real-agents")
        ok10 = rc1 == 0 and rc_r == 0 and rc_v == 0
        rep.set(10, "component", "passed" if ok10 else "failed", f"GREEN rc {rc1}, REFACTOR(--none) rc {rc_r}, REVIEW rc {rc_v}; review is the runner, not an independent human")
        rep.set(10, "final", "unrun", "needs --real-agents and an independent reviewer")
        rc_p, t_p = host.cli(["tdd", "report", str(frozen), "--state-dir", str(state), "--json"])
        (work / "report.txt").write_text(t_p)
        try:
            report = json.loads(t_p[t_p.index("{"):])
        except ValueError:
            report = {}

        # 12. metrics ------------------------------------------------------------------------
        events = bbmetrics.read_events(state, "four-layer")
        summ = bbmetrics.summarize(events)
        dispatch_events = sum(1 for e in events if e.get("event") == "dispatch")
        distinct = len({e.get("attempt_id") for e in events if e.get("event") == "dispatch"})
        tokens = summ.get("tokens")
        problems = []
        if summ.get("attempts_dispatched") != distinct:
            problems.append(f"attempts_dispatched={summ.get('attempts_dispatched')} but distinct dispatched attempts={distinct}")
        if isinstance(tokens, (int, float)) and tokens == 0:
            problems.append("token usage reported as 0 although no usage was reported (unknown expected)")
        rep.set(12, "component", "failed" if problems else "passed",
                "; ".join(problems) or f"attempts_dispatched={distinct} distinct (dispatch events {dispatch_events}); tokens {json.dumps(tokens)[:120]}; a duplicate event for one attempt is not exercised here",
                summary={k: summ.get(k) for k in ("attempts_dispatched", "tokens", "first_pass", "regressions") if k in summ})
        rep.set(12, "final", "unrun", "needs real usage from real workers")

        # 13. Orbit evidence view --------------------------------------------------------------
        if not o.get("evidence_route"):
            rep.set(13, "component", "blocked", "pinned Orbit has no evidence route")
        else:
            code_e, ev, raw_e = http_json(o["url"] + f"/api/acdd-evidence?contract={fc['id']}", None, key, "GET")
            view = ev.get("view") or {}
            accepted_cli = bool(report.get("accepted"))
            if code_e != 200:
                rep.set(13, "component", "failed", f"evidence route {code_e}")
            elif accepted_cli and not view.get("accepted"):
                pending = [c.get("id") + "=" + str(c.get("status")) for c in view.get("criteria", []) if c.get("status") != "passed"]
                has_report = (state / "reports" / f"{fc['id']}.json").is_file()
                why = (f"signed reports/{fc['id']}.json present; " if has_report else "no signed reports/<id>.json written; ")
                rep.set(13, "component", "blocked", f"bundlebees signed accepted=true but Orbit shows accepted=false "
                        f"(verificationState={view.get('verificationState')}, verified {view.get('verification', {}).get('verified')} records; "
                        f"{why}non-passed criteria: {', '.join(pending) or 'none'}; notes: {'; '.join(view.get('notes', []))[:200]})",
)
                if has_report and pending:
                    rep.finding("X2", "bundlebees signs acceptance_report/1 accepted=true while a review criterion is still "
                                f"{', '.join(pending)}; Orbit (fail-closed, no human-review verifier) shows incomplete. "
                                "The two layers disagree on what accepted means.", "medium")
            elif not accepted_cli:
                rep.set(13, "component", "unrun", f"nothing accepted to display (bundlebees accepted=False); Orbit verified "
                        f"{view.get('verification', {}).get('verified')} signed records and showed accepted={view.get('accepted')}")
            else:
                rep.set(13, "component", "passed" if view.get("accepted") == accepted_cli else "failed",
                        f"Orbit accepted={view.get('accepted')} vs bundlebees accepted={accepted_cli}")
        rep.set(13, "final", "blocked" if rep.steps[13]["component"]["status"] == "blocked" else "unrun", rep.steps[13]["component"]["reason"])

        # 14. human authorization separate --------------------------------------------------------
        human = report.get("human_authorization") or report.get("review_identity")
        gates = fc.get("authorization", {}).get("human_gates")
        if human is None:
            rep.set(14, "component", "blocked", "report does not state human authorization at all (needs bundlebees #12 semantics)")
        else:
            ok14 = "not_recorded" in json.dumps(human) or "unverified" in json.dumps(human)
            rep.set(14, "component", "passed" if ok14 else "failed", f"report keeps human authorization separate ({json.dumps(human)[:120]}); human gates {gates} untouched")
        rep.set(14, "final", rep.steps[14]["component"]["status"] if rep.steps[14]["component"]["status"] != "passed" else "unrun",
                "needs the final run's report" if rep.steps[14]["component"]["status"] == "passed" else rep.steps[14]["component"]["reason"])
    finally:
        for p in (oproc, hproc):
            p.terminate()
            with contextlib.suppress(Exception):
                p.wait(timeout=10)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--matrix", default=str(HERE / "matrix.json"))
    ap.add_argument("--src", action="append", default=[], help="repo=PATH: use a local checkout as-is instead of building")
    ap.add_argument("--real-agents", action="store_true", help="refused unless the preconditions in README are met")
    args = ap.parse_args()
    out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    matrix = json.loads(Path(args.matrix).read_text())
    rep = Report(out, matrix)
    overrides = dict(s.split("=", 1) for s in args.src)
    work = Path(tempfile.mkdtemp(prefix="four-layer-", dir=out))
    srcs: dict[str, Path] = {}
    try:
        for name, spec in matrix["repos"].items():
            info = build_repo(name, spec, work / "src", overrides.get(name))
            rep.revisions[name] = {k: v for k, v in info.items() if k != "path"}
            srcs[name] = Path(info["path"])
            for c in info.get("conflicts") or []:
                rep.finding(f"MERGE-{name}", f"merge candidate conflict: {c['merge'][:7]} in {', '.join(c['files'])}; built without it", "high")
        if args.real_agents:
            for s in rep.steps.values():
                s["final"] = {"status": "blocked", "reason": "--real-agents refused: preconditions in README (fixed blockers, bee cap check) are not automated yet"}
        step1_orbit(rep, srcs["orbitdesktop"], work)
        scenario(rep, srcs, work, args.real_agents)
    except Exception:
        (out / "runner-error.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), file=sys.stderr)
    doc = rep.write()
    for s in doc["steps"]:
        print(f"{s['n']:>2} {s['id']:<22} component={s['component']['status']:<8} final={s['final']['status']}")
    print("final accepted:", doc["final_accepted"])
    return 0 if doc["final_accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
