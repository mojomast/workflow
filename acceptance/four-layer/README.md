# Four-layer acceptance (workflow + hyvv + bundlebees + Orbit)

This runner checks the rizzstack mission's 14 acceptance steps against **pinned merge
candidates** of all four repositories. It reports every step as `passed`, `failed`,
`unrun` or `blocked`, with a reason. It never merges, pushes, tags, deploys, or touches a
live Orbit or launcher.

```
python3 acceptance/four-layer/run.py --out /tmp/four-layer
```

Needs: git, Node 22+ on `PATH` (`node --experimental-strip-types`), bubblewrap, and a
Python with `pytest`, `pyyaml`, `ruamel.yaml`, `tiktoken`, `fastapi` and `httpx` (the
bundlebees test dependencies). Use `--src repo=PATH` to run a local checkout as-is.

## What is real and what is scripted

| Layer | In the component run |
|---|---|
| Orbit | The real `server/local-workers-route.mjs` and `server/acdd-evidence-route.mjs` from the pinned merge candidate, served on a loopback ephemeral port by `orbit_stack.mjs` |
| hyvv | The real `launcher.py` runtime from the pinned hyvv revision (HTTP `/v1`, bearer auth, queue, result manifest), on loopback, via `hyvv_host.py` |
| Worker | **Scripted**: hyvv's own `FakeBackend` plus a fixed diff per brief. No model runs |
| bundlebees | The real plugin (dispatch tool, signed leases, capability-bound Orbit client, `verify`, `tdd`, `integrate`, metrics) in the real bubblewrap sandbox |
| workflow | Provides the ACDD contract shape and this runner |

So each step gets two verdicts:

* **component**: the wiring between the four real code bases, driven by a scripted
  worker. It can show that a step *fails* or is *blocked*. It can never pass the final
  step.
* **final**: the acceptance verdict. A worker-dependent step only passes in a run with
  real-agent workers. A scripted worker result, or one reconstructed by hand, is never
  accepted as final evidence (mission §10). Steps that need no worker (freeze, RED) carry
  their component verdict into the final column.

A step whose capability has not shipped in the pinned revisions is `blocked`, never
`passed`.

## The matrix

`matrix.json` pins one merge candidate per repo: a base plus local merges. A conflict is
recorded as a finding and the repo is built without that merge. Every step lists the PRs
that provide it. Update the SHAs as PR heads move. The report records exactly what ran.

## `--real-agents`

This mode is refused for now. A real-agent run is only worth its bee cost once the
blockers below are fixed, because until then it cannot pass anyway. When enabled it must:

1. use the existing launcher only (no restart or reconfiguration), with at most 2 bees;
2. read the active attempt count first and refuse if the shared 12-bee cap would be
   exceeded;
3. run Orbit from the merge candidate on a non-default loopback port;
4. never print the launcher token.

## Latest component run (2026-11-12)

See [`results/2026-11-12-component-run.md`](results/2026-11-12-component-run.md). Final:
**not accepted**. Blockers it found:

* **Step 2:** hyvv 0.1.15 has no `/v1/version`, so capability advertisement is
  specified but not implemented.
* **Step 3:** parallel dispatch through Orbit supersedes attempts (FL-2). The
  bundlebees client sends no `task_id`, so Orbit treats every task-less attempt as the
  same task and cancels the previous active one.
* **Step 4:** the bundlebees C1 work (#12) conflicts with the #9/#10/#11 line in
  `acdd_cli.py` and `sandbox.py`. No single bundlebees build has collected test IDs and the
  capability client.
* **Step 13:** Orbit verifies the signed evidence records but can never show acceptance.
  bundlebees prints its acceptance report and never writes a signed `reports/<id>.json`.
* **Step 14:** the pinned bundlebees line does not yet state human authorization
  separately (that is in #12).
* **Steps 1 and 6:** no fresh-container Orbit deployment and no real-agent run yet.
