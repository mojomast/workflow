> Status: deferred. The rebrand is not authorized; this runbook is documentation only and executes nothing without the owner typed yes.

# Rebrand execution runbook — the plan executed safely

**Status:** staged execution runbook for [docs/rebrand-plan.md](rebrand-plan.md). It executes nothing until the plan's decision checklist (section 6, D1–D8) is approved by Kyle in his own words — an agent's or sibling bot's go-ahead never stands in for it (docs/06-rules-and-lessons.md approval gates). Steps inside the window carry their own gates on top (launcher restart, merges, the Pages publish).

**Staged:** 2026-11-16 (America/Toronto). **Owner / approver:** Kyle Durepos (mojomast).

**Sources of truth:** the plan (mapping, at-once window, rollback story, decision gates); [docs/website-plan.md](website-plan.md) (the launch); docs/11-working-together.md (live-host rhythm); docs/03 and docs/05 (launcher, host and deploy surfaces); docs/CI.md (required contexts); [docs/m2-canary-runbook.md](m2-canary-runbook.md) — the house runbook style this document follows, including the `# confirm in Step 0` rule: a flag not documented in this repository is confirmed against recorded `--help` output before the window uses it, and a step whose precondition is missing is recorded **NOT RUN** with the reason, never silently skipped.

**Hygiene:** no tokens, no private hosts, no live data in this document; host paths are named generically or as templates; secret-shaped values never appear in commands or examples.

## Provenance and the workspace lesson

The first attempt at this runbook (attempt `att_b470a77f`) produced the document but never committed it. The worker was reprovisioned at 18:02 the same day and the workspace — runbook included — was destroyed with it. That failure class is now a rule of this runbook (section 3.4, rule R5): **the rebrand's own work lives only in commits.** This r2 rebuild commits to its branch immediately, and every execution step below ends with a commit or a committed evidence write before the next one starts. No step of the window relies on uncommitted local state surviving a provisioning event.

## 0. Scope and blast radius

| | |
|---|---|
| Executes | three repository renames (`mojomast/workflow` → `flww`, `mojomast/bundlebees` → `bzzq`, `mojomast/orbitdesktop` → `orbt`); one coordinated re-registration of every runtime surface that names a repository; one reference-update pass over docs and code; the umbrella launch publish |
| Does not touch | `mojomast/hyvv` (name unchanged per the plan's mapping); plugin ids, catalog keys and titles (D4 default, docs/06 rule); protocol identifiers — schemas, urn identifiers and `rizzstack.*` record names are already the umbrella namespace (plan §3.4); tags, releases and git history (no force-push anywhere in this runbook, ever — plan §5); sealed campaign records (plan §3.6); `mojomast/rizzstack` itself, which already exists as the protocol-distribution entry point under the umbrella name (recorded in `ground_truth.json`, umbrella row) — it needs a launch, not a rename |
| Conditional | `mojomast/orbit-control-plane` renames only if D1 says so; the dashboard and Observatory URL checks then join section 2.4 for it too |
| Deleted | nothing. A rename deletes nothing; the checklist never runs a destructive command |

---

## 1. RECOVERY PATH — per-rename rollback

### 1.1 The rule

Every rename is independently reversible at the moment it happens, and each rename's redirect evidence is recorded **before** the next rename starts. Rollback never assumes redirects: renaming back is itself a second rename, so after any rollback the section 2.2 verification block runs again for every repo whose name moved. The at-once rule (plan §4) cuts both ways: execution moves as one set, and so does rollback — a partial state is the worst state, which is exactly why the window keeps bees idle (section 3).

### 1.2 Pre-change inventory (recorded into acceptance evidence before the window)

The inventory is generated, not remembered. Before the window opens, record into evidence:

```
rg -n "mojomast/workflow|mojomast/bundlebees|mojomast/orbitdesktop|mojomast/hyvv" \
   --glob '!.git' . > inventory-mentions.txt          # every textual reference, with per-file counts
git status --porcelain                                # must be empty: R5 precondition
bundlebees status                                     # live bee count from the worker host
bundlebees project list                               # every project row and its repo field   # confirm in Step 0
crontab -l > crontab-backup-YYYYMMDD.txt              # cron entries naming repos
gh repo view mojomast/workflow --json name,description,defaultBranchRef   # repeat for the other four repos
git -C <each local checkout> remote -v                # checkout list + current remote URLs
```

Measured baseline from this checkout at staging time (2026-11-16): `mojomast/workflow` 131 mentions, `mojomast/bundlebees` 58, `mojomast/orbitdesktop` 57, `mojomast/hyvv` 25 (hyvv is counted because the inventory lists every surface, even one that does not rename). The counts include sealed evidence on purpose — the post-flight scan (section 4, step 11) predicts them as residual, it does not chase zero through sealed records (plan §3.6).

### 1.3 The inventory — every mutable name surface with its exact restore command

| # | Surface | Lives where | Exact restore command |
|---|---|---|---|
| 1 | GitHub repo name `workflow` → `flww` | GitHub Settings → General → Repository name | `gh api -X PATCH repos/mojomast/flww -f name=workflow   # confirm in Step 0` (equivalently `gh repo edit mojomast/flww --rename workflow`) |
| 2 | GitHub repo name `bundlebees` → `bzzq` | same | `gh api -X PATCH repos/mojomast/bzzq -f name=bundlebees   # confirm in Step 0` |
| 3 | GitHub repo name `orbitdesktop` → `orbt` | same | `gh api -X PATCH repos/mojomast/orbt -f name=orbitdesktop   # confirm in Step 0` |
| 4 | `orbit-control-plane` (only if D1 renames it) | same | `gh api -X PATCH repos/mojomast/<new-name> -f name=orbit-control-plane   # confirm in Step 0` |
| 5 | Repo settings (description, topics, homepage, default branch, branch-protection rulesets) | GitHub settings | Rename preserves settings; verify by diffing the Step 0 settings dump before/after. If anything is lost, re-apply from the dump: `gh api -X PATCH repos/mojomast/<name> -f description="<recorded value>"` (and the same for each lost field) |
| 6 | Remote URLs on every local checkout | the box's plugin checkouts (symlinked into the plugin state dir, docs/05), the Orbit live tree, every workflow/worker-host checkout — the list comes from the Step 0 scan | `git -C <checkout> remote set-url origin https://github.com/mojomast/<old>.git` — one per checkout, then `git -C <checkout> remote -v` to confirm |
| 7 | Local checkout directory names | every clone directory | Policy: directories are **never** renamed in this window (services, symlinks and scripts point at directory names, not remote names). If a directory was ever re-cloned under the new name and must roll back: `git clone https://github.com/mojomast/<old>.git <old-directory-name>` and re-point the symlink; verify with `readlink` on the plugin path |
| 8 | CI code references in this repo | `contrib/bee-ci/manifest.py` (the `REPOS` tuple), `contrib/bee-ci/jobs/{workflow,bundlebees,orbitdesktop,hyvv}.yaml` (file names + `repo` fields), the mirroring tests (`contrib/bee-ci/tests/test_manifest.py`, `test_run_shadow.py`, `test_evidence.py`, `test_jobs_manifest.py`, `test_jobs_conformance.py`), `contrib/bee-ci/poll.py` (`DEFAULT_REPOS`), schema `$id` URLs (`contrib/bee-ci/schema/ci-job.schema.json`, `contrib/bee-ci/schemas/job-manifest.schema.json`, `schemas/*.schema.json`) | `git revert <the-un-deferral-commit-range>` on this repository — the staging-branch structure keeps that commit set small and reviewable exactly for this (plan §5) |
| 9 | Clone defaults and pins in acceptance | `acceptance/cold_start.sh` (`WORKFLOW_REPO` / `BUNDLEBEES_REPO` defaults), `acceptance/harness.py` help text, `.github/workflows/ci.yml` (the `BUNDLEBEES_SHA` pin — a commit SHA survives any rename; verify it still resolves, never rewrite it casually) | same revert set as row 8 |
| 10 | Docs cross-references | `README.md` (index), docs/03, 04, 05, 08 (each renamed row gains a was-the-old-name note, the EOH-row precedent), docs/06 (naming table), docs/12, 13, 15, 17, 21–24, docs/quickstarts/*, `ROADMAP.md` (D8 closes the superseded swrm proposal), `templates/handoff/HANDOFF.md` (the layer table switches from operational names to selected names only in the un-deferral commit), `profiles/repos.json` (element-registry URLs; its pins are SHAs and survive), docs/m2-canary-runbook.md **if it has not executed yet** — a staged runbook is updated; an executed one's evidence is sealed | same revert set as row 8 |
| 11 | Deployed service units: `rizzstack-obs-collector.service` (template instance, e.g. `@8787`) and `rizzstack-decision-notifier.service` | installed under the user's systemd unit directory; their `Documentation=` line is the only repo-name surface inside a deployed unit (it names `https://github.com/mojomast/workflow`); `ExecStart` paths point at the user's bin/state directories and carry no repo name — the scripts are copied out of the checkout at install time | `install -m 0644 contrib/rizzstack-observability/<unit-file> ~/.config/systemd/user/<unit-file>` from the reverted checkout, then `systemctl --user daemon-reload` (any unit **restart** needs Kyle's explicit yes) |
| 12 | `usage-ingest.service` (merged on orbitdesktop main; installed nowhere observable per docs/memory-ground-truth-audit.md) | upstream orbitdesktop tree | Inventory-only row: `systemctl --user list-unit-files` must show nothing ingest-named. If a future install exists, restore with row 11's shape, from the orbitdesktop checkout |
| 13 | `hermes-dashboard` / `hermes-gateway` (`systemctl --user`) | the box's deploy pipeline (docs/05, contrib/hermes-forge.md) | Not a name surface and not scheduled for restart by this rebrand — no plugin code changes. Restore: n/a; listed so nobody "helpfully" restarts them. If a restart ever happens in the window anyway, it needs Kyle's yes and the snapshot-restore ritual from docs/04 (deploy pipeline) |
| 14 | PC launcher project allow-list | the launcher's project allow-list on Kyle's PC (docs/03: projects must be on the allow-list; authorizing a repo means a launcher restart) | Re-add or rename the entries to the old `owner/name`, then restart the launcher with the launcher folder's stop/start scripts — **restart needs Kyle's explicit yes and the quiet boundary (section 3)** |
| 15 | bundlebees project rows | the job store (`bundlebees project list` rows carry `--repo owner/name`) | `bundlebees project update <project-name> --repo <old-owner/name>   # confirm in Step 0` — one per affected row, then `bundlebees project list` to confirm |
| 16 | hyvv provisioning registrations | the worker host's project workspaces, registered with a repo field (`POST $HYVV_V1/provision/project`, the m2-canary-runbook Step 4a shape) | Re-register the project with the old repo name in the payload and keep the receipt   `# confirm in Step 0` |
| 17 | Orbit app registry | apps and panes served from the orbitdesktop checkout (Grok Bots app, Collab board, Google Colab app, local-workers adapter, Observatory app, the planned ACDD evidence view) | App ids and plugin ids do **not** follow repo names — the EOH precedent: plugin id `godseye` survived the `hermes-godseye` → `EOH` rename. Nothing to rename. Restore (only if a checkout directory was ever renamed): row 7's re-clone to the old directory name + re-symlink; registrations keep their ids |
| 18 | Agent registry (docs/15) | Orbit's agent registry — entries carry adapter kinds, not repo names | Restore: n/a — no rename surface; verification row only (section 2.4) |
| 19 | Dashboard URLs | the orbit-control-plane dashboard and the Observatory route — tailnet-only, named generically in this repository by policy; neither URL embeds a repo name; both serve from local checkout directories | Restore: n/a under the directory-name policy of row 7. If D1 renames orbit-control-plane: row 6's `set-url` treatment for its checkout, plus its URL check joins section 2.4 |
| 20 | Cron scripts | the bee-ci `poll.py` cron entries pass `--repo owner/name` arguments; the campaign wake-up entries (`job tick`, and the agent turn driven by `needs-agent.json`) name no repo (docs/31 §4) | `crontab crontab-backup-YYYYMMDD.txt` — restore from the Step 0 backup after the new-name entries are verified (section 3.3) |
| 21 | GitHub Pages sites under a renamed repo | Pages URLs follow the repository path; after a rename the old Pages URL does not redirect — it breaks | The rename-back in rows 1–3 restores the Pages URL with the repo name. Forward fix is a re-publish under the new name (needs Kyle's yes — Pages deploys are a standing gated change, docs/06) |
| 22 | Catalog records | Nous catalog plugin ids, keys, titles and open pull requests | Keys and titles stay as they are (D4 default). Open catalog PRs naming a renamed repo get a comment or a fresh PR only if Kyle asks (plan §3.2). Restore: withdraw or correct any PR updated for the rename (plan §5) |
| 23 | Sealed records | chapter 30/31 closeouts, campaign reports, lease and job documents, acceptance results, `ground_truth.json`, contrib accounts, docs/08 historical narratives | Restore: n/a — a rename never rewrites a sealed record; new records use the new names with a formerly-the-old-name pointer (plan §3.6) |
| 24 | Tags, releases, git history, stars, watchers, issues, PRs | GitHub | Restore: n/a — these follow the renamed repository untouched; no force-push and no history rewrite is part of this plan, ever |

### 1.4 Rollback order (reverse of execution)

If the window aborts at any point: (1) dispatches are already stopped — the boundary is open; (2) rename back every completed rename with rows 1–4's commands; (3) re-run the section 2.2 verification block for every repo whose name moved, in either direction; (4) revert the staging-branch merge (rows 8–10's revert set); (5) restore registrations — launcher allow-list (row 14, restart with Kyle's yes), project rows (row 15), provisioning registrations (row 16), cron (row 20); (6) record every action and its evidence. The rollback is not done until its own redirect verification passes.

---

## 2. SAME-PLACE MAPPING — every name and every caller

### 2.1 The name map

| Surface | Before | After | Moves how |
|---|---|---|---|
| GitHub repo (method/protocol) | `mojomast/workflow` | `mojomast/flww` | GitHub automatic redirect — verified per §2.2, never assumed |
| GitHub repo (execution) | `mojomast/bundlebees` | `mojomast/bzzq` | automatic redirect — verified per §2.2 |
| GitHub repo (coordination) | `mojomast/orbitdesktop` | `mojomast/orbt` | automatic redirect — verified per §2.2 |
| GitHub repo (worker host) | `mojomast/hyvv` | `mojomast/hyvv` | no change — verified unchanged in the window |
| GitHub repo (umbrella) | `mojomast/rizzstack` | `mojomast/rizzstack` | already the umbrella name; the launch publishes the site, the repo does not rename |
| GitHub repo (dashboard) | `mojomast/orbit-control-plane` | per D1 | rename + verification only if D1 says so |
| Local checkout directory names | e.g. `workflow`, `bundlebees`, `orbitdesktop` | unchanged | policy: never renamed in the window (section 1.3 row 7) |
| Docs layer names | Workflow / Bundlebees / Orbit / hyvv | flww / bzzq / orbt / hyvv | the un-deferral commit; sealed records keep the names in effect when they were recorded |
| Plugin ids, catalog keys, titles, app ids | unchanged | unchanged | EOH precedent; D4 default |
| Protocol identifiers | `rizzstack.*` record names, urn identifiers, schemas | unchanged | already the umbrella namespace (plan §3.4) |
| systemd unit names | `rizzstack-obs-collector@<port>`, `rizzstack-decision-notifier` | unchanged | already rizzstack-prefixed |
| bee-ci dispatch names | `REPOS = ("workflow", "bundlebees", "orbitdesktop", "hyvv")` | `("flww", "bzzq", "orbt", "hyvv")` | changed in the same commit as the renames (plan §3.4) |
| CI required contexts | `bee-ci/reference`, `bee-ci/project-state`, `bee-ci/secret-scan` | unchanged | they are job names, not repo names (docs/CI.md) |

### 2.2 GitHub redirect semantics — verified per repository, recorded in evidence

What a rename moves automatically: the web UI, git over HTTPS (clone, fetch, push), issues, pull requests, stars, watchers, releases, tags, wiki. What it does not: Pages site paths (the old URL breaks, it does not redirect), any caller that string-matches `owner/name`, and any caller that would otherwise lean on a redirect that can silently die — the redirect breaks the moment the old name is re-used by a new repository or the repository is renamed again (plan §3.1).

Per renamed repository, all five lines run and their output is recorded:

```
curl -sI https://github.com/mojomast/workflow | head -1     # expect 301/302 toward /mojomast/flww
git ls-remote https://github.com/mojomast/workflow HEAD     # expect exit 0 — a clone URL resolves through the redirect
gh api repos/mojomast/workflow --jq .full_name              # expect mojomast/flww (the API answers the redirect)
gh api repos/mojomast/flww --jq .full_name                  # expect mojomast/flww
gh repo view mojomast/flww --json name,description          # settings survived the rename
```

`hyvv` runs the same block expecting the same name on both sides; `orbit-control-plane` runs it only under the D1 conditional.

### 2.3 Every caller that breaks under — or must not lean on — a redirect

| Caller | Where it lives | Why a redirect is not enough | Fix and verify |
|---|---|---|---|
| GitHub Pages site path | any Pages site under a renamed repo (today: the game site, outside the four; tomorrow: the rizzstack site published from this repo per docs/website-plan.md §4) | Pages URLs contain the repo name and are **not** redirected after a rename — they 404 | Publish the site under the new name inside the window; verify: fetch the new Pages URL (200) and the old one (404 or a fixed link) |
| `raw.githubusercontent.com` links | docs, READMEs, any committed raw link | raw paths embed the repo name; a renamed repo's raw links must be rewritten rather than trusted | rewrite every raw link in the reference pass; verify with the same link check the site builder uses |
| `contrib/bee-ci/poll.py` `DEFAULT_REPOS` | the cron-driven poller lists open PRs per `owner/name` through the GitHub API | redirect-following clients survive, but queue state and dispatch identities must not pin dead names | update in the same commit as the renames; verify: the bee-ci test suite, then one `poll.py --cap 0` rehearsal writes clean state |
| `manifest.py` `REPOS` + jobs YAML + their tests | dispatch identity — not a URL at all, so a redirect does nothing for them | the manifest must never name a repository that does not exist (plan §3.4) | all five-plus files change in one commit; verify: `contrib/bee-ci/tests/` green after merge |
| acceptance clone defaults | `acceptance/cold_start.sh`, `acceptance/harness.py` | clones follow the redirect, but the defaults should name the real thing, not a dying alias | update in the reference pass; verify: the cold-start CI leg green at the merge head |
| schema `$id` URLs | `schemas/*.schema.json`, `contrib/bee-ci/**/schema*` | identifiers, never fetched — hygiene only | update in the reference pass; verify: the jsonschema CI job green |
| briefs, project rows, provisioning registrations, launcher allow-list | the runtime registration layer (section 1.3 rows 14–16) | **no redirect exists for these** — they string-match repository identity | the section 3.3 re-registration sequence, each step verified |
| cron `--repo` arguments | the poll entries (section 1.3 row 20) | API calls may follow the redirect; cron should not lean on one | rewrite entries after re-registration; verify: one `--cap 0` poll run |
| staged-but-unexecuted runbooks' `gh` snippets | e.g. docs/m2-canary-runbook.md `gh pr view --repo mojomast/bundlebees` | `gh` follows the redirect, but a staged runbook is documentation, and documentation gets rewritten | update in the reference pass if it has not executed; if it has, its evidence is sealed and stays as recorded |
| in-flight bees | attempts dispatched before the boundary | unaffected: branches and commit SHAs are rename-independent; verify/integrate match by `source_rev` and branch, not by repo name | no action; recorded as the reason the boundary only needs to be idle, not empty of history |
| sealed records | the expected residual (section 2.4) | they are not callers; they preserve names in effect | no action, by rule |

### 2.4 Acceptance — both halves, measured

1. **Every old URL resolves.** For each renamed repository the §2.2 block passes — web redirect observed, `git ls-remote` through the old URL exits 0, the API reports the new `full_name` — and the transcript is recorded in evidence. A redirect alone never counts as a rename done (plan §3.1); it counts here as *resolves*.
2. **No service, script or test references a dead name.** The post-flight scan (section 4, step 11) runs the §1.2 commands over the merged tree: the four old names appear only in (a) was-the-old-name notes in docs/08 and the mapping documents, (b) sealed evidence and campaign records, (c) this runbook and the plan. Zero hits in live code, live configuration, live docs cross-references, registration data or cron. Per-file counts are compared against the §1.2 baseline and the comparison is recorded.

---

## 3. PARALLEL OPERATION — the factory keeps working

### 3.1 What runs while bees work

Everything read-only and everything local to this repository is bee-safe and happens before the boundary opens: the pre-flight inventory (§1.2), the staging branch carrying every doc and code reference change from plan §3.3 and §3.4, the test updates, the redirect-verification scripts, the rollback rehearsal on a scratch clone, and the evidence scaffolding. None of it touches GitHub settings, the launcher, project rows, provisioning or cron. The staging branch merges only after the renames (plan §4.2), so while bees run it simply accumulates reviewed commits.

### 3.2 The quiet boundary — named explicitly

The **bee-idle boundary** opens when all four conditions hold, verified in one sitting and recorded in evidence:

1. `bundlebees status` reports **0 live bees** — the worker-host count, not a local tally (the m2-canary-runbook Step 0 convention);
2. no queued or `dispatching` items sit in the bee-ci poll state, and no wave is awaiting attempts;
3. the launcher reports idle via its status/probe script from the launcher folder (docs/05);
4. Kyle has said yes, in his own words, to both the window (the at-once sitting, plan §4) and the launcher restart that re-registration requires — a PC launcher restart is a standing gated change (docs/06).

Inside the boundary nothing else may dispatch. The boundary stays open through the whole runtime sequence: renames → redirect verification → launcher re-registration and restart → project rows → provisioning registrations → worker remotes → cron arguments → staging merge → post-flight scan. It closes only when the post-flight scan passes.

Why the boundary exists: a repository rename orphans the launcher's project mapping mid-flight. A bee dispatched between the rename and the re-registration would be briefed against a name the allow-list no longer knows, and docs/03 records that authorizing a repo on the launcher requires a restart — while docs/05 records that restarting the launcher kills in-flight bees. The boundary is what makes the rename window safe rather than merely quick.

### 3.3 Exact post-rename restart and re-registration sequence

In order; each step verifies and records before the next starts:

1. **Launcher allow-list.** Update each authorized project entry to the new `owner/name`. Verify: the launcher's status/doctor script lists the new names and nothing else changed.
2. **Launcher restart — Kyle's explicit yes, inside the boundary.** Use the launcher folder's stop/start scripts (docs/05). Verify: the status endpoint answers, zero attempts in flight, and the allow-list shows the new names after the restart. If Docker Desktop itself had to restart (the memory-incident pattern, docs/03), the sandbox image is digest-pinned and re-pulls on next use — no extra step.
3. **bundlebees project rows.** Update each row's repo field to the new name. Verify: `bundlebees project list` shows every row carrying the new name, and the listing shows every other row unchanged (record it).
4. **hyvv provisioning registrations.** Re-register each project workspace with the new repo name in the payload (`# confirm in Step 0` for the exact endpoint contract); keep every receipt. Verify: a status read returns the new repo per project.
5. **Worker remotes.** For every checkout in the Step 0 list: `git -C <checkout> remote set-url origin https://github.com/mojomast/<new>.git`, then `git -C <checkout> remote -v` and `git -C <checkout> ls-remote origin HEAD` — both recorded per checkout.
6. **Cron.** Rewrite the poll entries' `--repo` arguments to the new names. Verify: one `poll.py --cap 0` run completes with a clean state write and no unknown-repository errors.
7. **CI self-check.** After the staging merge, the manifest names only repositories that exist: the bee-ci manifest tests pass at the merge head, and CI is green including the required contexts (docs/CI.md).

Then the boundary closes on the post-flight scan's green result (section 4, step 11). A smoke dispatch happens only when Kyle says go — the m2 canary can serve as that smoke if it is next in the queue.

### 3.4 Rule R5 — incremental commits (the workspace lesson)

Uncommitted workspace work is destroyed by worker reprovisioning; that is how the r1 runbook (`att_b470a77f`) died at the 18:02 restart. Therefore:

- the runbook and the staging branch are committed **and pushed** before the window opens — a rename session never starts with unpushed work;
- every checklist step ends with either a commit (repository work) or an evidence file written into the repository and committed (host work); no step begins while the previous step's output is uncommitted;
- host-side artifacts — the crontab backup, the settings dumps, the provisioning receipts, the redirect transcripts — are copied into the evidence directory and committed, not left on the host;
- if the workspace is destroyed mid-window, recovery is: re-clone from origin, read the runbook's evidence trail, and resume at the first step whose output is not committed. The runbook is the first customer of its own recovery path.

---

## 4. EXECUTION CHECKLIST — ordered, individually verifiable, gated

Each step names its command surface, its expected evidence and its gate. A step whose precondition is missing is recorded **NOT RUN** with the reason. Nothing runs before Step 1's gate closes.

**Step 0 — Preflight (read-only; no writes anywhere).**
Commands: the §1.2 inventory block; `git fetch origin` and record the base revision; the per-repo settings dump; the local-checkout and remote-URL list; `bundlebees status` and `bundlebees project list`; `crontab -l` backup; flag confirmation for every `# confirm in Step 0` marker in this document (`gh repo edit --help`, `bundlebees project --help`, the provisioning contract).
Expected evidence: baseline counts, an empty `git status --porcelain` (the R5 precondition), the idle-state record, the backup path.
Commit: the inventory file — before anything else (R5).
Gate: none (read-only), but the commit is mandatory.

**Step 1 — Decision gate G0.**
Kyle's explicit yes, in his own words, on D1 through D8 — with D2 (the legal and availability screening) **passed before** the D3 window date is fixed, because the names are not legally cleared until it does. His words recorded verbatim with the timestamp.
Gate: this step *is* the gate for everything below.

**Step 2 — Staging branch (bee-safe).**
Every doc and code reference change from plan §3.3 and §3.4 on one branch; a commit per file-group; pushed (R5).
Verify: the full local suite green on the branch (unittest discovery, the bee-ci test suite, the rebrand-plan and website-plan conformance tests); `git diff main --stat` small and reviewable.
Gate: no merge yet — merging waits for the boundary.

**Step 3 — Open the quiet boundary.**
Verify and record all four §3.2 conditions, plus Kyle's window yes (which covers the launcher restart; re-confirm verbally if he prefers).
Gate: his yes. If any condition fails, the window does not open.

**Step 4 — Rename `mojomast/workflow` → `flww`** (the umbrella's host goes first so the site publish lands on the final name).
Command: `gh repo edit mojomast/workflow --rename flww   # confirm in Step 0` (or Settings → General).
Verify: the §2.2 block for this repo; the settings diff is clean — rulesets and required contexts intact.
Evidence + commit before Step 5 (R5).

**Step 5 — Rename `mojomast/bundlebees` → `bzzq`.** Same command shape, same §2.2 verification, same commit rule.

**Step 6 — Rename `mojomast/orbitdesktop` → `orbt`.** Same.

**Step 7 — The non-renames, verified on the record.** `gh repo view mojomast/hyvv --json name` (expect `hyvv`), the same for `mojomast/rizzstack` (already the umbrella name), and `orbit-control-plane` only as far as D1 decided — renamed with full verification, or recorded as staying. The record shows these were considered, not forgotten.

**Step 8 — Redirect and caller sweep.** The §2.2 block for every renamed repo, then the §2.3 caller rows one by one — Pages URLs fetched, raw links spot-checked, the API-by-name callers listed against their fix commitments.
Expected evidence: one PASS row per caller; any broken raw link found is fixed on the staging branch before the merge.

**Step 9 — Re-registration (the §3.3 sequence, all seven sub-steps in order, each verified and recorded).**
Gate: the launcher restart inside it needs Kyle's yes — given with the window or re-asked here.

**Step 10 — Merge the staging branch; run the reference-update pass.**
Verify: full suite, bee-ci tests and the plan-conformance tests green at the merge head; the manifest names only repositories that exist; CI green on the merge commit with the required contexts satisfied (docs/CI.md).
Gate: the merge is a standing gated change — covered by Kyle's window approval or re-asked.

**Step 11 — Post-flight scan and acceptance.** The §1.2 commands again, over the merged tree; the §2.4 acceptance measured and recorded; every §2.2 redirect row re-verified after all changes settle. Evidence committed.

**Step 12 — Umbrella launch** (plan §4.4; docs/website-plan.md §6): build, public-safe scan zero hits, link check, loopback preview, Kyle's publish yes, publish under the new repo name, deployed revision recorded.
Gate: the publish is its own explicit yes (docs/06).

**Step 13 — Closeout.** Catalog PR posture per plan §3.2 (default: leave open PRs, record the rename in the closeout); the campaign record and chapter record updated with the new names and formerly-the-old-name pointers; every rollback command from §1.3 archived beside the evidence, so the rollback story stays executable after the fact.
Gate: none — but the closeout is what makes the window auditable.

---

## 5. Self-check

- The four mandatory sections exist above, in order: recovery path (§1), same-place mapping (§2), parallel operation (§3), execution checklist (§4).
- Every row of the §1.3 inventory carries an exact restore command or an explicit, reasoned n/a.
- The §2.1 map covers every repository and identity surface; the §2.3 table covers every caller class, including the ones a redirect cannot save.
- §3.2 names the quiet boundary as a checked condition list, and §3.4 carries the workspace-destruction lesson as an executable rule, not a note.
- This document contains no secret-shaped values, no private hosts and no live data, and every command is either documented in this repository or marked `# confirm in Step 0`.
