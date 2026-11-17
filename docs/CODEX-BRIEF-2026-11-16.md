# CODEX BRIEF — Rizzstack failure analysis & prevention design (2026-11-16)

You are auditing an autonomous multi-agent software factory. Your job: build an up-to-date picture of the repositories, correlate a coordinator's self-reported failures against the raw logs, find additional failure modes the coordinator did NOT self-report, and propose concrete mechanical fixes. You are a reviewer, not an operator: read-only on the repos, no merges, no deploys, no dispatches.

## 0. The system you are auditing

Rizzstack is a governed, observable, agent-agnostic execution platform. Five moving parts, one repo each, all under github.com/mojomast:

| Repo | Role | main @ time of writing | Notes |
|---|---|---|---|
| `workflow` | campaign ledger, docs, coverage registry, the coordination protocol | `86c1bd2527109743aee8c7abec4bf2cd1bafd94b` (CI green) | Where this brief's subject matter lives |
| `bundlebees` | the CUA bee system: dispatch, leases, verify, outbox, jobs | `9b4ea87460c5a0934df944018bdd285f59d14598` | Runs on a worker host over SSH |
| `hyvv` | the launcher that runs bees in disposable sandboxes | `961a8bce501d0ce38922baeb6e5c10347d1f7efd` (DEPLOYED at this rev, 0.1.17) | `restart-idle` reprovisions the worker |
| `orbitdesktop` | the desktop shell + Observatory dashboard | `ace2eb0009af4fccc510ca569bb9715218bd9517` | Serves `apps/rizzstack-observatory/` |
| `rizzstack` | umbrella README / jump-off docs | | |

Fleet lifetime at time of writing: 545 succeeded / 47 failed / 28 cancelled, 1 running. There is a beat/heartbeat automation layer firing every ~10 minutes that merges PRs, writes docs-sync companions, and maintains the coverage registry. A human owner gates everything consequential; the coordinator (an LLM agent session) dispatches bees, verifies their work, and merges under standing rules.

## 1. Start here: the failure report + packaged evidence

Everything is on branch `docs/coordinator-failure-report-2026-11-16` of `mojomast/workflow`, open as PR #68:

- `docs/coordinator-failure-report-2026-11-16.md` — the self-reported failure ledger: 8 classes (F1–F8), each with what happened / detection / resolution / unresolved remainder, a shared root-cause analysis, a ranked unresolved table, and what was working correctly.
- `docs/failure-evidence-2026-11-16/` — the raw evidence: verbatim launcher logs for all seven failure-path attempts (`att_ccc560ab…`, `att_49baec23…`, `att_b470a77f…`, `att_8d113acc…`, `att_f2ca4416…` (the padded-sha death), `att_ab4f1be9…`, `att_0810b361…`), the audit stream tail, the full attempt ledger dump, the outbox tarball (note: it contains ONLY job-CLI-path `bee-landed` events — the absence of tool-path events IS failure F1's evidence), two verify-refusal envelopes (scope-violation + R00 recovery), all 13 immutable lease records including the poisoned one, and both campaign records.

The coordinator's own claimed root cause: every failure = "acting from the internal model of the world instead of a fresh read of it." **Your first task is to check that claim against the logs — confirm or refute it per failure, with quotes.**

## 2. Correlate, then go beyond the self-report

For each of F1–F8: find the primary evidence in `docs/failure-evidence-2026-11-16/`, and cross-check the narrative (e.g. F3's log is 386 bytes and shows `not our ref`; F6's scope-violation envelope lists the exact out-of-lease file).

Then hunt for what the coordinator did NOT report. Suggested lenses:
- **The attempt ledger** (`logs/attempts-dump.json`, 47 failed / 28 cancelled lifetime): sample the failures — do the same failure classes recur across days? Which are coordinator-caused vs machine-caused vs bee-caused?
- **The campaign records** (`docs/failure-evidence-2026-11-16/*.md`, ~800 lines): the running event log is the ground truth of the evening; look for discrepancies between what it claims and what the logs show.
- **The outbox tarball**: which completion paths emit events and which don't; what that asymmetry hides.
- **The leases**: compare `assigned_files` in the leases vs `files` in the verify envelopes — how often did the coordinator mispredict the work surface?
- **The verify-refusal envelopes**: is the scope checker's file-list output sufficient for a dispatcher to self-correct?
- **Launcher logs**: look for retry/amnesia patterns, usage/token anomalies, transport failures (the worker host has a history of WSL/Docker fragility).

## 3. Design questions the coordinator flagged (take positions, with mechanisms)

1. **F3 (fabricated revision):** should the launcher validate `source_rev` resolves at lease-recording time (`git cat-file` / fetch check server-side), or is coordinator-side pre-flight sufficient? Consider: the dispatch tool's format validator accepted a hex-shaped fake.
2. **F1 (work invisibility):** should "success = commit exists on branch" be a launcher-enforced success criterion (bee cannot be marked succeeded otherwise), or a post-hoc audit that flags succeeded-but-nothing-landed attempts? Consider the immutability constraints already in the system.
3. **F2 (restart into lane):** should `restart-idle` refuse while attempts are active (hard fence), defer-and-drain, or is coordinator discipline + a pre-check enough? Consider that the restart is also the recovery tool when the worker is wedged.
4. **F4/F5 (machinery duplication + manual churn):** the coordinator duplicated the automation twice, then hand-churned branch surgery for hours after recording the lesson. Is "one repair attempt then hand off to the automation" enforceable mechanically (e.g. a coordinator action log the beat checks before its own passes, or a lock/claim protocol on repo surfaces), or is this inherently procedural?
5. **F6 (immutable leases):** is no-amendment the right permanent answer (re-dispatch is cheap; the scope gate is the security property), or does dispatcher-error frequency justify a bounded amendment path (e.g. an append-only lease-addendum record the checker accepts)?
6. **The registry chase (F4/F7):** the coverage registry enforces a row for every merged campaign PR, but rows land in companions AFTER the merge — a one-merge-behind chase. The queued fix is "enforce rows only up to a recorded sync cursor." Evaluate that against alternatives: self-rows riding each PR, merge-time automation, or dropping enforcement to audit-only.

## 4. Constraints the fixes must respect (do not propose around them)

- **Security:** bees have NO push credentials by design; the coordinator is the only delivery bridge. Verify is scoped by immutable leases; the scope gate is a security property, not friction. The Zoo API key and all tokens live in 0600 files and are never printed/logged/argv'd.
- **Governance:** merges require CI green at exact head + independent review; deploy gate ≤1 active code-bearing bee; owner approval gates anything consequential (merges of held PRs, restarts of shared services, credential changes, releases).
- **Honesty:** no fake-healthy states anywhere (the Observatory demotes stale rows to `unknown` rather than reporting them in-flight; verify results carry `ok:false` plainly). Any fix that makes a number look better by hiding failure is rejected on sight.
- **The beat is machinery, not a suggestion:** its duties (merges, docs-sync, registry companions, ~10 min cadence) are real. Fixes must define the coordinator/beat boundary, not blur it further.

## 5. What to produce

A single report (markdown), in this order:

1. **Up-to-date picture** — the five repos at their current main revisions, deployed-vs-merged parity (bundlebees installed plugin rev vs main; hyvv deployed rev vs main; Observatory local patches vs main), open PRs and their states, in-flight/queued work. Flag any parity drift you find.
2. **Failure correlation table** — F1–F8: claimed narrative vs what the evidence shows, with file/line/quote citations.
3. **Unreported findings** — failure modes you found in the logs/ledger that the coordinator did not self-report, each with evidence and severity.
4. **Root-cause verdict** — confirm or refute "acted from the internal model instead of a fresh read" per failure.
5. **Prevention design** — for each of the 6 design questions: a position + the concrete mechanism (name the file/function in the relevant repo where it lands, the test that proves it, and the gate format `AC-NNN -> proven-by path::test`). Prefer mechanical gates over procedural rules; prefer fixes that fail loudly over ones that fail silently.
6. **Prio ordering** — what to fix first if the factory keeps running while you write.

Write plain, cite everything, and separate what you verified from what you infer. If evidence contradicts the report, say so plainly — the value of this audit is calibration, not agreement.

*Live-state snapshot at brief-writing time (verify against your own reads, it will have moved): workflow main `86c1bd25` CI-green, open PRs #68 (this report), #59 (DIRTY, beat-owned), #58 (DIRTY, held for owner read), #7 (hermes-bees, DIRTY); bundlebees main `9b4ea87`; hyvv main/deployed `961a8bce`; orbitdesktop main `ace2eb0`; launcher 545 succeeded / 47 failed / 28 cancelled / 1 running.*
