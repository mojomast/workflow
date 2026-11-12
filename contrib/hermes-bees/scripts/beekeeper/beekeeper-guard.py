"""Beekeeper pre_tool_call guard.

Blocks risky git, gh, deploy, delete and launcher-control commands, and mid-run
kanban parks (needs_input / schedule while a bee is in flight or waiting for
verify). This is a coordinator-side allowlist, not a prompt. Matches both the
shell tools and the kanban_block / kanban_schedule tools.

Stdlib only. Fail-closed on an unreadable payload. Never prints secrets or paths.
"""
from __future__ import annotations

import json, os, re, sys
from pathlib import Path

RULES = [
    (r"\bgit\s+push\b", "git push"),
    (r"\bgit\s+pull\b", "git pull"),
    (r"\bgh\s+pr\b", "gh pr"),
    (r"\bgit\s+merge\b", "git merge"),
    (r"\bgit\s+rebase\b", "git rebase"),
    (r"\bgit\s+commit\b", "git commit"),
    (r"\bgit\s+tag\b", "git tag"),
    (r"\bgit\s+remote\b", "git remote"),
    (r"\bgit\s+filter-(repo|branch)\b", "git history rewrite"),
    (r"\bgit\s+reset\b", "git reset"),
    (r"\bgit\s+checkout\s+(-b\s+)?(main|master|hermes/v0|hermes/art)\b", "checkout protected branch"),
    (r"\bgit\s+switch\b", "git switch"),
    (r"deploy-0", "deploy script"),
    (r"orbit-launcher\.nssm", "launcher service"),
    (r"restart-orbit-launcher", "launcher restart"),
    (r"Stop-Service|Restart-Service|nssm\s+(stop|restart|remove)", "service control"),
    (r"\brm\s+-rf\b|\bRemove-Item\b.*-Recurse|\brmdir\b", "recursive delete"),
    (r"Stop-Process|taskkill", "process kill"),
]

WAIT_RE = re.compile(
    r"waiting on (the )?(dispatched )?bee|no human action needed|"
    r"while (the|a) bee|bee is (still )?(running|in flight)|"
    r"waiting for (the )?verify|in flight",
    re.I,
)
ALLOW_PARK_RE = re.compile(
    r"stuck|SUSPECT_STUCK|LOW_DISK|verify fail|failed|cancelled|"
    r"secret_hits|scope_violation|patch_matches",
    re.I,
)
TERMINAL = {"succeeded", "failed", "cancelled"}
AID = re.compile(r"^att_[0-9a-f]{8,32}$")


def _home():
    return Path(os.environ.get("USERPROFILE") or Path.home())


def _att_dir():
    return Path(os.environ.get("BEES_ATT_DIR") or (_home() / ".orbit-launcher" / "attempts"))


def _owned_file():
    return Path(os.environ.get("BEES_OWNED_FILE") or (_home() / ".orbit-launcher" / "hermes-bees" / "owned-cards.json"))


def owned_task_ids():
    try:
        data = json.loads(_owned_file().read_text(encoding="utf-8"))
    except Exception:
        return set()
    ids = data.get("task_ids") if isinstance(data, dict) else data
    return {str(x) for x in (ids or []) if x}


def _brief_task_id(brief):
    b = brief or {}
    return str(b.get("task_id") or b.get("work_task_id") or b.get("kanban_task_id") or "")


def owned_gap():
    """True if an owned bee is non-terminal, or work succeeded with no verify yet."""
    att = _att_dir()
    if not att.exists():
        return False
    tasks = owned_task_ids()
    rows = []
    for p in att.glob("att_*.json"):
        if not AID.match(p.stem):
            continue
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(a, dict):
            a.setdefault("attempt_id", p.stem)
            rows.append(a)
    owned_work = set()
    for a in rows:
        b = a.get("brief") or {}
        if b.get("verify_of") or b.get("role") == "verify":
            continue
        if _brief_task_id(b) in tasks or (not tasks and False):
            owned_work.add(a.get("attempt_id"))
    verify_of = {}
    for a in rows:
        vof = (a.get("brief") or {}).get("verify_of")
        if vof:
            verify_of.setdefault(vof, []).append(a)
    for a in rows:
        aid = a.get("attempt_id")
        b = a.get("brief") or {}
        tid = _brief_task_id(b)
        is_verify = bool(b.get("verify_of") or b.get("role") == "verify")
        interesting = (tid in tasks) or (aid in owned_work) or ((b.get("verify_of") or "") in owned_work)
        if not interesting:
            continue
        st = a.get("state") or ""
        if st not in TERMINAL:
            return True
        if (not is_verify) and st == "succeeded" and not verify_of.get(aid):
            return True
    return False


def _tool_name(data):
    return str(data.get("tool_name") or data.get("tool") or data.get("name") or "").lower()


def _tool_text(data):
    ti = data.get("tool_input") or data.get("args") or data.get("input") or {}
    parts = []
    reason = kind = ""
    if isinstance(ti, dict):
        reason = str(ti.get("reason") or ti.get("message") or ti.get("comment") or "")
        kind = str(ti.get("kind") or ti.get("block_kind") or "")
        for k in ("command", "code", "cmd", "input", "script", "args", "reason", "message"):
            v = ti.get(k)
            if v:
                parts.append(v if isinstance(v, str) else json.dumps(v))
        if not parts:
            parts.append(json.dumps(ti))
    else:
        parts.append(str(ti))
    return "\n".join(parts), reason, kind


def park_decision(data, gap=None):
    """Return a block message if this is a mid-run park, else None.

    Allow stuck/fail reports. Deny waiting-for-bee parks, especially when an
    owned bee is in flight or work succeeded and verify has not been dispatched.
    """
    name = _tool_name(data)
    text, reason, kind = _tool_text(data)
    blob = " ".join([name, text, reason, kind])
    is_block_tool = name in {"kanban_block", "kanban_schedule"}
    is_block_cli = bool(re.search(r"\b(hermes\s+(-p\s+\S+\s+)?)?kanban\s+(block|schedule)\b", text, re.I))
    if not (is_block_tool or is_block_cli):
        return None
    if ALLOW_PARK_RE.search(reason) or ALLOW_PARK_RE.search(text):
        return None
    waiting = bool(WAIT_RE.search(reason) or WAIT_RE.search(text) or kind == "needs_input")
    if gap is None:
        gap = owned_gap()
    if gap or waiting:
        return (
            "Blocked by beekeeper-guard: do not park this card as needs_input "
            "while a bee is in flight or waiting for verify. End your turn without "
            "kanban_block; bee-watch will wake you. Report stuck or verify-fail "
            "explicitly if that is the case."
        )
    return None


def decide(data):
    msg = park_decision(data)
    if msg:
        return {"action": "block", "message": msg}
    ti_text, _, _ = _tool_text(data)
    low = ti_text.lower()
    for pat, why in RULES:
        if re.search(pat, low if pat == pat.lower() else ti_text, re.IGNORECASE):
            return {
                "action": "block",
                "message": (
                    f"Blocked by beekeeper house rules ({why}). Kyle runs this himself, "
                    "or the box coordinator does it after a secret scan. Report on the card instead."
                ),
            }
    return {}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"action": "block", "message": "beekeeper-guard: unreadable hook payload"}))
        return
    print(json.dumps(decide(data)))


if __name__ == "__main__":
    main()
