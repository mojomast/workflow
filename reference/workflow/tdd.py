"""TDD evidence for the reference demo: run, classify, record, check.

Implements docs/16-acdd-tdd.md §3-§5 with the standard library: a unittest
runner that reports per-case outcomes, the first-match-wins classification
table, ``tdd-evidence/1`` records, and the RED / GREEN / REFACTOR rules.

Teaching only: records are plain JSON files and are not signed. bundlebees
signs its records with the coordinator key (``bundlebees_plugin/tdd.py``).
Tests here run in a throwaway clone with a minimal environment, but not in a
sandbox; bundlebees runs worker-produced tests under bubblewrap or firejail.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import schema as _schema
from .acdd import added_interfaces, red_set

EVIDENCE_VERSION = "tdd-evidence/1"
CLASSIFICATIONS = ("behavioral_failure", "passed", "syntax_error", "collection_error",
                   "environment_error", "unrelated_failure", "timeout", "not_run")
_SYNTAX = {"SyntaxError", "IndentationError", "TabError"}
_MISSING = {"ImportError", "ModuleNotFoundError", "AttributeError"}


class TddError(ValueError):
    def __init__(self, code: str, error: str, fix: str) -> None:
        super().__init__(error)
        self.code, self.error, self.fix = code, error, fix


# --------------------------------------------------------------- running tests

_RUNNER = r'''
import json, sys, unittest
root, out, files = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.path.insert(0, root)
cases = []
def tid(test):
    raw = test.id()
    if raw.startswith("unittest.loader._FailedTest."):
        return raw.split("_FailedTest.", 1)[1].replace(".", "/") + ".py", "collection"
    parts = raw.split(".")
    mod = [p for p in parts[:-2]]
    return "/".join(mod) + ".py::" + parts[-2] + "::" + parts[-1], "call"
class R(unittest.TestResult):
    def _add(self, test, outcome, err=None):
        i, stage = tid(test)
        c = {"id": i, "outcome": outcome, "stage": stage, "error_type": "", "message": ""}
        if err:
            c["error_type"] = err[0].__name__
            c["message"] = str(err[1]).splitlines()[0][:500] if str(err[1]) else ""
        cases.append(c)
    def addSuccess(self, t): self._add(t, "passed")
    def addFailure(self, t, e): self._add(t, "failed", e)
    def addError(self, t, e): self._add(t, "error", e)
    def addSkip(self, t, r): self._add(t, "skipped")
    def addExpectedFailure(self, t, e): self._add(t, "passed")
    def addUnexpectedSuccess(self, t): self._add(t, "failed")
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for f in files:
    name = f[:-3].replace("/", ".")
    try:
        suite.addTests(loader.loadTestsFromName(name))
    except Exception as exc:
        cases.append({"id": f, "outcome": "error", "stage": "collection", "error_type": type(exc).__name__, "message": str(exc).splitlines()[0][:500] if str(exc) else ""})
suite.run(R())
json.dump(cases, open(out, "w"))
sys.exit(0 if all(c["outcome"] in ("passed", "skipped") for c in cases) else 1)
'''


def _discover(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in (root / "tests").glob("test_*.py"))


def run_unittest(root: Path, test_files: list[str] | None = None, *, timeout: int = 120) -> dict:
    """Run *test_files* (default: tests/test_*.py) and return a result with cases."""
    root = Path(root)
    files = list(test_files) if test_files else _discover(root)
    with tempfile.TemporaryDirectory(prefix="tdd-run-") as tmp:
        script, out = Path(tmp) / "runner.py", Path(tmp) / "cases.json"
        script.write_text(_RUNNER, encoding="utf-8")
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": tmp, "TMPDIR": tmp, "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONHASHSEED": "0"}
        try:
            proc = subprocess.run([sys.executable, "-B", str(script), str(root), str(out), *files], cwd=str(root),
                                  env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"exit_code": None, "tests": 0, "failures": 0, "errors": 0, "skipped": 0, "timed_out": True, "cases": []}
        cases = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    return {
        "exit_code": proc.returncode, "tests": len(cases),
        "failures": sum(c["outcome"] == "failed" for c in cases),
        "errors": sum(c["outcome"] == "error" for c in cases),
        "skipped": sum(c["outcome"] == "skipped" for c in cases),
        "timed_out": False, "cases": cases,
    }


def fingerprint_files(root: Path, files: list[str]) -> dict[str, str]:
    out = {}
    for f in files:
        p = Path(root) / f
        if f.startswith("/") or ".." in Path(f).parts or p.is_symlink() or not p.is_file():
            raise TddError("tests_tampered", f"approved test file {f} is missing or not a regular file", "Restore the approved test file.")
        out[f] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ----------------------------------------------------------- classification


def matches(case_id: str, test_id: str) -> bool:
    return case_id == test_id or any(case_id.startswith(test_id + sep) or test_id.startswith(case_id + sep) for sep in ("::", "["))


def _missing_interface(case: Mapping[str, Any], added: list[str]) -> bool:
    et, msg = case.get("error_type", ""), case.get("message", "")
    if et == "NotImplementedError":
        return True
    return et in _MISSING and any(f"'{n}'" in msg or f"'{n.rsplit('.', 1)[-1]}'" in msg for n in added)


def classify(result: Mapping[str, Any] | None, red: list[str], added: list[str]) -> str:
    """docs/16 §4, first match wins."""
    if result is None:
        return "not_run"
    if result.get("timed_out"):
        return "timeout"
    cases = result.get("cases") or []
    if any(c["outcome"] == "error" and c.get("error_type") in _SYNTAX for c in cases):
        return "syntax_error"
    if result.get("exit_code") in (3, 4, 5):
        return "environment_error"
    bad = [c for c in cases if c["outcome"] in ("failed", "error")]
    in_red = lambda c: any(matches(c["id"], t) for t in red)  # noqa: E731
    if any(not in_red(c) for c in bad):
        return "unrelated_failure"
    for c in bad:
        if c["outcome"] == "error" and not _missing_interface(c, added):
            return "collection_error" if c.get("stage") == "collection" else "environment_error"
    if not bad:
        return "passed" if result.get("exit_code") == 0 else "environment_error"
    return "behavioral_failure"


def _criteria(contract: Mapping[str, Any], phase: str, cases: list[dict], classification: str) -> dict[str, str]:
    out = {}
    for a in contract["acceptance_criteria"]:
        kind = a["verification"]
        if kind in ("review", "manual"):
            out[a["id"]] = "review_required"
        elif kind == "integration":
            out[a["id"]] = ("passed" if classification == "passed" else "failed") if phase == "integration" else "not_run"
        else:
            hit = [c for c in cases if any(matches(c["id"], t) for t in a.get("tests", [])) and c["outcome"] != "skipped"]
            out[a["id"]] = "not_run" if not hit else ("failed" if any(c["outcome"] in ("failed", "error") for c in hit) else "passed")
    return out


def make_record(contract: Mapping[str, Any], contract_sha256: str, *, phase: str, revision: str,
                test_fingerprints: Mapping[str, str], command: list[str], result: Mapping[str, Any] | None,
                produced_by: Mapping[str, str], test_first: bool, environment: Mapping[str, Any] | None = None,
                notes: str | None = None, now: str | None = None) -> dict:
    classification = classify(result, red_set(contract), added_interfaces(contract))
    res = dict(result) if result is not None else {"exit_code": None, "tests": 0, "failures": 0, "errors": 0, "skipped": 0, "timed_out": False, "cases": []}
    rec = {
        "evidence_version": EVIDENCE_VERSION, "contract_id": contract["id"], "contract_sha256": contract_sha256,
        "phase": phase, "revision": revision, "base_rev": contract["source_rev"],
        "test_fingerprints": dict(test_fingerprints), "command": list(command),
        "environment": dict(environment or {"python": sys.version.split()[0], "isolation": "throwaway clone, minimal env, no sandbox (teaching)"}),
        "result": res, "classification": classification,
        "criteria": _criteria(contract, phase, res.get("cases") or [], classification),
        "produced_by": dict(produced_by), "test_first": bool(test_first),
        "at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if notes:
        rec["notes"] = notes
    return rec


def validate_evidence(record: Mapping[str, Any]) -> None:
    err = _schema.first_error(dict(record), _schema.load("tdd-evidence.schema.json"), "evidence")
    if err:
        raise TddError("evidence_invalid", f"{err[0]}: {err[1]}", "Records must match schemas/tdd-evidence.schema.json.")


# ------------------------------------------------------------------- checks


def _same_contract(contract, sha, rec):
    if rec.get("contract_sha256") != sha or rec.get("base_rev") != contract["source_rev"]:
        raise TddError("stale_revision", f"{rec.get('phase')} evidence was recorded for another contract revision or baseline", "Re-run the check against the frozen contract.")


def check_red(contract: Mapping[str, Any], sha: str, rec: Mapping[str, Any]) -> None:
    _same_contract(contract, sha, rec)
    if rec.get("produced_by", {}).get("role") != "verifier":
        raise TddError("red_invalid", "RED must be produced by the independent verifier", "Have the verifier run the approved tests on the baseline.")
    cases = rec["result"].get("cases") or []
    missing = [t for t in red_set(contract) if not any(matches(c["id"], t) and c["outcome"] in ("failed", "error") for c in cases)]
    if rec["classification"] == "passed" or missing:
        raise TddError("red_incomplete", "RED tests passed on the baseline: " + ", ".join(missing or ["all"]), "Tighten the tests so they fail before the change.")
    if rec["classification"] != "behavioral_failure":
        raise TddError("red_invalid", f"RED run was {rec['classification']}, not a behavioural failure", "Fix the environment or test syntax, then record RED again.")
    if set(rec["test_fingerprints"]) != set(contract["scope"].get("test_files", [])):
        raise TddError("tests_tampered", "RED fingerprints do not cover exactly scope.test_files", "Fingerprint every approved test file.")


def check_green(contract: Mapping[str, Any], sha: str, red: Mapping[str, Any] | None, green: Mapping[str, Any]) -> None:
    after = contract.get("tdd", {}).get("test_first") is False
    if red is None and not after:
        raise TddError("red_missing", "GREEN has no RED to compare against", "Record RED on the baseline first.")
    _same_contract(contract, sha, green)
    if red is not None:
        check_red(contract, sha, red)
        if green["test_fingerprints"] != red["test_fingerprints"]:
            raise TddError("tests_tampered", "approved tests changed between RED and GREEN", "Restore the approved tests; do not edit them in the implementation.")
    if green.get("produced_by", {}).get("role") != "verifier" or green["classification"] != "passed":
        raise TddError("green_failed", f"GREEN run was {green['classification']}", "Fix the implementation until the approved tests pass.")


def check_refactor(contract, sha, red, green, refactor) -> None:
    check_green(contract, sha, red, green)
    _same_contract(contract, sha, refactor)
    if refactor["test_fingerprints"] != green["test_fingerprints"]:
        raise TddError("tests_tampered", "approved tests changed during refactor", "Refactor the code, not the tests.")
    if refactor.get("produced_by", {}).get("role") != "verifier" or refactor["classification"] != "passed":
        raise TddError("refactor_failed", f"REFACTOR run was {refactor['classification']}", "Keep the tests green while refactoring.")


def acceptance_report(contract: Mapping[str, Any], sha: str, records: list[Mapping[str, Any]]) -> dict:
    last = {}
    for r in records:
        last[r["phase"]] = r
    red, green, refactor = last.get("red"), last.get("green"), last.get("refactor")
    after = contract.get("tdd", {}).get("test_first") is False

    def status(fn, *args):
        try:
            fn(*args)
            return "valid"
        except TddError as exc:
            return exc.code

    phases = {}
    for phase in contract["evidence_required"]:
        rec = last.get(phase)
        if rec is None:
            phases[phase] = "unrun"
        elif phase == "red":
            phases[phase] = status(check_red, contract, sha, rec)
        elif phase == "green":
            phases[phase] = "red_missing" if red is None and not after else status(check_green, contract, sha, red, rec)
        elif phase == "refactor":
            phases[phase] = status(check_refactor, contract, sha, red, green, rec) if green else "unrun"
        elif phase == "integration":
            phases[phase] = "valid" if rec["classification"] == "passed" and rec.get("contract_sha256") == sha else "integration_failed"
        else:
            phases[phase] = "valid" if rec.get("produced_by", {}).get("role") in ("reviewer", "human") and rec["classification"] == "passed" else "review_failed"
    source = last.get("integration") or refactor or green
    criteria = {}
    for a in contract["acceptance_criteria"]:
        st = source["criteria"].get(a["id"], "not_run") if source else "not_run"
        criteria[a["id"]] = {"status": st, "evidence": source.get("_path") if source else None}
    review_ok = phases.get("review") == "valid"
    accepted = all(v == "valid" for v in phases.values()) and all(
        c["status"] == "passed" or (c["status"] == "review_required" and review_ok) for c in criteria.values())
    test_first = not after and red is not None and phases.get("red") == "valid" and all(r.get("test_first", True) for r in records)
    return {"contract_id": contract["id"], "contract_sha256": sha, "mode": "contract", "test_first": bool(test_first),
            "phases": phases, "criteria": criteria, "accepted": bool(accepted)}
