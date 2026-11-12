#!/usr/bin/env python3
"""Cold-start acceptance harness for the workflow + bundlebees stack.

Run by ``cold_start.sh`` inside a fresh container or a clean temp HOME and
venv. It never needs an API key and makes no model calls. Network is used only
by the shell script to clone the public repositories and install pytest.

What it proves, in order (every step is logged to ``steps.jsonl``):

 1. reference-demo   The workflow repo's offline reference demo passes from a
                     fresh clone.
 2. start            The bundlebees plugin, loaded from a fresh clone, is
                     registered into a minimal host (the same PluginContext
                     surface Hermes provides) with a coordinator state dir.
 3. register-worker  A worker backend is registered: by default the offline
                     ``ScriptedWorkerBackend`` below (implements bundlebees'
                     WorkerBackend contract: create/result/health/projects/
                     attempts). ``ACCEPTANCE_ADAPTER=launcher`` instead uses
                     bundlebees' real launcher adapter for the honest slices.
 4. dispatch         Three briefs are dispatched in parallel through the real
                     ``bundlebees_dispatch`` tool, which validates each strict
                     brief and writes an HMAC-signed coordinator lease.
 5. violation        One worker deliberately edits a file outside its lease
                     and claims a wider lease in its result.
 6. verify           ``hermes bundlebees verify`` (the real CLI handler) runs
                     for each attempt in the bwrap/firejail sandbox. The two
                     honest slices must verify; the violating one must be
                     rejected with ``scope_violation`` and leave no trace.
 7. integrate        ``hermes bundlebees integrate`` runs the full suite on the
                     combined branch and writes the accepted wave record.
 8. outputs          The harness independently re-checks the combined branch
                     (fresh clone of the bare remote, its own pytest run, the
                     out-of-lease change absent) and the metrics log.
 9. acdd             One ACDD contract end to end on a second toy repo: freeze,
                     RED on the tests-only commit, contract-carrying dispatch,
                     verify records GREEN, a worker that edits the approved
                     tests is refused (``tests_tampered``), REFACTOR skip,
                     integrate, REVIEW, and the acceptance report says accepted
                     and test-first. Needs an ACDD-capable bundlebees; with
                     ``ACCEPTANCE_ACDD=require`` a missing CLI fails the run,
                     otherwise it is reported as UNRUN (never as passed).
10. artifact         ``acceptance-artifact.json`` records shas, verify records,
                     the wave record, the ACDD result and the metrics summary.

Manual interventions are appended to ``interventions.jsonl``; the harness
itself adds one for every non-default escape hatch it was told to use.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import importlib
import io
import json
import os
import re
import types
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable

RUN_ID = "acceptance"
WAVE = "w1"
BRANCH = "wave/w1"

PRICING = '''"""Prices in integer cents."""


def apply_discount(cents: int, percent: int) -> int:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return cents - (cents * percent) // 100
'''

PRICING_TEST = '''from shop.pricing import apply_discount


def test_discount():
    assert apply_discount(1000, 10) == 900
'''

LABELS = '''"""Human-readable labels."""


def format_price(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"
'''

LABELS_TEST = '''from shop.labels import format_price


def test_format_price():
    assert format_price(199) == "$1.99"
'''

PRICING_TAX = PRICING + '''

def apply_tax(cents: int, rate_percent: int) -> int:
    if rate_percent < 0:
        raise ValueError("rate must not be negative")
    return cents + (cents * rate_percent) // 100
'''

PRICING_TAX_TEST = PRICING_TEST + '''

def test_apply_tax():
    from shop.pricing import apply_tax
    import pytest

    assert apply_tax(1000, 10) == 1100
    with pytest.raises(ValueError):
        apply_tax(1000, -1)
'''

LABELS_RECEIPT = LABELS + '''

def format_receipt_line(name: str, cents: int) -> str:
    if not name.strip():
        raise ValueError("name must not be blank")
    return f"{name}: {format_price(cents)}"
'''

LABELS_RECEIPT_TEST = LABELS_TEST + '''

def test_receipt_line():
    from shop.labels import format_receipt_line

    assert format_receipt_line("Tea", 199) == "Tea: $1.99"
'''

NOTES = '''"""Free-form order notes."""


def clean_note(text: str) -> str:
    return " ".join(text.split())
'''


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class Log:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.steps = out / "steps.jsonl"
        self.interventions = out / "interventions.jsonl"
        self.started = time.monotonic()
        self.results: list[dict[str, Any]] = []
        self.unrun_checks: list[dict[str, Any]] = []

    def step(self, name: str, ok: bool, **detail: Any) -> None:
        record = {"step": name, "ok": bool(ok), "t_s": round(time.monotonic() - self.started, 3), **detail}
        self.results.append(record)
        with self.steps.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail.get('summary')}" if detail.get("summary") else ""), flush=True)

    def unrun(self, name: str, why: str) -> None:
        """A check that did not run. Never counted as passed; listed in the summary."""
        self.unrun_checks.append({"step": name, "why": why})
        print(f"[UNRUN] {name} - {why}", flush=True)

    def intervention(self, what: str, why: str, kind: str = "manual") -> None:
        record = {"kind": kind, "what": what, "why": why, "t_s": round(time.monotonic() - self.started, 3)}
        with self.interventions.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")


def git(cwd: Path, *args: str, check: bool = True) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C.UTF-8",
    }
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Host and worker backend
# ---------------------------------------------------------------------------


class AcceptanceHost:
    """Minimal host with the PluginContext surface bundlebees uses in Hermes.

    ``bundlebees_state_dir`` and ``bundlebees_client`` are the plugin's
    documented injection seams (used when Hermes' plugin_data_dir and adapter
    config are not present). Nothing here bypasses brief validation, the
    signed lease, the sandbox, or verify/integrate.
    """

    def __init__(self, settings: dict[str, Any], state_dir: Path, client: Any | None) -> None:
        self.settings = dict(settings)
        self.tools: dict[str, dict[str, Any]] = {}
        self.cli_commands: dict[str, dict[str, Any]] = {}
        self.hooks: dict[str, Any] = {}
        self.skills: dict[str, Path] = {}
        self.bundlebees_state_dir = state_dir
        if client is not None:
            self.bundlebees_client = client

    def register_tool(self, name, toolset, schema, handler, description="", emoji="", **_kw):
        self.tools[name] = {"schema": schema, "handler": handler}
        return name

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli_commands[name] = {"setup_fn": setup_fn, "handler_fn": handler_fn}
        return name

    def register_hook(self, name, callback, **_kw):
        self.hooks[name] = callback

    def register_skill(self, name, skill_md):
        self.skills[name] = Path(skill_md)

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def cli(self, argv: list[str]) -> tuple[int, str]:
        import argparse as _argparse

        record = self.cli_commands["bundlebees"]
        parser = _argparse.ArgumentParser(prog="hermes bundlebees")
        record["setup_fn"](parser)
        args = parser.parse_args(argv)
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = record["handler_fn"](args)
        return int(rc or 0), buf.getvalue()

    def cli_help(self, argv: list[str]) -> str:
        """Return ``--help`` text for a subcommand without exiting."""
        import argparse as _argparse

        record = self.cli_commands["bundlebees"]
        parser = _argparse.ArgumentParser(prog="hermes bundlebees")
        record["setup_fn"](parser)
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            try:
                parser.parse_args([*argv, "--help"])
            except SystemExit:
                pass
        return buf.getvalue()


class ScriptedWorkerBackend:
    """Offline worker runtime implementing bundlebees' WorkerBackend contract.

    Each ``create`` runs a scripted worker in its own throwaway clone at the
    brief's ``source_rev`` and returns a unified diff. ``behaviour`` names
    which script runs; ``out_of_scope`` edits a file outside its lease and
    claims a wider lease, to provoke the verifier.
    """

    name = "scripted-offline"

    def __init__(self, repo: Path, scratch: Path, scripts: dict[str, Callable[[Path], None]]) -> None:
        self.repo = repo
        self.scratch = scratch
        self.scripts = scripts
        self.results: dict[str, dict[str, Any]] = {}
        self.created: list[dict[str, Any]] = []

    # Optional capabilities the dispatch tool consults.
    def health(self) -> dict[str, Any]:
        return {"ok": True, "models": ["scripted-worker"]}

    def projects(self) -> list[dict[str, Any]]:
        return [{"key": "toy-shop"}]

    def attempts(self) -> list[dict[str, Any]]:
        return []

    def create(self, brief: dict, *, model: str, kanban_task_id: str | None = None) -> dict:
        task = str(brief.get("objective", "")).split(":", 1)[0].strip()
        attempt_id = f"att-{task}"
        script = self.scripts[task]
        work = self.scratch / attempt_id
        git(self.scratch, "clone", "-q", str(self.repo), str(work))
        git(work, "checkout", "-q", brief["source_rev"])
        script(work)
        git(work, "add", "-A")
        patch = git(work, "diff", "--cached", "--binary", brief["source_rev"]) + "\n"
        claimed = list(brief["assigned_files"])
        if task == "W3":
            claimed = claimed + ["shop/pricing.py"]  # the worker tries to widen its lease
        self.results[attempt_id] = {
            "attempt_id": attempt_id,
            "patch": patch,
            "base_rev": brief["source_rev"],
            "assigned_files": claimed,
            "usage": {"tokens": 0, "cost_usd": 0.0},
            "tests": list(brief.get("tests") or []),
        }
        self.created.append({"attempt_id": attempt_id, "model": model, "files": claimed})
        return {"attempt_id": attempt_id, "state": "completed"}

    def result(self, attempt_id: str) -> dict:
        return dict(self.results[attempt_id])

    def get_raw(self, attempt_id: str) -> dict:
        return {"result": self.result(attempt_id)}


class RoutingBackend:
    """Optional real-backend mode: honest slices go to a real bundlebees
    adapter, the deliberate violation stays scripted so it is reproducible.
    Not exercised by the default offline run."""

    def __init__(self, real: Any, scripted: ScriptedWorkerBackend, timeout_s: float) -> None:
        self.real = real
        self.scripted = scripted
        self.timeout_s = timeout_s
        self.name = f"{getattr(real, 'name', type(real).__name__)}+scripted-violation"
        self.real_ids: set[str] = set()

    def health(self) -> dict[str, Any]:
        return self.real.health()

    def projects(self) -> list[dict[str, Any]]:
        return self.real.projects()

    def attempts(self) -> list[dict[str, Any]]:
        return self.real.attempts()

    def create(self, brief: dict, *, model: str, kanban_task_id: str | None = None) -> dict:
        if str(brief.get("objective", "")).startswith("W3:"):
            return self.scripted.create(brief, model=model, kanban_task_id=kanban_task_id)
        data = self.real.create(brief, model=model, kanban_task_id=kanban_task_id)
        self.real_ids.add(str(data.get("attempt_id")))
        return data

    def result(self, attempt_id: str) -> dict:
        if attempt_id not in self.real_ids:
            return self.scripted.result(attempt_id)
        deadline = time.monotonic() + self.timeout_s
        while True:
            data = self.real.result(attempt_id)
            if data.get("patch") or time.monotonic() > deadline:
                return data
            time.sleep(10)


def _install_env_secret_scope() -> None:
    """Host shim for real-adapter mode: Hermes resolves get_secret from the
    profile; here it reads BUNDLEBEES_LAUNCHER_TOKEN from the environment.
    The value is never printed or written to the output directory."""
    agent_mod = types.ModuleType("agent")
    scope = types.ModuleType("agent.secret_scope")
    scope.get_secret = lambda name, default=None: os.environ.get(name, default)
    agent_mod.secret_scope = scope
    sys.modules.setdefault("agent", agent_mod)
    sys.modules.setdefault("agent.secret_scope", scope)


_CODE_RE = re.compile(
    r"\b(scope_violation|lease_missing|lease_tampered|base_undeclared|base_mismatch|"
    r"source_rev_missing|patch_not_at_source_rev|branch_diverged|tests_failed|"
    r"secret_detected|sandbox_unavailable|patch_failed|not_configured)\b"
)


def _write(work: Path, rel: str, text: str) -> None:
    path = work / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


SCRIPTS: dict[str, Callable[[Path], None]] = {
    "W1": lambda w: (_write(w, "shop/pricing.py", PRICING_TAX), _write(w, "tests/test_pricing.py", PRICING_TAX_TEST)),
    "W2": lambda w: (_write(w, "shop/labels.py", LABELS_RECEIPT), _write(w, "tests/test_labels.py", LABELS_RECEIPT_TEST)),
    # Leased only shop/notes.py, but also rewrites pricing (out of lease).
    "W3": lambda w: (_write(w, "shop/notes.py", NOTES), _write(w, "shop/pricing.py", PRICING.replace("cents - (cents * percent) // 100", "0  # sabotage"))),
}

BRIEFS = {
    "W1": {
        "objective": "W1: add apply_tax(cents, rate_percent) to shop/pricing.py",
        "assigned_files": ["shop/pricing.py", "tests/test_pricing.py"],
        "acceptance": {"criteria": ["apply_tax(1000, 10) == 1100", "negative rate rejected"], "tests": ["tests/test_pricing.py"]},
        "tests": ["tests/test_pricing.py"],
    },
    "W2": {
        "objective": "W2: add format_receipt_line(name, cents) to shop/labels.py",
        "assigned_files": ["shop/labels.py", "tests/test_labels.py"],
        "acceptance": {"criteria": ["format_receipt_line('Tea', 199) == 'Tea: $1.99'"], "tests": ["tests/test_labels.py"]},
        "tests": ["tests/test_labels.py"],
    },
    "W3": {
        "objective": "W3: add clean_note(text) in a new shop/notes.py (deliberate lease violation)",
        "assigned_files": ["shop/notes.py"],
        "acceptance": {"criteria": ["clean_note collapses whitespace"], "tests": ["tests/test_pricing.py"]},
        "tests": ["tests/test_pricing.py"],
    },
}


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ACDD end to end (one contract): freeze -> RED -> dispatch -> verify (GREEN)
# -> refactor skip -> review -> integrate -> report. Needs an ACDD-capable
# bundlebees (the `contract` and `tdd` commands). ACCEPTANCE_ACDD=require
# fails the run without them; the default (auto) records the check as UNRUN,
# never as passed.
# ---------------------------------------------------------------------------

ACDD_TEST = '''from shop.pricing import apply_tax


def test_apply_tax_adds_the_rate():
    assert apply_tax(1000, 10) == 1100


def test_apply_tax_rejects_a_negative_rate():
    import pytest
    with pytest.raises(ValueError):
        apply_tax(100, -1)
'''

ACDD_IMPL = PRICING + '''

def apply_tax(cents: int, rate_percent: int) -> int:
    if rate_percent < 0:
        raise ValueError("rate_percent must not be negative")
    return cents * (100 + rate_percent) // 100
'''

ACDD_TAMPER_TEST = "def test_apply_tax_adds_the_rate():\n    assert True\n\n\ndef test_apply_tax_rejects_a_negative_rate():\n    assert True\n"


def _acdd_contract(red_rev: str) -> dict:
    t = "tests/test_tax.py::"
    return {
        "contract_version": "acdd/1", "id": "CS-apply-tax", "title": "apply_tax for the cold-start shop",
        "outcome": {"summary": "Callers can add a tax rate to a price in cents.", "observable_behavior": ["apply_tax(1000, 10) == 1100"]},
        "interfaces": [{"name": "apply_tax", "kind": "function", "change": "add"}],
        "acceptance_criteria": [
            {"id": "AC-001", "given": "1000 cents", "when": "apply_tax(1000, 10)", "then": "1100", "verification": "test",
             "tests": [t + "test_apply_tax_adds_the_rate"]},
            {"id": "AC-002", "given": "a negative rate", "when": "apply_tax(100, -1)", "then": "ValueError", "verification": "test",
             "tests": [t + "test_apply_tax_rejects_a_negative_rate"]},
            {"id": "AC-003", "statement": "the combined branch passes the full suite", "verification": "integration"},
            {"id": "AC-004", "statement": "a reviewer read the change", "verification": "review"},
        ],
        "scope": {"assigned_files": ["shop/pricing.py"], "test_files": ["tests/test_tax.py"], "prohibited": ["shop/labels.py"]},
        "source_rev": red_rev,
        "tdd": {"applicable": True, "test_first": True},
        "verification": {"independent": True, "integration": True},
        "evidence_required": ["red", "green", "refactor", "integration", "review"],
        "authorization": {"human_gates": ["merge", "tag", "release", "deploy", "publish"]},
    }


def acdd_end_to_end(log: "Log", host: "AcceptanceHost", work: Path, settings: dict, plugin: Any, out: Path) -> dict:
    mode = os.environ.get("ACCEPTANCE_ACDD", "auto").strip().lower()
    if not ({"contract", "tdd"} <= set(_subcommands(host))):
        why = "this bundlebees ref has no ACDD commands (contract/tdd)"
        if mode == "require":
            log.step("acdd", False, summary=why + " but ACCEPTANCE_ACDD=require")
        else:
            log.unrun("acdd", why + "; set BUNDLEBEES_REF to an ACDD-capable ref and ACCEPTANCE_ACDD=require")
        return {"status": "unrun", "why": why}

    root = work / "acdd"
    root.mkdir()
    state = root / "state"
    state.mkdir(mode=0o700)
    repo = root / "shop"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Acceptance Coordinator")
    git(repo, "config", "user.email", "acceptance@example.invalid")
    for rel, text in (("shop/__init__.py", ""), ("shop/pricing.py", PRICING), ("tests/__init__.py", ""),
                      ("tests/test_pricing.py", PRICING_TEST), ("conftest.py", "")):
        _write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "baseline")
    _write(repo, "tests/test_tax.py", ACDD_TEST)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "approved tests (RED, tests only)")
    red_rev = git(repo, "rev-parse", "HEAD")
    remote = root / "shop.git"
    git(root, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    branch = "acdd/cs"
    git(repo, "branch", branch)
    git(repo, "push", "-q", "-u", "origin", branch)

    checks: dict[str, Any] = {}
    draft = root / "contract.json"
    draft.write_text(json.dumps(_acdd_contract(red_rev), indent=2), encoding="utf-8")
    frozen = root / "contract.frozen.json"
    freeze = ["contract", "freeze", str(draft), "--approved-by", "acceptance reviewer", "--out", str(frozen)]
    # bundlebees after the Nov 12 review collects the approved test ids at
    # source_rev before freezing (needs --workdir); older pins lack the flag.
    if host.cli_help(["contract", "freeze"]).find("--workdir") >= 0:
        freeze += ["--workdir", str(repo), "--state-dir", str(state)]
    rc, text = host.cli(freeze)
    checks["freeze"] = rc == 0 and frozen.exists()
    (out / "acdd-freeze.log").write_text(text, encoding="utf-8")
    contract = json.loads(frozen.read_text()) if frozen.exists() else {}
    rc, text = host.cli(["tdd", "red", str(frozen), "--workdir", str(repo), "--state-dir", str(state)])
    checks["red"] = rc == 0
    (out / "acdd-red.log").write_text(text, encoding="utf-8")

    scripts = {"A1": lambda w: _write(w, "shop/pricing.py", ACDD_IMPL),
               "A2": lambda w: (_write(w, "shop/pricing.py", PRICING), _write(w, "tests/test_tax.py", ACDD_TAMPER_TEST))}
    worker = ScriptedWorkerBackend(repo, root / "workers", scripts)
    (root / "workers").mkdir()
    acdd_host = AcceptanceHost(settings, state, worker)
    plugin.register(acdd_host)
    dispatch = acdd_host.tools["bundlebees_dispatch"]["handler"]
    replies = {}
    for task, files in (("A1", ["shop/pricing.py"]), ("A2", ["shop/pricing.py"])):
        brief = {"objective": f"{task}: add apply_tax to shop/pricing.py", "assigned_files": files,
                 "acceptance": {"criteria": ["AC-001", "AC-002"], "tests": ["tests/test_tax.py"]}, "tests": ["tests/test_tax.py"],
                 "source_rev": red_rev, "branch": branch, "project": "toy-shop", "run_id": "acdd", "wave": "a1", "contract": contract}
        replies[task] = json.loads(dispatch({"brief": brief, "model": "scripted-worker"}))
    checks["dispatch"] = all(r.get("lease_recorded") for r in replies.values())
    rc1, t1 = acdd_host.cli(["verify", "att-A1", "--workdir", str(repo), "--branch", branch, "--state-dir", str(state)])
    rc2, t2 = acdd_host.cli(["verify", "att-A2", "--workdir", str(repo), "--branch", branch, "--state-dir", str(state)])
    (out / "acdd-verify.log").write_text(t1 + "\n----\n" + t2, encoding="utf-8")
    checks["green"] = rc1 == 0
    checks["tamper_refused"] = rc2 != 0 and "tests_tampered" in t2
    git(repo, "fetch", "-q", "origin")
    git(repo, "checkout", "-q", branch)
    git(repo, "reset", "-q", "--hard", f"origin/{branch}")
    rc, text = acdd_host.cli(["tdd", "refactor", str(frozen), "--workdir", str(repo), "--state-dir", str(state),
                              "--none", "--note", "already minimal"])
    checks["refactor"] = rc == 0
    rc, text = acdd_host.cli(["integrate", "--wave", "a1", "--attempts", "att-A1", "--workdir", str(repo), "--branch", branch,
                              "--state-dir", str(state)])
    checks["integrate"] = rc == 0
    (out / "acdd-integrate.log").write_text(text, encoding="utf-8")
    rc, text = acdd_host.cli(["tdd", "review", str(frozen), "--state-dir", str(state), "--reviewer", "acceptance reviewer",
                              "--approve", "--note", "scripted approval (acceptance harness)"])
    checks["review"] = rc == 0
    rc, text = acdd_host.cli(["tdd", "report", str(frozen), "--state-dir", str(state), "--json"])
    try:
        report = json.loads(text[text.index("{"):])
    except ValueError:
        report = {}
    (out / "acdd-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    checks["accepted"] = report.get("accepted") is True and report.get("test_first") is True
    records = sorted(p.name for p in (state / "evidence" / "CS-apply-tax").glob("*.json"))
    ok = all(checks.values())
    log.step("acdd", ok, summary=f"contract CS-apply-tax: {', '.join(k for k, v in checks.items() if v)}"
             + (f"; FAILED: {', '.join(k for k, v in checks.items() if not v)}" if not ok else "")
             + f"; {len(records)} signed records", checks=checks, phases=report.get("phases"), records=records)
    return {"status": "passed" if ok else "failed", "checks": checks, "phases": report.get("phases"), "records": records}


def _subcommands(host: "AcceptanceHost") -> list[str]:
    import argparse as _argparse
    parser = _argparse.ArgumentParser()
    host.cli_commands["bundlebees"]["setup_fn"](parser)
    for action in parser._actions:  # noqa: SLF001 - argparse has no public API for this
        if isinstance(action, _argparse._SubParsersAction):  # noqa: SLF001
            return list(action.choices)
    return []


def make_toy_repo(root: Path) -> tuple[Path, Path, str]:
    repo = root / "toy-shop"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Acceptance Coordinator")
    git(repo, "config", "user.email", "acceptance@example.invalid")
    _write(repo, "shop/__init__.py", "")
    _write(repo, "shop/pricing.py", PRICING)
    _write(repo, "shop/labels.py", LABELS)
    _write(repo, "tests/__init__.py", "")
    _write(repo, "tests/test_pricing.py", PRICING_TEST)
    _write(repo, "tests/test_labels.py", LABELS_TEST)
    _write(repo, "conftest.py", "")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "toy-shop baseline")
    source_rev = git(repo, "rev-parse", "HEAD")
    remote = root / "toy-shop.git"
    git(root, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "branch", BRANCH)
    git(repo, "push", "-q", "-u", "origin", BRANCH)
    return repo, remote, source_rev


def load_bundlebees(clone: Path):
    if clone.name != "bundlebees":
        raise RuntimeError("the bundlebees clone directory must be named 'bundlebees'")
    sys.path.insert(0, str(clone.parent))
    sys.path.insert(0, str(clone))
    sys.modules.pop("bundlebees", None)
    return importlib.import_module("bundlebees")


def run(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    log = Log(out)
    for raw in os.environ.get("ACCEPTANCE_PRIOR_INTERVENTIONS", "").split("||"):
        if raw.strip():
            what, _, why = raw.partition("::")
            log.intervention(what.strip(), why.strip() or "recorded by cold_start.sh", kind="environment")

    workflow = Path(args.workflow).resolve()
    bb_clone = Path(args.bundlebees).resolve()
    work = out / "work"
    work.mkdir(exist_ok=True)

    # 1. reference demo -------------------------------------------------------
    demo_out = work / "reference-run"
    proc = subprocess.run(
        [sys.executable, str(workflow / "reference" / "run_demo.py"), "--out", str(demo_out)],
        capture_output=True, text=True, cwd=str(work),
    )
    log.step("reference-demo", proc.returncode == 0, summary=(proc.stdout.strip().splitlines() or ["?"])[-1].strip(), exit_code=proc.returncode)
    if proc.returncode != 0:
        (out / "reference-demo.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")

    # 2. start the system -----------------------------------------------------
    plugin = load_bundlebees(bb_clone)
    from bundlebees_plugin import sandbox, metrics, revision  # noqa: E402  (from the fresh clone)

    backend = sandbox.detect_backend("auto")
    settings: dict[str, Any] = {"verify_isolation": "auto", "verify_timeout_s": 300}
    if backend is None:
        if os.environ.get("ACCEPTANCE_ALLOW_UNSAFE_LOCAL") == "1":
            settings["verify_allow_unsafe_local"] = True
            log.intervention(
                "set verify_allow_unsafe_local=true",
                "no strong sandbox (bubblewrap/firejail) on this host; ACCEPTANCE_ALLOW_UNSAFE_LOCAL=1",
                kind="escape-hatch",
            )
        else:
            log.step("start", False, summary="no strong sandbox backend; install bubblewrap (fails closed by design)")
            return finish(log, out, {})
    state_dir = work / "coordinator-state"
    state_dir.mkdir(mode=0o700, exist_ok=True)
    root = work / "toy"
    root.mkdir(exist_ok=True)
    repo, remote, source_rev = make_toy_repo(root)

    # 3. register a worker agent ------------------------------------------------
    adapter = os.environ.get("ACCEPTANCE_ADAPTER", "scripted").strip().lower()
    scripted = ScriptedWorkerBackend(repo, work / "workers", SCRIPTS)
    (work / "workers").mkdir(exist_ok=True)
    if adapter == "scripted":
        client: Any = scripted
    else:
        # Optional real backend: bundlebees' own adapter from settings/env.
        # Not exercised by the default offline run.
        from bundlebees_plugin.adapters import adapter_from_config  # noqa: E402

        _install_env_secret_scope()
        settings.update({
            "adapter": adapter,
            "launcher_url": os.environ.get("ACCEPTANCE_LAUNCHER_URL", ""),
            "allow_private": os.environ.get("ACCEPTANCE_ALLOW_PRIVATE") == "1",
        })
        real = adapter_from_config(settings)
        client = RoutingBackend(real, scripted, float(os.environ.get("ACCEPTANCE_RESULT_TIMEOUT", "1800")))
        log.intervention(f"used real adapter {adapter}", "ACCEPTANCE_ADAPTER set by the operator", kind="operator-choice")
    host = AcceptanceHost(settings, state_dir, client)
    plugin.register(host)
    started = "bundlebees" in host.cli_commands and "bundlebees_dispatch" in host.tools
    log.step("start", started, summary=f"plugin registered: {len(host.tools)} tools, sandbox={backend or 'none-unsafe-local'}",
             tools=sorted(host.tools), sandbox=backend or "none-unsafe-local")
    health = client.health()
    log.step("register-worker", bool(health.get("ok")), summary=f"worker backend '{getattr(client, 'name', adapter)}' healthy", backend=getattr(client, "name", adapter))

    # 4/5. dispatch in parallel ----------------------------------------------
    dispatch = host.tools["bundlebees_dispatch"]["handler"]
    model = "scripted-worker" if adapter == "scripted" else os.environ.get("ACCEPTANCE_MODEL", "deepseek-v4.1-flash")
    project = "toy-shop" if adapter == "scripted" else os.environ.get("ACCEPTANCE_PROJECT", "toy-shop")

    def send(task: str) -> dict:
        brief = dict(BRIEFS[task], source_rev=source_rev, branch=BRANCH, project=project, run_id=RUN_ID, wave=WAVE)
        return json.loads(dispatch({"brief": brief, "model": model}))

    with futures.ThreadPoolExecutor(max_workers=3) as pool:
        replies = dict(zip(BRIEFS, pool.map(send, BRIEFS)))
    attempts = {task: reply.get("attempt_id") for task, reply in replies.items()}
    leased = all(reply.get("lease_recorded") for reply in replies.values())
    lease_files = sorted(p.name for p in (state_dir / "leases").glob("*.json"))
    log.step("dispatch", leased and all(attempts.values()), summary=f"3 parallel dispatches, signed leases: {lease_files}",
             replies={t: {k: r.get(k) for k in ("ok", "attempt_id", "lease_recorded", "code")} for t, r in replies.items()})
    claimed = scripted.results.get("att-W3", {}).get("assigned_files")
    log.step("violation", claimed == ["shop/notes.py", "shop/pricing.py"],
             summary="W3 edited shop/pricing.py outside its lease and claimed it", worker_claimed=claimed)

    # 6. verify ---------------------------------------------------------------
    verify: dict[str, dict[str, Any]] = {}
    for task in ("W1", "W2", "W3"):
        rc, text = host.cli(["verify", attempts[task], "--workdir", str(repo), "--branch", BRANCH, "--state-dir", str(state_dir)])
        record_path = state_dir / "verify-results" / f"{attempts[task]}.json"
        record = json.loads(record_path.read_text()) if record_path.exists() else {}
        (out / f"verify-{task}.log").write_text(text, encoding="utf-8")
        found = _CODE_RE.search(text)
        code = record.get("code") or (found.group(1) if found else ("verified" if rc == 0 else None))
        verify[task] = {"rc": rc, "ok": record.get("ok"), "code": code, "output_tail": text[-1500:]}
    honest_ok = all(verify[t]["rc"] == 0 and verify[t]["ok"] for t in ("W1", "W2"))
    log.step("verify-honest", honest_ok, summary=f"W1 rc={verify['W1']['rc']}, W2 rc={verify['W2']['rc']}")
    w3 = verify["W3"]
    rejected = w3["rc"] != 0 and w3["code"] == "scope_violation" and w3["ok"] is False
    log.step("verify-rejects-violation", rejected, summary=f"W3 rc={w3['rc']} code={w3['code']}")

    # 7. integrate ------------------------------------------------------------
    git(repo, "checkout", "-q", BRANCH)
    rc, text = host.cli(["integrate", "--wave", WAVE, "--attempts", attempts["W1"], attempts["W2"],
                         "--workdir", str(repo), "--branch", BRANCH, "--state-dir", str(state_dir)])
    wave_path = state_dir / "waves" / f"{WAVE}.json"
    wave = json.loads(wave_path.read_text()) if wave_path.exists() else {}
    accepted = rc == 0 and "accepted: yes" in text and all(revision.attempt_accepted(state_dir, attempts[t]) for t in ("W1", "W2"))
    (out / "integrate.log").write_text(text, encoding="utf-8")
    log.step("integrate", accepted, summary=f"rc={rc}; wave record {'written' if wave else 'missing'}", output_tail=text[-1500:])

    # 8. independent output checks -------------------------------------------
    check = work / "check"
    git(work, "clone", "-q", "--branch", BRANCH, str(remote), str(check))
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=check, capture_output=True, text=True)
    pricing = (check / "shop" / "pricing.py").read_text()
    labels = (check / "shop" / "labels.py").read_text()
    outputs_ok = (
        tests.returncode == 0
        and "def apply_tax" in pricing
        and "sabotage" not in pricing
        and "def format_receipt_line" in labels
        and not (check / "shop" / "notes.py").exists()
        and not revision.attempt_accepted(state_dir, attempts["W3"])
    )
    summary = metrics.summarize(metrics.read_events(state_dir, RUN_ID))
    log.step("outputs", outputs_ok, summary=f"independent pytest: {(tests.stdout.strip().splitlines() or ['?'])[-1]}; W3 change absent",
             metrics=summary)

    # 9. ACDD: one contract end to end ---------------------------------------
    acdd = acdd_end_to_end(log, host, work, settings, plugin, out)

    # 10. artifact ------------------------------------------------------------
    artifact = {
        "acdd": acdd,
        "accepted": bool(accepted and outputs_ok and rejected and honest_ok and acdd["status"] != "failed"),
        "source_rev": source_rev,
        "branch": BRANCH,
        "integration_head": git(check, "rev-parse", "HEAD"),
        "attempts": attempts,
        "verify": {t: {k: v[k] for k in ("rc", "ok", "code")} for t, v in verify.items()},
        "wave": wave,
        "metrics": summary,
        "sandbox": backend or "none-unsafe-local",
        "worker_backend": getattr(client, "name", adapter),
        "workflow_rev": git(workflow, "rev-parse", "HEAD"),
        "bundlebees_rev": git(bb_clone, "rev-parse", "HEAD"),
    }
    (out / "acceptance-artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log.step("artifact", artifact["accepted"], summary=f"acceptance-artifact.json accepted={artifact['accepted']}")
    return finish(log, out, artifact)


def finish(log: Log, out: Path, artifact: dict) -> int:
    ok = bool(log.results) and all(r["ok"] for r in log.results)
    interventions = []
    if log.interventions.exists():
        interventions = [json.loads(l) for l in log.interventions.read_text().splitlines() if l.strip()]
    manual = [i for i in interventions if i.get("kind") == "manual"]
    summary = {
        "ok": ok,
        "steps": [{"step": r["step"], "ok": r["ok"], "summary": r.get("summary")} for r in log.results],
        "interventions": interventions,
        "manual_interventions": len(manual),
        "unrun": log.unrun_checks,
        "elapsed_s": round(time.monotonic() - log.started, 2),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    unrun = f", {len(log.unrun_checks)} UNRUN ({', '.join(u['step'] for u in log.unrun_checks)})" if log.unrun_checks else ""
    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({len(log.results)} steps{unrun}, {len(interventions)} logged interventions, {summary['elapsed_s']}s)")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", required=True, help="Fresh clone of mojomast/workflow")
    parser.add_argument("--bundlebees", required=True, help="Fresh clone of mojomast/bundlebees (dir named bundlebees)")
    parser.add_argument("--out", required=True, help="Output directory for logs and the artifact")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "harness-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
