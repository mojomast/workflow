# 11 — Working together: the recurring operating rhythm

This is the practical companion to [09](09-reproducible-collaboration.md). Chapter 09 describes how an artifact moves from outcome to evidence. This chapter describes how Kyle and an agent run a session when the work touches a live host, a shared service or an existing repo — the habits that keep a change reviewable and reversible.

## 1. Kyle's side of the contract

Kyle usually brings:

- a concrete outcome and a named source of truth (repo, tag, README or config);
- a runbook with exact revisions, ports, paths and forbidden actions;
- the approval boundary: what is allowed now and what still needs his words;
- a preference for the smallest change that proves the outcome.

He does not want an agent to broaden scope because a step looks inconvenient. If a step is wrong or unsafe, report the conflict and the protocol-correct alternative; do not silently rewrite the goal.

## 2. The agent's side

The default sequence:

1. Read the source of truth before touching the host.
2. Preflight read-only: OS, init, existing services, listeners, DNS, certificate path, disk and current revision.
3. State the plan and any blocker. Stop before mutation if the change would touch an unrelated service or an ambiguous owner.
4. Back up and record the rollback before changing state.
5. Change only the named surface. Preserve the previous container, image, env and database backup.
6. Verify the real path, not just process liveness.
7. Report paths, evidence, counts, deviations and the rollback command.

## 3. Stop and ask

Stop when:

- DNS does not point at the intended host;
- the requested port is taken or the bind would collide;
- the change would restart or reconfigure a shared web server, database or another site;
- two deployment methods are plausible and the choice changes blast radius;
- a credential is missing, or a command would print a secret;
- a backup cannot be verified;
- the instruction conflicts with the protocol or with the source of truth;
- deleting or rewriting anything that was not created in this session.

An existing service is not a test fixture. "Leave it untouched" includes not reloading it to pick up an unrelated certificate.

## 4. Secrets

- Secrets live in root-owned env files or secret scopes, mode 0600.
- Never print, diff or paste env contents, tokens, claim tokens or keys. Verify by key name and file path.
- Generated bootstrap credentials are written once to the protected file; report the path only.
- Tests use throwaway accounts and discard their tokens. Do not put tokens in shell history, logs or a final report.
- A plan that needs a secret on a command line is the wrong plan; use a file or stdin.

## 5. Shared-host etiquette

- Use the host's existing supervisor: systemd units and timers on the VPS, `boxctl` on the box.
- Do not use a broad restart to apply one app's change.
- Keep TLS renewals isolated per app when the host has a global deploy hook.
- Publish one application port; do not change unrelated firewall rules.
- Keep old containers and images until the replacement is accepted.
- Do not delete other agents' work, branches, containers, volumes or backups.
- Docker access is root-equivalent; use it for the authorized change, not as a general escape hatch.

## 6. Verification and report

Prefer the user's real path:

- TLS: hostname validation and chain from `openssl s_client`;
- protocol: one real framed request with a structured response;
- admin: the actual CLI help or command;
- data: before/after counts and a schema diff, never token columns;
- stability: the service stays up for a stated interval and the logs have no traceback;
- background jobs: timer states and one successful run.

Report in this shape: method/version, port and paths, every check with pass/fail/not-run, before/after counts, timers touched, deviations from the runbook, and a copy-paste rollback command. Distinguish "the process started" from "the user path works."

## 7. What carries forward

A session is reusable when the next person can answer: which revision, which host, which port, which files, which backup, which checks, which approval, which rollback. Put those in the [infrastructure deploy template](../templates/INFRA-DEPLOY.md) or the [handoff template](../templates/HANDOFF.md) rather than relying on chat history.

When a host-side workaround becomes unnecessary because the app now supports the feature, remove the workaround from the runbook and record the change. The HBBS auto-approver is the example: the host timer was retired when `HBBS_SIGNUP_MODE=auto` made it redundant.
