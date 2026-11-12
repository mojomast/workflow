"""Read-only replay of bees.ps1 VerifyFor + ResultSummary, for sessions where PowerShell
script execution is blocked (single-query mode) and `bees.ps1 result <card>` cannot run.

Usage: python replay_verify.py <work_attempt_id> <verify_attempt_id>
Prints the same compact fields the script prints (claimed, patch_matches, scope, secret
hits, failed cmds, telemetry extras) plus VERDICT=pass|fail. Prints no absolute paths,
no tokens, no hosts.
"""
import json
import os
import sys

ATT = os.path.join(os.path.expanduser("~"), ".orbit-launcher", "attempts")


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

    claimed = vres.get("worker_claims") or {}
    claim = claimed.get("verdict")
    if not claim and claimed.get("checks"):
        claim = "pass" if all(truth(c.get("passed")) for c in claimed["checks"]) else "fail"

    wm, vm = patch_map(wres), patch_map(vres)
    assigned = [norm(p) for p in ((watt.get("brief") or {}).get("assigned_files") or []) if norm(p)]
    lease = set(assigned) or set(wm)
    if assigned:
        for f in (wres.get("patch") or {}).get("files") or []:
            p = norm(f.get("path"))
            if p and (p in lease or truth(f.get("in_assigned_scope"))):
                lease.add(p)
    mismatch = [p for p in lease
                if (p in wm or p in vm) and (wm.get(p, "") != vm.get(p, ""))]
    alld = list(dict.fromkeys(list(wm) + list(vm)))
    tel = sorted(p for p in alld if p not in lease and is_telemetry(p))
    scope = sorted(p for p in alld if p not in lease and not is_telemetry(p))

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

    ok = (claim == "pass" and not mismatch and not scope and failed == 0 and secret_hits == 0
          and vatt.get("state") == "succeeded")
    print("claimed=", claim, "patch_matches=", not mismatch, "mismatch=", mismatch)
    print("scope_violation=", bool(scope), "scope_extras=", scope)
    print("telemetry_extras=", tel)
    print("failed_cmds=", failed, "secret_hits=", secret_hits, "cmds=", len(cmds))
    print("leased_files=", sorted(lease))
    print("VERDICT=", "pass" if ok else "fail")
    print("not_run=", claimed.get("not_run"))
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: replay_verify.py <work_attempt_id> <verify_attempt_id>")
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
