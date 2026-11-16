# Memory ground-truth audit (Phase 1)

**Date of audit: 2026-11-16.** Input: the owner's Hindsight research brief, Phase 1 —
establish ground truth before any memory-intelligence design. Output: this
document plus the machine-readable companion
[`ground_truth.json`](../ground_truth.json), guarded by
[`tests/test_ground_truth_audit.py`](../tests/test_ground_truth_audit.py).

The brief's standing rule is followed strictly: **nothing is classified as
operational because a PR merged.** Every level below is justified by citations
this audit actually inspected — files and lines in the audited tree, named tests
this audit re-ran where the tree allowed it, recorded runtime observations
archived in durable artifacts, and live probes plus GitHub API verification
performed on 2026-11-16.

## 1. What this audit inspected

| Source | How | Result |
|---|---|---|
| workflow tree | local checkout, tree `1ff8b943cb8c79c421b20845ea7ed6cf397c4630` | byte-identical to upstream main `9f6aa6dc7a74890ef2284d7aa4432efc9b6a4169` (tree hash compared via API). Every file:line citation is valid at the audited head |
| workflow tests | re-run locally (`pytest`, `unittest`) | 405 passed, 6 pre-existing failures — all pin/ancestry checks that need real git history (this clone is one squashed commit); the same checks are green in upstream CI run `43869972734` at the audited head |
| bundlebees, hyvv, orbitdesktop, rizzstack | GitHub API at named heads (no local checkouts exist anywhere on this machine) | heads, ancestry, tree listings, contract constants and CI conclusions verified on 2026-11-16 |
| workflow PR/issue #50 (memory contract) | API + raw file fetch from branch `feat/memory-contract` | contract chapter, schema and oracle read and quoted below |
| coordinator runtime (`~/.hermes`, launcher state, services, sockets) | local probes | every probe returned negative — see §3 |

**Constraints recorded as audit findings, not excuses:**

- **No sibling repos** exist on this filesystem; upstream code was verified at
  named heads through the API, and no upstream test suite was re-run locally.
- **`~/.hermes` is absent** here: no coordinator plugin state, no campaign
  records, no `events/outbox`, no usage ledger, no metrics logs are readable.
- **The clone has no git history** (one squashed commit), which is why exactly
  six pre-existing tests fail (pinned-ancestor checks in
  `tests/test_feature_packet.py`, `tests/test_return_manifest.py`).
- `pytest` and `jsonschema` were not installed and were installed for this audit.
- Live CI numbers were read on 2026-11-16 and can change at any time after.

## 2. The claimed heads, verified

| Repo | Brief claims | Verified (2026-11-16) | Verdict |
|---|---|---|---|
| workflow | `9f6aa6dc7a74…` | `9f6aa6dc7a74890ef2284d7aa4432efc9b6a4169` = main | **exact match** |
| bundlebees | chain `2084222` + `d0e41b5..e7f95ca` | main `e7f95ca5bfba96734ab5dba89aced9b1fbbd6d30`; `2084222` ancestor (3 ahead), `d0e41b5` ancestor (7 ahead) | **chain resolves onto main** |
| hyvv | `47d25c2` | main is `961a8bce501d0ce38922baeb6e5c10347d1f7efd`; `47d25c2` is an ancestor, 3 behind | **stale: main moved (feat/worker-cap-14 merged)** |
| orbitdesktop | `ace2eb0` | `ace2eb0009af4fccc510ca569bb9715218bd9517` = main | **exact match** |
| rizzstack (umbrella) | `5bf5174` | main is `f70754cce953117bf734588ec1a6f833b2009324`; `5bf5174` is an ancestor, 1 behind | **stale by one commit** |

CI conclusions at those heads, read 2026-11-16 (GitHub check-runs API):

| Repo @ head | Checks | Failing |
|---|---|---|
| workflow `9f6aa6d` — run `43869972734` | 14/14 success | none |
| bundlebees `e7f95ca` | 4/4 success (gitleaks; tests incl. sandbox; **orbit round trip, real Orbit API**; plugin doctor) | none |
| hyvv `961a8bc` | 14 success (installer dry-run, unit, contract, scan, release assets, multi-OS) | none |
| orbitdesktop `ace2eb0` | 11 checks | **3 failing: `workbench`, `Workbench / core`, `test`** |
| workflow PR #50 head `39f340c6` — run `43943932096` | all protocol jobs success | **`gitleaks` and `bee-ci/secret-scan` failing** |
| rizzstack `f70754c` | 0 check runs | n/a (no CI on the umbrella) |

## 3. Live runtime probes (deployed vs verified-in-operation)

The brief asks three runtime questions. Each probe below records what was
actually observed in the environment this audit ran in; the
deployed/verified-in-operation split in §4 leans on these results rather than
on upstream claims.

| Probe | Observed result | What it separates |
|---|---|---|
| Coordinator store `~/.hermes` (plugin-data, plugin-state, usage) | **absent** — the path does not exist | the coordinator store is deployed on the coordinator host per records (docs/31 §31.1), not in this environment |
| systemd user units matching rizzstack/obs/bee | **none** — `usage-ingest.service` is not installed here | the ingest unit exists merged on orbitdesktop main, installed nowhere observable |
| Listening sockets (`ss -tlnp`) | only `cua-spacesd:3211` and `opencode:4096`; **nothing on 8787, no Observatory server, no launcher endpoint** | nothing in the rizzstack stack is serving here |
| Launcher/ingest state paths (`~/.orbit-launcher/attempts`, `~/.local/state/bee/usage-ingest-status.json`, `~/.local/state/bee/usage.jsonl`) | **absent** | the ingest service's status JSON cannot be read here; any "deployed" claim rests on records |
| Sibling repo checkouts | **absent** from the reachable filesystem | upstream verification was API-based, not local re-execution |

## 4. The classification ladder

Operational definitions used by every row; the same definitions are in
`ground_truth.json` and enforced by the test suite.

- **SPECIFIED** — normative text and/or schema exists in an inspected repo (or
  on a named branch); no implementation in any audited default branch; no
  runtime evidence.
- **IMPLEMENTED+TESTED** — implementation exists and its named tests pass in
  this audit run (workflow side) or are named with a proof level in a durable
  record (upstream side); the audit flags which side it re-ran itself.
- **INTEGRATED** — two or more components' conformance to each other is
  evidenced by records the auditor holds: real cross-component artifacts
  archived in an inspected repo, cross-repo CI pins that ran green, or
  same-head code on both sides whose contract constants match as verified in
  this audit.
- **DEPLOYED** — durable evidence the system is installed and operating on a
  host, recorded by a party at a named time; not necessarily re-observable now.
- **VERIFIED-IN-OPERATION** — deployed AND observed working end-to-end with
  recorded runtime output (an acceptance run, a CI run ID, captured real
  records) at a named head and time.

Merged is none of these. orbitdesktop proves the point twice over: its
Observatory app is merged on main yet not serving anywhere observable, and its
main CI is red at the audited head.

## 5. Classification table

Verified-here column: `yes` = this audit re-ran or directly inspected the
evidence in the audited tree; `partial` = verified at named heads via API but
not re-run; `records` = rests on durable third-party records only.

| System | ID | Level | Key evidence | Verified here |
|---|---|---|---|---|
| Bee-landed events (`rizzstack.bee-landed/1`) | `bee-landed` | INTEGRATED | docs/29-bee-landed.md:20-43; tools/bee_landed.py:345,365; tests/test_bee_landed.py (45 tests); upstream:bundlebees@e7f95ca `bundlebees_plugin/bee_events.py:91-97` (SCHEMA/EVENT_TYPE match the contract, verified same-head); upstream CI green at e7f95ca incl. real Orbit round trip; LIVE-VERIFIED: 2026-11-16 run 43869972734 (bee-landed required job green) | yes |
| Usage payloads (`bee.usage/v1`) | `usage-payloads` | INTEGRATED | observability/README.md:31-40,89-111; upstream:orbitdesktop@ace2eb0 `pc-launcher/usage-schema.v1.json:3,66` (const `bee.usage/v1`, matches the workflow envelope); `contrib/rizzstack-observability/usage-ingest.service:1-30`; collector.py:547; tests/test_obs_snapshot.py::test_usage_aggregates_and_preserves_unknowns; freeze commit `1617ae0` ancestor of ace2eb0; RUNTIME: 2026-11-16 probe — no ledger, no unit, no status JSON in this environment | partial |
| Attempt/worker execution records | `attempt-records` | INTEGRATED | docs/13-bundlebees-hardening.md:24-38,69-75; docs/23-autonomy-devplan.md:53-60; tests/fixtures/runtime/README.md (provenance: real bundlebees 191dc85 output, captured-request.json sha `da6f6300…`); tests/test_runtime_conformance.py:275; collector.py:820,1175; RUNTIME: 2026-11-12 acceptance run steps 4-8 (acceptance/results/2026-11-12-first-run/REPORT.md:27-31); RUNTIME: 2026-11-15 docs/31-campaign-continuity.md:49-54 (22 leases / 15 job docs counted) | yes |
| Recovery digests (`rizzstack.recovery/1`) | `recovery-digests` | INTEGRATED | docs/27-recovery-protocol.md:131-143,286-310; tools/recovery.py:120,136,277,426,435; tests/test_recovery_protocol.py (90); tests/test_runtime_conformance.py (26); upstream:bundlebees@e7f95ca `bundlebees_plugin/recovery.py:100` (SCHEMA const matches); RUNTIME: 2026-11-14 M4 dogfood captures byte-for-byte in tests/fixtures/runtime/; RUNTIME: 2026-11-13/14 docs/24-autonomy-dogfood.md:87-108 (supervised real-model runs, Level B) | yes |
| Feature packets + source resolution | `feature-packets` | INTEGRATED | docs/25-feature-packet.md:43-65; tools/feature_packet.py:89,154,250,281; tests/test_feature_packet.py (36) + tests/test_multi_dependency.py (18); upstream:bundlebees@e7f95ca `bundlebees_plugin/packets.py:1-30` (loads the pinned workflow validator; seals packet bytes into the job); upstream:bundlebees@e7f95ca `tests/test_packet_enforcement.py`; LIVE-VERIFIED: 2026-11-16 run 43869972734 (feature-packet required job green) | yes |
| ACDD contracts + TDD evidence (`acdd/1`, `tdd-evidence/1`) | `acdd-contracts` | INTEGRATED | docs/16-acdd-tdd.md:31-65,100-110; schemas/acdd-contract.schema.json; reference/workflow/tdd.py; tools/acdd-lint/acdd_lint/cli.py; reference/tests/test_acdd.py; reference/tests/test_tdd.py; RUNTIME: 2026-11-12 evidence/2026-11-12-acdd-build/README.md:11-27 (real RED/GREEN across workflow, bundlebees PR #5, orbitdesktop PR #26); .github/workflows/ci.yml:105-114 (acceptance pins bundlebees `39602ff` with `ACCEPTANCE_ACDD=require`); LIVE-VERIFIED: 2026-11-16 run 43869972734 (reference + acceptance jobs green) | yes |
| RETURN manifests (`rizzstack.return/1`) | `return-manifests` | IMPLEMENTED+TESTED | docs/26-return-manifest.md:15-18,55-76; tools/return_manifest.py:78,83,145; tests/test_return_manifest.py (49); schemas/examples/return-exact.json; upstream:bundlebees@e7f95ca `bundlebees_plugin/return_report.py:65` (SCHEMA const matches); LIVE-VERIFIED: 2026-11-16 run 43869972734 (return-manifest required job green) | yes |
| Independent review findings | `review-findings` | IMPLEMENTED+TESTED | docs/30-campaign-closeout.md:83-105,174-186 (AF-### ids, clean/findings/not_run, one disposition); tools/campaign_report.py:431; tests/test_campaign_report.py (100); docs/19-coordinator-playbook.md:168,200; docs/28-agent-lessons.md:96-104 (the Nov-12 review is prose-recorded and, per :104, not reproducible from any repo); ROADMAP.md:12-13; LIVE-VERIFIED: 2026-11-16 run 43869972734 (campaign-report job green) | yes |
| CI/verification receipts | `ci-receipts` | VERIFIED-IN-OPERATION | docs/CI.md:3-8; .github/workflows/ci.yml:274-331 (required-context gates); contrib/bee-ci/README.md:1-22 (dry-run-only shadow harness, honestly bounded); LIVE-VERIFIED: 2026-11-16 run 43869972734 at the audited head — completed success, 14/14 checks (GitHub check-runs API); RUNTIME: 2026-11-12 acceptance receipt (acceptance/results/2026-11-12-first-run/summary.json:2 `ok: true`, 10/10 steps); RUNTIME: 2026-11-15 docs/31-campaign-continuity.md:238-243 (run IDs 43719698748 @ 57cea41, 43719698698 @ 817b7ee) | yes |
| Coordinator action queue | `action-queue` | IMPLEMENTED+TESTED | upstream:bundlebees@e7f95ca `bundlebees_plugin/coordinator_actions.py:1-end` (lease-and-fence, `bundlebees.coordinator-actions/1`); upstream:bundlebees@e7f95ca `docs/coordinator-actions.md:1-45`; upstream:bundlebees@e7f95ca `tests/test_queue.py`; collector.py:979 (backlog reads queue.json); tests/fixtures/observability-state/state/queue.json (synthetic); docs/19-coordinator-playbook.md:259-267 (the prose todo-queue practice); LIVE-VERIFIED: 2026-11-16 bundlebees CI green at e7f95ca | partial |
| Observability snapshots (`rizzstack.observability/snapshot/1`) | `obs-snapshots` | IMPLEMENTED+TESTED | observability/README.md:8-14 (status: frozen formats, not a working pipeline); contrib/rizzstack-observability/collector.py:402,445,547,820,979,1033,1175; tests/test_obs_snapshot.py (33, incl. test_serves_validating_snapshot, test_collector_writes_nothing); observability/envelope.py:35,54; RUNTIME: 2026-11-16 probe — nothing serving on 8787, systemd template uninstalled here | yes |
| The Observatory (orbitdesktop viewer) | `observatory` | IMPLEMENTED+TESTED | upstream:orbitdesktop@ace2eb0 `apps/rizzstack-observatory/app.js:1-40` (renders `rizzstack.observability/snapshot/1`, bearer in localStorage only); upstream:orbitdesktop@ace2eb0 `extensions/rizzstack-observatory/README.md:1-40`; upstream:orbitdesktop@ace2eb0 `tests/test_rizzstack_observatory.py`; orbitdesktop CI RED at ace2eb0 (workbench, Workbench / core, test); ROADMAP.md:89 is **stale** — it says the app is not merged, but it is merged at ace2eb0; RUNTIME: 2026-11-16 probe — no Observatory serving anywhere observable | partial |
| Campaign closeout record format (`rizzstack.campaign-report/1`) | `campaign-report-format` | IMPLEMENTED+TESTED | docs/30-campaign-closeout.md:36-49,157-198; schemas/campaign-report.schema.json; tools/campaign_report.py:114-431; tests/test_campaign_report.py (100); .github/workflows/ci.yml:192-211 (job additive, deliberately not required); RUNTIME: 2026-11-15 docs/31-campaign-continuity.md:238-243 (job green in run 43719698748) | yes |
| Coordinator campaign records store (`~/.hermes/plugin-data/bundlebees/campaigns/`) | `campaign-records-store` | DEPLOYED | plans/packets/README.md:3-7 (names the archive path; discloses this checkout cannot reach it); docs/31-campaign-continuity.md:49-54 (22 lease files, 15 job docs counted in the durable store); upstream:bundlebees@e7f95ca `bundlebees_plugin/campaign.py` + `campaign_cli.py`; upstream:bundlebees@e7f95ca `tests/test_campaign_continuity.py` (18 passed per docs/31 §31.7); RUNTIME: 2026-11-16 probe — `~/.hermes` absent here, so the store cannot be re-counted | records |
| Lease-payload generation (HMAC-signed leases) | `lease-payloads` | VERIFIED-IN-OPERATION | docs/13-bundlebees-hardening.md:51-59 (O_EXCL, 0400, HMAC-SHA256, lease_tampered); reference/workflow/contract.py:3-7,54-67 (teaching-only unkeyed fingerprints, honestly labelled); acceptance/harness.py:22-33,296-300; upstream:bundlebees@e7f95ca `tests/test_leases.py`; RUNTIME: 2026-11-12 acceptance run steps 4-7 — three signed leases generated, out-of-lease edit rejected `rc=1 code=scope_violation` (acceptance/results/2026-11-12-first-run/REPORT.md:27-31) | yes |
| Deploy/version provenance | `deploy-provenance` | IMPLEMENTED+TESTED | .github/workflows/ci.yml:105-114 (pinned `BUNDLEBEES_SHA 39602ff`, `ACCEPTANCE_ACDD=require`, deliberate-pin comment); acceptance/results/README.md:3-7 (runs table with exact commits); docs/05-infrastructure-hosting-networking.md:122-130 (deploy/rollback rules — specified only); docs/13-bundlebees-hardening.md:7-18 (status table: hardening untagged, v0.1.1 latest); docs/23-autonomy-devplan.md:70-81 (cross-repo CI pins 070b6c1/5bee1a8/d7cf47a/60f0ca0); tests/test_cold_start_diagnosis.py; LIVE-VERIFIED: 2026-11-16 heads + CI via API | yes |
| Memory contract (`rizzstack.memory/1`, workflow #50) | `memory-contract` | SPECIFIED | upstream:workflow PR #50 branch `feat/memory-contract` @ `39f340c6` `docs/memory-contract.md:1-40,265-286` (chapter 32; its own Gaps table: vault service, FTS5/embeddings, capture/distill are design-only); `schemas/memory-schema.v1.json:1-60` (const `rizzstack.memory/1`); `tests/test_memory_contract.py:1-30` (normative oracle); issue #50 body — verify GREEN att_5369386df80e4094 (r2, firejail), r1 refused secret_detected; RUNTIME: 2026-11-16 CI run 43943932096 at the PR head — protocol jobs success, gitleaks + bee-ci/secret-scan failing; **not merged** into any audited default branch (grep over this tree: zero `rizzstack.memory` hits); blocked behind #40 by repo policy | partial |

## 6. Findings that correct or contradict the record

1. **The memory contract is real, specified, and not operational.** PR/issue #50
   (`feat/memory-contract` @ `39f340c6`) carries `docs/memory-contract.md`
   (chapter 32), `schemas/memory-schema.v1.json` (const `rizzstack.memory/1`)
   and a normative oracle `tests/test_memory_contract.py`, with a recorded
   in-jail verify GREEN. It is **not merged** into any audited default branch;
   its own Gaps table marks the vault service, FTS5/embeddings/RRF/ripgrep, and
   the capture/distill runners design-only; CI at the PR head fails
   `gitleaks`/`bee-ci/secret-scan` (disclosed in the issue as expected while #40
   is open); and the issue's own merge gate ("CI green at the exact head") is
   therefore not satisfied. Phase 1 must treat `rizzstack.memory/1` as a draft
   contract on a branch, not a system that exists.
2. **The brief's hyvv and umbrella heads are stale.** hyvv main is `961a8bc`
   (`feat/worker-cap-14` merged; brief head `47d25c2` is 3 behind) and the
   umbrella main is `f70754c` (brief head `5bf5174` is 1 behind). Both remain
   ancestors; the workflow, bundlebees and orbitdesktop heads match exactly.
3. **orbitdesktop main CI is red** at the audited head (`workbench`,
   `Workbench / core`, `test`). Any claim that depends on "green orbit main"
   must be re-checked when that repo is next audited.
4. **ROADMAP.md:89 is stale**: it says the Orbit observatory app is not merged,
   but `apps/rizzstack-observatory/` + `extensions/rizzstack-observatory/` +
   `tests/test_rizzstack_observatory.py` are on orbitdesktop main at `ace2eb0`.
   Merged is still not serving: nothing in this environment serves a snapshot.
5. **bundlebees' own bee-events doc example disagrees with its code and with
   the workflow schema**: `docs/bee-events.md` at `e7f95ca` shows
   `"schema": "rizzstack.bee.landed/1"` (dots) and a non-terminal
   `"state": "landed"`, while `bundlebees_plugin/bee_events.py:91` declares the
   correct `"rizzstack.bee-landed/1"` and the workflow validator refuses both
   deviations. The code is right; the example is doc skew to fix upstream.
6. **No rizzstack component is deployed anywhere this audit can observe.** The
   only VERIFIED-IN-OPERATION rows are the ones whose recorded runtime output
   this audit could hold (CI receipts; the acceptance-run demonstration of
   lease generation). The ingest service, the Observatory, the collector's
   serve mode, the coordinator store and the launcher are all
   records-only from here.

## 7. The umbrella is the entry point, not a fifth runtime element

`mojomast/rizzstack` (main `f70754c` on 2026-11-16; brief head `5bf5174` is an
ancestor) is the **protocol/distribution entry point**: it carries the protocol
map and distribution surfaces, has **no CI configured** (0 check runs), and is
not listed as a runtime element of the stack. The four runtime elements are
workflow (protocol), hyvv (worker host), bundlebees (orchestration) and
orbitdesktop (control surface), per docs/12-three-layer-architecture.md:5-31 and
docs/19-coordinator-playbook.md:34. `ground_truth.json` encodes this as
`umbrella.role = "protocol-distribution-entry-point"`,
`umbrella.runtime_element = false`.

## 8. What Phase 2 must not assume

- `rizzstack.memory/1` has no merged artifact, no vault service, and no
  runtime — the memory design starts from a branch-level draft and a conformance
  oracle.
- Merged ≠ operational: the Observatory is merged and unserved; bundlebees'
  hardened verifier is merged and untagged (docs/13:14); the ingest service is
  merged and uninstalled here.
- The coordinator's campaign records and the bee-landed outbox live under
  `~/.hermes/…` on the coordinator host, which is outside this audit's reach;
  anything that must be verified about them needs either a durable export into
  a repo or access to that host.
- Six pre-existing workflow tests fail only because this clone lacks history;
  the audit's own tests avoid ancestry checks so they stay green on any clone.
