# Docs-parity audit — the five rizzstack repositories at current main

Owner directive, 2026-11-16: audit all five repos at current main for
CHANGELOG / README / protocol-chapter coverage of the last 48 hours of merges,
fix every gap as per-repo docs-parity commits, correct the umbrella truth table
to post-#40 reality, and validate via the existing coverage tests on
full-history worktrees. RED-first: the parity test fails listing the gaps
before the fix and passes after. Docs only; no code changes.

## 0. Method and audited heads

Fresh heads were fetched from GitHub at audit time (2026-11-16 ~21:44 UTC);
every merge below was checked against its actual diff, not its title. The
48-hour window opens 2026-11-14 21:44 UTC; the last merge before it is
workflow #34 at 2026-11-14 20:16:48Z, so the window is exactly workflow
#35–#40. A merge's *content* is audited against four dimensions:

(a) **CHANGELOG coverage** — a discoverable Unreleased entry describing what
the merged diff changed (the bundlebees docs-sync §66 standard);
(b) **README/module documentation touch** — the README or module doc that
should carry the feature says so, and does not contradict main;
(c) **protocol-chapter consistency** — the numbered `docs/` chapters register
what exists (files present on main are indexed, linked and numbered);
(d) **umbrella accuracy** — the rizzstack README truth table and the protocol
map state the actual main state of each row.

| Repo | Audited head | Merged in window | In review at audit |
|---|---|---|---|
| workflow | `9850efa` (#40 merge, 2026-11-16 21:38:41Z) | #35, #36, #37, #38, #39, #40 | #41–#52 |
| bundlebees | `e7f95ca` (docs-sync companion for #67, 2026-11-16 21:01:36Z) | #24–#67 (40 merges) | — |
| hyvv | `961a8bce` (#23 merge, 2026-11-16 21:28:21Z) | #9–#23 (15 merges) | — |
| orbitdesktop | `ace2eb0` (#39 merge, 2026-11-16 19:22:29Z) | #30–#39 (9 merges; no #34) | — |
| rizzstack (umbrella) | `f70754c` (2026-11-16 20:40:29Z) | 3 direct pushes (#2c599cb, #5bf5174, #f70754c) | — |

The parity guard for this repository is `tests/test_docs_parity.py`, modeled on
bundlebees' `tests/test_changelog_coverage.py` (the existing coverage test) and
extended with the in-review wave and the umbrella rows, which that guard is too
narrow to express.

## 1. workflow @ `9850efa`

### 1.1 Merged in the window

| PR | Merged (UTC) | Content (from the diff) | CHANGELOG | README/chapters | Verdict |
|---|---|---|---|---|---|
| wf#35 | 2026-11-15 14:43:32 | campaign closeout hardening: `merge_order` as a 1..N ordinal compared as an exact sequence; each audit carries `status: clean|findings|not_run` | present (Unreleased bullet + chapter 30/31 entries) | chapters 30/31 indexed | covered |
| wf#36 | 2026-11-16 09:45:14 | `rizzstack.observability/snapshot/1` + read-only collector | present (Unreleased bullet) | observability/README | covered |
| wf#37 | 2026-11-16 10:04:55 | the changelog/README/ROADMAP companion for #36 | self-covers (it lands the #36 entry) | — | excluded from the registry with a stated reason |
| wf#38 | 2026-11-16 12:43:32 | wave-4 feature packets F11–F14 + the fail-closed packet parser test | **missing** | packets not indexed beyond chapter 17's pointer | **gap → fixed in this pass** |
| wf#39 | 2026-11-16 12:48:51 | `rizzstack.feature-packet/2`: multi-dependency packets + admission gating (`dependency_not_accepted`), derived schema (no repin) | **missing** | chapter 25 updated by the merge itself | **gap → fixed in this pass** |
| wf#40 | 2026-11-16 21:38:41 | the Rizzstack Rails specification (`specs/rizzstack-rails-spec.md`) + draft `rizzstack.rails/1` event contract (`schemas/rails/`) | **missing** | **unregistered everywhere**: no README index row, no ROADMAP row, no chapter pointer — the spec is specification-only and lives outside the chapter series | **gap → fixed in this pass** (CHANGELOG entry; README/ROADMAP rows prescribed in §6) |

### 1.2 The in-review wave (open PRs #41–#52, none merged at the audited head)

The directive lists several of these as "CHANGELOG gaps"; the audit reconciles
the numbering against actual repo state — these PRs are **open**, not merged,
so their correct CHANGELOG representation is the new `### In review`
subsection (entries written from the open PRs' leased file lists and bodies),
not shipped-work entries. The umbrella truth table rows carry their states.

| PR | Title (state) | What it is (from the PR diff/body) |
|---|---|---|
| wf#41 | collector fleet+health wiring (in review) | the collector's fleet and health sections consume the real bundlebees CLI (`bundlebees attempts` / `bundlebees status`, the subcommands bb#52 ships) |
| wf#42 | bottlenecks section (in review, owner directive) | per-stage queue depth, oldest-item age, dwell-time median/p95, throughput, WIP versus capacity, and the reconciler's waiting-despite-capacity invariant, from real records only |
| wf#43 | owner decision queue `rizzstack.owner-decision/1` (in review) | durable request per owner-only act, digest+nonce sealed; answers bind request bytes via `request_digest`/`decision_nonce`; exactly-once consumption |
| wf#44 | packets F15–F19 rebuilt on main (in review) | the packets lane's RED-first coordinator repair; content is the verified r4 attempt taken verbatim with provenance |
| wf#45 | RESEARCH-BEFORE-RETRY / RESEARCH-BEFORE-PLAN (in review) | normative research-before-another-fix-attempt rule + the planning twin, in chapters 19/24, with conformance tests |
| wf#46 | M2 canary prep (in review) | dedicated smoke project packet + runbook (`rizzstack-m2-canary`), plan/runbook-only, fires when F2 lands |
| wf#47 | rebrand + website plans (in review) | PLAN-ONLY decision documents; names not legally cleared; nothing renames |
| wf#48 | gate-backlog seed (in review) | `plans/backlog.json` (`bundlebees.gate-backlog/1`) seeded for bb#61's gate-watcher; direct push to main was refused by repository rules |
| wf#49 | Observatory events bridge (in review) | `contrib/rizzstack-observability/events_bridge.py` + the `apps/rizzstack-observatory` app wiring, additive only, verify GREEN in-jail |
| wf#50 | memory contract (in review) | new chapter 32 `rizzstack.memory/1`: Obsidian-compatible markdown vault, typed memories, sha-guarded writes, brief-injection; verify GREEN in-jail at `39f340c6` |
| wf#51 | decision notifier service (in review) | one pass over the decision queue's `queue.json` printing a status document; optional chat webhook from a 0600 file |
| wf#52 | modularity umbrella (in review) | `docs/modularity.md`, install profiles as JSON, per-profile quickstarts, `tests/test_modularity_spec.py` |

### 1.3 Adjacent gaps the audit surfaced (outside the 48h window, fixed in the same pass)

- **Chapter 29 (wf#34, merged 2026-11-14 20:16:48Z — 88 minutes before the
  window opens)** has no CHANGELOG entry although `rizzstack.bee-landed/1` is a
  registered protocol with schema, validator, tests and a README index row.
- **Chapters 25/26/27** (feature packet, RETURN manifest, bounded recovery;
  landed with the 2026-11-14 protocol-docs reconciliation `d6db156`) have no
  CHANGELOG entry; the chapter-28 entry's text even says "the README index now
  also lists chapters 25–27" while the changelog itself never introduced them.
- **README index row for chapter 18 is stale**: it still says "18 (open PR, not
  on `main` yet)" but workflow #9 merged the chapter on 2026-11-12
  (`2708264`); `docs/18-parking-projects.md` exists on main. This file is not
  part of this pass's change set (docs-only CHANGELOG/audit/test), so the
  prescribed one-line README fix is recorded in §6 and the parity guard carries
  the stale row explicitly until it is applied.

### 1.4 Protocol-chapter consistency

`docs/01`–`docs/31` are contiguous, every chapter is README-indexed except the
stale chapter-18 row above, and every docs link in the CHANGELOG resolves.
The rails spec is the first protocol artifact that lives **outside** the
chapter series (`specs/`); its registration home is the CHANGELOG entry plus a
README/ROADMAP row (prescribed in §6) — the numbered chapters do not renumber
for it, so the "the docs/ numbered chapters register what exists" check passes
once the spec is discoverable from the README index rather than only from git.

## 2. bundlebees @ `e7f95ca`

The directive's claim — "bundlebees CHANGELOG lacks entries for the post-#66
chain (gate-watcher #61, reconciliation #62, graceful-recovery #63, V1 #64,
payload-serving #66, F2-rebase #65 … have registry rows but verify the
CHANGELOG narrative)" — was **verified against the actual head and does not
hold**: the `[0.2.0] - Unreleased` section documents all seven merges
(#61 gate-watcher `bundlebees.gate-backlog/1`, #62 attempt-reconciliation/1,
#63 graceful recovery (`stream.jsonl`/`resume.json`/`beat.claim.json`), #64
parallel verify workers (shadow first), #65 require-contract gate, #66 lease
payload served on every run, #67 contract-enforcement regression net), and the
HEAD commit `e7f95ca` is precisely the docs-sync companion that added the #67
row. The coverage registry `tests/test_changelog_coverage.py` carries rows for
every merged campaign PR since #43 with diffs-derived keywords, exclusions for
the changelog-companion PRs (#46, #50) with stated reasons, and merge-history
parsing with a pinned snapshot fallback. **Verdict: no gap; the bundlebees
docs-sync chain is the pattern this audit copied for workflow.** The
full-history-worktree validation run is recorded in §8.

## 3. hyvv @ `961a8bce`

Two confirmed gaps, both against the directive's list:

- **hyvv#23 (MAX_WORKERS 10 → 14, owner FINAL directive, RED-first, merged
  2026-11-16 21:28:21Z).** The merge itself carries its module documentation
  (`docs/capacity.md`: the hard clamp, the `400 max_concurrent must be 1..14`
  refusal, the runtime-only setter, the superseded interim cap-12) — but the
  repository has **no CHANGELOG.md at all**, and the README's Zoo routing
  section still says "the launcher's `MAX_WORKERS` ceiling of 10 keeps a host
  under it", which now **contradicts main**. Gap confirmed on both dimensions.
- **hyvv#22 (bee-landed usage payload, D-1 launcher side, merged 17:18:31Z).**
  The launcher emits the attempt receipt's usage block as the CloudEvents
  extension attribute `rizzstackusage` (envelope root, sibling of
  `id`/`source`/`data`, never inside `data`), scrubbed, idempotent,
  backward-compatible — and `docs/bee-landed.md` documents it, but the README
  carries no usage-payload narrative and there is no CHANGELOG to record the
  merge; the two pending consumer changes (the bundlebees envelope allowlist
  must learn `rizzstackusage`; the orbitdesktop outbox source must cross to
  this event type) are documented only inside the diff.

**Prescribed hyvv docs-parity commit** (repo not in this working directory; the
exact text to apply, written from the merged diffs):

```markdown
# Changelog

## Unreleased

### Added

- **Bee-landed usage payload (D-1, launcher side)** (hyvv #22, merged at `47d25c2`):
  the landing envelope may carry the attempt receipt's usage block as the
  CloudEvents extension attribute `rizzstackusage` — at the envelope root,
  a sibling of `id`, `source` and `data`, never inside `data` — scrubbed,
  idempotent under replay, and backward-compatible: events without the block
  stay valid, and a producer that cannot observe usage omits the attribute
  instead of inventing zeros. Nothing consumes it yet, and that is stated:
  the bundlebees envelope allowlist must learn `rizzstackusage` and the
  orbitdesktop outbox source must cross to this event type before the numbers
  flow. `docs/bee-landed.md` documents the block; `tests/test_bee_landed_usage.py`
  pins it.
- **Worker ceiling 10 → 14 (owner FINAL directive, RED-first)** (hyvv #23,
  merged at `961a8bce`): `MAX_WORKERS = 14` is the hard clamp for
  `max_concurrent` — every value is clamped into `1..MAX_WORKERS` at config
  load, and `POST /v1/config` rejects anything above it with
  `400 max_concurrent must be 1..14`. The runtime-only setter changes the
  running launcher's in-memory cfg only (disk config is untouched;
  `max_concurrent` stays out of `CONFIG_HOT_KEYS`), and the ceiling supersedes
  the interim cap-12. `docs/capacity.md` carries the contract;
  `tests/test_worker_cap.py` pins it. Deployed hosts still clamp at 10 until
  the next deploy.
```

Plus the one-line README correction: "the launcher's `MAX_WORKERS` ceiling of
10 keeps a host under it" → "the launcher's `MAX_WORKERS` ceiling of 14 keeps a
host under it" (and `docs/capacity.md` is already the linked source of truth).

## 4. orbitdesktop @ `ace2eb0`

- **There is no CHANGELOG.md in the repository at all**, so nothing of the
  last-48h wave (#30–#39) is changelog-recorded. Two items are directive-named:
  - **od#39 (Orbit decomposition inventory + keep/drop-extract plan, plan-only,
    merged 19:22:29Z)**: `docs/orbit-decomposition.md` + `docs/orbit-inventory.json`
    (`orbit-decomposition/inventory-v1`) + `tests/test_orbit_decomposition.py`
    exist on main and are recorded nowhere else — no changelog, no README row.
  - **od#36-era content check (observatory/usage stack)**: the usage pipeline
    (#31–#38: Zoo provider identity, strict OTLP ledger read, pricing
    snapshots, real launcher receipts wired into the `bee.usage/v1` ledger via
    the `usage-ingest.service` systemd user unit, outbox source for the split
    topology) is present under `pc-launcher/scripts/` and
    `contrib/rizzstack-observability/` — the README mentions neither the
    observatory app (`apps/rizzstack-observatory/`) nor the usage ledger/ingest
    stack. Gap confirmed.
- od#30 (keep campaign closeout outside the ACDD evidence view) is docs-only
  and self-documenting; excluded with that reason.

**Prescribed orbitdesktop docs-parity commit** (exact text to apply, written
from the merged diffs):

```markdown
# Changelog

## Unreleased

### Added

- **Usage pipeline, receipts to rollup** (od #31–#38, merged 2026-11-16):
  `bee.usage/v1` records keep Zoo provider identity (#31), the ledger read is a
  strict OTLP pass with a `gen_ai` whitelist and compact unknown-cost
  visibility (#33), pricing comes from versioned snapshots with per-attempt,
  per-job and per-feature cost rollup (#37), zoo-billed coordinator rows price
  as zoo and never from the DeepSeek table (#35), the ingest service
  (`contrib/rizzstack-observability/usage-ingest.service`) feeds the ledger
  from the pc-launcher's real attempt receipts (#36), and the outbox source
  covers the split topology (defect D-1, #38). The deployed launcher predates
  the payload, so numbers appear after the next deploy — stated, not implied.
- **Orbit decomposition inventory + keep/drop-extract plan** (od #39, plan-only,
  merged at `ace2eb0`): `docs/orbit-decomposition.md` and
  `docs/orbit-inventory.json` classify the corpus (151 server modules, 226 src
  modules, 131 docs, 35 contract modules, 361 test files) as KEEP, EXTRACT or
  RETIRE with evidence per module; nothing is removed, disabled, rewired or
  redeployed by this change, every RETIRE/EXTRACT is a proposal that becomes
  real only when the owner ticks it in the decision checklist, and the deployed
  Observatory and the campaign surfaces are protected.
```

Plus a README pointer row under the Observatory/architecture section naming
`apps/rizzstack-observatory/` and the usage stack, so the README module touch
dimension stops failing for the merged wave.

## 5. rizzstack (umbrella) @ `f70754c`

The README truth table and protocol map were restructured at 20:37–20:40 UTC —
**before** workflow #40 merged at 21:38 UTC — so both carry pre-#40 state that
post-#40 reality contradicts. Corrections prescribed (exact rows):

### 5.1 README protocol map (§ The protocol map)

| Contract | Current row (f70754c) | Corrected row (post-`9850efa`) |
|---|---|---|
| `rizzstack.observability/snapshot/1` | **frozen + deployed** | **frozen + deployed** (accurate; bottlenecks section rides wf#42 in review) |
| `bee-landed/1` + usage payload | **frozen + merged** | **frozen + merged** (launcher side hyvv#22 merged; consumers pending — bundlebees allowlist, od outbox) |
| `rizzstack.rails/1` | **spec in final review** | **merged spec, build in wave 1** — workflow #40 merged at `9850efaf`, 2026-11-16 21:38 UTC |
| action queue + fencing | **merged** | **merged** (bundlebees #54/#58) |
| owner decision queue | **in review** | **still in-review** (workflow #43 open) — unchanged, now anchored |
| `rizzstack.memory/1` | **spec built** | **spec built — per wf#50 state** (in review, verify GREEN at `39f340c6`) |
| ACDD contracts + packets | **frozen** | **frozen** (`feature-packet/2` admission wf#39 merged; F15–F19 wf#44 in review) |
| job authorize / sealed ceilings | **frozen** | **frozen** |

### 5.2 README truth table (§ Live truth table)

- The first "Honest gaps" bullet ("13 PRs queue behind one review verdict — the
  Rails spec (#40) passed CI 14/14 and a two-reviewer panel …; when its
  re-review clears, the 22-package parallel build opens under a 14-bee
  ceiling") is pre-#40. Corrected: **the Rails spec is merged (workflow #40 at
  `9850efaf`); the 22-package parallel build opens in wave 1 under the 14-bee
  ceiling**, and the remaining queued PRs ride their own review verdicts.
- "The M2 canary … proves it under fire next" is accurate against wf#46's
  state (in review, runbook ready) — keep, anchored to wf#46.
- "The fleet section of the Observatory waits on the M1 wiring PR (#41)" —
  accurate (wf#41 in review).

### 5.3 README roadmap rows

- `| **Rails** | … | spec in final gate; 22-package build behind it |` →
  `| **Rails** | … | spec merged (wf#40); 22-package build in wave 1 |`.
- `| **Memory** | … | contract built; service next |` → keep the substance,
  anchor it: `contract built (wf#50 in review, verify GREEN); service next`.

### 5.4 docs/protocol.md (the umbrella's machine-facing map)

- `rails … | spec in review (workflow #40)` → `merged spec (workflow #40 at
  9850efaf); build in wave 1`.
- `bee-landed/1 (+usage payload) | frozen (payload extension in review)` →
  `frozen (usage payload merged on the launcher, hyvv #22; consumers pending:
  bundlebees envelope allowlist, orbitdesktop outbox source)`.
- `owner decision queue | spec in review` → add the anchor `(workflow #43)`.
- **`rizzstack.memory/1` is missing from this map entirely** although the
  README's map lists it — add the row: `rizzstack.memory/1 | spec built
  (workflow #50 in review) | workflow docs/memory-contract.md +
  schemas/memory-schema.v1.json | memory service (planned), brief-injection`.
- `snapshot/1 | frozen (bottlenecks section in review)` — accurate; anchor
  `(workflow #42)`.

The umbrella repository is not part of this working directory, so these rows
are prescribed here and machine-checked below; the umbrella's next docs-sync
applies them verbatim (re-verify against current main before applying: as of the 2026-11-16 post-drain state #41-#47 and #49-#54 are merged and only #48 remains open).

## 6. Fixes applied in this pass vs prescribed

**Applied here (workflow, one docs-parity commit):**

1. `CHANGELOG.md` — Added entries for wf#38, wf#39, wf#40 (written from the
   merged diffs), plus the surfaced adjacent gaps: chapter 29 (wf#34) and the
   chapters 25–27 protocol trio; and the new `### In review (open PRs — not on
   main)` subsection carrying wf#41–#52 with their real states, so the
   changelog is the source the umbrella table and the next docs-sync are
   written from.
2. `tests/test_docs_parity.py` — the workflow coverage guard (RED-first; see
   §8), modeled on bundlebees' `tests/test_changelog_coverage.py`.
3. `docs/docs-parity-audit.md` — this document, including the machine-checked
   coverage registry (§7).

**Prescribed for the other repos (exact texts in §3, §4, §5):** the hyvv
CHANGELOG + README MAX_WORKERS correction; the orbitdesktop CHANGELOG + README
pointer; the umbrella README/protocol-map row corrections. None of these
repositories is inside this working directory, so their commits are specified,
not made.

**Prescribed here but out of this pass's file set:** the README index row for
chapter 18 ("18 (open PR…)" → a real index row); a README index/ROADMAP row for
the rails spec pointing at `specs/rizzstack-rails-spec.md`. Recorded as
follow-ups because this pass's change set is docs-parity (CHANGELOG, audit,
test) only.

## 7. Coverage registry (machine-checked by `tests/test_docs_parity.py`)

Every row was verified against the actual diff at the audited head. States:
**merged** (on main at the audited head), **in-review** (open PR), **verified
present** (directive claimed a gap; the head shows coverage).

| Item | PR | Head state | CHANGELOG | Registry row |
|---|---|---|---|---|
| workflow campaign closeout hardening | wf#35 | merged | present | covered |
| workflow observability snapshot stack | wf#36 | merged | present | covered |
| workflow obs docs companion | wf#37 | merged | self-covers | excluded (reason stated) |
| workflow wave-4 packets F11–F14 | wf#38 | merged | **added this pass** | covered |
| workflow feature-packet/2 + admission | wf#39 | merged | **added this pass** | covered |
| workflow rails spec + draft event contract | wf#40 | merged | **added this pass** | covered |
| workflow collector fleet+health wiring | wf#41 | in-review | **In review entry** | covered |
| workflow bottlenecks section | wf#42 | in-review | **In review entry** | covered |
| workflow owner decision queue | wf#43 | in-review | **In review entry** | covered |
| workflow packets F15–F19 | wf#44 | in-review | **In review entry** | covered |
| workflow RESEARCH-BEFORE-* rules | wf#45 | in-review | **In review entry** | covered |
| workflow M2 canary prep | wf#46 | in-review | **In review entry** | covered |
| workflow rebrand + website plans | wf#47 | in-review | **In review entry** | covered |
| workflow gate-backlog seed | wf#48 | in-review | **In review entry** | covered |
| workflow Observatory events bridge | wf#49 | in-review | **In review entry** | covered |
| workflow memory contract (chapter 32) | wf#50 | in-review | **In review entry** | covered |
| workflow decision notifier service | wf#51 | in-review | **In review entry** | covered |
| workflow modularity umbrella | wf#52 | in-review | **In review entry** | covered |
| bundlebees gate-watcher | bb#61 | merged | verified present | covered (bb registry) |
| bundlebees attempt reconciliation sweep | bb#62 | merged | verified present | covered (bb registry) |
| bundlebees graceful recovery records | bb#63 | merged | verified present | covered (bb registry) |
| bundlebees parallel verify workers (shadow) | bb#64 | merged | verified present | covered (bb registry) |
| bundlebees lease payload served on every run | bb#66 | merged | verified present | covered (bb registry) |
| bundlebees require-contract gate (F2 rebase) | bb#65 | merged | verified present | covered (bb registry) |
| bundlebees contract-enforcement regression net | bb#67 | merged | verified present | covered (bb registry) |
| hyvv bee-landed usage payload (launcher side) | hyvv#22 | merged | **gap** (no CHANGELOG file) | prescribed fix §3 |
| hyvv worker ceiling 10 → 14 | hyvv#23 | merged | **gap** (no CHANGELOG file; README contradicts main) | prescribed fix §3 |
| orbitdesktop usage wiring (ingest service + hardened unit) | od#36 | merged | **gap** (no CHANGELOG file) | prescribed fix §4 |
| orbitdesktop decomposition inventory (plan-only) | od#39 | merged | **gap** (no CHANGELOG file) | prescribed fix §4 |
| rizzstack umbrella truth table + protocol map | f70754c | direct pushes | **pre-#40 rows** | corrected rows §5 |

## 8. RED-first evidence and validation

The guard was written first and run against the untouched tree; the RED run
failed listing exactly the gaps, the fix landed, and the GREEN run passed:

```
$ python3 -m pytest tests/test_docs_parity.py -q   # before the fix
FAILED .../test_merged_campaign_pr_has_discoverable_changelog_coverage[pr-38]
FAILED .../test_merged_campaign_pr_has_discoverable_changelog_coverage[pr-39]
FAILED .../test_merged_campaign_pr_has_discoverable_changelog_coverage[pr-40]
FAILED .../test_in_review_pr_has_changelog_representation[pr-41] … [pr-52] (12)
FAILED .../test_in_review_subsection_states_it_is_not_on_main
FAILED .../test_audit_doc_exists_and_covers_all_five_repos
FAILED .../test_audit_doc_records_the_umbrella_truth_table_rows
FAILED .../test_audit_doc_registry_carries_every_audited_item
FAILED .../test_rails_spec_artifacts_are_registered_in_the_changelog
20 failed, 5 passed

$ python3 -m pytest tests/test_docs_parity.py -q   # after the fix
25 passed
```

The RED run's full output is retained in the work order's evidence, and the
bundlebees guard (`tests/test_changelog_coverage.py`) was run on a
full-history worktree of `e7f95ca` as the cross-repo validation the directive
names: **23 passed**. The parity guard was additionally run on a full-history
worktree checked out at exactly `9850efa` (real merge-log path, not the
snapshot fallback): **25 passed**, and that worktree's whole `tests/` tree
passes (**436 passed, 7 subtests**) — the squashed snapshot in this working
directory shows 6 pre-existing failures in `tests/test_feature_packet.py` /
`tests/test_return_manifest.py` that walk real merge history for the
schema-adding commit; they pass identically on the full-history worktree and
are unrelated to this change (verified before and after the fix).

## 9. Open items

- The umbrella, hyvv and orbitdesktop prescribed commits (§3–§5) are exact-text
  and waiting for their per-repo docs-sync; none of those checkouts is inside
  this working directory.
- workflow README: the chapter-18 stale index row and a rails-spec index row
  are prescribed follow-ups outside this pass's file set.
- The directive's workflow numbering for the in-review items is recorded here
  as corrected: #42 bottlenecks, #43 owner decision queue (+#44 packets, a
  separate slice), #45 RESEARCH-BEFORE-* ("the research protocol"), #46 M2
  canary prep, #47 rebrand plan, #48 gate-backlog seed, #50 memory contract;
  the "#49s" in the directive's research-protocol line matches no workflow PR
  about research — wf#49 is the Observatory events bridge, which the directive
  itself lists under orbitdesktop's "#36-era content check", and both readings
  are covered above.
