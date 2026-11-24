"""Contract-first, test-first run of the reference workflow (docs/16-acdd-tdd.md).

USER OBJECTIVE -> ACDD CONTRACT -> CONTRACT REVIEW (freeze) -> TEST-FIRST
PREPARATION (approved tests, RED on baseline + tests only) -> PARALLEL
WORKERS (leases exclude the approved tests) -> GREEN -> REFACTOR ->
INDEPENDENT VERIFICATION -> INTEGRATION -> acceptance report. Human gates
(merge, tag, release, deploy, publish) are never exercised here.

Teaching code: scripted workers and a scripted reviewer, unkeyed leases, and
a demo verifier key kept in the run directory. Evidence records are
HMAC-signed and checked, and tests run in throwaway clones inside bubblewrap
when it is available (records say ``sandbox: none`` when it is not).
bundlebees is the production implementation of the same rules.
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path

from . import acdd, tdd
from .metrics import MetricsLog
from .orchestrator import prepare_run_dir
from .packets import write_handoff
from .toy import create_toy_repo, run_git, write
from .verify import _changed_paths_from_patch, throwaway_checkout
from .workers import LABELS_WITH_RECEIPT, PRICING_WITH_TAX, _export_clone

GATES = ["merge", "tag", "release", "deploy", "publish"]
VERIFIER = {"role": "verifier", "name": "reference verifier"}

APPROVED_TEST_PRICING = '''import unittest

from shop import pricing


class PricingTests(unittest.TestCase):
    def test_ten_percent_off(self):
        self.assertEqual(pricing.apply_discount(1000, 10), 900)

    def test_rejects_negative_price(self):
        with self.assertRaises(ValueError):
            pricing.apply_discount(-1, 10)

    def test_rejects_bad_percent(self):
        with self.assertRaises(ValueError):
            pricing.apply_discount(100, 150)

    def test_apply_tax(self):
        self.assertEqual(pricing.apply_tax(1000, 10), 1100)

    def test_apply_tax_rejects_negative_rate(self):
        with self.assertRaises(ValueError):
            pricing.apply_tax(100, -1)


if __name__ == "__main__":
    unittest.main()
'''

APPROVED_TEST_LABELS = '''import unittest

from shop import labels


class LabelTests(unittest.TestCase):
    def test_formats_cents(self):
        self.assertEqual(labels.format_price(199), "$1.99")

    def test_formats_zero(self):
        self.assertEqual(labels.format_price(0), "$0.00")

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            labels.format_price(-5)

    def test_receipt_line(self):
        self.assertEqual(labels.format_receipt_line("Tea", 199), "Tea: $1.99")

    def test_receipt_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            labels.format_receipt_line("  ", 100)


if __name__ == "__main__":
    unittest.main()
'''

PRICING_REFACTORED = '''def _require_non_negative(value: int, what: str) -> None:
    if value < 0:
        raise ValueError(f"{what} must be non-negative")


def apply_discount(price_cents: int, percent: int) -> int:
    """Return the discounted price in cents, rounding down."""
    _require_non_negative(price_cents, "price")
    if percent < 0 or percent > 100:
        raise ValueError("percent out of range")
    return price_cents * (100 - percent) // 100


def apply_tax(price_cents: int, rate_percent: int) -> int:
    """Return the price with tax added, rounding down."""
    _require_non_negative(price_cents, "price")
    _require_non_negative(rate_percent, "rate")
    return price_cents * (100 + rate_percent) // 100
'''

WEAKENED_TEST_PRICING = APPROVED_TEST_PRICING.replace(
    "        self.assertEqual(pricing.apply_tax(1000, 10), 1100)", "        self.assertTrue(callable(pricing.apply_tax))"
).replace("        with self.assertRaises(ValueError):\n            pricing.apply_tax(100, -1)", "        pass")

BROKEN_PRICING = PRICING_WITH_TAX.replace("return price_cents * (100 + rate_percent) // 100", "return price_cents")


def _pricing_contract(cid: str, source_rev: str, title: str) -> dict:
    return {
        "contract_version": "acdd/1", "id": cid, "title": title,
        "outcome": {"summary": "Callers can add a tax rate to a price in cents.",
                    "observable_behavior": ["apply_tax(1000, 10) returns 1100", "a negative rate raises ValueError"]},
        "interfaces": [{"name": "apply_tax", "kind": "function", "change": "add"}],
        "acceptance_criteria": [
            {"id": "AC-001", "given": "a price of 1000 cents", "when": "apply_tax(1000, 10) is called", "then": "it returns 1100",
             "verification": "test", "tests": ["tests/test_pricing.py::PricingTests::test_apply_tax"]},
            {"id": "AC-002", "given": "a negative rate", "when": "apply_tax(100, -1) is called", "then": "it raises ValueError",
             "verification": "test", "tests": ["tests/test_pricing.py::PricingTests::test_apply_tax_rejects_negative_rate"]},
            {"id": "AC-003", "statement": "existing apply_discount tests keep passing", "verification": "test", "regression": True,
             "tests": ["tests/test_pricing.py::PricingTests::test_ten_percent_off", "tests/test_pricing.py::PricingTests::test_rejects_negative_price",
                       "tests/test_pricing.py::PricingTests::test_rejects_bad_percent"]},
            {"id": "AC-004", "statement": "the combined branch passes the full suite", "verification": "integration"},
            *([{"id": "AC-005", "statement": "a reviewer reads the change: apply_tax mirrors apply_discount and its error text is clear",
                "verification": "review"}] if cid == "W1-pricing" else []),
        ],
        "dependencies": [], "assumptions": ["prices are integer cents"],
        "scope": {"assigned_files": ["shop/pricing.py"], "test_files": ["tests/test_pricing.py"],
                  "prohibited": ["shop/labels.py", "tests/test_labels.py"]},
        "source_rev": source_rev,
        "tdd": {"applicable": True, "test_first": True},
        "verification": {"independent": True, "integration": True},
        "evidence_required": ["red", "green", "refactor", "integration", "review"] if cid == "W1-pricing" else ["red", "green", "integration"],
        "authorization": {"human_gates": GATES, "not_authorized": ["editing approved tests", "merge", "release", "deploy", "publish"]},
    }


def _labels_contract(source_rev: str) -> dict:
    return {
        "contract_version": "acdd/1", "id": "W2-labels", "title": "Add format_receipt_line to the labels module",
        "outcome": {"summary": "A receipt line can be formatted as 'name: $x.yy'.", "observable_behavior": ["format_receipt_line('Tea', 199) == 'Tea: $1.99'"]},
        "interfaces": [{"name": "format_receipt_line", "kind": "function", "change": "add"}],
        "acceptance_criteria": [
            {"id": "AC-001", "given": "the name 'Tea' and 199 cents", "when": "format_receipt_line is called", "then": "it returns 'Tea: $1.99'",
             "verification": "test", "tests": ["tests/test_labels.py::LabelTests::test_receipt_line"]},
            {"id": "AC-002", "given": "a blank name", "when": "format_receipt_line('  ', 100) is called", "then": "it raises ValueError",
             "verification": "test", "tests": ["tests/test_labels.py::LabelTests::test_receipt_rejects_blank_name"]},
            {"id": "AC-003", "statement": "existing format_price tests keep passing", "verification": "test", "regression": True,
             "tests": ["tests/test_labels.py::LabelTests::test_formats_cents", "tests/test_labels.py::LabelTests::test_formats_zero",
                       "tests/test_labels.py::LabelTests::test_rejects_negative"]},
            {"id": "AC-004", "statement": "the combined branch passes the full suite", "verification": "integration"},
        ],
        "dependencies": [], "assumptions": ["names are plain strings"],
        "scope": {"assigned_files": ["shop/labels.py"], "test_files": ["tests/test_labels.py"], "prohibited": ["shop/pricing.py", "tests/test_pricing.py"]},
        "source_rev": source_rev,
        "tdd": {"applicable": True, "test_first": True},
        "verification": {"independent": True, "integration": True},
        "evidence_required": ["red", "green", "integration"],
        "authorization": {"human_gates": GATES},
    }


TESTS = {"tests/test_pricing.py": APPROVED_TEST_PRICING, "tests/test_labels.py": APPROVED_TEST_LABELS}


class Rejected(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code, self.reason = code, reason


def _commit_tests(toy: Path, base: str, contract: dict) -> str:
    """Test-first preparation: commit ONLY the approved tests on top of the baseline."""
    branch = f"acdd/tests-{contract['id']}"
    run_git(toy, "checkout", "-q", "-b", branch, base)
    for f in contract["scope"]["test_files"]:
        write(toy / f, TESTS[f])
    run_git(toy, "add", *contract["scope"]["test_files"])
    run_git(toy, "commit", "-q", "-m", f"approved tests for {contract['id']}")
    rev = run_git(toy, "rev-parse", "HEAD").stdout.strip()
    run_git(toy, "checkout", "-q", "main")
    return rev


def _run_phase(toy: Path, rev: str, contract: dict, sha: str, phase: str, test_files: list[str] | None, **kw) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"acdd-{phase}-"))
    try:
        clone = tmp / "repo"
        throwaway_checkout(toy, rev, clone)
        fp = tdd.fingerprint_files(clone, contract["scope"]["test_files"])
        result = tdd.run_unittest(clone, test_files, sandbox=True)
        cmd = ["python3", "-m", "unittest"] + (test_files or ["discover", "-s", "tests"])
        return tdd.make_record(contract, sha, phase=phase, revision=rev, test_fingerprints=fp, command=cmd,
                               result=result, produced_by=VERIFIER, test_first=True,
                               environment=tdd.isolation_environment(), **kw)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _save(ev_dir: Path, name: str, rec: dict, run_dir: Path) -> str:
    """Sign *rec* in place with the run's demo key, validate it and write it."""
    rec.pop("_path", None)
    # Signed order (review C2): sequence and predecessor digest go inside the
    # signed body, so same-second records are ordered by the signer, not by
    # their phase label or file name.
    previous = []
    for other in sorted(ev_dir.glob("*.json")) if ev_dir.is_dir() else []:
        try:
            data = json.loads(other.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("sequence"), int):
            previous.append(data)
    last = max(previous, key=lambda item: item["sequence"]) if previous else None
    rec["sequence"] = (last["sequence"] + 1) if last else 1
    rec["prev_sha256"] = tdd.record_digest(last) if last else None
    rec.update(tdd.sign_record(rec, _key(run_dir)))
    tdd.validate_evidence(rec)
    path = ev_dir / f"{name}.json"
    path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rec["_path"] = str(path.relative_to(run_dir))
    return rec["_path"]


def _key(run_dir: Path) -> bytes:
    return tdd.ensure_key(run_dir / "keys" / "verifier.key")


def _worker(toy: Path, red_rev: str, root: Path, tid: str, files: dict[str, str], claims: dict) -> dict:
    clone = root / tid
    _export_clone(toy, red_rev, clone)
    for path, text in files.items():
        write(clone / path, text)
    patch = run_git(clone, "diff", "--binary", red_rev).stdout
    return {"task_id": tid, "source_rev": red_rev, "patch": patch, "worker_claims": claims}


def _verify_green(toy: Path, contract: dict, sha: str, red: dict, manifest: dict, branch: str) -> tuple[dict, str]:
    """Independent verification + GREEN. Returns (green_record, implementation_rev)."""
    if manifest.get("source_rev") != red["revision"]:
        raise Rejected("stale_revision", "worker started from a different revision than the RED tests")
    paths = _changed_paths_from_patch(manifest["patch"])
    if not paths:
        raise Rejected("unrun", "empty patch: nothing to verify")
    touched_tests = sorted(p for p in paths if p in contract["scope"]["test_files"])
    if touched_tests:
        raise Rejected("tests_tampered", f"patch edits approved tests: {', '.join(touched_tests)}")
    outside = sorted(p for p in paths if p not in contract["scope"]["assigned_files"] or acdd.is_prohibited(p, contract))
    if outside:
        raise Rejected("scope_violation", f"patch touches files outside the contract lease: {', '.join(outside)}")
    tmp = Path(tempfile.mkdtemp(prefix="acdd-apply-"))
    try:
        clone = tmp / "repo"
        throwaway_checkout(toy, red["revision"], clone)
        for k, v in (("user.name", "Reference Verifier"), ("user.email", "verifier@example.invalid"), ("commit.gpgsign", "false")):
            run_git(clone, "config", k, v)
        pf = tmp / "change.patch"
        pf.write_text(manifest["patch"], encoding="utf-8")
        if run_git(clone, "apply", "--check", str(pf), check=False).returncode != 0:
            raise Rejected("stale_revision", "patch does not apply at the RED revision")
        run_git(clone, "apply", str(pf))
        run_git(clone, "add", "-A")
        run_git(clone, "commit", "-q", "-m", f"{manifest['task_id']} implementation")
        rev = run_git(clone, "rev-parse", "HEAD").stdout.strip()
        run_git(clone, "push", "-q", str(toy), f"HEAD:refs/heads/{branch}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rec = _run_phase(toy, rev, contract, sha, "green", contract["scope"]["test_files"])
    try:
        tdd.check_green(contract, sha, red, rec)
    except tdd.TddError as exc:
        raise Rejected(exc.code, exc.error) from exc
    return rec, rev


def run_acdd(run_dir: Path, *, force: bool = False) -> dict:
    run_dir = prepare_run_dir(Path(run_dir), force=force)
    toy = run_dir / "toy-shop"
    base = create_toy_repo(toy)
    for d in ("contracts", "packets", "workers", "evidence"):
        (run_dir / d).mkdir()
    metrics = MetricsLog(run_dir / "metrics.jsonl")
    metrics.emit("plan", source_rev=base, mode="acdd")

    # 1-2. Contracts and contract review: invalid contracts never reach a worker.
    drafts = [_pricing_contract("W1-pricing", base, "Add apply_tax to the pricing module"), _labels_contract(base),
              _pricing_contract("W3-out-of-scope", base, "Negative test: crosses its lease"),
              _pricing_contract("W4-weakened-tests", base, "Negative test: edits the approved tests")]
    invalid = _pricing_contract("W0-invalid", base, "Negative test: leases its own tests")
    invalid["scope"]["assigned_files"].append("tests/test_pricing.py")
    rejected_contracts, frozen = {}, {}
    for c in [invalid, *drafts]:
        path = run_dir / "contracts" / f"{c['id']}.contract.json"
        try:
            f = acdd.freeze_contract(c, approved_by="reference reviewer")
            acdd.check_frozen(f)
        except acdd.ContractError as exc:
            rejected_contracts[c["id"]] = exc.code
            path.write_text(json.dumps({"rejected": exc.code, "error": exc.error, "fix": exc.fix, "draft": c}, indent=2) + "\n", encoding="utf-8")
            metrics.emit("contract_rejected", task_id=c["id"], code=exc.code)
            continue
        frozen[f["id"]] = f
        path.write_text(json.dumps(f, indent=2) + "\n", encoding="utf-8")
        write_handoff(run_dir / "packets" / f"{f['id']}.HANDOFF.md", _handoff(f))
        metrics.emit("contract_frozen", task_id=f["id"], contract_sha256=f["review"]["contract_sha256"])

    # 3. Test-first preparation: approved tests only, RED against the baseline.
    reds, records = {}, {cid: [] for cid in frozen}
    for cid, c in frozen.items():
        sha = c["review"]["contract_sha256"]
        ev = run_dir / "evidence" / cid
        ev.mkdir()
        red_rev = _commit_tests(toy, base, c)
        red = _run_phase(toy, red_rev, c, sha, "red", c["scope"]["test_files"])
        tdd.check_red(c, sha, red)  # a broken RED stops the run: never dispatch on it
        _save(ev, "red", red, run_dir)
        reds[cid] = red
        records[cid].append(red)
        metrics.emit("red", task_id=cid, classification=red["classification"])

    # 4. Parallel workers (scripted). Leases exclude the approved tests.
    plans = {
        "W1-pricing": ({"shop/pricing.py": PRICING_WITH_TAX}, {"result": "implemented apply_tax"}),
        "W2-labels": ({"shop/labels.py": LABELS_WITH_RECEIPT}, {"result": "implemented format_receipt_line"}),
        "W3-out-of-scope": ({"shop/pricing.py": PRICING_WITH_TAX, "shop/labels.py": LABELS_WITH_RECEIPT},
                            {"result": "done", "assigned_files": ["shop/pricing.py", "shop/labels.py"]}),
        "W4-weakened-tests": ({"shop/pricing.py": BROKEN_PRICING, "tests/test_pricing.py": WEAKENED_TEST_PRICING},
                              {"result": "all tests pass"}),
    }
    accepted, rejected, final = [], {}, {}
    for cid, c in frozen.items():
        files, claims = plans[cid]
        manifest = _worker(toy, reds[cid]["revision"], run_dir / "workers", cid, files, claims)
        (run_dir / "evidence" / f"{cid}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        metrics.emit("worker_finished", task_id=cid, cost_units=1)
        sha = c["review"]["contract_sha256"]
        try:
            green, rev = _verify_green(toy, c, sha, reds[cid], manifest, f"acdd/green-{cid}")
        except Rejected as exc:
            rejected[cid] = exc.code
            (run_dir / "evidence" / cid / "rejected.json").write_text(json.dumps({"code": exc.code, "reason": exc.reason}, indent=2) + "\n", encoding="utf-8")
            metrics.emit("verified", task_id=cid, decision="rejected", code=exc.code)
            continue
        _save(run_dir / "evidence" / cid, "green", green, run_dir)
        records[cid].append(green)
        final[cid] = rev
        metrics.emit("verified", task_id=cid, decision="green")

    # 5. REFACTOR where the contract asks for it, with the same approved tests.
    if "W1-pricing" in final:
        c = frozen["W1-pricing"]
        sha = c["review"]["contract_sha256"]
        manifest = _worker(toy, final["W1-pricing"], run_dir / "workers", "W1-pricing-refactor", {"shop/pricing.py": PRICING_REFACTORED}, {"result": "refactored"})
        manifest["task_id"] = "W1-pricing-refactor"
        try:
            rev = _apply_checked(toy, c, final["W1-pricing"], manifest, "acdd/refactor-W1-pricing")
            ref = _run_phase(toy, rev, c, sha, "refactor", c["scope"]["test_files"], notes="extracted _require_non_negative; behaviour unchanged")
            tdd.check_refactor(c, sha, reds["W1-pricing"], records["W1-pricing"][-1], ref)
            _save(run_dir / "evidence" / "W1-pricing", "refactor", ref, run_dir)
            records["W1-pricing"].append(ref)
            final["W1-pricing"] = rev
        except (Rejected, tdd.TddError) as exc:
            rejected["W1-pricing-refactor"] = exc.code

    # 6. Integration: baseline + every approved test + every GREEN implementation.
    integration = _integrate(toy, base, frozen, reds, final)
    (run_dir / "evidence" / "integration.json").write_text(json.dumps({k: v for k, v in integration.items() if k != "result"}, indent=2) + "\n", encoding="utf-8")
    reports = {}
    for cid in final:
        c = frozen[cid]
        sha = c["review"]["contract_sha256"]
        rec = tdd.make_record(c, sha, phase="integration", revision=integration["integration_rev"], test_fingerprints=integration["fingerprints"][cid],
                              command=["python3", "-m", "unittest", "discover", "-s", "tests"], result=integration["result"], produced_by=VERIFIER, test_first=True)
        _save(run_dir / "evidence" / cid, "integration", rec, run_dir)
        records[cid].append(rec)

    # 7. REVIEW where the contract asks for it (scripted reviewer: teaching only;
    #    in production a named person records it with `hermes bundlebees tdd review`).
    for cid in final:
        c = frozen[cid]
        if "review" not in c["evidence_required"]:
            continue
        last = records[cid][-1]
        rec = tdd.make_record(c, c["review"]["contract_sha256"], phase="review", revision=final[cid],
                              test_fingerprints=last["test_fingerprints"], command=["review"], result=None,
                              produced_by={"role": "reviewer", "name": "scripted reviewer (teaching)"}, test_first=True,
                              notes="scripted approval: read the diff; apply_tax mirrors apply_discount", review_outcome="passed")
        _save(run_dir / "evidence" / cid, "review", rec, run_dir)
        records[cid].append(rec)
        metrics.emit("reviewed", task_id=cid, decision="approved", reviewer="scripted")

    key = _key(run_dir)
    for cid, c in frozen.items():
        rep = tdd.acceptance_report(c, c["review"]["contract_sha256"], records[cid], key=key)
        (run_dir / "evidence" / cid / "report.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        reports[cid] = rep
        if rep["accepted"]:
            accepted.append(cid)
    metrics.emit("integrated", passed=integration["passed"], applied=integration["applied"])
    _write_acceptance(run_dir, frozen, reports, rejected, rejected_contracts, records)

    ok = (sorted(accepted) == ["W1-pricing", "W2-labels"] and integration["passed"]
          and rejected.get("W3-out-of-scope") == "scope_violation" and rejected.get("W4-weakened-tests") == "tests_tampered"
          and rejected_contracts.get("W0-invalid") == "contract_invalid")
    result = {"ok": ok, "mode": "acdd", "run_dir": str(run_dir), "source_rev": base, "accepted": sorted(accepted), "rejected": rejected,
              "rejected_contracts": rejected_contracts,
              "integration": {k: integration[k] for k in ("passed", "applied", "integration_rev", "reason")},
              "reports": {k: {"accepted": v["accepted"], "phases": v["phases"], "test_first": v["test_first"]} for k, v in reports.items()},
              "acceptance_path": str(run_dir / "ACCEPTANCE.md"), "metrics_path": str(run_dir / "metrics.jsonl"),
              "evidence_signed": True, "sandbox": tdd.isolation_environment()["sandbox"]}
    (run_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _apply_checked(toy: Path, contract: dict, rev: str, manifest: dict, branch: str) -> str:
    """REFACTOR patches get the same lease and test-immutability checks as GREEN."""
    paths = _changed_paths_from_patch(manifest["patch"])
    if any(p in contract["scope"]["test_files"] for p in paths):
        raise Rejected("tests_tampered", "refactor edits approved tests")
    if any(p not in contract["scope"]["assigned_files"] for p in paths) or not paths:
        raise Rejected("scope_violation", "refactor touches files outside the lease")
    tmp = Path(tempfile.mkdtemp(prefix="acdd-refactor-"))
    try:
        clone = tmp / "repo"
        throwaway_checkout(toy, rev, clone)
        for k, v in (("user.name", "Reference Verifier"), ("user.email", "verifier@example.invalid"), ("commit.gpgsign", "false")):
            run_git(clone, "config", k, v)
        pf = tmp / "change.patch"
        pf.write_text(manifest["patch"], encoding="utf-8")
        run_git(clone, "apply", str(pf))
        run_git(clone, "add", "-A")
        run_git(clone, "commit", "-q", "-m", f"{manifest['task_id']}")
        new = run_git(clone, "rev-parse", "HEAD").stdout.strip()
        run_git(clone, "push", "-q", str(toy), f"HEAD:refs/heads/{branch}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return new


def _integrate(toy: Path, base: str, frozen: dict, reds: dict, final: dict) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="acdd-integrate-"))
    try:
        repo = tmp / "repo"
        throwaway_checkout(toy, base, repo)
        for k, v in (("user.name", "Reference Integrator"), ("user.email", "integrator@example.invalid"), ("commit.gpgsign", "false")):
            run_git(repo, "config", k, v)
        run_git(repo, "checkout", "-q", "-b", "integration")
        for cid in frozen:
            for f in frozen[cid]["scope"]["test_files"]:
                write(repo / f, TESTS[f])
        run_git(repo, "add", "-A")
        run_git(repo, "commit", "-q", "-m", "approved tests")
        applied = []
        for cid, rev in final.items():
            patch = run_git(toy, "diff", "--binary", reds[cid]["revision"], rev).stdout
            pf = tmp / f"{cid}.patch"
            pf.write_text(patch, encoding="utf-8")
            if run_git(repo, "apply", "--check", str(pf), check=False).returncode != 0:
                return {"passed": False, "reason": f"{cid} does not apply on the combined branch", "applied": applied,
                        "integration_rev": run_git(repo, "rev-parse", "HEAD").stdout.strip(), "result": None, "fingerprints": {}}
            run_git(repo, "apply", str(pf))
            run_git(repo, "add", "-A")
            run_git(repo, "commit", "-q", "-m", f"integrate {cid}")
            applied.append(cid)
        result = tdd.run_unittest(repo, sandbox=True)
        fps = {cid: tdd.fingerprint_files(repo, frozen[cid]["scope"]["test_files"]) for cid in final}
        passed = result["exit_code"] == 0 and not result["timed_out"]
        return {"passed": passed, "reason": "combined test suite passed" if passed else "combined test suite failed", "applied": applied,
                "integration_rev": run_git(repo, "rev-parse", "HEAD").stdout.strip(), "result": result, "fingerprints": fps}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _handoff(c: dict) -> dict:
    acc = "; ".join(f"{a['id']} " + (f"given {a['given']}, when {a['when']}, then {a['then']}" if "given" in a else a["statement"]) for a in c["acceptance_criteria"])
    return {
        "project_owner": "reference/toy-shop, orchestrator", "user_visible": c["outcome"]["summary"],
        "why": "Demonstrate a contract-first, test-first loop on a disposable example.", "acceptance": acc,
        "baseline": f"toy-shop @ {c['source_rev']}", "target": "integration branch in the throwaway run directory",
        "spec": f"contract {c['id']} sha256 {c['review']['contract_sha256']}", "inputs": "the toy-shop git repo created by this demo (no network)",
        "prior": "none", "direction": "Make the approved tests pass by editing only the leased files.", "superseded": "none",
        "authorized": "This reference demo is documentation; it does not authorize a production deploy.",
        "not_authorized": "editing approved tests, merge, tag, release, deploy, publish, network use",
        "assigned": ", ".join(c["scope"]["assigned_files"]) + " (approved tests read-only: " + ", ".join(c["scope"]["test_files"]) + ")",
        "budget": "offline, stdlib + git, scripted workers", "assumptions": "; ".join(c.get("assumptions", [])) or "none",
        "deliverable": "unified diff against the RED revision", "checks": "RED on baseline + tests only, GREEN, REFACTOR and REVIEW where required, integration",
        "invariants": "approved tests unchanged; files outside the lease untouched", "visual": "not applicable",
        "unavailable": "no model, no Orbit; scripted workers and reviewer; demo key in the run directory; sandbox only when bwrap is available (teaching)",
    }


def _write_acceptance(run_dir: Path, frozen: dict, reports: dict, rejected: dict, rejected_contracts: dict, records: dict) -> None:
    lines = ["# Acceptance report (reference demo)", "",
             "Every row links the verifier evidence that decided it. `not run` means the check never ran; it is never counted as passed.",
             "Human gates (merge, tag, release, deploy, publish) are outside this demo and were not exercised.", ""]
    for cid, c in frozen.items():
        rep = reports[cid]
        lines += [f"## {cid} — {c['title']}", "",
                  f"Contract sha256 `{c['review']['contract_sha256']}` · accepted: **{'yes' if rep['accepted'] else 'no'}** · test-first: {'yes' if rep['test_first'] else 'no'}", "",
                  "| Phase | Result | Evidence |", "|---|---|---|"]
        paths = {r["phase"]: r.get("_path") for r in records[cid]}
        for phase, state in rep["phases"].items():
            lines.append(f"| {phase} | {'not run' if state == 'unrun' else state} | {paths.get(phase) or '—'} |")
        lines += ["", "| Criterion | Check | Status | Evidence |", "|---|---|---|---|"]
        for a in c["acceptance_criteria"]:
            text = f"Given {a['given']}, when {a['when']}, then {a['then']}" if "given" in a else a["statement"]
            st = rep["criteria"][a["id"]]
            lines.append(f"| {a['id']} {text} | {a['verification']} | {st['status'].replace('_', ' ')} | {st['evidence'] or '—'} |")
        if cid in rejected:
            lines += ["", f"Rejected: `{rejected[cid]}` (see evidence/{cid}/rejected.json)."]
        lines.append("")
    if rejected_contracts:
        lines += ["## Contracts rejected at review", ""] + [f"- {k}: `{v}` (see contracts/{k}.contract.json)" for k, v in rejected_contracts.items()] + [""]
    (run_dir / "ACCEPTANCE.md").write_text("\n".join(lines), encoding="utf-8")
