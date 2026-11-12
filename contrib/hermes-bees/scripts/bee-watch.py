"""bee-watch.py: Hermes cron pre-check for the beekeeper (stdlib only, zero tokens when idle).

Level-triggered reconcile (Kubernetes-controller style): compare desired vs actual
state every tick. A short bee that finished between ticks still wakes us, because
we do not require having seen a non-terminal edge. Events only hint; the ticker
is the backstop.

Ownership is explicit (handoff-written owned-cards.json + bundlebees leases).
Unowned attempts (including other operators) are ignored.

Output is under 1 KB, with no paths, hosts or tokens. Never cancels or restarts
anything; never dispatches a bee itself (the beekeeper does, idempotently).
"""
from __future__ import annotations

import json, os, re, shutil, sys, time
from pathlib import Path

HOME = Path(os.environ.get("BEE_WATCH_HOME") or os.environ.get("USERPROFILE") or Path.home())
ATT = Path(os.environ.get("BEE_WATCH_ATT") or (HOME / ".orbit-launcher" / "attempts"))
OWNED = Path(os.environ.get("BEE_WATCH_OWNED") or (HOME / ".orbit-launcher" / "hermes-bees" / "owned-cards.json"))
HH = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local"))) / "hermes"
MEMO = Path(os.environ.get("BEE_WATCH_MEMO") or (HH / "scripts" / "bee-watch.state.json"))
TERMINAL = {"succeeded", "failed", "cancelled"}
STUCK_MIN = float(os.environ.get("BEE_WATCH_STUCK_MIN", "20"))
TOOL_MAX_MIN = float(os.environ.get("BEE_WATCH_TOOL_MAX_MIN", "45"))
WAKE_COOLDOWN_S = float(os.environ.get("BEE_WATCH_WAKE_COOLDOWN_S", "90"))
ID = re.compile(r"^att_[0-9a-f]{8,32}$")


def leased_ids():
    out = set()
    for base in [HH / "profiles" / "beekeeper", HH]:
        for d in base.glob("**/bundlebees/leases"):
            out |= {p.stem for p in d.glob("att_*.json")}
        if out:
            break
    return out


def owned_task_ids():
    try:
        data = json.loads(OWNED.read_text(encoding="utf-8-sig"))
    except Exception:
        return set()
    ids = data.get("task_ids") if isinstance(data, dict) else data
    return {str(x) for x in (ids or []) if x}


def brief_task_id(brief):
    b = brief or {}
    return str(b.get("task_id") or b.get("work_task_id") or b.get("kanban_task_id") or "")


def last_tool_in_progress(ev_path):
    try:
        with ev_path.open("rb") as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - 20000))
            tail = f.read().decode("utf-8", "replace")
        i, c = tail.rfind("in_progress"), tail.rfind("completed")
        return i > c
    except OSError:
        return False


def load_attempts(now):
    rows = []
    if not ATT.exists():
        return rows
    for p in ATT.glob("att_*.json"):
        aid = p.stem
        if not ID.match(aid) or now - p.stat().st_mtime > 2 * 86400:
            continue
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(a, dict):
            continue
        a.setdefault("attempt_id", aid)
        rows.append(a)
    return rows


def is_owned(a, leased, tasks, owned_work):
    aid = a.get("attempt_id")
    if aid in leased or aid in owned_work:
        return True
    b = a.get("brief") or {}
    tid = brief_task_id(b)
    if tid and tid in tasks:
        return True
    vof = b.get("verify_of")
    if vof and vof in owned_work:
        return True
    return False



def is_stuck(a, now):
    aid = a.get("attempt_id")
    evp = ATT / f"{aid}.events.jsonl"
    ap = ATT / f"{aid}.json"
    if evp.exists():
        mtime = evp.stat().st_mtime
    elif ap.exists():
        mtime = ap.stat().st_mtime
    else:
        mtime = now
    age = (now - mtime) / 60
    limit = TOOL_MAX_MIN if last_tool_in_progress(evp) else STUCK_MIN
    return (a.get("state") == "running") and age > limit


def reconcile(rows, leased, tasks, now, memo, stuck_fn=None):
    """Return (events, running, seen). Pure; does not write the memo."""
    wakes = dict(memo.get("wakes") or {})
    seen_prev = memo.get("attempts") or {}
    owned_work = set()
    for a in rows:
        b = a.get("brief") or {}
        if not (b.get("role") == "verify" or b.get("verify_of")):
            tid = brief_task_id(b)
            if a.get("attempt_id") in leased or (tid and tid in tasks):
                owned_work.add(a.get("attempt_id"))

    verify_of = {}
    for a in rows:
        b = a.get("brief") or {}
        vof = b.get("verify_of")
        if vof:
            verify_of.setdefault(vof, []).append(a)

    events, running, seen = [], 0, {}
    for a in rows:
        aid = a.get("attempt_id")
        st = a.get("state") or "?"
        b = a.get("brief") or {}
        interesting = is_owned(a, leased, tasks, owned_work)
        rec = {"state": st, "stuck": False}
        is_verify = bool(b.get("verify_of") or b.get("role") == "verify")

        if st not in TERMINAL:
            running += 1
            if stuck_fn:
                stuck = stuck_fn(a)
            else:
                stuck = is_stuck(a, now)
            rec["stuck"] = bool(stuck)
            if interesting and rec["stuck"]:
                _maybe_wake(events, wakes, now, aid, "SUSPECT_STUCK",
                            {"attempt": aid, "state": st, "why": "SUSPECT_STUCK"})
        elif interesting:
            if is_verify:
                ev = {"attempt": aid, "state": st, "why": "VERIFY_TERMINAL",
                      "verify_of": str(b.get("verify_of") or "")[:40]}
                _maybe_wake(events, wakes, now, aid, "VERIFY_TERMINAL", ev)
            else:
                kids = verify_of.get(aid) or []
                if st == "succeeded" and not kids:
                    ev = {"attempt": aid, "state": st, "why": "WORK_NEEDS_VERIFY",
                          "task_id": brief_task_id(b)[:40]}
                    _maybe_wake(events, wakes, now, aid, "WORK_NEEDS_VERIFY", ev)
                elif st in ("failed", "cancelled"):
                    ev = {"attempt": aid, "state": st, "why": "WORK_TERMINAL",
                          "task_id": brief_task_id(b)[:40]}
                    _maybe_wake(events, wakes, now, aid, "WORK_TERMINAL", ev)
        seen[aid] = rec
    return events, running, seen, wakes


def _maybe_wake(events, wakes, now, aid, why, ev):
    key = f"{aid}:{why}"
    last = float(wakes.get(key) or 0)
    if last and (now - last) < WAKE_COOLDOWN_S:
        return
    wakes[key] = now
    events.append(ev)


def main():
    now = time.time()
    try:
        memo = json.loads(MEMO.read_text())
    except Exception:
        memo = {}
    leased = leased_ids()
    tasks = owned_task_ids()
    rows = load_attempts(now)
    events, running, seen, wakes = reconcile(rows, leased, tasks, now, memo)
    seen = {k: v for k, v in seen.items() if (ATT / f"{k}.json").exists()}
    free_gb = round(shutil.disk_usage(str(HOME.anchor or "C:\\")).free / 2**30, 1)
    low = free_gb < 10
    if low and not memo.get("low_disk"):
        events.append({"why": "LOW_DISK", "c_free_gb": free_gb})
    MEMO.parent.mkdir(parents=True, exist_ok=True)
    MEMO.write_text(json.dumps({"attempts": seen, "wakes": wakes, "low_disk": low, "at": int(now)}))
    if not events:
        print(json.dumps({"wakeAgent": False}))
        return
    msg = {
        "wakeAgent": True,
        "running": running,
        "events": events[:6],
        "todo": (
            "WORK_NEEDS_VERIFY: run make-verify-brief.py <attempt> [--priority from brief.verify_priority] "
            "and dispatch only if no verify_of attempt exists (idempotent). "
            "VERIFY_TERMINAL: run bees.ps1 result <card> (settles). "
            "WORK_TERMINAL / SUSPECT_STUCK / LOW_DISK: report-only, comment; do not kanban_block to wait. "
            "Never cancel, re-dispatch, push or restart."
        ),
    }
    s = json.dumps(msg)
    while len(s) > 1000 and msg["events"]:
        msg["events"].pop()
        s = json.dumps(msg)
    print(s)


if __name__ == "__main__":
    main()
