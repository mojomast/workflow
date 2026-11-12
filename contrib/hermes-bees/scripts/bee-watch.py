"""
Reference implementation only. This is Windows/Python reference code for one
host. Paths and host-specific values in a live checkout must be replaced with
local values. This tree includes no key files and is not an installer.
Not the PC launcher (that remains a private tree; see the parent README).
"""

"""bee-watch.py: Hermes cron pre-check for the beekeeper (stdlib only, zero tokens when idle).

Reads launcher attempt files on disk (works with launcher 0.1.10 and 0.1.11), never calls the
network, never cancels or restarts anything. Prints {"wakeAgent": false} unless an attempt that
the beekeeper dispatched (has a bundlebees lease) went terminal or looks stuck, or C: drops
under 10 GB (latched). Output is under 1 KB, with no paths, hosts or tokens.
"""
import json, os, re, shutil, sys, time
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE") or Path.home())
ATT = HOME / ".orbit-launcher" / "attempts"
HH = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local"))) / "hermes"
MEMO = HH / "scripts" / "bee-watch.state.json"
TERMINAL = {"succeeded", "failed", "cancelled"}
STUCK_MIN = float(os.environ.get("BEE_WATCH_STUCK_MIN", "20"))
TOOL_MAX_MIN = float(os.environ.get("BEE_WATCH_TOOL_MAX_MIN", "45"))
WATCH_ALL = os.environ.get("BEE_WATCH_ALL") == "1"
ID = re.compile(r"^att_[0-9a-f]{8,32}$")


def leased_ids():
    out = set()
    for base in [HH / "profiles" / "beekeeper", HH]:
        for d in base.glob("**/bundlebees/leases"):
            out |= {p.stem for p in d.glob("att_*.json")}
        if out:
            break
    return out


def last_tool_in_progress(ev_path):
    try:
        with ev_path.open("rb") as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 20000))
            tail = f.read().decode("utf-8", "replace")
        i, c = tail.rfind("in_progress"), tail.rfind("completed")
        return i > c
    except OSError:
        return False


def main():
    now = time.time()
    try:
        memo = json.loads(MEMO.read_text())
    except Exception:
        memo = {}
    seen = memo.get("attempts", {})
    owned = leased_ids()
    events, running = [], 0
    for p in ATT.glob("att_*.json") if ATT.exists() else []:
        aid = p.stem
        if not ID.match(aid) or now - p.stat().st_mtime > 2 * 86400:
            continue
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        st = a.get("state", "?")
        prev = seen.get(aid, {})
        interesting = WATCH_ALL or aid in owned
        rec = {"state": st, "stuck": False}
        if st not in TERMINAL:
            running += 1
            ev = ATT / f"{aid}.events.jsonl"
            age = (now - (ev.stat().st_mtime if ev.exists() else p.stat().st_mtime)) / 60
            limit = TOOL_MAX_MIN if last_tool_in_progress(ev) else STUCK_MIN
            if st == "running" and age > limit:
                rec["stuck"] = True
                if interesting and not prev.get("stuck"):
                    events.append({"attempt": aid, "state": st, "why": "SUSPECT_STUCK", "quiet_min": round(age)})
        elif interesting and prev and prev.get("state") not in TERMINAL:
            brief = a.get("brief") or {}
            ev = {"attempt": aid, "state": st, "why": "TERMINAL", "task_id": str(brief.get("task_id") or brief.get("work_task_id") or "")[:40]}
            if brief.get("verify_of"):
                ev.update(role="verify", verify_of=str(brief["verify_of"])[:40])
            events.append(ev)
        seen[aid] = rec
    seen = {k: v for k, v in seen.items() if (ATT / f"{k}.json").exists()}
    free_gb = round(shutil.disk_usage(str(HOME.anchor or "C:\\")).free / 2**30, 1)
    low = free_gb < 10
    if low and not memo.get("low_disk"):
        events.append({"why": "LOW_DISK", "c_free_gb": free_gb})
    MEMO.parent.mkdir(parents=True, exist_ok=True)
    MEMO.write_text(json.dumps({"attempts": seen, "low_disk": low, "at": int(now)}))
    if not events:
        print(json.dumps({"wakeAgent": False}))
        return
    msg = {"wakeAgent": True, "running": running, "events": events[:6],
           "todo": "Work bee succeeded: run make-verify-brief.py <attempt> and dispatch that verify bee; never kanban_block to wait. Verify bee finished: run bees.ps1 result <card> (it settles: pass -> unblock if needed then request-review, fail -> blocked). Work bee failed, SUSPECT_STUCK, LOW_DISK: report-only, comment and block. Never cancel, re-dispatch, push or restart."}
    s = json.dumps(msg)
    while len(s) > 1000 and msg["events"]:
        msg["events"].pop(); s = json.dumps(msg)
    print(s)


if __name__ == "__main__":
    main()
