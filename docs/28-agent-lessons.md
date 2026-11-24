# 28 — Agent lessons: what the campaigns proved, observed and only recommend

**Status (Nov 14, 2026):** a graded catalogue of engineering lessons taken from the November 2026 orchestration and provisioning campaigns. It is descriptive. It records what was learned, what demonstrated it, and how strongly the claim is supported. Nothing here grants an approval, defines a protocol, or replaces [16](16-acdd-tdd.md), [25](25-feature-packet.md), [26](26-return-manifest.md) or [27](27-recovery-protocol.md).

**Audience:** a coordinator, a brief author, or an agent asked to take over either role — in any harness. [19](19-coordinator-playbook.md) is the procedure and [20](20-orchestrator-handoff.md) is the switch; this chapter is the evidence behind both. Where a lesson depends on a mechanism that a chapter already defines, the lesson links to it instead of restating it.

## 1. How to read a grade

**Method.** Every lesson carries one grade, or an explicit split grade, from the four below. A grade describes the support for the *specific claim*, not its importance, and it does not travel: a proven rejection in a verifier says nothing about the brief that produced the patch.

| Grade | Means | What it lets a reader claim |
|---|---|---|
| **PROVEN** | A test, schema, validator or CI job enforces the rule at a named place, or a production-like experiment recorded its result at a named revision | "This holds where that check runs" — not "this holds everywhere" |
| **OBSERVED** | Agent work whose result was recorded, but no independent automated check pins it | "This happened, and the practice follows from it" |
| **RECOMMENDED** | Reasoned from the failure or from the mechanism, not yet exercised | "This is the proposed practice; it is untested" |
| **HISTORICAL** | Explains why an approach changed or failed; not a live rule | "This is why the current rule exists" |

No check in this chapter was re-executed while writing it. **PROVEN** therefore means the check exists by name and its result is recorded — in a required CI job, a test module, a validator, or a dated experiment — not that this chapter reproduced it. Where the only record is a campaign report, the lesson is **OBSERVED** even when the original run was automated, because a reader cannot replay it from this repository.

## 2. Delegation shape

### L-01 · Parallelism is bounded by the coordinator, not by the worker pool

**Grade:** OBSERVED for the capacity claim; RECOMMENDED for "two to three lanes".

**Learned.** A lane buys worker time and spends coordinator time: interface reconciliation, the integrated-tree run, CI on the combined head, and one report that separates worker output from coordinator correction. Splitting earlier than the coordinator can absorb does not shorten the milestone; it moves the queue into the parent's context.

**Shown by.** Campaigns that ran as three lanes — protocol, coordinator authority and binding, end-to-end proof — finished only when the parent wired the one caller nobody owned and ran the real path. The counter-case is serial implementation inside one context, where the phase outgrew the context before any artifact was integrated.

**Practice.** Read the runtime's real limits first (`agent.max_turns`, delegation iteration caps, gateway concurrency); when they are generous, the bottleneck is sequencing, not the runtime, and shrinking the milestone is the wrong response. Then dispatch two or three lanes in one batch, keep the parent on the seam, and do not open a lane whose remaining work has no seam to own.

**Portability.** The caps are per-runtime; the accounting is not. Any orchestrator with subagents pays integration cost per lane.

**Evidence.** The three-lane split is recorded in the provisioning campaign handoff; the integrated artifact is `tests/test_queue_factory_e2e.py` and `tests/test_queue_two_features_e2e.py` in bundlebees.

**Limits.** There is no controlled comparison of two versus three lanes. "Two to three" is a working heuristic, not a measurement.

### L-02 · The advertised concurrency is not the usable concurrency

**Grade:** OBSERVED.

**Learned.** A launcher can advertise `max_concurrent: 10` and a shared cap of 12 while the host sustains about seven bees at 4 GB and 2 CPUs each. Capacity is a property of the host at that moment, not of the configuration file, and a peer agent's bees draw from the same pool.

**Shown by.** The worker-host report of Nov 12 measured about seven practical concurrent bees against an advertised `max_concurrent` of 10, on 4 GB and 2 CPUs per bee. The same report recorded that a Docker/WSL restart kills every running container, so a dispatch into a pending restart is lost work rather than a retry.

**Practice.** Read live capacity from the host before every dispatch, compare it with both the pool cap and the lane cap, plan waves below the measured ceiling, and report "pool full" as a state rather than overrunning it.

**Portability.** The numbers are one host's. "Measure, then size the wave below the measurement" is not.

**Evidence.** [03 §4](03-development-and-orchestration.md) records the capacity history (1 → 3 → 6 → 10 slots); [19 §3](19-coordinator-playbook.md) records the pooled cap; the ~7 figure comes from the dated worker-host report in the orchestration handoff.

**Limits.** One host, one configuration, no benchmark. Treat ~7 as an observation with an expiry date.

## 3. Ownership and commit hygiene

### L-03 · Disjoint ownership is the precondition; the lease is what makes it enforceable

**Grade:** PROVEN for the lease rejection; OBSERVED for the shared-worktree discipline.

**Learned.** Parallel slices are safe only when file ownership is exclusive and recorded before dispatch. A brief that lists `assigned_files` is a promise; a verifier that rejects any patch touching a path outside it is the enforcement. Two lanes may share one checkout or branch only with explicit-path commits.

**Shown by.** Commits that captured another lane's half-finished work when `git add -A` was used in a shared worktree. On the enforcement side, the bundlebees verifier refuses an out-of-lease path, a missing lease and an edited lease with stable codes.

**Practice.** `git add <files>` only; never `git add -A`, reset, stash or check out another lane's files. Expect interleaved commits and verify that the final head contains every lane's files rather than expecting tidy history. A lane that needs an API another lane owns reports the missing name and lets its test fail — it never edits the other lane's production file to make the test pass.

**Portability.** The lease is a concept; the enforcement can be a signed lease, a path filter in review, or a required check. What does not port is the assumption that goodwill keeps lanes apart.

**Evidence.** [13 §3](13-bundlebees-hardening.md) (HMAC lease, `lease_tampered`, `lease_missing`), [16 §6–§7](16-acdd-tdd.md) (parallel contracts must have disjoint `scope.assigned_files`; `scope_violation`), bundlebees PR #3 and PR #4.

**Limits.** A lease bounds files, not behaviour. A wrong implementation inside the leased path passes every scope check, which is why L-05 exists.

### L-04 · Prove the tree you are about to commit, not the script that edited it

**Grade:** PROVEN for the marker assertion; OBSERVED for the corruption case.

**Learned.** Scripted merges fail in ways that leave a file looking written. `git checkout -m` labels conflicts `ours` and `theirs`, not `HEAD` and `origin/main`, so a resolver that matches `HEAD` finds zero blocks, replaces nothing, and leaves an unresolved file that still reads like a finished document. A reader that prefixes line numbers corrupts pipe-heavy markdown when its output is written back, because `N|` collides with table rows.

**Shown by.** An unresolved merge that survived a zero-block resolver until the marker check caught it; a chapter table silently mangled by a line-numbered read.

**Practice.** Grep the labels you actually have, then assert zero `^(<{7}|={7}|>{7})` lines and an empty `git ls-files -u` before `git add`. Read with plain `open()` when the content is going back to disk. Re-run the repository's checks and scan the diff before pushing, and re-read the head immediately before merging — your own sync push moves it.

**Portability.** These are properties of git and of any line-numbering reader, not of one agent.

**Evidence.** The branch-sync procedure in the orchestration handoff; [19 §10](19-coordinator-playbook.md) for the stacked-branch merge order that makes the sync necessary.

**Limits.** The recorded incidents were document overlaps. When the overlap is code that both sides rewrote, stop resolving by hand: the full suite decides, and a merge that keeps failing becomes a port onto `main`.

## 4. Evidence and claims

### L-05 · A worker's success report is a claim; acceptance is a check you ran yourself

**Grade:** PROVEN for the conformance technique; OBSERVED for the incident.

**Learned.** `state: succeeded`, "all tests pass" and "pushed" are producer statements. Acceptance needs the exact head, CI on that head, the named tests re-run when CI cannot settle it, the diff checked against the lease, and a claim that matches the evidence. Accepting against a worker's own suite is weaker still: a bee writes tests against the interface it actually built, so green tests prove the tests match the implementation and nothing more.

**Shown by.** An independent review of the open PRs found blocking issues that the lanes' self-reports had missed; that review is why merges paused. A reconciler submission of 1,979 lines passed its own suite while ignoring a frozen `grace_s`, returning a `dict` subclass where the contract specified a frozen dataclass, and resolving the launcher by trying eight method names.

**Practice.** Re-fetch the head from the forge and compare it with the reported SHA; check CI on that commit, counting pending as pending; run the named tests locally under `nice`/`ionice` when CI cannot settle the question; compare the diff with the lease. For a frozen interface, check conformance mechanically — `dataclasses.is_dataclass`, `__dataclass_params__.frozen`, field names and order, `inspect.signature` parity for the public entry point, and negative tests that fail when the module accepts an out-of-contract launcher or a non-boolean capability flag. Then prove the negatives are meaningful by running them against the worker's **unmodified** module before accepting a correction.

**Portability.** High. The claim/evidence split is harness-independent; only the API names change.

**Evidence.** [19 §4](19-coordinator-playbook.md) (re-fetch, CI on the exact SHA, scope, claim matches evidence); the conformance checks and the 1,979 → 692 line correction are recorded in the orchestration handoff; the protocol side is [16 §3](16-acdd-tdd.md) (only verifier records count).

**Limits.** The independent review was manual; its findings are recorded, not reproducible from this repository.

### L-06 · A hermetic test proves the fake, not the contract

**Grade:** OBSERVED; the real-subprocess fixture pattern is PROVEN in the queue E2E tests.

**Learned.** Tests written against an imagined API pass forever. A client tested only against its own fake server has proved itself against itself.

**Shown by.** A CLI whose tests mocked two routes that did not exist on the launcher; the suite went green and every live run failed closed with `capacity_check_failed`. The inverse also bit: a capability test that asserted a pinned version string broke on every bump while the behaviour it guarded never changed.

**Practice.** Put the measured shapes in the brief — real route, real field names, real status codes — and exercise the artifact against the real thing. For anything that touches git, the filesystem or process lifetime, use real temporary repositories and real subprocesses: a fake cannot show that a pinned SHA outside the fetched refs resolves, that `HEAD` is detached, that a dirty tree is refused, or that a killed owner releases a lock. Assert shape with a pattern, not a release number.

**Portability.** Universal. The only question is where the real boundary is.

**Evidence.** The mock-route incident is in the orchestration handoff; `tests/test_queue_factory_e2e.py` and `tests/test_crash_recovery_e2e.py` in bundlebees use real git, real gitleaks and a real killed process; [13 §6](13-bundlebees-hardening.md) makes the same point structurally (`normalize_result` drops everything the worker claims).

**Limits.** Some contracts cannot be exercised in CI — a live model, a Windows-only path, a cross-machine transport. Those are reported **NOT RUN**, never simulated.

### L-07 · Name the layer that was actually proven

**Grade:** OBSERVED, with one PROVEN remedy pattern (a command-level test).

**Learned.** A capability exists at several layers — module, command, deployed endpoint, running process — and each can be green while the next is absent. "Done" without a layer is an ambiguous claim, and ambiguity resolves in the optimistic direction.

**Shown by.** Five separate instances, each recorded: a green vertical slice while the real `job tick` command never constructed a provisioner; an endpoint merged but absent until the running launcher was upgraded and a startup-read flag set; a plugin fix merged and installed while the old module stayed loaded until a gateway restart; a report builder covered by unit fixtures that the factory never generated; a locally verified commit unreachable to the worker host because nothing transported it.

**Practice.** Say which layer was proven and which was not: "merged and installed, not yet loaded", "endpoint implemented, not deployed", "verified locally, transport NOT RUN". Add a test that asserts the *command* passes the configured dependency, including the `None` case, rather than only testing the function. A draft pull request is not a delivered capability, and neither is a local branch.

**Portability.** High. Layer names differ per stack; the discipline does not.

**Evidence.** [20 §7](20-orchestrator-handoff.md) (install versus load), the provisioning handoff ("a proven Python path is not a shipped path"), and the deploy notes in the orchestration handoff ("merged and installed, not yet loaded").

**Limits.** The launcher case was fixed by review, not by an automated check; only the command-wiring case has a test behind it.

### L-08 · The harness must not do the production step

**Grade:** PROVEN for the current fixture; OBSERVED for the original defect.

**Learned.** An end-to-end test that performs the production steps by hand — publish the commit, resolve the dependent rule, seal the derived authorization, create the job — proves the pieces fit together by hand. It does not prove the product does them.

**Shown by.** An E2E whose test resolved the descendant rule and sealed the derived authorization between queue passes, while the production runner did not; the harness hid the gap it existed to expose.

**Practice.** Move the steps into the runner in dependency order (sealed policy → validate dependency evidence → publish → derive → authorize → create → advance), let the test enrol its policy once, then call only the public entry point. Keep each step's durable identity so a rerun adopts instead of duplicating.

**Portability.** Universal test-design rule; it applies to any "does the real path run" claim.

**Evidence.** `tests/test_queue_two_features_e2e.py` in bundlebees calls only `queue.run_once()` after enrolment, as recorded in the provisioning handoff; [25 §Coordinator conformance](25-feature-packet.md) lists the same steps as coordinator duties.

**Limits.** Fixtures and enrolment are legitimately test-only. The line is whether production performs the step on its own path.

### L-09 · Unrun is a status, not a zero

**Grade:** PROVEN.

**Learned.** Honest reporting needs a status for every check — passed, failed, not run, blocked, or unverified — and a level for every claim: observed by you, reported by someone else, or unverified. An unmeasured number is **UNKNOWN**, never zero, and a `PASS` with no evidence is not a pass.

**Shown by.** The ACDD lint dogfood was written up as what it was — 0 accepted changes and 2 rejected waves — instead of being rounded to a success because all four GREENs landed first try. The RETURN schema now refuses `PASS` with an empty evidence array, and a generated manifest cannot carry a filled receiver decision.

**Practice.** Report an unrun step with its reason ("NOT RUN: needs a Windows runner"); never invent counts, durations or percentages; when a claim came from a worker, say so; when it came from your own run, say where.

**Portability.** Universal.

**Evidence.** [16 §12](16-acdd-tdd.md), [26 §Acceptance](26-return-manifest.md) (`PASS`, `FAIL`, `NOT RUN`, `UNVERIFIED`, `BLOCKED`; `pass_without_evidence`), [27 §Limits](27-recovery-protocol.md) ("cost stays UNKNOWN").

**Limits.** A status vocabulary is not a measurement. It prevents false positives; it does not produce the missing number.

## 5. CI that can actually fail

### L-10 · A green run that skips the tests is a false green

**Grade:** PROVEN.

**Learned.** A suite gated on an external checkout reports success while executing nothing. A required dependency that is optional in the test file is a gate that never closes.

**Shown by.** One run reported `759 passed, 10 skipped` and looked healthy; after the checkout was wired in, the same suite reported `766 passed, 3 skipped`. The seven missing tests were the ones that proved the integration.

**Practice.** Export the dependency path *and* a `REQUIRE_<X>=1` flag from the same job that runs the tests, and make a missing path fail in `setUp` rather than skip. Read the skip count and the named tests in the log, not just the pass line. Check out the dependency at the exact pinned SHA and assert it. The only acceptable skipped check is a path-filtered family with a separate detector job concluded success on the same head and a literal `SKIPPED` conclusion; anything else blocks.

**Portability.** Universal CI rule. The variable name is arbitrary; the fail-not-skip choice is not.

**Evidence.** bundlebees CI pins hyvv (`HYVV_SRC`, `REQUIRE_HYVV=1`) and workflow (`REQUIRE_WORKFLOW=1`) by full SHA and requires both; the counts are recorded in the orchestration handoff; [13 §1](13-bundlebees-hardening.md) covers the fail-closed verifier side.

**Limits.** The three-part exception above is narrow on purpose. It records why a skip was allowed; it does not make skipped tests count as run.

### L-11 · A failure with zero jobs is a rejected workflow file

**Grade:** OBSERVED.

**Learned.** A job-level `if:` that reads `matrix` invalidates the whole workflow file. Every check disappears from every ref that uses it, the YAML still parses locally, and the run log is empty — so the symptom is "no checks reported", not a red check.

**Shown by.** A pull request whose checks vanished, `gh run view --log-failed` printed nothing, and the runs-jobs API returned an empty list. Removing the leg from the matrix was the fix; there was never a failing test.

**Practice.** Separate three signatures before touching code: zero jobs (invalid workflow), a tool banner such as a browser runtime rejecting the runner image (infrastructure drift), and a real assertion (code or test). A workflow fix merged to `main` does not reach an existing PR until `main` is merged into that PR's branch, because `pull_request` runs take the workflow file from the head branch.

**Portability.** The zero-job signature is GitHub-specific; "empty work list means configuration, not code" generalizes.

**Evidence.** The CI-troubleshooting section of the orchestration handoff.

**Limits.** Other CI systems have their own invalid-configuration signature. Do not generalize the exact message.

### L-12 · Dependencies come from the declaration, not a hand-kept list

**Grade:** OBSERVED.

**Learned.** A job that hand-maintains its install list drifts from the project's declared dependencies and fails months later. Each missing dependency also hides the next, so the first error names only the first gap.

**Shown by.** A job that died at collection with `ModuleNotFoundError`, executed zero tests, and failed identically on `main` — an environment defect, not a code defect. Repairing it took three modules, not the one the first error named.

**Practice.** Derive the requirements inside the step from the declaration (for example `tomllib` over `pyproject.toml`, then install the project and dev extras), so the file cannot drift again. Reproduce the failure in a throwaway virtualenv at the job's own Python version, using the install command from the **PR's head branch**, not `main` — a branch's install list drifts too. Add names one at a time and report the collection-error count as the evidence. `pip install -e .` is not automatically the fix; on a repo without package configuration it fails and turns a CI-only change into a packaging change outside the authorisation.

**Portability.** The snippet is Python; the rule holds for any package manager with a declaration file.

**Evidence.** The CI section of the orchestration handoff, including the derivation snippet; the provisioning handoff records that hyvv runs `unittest` discovery while bundlebees runs pytest — a file written for the wrong runner fails at import, the same defect class.

**Limits.** A repository with no declared extras still needs a list. Then the list *is* the declaration and needs its own test.

### L-13 · A pin is a claim that must resolve at the revision that bears it

**Grade:** PROVEN.

**Learned.** In a multi-repository stack, a consumer that checks out a producer at a fixed SHA has made the producer's shape part of its own contract. A pin that predates the schema it validates is refused, a pin to the example's own commit is circular, and a consumer pin that is not bumped with the producer's public shape fails as a type error that looks like a test bug.

**Shown by.** A packet pinned before its schema existed, refused as `workflow_ref_unsupported`; examples that would have been pinned to the commit that contains them; a hyvv policy field added without bumping bundlebees' pinned checkout, producing a `TypeError` in the real-implementation tests.

**Practice.** Land the schema and validator first, then repin the examples in a later commit, then bump the consumer's pin to a head that contains both. Assert that a pin is a real commit, an ancestor of `HEAD`, and byte-identical to the enforced schema for **every** schema the record depends on — a dependent feature is read under two stages, so it is checked against both. Use full history (`fetch-depth: 0`) and install the schema dependency in that job; a shallow clone makes a valid pin look unknown. Bump the dependency pin in the same commit as the shape change.

**Portability.** Any stack with pinned consumers. The two-stage check is specific to dependent features.

**Evidence.** `tests/test_feature_packet.py` asserts the pin is a commit, an ancestor and byte-identical for both schemas; the required CI jobs `feature-packet`, `return-manifest` and `recovery-protocol` all set `fetch-depth: 0`; [25 §Pinned examples](25-feature-packet.md) and [26 §Pinned examples](26-return-manifest.md).

**Limits.** A shallow clone turning a valid pin into `*_unknown` is a CI defect, not a bad pin — fix the job, not the pin.

### L-14 · Read the gate before calling a red check a blocker

**Grade:** OBSERVED.

**Learned.** A failing check blocks a merge only if a rule requires that context. A repository can have neither a ruleset nor branch protection, in which case a red check leaves the pull request `UNSTABLE` and the merge permitted. Reasoning from the check list instead of the ruleset produces a plan around a gate that does not exist.

**Shown by.** A proposed "CI policy change" for a repository with no policy, and a merge plan sequenced around a required context that was never required.

**Practice.** Read the ruleset and branch protection first — an empty array and a 404 are answers. Interpret the merge state precisely: `BLOCKED` means a rule is unmet, `UNSTABLE` means only non-required checks are failing, `DIRTY` means conflicts, `BEHIND` means the base moved under a strict up-to-date policy. Before requiring an approval, count the accounts: on a single-account repository the rule is unsatisfiable because the only author cannot approve their own pull request. Dropping required approvals to zero does not help while `require_last_push_approval` is on — it blocks on its own.

**Portability.** The field names are one forge's; the instruction "read the rule, not the symptom" is not.

**Evidence.** The ruleset section of the orchestration handoff; [20 §8](20-orchestrator-handoff.md) for fail-closed merge gates built on the same reading.

**Limits.** Platform behaviour changes. Re-read the API rather than trusting this list.

## 6. Durable state, claims and exactly-once

### L-15 · Claim before create; a queue card is not a completion record

**Grade:** PROVEN.

**Learned.** A durable queue needs an exclusive claim before any side effect, and completion has to be read from the job's own records. A card that says `queued` or `accepted` is presentation; the job document and the verifier's record are state.

**Shown by.** Three concrete failures: a claimed item whose job was missing, which is a crash window that must block rather than licence a re-run; a completion check keyed on `state == "accepted"` that never fired, because opening the next wave resets that field; and an eligibility pass that re-ran features whose card still read `queued` after they were done.

**Practice.** Take an `O_EXCL` per-feature claim before creating anything. Skip features already in the done set even when the card says `queued`. Validate completion with the verifier's record (ok, commit, base revision, gitleaks, suite), not with a task field the reconciler never writes. Use `accepted_waves[].commit` or `last_commit` when a completion must name a revision. Refuse an unreadable record instead of dropping it.

**Portability.** Universal queue design; the record shape is bundlebees'.

**Evidence.** `tests/test_queue_factory_e2e.py` and the queue state machine in the provisioning handoff; [25 §Coordinator conformance](25-feature-packet.md).

**Limits.** The specific field names are implementation details. The invariant — claim, then act, then read the durable record — is not.

### L-16 · Adoption is identity, not resemblance

**Grade:** PROVEN.

**Learned.** After a lost acknowledgement, a journal entry that looks like your work is not proof of it. Adoption needs the attempt id, a non-empty objective, the exact `source_rev`, the exact `assigned_files`, a parseable creation time, and the job and task ids the brief was dispatched for. Zero plausible matches still does not prove absence, because the journal lags. A claimed work item is likewise kept, not consumed: deleting it on read loses the work when the agent turn dies mid-decision.

**Shown by.** A launcher blip flushed 30 minutes of buffered events at once, which made healthy bees look stuck and a completed dispatch look missing. Separately, identity matching against the public attempt view always failed because that view drops the brief; the raw record was the only usable source.

**Practice.** Match against the raw record and the whole journal, never a summary. Bound an uncertain outcome with a grace measured in **elapsed seconds** from a persisted first-uncertain timestamp, then escalate — never re-dispatch. A claim held by a dead process is adopted only after the same identity checks and a bounded staleness window; a live claim is waited on, never stolen. Treat a corrupt intent as corrupt, not missing: an unreadable record that is swallowed becomes permission to post again. Lock with `flock` and never unlink the lock file: the kernel releases it on death, and a live holder is not displaced however old the file looks. Claiming a work item marks it claimed and keeps it; only a recorded decision acknowledges and closes it.

**Portability.** Universal for at-least-once transports with a lagging journal.

**Evidence.** `tests/test_crash_recovery_e2e.py` and the autonomy-loop invariants in the orchestration handoff; [27 §Decision matrix](27-recovery-protocol.md) for the escalation path.

**Limits.** `exactly_once` may only be claimed when the host enforces server-side idempotency. Without it, the honest word is "adopted", and the honest bound is a grace window.

### L-17 · Exactly-once must be asserted from durable state

**Grade:** PROVEN.

**Learned.** A crash test needs a real child process, a durable worker ledger outside the coordinator's memory, and an armed fault that cannot re-fire after restart. A simulated crash inside one process proves the exception handler, not the recovery.

**Shown by.** Three checkpoints — after dispatch, after a wave record is persisted, and after a publish — where the child writes a fsynced marker and exits, and the restarted coordinator must resume from durable state alone. The tests count dispatches, wave records and mirror refs, compare integrated SHAs and the dependent source before and after, and require the same final tree plus both acceptance suites.

**Practice.** Make the production path call a checkpoint that is inert by default and registerable by a test, so production never kills itself. Count effects from durable state rather than reading a log. Treat a recovery that re-integrates, re-publishes or changes the derived source as a failure even when the tests pass. Assert the negative: a leftover branch with no record is not verified work — re-run every check from scratch.

**Portability.** Universal crash-testing pattern; hook names and record formats are local.

**Evidence.** `tests/test_crash_recovery_e2e.py` and `bundlebees_plugin/faults.py`; [27 §Runtime conformance](27-recovery-protocol.md) for the producer/consumer check.

**Limits.** A process kill is not power loss, and a file-level key is not an OS-level principal. Both were reported **NOT RUN**.

### L-18 · Diagnose from the event stream, not the state field

**Grade:** OBSERVED.

**Learned.** `state: running` is not progress. A launcher keeps a turn open while nothing happens: the only events are heartbeats with a climbing idle time, and the result endpoint answers 409. Conversely, a "successful" attempt can hold no patch at all.

**Shown by.** Five independent attempts did real tool work for two to four minutes, then went quiet within seconds of each other and emitted only heartbeats for the next 18 minutes while still reading `running` — a model or credential failure on the worker side, not five bad briefs. In a second incident, five attempts ended `succeeded` with an empty patch while `observed.files` listed every changed path: the files existed inside the container and could not be integrated.

**Practice.** Read the event `kind`, not `type`; judge by the age of the last non-heartbeat event and the mix of kinds. Several attempts stalling within seconds points at the model stream or network egress, not the briefs. After any stall or credential fix, send one canary before a whole wave. Never report a worker's work as delivered until a diff is in hand — `observed.files` proves files were written, not that anything can be reviewed.

**Portability.** Any worker runtime with an event stream. The field names are the launcher's; the triage method is not.

**Evidence.** The attempt-triage section of the orchestration handoff; [03 §4](03-development-and-orchestration.md) bee rules (worker claims are self-reported; a 20-minute silence may be a launcher blip).

**Limits.** The 10- and 30-minute thresholds are operational settings, not measurements, and they depend on the event cadence of the host.

## 7. Authority and supersession

### L-19 · A supersession corrects the contract; it never widens authority

**Grade:** PROVEN.

**Learned.** A failure inside an authorized job has three honest outcomes: retry the same contract, correct a contract that cannot be satisfied, or stop and ask the human who authorized it. The choice must be bounded by the authorization that already exists, and the correction must keep the contract's identity.

**Shown by.** The M4 dogfood: the first contract named a test that did not exist at the pinned revision, the loop classified it `specification`, superseded once, re-dispatched, and accepted the corrected patch with the failed attempt and its evidence preserved. The same protocol then refused a working runtime's documents, one rule at a time — `contract_corrections_allowed: true` instead of an integer, evidence as a prose string, a free-text failure code, a revisioned contract id — and each refusal named the exact rule.

**Practice.** One correction per task; same contract id, different hash; the old attempt and its evidence stay on disk. Corrected tests are a positional replacement of exactly the approved selectors — a menu invites a model to return every candidate, and production then correctly refuses a decision that looks like a model failure. The envelope comes from the sealed authorization and may only narrow it; when the authorization is silent, the ceiling is one attempt and zero corrections, and the proof is a job policy mutated upward that is refused. A mechanical component cannot name itself the deciding adapter.

**Portability.** High. The request/decision split is a pattern; the schema is one implementation.

**Evidence.** `schemas/recovery.schema.json`, `tools/recovery.py`, `tests/test_recovery_protocol.py`, required CI job `recovery-protocol`; [27](27-recovery-protocol.md); the archived pre-conformance pair from bundlebees `191dc85` is kept non-authoritative in `tests/fixtures/runtime/`.

**Limits.** v1 caps at five attempts and one correction, and has no automatic re-planning: a supersession corrects the selection, it does not decompose the feature differently.

### L-20 · Never manufacture a human gesture

**Grade:** PROVEN for the schema-enforced parts; OBSERVED for the policy.

**Learned.** An interactive gate exists to record that the human acted. A pseudo-terminal or scripted stdin satisfies it mechanically and turns chat consent into a forged record. Integrity is not consent either: an HMAC held by the coordinator proves the bytes were not edited, not that a person approved them.

**Shown by.** The job object's signature was described as integrity only, with authority kept in a separate object written through an interactive path the job can only narrow. A terminal-based enrolment gate was likewise recorded as workflow, not identity: an agent with coordinator access can satisfy it from a real terminal.

**Practice.** Prepare the exact command and hand it to the approver. Keep the receiver decision pinned `pending` in generated manifests, and require human gates to name merge, release, deploy and publish in every contract. Say plainly when a control is `NOT ENFORCED` — network egress to a provider and filesystem write protection for the same user usually cannot be enforced — instead of implying a sandbox that does not exist.

**Portability.** Universal.

**Evidence.** `tools/return_manifest.py` (`receiver_decision_not_pending`), [26 §Receiver decision](26-return-manifest.md), [16 §2](16-acdd-tdd.md) (`authorization.human_gates`), [27 §Limits](27-recovery-protocol.md) (`adapter` is a name, not authentication).

**Limits.** A schema stops a manifest edit, not a determined agent with a terminal. Only OS-level separation does that, and it is not claimed.

### L-21 · Separate the adapter from the reasoning

**Grade:** PROVEN for the protocol separation; OBSERVED for the experiment discipline.

**Learned.** Deterministic control flow and model reasoning are different evidence. A scripted adapter proves the loop; it does not prove that a model can decide. A real-model adapter is a separate experiment inside the same trust boundary, not a drop-in replacement for the deterministic one.

**Shown by.** A factory test that had to add a separately named test-only adapter to exercise the corrective path, because the production deterministic adapter correctly escalates a specification failure it cannot authorize. Separately, adapter tests passed on a host with the CLI installed and failed in CI with `unavailable` for every case, because the injected runner still discovered the binary.

**Practice.** Run the model in a fresh empty working directory through a noninteractive mode, hand it a read-only evidence package, and give it no state, repository, provisioner, approval key or dispatch access. Parse one strict JSON object; store the raw proposal with its SHA-256 and invocation metadata; compile the canonical decision mechanically without changing the model's action or tests; validate with the pinned protocol before acting. Malformed, ambiguous, unauthorized or timed-out output fails closed, and validation never "repairs" a wrong choice into a success. Inject the process boundary in offline tests and run them with a stripped `PATH`, so a host with the binary installed and CI without it behave the same. Label every result deterministic or real-model, and say which ran.

**Portability.** Universal for agent harnesses.

**Evidence.** [27 §No self-approved widening](27-recovery-protocol.md) (`adapter_reserved`), [27 §What bundlebees must emit](27-recovery-protocol.md); the real-model experiment and the PATH failure are recorded in the parallel-campaign handoff; `tests/test_runtime_conformance.py` checks producer and consumer against the same validator.

**Limits.** `adapter` is a name, not an authentication. The digest proves the decision answers this request, not who wrote it.

## 8. Briefs: what worked and what failed

### L-22 · Patterns that worked

**Grade:** OBSERVED.

**Learned.** A brief that consistently produced reviewable work carried the same elements: hard rules first; the exact full `source_rev`; a lease that matches the acceptance criteria and nothing else; one `AC-NNN` per observable behaviour, each naming one test id; "write the failing tests first and paste the RED output, then GREEN"; "never commit, never move HEAD"; and a report format that demands per-criterion evidence, commands with exit codes, and **NOT RUN** with reasons.

**Shown by.** Waves that produced patches the coordinator could verify in one pass, and the counter-case in L-24: briefs that allowed a worker to move `HEAD` came back with an empty patch.

**Practice.** Fix the interface in every brief before dispatch — module, function and CLI names, durable-record field names, environment variables, pinned revisions. Freeze any shared data contract verbatim in every brief that touches it, or two parallel workers invent incompatible ones. Carry the bound worker project in the brief, and let the signed lease inherit it. Hand over the problem and the bar, not a line-by-line fix; label a hunch about the cause as non-binding.

**Portability.** High. The vocabulary is local; the structure is not.

**Evidence.** [03 §7](03-development-and-orchestration.md), [19 §2](19-coordinator-playbook.md) brief template and rules, [13 §2](13-bundlebees-hardening.md) strict brief schema.

**Limits.** Descriptive. There is no A/B test of one element at a time.

### L-23 · Patterns that failed

**Grade:** OBSERVED.

**Learned.** Most bad outcomes traced to a brief or fixture that made the correct behaviour impossible or the wrong behaviour rational:

- **A file outside the lease, "even only locally."** The worker has no way to keep it local; give parallel slices a committed package skeleton instead.
- **A menu of allowed replacement tests.** The model returns all of them, the validator refuses the decision, and the run reads as a model failure when it is a prompt failure.
- **Fixture text that contradicts the approved selector.** A criterion that describes one behaviour while the approved test asserts another makes the model's defensible choice fail an exact-match assertion.
- **An acceptance criterion that assumes an unmeasured environment**, such as mirror-only container networking when the host's network policy was never measured.
- **An acceptance criterion pinned to a version string.** It breaks on every bump while the behaviour is unchanged.
- **An assumption of native Windows legs** on a Linux-only worker host.
- **A command chain that commits after the tests**, joined with `;` instead of `&&`, which publishes code from a failing suite and then contradicts the CI report.
- **A test named by a reference that matches no collected test.** Use the runner's real id, and remember a class-based test may need an explicit marker before the runner collects it.

**Shown by.** Each item above is a recorded brief or fixture defect, not a hypothetical.

**Practice.** Two failures on the same brief mean the brief is wrong: shrink the lease, split the task, or clarify the acceptance criteria before dispatching again. Fix the prompt and the fixture; never relax the validator or the authority check to make the first proposal succeed.

**Portability.** High. The specific marker (`__test__`) is Python; the failure mode is universal.

**Evidence.** [16 §12](16-acdd-tdd.md) dogfood rules; [27 §Worked example](27-recovery-protocol.md); the brief rules in the orchestration and provisioning handoffs.

**Limits.** These are the observed failures, not an exhaustive taxonomy.

### L-24 · The no-commit rule is a workaround, not the design

**Grade:** HISTORICAL.

**Learned.** A worker that commits inside its sandbox moves `HEAD`, and a patch built as `git add -A && git diff --cached HEAD` becomes empty. The work is lost with the container even though the attempt reads `succeeded`.

**Shown by.** Five "successful" attempts returning an empty patch while their file lists showed the changes — the same incident as L-18, seen from the tooling side.

**Practice today.** Every brief carries "do not commit, do not stash, do not move `HEAD`", the coordinator commits after retrieving and verifying the diff, and RED evidence comes from the worker pasting the failing output rather than from a commit. The coordinator keeps the worker's output as its own **verbatim, unaccepted** commit before a correction, so a reviewer can separate worker error from coordinator fix.

**Why it is historical.** The durable fix is to diff against the base commit the host recorded when seeding the sandbox, instead of against `HEAD`. That belongs to the worker-host repository and was proposed, not applied; until it lands, the rule is a convention that every brief must repeat.

**Portability.** The specific commands are the launcher's. Any worker runtime that computes a diff from a moving `HEAD` has the same failure.

**Evidence.** The orchestration handoff's no-commit rule and empty-patch report; [03 §4](03-development-and-orchestration.md) ("Don't commit inside the sandbox").

**Limits.** On a runtime that diffs against a recorded base, the workaround is unnecessary and the unaccepted-commit convention is the part worth keeping.

## 9. Porting the lessons to another stack

**Grade of this section:** RECOMMENDED. It is a checklist distilled from the lessons above, not a tested procedure.

Before trusting a parallel campaign on a new stack, answer these in writing:

1. What is the coordinator's integration budget, and which lane owns which files? (L-01, L-03)
2. Where is the measured capacity, and what does the host do to a wave that exceeds it? (L-02)
3. What check rejects a patch outside its lease, and what is the refusal code? (L-03)
4. Which acceptance claim is machine-checked, and which is a producer's sentence? (L-05, L-07)
5. Which checks fail when their dependency is absent, and which merely skip? (L-10)
6. What is the durable record of a claim, and what proves exactly one effect after a crash? (L-15 to L-17)
7. Which decisions may an agent make, which may it only narrow, and which require a person? (L-19, L-20)
8. How does a reviewer tell a deterministic run from a model run? (L-21)

If any answer is "the report says so", that item is **OBSERVED** at best.

## 10. What is not claimed, and what was left out

**Not claimed.**

- No figure in this chapter was re-measured while writing it. The 1,979 → 692 line correction, the `759 passed, 10 skipped` → `766 passed, 3 skipped` counts, the ~7-bee ceiling and the five empty patches are recorded campaign results; the attempt ids and run links are not public.
- The independent review that found blocking issues is recorded in [19 §4](19-coordinator-playbook.md); its individual findings are not reproduced here.
- Version-specific worker behaviours (launcher 0.1.15) may not hold on later releases. Treat them as historical detail, not current guarantees.
- Cost per accepted change is still **UNKNOWN** everywhere in this repository. No lesson here is priced.

**Deliberately omitted, with the reason.**

| Material | Why it is not a lesson here |
|---|---|
| Catalog, release, screenshot and naming rules | Product policy for one plugin ecosystem; they live in [06](06-rules-and-lessons.md) and the plugin-development skill |
| Host administration procedure (forced-command SSH, shell-version differences, host-key pinning) | Operational runbook for one host; it belongs to the runtime skill, and its transferable part ("prove the control from the calling side") is one line, not a lesson |
| Bee lifecycle commands (retrieve → verify → PR) | Already specified in [03 §4](03-development-and-orchestration.md) and [13](13-bundlebees-hardening.md); repeating them would create a second copy that drifts |
| Sandbox backend selection | Enforced and documented in [13 §1](13-bundlebees-hardening.md); this chapter would only restate it |
| Orbit UI routes and panels | Planned work in [17](17-orbit-plans.md), not a lesson |
| Numeric caps, model names and dates | Configuration, kept in the marked tables of [19](19-coordinator-playbook.md) |

## 11. Sources

Read on Nov 14, 2026, in full, read-only. They were not modified and are not copied here; this chapter cites them by name and hash so a later reader can tell which revision of the practice it describes.

| Source skill | Bytes | SHA-256 |
|---|---|---|
| `rizzstack-orchestration-handoff` (`SKILL.md`) | 76,637 | `c88c8532422936aa90501e5ad087fbd43df90a7eae3d70aa4796b46de87cbd50` |
| `rizzstack-provisioning-stack` (`SKILL.md`) | 24,979 | `19f2b7d09be9708feb39e8ac6975f7eb8e7cdb110d70626687e21a3c1443da5c` |
| `launcher-admin` (`SKILL.md`) | 8,191 | `ce3f4133c51221c9a4442246f1118b6ea8eec453c87d529c0ff48ad2c463a948` |

Existing chapters read for de-duplication, and linked rather than repeated: [03](03-development-and-orchestration.md), [06](06-rules-and-lessons.md), [09](09-reproducible-collaboration.md), [12](12-three-layer-architecture.md), [13](13-bundlebees-hardening.md), [16](16-acdd-tdd.md), [19](19-coordinator-playbook.md), [20](20-orchestrator-handoff.md), [25](25-feature-packet.md), [26](26-return-manifest.md), [27](27-recovery-protocol.md).

Repository evidence named in this chapter: `tests/test_feature_packet.py`, `tests/test_return_manifest.py`, `tests/test_recovery_protocol.py`, `tests/test_runtime_conformance.py` and the required CI jobs `feature-packet`, `return-manifest`, `recovery-protocol` (this repository); `tests/test_queue_factory_e2e.py`, `tests/test_queue_two_features_e2e.py`, `tests/test_crash_recovery_e2e.py` and `bundlebees_plugin/faults.py` (bundlebees); `tools/feature_packet.py`, `tools/return_manifest.py`, `tools/recovery.py` and their schemas (this repository). Pull requests named as provenance: bundlebees #3 and #4 (verifier hardening).
