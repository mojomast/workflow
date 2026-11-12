"""Read-only replay of bees.ps1 VerifyFor + ResultSummary, for sessions where PowerShell
script execution is blocked (single-query mode) and `bees.ps1 result <card>` cannot run.

Usage: python replay_verify.py <work_attempt_id> <verify_attempt_id>
Prints the same compact fields the script prints (claimed, patch_matches, scope, secret
hits, failed cmds, telemetry extras) plus lease_missing and VERDICT=pass|fail. Prints no
absolute paths, no tokens, no hosts.

The lease is coordinator-owned: it is only the work attempt record's
brief.assigned_files. The verify brief, the work result (in_assigned_scope flags or
patch paths) and the verify result never widen it. A missing lease fails closed.
"""
import json
import os
import sys

ATT = os.path.join(os.path.expanduser("~"), ".orbit-launcher", "attempts")

LEASE_MISSING_NOTE = "no coordinator lease: work brief assigned_files missing"


def load(name):
    p = os.path.join(ATT, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as fh:
        return json.load(fh)


def norm(p):
    return "" if not p else str(p).replace("\\", "/").lstrip("./")


def is_telemetry(p):
    n = norm(p)
    return n.startswith("shots/") or "/shots/" in n or n.endswith("PROGRESS.log")


def patch_map(res):
    m = {}
    if res and isinstance(res.get("patch"), dict):
        for f in res["patch"].get("files") or []:
            p = norm(f.get("path"))
            if p:
                m[p] = str(f.get("sha256"))
    return m


def truth(v):
    return v is True or str(v).lower() == "true"


def lease_from(work_attempt):
    """Return (lease, missing) using only the work attempt's brief.assigned_files.

    Directory entries ending in "/" cover paths below them. An absent or empty list
    means the coordinator lease is missing; callers must fail closed.
    """
    brief = (work_attempt or {}).get("brief") or {}
    assigned_files = brief.get("assigned_files")
    if isinstance(assigned_files, str):
        assigned_files = [assigned_files]
    assigned = []
    for p in assigned_files or []:
        n = norm(p)
        if n:
            assigned.append(n)
    lease = set(assigned)
    return lease, not lease


def _is_leased(path, lease):
    if path in lease:
        return True
    for entry in lease:
        if entry.endswith("/") and path.startswith(entry):
            return True
    return False


def _claimed(verify_result):
    claimed = (verify_result or {}).get("worker_claims") or {}
    claim = claimed.get("verdict")
    if not claim and claimed.get("checks"):
        claim = "pass" if all(truth(c.get("passed")) for c in claimed["checks"]) else "fail"
    return claim, claimed


def decide(work_attempt, verify_attempt, work_result, verify_result):
    """Pure decision for one worker/verifier pair. No I/O; never mutates inputs."""
    work_attempt = work_attempt or {}
    verify_attempt = verify_attempt or {}
    work_result = work_result or {}
    verify_result = verify_result or {}

    claim, claimed = _claimed(verify_result)
    wm, vm = patch_map(work_result), patch_map(verify_result)
    lease, lease_missing = lease_from(work_attempt)

    leased_files = [p for p in dict.fromkeys(list(wm) + list(vm)) if _is_leased(p, lease)]
    mismatch = sorted(p for p in leased_files if wm.get(p, "") != vm.get(p, ""))
    alld = list(dict.fromkeys(list(wm) + list(vm)))
    tel = sorted(p for p in alld if not _is_leased(p, lease) and is_telemetry(p))
    scope = sorted(p for p in alld if not _is_leased(p, lease) and not is_telemetry(p))

    cmds = claimed.get("commands") or [
        {"rc": 0 if truth(c.get("passed")) else 1} for c in (claimed.get("checks") or [])]
    failed = sum(1 for c in cmds if int(c.get("rc", 1)) != 0)
    ss = claimed.get("secret_scan")
    if isinstance(ss, dict) and ss.get("hits") is not None:
        secret_hits = len(ss["hits"])
    else:
        hits = [c for c in (claimed.get("checks") or [])
                if "secret" in str(c.get("name", "")).lower()
                and "scan" in str(c.get("name", "")).lower()]
        secret_hits = (0 if truth(hits[0].get("passed")) else 1) if hits else -1

    ok = (claim == "pass" and not lease_missing and not mismatch and not scope
          and failed == 0 and secret_hits == 0
          and verify_attempt.get("state") == "succeeded")
    return {
        "verdict": "pass" if ok else "fail",
        "lease_missing": lease_missing,
        "patch_matches": not mismatch,
        "mismatch": mismatch,
        "scope_violation": bool(scope),
        "scope_extras": scope,
        "telemetry_extras": tel,
        "failed_cmds": failed,
        "secret_hits": secret_hits,
        "claimed": claim,
        "lease": lease,
        "leased_files": sorted(leased_files),
        "cmds": cmds,
        "not_run": claimed.get("not_run"),
        "note": LEASE_MISSING_NOTE if lease_missing else "",
    }


def main(work_id, verify_id):
    watt = load(work_id + ".json") or {}
    wres = load(work_id + ".result.json") or {}
    vatt = load(verify_id + ".json") or {}
    vres = load(verify_id + ".result.json") or {}
    if not watt or not vatt:
        print("missing attempt record")
        return 2
    print("work_state=", watt.get("state"), "verify_state=", vatt.get("state"))
    print("verify_of=", (vatt.get("brief") or {}).get("verify_of"))

    d = decide(watt, vatt, wres, vres)
    print("claimed=", d["claimed"], "patch_matches=", d["patch_matches"],
          "mismatch=", d["mismatch"])
    print("scope_violation=", d["scope_violation"], "scope_extras=", d["scope_extras"])
    print("telemetry_extras=", d["telemetry_extras"])
    print("failed_cmds=", d["failed_cmds"], "secret_hits=", d["secret_hits"],
          "cmds=", len(d["cmds"]))
    print("leased_files=", d["leased_files"])
    print("lease_missing=", d["lease_missing"])
    if d["note"]:
        print("note=", d["note"])
    print("VERDICT=", d["verdict"])
    print("not_run=", d["not_run"])
    return 0 if d["verdict"] == "pass" else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: replay_verify.py <work_attempt_id> <verify_attempt_id>")
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
