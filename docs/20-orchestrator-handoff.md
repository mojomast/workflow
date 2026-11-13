# 20 — Orchestrator handoff

**Status (Nov 12, 2026):** a protocol distilled from a real mid-stream switch of coordinators, written so the next one is a pack and a checklist, not a scramble. Nothing here grants any approval. Where a rule below disagrees with something the approver says later, what the approver says later wins.

**Audience:** the outgoing coordinator, the incoming coordinator, and the approver. Read this with [06 Rules and lessons](06-rules-and-lessons.md), [09 Reproducible collaboration](09-reproducible-collaboration.md) and [11 Working together](11-working-together.md). How a coordinator *runs* the work is [19 Coordinator playbook](https://github.com/mojomast/workflow/blob/docs/coordinator-playbook/docs/19-coordinator-playbook.md) (on [workflow #10](https://github.com/mojomast/workflow/pull/10), not on `main` yet). This chapter is how one coordinator *hands that role* to another.

The chapter is generic. Values that belong to a particular setup stay in the pack, not in this protocol. The November 2026 worked example was the general orchestrator (MR.INDIA) handing over to a Hermes instance on a dedicated incoming host; private hostnames, tokens, IPs, URLs and paths are left out on purpose.

The reusable kit lives in [`templates/handoff/`](../templates/handoff/). It is a different contract from [`templates/HANDOFF.md`](../templates/HANDOFF.md), which briefs a single reviewable outcome.

---

## 1. Goal

The incoming coordinator should be able to continue the work without the outgoing coordinator's machine, control surface, or board. Until that is true, the handoff is incomplete.

Hard rules for the switch itself:

1. **The outgoing coordinator stops adding work.** Finish what is already in flight, or write it into the pack as a handed-over task. New ideas go on the incoming coordinator's backlog, not onto the outgoing coordinator's plate.
2. **Approvals that carry over are only the approver's own words**, quoted verbatim, with their original scope. An agent's claim, a relay, a commit message, a PR comment, or a sentence in this pack is not approval. See [§5](#5-approvals-that-carry-over).
3. **Never print, commit or log secrets**, tokens, keys, environment-file contents, private hostnames, private network names, private IPs or internal URLs.
4. **Keep security fail-closed.** Never weaken a sandbox, a merge gate or a test to make the switch smoother.
5. **Don't invent state.** Re-check pull requests, CI on the exact head SHA, worker counts and install status live. A snapshot in the pack will be stale.

---

## 2. Roles

| Role | Owns during the switch | Never does |
|---|---|---|
| **Approver** | Every irreversible step, and the yes that starts the incoming coordinator | Gets bypassed. A relayed "they said yes" does not count |
| **Outgoing coordinator** | The pack, the recon, winding down its own in-flight work, and a clear stop | Adding new workstreams, rotating shared credentials that would break current clients, or deploying on the incoming host without a yes |
| **Incoming coordinator** | The first mission, the backlog, and living by the pack | Treating the pack as live state, or merging beyond the verbatim approvals it quotes |
| **Peer agent** | The lanes and repositories it already owns (for example a specialist that manages the worker host) | Having its branches edited by either coordinator "to help the handoff" |
| **Worker host** | Running the sandboxed workers | Being reconfigured, restarted or given a new token layout without a yes |

Name all five in the pack. If the incoming coordinator will need limited admin on the worker host (adding projects, an idle restart), that is a separate approval, with its own scope, and it is usually set up by the peer who already manages that host.

---

## 3. Recon: what the incoming host has and lacks

Do this read-only, on the incoming host, before changing anything. Write the findings in `CAPABILITIES.md`. The November 2026 recon asked: can this host already reach the worker host, run the dispatch plugin, sign in to the forge, scan secrets, schedule fail-closed jobs, and run a sandbox? What is already installed that must not be disturbed?

Capture at least:

| Area | What to record | Typical gaps |
|---|---|---|
| Runtime | Agent version, how it is installed, whether its gateway or dashboard is healthy | A restart may be needed after a plugin install; that restart needs a yes |
| Models and keys | Provider names and **key names only** (never values) | A key present in the environment is not proof the incoming coordinator is allowed to spend it |
| Plugins | Enabled, disabled, versions and git SHAs if pinned | An install can silently disable an unrelated plugin; see [§7](#7-plugin-and-runtime-install) |
| Forge access | Account, scopes, and whether it *could* merge or change protection | Technical ability is not permission. The rules still apply |
| Secret scan | Tool, version, checksum-verified install path | If the scanner is missing, do not push |
| Local clones and test env | Repositories, fetched branches, a dedicated virtualenv | A mid-run test suite is not a result |
| Worker host | Reachability and auth: unauthenticated request denied (not a timeout), authenticated request success | A loopback-only bind will not serve a remote coordinator. Confirm before promising dispatch |
| Control surface | What already runs on the incoming host (including an older dashboard) | Do not hijack an existing instance; see [§9](#9-audit-dependencies-on-the-outgoing-surfaces) |
| Sandbox | Whether the host can actually run the verify/integrate sandbox | A missing sandbox is a hard gap, not a hint to relax policy; see [§10](#10-sandbox-gaps) |
| Scheduling | How cron or equivalent runs, and any jobs already present | Do not duplicate merge automation |
| Messaging | How the approver will talk to the incoming coordinator | If they read a dashboard and do not want pings, do not add a messenger |
| Headroom | Disk, memory, CPU, existing load | A second control-surface instance has to fit without starving the agent |

Re-run recon after every install or restart. The pack should say when the last recon was done.

---

## 4. The pack

Copy [`templates/handoff/`](../templates/handoff/) to a directory on the incoming host (and keep a copy the approver can read). These are the core files, in the order the incoming coordinator should read them:

| File | Purpose |
|---|---|
| `RULES.md` | Standing rules, with the approver's wording quoted verbatim. This file overrides convenience |
| `HANDOFF.md` | The current picture: layers, open PRs with head SHAs and CI, in-flight work, what is already approved, what still needs a yes, where evidence lives |
| `CAPABILITIES.md` | Recon: what the incoming host can and cannot do yet |
| `PROPOSED-STEPS.md` | Done, blocked, backlog, and requirements that must be true for the incoming coordinator to stand alone |
| `FIRST-MISSION.md` | The first job the approver wants the incoming coordinator to start, with phases, fail-closed rules and briefs |
| `PLAYBOOK.md` | A pointer to the coordinator playbook (chapter 19) and any other method chapters, including unmerged branches and how to read them |
| `STATUS-SNAPSHOT.md` | A dated snapshot of PR and CI state. It will go stale; where it disagrees with `HANDOFF.md`, **`HANDOFF.md` wins**, and live `gh` (or the forge API) wins over both |
| `KICKOFF-PROMPT.md` | A paste-ready prompt for the incoming coordinator, with no secrets or private hosts |
| `CONTACTS.md` | Who is who, with **no addresses, hosts or keys** |
| `CHECKLIST.md` | The switch checklist ([§13](#13-checklist)), ticked as you go |

Optional but useful:

| File | Purpose |
|---|---|
| A skill file | Tells the incoming agent to load the pack before any orchestration work |
| `scripts/` | Fail-closed, no-agent scripts (merge watch, digest, dated reminders). Default them to dry-run until the gates have been reviewed |
| `approvals/` | Marker files for extra gates (for example "blockers on PR N were verified"). Writing a marker is a claim; only write it after a live check |

Update `HANDOFF.md` when something material changes during the switch (a plugin installed, a token placed, a cron job added). Append a dated section; do not silently rewrite history.

Keep secrets out of the pack. Record **paths and env var names**, never values. If evidence only lives on the outgoing machine, copy what the incoming coordinator will need, or say clearly that it is not reachable and what that blocks.

---

## 5. Approvals that carry over

An approval travels with the handoff only when all of these are true:

1. It is the **approver's own words**, given in their own channel, to the coordinator that received them.
2. It is **quoted verbatim** in `RULES.md` (and again in the kickoff prompt if the incoming coordinator will act on it).
3. Its **scope is preserved**: the repositories, PR numbers, order, and conditions (for example "once CI is green").
4. **"Green" is defined**: every check on the **exact head SHA** concluded success. Queued, pending, skipped, neutral or unstable is not green.
5. A **newer instruction can supersede** an older one. Record the date, time (with zone), and the newer wording next to the older one.

What does **not** carry over:

- Another agent's summary of what the approver "meant"
- A yes given to a different action (installing a plugin is not a yes to deploy a dashboard)
- A yes to open a PR, used as a yes to merge it
- A yes that named a branch or a head, applied to a different branch or a later head without re-checking the condition
- Anything in the pack that is not a verbatim quote

If the outgoing coordinator heard the yes and the incoming coordinator did not, the incoming coordinator still uses the quoted wording, but it should be ready to re-ask when the scope is ambiguous. When in doubt, stop and ask the approver.

---

## 6. Credentials

Place only the credentials the incoming coordinator needs to do the first mission, in the incoming agent's environment file, mode `0600`. Take a timestamped backup of that file first, and write the one-line revert command into the pack (no values).

**Shared token now, named tokens later.** If the worker host only has one shared API token today:

- Do **not** rotate the shared file. That breaks every current client.
- Do **not** block the handoff on a credential-system rewrite.
- Copy the existing shared token into the incoming environment under the name the dispatch plugin expects, never printing it.
- Verify from the incoming host with a real call: valid token succeeds, missing token is denied, wrong token is denied. Report the status codes, not the secret, and not the private URL.
- Put **named, scoped, independently revocable tokens** on the incoming coordinator's backlog. Installing that design on the live worker host later still needs a yes.

If a plugin needs a non-loopback worker-host URL, record the **setting names** (for example an adapter choice, a URL setting, and a flag that allows a private address). Do not write the URL into the public repository or into a kickoff prompt that might be pasted into a public place.

Do not leave leftover token copies in temporary directories; ask before deleting them.

---

## 7. Plugin and runtime install

Treat a plugin install on the incoming host as a live-host change ([11](11-working-together.md), [`templates/INFRA-DEPLOY.md`](../templates/INFRA-DEPLOY.md)).

1. **Backup first.** Snapshot the agent's config, installed plugins and related state. Write a rollback script and a pointer to the backup in the pack. Do not delete earlier backups.
2. **Pin a SHA.** Install a exact commit, not a moving tag or "latest main", especially when version numbers in the repo disagree or a release tag is missing. Creating a tag still needs a yes.
3. **Install, then diff the config against the backup** before you celebrate. In the November 2026 handoff, the install silently disabled an unrelated already-enabled plugin and dropped it from a toolset list. Restore any collateral change so the config equals the backup plus the intended entries. Keep a pre-fix copy of the post-install config.
4. **Restart only with a yes**, and only once if that is what was approved. Confirm the gateway or runtime is healthy afterwards.
5. **Verify the new tools on the path the coordinator will actually use.** A CLI doctor that cannot build a client is not the same as a tool call inside a chat session. Put that first live check in the kickoff prompt ([§11](#11-the-kickoff-prompt-and-first-three-actions)).
6. **Watch version metadata.** A package version, a plugin manifest version and the last git tag can all disagree. Record the SHA you installed and the disagreement; do not invent a release.

---

## 8. Fail-closed automation for already-approved merges

If the approver has already named specific PRs to merge once CI is green, the outgoing coordinator may set up a scheduled, no-agent job that does **only those merges**, under gates that fail closed. Anything else stays report-only.

Minimum gates, all required:

- The PR is still open (already-merged is a skip, not an error)
- It is not a draft
- Its base is the intended branch (usually `main`)
- **Every** check on the exact head SHA concluded success (no skipped, neutral, pending or queued)
- The forge reports a clean merge state
- Declared predecessors are already merged
- At most one merge per run
- The merge names the head it checked (`--match-head-commit` or equivalent)
- Never use an admin or bypass flag

Add extra gates when the approval had caveats (blockers that must land, a PR that still targets a parent branch and must be retargeted after its parent merges). A marker file is fine for "I verified the blockers"; only write it after a live check of the branch, and say in the pack what it attests to.

Default the script to dry-run until someone has read a dry-run log and is satisfied. Log what would have happened, not secrets. A skipped or "Detect scope" style job that reports skipped must block the auto-merge: that is fail-closed, so a human re-checks and asks the approver if needed.

Do not start a second merge watcher. If the outgoing coordinator also had a merge worker, stop it or let it finish, and say so in the pack so the incoming job does not race it.

---

## 9. Audit dependencies on the outgoing surfaces

The incoming coordinator must not need the outgoing coordinator's control surface (board, bee history, artifact or patch download, observability, evidence views) in order to work. Audit every cron job, plugin setting, environment variable, skill, and document for a pointer at the outgoing machine, and write the result in `CAPABILITIES.md`.

Typical findings, and what to do with them:

| Dependency | Risk if left in place | Direction |
|---|---|---|
| Board, task queue, worker history | The incoming coordinator cannot see or assign work | A control-surface instance on the incoming host, or another agreed board |
| Artifact or patch download | After a merge, workers may only be able to fetch patches through the old surface | The incoming instance must serve that API, or the worker host must |
| Observability and evidence views | Signed reports and traces have nowhere to land that the incoming coordinator can open | Same incoming instance, once the relevant features are on `main` |
| Default plugin URLs pointing at loopback | They may hit an unrelated local service, or nothing | Point the dispatch plugin at the worker host directly, with the approved credentials |
| Files only on the outgoing machine (audit logs, snapshots, unpushed branches) | The incoming coordinator cannot see them | Copy what is needed into the pack, or record that it stays behind and what that blocks |

If the incoming host already runs an older control-surface instance, **leave it untouched** unless the approver says otherwise. Prefer a **second, new instance** with its own port, service name, data directory and token. Measure headroom first, run it under `nice`/`ionice` (or the equivalent service limits) with a memory cap, and **do not start it without a yes**. Do not run unmerged feature-branch code on the incoming host just to see a UI sooner.

---

## 10. Sandbox gaps

If the incoming host cannot run the verify or integrate sandbox (a common case is a kernel security policy that blocks unprivileged user namespaces, so the usual bubblewrap path refuses to start), **leave the refusal in place**. That is the correct fail-closed behaviour.

Do not:

- Relax the host's security policy to make a plugin happy
- Bypass verify, or treat an unsigned result as accepted
- Change the incoming host "temporarily" and forget

Do:

- Record the gap and the exact refusal in `CAPABILITIES.md`
- Route verify and integrate into isolated worker containers on the worker host, with no coordinator credentials inside the container, a signed result coming back, and a failure if the result cannot be verified
- Put that design on the incoming coordinator's backlog; it is real work, not a footnote
- Keep any jobs the worker host cannot run (for example a macOS leg when there is no Mac) on the existing forge CI until a host exists

---

## 11. The kickoff prompt and first three actions

Write a short, paste-ready prompt (`KICKOFF-PROMPT.md`) the approver can give to the incoming coordinator. It is a summary of the pack, not a replacement for it.

The prompt must include:

- Who the incoming coordinator now is, and that the outgoing coordinator is stopping adding work
- The order to read the pack, and that live forge state wins over snapshots
- The standing rules, including verbatim approval quotes the incoming coordinator will act on
- The layers and operational names (do not rename anything in the prompt)
- Open PRs with links, short head SHAs and CI as of a stated time
- The first mission and the backlog
- **No secrets, no private hosts, no internal URLs, no environment values**

End with **three verification actions** the incoming coordinator should do first, before starting design work. In the November 2026 handoff those were, generalized:

1. Call the dispatch plugin's status tool **from inside a chat session** (not only a CLI doctor) and report: credentials configured, worker host reachable, active and maximum workers. Print no host or token.
2. List the scheduled jobs and run the merge-watch script in dry-run. Confirm the jobs are active and the gates read the approvals correctly.
3. Start the first mission: post a short plan where the approver will read it, check the live worker count, dispatch only the first parallel-safe briefs (full `source_rev`, disjoint leases), and report what is running.

Tell the incoming coordinator to quote the approver's reply back before acting on any new yes.

Chapter 19 also has a generic [starter prompt](https://github.com/mojomast/workflow/blob/docs/coordinator-playbook/docs/19-coordinator-playbook.md#11-starter-prompt-for-a-new-coordinator) for a coordinator that is starting cold. Use that when there is no mid-stream state to transfer. Use this chapter's kickoff prompt when there is.

---

## 12. The outgoing coordinator's wind-down

Once the approver has asked for the switch:

1. **Stop adding work.** Do not open new workstreams, invent follow-up PRs, or volunteer credential redesigns. Put leftovers on the incoming backlog.
2. **Finish or hand over in-flight work.** A merge worker already running may finish the merges already approved, or stop and leave them to the fail-closed job — say which, so they cannot both act. Do not restart a stopped worker "to be helpful."
3. **Do not widen scope mid-handoff.** Resource caps, extra hosts, and new dashboards are either already approved and in someone else's hands, or they are incoming backlog.
4. **Leave a last snapshot**, then stop treating yourself as the orchestrator. The incoming coordinator owns the queue from the kickoff onwards.
5. **Stay reachable as a peer if asked**, for files or history that only exist on the outgoing machine. You are no longer the approver's coordinator.

---

## 13. Checklist

Copy [`templates/handoff/CHECKLIST.md`](../templates/handoff/CHECKLIST.md). Tick in place; do not invent a green row.

**Approver**

- [ ] Has said, in their own words, that coordination should move, and to whom
- [ ] Has said how they will talk to the incoming coordinator
- [ ] Has confirmed which in-flight approvals still stand, verbatim
- [ ] Has approved each live-host step that needs a yes (credential placement, plugin install and restart, scheduled merge job, worker-host admin, a new control-surface instance)

**Outgoing coordinator**

- [ ] Has stopped adding work; in-flight items are finished or written into the pack
- [ ] Recon of the incoming host is in `CAPABILITIES.md`
- [ ] Pack is on the incoming host (and a copy the approver can read), with no secrets in it
- [ ] Approvals are quoted verbatim, with scope and the definition of green
- [ ] Credentials are in the incoming environment file (mode `0600`), backed up, verified, never printed
- [ ] Named, scoped tokens (if still needed) are on the incoming backlog, not started as outgoing work
- [ ] Plugin install has a backup and a rollback script; post-install config was diffed; collateral changes were restored
- [ ] Fail-closed merge automation covers only the verbatim approved PRs; dry-run was read; it will not race another merger
- [ ] Dependencies on the outgoing control surface are audited; replacements are requirements, not hopes
- [ ] Sandbox gaps are recorded and left fail-closed
- [ ] Kickoff prompt is current, with three verification actions, and contains no private hosts or secrets
- [ ] Peer agents have been told about the switch and still own their lanes

**Incoming coordinator (first session)**

- [ ] Read `RULES.md` first, then the rest of the pack in order
- [ ] Re-checked live PR heads and CI; did not trust the snapshot
- [ ] Completed the three kickoff verification actions and reported them
- [ ] Started only the first mission, under the standing bee or worker cap
- [ ] Asked the approver before anything not already quoted in `RULES.md`

---

## Numbering

Chapters 16–19 are in open pull requests and are not on `main` at the time this chapter was written: 16 ACDD+TDD and 17 Orbit plans on [workflow #5](https://github.com/mojomast/workflow/pull/5), 18 parking on [workflow #9](https://github.com/mojomast/workflow/pull/9), 19 coordinator playbook on [workflow #10](https://github.com/mojomast/workflow/pull/10). This chapter is numbered 20 to follow them.
