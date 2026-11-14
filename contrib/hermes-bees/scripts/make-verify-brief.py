"""
Reference implementation only. This is Windows/Python reference code for one
host. Paths and host-specific values in a live checkout must be replaced with
local values. This tree includes no key files and is not an installer.
Not the PC launcher (that remains a private tree; see the parent README).
"""

"""make-verify-brief.py <work_attempt_id>: render the default verify-bee brief for a succeeded work bee.

Reads the work bee's brief and result from the launcher attempts dir, renders templates/verify.md with
templates/render_brief.py, writes verify-briefs/verify-<attempt>.json, and prints one line of JSON.
Report-only: dispatches nothing. The beekeeper passes the file's JSON to bundlebees_dispatch.
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATT = Path(os.environ.get("USERPROFILE") or Path.home()) / ".orbit-launcher" / "attempts"


def out(**kw):
    print(json.dumps(kw)); sys.exit(0 if kw.get("ok") else 2)


def main():
    args = [a for a in sys.argv[1:] if a]
    priority = None
    if "--priority" in args:
        i = args.index("--priority")
        if i + 1 >= len(args):
            out(ok=False, error="usage: make-verify-brief.py att_<hex> [--priority high]")
        priority = args[i + 1]
        del args[i:i + 2]
    if len(args) < 1 or not re.fullmatch(r"att_[0-9a-f]{8,32}", args[0]):
        out(ok=False, error="usage: make-verify-brief.py att_<hex> [--priority high]")
    aid = args[0]
    try:
        a = json.loads((ATT / f"{aid}.json").read_text(encoding="utf-8"))
    except Exception:
        out(ok=False, error="work attempt not found")
    b = a.get("brief") or {}
    if b.get("role") == "verify" or b.get("verify_of"):
        out(ok=False, error="attempt is itself a verify bee")
    if a.get("state") != "succeeded":
        out(ok=False, error=f"work attempt state is {a.get('state')}, not succeeded")
    try:
        r = json.loads((ATT / f"{aid}.result.json").read_text(encoding="utf-8"))
    except Exception:
        out(ok=False, error="work attempt has no result")
    if not ((r.get("patch") or {}).get("diff") or "").strip():
        out(ok=False, error="work attempt produced no patch; nothing to verify")
    if not b.get("source_rev") or not b.get("assigned_files"):
        out(ok=False, error="work brief lacks source_rev or assigned_files")
    acc = b.get("acceptance")
    if isinstance(acc, dict):
        b["acceptance"] = list(acc.get("criteria") or [])
        b.setdefault("commands", list(acc.get("commands") or []) + [f"python3 -m pytest -q {t}" for t in acc.get("tests") or []])
    b.setdefault("task_id", b.get("kanban_task_id") or b.get("label") or aid)
    def _py3(cmds):
        out = []
        for c in cmds or []:
            if isinstance(c, str):
                c = re.sub(r"(^|(?<=[\s;&|]))python(?=\s)", "python3", c)
            out.append(c)
        return out
    if b.get("commands"):
        b["commands"] = _py3(b["commands"])
    observed = (r.get("observed") or {}) if isinstance(r.get("observed"), dict) else {}
    local_base = observed.get("local_base_rev") or r.get("local_base_rev") or a.get("local_base_rev") or b.get("source_rev")
    dest = HERE / "verify-briefs"; dest.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wb = Path(td) / "work.json"; wb.write_text(json.dumps(b), encoding="utf-8")
        vals = Path(td) / "vals.json"; vals.write_text(json.dumps({"work_brief": str(wb), "verify_of": aid, "local_base_rev": local_base, "bbs_test_token": False}), encoding="utf-8")
        target = dest / f"verify-{aid}.json"
        p = subprocess.run([sys.executable, str(HERE / "templates" / "render_brief.py"), str(HERE / "templates" / "verify.md"), str(vals), "--out", str(target)],
                           capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        out(ok=False, error=(p.stderr or p.stdout).strip().splitlines()[-1][:200] if (p.stderr or p.stdout).strip() else "render failed")
    vb = json.loads(target.read_text(encoding="utf-8"))
    if priority:
        vb["priority"] = priority
        target.write_text(json.dumps(vb, indent=2), encoding="utf-8")
    out(ok=True, brief_file=f"verify-briefs/verify-{aid}.json", verify_of=aid, project=vb.get("project"), commands=len(vb.get("commands") or []), bytes=target.stat().st_size, priority=vb.get("priority"))


if __name__ == "__main__":
    main()
