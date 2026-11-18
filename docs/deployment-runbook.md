# Deployment runbook — staged rollout for the four-repository stack

Owner decision (2026-11-17): deployments run **staged, one surface at a time**, with a parity
check and a rollback checkpoint at each stage. The order is fixed:

```
collector  ->  orbit  ->  plugin (bundlebees)  ->  hyvv launcher
```

Rationale for that order: the collector only reads and stores (cheapest to undo), orbit serves
the read surfaces people look at, the plugin decides *what* runs, and the launcher executes it.
A defect therefore surfaces on the least dangerous surface first, and nothing that dispatches
work changes until the observation layer is proven.

## 0. Rules that apply to every stage

1. **Merged tuple only.** Deploy from commits that are on each repository's authoritative branch.
   Never deploy unmerged branch heads into staging, and never assemble an installed plugin by
   copying files out of an open PR.
   *Why:* an installed plugin assembled from an unmerged branch silently lost the `reviewer`
   subcommand and then failed to import at all (2026-11-17). The plugin is a merged artifact or
   it is not deployed.
2. **Record before you run.** Write the intended tuple (four SHAs), the operator, the time and the
   reason to the campaign record *before* the first stage starts.
3. **One stage, one checkpoint.** After each stage: run parity, read the service state, write the
   result. Do not start the next stage on a yellow checkpoint.
4. **Stop conditions** (any one aborts the rollout and triggers rollback of the current stage):
   parity reports `DRIFT` on the surface just deployed; the service does not answer within its
   normal startup window; a tool/endpoint that answered before the stage now errors; a version
   marker disagrees with the deployed SHA.
5. **Never "fix forward" during a rollout.** A failing stage is rolled back first, diagnosed
   after.

## 1. Preflight (no changes yet)

```bash
# 1a. The four candidate commits must exist and be on the authoritative branches.
for repo in workflow bundlebees hyvv orbitdesktop; do
  git -C ~/rizzstack/<repo> fetch -q origin
  git -C ~/rizzstack/<repo> cat-file -e <merged_sha>^{commit} && echo "$repo ok"
done

# 1b. The qualified-tuple gate: vendor manifests and runtime copies agree at that tuple.
#     (Workflow's immutable qualification evidence, not a hand-built list.)
cd ~/rizzstack/workflow-closeout
python scripts/deploy_parity.py            # must be ALL OK before stage 1
```

Record the tuple and the preflight output in the campaign record. If preflight is not `ALL OK`,
stop: a rollout never starts from a drifted baseline.

## 2. Stage 1 — collector (read-only)

```bash
sudo systemctl restart rizzstack-obs-collector@8787.service
systemctl is-active rizzstack-obs-collector@8787.service
TOKEN=$(grep -i token ~/.config/rizzstack-obs/8787.env | cut -d= -f2-)
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/health
```

Checkpoint: parity `collector OK`; `/health` answers; the observation page loads with fresh
timestamps.

Rollback: check out the previous collector SHA, restart the unit, re-run the health check.

## 3. Stage 2 — orbit (read surfaces)

```bash
git -C ~/rizzstack/orbitdesktop checkout <orbit_sha>
sudo systemctl restart orbitdesktop.service
systemctl is-active orbitdesktop.service
curl -fsS http://127.0.0.1:<orbit_port>/healthz
```

Checkpoint: parity `obs_app OK`; the Observatory renders; onboarding and opt-in screens load.

Rollback: previous SHA, restart, re-check. Orbit holds no dispatch authority, so its rollback is
always safe to perform alone.

## 4. Stage 3 — plugin (bundlebees, decides what runs)

```bash
# The installed plugin is a MERGED artifact: install, do not assemble.
hermes plugin update bundlebees          # or the profile's documented install path
hermes bundlebees status                 # must answer, not "not a hermes command"
hermes bundlebees reviewer list          # subcommands from the merged branch must all be present
```

Checkpoint: parity `plugin OK`; `bundlebees status` returns worker state; every subcommand that
existed before the deploy still exists (this is the regression that cost a staging window).

Rollback: `hermes plugin update bundlebees --ref <previous_sha>`, restart the gateway, re-run the
same three commands.

## 5. Stage 4 — hyvv launcher (executes work)

```bash
# last, because it is the only surface that can start spending money and worker time
hermes bundlebees status                 # launcher healthy, 0 active attempts expected
# apply-update is a human-run CLI command; pass the exact merged SHA
hyvv apply-update <hyvv_sha>
hermes bundlebees status                 # version marker matches <hyvv_sha>
```

Checkpoint: parity `hyvv OK`; the deployment marker equals the deployed SHA; one canary dispatch
(marked as such, in the canary project only) completes with attribution intact.

Rollback: `hyvv apply-update <previous_sha>`; confirm the marker and that no attempts are left
`running`.

## 6. After the rollout

Write, in the campaign record: the four deployed SHAs, each checkpoint's parity output, the
canary dispatch's attempt id, and anything the rollout taught. A rollout without that record did
not happen.

## 7. Relationship to the qualification evidence

A staged rollout consumes the **merged** tuple. Test evidence gathered against draft heads does
not transfer: when a draft merges, the tuple changes, and the four-checkout gate is re-run at the
merged SHAs before stage 1. `COVERED_BY_DRAFT` is not `LANDED`, and `LANDED` is not `DEPLOYED`.
