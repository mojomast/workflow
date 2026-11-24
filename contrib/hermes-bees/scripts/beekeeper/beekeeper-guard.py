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


def _load_rows(att):
    """(attempt records, unreadable): unreadable is True if any attempt file
    could not be read or parsed."""
    rows, unreadable = [], False
    for p in att.glob("att_*.json"):
        if not AID.match(p.stem):
            continue
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable = True
            continue
        if isinstance(a, dict):
            a.setdefault("attempt_id", p.stem)
            rows.append(a)
    return rows, unreadable


def _is_verify(brief):
    return bool(brief.get("verify_of") or brief.get("role") == "verify")


def _verify_index(rows):
    index = {}
    for a in rows:
        vof = (a.get("brief") or {}).get("verify_of")
        if vof:
            index.setdefault(vof, []).append(a)
    return index


def _has_gap(a, tasks, owned_work, verify_of):
    """True if this owned attempt is in flight or is succeeded work without a verify."""
    b = a.get("brief") or {}
    aid = a.get("attempt_id")
    if not (_brief_task_id(b) in tasks or aid in owned_work or (b.get("verify_of") or "") in owned_work):
        return False
    st = a.get("state") or ""
    if st not in TERMINAL:
        return True
    return not _is_verify(b) and st == "succeeded" and not verify_of.get(aid)


def owned_gap():
    """True if an owned bee is non-terminal, or work succeeded with no verify yet.

    Fail-closed: an unreadable attempt file counts as a gap, because the guard
    can no longer prove that nothing is in flight.
    """
    att = _att_dir()
    if not att.exists():
        return False
    rows, unreadable = _load_rows(att)
    if unreadable:
        return True
    tasks = owned_task_ids()
    owned_work = {a.get("attempt_id") for a in rows
                  if not _is_verify(a.get("brief") or {}) and _brief_task_id(a.get("brief")) in tasks}
    verify_of = _verify_index(rows)
    return any(_has_gap(a, tasks, owned_work, verify_of) for a in rows)


def _tool_name(data):
    return str(data.get("tool_name") or data.get("tool") or data.get("name") or "").lower()


_TEXT_KEYS = ("command", "code", "cmd", "input", "script", "args", "reason", "message")


def _first(ti, *keys):
    return str(next((ti.get(k) for k in keys if ti.get(k)), "") or "")


def _tool_text(data):
    """(text to match, reason, kind) from the tool input."""
    ti = data.get("tool_input") or data.get("args") or data.get("input") or {}
    if not isinstance(ti, dict):
        return str(ti), "", ""
    reason = _first(ti, "reason", "message", "comment")
    kind = _first(ti, "kind", "block_kind")
    parts = [v if isinstance(v, str) else json.dumps(v) for v in (ti.get(k) for k in _TEXT_KEYS) if v]
    return "\n".join(parts or [json.dumps(ti)]), reason, kind


_BLOCK_CLI_RE = re.compile(r"\b(hermes\s+(-p\s+\S+\s+)?)?kanban\s+(block|schedule)\b", re.I)


def _is_park(name, text):
    return name in {"kanban_block", "kanban_schedule"} or bool(_BLOCK_CLI_RE.search(text))


def _is_waiting(reason, text, kind):
    return bool(WAIT_RE.search(reason) or WAIT_RE.search(text) or kind == "needs_input")


def park_decision(data, gap=None):
    """Return a block message if this is a mid-run park, else None.

    Allow stuck/fail reports. Deny waiting-for-bee parks, especially when an
    owned bee is in flight or work succeeded and verify has not been dispatched.
    """
    name = _tool_name(data)
    text, reason, kind = _tool_text(data)
    if not _is_park(name, text):
        return None
    if ALLOW_PARK_RE.search(reason) or ALLOW_PARK_RE.search(text):
        return None
    waiting = _is_waiting(reason, text, kind)
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
