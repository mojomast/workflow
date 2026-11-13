"""ACDD (Agentic Contract-Driven Development) contracts for the reference demo.

Implements docs/16-acdd-tdd.md §2: the shared ``acdd/1`` JSON Schema, the
code checks JSON Schema cannot express, the canonical contract hash, and the
freeze/review step. Standard library only. The bundlebees plugin enforces the
same rules for real work (``bundlebees_plugin/contract.py``).
"""

from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from . import schema as _schema

CONTRACT_VERSION = "acdd/1"
REQUIRED_HUMAN_GATES = ("merge", "release", "deploy", "publish")
SUPPORTED_KEYWORDS = _schema.SUPPORTED_KEYWORDS
_DRIVE = re.compile(r"^[A-Za-z]:")


class ContractError(ValueError):
    """A contract was rejected. ``code`` is one of the §7 failure states."""

    def __init__(self, code: str, error: str, fix: str, field: str = "") -> None:
        super().__init__(error)
        self.code, self.error, self.fix, self.field = code, error, fix, field


def _invalid(field: str, error: str, fix: str) -> ContractError:
    return ContractError("contract_invalid", f"{field}: {error}", fix, field)


def load_schema() -> dict:
    return _schema.load("acdd-contract.schema.json")


def _norm_path(value: str, field: str) -> str:
    text = value.replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not text or text.startswith("/") or _DRIVE.match(text):
        raise _invalid(field, "must be a repository-relative path", "Use paths like shop/pricing.py.")
    if ".." in parts or any(p.lower() == ".git" for p in parts):
        raise _invalid(field, "must not contain '..' or be under .git", "Name files inside the repository.")
    return "/".join(parts)


def _test_file(test_id: str) -> str:
    return test_id.split("::", 1)[0]


def validate_contract(contract: Mapping[str, Any]) -> dict:
    """Return a validated, normalised deep copy; never mutates *contract*."""
    if not isinstance(contract, Mapping):
        raise _invalid("contract", "must be an object", "Pass an acdd/1 contract object.")
    c = copy.deepcopy(dict(contract))
    err = _schema.first_error(c, load_schema(), "contract")
    if err:
        raise _invalid(err[0], err[1], "Fix the field so it matches schemas/acdd-contract.schema.json.")
    scope = c["scope"]
    for key in ("assigned_files", "test_files", "read_only"):
        scope[key] = [_norm_path(p, f"contract.scope.{key}[{i}]") for i, p in enumerate(scope.get(key, []))] if key in scope else scope.get(key)
        if scope[key] is None:
            del scope[key]
    ids = [a["id"] for a in c["acceptance_criteria"]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise _invalid("contract.acceptance_criteria", f"duplicate criterion ids {', '.join(dupes)}", "Give every criterion a unique AC-NNN id.")
    tdd = c["tdd"]
    tests = set(scope.get("test_files", []))
    assigned = scope["assigned_files"]
    if tdd["applicable"]:
        for a in c["acceptance_criteria"]:
            if a["verification"] != "test":
                continue
            if not a.get("tests"):
                raise _invalid(f"contract.acceptance_criteria.{a['id']}", f"{a['id']} lists no tests", "Name the tests (path::name) that prove it.")
            for t in a["tests"]:
                if _test_file(t) not in tests:
                    raise _invalid(f"contract.acceptance_criteria.{a['id']}", f"test {t} is not in scope.test_files", "Add its file to scope.test_files.")
        overlap = sorted(tests & set(assigned))
        if overlap:
            raise _invalid("contract.scope", f"{', '.join(overlap)} is in both assigned_files and test_files", "The implementer must not be able to edit approved tests.")
        need = {"green"} | ({"red"} if tdd.get("test_first", True) is not False else set())
        missing = sorted(need - set(c["evidence_required"]))
        if missing:
            raise _invalid("contract.evidence_required", f"missing {', '.join(missing)}", "TDD contracts require red and green evidence.")
    elif not str(tdd.get("reason", "")).strip():
        raise _invalid("contract.tdd.reason", "is required when tdd.applicable is false", "Say why test-first does not apply.")
    for path in assigned:
        if is_prohibited(path, c):
            raise _invalid("contract.scope.prohibited", f"{path} is assigned but prohibited", "Remove it from assigned_files or prohibited.")
    gates = set(c["authorization"]["human_gates"])
    lost = [g for g in REQUIRED_HUMAN_GATES if g not in gates]
    if lost:
        raise _invalid("contract.authorization.human_gates", f"must keep {', '.join(lost)}", "Contracts cannot remove human gates.")
    if c["id"] in c.get("dependencies", []):
        raise _invalid("contract.dependencies", "a contract cannot depend on itself", "Remove its own id.")
    return c


def contract_sha256(contract: Mapping[str, Any]) -> str:
    body = {k: v for k, v in contract.items() if k != "review"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def freeze_contract(contract: Mapping[str, Any], *, approved_by: str, approved_at: str | None = None) -> dict:
    c = validate_contract(contract)
    c.pop("review", None)
    at = approved_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    c["review"] = {"status": "approved", "approved_by": approved_by, "approved_at": at, "contract_sha256": contract_sha256(c)}
    return c


def check_frozen(contract: Mapping[str, Any]) -> str:
    review = contract.get("review") if isinstance(contract, Mapping) else None
    if not isinstance(review, Mapping) or review.get("status") != "approved":
        raise ContractError("contract_not_frozen", "contract has not been approved", "Review it and freeze it before dispatch.", "contract.review")
    digest = contract_sha256(contract)
    if review.get("contract_sha256") != digest:
        raise ContractError("contract_changed", "contract changed after approval", "Re-review and freeze the new revision.", "contract.review.contract_sha256")
    validate_contract(contract)
    return digest


def criteria_tests(contract: Mapping[str, Any]) -> dict[str, list[str]]:
    return {a["id"]: list(a.get("tests", [])) for a in contract["acceptance_criteria"]}


def red_set(contract: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for a in contract["acceptance_criteria"]:
        if a["verification"] == "test" and not a.get("regression"):
            out += [t for t in a.get("tests", []) if t not in out]
    return out


def added_interfaces(contract: Mapping[str, Any]) -> list[str]:
    return [i["name"] for i in contract.get("interfaces", []) if i.get("change") == "add"]


def is_prohibited(path: str, contract: Mapping[str, Any]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in contract.get("scope", {}).get("prohibited", []))
