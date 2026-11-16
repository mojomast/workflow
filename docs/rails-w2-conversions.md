# Rails W2 conversions — R00/R01 attempt loss, destruction evidence and re-dispatch readiness

Status: conversion record, regeneration attempt **r3**, written 2026-11-16 on the freshly re-provisioned worker
(workflow seed `ab05d8f`, snapshot of `97ce5680d88543052ec75e46148303e2927eae24`).
Committed on branch `docs/rails-w2-conversions-r3`; the coordinator pushes (this worker holds no push credentials by design).

## 1. Purpose and scope

Records the W2 conversion state of the two Rails readiness attempts whose turns ended (state succeeded)
but whose patches the coordinator's verify REFUSED - scope_violation, nothing applied, sha null - and whose
workspaces were in any case destroyed by the 2026-11-16 18:02:25 EST (23:02:25 UTC) restart-idle:

- `att_ef6953fe272341f9` — `feat/rails-r00-readiness` (R00 source/attachment feasibility)
- `att_584b1d5f44824af8` — `feat/rails-r01-freeze` (R01 contract freeze)

No verified work was ever produced: verify refused both patches before anything was applied, so no branch
tip exists and nothing that had passed verification was lost. The remedies recorded before the owner are
(a) corrected-lease re-dispatch re-applying the already-written R00/R01 packets, or (b) full re-dispatch
from the frozen spec (merged via #40) if the owner declines the corrected leases.
Also assesses re-dispatch readiness from the spec as extractable in this workspace.

Regeneration history: r1 pushed only `docs/parity-audit-nov16` (already PR #55 — not duplicated here, out of
scope for this file). r2 confirmed the R00/R01 workspaces are absent from the freshly provisioned worker.
This file is the r3 regeneration, authored from the current worker after exhaustive recovery checks (§4).

## 2. Conversion state summary

| Attempt | Branch | Result | Work state at restart | Conversion outcome |
|---|---|---|---|---|
| att_ef6953fe272341f9 | feat/rails-r00-readiness | turn ended; verify REFUSED | no accepted patch (scope_violation); workspace destroyed 18:02:25 EST | **no verified work existed; path pending owner corrected-lease decisions** |
| att_584b1d5f44824af8 | feat/rails-r01-freeze | turn ended; verify REFUSED | no accepted patch (scope_violation); workspace destroyed 18:02:25 EST | **no verified work existed; path pending owner corrected-lease decisions** |

## 3. Attempt records

### att_ef6953fe272341f9 — R00 readiness

- Attempt id: `att_ef6953fe272341f9`
- Branch: `feat/rails-r00-readiness`
- Original dispatch time: 2026-11-16 16:39:01 EST (coordinator dispatch record; authoritative).
- Result: the attempt's turn ended (state succeeded), but the coordinator's verify REFUSED the patch -
  scope_violation, nothing applied, sha null (verify-results/att_ef6953fe272341f9.json: ok:false; recorded
  23:15:00Z). The patch touched 11 files, of which 9 were OUT OF LEASE - the recorded out-of-lease list,
  verbatim in the campaign record (§136): contrib/rizzstack-rails/provenance/{LICENSE, README.md,
  vibeline-provenance.json} + contrib/rizzstack-rails/source_fixtures/{README.md, one filename redacted in
  the record, hermes-session-shape.json, native-worker-trace.jsonl, orbit-serving-layer.json,
  source-matrix.json}. The two assigned files (docs/rails-r00-readiness.md, tests/test_rails_r00.py) were
  in scope; vendor-manifest.json and vendor_rails.py belong to R01's refusal, not R00's. The workspace was
  destroyed by the 18:02:25 EST restart-idle before any corrected-lease decision existed.
- Destruction evidence: see §4. No surviving workspace, ref, stash, reflog entry, dangling object, pack
  or stray artifact from this attempt exists anywhere on this worker.
- Remedy path (owner decision pending): corrected-lease re-dispatch re-applying the recorded R00 packet, or
  full re-dispatch from the frozen spec (§5) if declined. Workers hold no push/pull credentials by design.

### att_584b1d5f44824af8 — R01 freeze

- Attempt id: `att_584b1d5f44824af8`
- Branch: `feat/rails-r01-freeze`
- Original dispatch time: 2026-11-16 16:39:08 EST (coordinator dispatch record; authoritative).
- Result: the attempt's turn ended (state succeeded), but the coordinator's verify REFUSED the patch -
  scope_violation, nothing applied, sha null (verify-results/att_584b1d5f44824af8.json: ok:false; recorded
  22:39:52Z). The patch's full out-of-lease file list (24 files incl. the OWNER'S frozen-interface
  schemas/rails/event.schema.json, README.md and examples.json) is recorded verbatim in the campaign
  record (§136). The workspace was destroyed by the 18:02:25 EST restart-idle before any corrected-lease
  decision existed.
- Destruction evidence: see §4.
- Remedy path (owner decision pending): corrected-lease re-dispatch re-applying the recorded R01 packet,
  or full re-dispatch from the frozen spec (§5) if declined, sequenced after R00 (R01 depends on
  "R00 inputs" per the spec's packet table).

## 4. Destruction evidence (this worker, verified 2026-11-16 ~23:04 UTC)

The worker was re-provisioned at 23:03 UTC (seed commit authored 2026-11-16 23:03:47 UTC; every entry in
`/home/cua` carries that timestamp). Checks run on the current worker:

| # | Check | Command | Observed result |
|---|---|---|---|
| 1 | Workspaces | `ls /home/cua/work` | only `workflow` — no R00/R01 workspaces survive |
| 2 | Branches | `git branch -a` | only `master` — neither `feat/rails-r00-readiness` nor `feat/rails-r01-freeze` exists |
| 3 | Stashes | `git stash list` | empty |
| 4 | Dangling/unreachable objects | `git fsck --dangling --no-reflogs`, `git fsck --lost-found` | no dangling objects reported; no `.git/lost-found` created |
| 5 | Reflogs | `git reflog --all` | single entry: initial seed commit `ab05d8f` |
| 6 | All refs | `git for-each-ref` | only `refs/heads/master` and `refs/hyvv/seed`, both at `ab05d8f` |
| 7 | Object inventory | `git count-objects -v` | 425 loose objects, 0 in pack; all reachable (fsck clean) — no hidden commits |
| 8 | Worktrees | `git worktree list` | single worktree `/home/cua/work/workflow` at `ab05d8f` |
| 9 | Remotes | `git remote -v` | none configured — nothing to fetch from; credentials absent by design |
| 10 | Stray artifacts | `ls /tmp/opencode`, home sweep | empty; no prior-attempt files anywhere |

Conclusion: the 18:02:25 EST (23:02:25 UTC) restart-idle destroyed both workspaces, and the 23:03 UTC re-provisioning replaced the
worker entirely. The committed-but-unpushed tips of both attempts left no recoverable trace on this machine.
**Unrecoverable from this worker — verified, not assumed.**

## 5. Required remedy

**Primary (pending owner decision): corrected-lease re-dispatch.** The R00/R01 packets were already
written; they were refused only because their file lists exceed the dispatched leases (full lists in the
campaign record §136). Re-applying them under corrected leases needs no re-run; R01's lease touches the
owner's frozen-interface schemas/rails files, which is exactly why the decision is the owner's.
**Alternative (if the owner declines): full re-dispatch from the frozen spec**
(`specs/rizzstack-rails-spec.md`, merged via #40). What is true regardless of path: the tips died with the
workspaces and workers hold no push/pull credentials, so nothing can be recovered or pushed from here.
Concretely, under either path:

1. Coordinator re-dispatches **R00** (corrected lease re-applying the recorded packet, or an `att` brief:
   spec §9 packet table, R00 row) onto a fresh branch. Original branch names may be reused (no refs
   survive) at the coordinator's discretion.
2. Coordinator re-dispatches **R01** (same split by path; spec §9, R01 row) after R00's output exists;
   R01's depends-on is literally "R00 inputs; this draft".
3. Order matters: spec §11 states "First ready work: R00 source/attachment feasibility, followed by R01
   freeze"; the critical path to M1a is R00 → R01 → R02 (§9 schedule), so this re-dispatch is the
   unblocking step for every dependent wave (R02/R03 next; R05–R14 and R17 further downstream).
4. Salvage of workspace contents is impossible: partial findings, notes and fixture drafts from the
   destroyed workspaces are gone. This is a statement about the workspaces only - it does not decide the
   lease question, because the recorded packets survive independently as refusal evidence. Under the
   corrected-lease path those packets are the starting point; under full re-dispatch the bees start from
   the spec and the in-tree draft artifacts (§6) alone.

Operational note (process, not a blocker): while workers hold no push credentials by design, any
committed-but-unpushed work at the instant of a worker restart has no durable copy. The coordinator should
convert-and-push SUCCEEDED attempts immediately on success so a restart window cannot destroy another
attempt. (Conversions are the only persistence path on this fleet.)

## 6. Re-dispatch readiness assessment

### 6.1 Spec extractability — CONFIRMED, with one path note

The frozen spec is present and complete in this workspace's seed tree at **`specs/rizzstack-rails-spec.md`**
(331 lines). Path note: the brief cites `docs/rizzstack-rails-spec`; in this snapshot the file lives under
`specs/` and no `docs/` copy exists (`git ls-tree HEAD docs/` verified). The coordinator should pin the exact
path + merge commit of #40 on main when writing the re-dispatch briefs; this worker cannot fetch main to
reconcile the two paths (no remote, no credentials).

The R00/R01 acceptance criteria are directly extractable (spec §9 packet table):

- **R00** (S): owning repo `workflow`; lease `specs/rails-feasibility.md`,
  `schemas/rails/fixtures/source-matrix.json`, `tests/test_rails_feasibility.py`; depends on none.
  RED-first acceptance: pin real source versions, record sanitized native trace and session shape, locate
  proxy/auth/queue hooks, resolve uncertainties Q1–Q4; missing fixture/version/attachment makes the test RED.
  Command: `python -m unittest discover -s tests -p test_rails_feasibility.py`; review rejects guessed hooks.
  Milestone M0; consumers: all source authors + integrator.
- **R01** (M): owning repo `workflow`; lease `schemas/rails/{event,source,query,view,http,payload,evidence}.schema.json`,
  `schemas/rails/examples.json`, `schemas/rails/fixtures/hash-vectors.json`, `schemas/rails/README.md`,
  `tests/test_rails_contract.py`; depends on "R00 inputs; this draft".
  RED-first acceptance: bad hashes / duplicate keys / kind payloads / PASS without evidence fail; legacy
  vector matches upstream; freeze digest. Command:
  `python -m unittest discover -s tests -p test_rails_contract.py`. Milestone M0; consumers: every
  producer + consumer.

Q1–Q4 (R00's bounded investigations) are specified in §10's unknowns table: Q1 deployed /obs-snapshot proxy
layer vs inspected main; Q2 action-queue/fencing API semantics; Q3 native worker stream drift (sanitized
fixture); Q4 installed Hermes schema (read-only fixture).

### 6.2 In-tree starting artifacts (seed `ab05d8f`)

Present (draft baseline R01 completes): `schemas/rails/README.md` (states R01 owns the kind-specific closed
payload schemas, semantic validation and golden vectors before dependent dispatch),
`schemas/rails/event.schema.json` (draft envelope), `schemas/rails/examples.json` (synthetic chained events).

Absent — must be produced by the re-dispatched bees: `schemas/rails/fixtures/` (both `source-matrix.json`
and `hash-vectors.json`), the six remaining closed schemas (source, query, view, http, payload, evidence),
`specs/rails-feasibility.md`, `tests/test_rails_feasibility.py`, `tests/test_rails_contract.py`
(`git ls-tree` verified).

### 6.3 Inputs the re-dispatch briefs need

Common to both briefs (spec §9 context rule: "this spec, frozen schemas/examples, upstream dependencies'
handoff, owning repo instructions"):

- Exact spec path + #40 merge commit on coordinator main (see path note in 6.1).
- Source inspection pins and the recheck-at-admission rule (§2): workflow `9f6aa6dc…`, bundlebees
  `b2db04b8…`, hyvv `316bd975…`, orbitdesktop `8530a14b…`, vibeline `d5d0f425…`.
- RED-first discipline and handoff contents (§9): test-first revision, GREEN head, commands/environment,
  contract digest, changed paths, unresolved findings, independent review.
- Lease discipline: exact file lists only, no wildcards; no editing approved test expectations to pass.

R00-specific: Q1–Q4 framing plus the downstream consumers that consume R00 outputs — R01 (source matrix),
R07 (Hermes fixture), R08 (native-log fixture), R15 (queue contract), R16 (auth attachment), R17 (exact
proxy/CLI/doctor paths; §9's note that if observed paths differ, the contract freeze must replace them and
R17's lease must not be silently expanded).

R01-specific: the "R00 inputs" dependency (brief must state whether R00's re-run output is available or R01
waits); the in-tree draft baseline (6.2); the single-owner rule for shared contracts; the freeze-digest
requirement; downstream unblocking (R02/R03 and every producer+consumer wait on the freeze per the §9
schedule).

### 6.4 Verdict

**Re-dispatch is executable now.** All acceptance criteria, leases, commands and dependencies for R00/R01
are extractable from the spec in this workspace; the draft contract artifacts R01 extends are in-tree.
No content blocker. Two coordinator-side notes: (a) pin the spec path/merge commit on main (6.1); (b) treat
the lost attempts' partial findings as gone — no salvage assumptions in the briefs.

## 7. Checks performed for this record

- `git branch -a`, `git stash list`, `git fsck --dangling --no-reflogs`, `git fsck --lost-found`,
  `git reflog --all`, `git for-each-ref`, `git count-objects -v`, `git worktree list`, `git remote -v` —
  recovery sweep, all negative (§4).
- `git ls-tree HEAD specs/ docs/ schemas/rails/ tests/` — spec location, draft-artifact inventory,
  missing-file confirmation (§6.2).
- R00/R01 rows, Q1–Q4 and schedule quotes read from `specs/rizzstack-rails-spec.md` §9–§11.
