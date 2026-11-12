# Four-layer acceptance report

Run 2026-11-12T17:38:24-0500 to 2026-11-12T17:38:33-0500.
**Final acceptance: NOT ACCEPTED**

## Revisions

- workflow: `ab21f588e0d53d1810ab5bc8f560d48e616e57d0` (base ab21f58)
- hyvv: `28ad423d63913245e46f0c6ebaa89c8d011f9222` (base 28ad423)
- bundlebees: `46a8d20f61b74cdd54f6b2c56d040ec69f353922` (base 46a8d20; merge 750b10b CONFLICT ['bundlebees_plugin/acdd_cli.py', 'bundlebees_plugin/sandbox.py'])
- orbitdesktop: `2bc883af597cdce491b332f8f7f2e8dfd49a6b58` (base 96916aa; merge d08b8f6 ok; merge d7cf47a ok)

## Steps

| # | Step | Component (real code, scripted worker) | Final |
|---|---|---|---|
| 1 | Fresh Orbit deployment and initial agent setup | **passed**: S1/S5 probes refused every unauthenticated approval and default grant | **unrun**: fresh container deployment + first-agent onboarding not executed by this runner (needs the docker compose path of Orbit #25 on a clean host); routes were run from the checkout instead |
| 2 | Compatible hyvv host advertising its actual capabilities | **blocked**: hyvv 0.1.15 answers /v1/health but /v1/version is 404: capability advertisement is specified, not implemented | **blocked**: hyvv 0.1.15 answers /v1/health but /v1/version is 404: capability advertisement is specified, not implemented |
| 3 | Coordinator-authenticated worker dispatch | **failed**: bundlebees -> Orbit (board key) -> hyvv (bearer); signed leases, 0600 capabilities; parallel states {'A1': 'superseded', 'A2': 'succeeded'}; re-dispatched sequentially -> {'A1': 'succeeded', 'A2': 'succeeded'} | **blocked**: parallel dispatch supersedes attempts (FL-2) |
| 4 | Frozen ACDD contract with collected test IDs | **blocked**: pinned bundlebees freezes without collecting test ids (C1 lives in bundlebees #12, not in this build) | **blocked**: pinned bundlebees freezes without collecting test ids (C1 lives in bundlebees #12, not in this build) (contract step needs no worker) |
| 5 | Genuine, independently recorded RED evidence | **passed**: verifier recorded signed behavioral RED at source_rev in the sandbox | **passed**: verifier recorded signed behavioral RED at source_rev in the sandbox (RED needs no worker) |
| 6 | At least two parallel real-agent workers | **unrun**: scripted worker (hyvv FakeBackend + diff): component evidence only, never final | **unrun**: real-agent mode not run: see README 'When to run --real-agents' |
| 7 | Enforced file ownership and refusal of an out-of-scope attempt | **passed**: A2 edited shop/labels.py outside its lease and was refused with scope_violation | **unrun**: needs --real-agents |
| 8 | Authenticated worker artifact retrieval | **passed**: shared board key without capability -> 403 send the attempt artifact_capability from create; forged capability -> 403; owner capability -> artifact | **unrun**: needs --real-agents |
| 9 | Patch integrity and source revision checks | **passed**: verify fetched A1 via Orbit, patch_sha256 matches the scripted diff, source_rev pinned | **unrun**: needs --real-agents |
| 10 | GREEN, REFACTOR and independent REVIEW | **passed**: GREEN rc 0, REFACTOR(--none) rc 0, REVIEW rc 0; review is the runner, not an independent human | **unrun**: needs --real-agents and an independent reviewer |
| 11 | Successful sandboxed combined integration | **passed**: combined branch integrated in the sandbox | **unrun**: needs --real-agents |
| 12 | Accurate token, cost and failure metrics | **passed**: attempts_dispatched=3 (events 3); tokens null | **unrun**: needs real usage from real workers |
| 13 | Trustworthy evidence view in Orbit | **blocked**: Orbit verified 5 signed records but cannot show acceptance: bundlebees reports accepted on stdout only and writes no signed reports/<id>.json for Orbit to verify | **blocked**: Orbit verified 5 signed records but cannot show acceptance: bundlebees reports accepted on stdout only and writes no signed reports/<id>.json for Orbit to verify |
| 14 | Human authorization separate from technical acceptance | **blocked**: report does not state human authorization at all (needs bundlebees #12 semantics) | **blocked**: report does not state human authorization at all (needs bundlebees #12 semantics) |

## Findings raised by this run

- **MERGE-bundlebees** (high): merge candidate conflict: 750b10b in bundlebees_plugin/acdd_cli.py, bundlebees_plugin/sandbox.py; built without it
- **FL-2** (high): Parallel dispatch through Orbit is impossible from bundlebees: OrbitAdapterClient sends no task_id (only kanban_task_id), Orbit keys attempts by task_id, so every task-less attempt shares task_id=undefined and each new dispatch supersedes and cancels the previous active one (here ['A1']). Owners: bundlebees #9 client + Orbit #28 create.
