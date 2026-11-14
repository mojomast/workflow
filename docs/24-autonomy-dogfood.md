# 24 — Autonomy dogfood

**Status (November 14, 2026):** the campaign was executed. The deterministic arm runs in CI; the supervised
real-model arms were run on 2026-11-13/14 and are recorded separately. This chapter states what ran, what
the durable records show, and what none of it proves.

**Audience:** the approver and the coordinator running the campaign.

Part of the autonomy set: [21](21-autonomy-gap-analysis.md) · [22](22-autonomy-architecture.md) ·
[23](23-autonomy-devplan.md) · [24](24-autonomy-dogfood.md). Read them in that order.

---

One real objective, one authorization, one verified result, no human decision inside the run. Failure
with accurate evidence is an acceptable outcome; a success that needed undisclosed help is not.

## 1. The objective

**“Add contract-source-revision validation to `acdd-lint`.”**

Two tasks, disjoint leases, both genuinely useful — a frozen contract whose `source_rev` is not a
reachable commit, or not a full 40-hex sha, currently passes lint while making every downstream evidence
record meaningless.

| Task | Requirement | Lease |
|---|---|---|
| T1 | a contract whose `source_rev` is not 40 hex is refused (`contract_source_rev_malformed`); a valid sha is silent | `tools/acdd-lint/acdd_lint/checks_source_rev.py`, `tools/acdd-lint/tests/test_check_source_rev.py` |
| T2 | a contract whose `source_rev` is not reachable from the repository head is refused (`contract_source_rev_unreachable`), with an explicit “not checked” result when no repository is supplied | `tools/acdd-lint/acdd_lint/checks_reachability.py`, `tools/acdd-lint/tests/test_check_reachability.py` |

Wiring into `cli.py` stayed coordinator-owned, as in Experiment B.

## 2. The controlled failure (declared in advance)

T2's **first** contract names a test id that does not exist at the pinned revision
(`tests/test_check_reachability.py::Reachability::test_ancestor_ok` while the real method is
`test_reachable_commit_is_silent`). The worker produces a patch whose named test cannot pass. The loop
must:

1. verify → test not found → task `rejected` with `failure_class: specification`;
2. freeze a **superseding** contract (`supersedes` + `supersedes_sha256`, the B3b pattern);
3. re-dispatch T2 once with the corrected contract;
4. accept the corrected patch and integrate.

The failure is declared in the job file under `injected_failures`, so nobody can mistake it for a real
defect or claim the run was flawless. The superseding contract keeps the same id (`T2-REACHABILITY`) and
changes only its hash, so the correction is visible as a same-id revision rather than a new task.

## 3. Authorization (asked once)

One envelope, written into the job file before dispatch:

- repo `mojomast/workflow` at the authorized revision;
- scope: `tools/acdd-lint/**` only;
- budget: **4 bee dispatches** (T1, T2-fail, T2-retry, one spare), **90 minutes** wall clock;
- recovery: **one correction**, attempts capped by the sealed envelope;
- push: **forbidden** — the run ends with a local integrated commit and a RETURN; branches and PRs are a
  human act;
- merge/deploy/release: **forbidden**, approval gate at the end.

The run was launched by a supervisor, as any test is. “Zero human interventions” below means zero
decisions *inside* the run after authorization — not an unattended overnight production run.

## 4. What ran

### 4.1 Deterministic factory (mandatory CI, Level A)

`tests/test_m4_dogfood_e2e.py` runs the real `acdd-lint` tree, real git, real hyvv provisioning over HTTP,
the real verifier and integrator, and gitleaks. Three worker attempts: `att_m4_1` accepted, `att_m4_2`
rejected on the injected nonexistent selector, `att_m4_3` accepted after the supersession. The accepted
wave integrates `att_m4_1` and `att_m4_3` only; the combined suite passes with **63 tests** at the
integrated commit; the rejected attempt keeps its artifact and has no verification record and no commit;
the RETURN names all three attempts and leaves the receiver decision pending.

The same file carries the negatives: a forged failure classification, a contract altered after freeze, a
corrective test outside the envelope, an exhausted budget, a decision without evidence, a repeated
decision, a supersession bound to a stale provisioning receipt, and an unauthorized supersession. Each
is refused with a named code.

`tests/test_queue_two_features_e2e.py` (5 tests) runs the wider factory: feature A from an exact packet,
feature B from an intent packet plus an enrolled policy. B is resolved against A's accepted commit,
provisioned at that revision through the mirror, and both approved tests pass in a fresh clone of the
final history. Negatives: mutated A contract, mutated B intent packet, a second policy for the same
dependency, and a forged queue card.

### 4.2 Supervised real-model decisions (Level B, not CI)

M4.2 replaced only the decision step with the real Hermes adapter; the pipeline was the same. Three
independent fresh-fixture runs on `deepseek-flash`/`deepseek` each chose `supersede` with the single
authorized positional replacement `test_reachable_commit_is_silent`, exited 0, and took 5.3 s, 5.4 s and
5.9 s end-to-end. Two no-authority cases chose `escalate` with an evidence-based rationale and dispatched
nothing. In run 1 the durable state records the attempts `att_m4_1` (accepted), `att_m4_2` (rejected) and
`att_m4_3` (accepted); T1 contract `83c3d1c6…`, T2 `52863152…`, superseding `b29cf223…` (same id, changed
hash); integrated commit `afca2e74…`; request digest `10d4572a…`; zero human-actor events; receiver
decision pending.

One honest correction is part of the record: the first framed run proposed all three candidate tests. The
production validator refused it because the contract has exactly one selection. The prompt gained the
positional-replacement rule and the fixture criterion text was aligned with its declared selector — **no
validator or authority check was relaxed**. A proposal that the envelope does not permit still cannot be
recorded.

### 4.3 Supervised wake-up (Level B, not CI)

M4.3 runs the coordinator and a separate `agent_consumer` process. The deterministic control (adapter
`authorized`) completes the factory with three attempts and no harness decision. The supervised Hermes
consumer completed the wake-up in **39.2 s** (decision `supersede`, integrated `0ed3f182…`). A consumer
killed after the proposal was persisted was adopted by a fresh consumer in **43.7 s** with no second model
call (`adopted_stale_claim`, claims 2, model invocation 1).

### 4.4 Process-crash scenarios (mandatory CI, Level A)

`tests/test_crash_recovery_e2e.py` runs the coordinator in a separate OS process against a durable worker
service and kills it at named boundaries:

| Scenario | Boundary | Result | Duplicates |
|---|---|---|---|
| A | `tick.after_dispatch` (worker succeeded, no ack) | adopts the attempt, verifies, integrates | 0 extra dispatches |
| B | `wave.after_persist` (accepted wave durable, job not updated) | adopts the accepted wave, restores the ref, no re-integration | 0 extra waves or commits |
| C | `transport.after_publish` (ref exists, handoff records incomplete) | reconciles the ref, writes and validates the resolution, advances B | 0 extra publications, source unchanged |
| control | none | completes normally | 1 attempt per feature |

Durability checks cover corrupt queue records (`queue_state_unreadable` / `queue_state_corrupt`),
missing/unreadable/malformed wave evidence, fsynced create-only wave publication, and a `save_job` that
refuses to drop or rewind accepted evidence.

## 5. Measurements

| Metric | Recorded | Note |
|---|---|---|
| Human interventions after authorization | **0** in the deterministic factory and in the supervised runs | primary metric; the supervisor launched the run, nothing was decided for it |
| Autonomous transitions | dispatch, reap, verify, reject, supersede, re-dispatch, verify, integrate, report | ≥ 8 across the run |
| Accepted vs rejected patches | 3 attempts, 2 accepted, 1 rejected | the rejected patch is preserved |
| Retry / repair cycles | exactly 1 supersession | no second correction |
| Combined suite | 63 passed at the integrated commit (M4 dogfood) | the suite is re-run on the combined branch, not inferred |
| Integration failures | 0 after the corrected patch | the accepted wave is recorded |
| Supervised decision time | 5.3 s / 5.4 s / 5.9 s (M4.2); 39.2 s wake-up, 43.7 s crash adoption (M4.3) | includes process start and model call |
| Tokens / cost | tokens where the runtime reports them; **cost UNKNOWN** | no pricing feed |
| Per-bee CPU/RAM | **UNKNOWN** | not collected |
| Power-loss behaviour | **not tested** | process kills only |

## 6. What this proves

That one authorization can carry a small, real change from goal to verified, integrated, auditable result
with one genuine specification failure classified, superseded and recovered inside the declared budget,
and with the receiver decision left to a human. It proves that the deterministic factory enforces the
rules on every push, and that the Hermes adapter can make the same decision under supervision without any
authority check being loosened.

## 7. What it does not prove

- **No real coding-worker feature has run through the complete factory.** The factory proofs use
  deterministic worker scripts; the real-bee experiments predate the job store and did not include
  recovery or RETURN.
- **No multi-feature, multi-agent campaign.** A→B is the widest run. Several concurrent features, several
  agents, or several waves under load are unproven.
- **OS principal isolation is not established.** Authority separation is file-level inside one state
  directory.
- **Network and filesystem restrictions for Hermes inference are not fully enforced.** No egress
  allowlist, no filesystem isolation, no seccomp, no CPU/memory rlimits; the provider key is visible to
  the child and the prompt is visible to local `ps`.
- **Cross-machine operation is unproven.** The mirror and create-only publication run against local
  fixtures.
- **Windows live is unproven.** hyvv's Windows path handling is unit-tested; the live host has not run
  the provisioning branch.
- **Power-loss durability is unproven.** The crash tests kill processes; torn writes and fsync-loss are
  not covered.
- **Real-model cost and usage are incomplete.** Cost stays `UNKNOWN`.
- **Multi-wave acceptance coverage is thin.** One wave, at most two features.
- **Workflow cold-start acceptance is still failing** (`CS-apply-tax … 0 signed records`).
- **Merges, deploys, releases and final acceptance are human-gated.** The run ends with a local integrated
  commit and a RETURN; it does not merge, tag, push to a protected branch, deploy, or record a receiver
  decision.

## 8. Failure modes, retained

| Observation | Meaning |
|---|---|
| Job stalls with a task in `dispatched` and no state change | the tick is not running, or the reconciler crashed — infrastructure defect |
| A verified patch is integrated without RED evidence | correctness defect in the verifier wiring; stop the run |
| The injected failure is “recovered” by editing the contract to match the worker's output | the exact defect Experiment B caught; treat as a failed run |
| The run reports success but the combined suite was not run | acceptance was manufactured; failed run |
| A human is asked anything between authorization and the report | the loop is not autonomous yet; record the reason |

## 9. Crash honesty

If the coordinator is killed mid-run, the run is not restarted from scratch and not quietly
re-dispatched. The next tick adopts the in-flight attempt from the launcher journal, and the report says
`attempt_adopted` with the crash window. A duplicate dispatch is a failed run, even if the final result
looks correct. The P3 scenarios exercise three such boundaries; a real kill at `queue.before_ack` remains
unproven because that hook raises in-process rather than terminating.
