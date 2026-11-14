# 23 — Autonomy development plan

**Status (November 14, 2026):** the plan has become a delivery record. M1–M3.5 merged into bundlebees
`main` (#16–#19, `875025b`); the workflow protocol chapters 25–27 and the hyvv provisioning endpoints are
delivered on their branches but **not merged**. This chapter states what each milestone actually proves
and at which proof level, so nobody converts a supervised experiment into a CI claim.

**Audience:** the coordinator and whoever assigns the bee work.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) ·
[23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md).

---

## 1. What changed from the plan

The plan assumed five milestones (`M1 → M2 → M3 → M4 → M5`) on one branch. Delivery took a different
shape, and this document records what happened rather than the original sequence:

- `M1`, `M2` and `M3` landed as separate PRs (#16, #17, #18).
- `M3.5` became the provisioning and packet-native factory programme. Its phases `P2` (packets), `P3`
  (process-crash recovery) and `P4` (RETURN) landed inside PR #19, together with `M4` and its follow-ups
  `M4.1`–`M4.3`.
- The planned `M5` report-and-approval milestone was folded into `P4`: `job report` writes the RETURN
  manifest and leaves the receiver decision pending; there is no separate `job approve` verb that records
  a human merge decision.

The ordering that survived is the important one: a job store before a reconciler, a reconciler before
local verification, local verification before integration, recovery after integration, and the wake-up
after recovery.

## 2. Proof levels

Every milestone below carries exactly one of two labels. They are not interchangeable.

**Level A — deterministic mandatory CI.** Runs on every push and every pull request, with no model call
and no network beyond the committed fixtures. A failure blocks the merge. This is the only level that
proves the system *as shipped* enforces a rule.

**Level B — separately recorded supervised real-model run.** A human runs the same pipeline with a real
model adapter, records the durable state and the raw proposal, and the result is written down outside CI.
It proves the adapter can work under supervision; it does **not** prove determinism, cost, or that CI
would catch a regression in the model's behaviour. The workflow protocol's own tests are Level A; a
real-model decision is Level B even when it uses the same production code.

A milestone can have both labels, but only the Level A part is a gate. The supervised tests are env-gated
(`HERMES_M42_REAL=1`, `HERMES_M43_REAL=1`) and never run in GitHub Actions.

## 3. Delivered milestones

| Milestone | What shipped | Merge / location | Proof | Residual |
|---|---|---|---|---|
| **M1** — job state and authorization | Signed job documents; authorizations that a job may only narrow; task state machine; event append; TTY gate; refusal codes (`job_tampered`, `job_bad_transition`, `authorization_widened`, `lease_out_of_scope`) | bundlebees #16, merge `a4d47e8`; `bundlebees_plugin/job.py`, `job_cli.py` | **A:** `tests/test_job.py`, `test_job_identity.py`, `test_job_cli.py` in the mandatory suite | Seals are file-level tamper evidence, not OS isolation |
| **M2** — crash-safe reconciler | One tick: unbounded pure updates, bounded dispatch batch, one heavy op; intent → call → confirm; strict journal adoption; ambiguity escalation; kernel-held single-writer lock | #17, merge `7a1480c`; `bundlebees_plugin/reconcile.py`, `launcher_adapter.py` | **A:** `test_reconcile.py`, `test_reconcile_crash.py`, `test_reconcile_crash_process.py`, `test_reconcile_hardening.py` | Launcher has no server-side idempotency; `exactly_once` is never claimed |
| **M3** — local verification, integration, wake-up | `verify --commit-local`; isolated worktree at the pinned base; RED before / GREEN after; local `bb-verify/<attempt>` commit; `integrate_job` merges verified commits before `integrate_wave`; `needs-agent.json` handoff | #18, merge `e25e00a`; `verify_local.py`, `integrate_job.py`, `job_cli.py` | **A:** `test_verify_local.py`, `test_integrate_job.py`, `test_self_integration.py`, `test_wave_identity.py`, `test_m3_closeout.py` | The older user-run `verify` still commits and pushes a feature branch; only the loop path is local-only |
| **M3.5 phase 1** — hyvv provisioning | Host-enrolled `provisioning-policy.json`; `POST /v1/provision/project`, capabilities, read-only receipts, cleanup; idempotency, quotas, crash adoption, Windows-aware paths | hyvv `feat/worker-provisioning`, pinned at `5bee1a8` (**PR #4 open**) | **A:** 171 hyvv unit tests, 93 contract tests; `test_provisioning.py`, `test_provisioning_api.py`, `test_provisioning_convergence.py` | Live Windows host unproven; branch is not merged |
| **M3.5 phase 2** — coordinator contract and grants | `rizzstack.provisioning/1` interface, receipt validation, job↔project binding, 5xx as `ProvisionUncertain`; standing grants with TTY enrollment and atomic budget reservation | #19, merge `875025b`; `provisioning.py`, `grants.py`, `provision_bind.py` | **A:** `test_provisioning_client.py` (10), `test_grants.py` (14), `test_provision_vertical.py` | Provisioning is a one-time privileged host step; no cross-host run |
| **P2** — feature packets and the two-feature factory | `rizzstack.feature-packet/1` and `rizzstack.source-resolution/1`; exact and descendant packets; packet digest sealed into the job; production A→B handoff through the queue and mirror | workflow PR #33, pinned at `070b6c1`; bundlebees #19 | **A:** bundlebees `test_queue_two_features_e2e.py` (5 tests, real git + real hyvv HTTP + gitleaks); workflow required job `feature-packet` (16 tests) | Exactly one dependency per descendant packet; no campaign beyond A→B |
| **P3** — process-level crash recovery | Coordinator and worker in separate OS processes; durable worker ledger; named fault checkpoints; four scenarios (after dispatch, after wave persist, after publish, no-fault control); create-only publication at Git's update boundary | #19; `faults.py`, `integrate_job.py`, `handoff.py` | **A:** `test_crash_recovery_e2e.py` (4), `test_crash_durability.py` (26), `test_mirror_concurrency.py` (11), `test_faults.py` (6); full suite 890 passed / 14 skipped at that head | Power-loss torn writes; cross-machine; Windows; a real kill at `queue.before_ack` (that hook raises in-process) |
| **P4** — RETURN packets | `rizzstack.return/1` manifest and `RETURN.md` from durable evidence; strict PASS/FAIL/NOT RUN/BLOCKED/UNVERIFIED classification; always-pending receiver decision; `job report --verify` digest check | workflow PR #33, pinned at `070b6c1` (`return-manifest` job); bundlebees #19 | **A:** bundlebees `test_return_report.py`, factory assertions in `test_queue_two_features_e2e.py`; workflow `test_return_manifest.py` (49 tests) | Commit-presence checks are skipped when no `--repo` is supplied |
| **M4** — bounded recovery | `rizzstack.recovery/1` request/decision pair; five failure classes; sealed envelope; one supersession; corrective dispatch; escalation on exhaustion; RETURN `recovery[]` | workflow PR #33, pinned at `070b6c1` (`recovery-protocol` job); bundlebees #19 | **A:** bundlebees `test_m4_dogfood_e2e.py` (9 tests) with a **scripted** decision adapter; workflow `test_recovery_protocol.py` (90 tests) | The scripted adapter is not an LLM reasoning proof; that is M4.2 |
| **M4.1** — cross-repository conformance | Runtime emits exactly `rizzstack.recovery/1`: 11 request fields, structured evidence, canonical codes, integer correction budget, 9 decision fields, same-ID supersession; pre-conformance records archived as `.legacy.json` (`authoritative: false`) | workflow #33, pinned at `070b6c1`; bundlebees #19 | **A:** workflow `test_runtime_conformance.py` (26 tests) refuses every archived incompatibility and accepts the canonical pair; the M4 dogfood validates its emitted pair unchanged | Protocol v1 only; the archive is evidence, never dispatch input |
| **M4.2** — sealed recovery authority + Hermes decision | Recovery ceiling sealed inside the authorization (attempts, corrections, selectors, file/test scope, gates, digest); `_recheck_authority` at admission and apply; Hermes adapter with strict proposal parsing, provenance and `adopt_proposal` | bundlebees #19; `job.py`, `hermes_adapter.py` | **A:** 16 authority tests, 34 offline adapter tests; **B:** three supervised fresh-fixture runs on `deepseek-flash`/`deepseek` (5.3 s, 5.4 s, 5.9 s, all `supersede`, exit 0), two no-authority cases escalated | No network egress allowlist; no filesystem isolation; no seccomp or CPU/memory rlimits; provider key visible to the child; prompt visible in `ps` |
| **M4.3** — autonomous recovery wake-up | Durable `rizzstack.agent-work/1` item per request; `pending → claimed → completed \| refused`; single active claim, TTL/dead-pid adoption, max two claims; separate `agent_consumer` process; no inference in the mechanical tick | bundlebees #19; `agent_work.py`, `agent_consumer.py` | **A:** deterministic wake-up control (`test_m43_wakeup_e2e.py`) completes the factory with three attempts and no harness decision; **B:** supervised Hermes wake-up in 39.2 s and crash adoption in 43.7 s (claims 2, model invocation 1) | Real-model cost/usage incomplete; run under `unittest` because the live-system guard blocks a pytest parent; unsupervised operation never attempted |

## 4. Required commands (what CI actually runs)

**bundlebees** — deterministic, mandatory:

```bash
# CI pins both protocols by commit; a missing checkout must fail, not skip.
WORKFLOW_SRC=<checkout at 070b6c10bdfa3e9d31b84cc83a2d9d701222082f> REQUIRE_WORKFLOW=1 \
HYVV_SRC=<checkout at 5bee1a870ffe32ee91c6a70b7be807eaa8400801> REQUIRE_HYVV=1 \
python -m pytest -rs
python scripts/measure_schemas.py
```

The `orbit-roundtrip` job separately runs `tests/test_orbit_roundtrip.py`,
`tests/test_orbit_artifact.py` and `tests/test_signed_report.py` against pinned Orbit commits
(`d7cf47a`, `60f0ca0`) with `BUNDLEBEES_REQUIRE_ROUNDTRIP=1`; `plugin-doctor` asserts four registered
tools and no `ERROR` line; `secret-scan` runs gitleaks over history.

**workflow** — required jobs:

```bash
python3 -m unittest tests.test_feature_packet -v
python3 -m unittest tests.test_return_manifest -v
python3 -m unittest tests.test_recovery_protocol -v
python3 -m unittest tests.test_runtime_conformance -v
python3 -m unittest discover -s tests -t . -q
```

**hyvv**:

```bash
uv run python -m unittest discover -s tests -v   # 171 tests, 2 skipped on 2026-11-14
uv run python -m contract                        # 93 tests, 3 skipped
```

**Supervised runs (never CI):**

```bash
HERMES_M42_REAL=1 python -m unittest tests.test_m4_dogfood_e2e -v
HERMES_M43_REAL=1 python -m unittest tests.test_m43_wakeup_e2e -v
```

They call a paid/remote model and are deliberately excluded from GitHub Actions. Their results belong in
the dogfood record ([24](24-autonomy-dogfood.md)), not in a green CI badge.

## 5. Integration test matrix, as delivered

| Test | What it proves | Where |
|---|---|---|
| duplicate dispatch | two concurrent ticks → one attempt per task | `test_reconcile_crash.py` |
| crash between dispatch and persistence | intent + journal adoption, no second POST | `test_reconcile_crash.py`, `test_crash_recovery_e2e.py` |
| failed verification | no commit, classified rejection, wave blocked | `test_verify_local.py`, `test_m4_dogfood_e2e.py` |
| local-only committed integration | `integrate_wave` receives a real ancestor commit; no ref is pushed | `test_integrate_job.py` |
| wake-up without a human | separate consumer claims the work item and completes the factory | `test_m43_wakeup_e2e.py` |
| two-feature factory | dispatch → reap → verify → integrate → RETURN, real git and hyvv HTTP | `test_queue_two_features_e2e.py` |
| crash after wave publish | accepted wave adopted, no re-integration | `test_crash_recovery_e2e.py` |
| recovery conformance | emitted request/decision validate against the pinned protocol unchanged | `test_recovery_conformance.py`, workflow `test_runtime_conformance.py` |

## 6. Ordering and ownership

`M1 → M2 → M3 → M3.5`, then `P2 → P3 → P4`, then `M4 → M4.1 → M4.2 → M4.3`. This is the dependency order
in the code: M2's intents need M1's job records; M3's commits are what integration consumes; P3's crash
points wrap the queue, wave and transport code P2 introduced; M4's recovery needs a stable integrated
head; M4.1 constrains the runtime to the protocol; M4.2 seals the envelope; M4.3 separates the wake-up.

Bee-assignable work was M1 (job store and schema), M3's `verify_local.py`, M3.5 phase 1 (hyvv
provisioning), and the recovery/queue slices with coordinator-approved tests. The reconciler, the
integration wiring and every authority check stayed coordinator-owned because they encode the ordering and
narrowing rules this plan exists to get right.

## 7. Explicitly deferred or never claimed

- Launcher push/webhook events. Polling remains acceptable because the tick recomputes from disk.
- Automatic re-planning. v1 decomposes once at `job create`; a supersession corrects the selection, it
  does not decompose the feature differently.
- Multi-repo jobs; dashboards; alerting; cost accounting (no pricing feed — cost stays `UNKNOWN`).
- Parallel verification. One heavy operation per tick is deliberate.
- A real coding-worker feature through the complete factory, a multi-feature multi-agent campaign, a
  cross-machine run, a live Windows run, power-loss durability, and OS-principal isolation. Those are
  limitations in [21](21-autonomy-gap-analysis.md) §4, not milestones that quietly passed.
- Merges, deploys, releases and final acceptance. Human-gated, always.
