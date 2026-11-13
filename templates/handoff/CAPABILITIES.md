# What the incoming coordinator can and cannot do (recon)

Recon at `<DATE, TIME, ZONE>`, `<read-only / after install>`. Re-run after every install or restart.

| Area | Finding |
|---|---|
| Runtime | `<VERSION, INSTALL STYLE, GATEWAY HEALTH>` |
| Models | `<DEFAULT MODEL AND PROVIDER. KEY NAMES ONLY, NEVER VALUES>` |
| Plugins enabled | `<NAME AND VERSION. NOTE DISABLED ONES TOO>` |
| Dispatch plugin | `<INSTALLED SHA, ADAPTER / SETTINGS NAMES ONLY, HEALTH CHECK RESULT CODES. NO URLS OR TOKENS>` |
| Forge CLI | `<ACCOUNT, SCOPES, WHETHER IT *COULD* MERGE OR CHANGE PROTECTION — AND THAT THE RULES STILL APPLY>` |
| Secret scanner | `<TOOL, VERSION, HOW THE BINARY WAS VERIFIED>` |
| Local clones | `<DIRECTORY PATTERN, FETCHED REPOS, TEST ENV>` |
| Worker host | `<REACHABLE OR NOT. UNAUTHENTICATED = DENIED, AUTHENTICATED = SUCCESS? SETUP STILL PENDING?>` |
| Control surface | `<WHAT ALREADY RUNS ON THIS HOST. ANY DEPENDENCY ON THE OUTGOING SURFACE?>` |
| Sandbox | `<CAN VERIFY/INTEGRATE RUN HERE? IF NOT, THE REFUSAL AND THE FALLBACK PLAN>` |
| Scheduling | `<HOW CRON RUNS, JOB NAMES, CADENCE. DO NOT DUPLICATE>` |
| Messaging | `<HOW THE APPROVER REACHES YOU. WHETHER PROACTIVE PINGS ARE WANTED>` |
| Headroom | `<DISK, MEMORY, CPU, LOAD>` |

## Worker-host admin (if approved)

- Scope approved: `<LIST, ADD, REMOVE PROJECTS? IDLE-SWAP RESTART ONLY?>`
- Who is setting it up: `<PEER>`
- Usable yet: `<YES / NO>`

## Merge-watch behaviour (if present)

Merges only `<THE VERBATIM APPROVED SET, IN ORDER>`. Each merge requires: PR open (skip if already merged), not draft, base `<BASE>`, every check on the exact head = success (no skipped/queued), merge state clean, predecessor merged, at most one merge per run, match the checked head, never an admin bypass. Extra markers: `<FILE AND WHAT IT ATTESTS TO>`. A skipped check blocks auto-merge.

## Dependency audit (outgoing control surface)

| Item | Depends on the outgoing surface? | Action |
|---|---|---|
| Scheduled scripts | | |
| Dispatch-plugin settings | | |
| Environment variables (names only) | | |
| Skills | | |
| Board / task queue / worker history | | |
| Artifact or patch retrieval | | |
| Observability / evidence views | | |
| Files only on the outgoing machine | | |
