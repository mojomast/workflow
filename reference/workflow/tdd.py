"""TDD evidence for the reference demo: run, classify, record, check.

Implements docs/16-acdd-tdd.md §3-§5 with the standard library: a unittest
runner that reports per-case outcomes, the first-match-wins classification
table, ``tdd-evidence/1`` records, and the RED / GREEN / REFACTOR rules.

Teaching code, but honest: records are HMAC-SHA256 signed with a demo key
kept in the run directory (``keys/verifier.key``), and the report treats a
record whose signature does not verify as ``evidence_tampered``. A key next to
the evidence only shows the mechanism; bundlebees keeps its key in the
coordinator's private state directory. Tests run in a throwaway clone with a
minimal environment, inside bubblewrap when it is available
(``workflow/sandbox.py``); records say ``sandbox: none`` when it is not.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import sandbox as _sandbox
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
    desc = getattr(test, "description", "")
    if raw == desc and desc.endswith(")") and " (" in desc:
        # unittest's _ErrorHolder for setUpClass/setUpModule (and tearDown*) failures:
        # "setUpClass (tests.test_x.Cls)" -> tests/test_x.py::Cls
        kind, target = desc[:-1].split(" (", 1)
        parts = target.split(".")
        if kind.endswith("Module"):
            return "/".join(parts) + ".py", "setup" if kind.startswith("setUp") else "teardown"
        return "/".join(parts[:-1]) + ".py::" + parts[-1], "setup" if kind.startswith("setUp") else "teardown"
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


def run_unittest(root: Path, test_files: list[str] | None = None, *, timeout: int = 120, sandbox: bool = False) -> dict:
    """Run *test_files* (default: tests/test_*.py) and return a result with cases.

    With ``sandbox=True`` the run uses bubblewrap when it is available; the
    result's ``sandbox`` field says which (``"bwrap"`` or ``"none"``).
    """
    root = Path(root).resolve()
    files = list(test_files) if test_files else _discover(root)
    backend = _sandbox.detect_backend() if sandbox else None
    with tempfile.TemporaryDirectory(prefix="tdd-run-") as tmp:
        script, out = Path(tmp) / "runner.py", Path(tmp) / "cases.json"
        script.write_text(_RUNNER, encoding="utf-8")
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": tmp, "TMPDIR": tmp, "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONHASHSEED": "0"}
        argv = [sys.executable, "-B", str(script), str(root), str(out), *files]
        if backend == "bwrap":
            argv = _sandbox.wrap(argv, root, Path(tmp))
        try:
            proc = subprocess.run(argv, cwd=str(root), env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"exit_code": None, "tests": 0, "failures": 0, "errors": 0, "skipped": 0, "timed_out": True, "cases": [],
                    "sandbox": backend or "none"}
        cases = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    return {
        "exit_code": proc.returncode, "tests": len(cases),
        "failures": sum(c["outcome"] == "failed" for c in cases),
        "errors": sum(c["outcome"] == "error" for c in cases),
        "skipped": sum(c["outcome"] == "skipped" for c in cases),
        "timed_out": False, "cases": cases, "sandbox": backend or "none",
    }


def isolation_environment() -> dict:
    """The ``environment`` block for records: which isolation the runs really had."""
    backend = _sandbox.detect_backend()
    if backend == "bwrap":
        return {"python": sys.version.split()[0], "sandbox": "bwrap",
                "isolation": "throwaway clone, minimal env, bwrap: no network, private /tmp, home hidden"}
    return {"python": sys.version.split()[0], "sandbox": "none",
            "isolation": "throwaway clone, minimal env, no sandbox (bwrap not available)"}


# ----------------------------------------------------------------- signing


def ensure_key(path: Path) -> bytes:
    """Return the 32-byte demo verifier key at *path*, creating it (0600) atomically."""
    path = Path(path)
    if path.exists():
        data = path.read_bytes()
        if len(data) != 32:
            raise TddError("evidence_invalid", "the verifier key is not 32 bytes", "Delete the run directory and run the demo again.")
        return data
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        key = os.urandom(32)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
        try:
            os.link(tmp, path)
        except FileExistsError:
            return ensure_key(path)
        return key
    finally:
        tmp.unlink(missing_ok=True)


def _canonical(record: Mapping[str, Any]) -> bytes:
    body = {k: v for k, v in record.items() if k not in ("signature", "_path")}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sign_record(record: Mapping[str, Any], key: bytes) -> dict:
    """Return a copy of *record* with an HMAC-SHA256 ``signature`` (``_path`` is not signed)."""
    return {**record, "signature": hmac.new(key, _canonical(record), hashlib.sha256).hexdigest()}


def verify_signature(record: Mapping[str, Any], key: bytes) -> bool:
    sig = record.get("signature")
    if not isinstance(sig, str):
        return False
    return hmac.compare_digest(sig, hmac.new(key, _canonical(record), hashlib.sha256).hexdigest())


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


def _criteria(contract: Mapping[str, Any], phase: str, cases: list[dict], classification: str,
              review_outcome: str | None = None) -> dict[str, str]:
    out = {}
    for a in contract["acceptance_criteria"]:
        kind = a["verification"]
        if kind in ("review", "manual"):
            out[a["id"]] = review_outcome or "review_required"
        elif kind == "integration":
            out[a["id"]] = ("passed" if classification == "passed" else "failed") if phase == "integration" else "not_run"
        else:
            hit = [c for c in cases if any(matches(c["id"], t) for t in a.get("tests", [])) and c["outcome"] != "skipped"]
            out[a["id"]] = "not_run" if not hit else ("failed" if any(c["outcome"] in ("failed", "error") for c in hit) else "passed")
    return out


def make_record(contract: Mapping[str, Any], contract_sha256: str, *, phase: str, revision: str,
                test_fingerprints: Mapping[str, str], command: list[str], result: Mapping[str, Any] | None,
                produced_by: Mapping[str, str], test_first: bool, environment: Mapping[str, Any] | None = None,
                notes: str | None = None, now: str | None = None, review_outcome: str | None = None) -> dict:
    if review_outcome is not None and (phase != "review" or review_outcome not in ("passed", "failed")):
        raise TddError("evidence_invalid", "review_outcome is only for review records and must be passed or failed", "Record reviews with phase='review'.")
    classification = review_outcome or classify(result, red_set(contract), added_interfaces(contract))
    res = dict(result) if result is not None else {"exit_code": None, "tests": 0, "failures": 0, "errors": 0, "skipped": 0, "timed_out": False, "cases": []}
    rec = {
        "evidence_version": EVIDENCE_VERSION, "contract_id": contract["id"], "contract_sha256": contract_sha256,
        "phase": phase, "revision": revision, "base_rev": contract["source_rev"],
        "test_fingerprints": dict(test_fingerprints), "command": list(command),
        "environment": dict(environment or isolation_environment()),
        "result": res, "classification": classification,
        "criteria": _criteria(contract, phase, res.get("cases") or [], classification, review_outcome),
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


def acceptance_report(contract: Mapping[str, Any], sha: str, records: list[Mapping[str, Any]], *, key: bytes | None = None) -> dict:
    """With *key*, records whose signature does not verify are ignored and their phase is ``evidence_tampered``."""
    tampered = set()
    if key is not None:
        tampered = {r["phase"] for r in records if not verify_signature(r, key)}
        records = [r for r in records if verify_signature(r, key)]
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
    for phase in tampered:
        if phase in phases:
            phases[phase] = "evidence_tampered"
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
