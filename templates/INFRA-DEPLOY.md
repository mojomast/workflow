# Infrastructure deploy

Use for one authorized change to a live host. This is a task checklist, not an approval record; record Kyle's instruction and scope explicitly.

## Authorization and scope

- Host and service:
- Kyle's instruction and date:
- Authorized actions (build, stop/start, switch container, disable timer):
- Not authorized (other sites, nginx, firewall ranges, deletes, pushes):
- Source of truth and exact revision/tag/SHA:

## Preflight

- OS and init system:
- Existing services and listeners (`ss -ltn`, `docker ps`):
- DNS result and certificate renewal path:
- Current version, image, container and restart policy:
- Disk and backup target:
- Port chosen and reason:
- Blockers or stop conditions:

## Backup

- Directory:
- Env copy (mode 0600):
- `docker inspect` snapshot:
- SQLite `.backup` and `quick_check`:
- Old image tag:
- Old container/image retained as:

## Change

- Build command and tag:
- Env keys changed (names only):
- Config check:
- Stop, rename and start commands:
- Firewall change:
- Other services left untouched:

## Verification

| Check | Command or input | Expected | Result |
|---|---|---|---|
| TLS hostname and chain | | | |
| Real protocol or user path | | | |
| Admin CLI | | | |
| Data counts | | | |
| Schema or columns | | | |
| Stability and log scan | | | |
| Timers | | | |

- Before/after counts: accounts, boards, posts, threads:
- Schema or columns added:
- 60-second stability and log result:
- Timer states (changed and untouched):
- External check, when possible:

## Rollback

- One command:
- Database restore source:
- Env restore source:
- Old container/image:
- Timer to re-enable:

## Report

- Paths only for secrets:
- Deviations from the runbook:
- Unproven or unavailable checks:
- Next action and owner:
