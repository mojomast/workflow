#!/usr/bin/env python3
"""
Reference implementation only. This is Windows/Python reference code for one
host. Paths and host-specific values in a live checkout must be replaced with
local values. This tree includes no key files and is not an installer.
Not the PC launcher (that remains a private tree; see the parent README).
"""

"""Render a brief template into briefs/<TASK_ID>.json.

  python3 templates/render_brief.py templates/guest-fix.md values.json [--out briefs/TOH-X.json]

values.json supplies the {{slots}}; list/obj values are inserted as JSON.
Fails if any {{slot}} is left unfilled. Never put secrets in values.json.
"bbs_test_token": true|false in values.json controls the launcher-injected BBS test token.
"""
import json, re, sys
from pathlib import Path
T = Path(__file__).resolve().parent

def as_python3(cmds):
    """Rewrite a `python` command to `python3` without touching python3 already."""
    if not isinstance(cmds, list):
        return cmds
    out = []
    for c in cmds:
        if isinstance(c, str):
            c = re.sub(r"(^|(?<=[\s;&|]))python(?=\s)", "python3", c)
        out.append(c)
    return out

tpl, vals = Path(sys.argv[1]).read_text(), json.loads(Path(sys.argv[2]).read_text())
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
if Path(sys.argv[1]).name == "verify.md":
    # Verify bee: derive slots from the finished work bee's rendered brief.
    wb = json.loads(Path(vals["work_brief"]).read_text()) if vals.get("work_brief") else {}
    acc = wb.get("acceptance") or []
    if isinstance(acc, dict): acc = list(acc.get("criteria") or []) + list(acc.get("commands") or [])
    cmds = wb.get("commands") or (acc_raw.get("commands") if isinstance(acc_raw := wb.get("acceptance"), dict) else None) or []
    cmds = as_python3(list(cmds))
    wid = wb.get("task_id") or wb.get("label") or wb.get("title") or "work"
    for k, v in {"repo_project": wb.get("project"), "branch": wb.get("branch"), "source_rev": wb.get("source_rev"),
                 "local_base_rev": vals.get("local_base_rev") or wb.get("local_base_rev") or wb.get("source_rev"),
                 "assigned_files": wb.get("assigned_files"), "work_commands": cmds, "work_task_id": wid,
                 "work_acceptance": "\n".join(f"- {a}" for a in acc) or "- (none listed)",
                 "task_id": f"verify-{wid}", "label": f"verify-{wb.get('label') or wid}", "title": f"Verify {wid}"}.items():
        if v is not None: vals.setdefault(k, v)
    vals.setdefault("timeout_s", 2700)
    vals.setdefault("local_base_rev", vals.get("source_rev") or "seeded-tree")
    if vals.get("branch") in ("main", "master"): sys.exit("verify: work branch must be a feature branch")
    if not re.fullmatch(r"att_[0-9a-f]{8,32}", str(vals.get("verify_of", ""))): sys.exit("verify: verify_of must be an attempt id")
vals.setdefault("timeout_s", 10800)
if "source_branch" in vals: vals.setdefault("branch", vals["source_branch"])
vals.setdefault("progress_file", f"shots/{vals.get('label', 'task')}/PROGRESS.log")
body = re.search(r"```json\n(.*?)\n```", tpl, re.S).group(1)
rules = (T / "_house-rules.md").read_text().split("-->", 1)[-1].strip()
body = body.replace("{{> _house-rules.md}}", json.dumps(rules)[1:-1])
def sub(m):
    k = m.group(1); v = vals.get(k)
    if v is None: return m.group(0)
    if isinstance(v, (list, dict)): return json.dumps(v)
    if isinstance(v, int): return str(v)
    return json.dumps(str(v))[1:-1]
for _ in range(3):
    body = re.sub(r"\{\{(\w+)\}\}", sub, body)
left = sorted(set(re.findall(r"\{\{(\w+)\}\}", body)))
if left: sys.exit(f"unfilled slots: {left}")
brief = json.loads(body)
brief["acceptance"] = [a for a in brief["acceptance"] if a.strip()]
# Opt-in: the PC launcher (>= 0.1.10) mints a ~15-min toh-beetest-agent token via
# %USERPROFILE%\.orbit-launcher\bbs-beetest\mint-token.ps1 and puts it at $TOH_BBS_TEST_TOKEN_FILE.
# Default on for guest-fix / plugin-fix (real-setup tests); set "bbs_test_token": false to skip.
_tok = vals.get("bbs_test_token", Path(sys.argv[1]).name in ("guest-fix.md", "plugin-fix.md"))
if _tok: brief["bbs_test_token"] = True
text = json.dumps(brief, indent=1) + "\n"
(Path(out).write_text(text) if out else sys.stdout.write(text))
