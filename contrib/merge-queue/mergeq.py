#!/usr/bin/env python3
"""t1634 merge queue owner (Kyle t1648s8339). Runs on the box as the single owner of tracks 1-4 merges.

Each cycle (60 s) it reads the host queue (~/rizzstack-t1634/mergeq/queue.json, written by t1634-mergeq),
then handles ONE entry per repo, in queue order:
  * MERGED already -> board done + kanban complete.
  * branch behind/conflicting -> merge origin/main into it (no rebase, no force). A conflict is resolved
    only if it is confined to CHANGELOG.md, by keeping both sides. Anything else goes back to the worker.
  * workflow: the PR's own docs-parity MERGED_WINDOW_ROWS row rides in the same coordinator commit. Its
    keywords come from the PR's own CHANGELOG bullet. So the merge leaves main green and no per-merge
    companion is needed. Fallback: if main's parity test reports merged PRs with no row, ONE batched
    docs-sync PR covers all of them, carrying its own exclusion.
  * all checks green + mergeStateStatus CLEAN -> gh pr merge --merge --match-head-commit <head read now>.
  * a failed check -> unblock the parked kanban task with the failing check names, so the worker respawns.
Never --admin, never force, gitleaks before every push (push.sh). Track 5 merges approved by Kyle t1650u (no tags/releases/PyPI)."""
import json, os, re, subprocess, sys, time
RUN = os.environ.get("MERGEQ_RUN", os.getcwd()); LOG = f"{RUN}/mergeq.log"; ST = f"{RUN}/mergeq-state.json"
HOST = os.environ["MERGEQ_HOST"]  # the coordinator host (ssh target); never committed; SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", HOST]
PY = os.environ.get("MERGEQ_PYTHON", sys.executable)
for _k, _v in (("GIT_AUTHOR_NAME", "rizzstack plan coordinator"), ("GIT_AUTHOR_EMAIL", "coordinator@example.invalid"),
               ("GIT_COMMITTER_NAME", "rizzstack plan coordinator"), ("GIT_COMMITTER_EMAIL", "coordinator@example.invalid")):
    os.environ.setdefault(_k, _v)  # merges need an identity even without a conflict
GREEN = {"SUCCESS", "SKIPPED", "NEUTRAL"}
def log(m): open(LOG, "a").write(time.strftime("%H:%M:%S ") + m + "\n")
def sh(cmd, timeout=300, **kw): return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
def git(repo, *a, timeout=300): return sh(["git", "-C", wt(repo), *a], timeout=timeout)
def host(cmd, timeout=90): return sh(SSH + [cmd], timeout=timeout)
def board(tid, status, note): host(f"~/rizzstack-t1634/bin/board set {tid} {status} {json.dumps(note)}")
def kan(*a): return host("~/.local/bin/hermes kanban --board rizzstack-t1634 " + " ".join(json.dumps(x) for x in a))
def task_of(tid):
    return json.loads(host("cat ~/rizzstack-t1634/board/tasks.json").stdout or "{}").get(tid)
def state():
    try: return json.load(open(ST))
    except FileNotFoundError: return {"done": {}, "batch": None, "parked_note": {}}
def save(s): json.dump(s, open(ST, "w"), indent=1)
def wt(repo):
    p = f"{RUN}/mq/{repo}"
    if not os.path.isdir(p):
        sh(["git", "-C", f"{RUN}/src/{repo}", "worktree", "add", "-q", "--detach", p, "origin/main"])
    return p
def pr_view(repo, n):
    r = sh(["gh", "pr", "view", str(n), "--repo", f"mojomast/{repo}", "--json",
            "state,mergeStateStatus,headRefOid,headRefName,statusCheckRollup,mergeCommit"], timeout=60)
    return json.loads(r.stdout) if r.returncode == 0 else None
def checks(v):
    roll = v.get("statusCheckRollup") or []
    pend = [c.get("name") or c.get("context") for c in roll if (c.get("status") or "COMPLETED") != "COMPLETED" or c.get("state") in ("PENDING", "EXPECTED")]
    fail = [c.get("name") or c.get("context") for c in roll if (c.get("conclusion") or c.get("state") or "SUCCESS").upper() not in GREEN | {"PENDING", "EXPECTED", ""} and (c.get("status") or "COMPLETED") == "COMPLETED"]
    return pend, fail, len(roll)
def bullets(repo, n):
    d = sh(["gh", "pr", "diff", str(n), "--repo", f"mojomast/{repo}"], timeout=60).stdout
    out, cur = [], None
    for line in d.splitlines():
        if line.startswith("diff --git"): cur = line.split(" b/")[-1]
        elif cur == "CHANGELOG.md" and line.startswith("+- "): out.append(line[1:])
    return out
def keywords(text):
    toks = []
    for t in re.findall(r"`([^`]{5,80})`", text):
        if t not in toks: toks.append(t)
    return toks[:3]
def parity_rows(src): return set(int(x) for x in re.findall(r'"pr":\s*(\d+)', src.split("MERGED_WINDOW_ROWS", 1)[1].split("\n)\n", 1)[0]))
def add_row(path, n, name, kws, why):
    s = open(path).read(); head, rest = s.split("MERGED_WINDOW_ROWS", 1); body, tail = rest.split("\n)\n", 1)
    row = (f'\n    {{\n        # {why}\n        "pr": {n},\n        "name": {json.dumps(name)},\n'
           f'        "keywords": ({", ".join(json.dumps(k) for k in kws)},),\n    }},')
    open(path, "w").write(head + "MERGED_WINDOW_ROWS" + body + row + "\n)\n" + tail)
def parity_ok(repo):
    r = sh(["nice", "-n", "10", PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_docs_parity.py"], cwd=wt(repo), timeout=300)
    return r.returncode == 0, (r.stdout + r.stderr)[-600:]
def commit(repo, msg):
    env = dict(os.environ, GIT_AUTHOR_NAME="rizzstack plan coordinator", GIT_AUTHOR_EMAIL="coordinator@example.invalid",
               GIT_COMMITTER_NAME="rizzstack plan coordinator", GIT_COMMITTER_EMAIL="coordinator@example.invalid")
    return sh(["git", "-C", wt(repo), "commit", "-q", "--no-edit", "-am", msg] if msg else ["git", "-C", wt(repo), "commit", "-q", "--no-edit"], env=env)
def push(repo, branch):
    r = sh([f"{RUN}/push.sh", wt(repo), branch], timeout=300)
    local = git(repo, "rev-parse", branch).stdout.strip()
    remote = (git(repo, "ls-remote", "origin", f"refs/heads/{branch}").stdout.split() or [""])[0]
    return r.returncode == 0 and local == remote, (r.stdout + r.stderr)[-300:]
def union_changelog(path):
    s = open(path).read()
    s2 = re.sub(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", lambda m: m.group(2) + m.group(1), s, flags=re.S)
    open(path, "w").write(s2); return "<<<<<<<" not in s2
def to_worker(e, why, s, head=None):
    key = f"{e['tid']}:{why}"
    if head: s.setdefault("parked_head", {})[e["tid"]] = head
    if s["parked_note"].get(e["tid"]) == key: return
    t = task_of(e["tid"])
    if t:
        kan("comment", t, f"[mergeq] needs the worker: {why}. Fix it on the branch (no force), then run t1634-mergeq enqueue again.")
        kan("unblock", t)
    board(e["tid"], "review", f"merge queue: needs worker: {why}"[:290]); s["parked_note"][e["tid"]] = key; log(f"{e['tid']} -> worker: {why}")
BATCH_REPOS = {"bundlebees", "orbitdesktop"}  # Kyle t1659s8401 (B): non-strict repos, disjoint green PRs merge together
def batch_guard(repo, s):
    """Stop batching in a repo as soon as main's latest completed CI run there is red (Kyle: stop if main goes red)."""
    r = sh(["gh", "run", "list", "--repo", f"mojomast/{repo}", "--branch", "main", "--workflow", "CI", "--limit", "5",
            "--json", "status,conclusion,headSha"], timeout=60)
    try: runs = [x for x in json.loads(r.stdout or "[]") if x["status"] == "completed"]
    except ValueError: return
    if runs and runs[0]["conclusion"] not in ("success", "skipped", "neutral"):
        if not s.setdefault("batch_off", {}).get(repo):
            s["batch_off"][repo] = runs[0]["headSha"][:9]; log(f"BATCHING OFF in {repo}: main CI {runs[0]['conclusion']} at {runs[0]['headSha'][:9]}")
QUEUE_REPOS = {"workflow", "hyvv"}  # Kyle 14:39 ET (C/D): native GitHub merge queue once main's ruleset has it
AUTO_REPOS = {"workflow", "hyvv", "bundlebees", "orbitdesktop"}  # Kyle 14:39 ET (E): GitHub merges on CI completion
_rules = {}
def rules(repo):
    t, val = _rules.get(repo, (0, None))
    if val is not None and time.time() - t < 300: return val
    r = sh(["gh", "api", f"repos/mojomast/{repo}/rules/branches/main"], timeout=60)
    try: rs = json.loads(r.stdout) if r.returncode == 0 else None
    except ValueError: rs = None
    if rs is None: return {"queue": False, "required": None}  # unknown: fail closed (no auto-merge)
    req = set()
    for x in rs:
        if x.get("type") == "required_status_checks":
            req |= {c["context"] for c in x.get("parameters", {}).get("required_status_checks", [])}
    val = {"queue": any(x.get("type") == "merge_queue" for x in rs), "required": req}
    _rules[repo] = (time.time(), val); return val
def queue_on(repo): return repo in QUEUE_REPOS and rules(repo)["queue"]
def auto_ok(repo, v):
    """Arm auto-merge only if nothing failed and every NON-required check is already complete and green, so
    GitHub's merge on required-check completion can never skip a check the standing rule waits for."""
    req = rules(repo)["required"]
    if repo not in AUTO_REPOS or not req: return False
    for c in v.get("statusCheckRollup") or []:
        name = c.get("name") or c.get("context"); done = (c.get("status") or "COMPLETED") == "COMPLETED" and c.get("state") not in ("PENDING", "EXPECTED")
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        if done and concl not in GREEN: return False
        if not done and name not in req: return False
    return True
def arm_auto(e, v, s):
    head = v["headRefOid"]; armed = s.setdefault("auto_armed", {})
    if armed.get(e["tid"]) == head: return True
    r = sh(["gh", "pr", "merge", str(e["pr"]), "--repo", f"mojomast/{e['repo']}", "--merge", "--auto", "--match-head-commit", head], timeout=120)
    log(f"{e['tid']} auto-merge {'(merge queue) ' if queue_on(e['repo']) else ''}armed at {head[:9]} rc={r.returncode} {r.stderr.strip()[:120]}")
    if r.returncode == 0: armed[e["tid"]] = head; return True
    return False
def disarm(e, s):
    if s.get("auto_armed", {}).pop(e["tid"], None):
        sh(["gh", "pr", "merge", str(e["pr"]), "--repo", f"mojomast/{e['repo']}", "--disable-auto"], timeout=60); log(f"{e['tid']} auto-merge disarmed")
TRAIN_REPOS = {"workflow", "hyvv"}  # Kyle 14:39 ET (D): strict repos without a native queue (user-owned): stack N green PRs, CI once
TRAIN_MAX = 5
def green_all(v):
    pend, fail, n = checks(v); return n and not pend and not fail
def train_build(repo, members, s):
    """One train branch off main that merges every member's verified head (--no-ff), one PR, CI runs once on it."""
    sh(["git", "-C", f"{RUN}/src/{repo}", "fetch", "-q", "origin", "main"] + [f"refs/pull/{e['pr']}/head" for e, _ in members], timeout=180)
    br = f"train/{repo}-{time.strftime('%H%M%S')}"
    if git(repo, "checkout", "-q", "-f", "-B", br, "origin/main").returncode != 0: return log(f"train {repo}: checkout failed")
    took = []
    for e, v in members:
        head = v["headRefOid"]
        m = git(repo, "merge", "--no-ff", "--no-edit", "-m", f"train: merge #{e['pr']} ({e['tid']}) at {head[:9]}", head)
        if m.returncode != 0:
            bad = [f for f in git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()]
            for f in list(bad):
                if f == "CHANGELOG.md" and union_changelog(f"{wt(repo)}/CHANGELOG.md"): git(repo, "add", f); bad.remove(f)
                elif repo == "workflow" and f == PARITY and union_rows(f"{wt(repo)}/{PARITY}"): git(repo, "add", f); bad.remove(f)
            if bad or not git(repo, "diff", "--name-only", "--diff-filter=U").stdout.strip() == "":
                git(repo, "merge", "--abort"); log(f"train {repo}: #{e['pr']} left out (conflict {', '.join(bad)[:80]})"); continue
            if commit(repo, None).returncode != 0: git(repo, "merge", "--abort"); continue
        took.append((e, head))
    if len(took) < 2: return log(f"train {repo}: only {len(took)} member(s) merged cleanly; singles path instead")
    if repo == "workflow":
        ok, out = parity_ok(repo)
        if not ok: return log("train workflow: docs-parity fails on the train: " + out.strip().splitlines()[-1][:150])
    ok, out = push(repo, br)
    if not ok: return log(f"train {repo}: push refused: {out[-150:]}")
    names = ", ".join(f"#{e['pr']} ({e['tid']})" for e, _ in took)
    r = sh(["gh", "pr", "create", "--repo", f"mojomast/{repo}", "--base", "main", "--head", br, "--title", f"merge train: {names}"[:200],
            "--body", f"Merge train (speed-up D, Kyle 14:39 ET): stacks {len(took)} green, reviewed PRs at their verified heads, runs CI once, and merges them all with one merge commit. GitHub marks each member merged. Members: {names}."], timeout=60)
    if r.returncode != 0: return log(f"train {repo}: pr create failed {r.stderr.strip()[:120]}")
    num = int(r.stdout.strip().rsplit("/", 1)[-1])
    if repo == "workflow":
        pth = f"{wt(repo)}/{PARITY}"; s2 = open(pth).read()
        s2 = s2.replace("EXCLUDED_PRS: dict[int, str] = {\n", "EXCLUDED_PRS: dict[int, str] = {\n    %d: (\n        \"merge train (t1634 merge queue, speed-up D): carries only already-rowed member PRs; \"\n        \"it has no change of its own\"\n    ),\n" % num, 1)
        open(pth, "w").write(s2); commit(repo, f"docs(parity): exclude merge train PR #{num}")
        ok, out = parity_ok(repo)
        if not ok or not push(repo, br)[0]:
            sh(["gh", "pr", "close", str(num), "--repo", f"mojomast/{repo}", "--comment", "train aborted: parity exclusion failed"], timeout=60)
            return log(f"train workflow #{num} aborted: parity exclusion failed")
    s.setdefault("train", {})[repo] = {"pr": num, "members": [[e["tid"], e["pr"], h] for e, h in took]}
    log(f"train {repo} #{num} built with {names}")
def train_step(repo, entries, s):
    """Returns the set of tids the train owns this cycle (handle() skips them)."""
    t = s.setdefault("train", {}).get(repo)
    if t:
        v = pr_view(repo, t["pr"])
        if not v: return {m[0] for m in t["members"]}
        if v["state"] == "MERGED":
            for tid, n, _ in t["members"]:
                e = next((x for x in entries if x["tid"] == tid), {"tid": tid, "repo": repo, "pr": n})
                mv = pr_view(repo, n) or {}
                landed(e, mv if mv.get("state") == "MERGED" else v, s)
            log(f"train {repo} #{t['pr']} MERGED {(v.get('mergeCommit') or {}).get('oid', '')[:9]}"); s["train"][repo] = None; return set()
        moved = [n for _, n, h in t["members"] if (pr_view(repo, n) or {}).get("headRefOid") != h]
        pend, fail, n = checks(v)
        if v["state"] != "OPEN" or moved or fail:
            why = "member head moved " + str(moved) if moved else ("CI failed: " + ", ".join(sorted(set(fail)))[:120] if fail else v["state"])
            if v["state"] == "OPEN": sh(["gh", "pr", "close", str(t["pr"]), "--repo", f"mojomast/{repo}", "--comment", f"Train dissolved: {why}. Members go back to the singles path."], timeout=60)
            log(f"train {repo} #{t['pr']} dissolved: {why}"); s["train"][repo] = None
            if fail: s.setdefault("train_cool", {})[repo] = time.time()  # one failed train -> singles for 30 min
            return set()
        if n and not pend and v["mergeStateStatus"] == "CLEAN":
            r = sh(["gh", "pr", "merge", str(t["pr"]), "--repo", f"mojomast/{repo}", "--merge", "--match-head-commit", v["headRefOid"]], timeout=120)
            log(f"train {repo} #{t['pr']} merge attempt rc={r.returncode} {r.stderr.strip()[:100]}")
        elif v["mergeStateStatus"] == "BEHIND":
            sh(["gh", "pr", "close", str(t["pr"]), "--repo", f"mojomast/{repo}", "--comment", "Train dissolved: main moved; rebuilding."], timeout=60)
            log(f"train {repo} #{t['pr']} dissolved: main moved"); s["train"][repo] = None; return set()
        return {m[0] for m in t["members"]}
    if time.time() - s.get("train_cool", {}).get(repo, 0) < 1800: return set()
    cand = []
    for e in sorted(entries, key=lambda e: (e["tid"] not in PRIORITY, e["seq"])):
        if e["repo"] != repo or e["tid"] in s["done"]: continue
        v = pr_view(repo, e["pr"])
        if not v or v["state"] != "OPEN" or v["mergeStateStatus"] == "DIRTY": continue
        if s.get("parked_head", {}).get(e["tid"]) == v["headRefOid"]: continue
        if repo == "workflow" and e["tid"] not in s.get("rowed", []): continue
        if green_all(v): cand.append((e, v))
        if len(cand) >= TRAIN_MAX: break
    if len(cand) >= 2:
        for e, _ in cand: disarm(e, s)
        train_build(repo, cand, s)
        t = s["train"].get(repo)
        if t: return {m[0] for m in t["members"]}
    return set()
PRIORITY = {"WA-DEC-CHANGELOG", "WA-DEC-TARBALL"}  # Kyle t1658u: conflict killers jump the queue
def fragments_supported(repo):
    """Proposal A (Kyle-approved): once main's parity guard reads changelog.d/, rows go to fragments instead."""
    w = wt(repo); guard = {"workflow": "tests/test_docs_parity.py", "bundlebees": "tests/test_changelog_coverage.py"}.get(repo)
    return bool(guard) and os.path.isdir(f"{w}/changelog.d") and os.path.exists(f"{w}/{guard}") and "changelog.d" in open(f"{w}/{guard}").read()
def to_fragment(e, br):
    """Move the PR's own CHANGELOG bullets into changelog.d/<branch-slug>.md. Returns an error string or None."""
    repo, n = e["repo"], e["pr"]; w = wt(repo)
    frag = f"changelog.d/{br.replace('/', '--')}.md"
    if os.path.exists(f"{w}/{frag}"): return None
    bl = bullets(repo, n); kws = keywords(" ".join(bl))
    if not bl or len(kws) < 2: return "no CHANGELOG bullet with >=2 backticked keywords to move into a fragment"
    body = "---\nsection: Added\nkeywords: [" + ", ".join("`%s`" % k for k in kws) + "]\n---\n" + "\n".join(bl) + "\n"
    open(f"{w}/{frag}", "w").write(body)
    cl = f"{w}/CHANGELOG.md"
    if os.path.exists(cl):
        lines = open(cl).read().split("\n"); drop = set(bl)
        open(cl, "w").write("\n".join(l for l in lines if l not in drop))
    git(repo, "add", frag, "CHANGELOG.md"); commit(repo, f"changelog: move #{n} bullet into {frag} (merge queue, proposal A)")
    return None
PARITY = "tests/test_docs_parity.py"
def union_rows(path):
    """Resolve conflicts where both sides only appended MERGED_WINDOW_ROWS dict rows; anything else stays a conflict."""
    s = open(path).read()
    def fix(m):
        a, b = m.group(1), m.group(2)
        if not all(re.fullmatch(r'(?s)\s*(#[^\n]*\n\s*)*"(pr|name|keywords)".*', x.strip()+"\n") or x.strip()=="" for x in (a, b)): raise ValueError
        return a + "    },\n    {\n" + b
    try: s2 = re.sub(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", fix, s, flags=re.S)
    except ValueError: return False
    if "<<<<<<<" in s2: return False
    open(path, "w").write(s2)
    import ast
    try: ast.parse(s2)
    except SyntaxError: open(path, "w").write(s); return False
    return True
BUNDLE = "hermes-plugin/orbit-source.tar.gz"
def refresh(e, v):
    """Bring the branch up to date with main (CHANGELOG union only), plus the workflow parity row. Returns pushed?"""
    repo, n, br = e["repo"], e["pr"], v["headRefName"]
    sh(["git", "-C", f"{RUN}/src/{repo}", "fetch", "-q", "origin", "main", br], timeout=180)
    co = git(repo, "checkout", "-q", "-f", "-B", br, f"origin/{br}")
    if co.returncode != 0: return "QUEUE: cannot check out the branch in the queue worktree: " + co.stderr.strip()[-120:]
    git(repo, "reset", "-q", "--hard", f"origin/{br}")
    m = git(repo, "merge", "--no-edit", "origin/main")
    if m.returncode != 0:
        conflicted = git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
        if not conflicted:
            git(repo, "merge", "--abort"); return "merge of origin/main failed without conflicts: " + (m.stderr or m.stdout).strip()[-120:]
        bad = [f for f in conflicted if f != "CHANGELOG.md"]
        if repo == "orbitdesktop" and bad == [BUNDLE]:
            # generated artefact: take ours, then regenerate from the merged tree (tests/test_orbit_bundle.py checks parity)
            git(repo, "checkout", "--ours", BUNDLE)
            if "CHANGELOG.md" not in git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split() or union_changelog(f"{wt(repo)}/CHANGELOG.md"):  # only reads it when conflicted
                g = sh(["nice", "-n", "10", PY, "scripts/bundle_hermes.py"], cwd=wt(repo), timeout=300)
                if g.returncode == 0:
                    git(repo, "add", BUNDLE); bad = []
                    if os.path.exists(f"{wt(repo)}/CHANGELOG.md"): git(repo, "add", "CHANGELOG.md")
        if repo == "workflow" and PARITY in bad and union_rows(f"{wt(repo)}/{PARITY}"):
            git(repo, "add", PARITY); bad.remove(PARITY)  # both sides only added registry rows: keep both
        cl = f"{wt(repo)}/CHANGELOG.md"
        if bad or (os.path.exists(cl) and "<<<<<<<" in open(cl).read() and not union_changelog(cl)):
            git(repo, "merge", "--abort"); return f"conflict outside CHANGELOG.md: {', '.join(bad)[:120]}"
        git(repo, "add", "CHANGELOG.md"); commit(repo, None)
    if fragments_supported(repo):
        err = to_fragment(e, br)
        if err: return err
        guard = {"workflow": "tests/test_docs_parity.py", "bundlebees": "tests/test_changelog_coverage.py"}[repo]
        r = sh(["nice", "-n", "10", PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", guard], cwd=wt(repo), timeout=300)
        if r.returncode != 0: return "fragment coverage guard fails on the refreshed branch: " + (r.stdout + r.stderr).strip().splitlines()[-1][:150]
    elif repo == "workflow":
        p = f"{wt(repo)}/tests/test_docs_parity.py"
        if n not in parity_rows(open(p).read()):
            bl = bullets(repo, n); kws = keywords(" ".join(bl))
            if len(kws) < 2: return "no CHANGELOG bullet with >=2 backticked keywords for the docs-parity row"
            add_row(p, n, e["tid"] + ": " + (bl[0][2:70] if bl else e["tid"]), kws,
                    f"{e['tid']} (t1634 merge queue): row rides in its own PR so the merge leaves main green.")
            commit(repo, f"docs(parity): {e['tid']} coverage row for #{n} (merge queue, rides in its own PR)")
        ok, out = parity_ok(repo)
        if not ok: return "docs-parity test fails on the refreshed branch: " + out.strip().splitlines()[-1][:150]
    if git(repo, "rev-parse", "HEAD").stdout.strip() == v["headRefOid"]: return None
    ok, out = push(repo, br)
    if not ok: return "push refused (gitleaks/host scan or remote): " + out.strip()[-150:]
    log(f"{e['tid']} refreshed and pushed {git(repo, 'rev-parse', '--short', 'HEAD').stdout.strip()}"); return "PUSHED"
def landed(e, v, s):
    sha = (v.get("mergeCommit") or {}).get("oid", "")[:9]; s["done"][e["tid"]] = sha
    board(e["tid"], "done", f"merged {sha} ({e['repo']} PR #{e['pr']}) by the merge queue; review APPROVE")
    t = task_of(e["tid"])
    if t: kan("complete", t, "--result", f"merged {sha} ({e['repo']}#{e['pr']}) via t1634 merge queue")
    log(f"{e['tid']} MERGED {sha}")
def batch_fallback(s):
    """Main's parity test names merged PRs with no row: one batched docs-sync PR for all of them."""
    if s.get("batch"):
        v = pr_view("workflow", s["batch"]["pr"])
        if v and v["state"] == "MERGED": log(f"batch #{s['batch']['pr']} merged"); s["batch"] = None
        elif v and v["state"] == "OPEN":
            pend, fail, n = checks(v)
            if n and not pend and not fail and v["mergeStateStatus"] == "CLEAN":
                head = pr_view("workflow", s["batch"]["pr"])["headRefOid"]
                sh(["gh", "pr", "merge", str(s["batch"]["pr"]), "--repo", "mojomast/workflow", "--merge", "--match-head-commit", head], timeout=120)
        return
    sh(["git", "-C", f"{RUN}/src/workflow", "fetch", "-q", "origin", "main"], timeout=180)
    git("workflow", "checkout", "-q", "-f", "--detach", "origin/main")
    ok, out = parity_ok("workflow")
    m = re.search(r"merged campaign PR\(s\) \[([0-9, ]+)\] have no coverage registry entry", out)
    if ok or not m: return
    missing = [int(x) for x in m.group(1).split(",")]
    open_ = sh(["gh", "pr", "list", "--repo", "mojomast/workflow", "--state", "open", "--search", "docs(parity) in:title", "--json", "number"], timeout=60).stdout
    if json.loads(open_ or "[]"): log("parity red but a docs(parity) PR is already open; not duplicating"); return
    br = f"docs/parity-batch-{time.strftime('%H%M')}"; git("workflow", "checkout", "-q", "-B", br, "origin/main")
    p = f"{wt('workflow')}/tests/test_docs_parity.py"
    for n in missing:
        kws = keywords(" ".join(bullets("workflow", n)))
        if len(kws) < 2: log(f"batch: #{n} has no usable keywords; leaving for a human"); return
        add_row(p, n, f"merged PR #{n}", kws, f"#{n}: batched docs-sync row (t1634 merge queue fallback).")
    commit("workflow", f"docs(parity): batched coverage rows for {', '.join('#'+str(n) for n in missing)}")
    ok1, _ = push("workflow", br)
    r = sh(["gh", "pr", "create", "--repo", "mojomast/workflow", "--base", "main", "--head", br, "--title",
            f"docs(parity): batched coverage rows for {', '.join('#'+str(n) for n in missing)}", "--body",
            "One batched docs-sync PR (t1634 merge queue fallback, Kyle t1648s8339): rows for merged PRs that landed without one. It carries its own exclusion."], timeout=60)
    num = int(r.stdout.strip().rsplit("/", 1)[-1]); s2 = open(p).read()
    s2 = s2.replace("EXCLUDED_PRS: dict[int, str] = {\n", "EXCLUDED_PRS: dict[int, str] = {\n    %d: (\n        \"batched docs-sync companion (t1634 merge queue): registry bookkeeping only; \"\n        \"it carries its own exclusion so merging it leaves main green\"\n    ),\n" % num, 1)
    open(p, "w").write(s2); commit("workflow", f"docs(parity): exclude batched companion PR #{num}")
    ok, out = parity_ok("workflow")
    if ok: push("workflow", br); s["batch"] = {"pr": num, "rows": missing}; log(f"batch PR #{num} for {missing}")
    else: log("batch parity test failed locally: " + out[-200:])
def cycle():
    s = state()
    q = json.loads(host("cat ~/rizzstack-t1634/mergeq/queue.json 2>/dev/null || echo '{}'").stdout or "{}")
    batch_fallback(s)
    seen = set(); s["_cycle_files"] = {}
    for r in BATCH_REPOS: batch_guard(r, s)
    owned = set()
    for r in TRAIN_REPOS:
        try: owned |= train_step(r, q.get("entries", []), s)
        except Exception as ex: log(f"train {r} error {type(ex).__name__}: {str(ex)[:160]}")
    for e in sorted(q.get("entries", []), key=lambda e: (e["tid"] not in PRIORITY, e["seq"])):
        if e["tid"] in s["done"] or e["repo"] in seen or e["tid"] in owned: continue
        try: handle(e, s, seen)
        except Exception as ex: seen.add(e["repo"]); log(f"{e['tid']} error {type(ex).__name__}: {str(ex)[:160]}")
    s.pop("_cycle_files", None); s.pop("_refreshed", None)
    save(s)
def handle(e, s, seen):
    if True:
        v = pr_view(e["repo"], e["pr"])
        if not v: return
        ph = s.setdefault("parked_head", {}).get(e["tid"])
        if ph and v["state"] == "OPEN" and v["headRefOid"] == ph: return  # parked for its worker: no head-of-line block
        batching = e["repo"] in BATCH_REPOS and not s.get("batch_off", {}).get(e["repo"])
        qon = queue_on(e["repo"])
        if not batching and not qon:
            seen.add(e["repo"])  # one PR per repo at a time, in queue order
        if v["state"] == "MERGED": landed(e, v, s); seen.discard(e["repo"]); return
        if v["state"] != "OPEN": to_worker(e, f"PR is {v['state']}", s); return
        if s.get("batch") and e["repo"] == "workflow": return  # let the batch land first
        if v["mergeStateStatus"] == "DIRTY" or (v["mergeStateStatus"] == "BEHIND" and not qon) or (e["repo"] == "workflow" and e["tid"] not in s.get("rowed", [])):
            disarm(e, s)
            if batching or qon:
                if e["repo"] in s.setdefault("_refreshed", set()): return  # one worktree refresh per repo per cycle
                s["_refreshed"].add(e["repo"])
            res = refresh(e, v)
            if e["repo"] == "workflow" and res in (None, "PUSHED"): s.setdefault("rowed", []).append(e["tid"])
            if res not in (None, "PUSHED"): to_worker(e, res, s, v["headRefOid"])
            return
        pend, fail, n = checks(v)
        if fail: disarm(e, s); to_worker(e, "CI failed: " + ", ".join(sorted(set(fail)))[:150], s, v["headRefOid"]); return
        if s.get("batch_off", {}).get(e["repo"]) and e["repo"] in BATCH_REPOS: disarm(e, s)  # main red: back to one at a time
        elif n and (qon or e["repo"] in AUTO_REPOS) and auto_ok(e["repo"], v) and arm_auto(e, v, s):
            return  # E: GitHub merges (or enqueues) the moment the required checks finish; landed() books it next cycle
        if pend or not n or v["mergeStateStatus"] != "CLEAN": return
        if batching:
            files = set(sh(["gh", "pr", "diff", str(e["pr"]), "--repo", f"mojomast/{e['repo']}", "--name-only"], timeout=60).stdout.split())
            used = s["_cycle_files"].setdefault(e["repo"], set())
            if not files or files & used: return  # overlaps a PR merged this cycle: wait for the next cycle
            used |= files
        head = pr_view(e["repo"], e["pr"])["headRefOid"]
        r = sh(["gh", "pr", "merge", str(e["pr"]), "--repo", f"mojomast/{e['repo']}", "--merge", "--match-head-commit", head], timeout=120)
        log(f"{e['tid']} merge attempt rc={r.returncode} {r.stderr.strip()[:120]}")
        v2 = pr_view(e["repo"], e["pr"])
        if v2 and v2["state"] == "MERGED":
            landed(e, v2, s)
            if batching: s.setdefault("batched", []).append([time.strftime("%H:%M:%S"), e["repo"], e["pr"]])
if __name__ == "__main__":
    while True:
        try: cycle()
        except Exception as ex: log(f"cycle error {type(ex).__name__}: {str(ex)[:200]}")
        if "--once" in sys.argv: break
        time.sleep(30)
