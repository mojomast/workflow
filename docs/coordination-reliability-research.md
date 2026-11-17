# Coordination reliability research — the six failure classes and their unowned boundaries

**Status (2026-11-17):** PLAN-ONLY research. This document records, classifies and prescribes for
six recurring coordination failure classes in the rizzstack stack. It implements no change. The
acceptance gates below are commitments for a later, separately authorized implementation wave;
until that wave runs, every planned gate is a stated intention, not a shipped check.

**Third attempt.** Two earlier drafts of this document were refused by the coordinator-side secret
scan before commit. The refusals are themselves evidence and are treated as such in
[§4](#4-the-scan-diagnosability-finding). The hard constraint adopted for this draft: zero
secret-shaped literals anywhere — no credential-formatted examples, no provider-prefixed strings,
no high-entropy runs except real git revisions being cited. Credential formats are described in
prose only (for example, "a provider-prefixed token string", never the string itself).

**Audience:** the coordinator, the approver, and the implementer of the eventual hardening wave.
Read alongside [19](19-coordinator-playbook.md), [27](27-recovery-protocol.md),
[28](28-agent-lessons.md) and [31](31-campaign-continuity.md); this document classifies, those
chapters prescribe the mechanisms it measures against.

---

## 1. The shared root cause: unowned boundaries

The independent audit that reviewed the two refused attempts refined the root-cause statement, and
this revision adopts it as the organizing spine: **every failure class below is an unowned
boundary.** A boundary is *owned* when three conditions hold:

1. exactly one named mechanism on each side is the authority for the transition;
2. the transition is recorded durably at the moment it happens, by that mechanism;
3. a reader arriving after a crash can determine from records alone whether it happened.

Five boundaries recur. Each failure class is the observed cost of leaving one of them unowned:

| # | Boundary | Left side | Right side | Failure classes |
|---|---|---|---|---|
| B-1 | execution vs durable delivery | the worker's in-sandbox execution | the durable record that makes the work exist | FC-1 |
| B-2 | observed state vs restart | what the operator or coordinator observes mid-flight | what a restart can reconstruct | FC-2 |
| B-3 | coordinator vs beat | the reasoning coordinator agent | the mechanical scheduler pass that owns claims and dedup | FC-4 |
| B-4 | planned scope vs authorized scope | what the plan asserts (brief, gate, lease draft) | what durable state actually authorizes | FC-3, FC-6 |
| B-5 | evidence vs exported evidence | evidence that exists at the moment of the act | evidence discoverable where later readers need it | FC-5, [§4](#4-the-scan-diagnosability-finding) |

The classes are not six independent bugs. They are the same hole in five fences, observed six
times. The work packages in [§5](#5-work-packages) therefore gate on *boundary ownership* per
class, not on patches per incident.

## 2. The six failure classes

### FC-1 — Brief-commit omission (boundary B-1: execution vs durable delivery)

**Definition.** A worker executes real work; the durable commit step is omitted from every owned
path, so the execution leaves no record and the work is lost with the environment that produced it.

**Recorded instances.**

- November 2026 orchestration campaign: five attempts reported `succeeded` while carrying an empty
  patch; the host's observed file list named every changed path, so files existed inside the
  containers and could not be integrated. Root cause recorded in chapter 28 (L-24, L-18): the
  sandbox diff was computed against a moving `HEAD`, and the brief forbade the worker to commit,
  so the work vanished with the container (chapter 28 status 2026-11-14; the incidents are
  recorded in the orchestration handoff).
- The standing bee rule "Don't commit inside the sandbox" (chapter 03 §4) is the workaround
  version of the same omission: the brief owns a prohibition, nobody owns the durable step.
- The worker-host remedy — diff against the base revision the host recorded at seed time — is
  recorded as *proposed, not applied* by L-24 (chapter 28 status 2026-11-14); the pinned launcher
  source contradicts that status as of the pin: `upstream:hyvv@5bee1a87` `launcher.py` records the
  seed commit at seed time (`refs/hyvv/seed`) and diffs the returned patch against it
  (`_seed_project`, `patch`; pin dated 2026-11-13), so the diff-base half of the remedy is present
  in the worker host, not missing, and its home is the worker-host repository, not the brief
  author's discipline.

**Why the boundary is unowned.** Execution happens in a disposable sandbox; durable delivery
happens in the coordinator's tree. Between the two sits a transition — commit — that the brief
forbids to one side and never assigns to the other. The assignee of record today is the
coordinator, "commits after retrieving and verifying the diff" (L-24 practice today), which makes
delivery a manual convention rather than a mechanism: conditions 1 and 2 of
[§1](#1-the-shared-root-cause-unowned-boundaries) fail.

**External prior art (dated).**

- Jim Gray, "The Transaction Concept: Virtues and Limitations", *Proceedings of the 7th
  International Conference on Very Large Data Bases* (VLDB '81), Cannes, September 1981: a
  transaction's work exists only at its commit point; before it, the effect is provisional and
  may be undone without trace. An uncommitted execution is not a delivery.
- Diego Ongaro and John Ousterhout, "In Search of an Understandable Consensus Algorithm (Raft)",
  *USENIX ATC '14*, Philadelphia, June 2014: reality is the committed log; a restarted leader
  rebuilds from committed entries and treats anything else as unproven. The same discipline
  applies at one machine's edge: the committed revision is the only state a restart trusts.

**File comparison (rizzstack).**

- `upstream:bundlebees@875025b` `bundlebees_plugin/verify_local.py` — the owned counter-example:
  `verify --commit-local` performs the durable step inside a proven path (isolated worktree at the
  pinned base, RED before, GREEN after, local commit whose recorded shape the observability
  contract re-checks; this repository's `tests/test_obs_bottlenecks.py` pins the record shape that
  the bundlebees CLI verify writer and the verify_local commit-local path produce).
- `upstream:hyvv@5bee1a87` `launcher.py` (the worker host, extracted from the pre-extraction
  `pc-launcher/launcher.py` lineage shown in chapter 03's figure) — where the diff-base half of
  the L-24 remedy already lives: the host seeds the sandbox per brief, commits the seeded copy
  in-sandbox and records that commit as the seed base (`refs/hyvv/seed`, returned as
  `seed_commit`), and the patch collector diffs the returned patch against that recorded base —
  not against the sandbox's moving `HEAD`, which survives only as the fallback for attempts seeded
  before the record existed (`_seed_project`, `patch`; pin dated 2026-11-13). What the host still
  leaves unowned is the durable commit itself: it returns the patch and integrates nothing, so
  delivery remains the coordinator's manual convention (L-24, "practice today").
- *Open question for the next wave:* `upstream:bundlebees@875025b` `bundlebees_plugin/tools.py`
  was named in the audit's file set; its role in this boundary has not been confirmed against the
  pinned checkout in this workspace (the checkout is absent here — see [§6](#6-limits-and-status)).

**Candidate remedy (plan-only).** Assign the durable step: the worker host already records the
seed base and diffs against it (`upstream:hyvv@5bee1a87` `launcher.py`, `_seed_project`/`patch`),
so patch capture is owned — what remains unowned is the commit that makes the work durable:
either the executor's verify owns a commit-local delivery for every attempt (executor-owned), or
an integration step above the returned patch is assigned in writing (coordinator- or host-owned).
Pick one owner in writing, carry the rejected alternative, and gate it — AC-003, AC-004.

### FC-2 — Restart-into-lane (boundary B-2: observed state vs restart)

**Definition.** After a coordinator, launcher or host restart, work is re-entered into a lane from
observed state (board columns, cards, chat, lease files) instead of from durable records, so the
restart duplicates in-flight work or loses it.

**Recorded instances.**

- The Jackpot Syndicate build (2026-11-14/15, chapter 31): the bundlebees lease directory held
  **22 lease files naming the campaign's repository while the job directory held 15 job documents,
  all of them `smoke-*`** — there was no campaign job document and no queue entry. A restart had
  nothing durable to reconcile at campaign level; the coordinator reconstructed progress from
  leases, Git and chat on every turn. The six recorded owner nudges total 1 h 9 m 39 s of wall
  clock, all classified tick-stopped rather than worker-stuck.
- The host-side variant (chapter 28 L-02, worker-host report of 2026-11-12): a Docker/WSL restart
  kills every running container, so a dispatch into a pending restart is lost work rather than a
  retry.
- The historical control that worked: "Orbit and launcher restarts reattach by attempt id and
  never re-dispatch" (chapter 03 §4). It is a rule, not a mechanism — nothing enforces it at the
  lane boundary.
- The owned counter-example: chapter 31 §31.3 defines restart reconciliation from durable state
  only ("adopt completed and in-flight work from the job's durable state — do not dispatch a
  second time"), and the bundlebees crash-recovery suite proves adoption from durable records
  after real process kills (`tests/test_crash_recovery_e2e.py`, `bundlebees_plugin/faults.py`;
  chapter 28 L-16, L-17).

**Why the boundary is unowned.** The lane's "is something running here?" answer lives in observed
state (cards, chat, in-memory tallies), while the durable claim — the only answer that survives a
restart — lives in the job store, the dispatch intent and the lease. On restart, the coordinator
reads the cheap side. Condition 3 of [§1](#1-the-shared-root-cause-unowned-boundaries) fails: a
reader after a crash cannot tell from records alone whether the lane's work is claimed, done or
never started.

**External prior art (dated).**

- K. Mani Chandy and Leslie Lamport, "Distributed Snapshots: Determining Global States of
  Distributed Systems", *ACM Transactions on Computer Systems* 3(1), February 1985: a meaningful
  global state is a consistent snapshot captured by a defined protocol — not a collage of whatever
  each observer last saw. A restart must reconcile against a snapshot, not against sightings.
- Leslie Lamport, "Time, Clocks, and the Ordering of Events in a Distributed System",
  *Communications of the ACM* 21(7), July 1978: telling a continuation from a re-execution
  requires a recorded happened-before order. Adoption-by-identity (chapter 28 L-16) is this rule
  applied to attempt records.
- Eric A. Brewer, "CAP twelve years later: How the 'rules' have changed", *IEEE Computer* 45(2),
  February 2012: in the presence of uncertainty, the correct behavior is an explicit state with a
  bounded grace, not a guess — the same shape as the grace-window adoption rules in L-16.

**File comparison (rizzstack).**

- `upstream:bundlebees@875025b` `bundlebees_plugin/agent_consumer.py` — the owned claim/adoption
  surface for the one reasoning transition: durable `pending → claimed → completed | refused`,
  single active claim, TTL and dead-pid adoption, at most two claims (chapter 22 §11, chapter 23
  M4.3 row). It is the template the lane-level restart invariant should copy.
- `upstream:hyvv@5bee1a87` `launcher.py` — the reattach surface: the pre-extraction lineage
  already carried the right rule (reattach by attempt id, never re-dispatch); the extraction is
  where the rule should have become a mechanism instead of a chapter sentence.
- `upstream:bundlebees@875025b` `bundlebees_plugin/cli.py` — the verbs a restarted operator
  actually has (`job tick`, `job recover --repo`, `campaign reconcile`); the gap is that the
  campaign-level record those verbs reconcile against did not exist in the recorded Jackpot case.

**Candidate remedy (plan-only).** Make the durable claim precede every lane dispatch and make the
restart reconcile only against it (chapter 31 §31.3 already specifies the reconciliation; the gap
is that campaign-level dispatches can exist without a campaign record at all). Gates AC-005,
AC-006.

### FC-3 — Fabricated-revision dispatch (boundary B-4: planned scope vs authorized scope)

**Definition.** A brief, gate or contract asserts a revision, pull request or test that durable
state cannot prove exists, and dispatch proceeds on the assertion.

**Recorded instances.**

- `plans/backlog.json`, slice F5, transition recorded 2026-11-16T15:19:41-05:00: the seeded gate
  named a merged-pull-request reference for workflow PR 60 — "workflow PR 60 does not exist;
  bb#60 was closed superseded by bb#65". The transition was executed only after
  `gate_repaired_then_historic_dispatch`: the plan's gate pointed at a revision of the world that
  never was.
- The M4 dogfood (chapter 24, 2026-11-14; chapter 28 L-19): the first contract named a test that
  did not exist at the pinned revision; the recovery protocol classified it `specification` and
  superseded once — the correct bounded path, reached only after a fabricated reference was
  dispatched.
- Chapter 28 L-06: a CLI's tests mocked two routes that did not exist on the launcher; the suite
  went green and every live run failed closed with `capacity_check_failed` — a fabricated
  interface, asserted into existence by fixtures.
- Chapter 28 L-13: a packet pinned before its schema existed was refused as
  `workflow_ref_unsupported`, and a pin outside the fetched refs cannot resolve — the machine
  refuses what the plan asserted.

**Why the boundary is unowned.** The plan (brief, gate, contract) is written in one place and the
authorization (the durable store, the fetched refs, the pinned schema) lives in another. Nothing
at dispatch time validates that the plan's references resolve; validation happens later, at
verify, where the cost is a wasted attempt and a recovery cycle. Condition 1 fails in a specific
way: the plan side *speaks* for the authorization side without being it.

**External prior art (dated).**

- Santiago Torres-Arias et al., "in-toto: A Framework to Define and Protect the Software Supply
  Chain", *Proceedings of the 2019 ACM SIGSAC Conference on Computer and Communications Security
  (CCS)*, London, November 2019: every step of a software pipeline records the materials it
  actually consumed as attestations, so what a later stage *claims* to have used is checked
  against what was *recorded* as used. Dispatch against a fabricated revision is exactly the
  missing attestation.
- Scott Chacon and Ben Straub, *Pro Git*, 2nd edition, Apress, 2014: a revision exists if and only
  if it is reachable in the object database; "latest main" is not a baseline (the same sentence
  the coordinator playbook repeats as a brief rule). The object database is the referee the plan
  must be checked against before dispatch, not after.

**File comparison (rizzstack).**

- `upstream:bundlebees@875025b` `bundlebees_plugin/cli.py` — the dispatch/gate verb surface where
  the F5-class check belongs: at gate evaluation and dispatch, resolve every named revision and
  reference against fetched refs before the attempt is created. The brief schema already demands
  a full-length `source_rev` (chapter 13 §2); what is missing is the *resolution* check at
  dispatch.
- `upstream:hyvv@5bee1a87` `launcher.py` — the host-side authorization boundary the plan must not
  outrun: projects must be on the launcher's allow-list, and authorizing a new repo means
  restarting the launcher with the owner's OK (chapter 03 §4). A plan that assumes a repo is
  authorized when the host has not restarted asserts scope it does not have — the same class as
  the fabricated revision, one boundary down.
- `upstream:bundlebees@875025b` `bundlebees_plugin/tools.py` — open question as in FC-1; the
  audit named it, this workspace cannot confirm its role (see [§6](#6-limits-and-status)).

**Candidate remedy (plan-only).** Dispatch-time resolution: every reference a gate or brief names
(a revision, a pull request, a test id) must resolve against the durable store or the fetched refs
at the moment of dispatch, and unresolvable references are a refusal with a stable code, not a
post-hoc repair. Gates AC-007, AC-008.

### FC-4 — Coordinator-duplicates-machinery (boundary B-3: coordinator vs beat)

**Definition.** The coordinator agent reimplements, outside the durable store, the machinery the
beat owns — dispatch cadence, duplicate suppression, capacity accounting, claim management — so
the guarantees that depend on durable state silently stop holding.

**Recorded instances.**

- The Jackpot Syndicate build (chapter 31): authority was per-lease dispatch with no job document
  and no campaign/queue entry — the coordinator ran the beat by hand in chat. Chapter 31 states
  the boundary plainly: "The campaign layer does not dispatch. Duplicate suppression remains in
  the job's dispatch intent/idempotency key, the signed lease and the queue's exclusive claim."
  A coordinator dispatching per lease bypasses exactly those three.
- Chapter 28 L-08: an end-to-end harness resolved the descendant rule and sealed the derived
  authorization between queue passes while the production runner did not — the harness did the
  production step. The test-side twin of the coordinator-side duplication: in both cases a
  second actor performs machinery steps whose ownership belongs to one mechanism.
- Chapter 31 §31.1: every continuity pause was classified tick-stopped — the beat was not running
  because there was no resident beat, only coordinator turns. The machinery existed as commands;
  nothing owned running them.

**Why the boundary is unowned.** The beat (`job tick`, the queue pass, the reconciler) is a
mechanism; the coordinator is a reasoning agent that may only narrow its authorization (chapter
27's rule). Nothing detects the moment the coordinator stops driving the beat and starts *being*
the beat, because the coordinator's chat turns are not recorded as transitions against the durable
store — conditions 2 and 3 of [§1](#1-the-shared-root-cause-unowned-boundaries) fail together.

**External prior art (dated).**

- Mike Burrows, "The Chubby lock service for loosely-coupled distributed systems", *7th USENIX
  Symposium on Operating Systems Design and Implementation (OSDI '06)*, Seattle, November 2006:
  provide one coarse-grained service that owns locks, sequencing and liveness announcements, so
  thousands of clients do not each improvise their own — and so the guarantee is uniform because
  the owner is single.
- Philip A. Bernstein and Nathan Goodman, "Concurrency Control in Distributed Database Systems",
  *ACM Computing Surveys* 13(2), June 1981: correctness of interleaved effects is a property of
  the concurrency-control mechanism; discipline that lives in convention instead of the mechanism
  is not correctness. Exclusive claims and idempotency keys are the mechanism side of exactly the
  duplicate suppression the coordinator duplicated by hand.

**File comparison (rizzstack).**

- `upstream:bundlebees@875025b` `bundlebees_plugin/cli.py` — where the beat lives as verbs;
  `job tick` is specified as mechanical, one heavy op, no inference (chapter 22 §6, §11).
- `upstream:bundlebees@875025b` `bundlebees_plugin/agent_consumer.py` — the deliberate split this
  boundary demands: the mechanical tick never calls inference; a separate consumer process claims
  the one reasoning transition. The coordinator's correct role is the consumer's caller, not a
  second tick.
- `upstream:bundlebees@875025b` `bundlebees_plugin/tools.py` — open question as above (AC-010).
- Workflow-side witness: `tests/test_runtime_conformance.py` and
  `tests/test_decision_queue.py` in this repository pin producer/consumer conformance for the
  decision surface — the pattern (one producer, one mechanical validator) that the campaign
  dispatch surface lacks.

**Candidate remedy (plan-only).** An observable rule, not new code: a campaign may dispatch only
through the beat, and every coordinator-initiated dispatch outside the beat is a recorded defect
with a stable name. First deliverable is the *decision record* (who owns dispatch), then the
gate. AC-009.

### FC-5 — Registry-after-merge chase (boundary B-5: evidence vs exported evidence)

**Definition.** Work merges with its evidence in place but unexported; a later companion PR then
chases the changelog/registry coverage the merge should have carried — and the chase itself
becomes new merges needing coverage.

**Recorded instances.**

- The 48-hour docs-parity audit (owner directive 2026-11-16; window exactly workflow PRs #35–#40,
  closing at the #40 merge, 2026-11-16 21:38:41Z): merges had landed without changelog coverage;
  coverage then arrived via later docs-sync companions.
- The chase is visible in this repository's own guard: `tests/test_docs_parity.py` carries
  explicit exclusions for workflow PRs #56, #62, #64 and #67, each a "docs-sync companion" whose
  *own* diff is bookkeeping that must carry its own exclusion "so merging it leaves main green" —
  the chase pattern recorded in code.
- The self-referential defect: the #67 exclusion names "the main Unreleased-heading repair after
  the #57 self-registration mangle" — a registry entry that mangled the section it was
  registering into, requiring a second companion to repair the register.
- The counter-move already in place: `tests/test_docs_parity.py` converts the chase into a
  merge-time duty (every merged campaign PR at or after #35 must have a registry row whose
  keywords appear in the changelog's Unreleased section, or an exclusion with a reason; open work
  must sit in the In-review subsection so it is not implied shipped).

**Why the boundary is unowned.** The evidence (the merged diff, the passing suite) exists at merge
time; the exported evidence (the changelog entry, the registry row) has no owner at that moment,
so it accrues as debt that a later PR pays — and the paying PR itself must be covered, which is
why the chase is self-perpetuating. Conditions 1 and 2 of
[§1](#1-the-shared-root-cause-unowned-boundaries) fail: no named mechanism exports at the moment
of the act.

**External prior art (dated).**

- Martin Fowler, "Continuous Integration", martinfowler.com, 1 September 2006: the integration
  result is published state everyone can see, and keeping it visible is the mechanism that keeps
  integration cheap; hidden state — merged but unannounced — is precisely the state that rots.
- Jez Humble and David Farley, *Continuous Delivery*, Addison-Wesley, 2010: the deployment
  pipeline is the traceability record — every artifact is traceable to its revision *by the
  pipeline*, not by anyone's memory of it. A merge that leaves no pipeline-visible trace has not
  delivered its evidence, whatever its diff says.

**File comparison (rizzstack).**

- `tests/test_docs_parity.py` (this checkout) — the merge-time gate this boundary needs, already
  implemented here; its docstring names its bundlebees counterpart
  (`tests/test_changelog_coverage.py`, the docs-sync §66 pattern), the same gate in the executor
  repo.
- `upstream:bundlebees@e7f95ca` `tests/test_changelog_coverage.py` — the executor-side twin named
  by this repository's guard; the pair is the existing owned export path, and the chase
  instances above are the record of what happens when merges precede it.

**Candidate remedy (plan-only).** Treat the registry row as part of the change, not a follow-up:
the coverage row (or an exclusion with a reason) rides in the same PR as the work it covers. The
guard exists; what is missing is the convention that a campaign PR without its row is not ready
to merge. Gates AC-011, AC-012.

### FC-6 — Immutable-lease dead-ends (boundary B-4: planned scope vs authorized scope)

**Definition.** The authorization artifact for an attempt (the lease) is immutable by design, but
there is no lawful path to correct or replace it — so a wrong or orphaned lease turns into a
dead-end: verify refuses forever, or the work must be re-dispatched as a fresh attempt while the
old lease and its authority linger.

**Recorded instances.**

- The lease mechanics (chapter 13 §3, landed with PRs #3 and #4, merged 2026-11-12): the lease is
  created once at dispatch (create-exclusive, mode 0400, HMAC-signed with a key file the operator
  holds); verify refuses a missing lease and an edited lease with stable codes, and ignores — then
  reports — any scope the worker's result claims. The manual lease-recording verb "refuses to
  overwrite". Every one of those refusals is correct; none of them is a *correction path*.
- The abbreviated-path incident (recorded in chapter 19's RESEARCH-BEFORE-RETRY subsection as a
  known pitfall carried from the sibling lane): abbreviated lease paths in a brief once caused a
  `scope_violation` refusal — a planning-side spelling error expressed as a hard authorization
  mismatch, resolvable only by a fresh attempt.
- The orphaned-authority instance (chapter 31, Jackpot): 22 lease files standing as the *only*
  authority for a whole campaign, with no job document above them — immutable per-attempt
  authorizations with nothing owning the campaign-level scope they were meant to add up to.
- Chapter 28 L-03 states the residual limit plainly: "A lease bounds files, not behaviour." The
  immutable artifact cannot even represent the correction the recovery protocol knows how to make
  for contracts (one supersession, same identity, hash-anchored — chapter 27); no such convention
  exists for leases.

**Why the boundary is unowned.** Planned scope (the brief's assigned files) and authorized scope
(the lease's recorded paths) are two artifacts written at two moments by two writers, and the
authorized side is deliberately immutable — which is right for integrity and wrong for repair:
there is no owned transition from "this authorization is wrong" to "here is the corrected
authorization, by the authority that issued it". Every correction today is a bypass (new attempt,
new lease, old lease orphaned).

**External prior art (dated).**

- Carey L. Gray and David R. Cheriton, "Leases: An Efficient Fault-Tolerant Mechanism for
  Distributed File Cache Consistency", *SOSP '89* (ninth ACM Symposium on Operating Systems
  Principles; ACM SIGOPS Operating Systems Review 23(5)), 1989: a lease's defining property is
  that it *expires* — authority is granted for a bounded interval so stale grants self-heal
  without revocation machinery. The bundlebees lease has the opposite shape: unbounded lifetime
  and no replacement path, so stale or wrong grants persist and dead-end.
- Pat Helland, "Immutability Changes Everything", *7th Biennial Conference on Innovative Data
  Systems Research (CIDR 2015)*, Asilomar, January 2015: immutable data is managed by append-only
  correction — a later record supersedes an earlier one, both preserved; edits are replaced by
  correction records. A superseded-lease convention is the CIDR-2015-shaped answer and already
  has a protocol precedent in this stack: the recovery protocol's supersession for contracts
  (chapter 27).
- Jerome H. Saltzer and Michael D. Schroeder, "The Protection of Information in Computer Systems",
  *Proceedings of the IEEE* 63(9), September 1975: complete mediation — every reference to an
  object is validated against authority at the moment of use, and the authority-changing path is
  part of the protection design, not an afterthought.

**File comparison (rizzstack).**

- `upstream:bundlebees@875025b` `bundlebees_plugin/verify_local.py` — the enforcement half, owned
  and proven: refuse missing, refuse edited, refuse out-of-scope (chapter 22 §8 step 2). The
  missing half is the issuance side: a signed, auditable supersession for a lease that was
  recorded wrong.
- `upstream:bundlebees@875025b` `bundlebees_plugin/cli.py` — the lease verb that "refuses to
  overwrite" (chapter 13 §3); the same verb surface is where a lease-supersession path would live
  if the AC-013 decision picks the supersession remedy.
- `upstream:hyvv@5bee1a87` `launcher.py` — the host-side twin of the same boundary: the allow-list
  plus restart rule means a scope change at the host is a restart event with an owner (the
  operator), while a scope change at the lease has no owned event at all.

**Candidate remedy (plan-only).** A decision record first: either leases gain an expiry (the
SOSP '89 shape) or a signed supersession record (the CIDR 2015 / chapter 27 shape); both rejected
alternatives must be written down. Then orphan accounting: leases without a job document are a
reported state, not silent accumulation. Gates AC-013, AC-014, AC-015.

## 3. Why the classes persisted across attempts

Each class survived its first recording because the boundary it violates has no owner whose job
title includes noticing it: the coordinator notices coordinator-shaped failures (FC-4 would be
self-accusation), the beat notices beat-shaped failures (FC-2's restart is exactly when the beat
is absent), and the scan (FC-5, [§4](#4-the-scan-diagnosability-finding)) reports at a level too
coarse to drive repair. The work packages therefore assign each boundary a named owner side
first, mechanisms second.

## 4. The scan diagnosability finding

**What happened.** Two prior drafts of this document were refused by the coordinator-side secret
scan (the same check the repository gates as `bee-ci/secret-scan`, a full-history gitleaks scan
pinned and checksum-verified per `docs/CI.md`). Each refusal reported that *a finding exists*;
neither refusal named the line, the detector or the matched text. The author could not tell a
real leak from a prose example about credentials.

**Why it belongs in this research.** It is boundary B-5 applied to the scan itself: the scan's
evidence is not exported to the place and shape where correction happens. Two supporting facts
show the gap is in the *surfacing*, not the tool: (a) the repository's own ignore file
(`.gitleaksignore`, which carries an allow-list entry for a schema example addressed by detector
id and line number) proves line-attributed addressing exists end to end; (b) gitleaks reports
name file, line and rule in its report formats — the collapse happens between the tool and the
refusal the author sees.

**Consequences recorded here.** Two drafts were lost to repairable prose, and the repair rule
("rewrite any matching line in prose") had to be reconstructed by the author without knowing
which line matched — the exact cost pattern FC-5 records for changelogs, applied to security
gating.

**Candidate remedy (plan-only).** A repo-local self-check, run before push, that runs the same
detector class locally and prints file, line, rule and matched-shape classification for every
finding — so refusal never arrives as an unexplained verdict. It must remain a *pre-flight
convenience*, not a weakening: the required context stays the CI scan. Gates AC-016, AC-017.

## 5. Work packages

Gate format follows the brief template in chapter 19: `AC-NNN <observable behavior> -> proven by
<path::test>`. Tests marked *(planned)* are commitments for the implementing wave and do not
exist at the time of writing; tests named without the marker exist in the named checkout and are
cited as the anchor. Cross-repo paths use the `upstream:<repo>@<pin>:` convention from the memory
audit. Where the deliverable is a decision record inside this document, the guard is a planned
test module for this repository (`tests/test_coordination_reliability.py`) that parses and
asserts the record's presence and shape — the same pattern `tests/test_docs_parity.py` uses for
chapters.

### WP-1 — Boundary ownership map (this document)

- AC-001: The five boundary pairs are recorded with the failure-class mapping and one named
  owner-side mechanism per pair, and the mapping table parses mechanically ->
  proven by tests/test_coordination_reliability.py::test_boundary_matrix_complete *(planned)*
- AC-002: Every FC section carries at least two dated external citations and at least one named
  rizzstack file comparison ->
  proven by tests/test_coordination_reliability.py::test_fc_sections_citations_and_files *(planned)*

### WP-2 — FC-1 commit ownership decision

- AC-003: A decision record names the owner of the durable commit step (the coordinator's
  post-retrieval commit as in L-24 practice today, executor commit-local, or a host-owned
  integration step above the seed-base patch capture) with the rejected alternatives written down ->
  proven by tests/test_coordination_reliability.py::test_commit_owner_decision_recorded *(planned)*
- AC-004: The worker host records the sandbox seed base and the returned patch is computed against
  that recorded base, not against a moving `HEAD` — behavior already present at the pin
  (`upstream:hyvv@5bee1a87` `launcher.py` `_seed_project`/`patch`, pin dated 2026-11-13; hyvv
  `main`, read 2026-11-17, hardens it by refusing a `HEAD` fallback in `_verify_workspace`), which
  this gate locks ->
  proven by upstream:hyvv@5bee1a87:tests/test_seed_base_diff.py::test_patch_diffs_recorded_base
  *(planned, NOT RUN — the test module does not exist at the pin; the asserted behavior does)*

### WP-3 — FC-2 restart reconciliation at lane level

- AC-005: A restart never dispatches into a lane whose durable claim is live; adoption of a dead
  claim requires the identity checks of L-16 and a bounded grace ->
  proven by upstream:bundlebees@875025b:tests/test_crash_recovery_e2e.py::test_restart_adopts_never_redispatches
  *(planned; the module exists and already proves the adoption half)*
- AC-006: A campaign-level durable record exists before the first lane dispatch, so a restart has
  something to reconcile ->
  proven by upstream:bundlebees@875025b:tests/test_campaign_continuity.py::test_campaign_record_precedes_first_dispatch
  *(planned, NOT RUN)*

### WP-4 — FC-3 dispatch-time resolution

- AC-007: Every revision, pull request and test id a gate or brief names resolves against the
  fetched refs or the durable store at dispatch time; unresolvable references are refused with a
  stable code before the attempt is created ->
  proven by upstream:bundlebees@875025b:tests/test_dispatch_gate_resolution.py::test_unresolvable_gate_reference_refused
  *(planned, NOT RUN)*
- AC-008: The F5 incident class (a gate naming a nonexistent pull request) is recorded as a
  named classification with its evidence reference ->
  proven by tests/test_coordination_reliability.py::test_fabricated_reference_incident_recorded
  *(planned)*

### WP-5 — FC-4 beat ownership

- AC-009: The decision record states that only the beat dispatches within an authorized campaign
  and names the coordinator-initiated outside-the-beat dispatch as a defect with a stable name ->
  proven by tests/test_coordination_reliability.py::test_beat_ownership_decision_recorded
  *(planned)*
- AC-010: The role of `bundlebees_plugin/tools.py` is confirmed or corrected against the pinned
  bundlebees checkout and recorded in this document's revision history ->
  proven by tests/test_coordination_reliability.py::test_tools_py_role_recorded *(planned)*

### WP-6 — FC-5 merge-time export

- AC-011: Every campaign PR merges together with its changelog coverage row (or an exclusion with
  a reason); the guard enforces it at merge time, not afterwards ->
  proven by tests/test_docs_parity.py::test_registry_covers_every_merged_campaign_pr_in_window
- AC-012: Companion PRs remain single-purpose: one row or one exclusion per companion, and no
  companion's own bookkeeping breaks the gate it serves ->
  proven by tests/test_docs_parity.py::test_registry_rows_are_well_formed

### WP-7 — FC-6 lease correction path

- AC-013: A decision record picks the lease-correction shape (bounded expiry, or signed
  supersession) with the rejected alternative recorded ->
  proven by tests/test_coordination_reliability.py::test_lease_correction_decision_recorded
  *(planned)*
- AC-014: Leases that name no job document are reported as a counted state (orphan authority),
  not silently accumulated ->
  proven by upstream:bundlebees@875025b:tests/test_campaign_continuity.py::test_orphan_lease_report
  *(planned, NOT RUN)*
- AC-015: The correction shape chosen by AC-013 is implemented: a superseded lease keeps the
  original on disk, carries the superseding record, and verify accepts the corrected lease
  exactly once ->
  proven by upstream:bundlebees@875025b:tests/test_lease_supersession.py::test_superseded_lease_accepted_once
  *(planned, NOT RUN)*

### WP-8 — Scan diagnosability

- AC-016: A repo-local pre-flight self-check reports file, line, rule and shape-class for every
  secret-scan finding before push, without weakening the required CI gate ->
  proven by tools/secret-selfcheck.py::test_reports_file_line_rule_and_class *(planned, NOT RUN)*
- AC-017: This document passes the repository's required secret-scan gate with zero findings ->
  proven by .github/workflows/ci.yml::bee-ci-secret-scan

## 6. Limits and status

- The hyvv, bundlebees and orbitdesktop trees are not checked out in this workspace. All
  cross-repo statements cite the pinned revisions recorded in `profiles/repos.json` and the
  chapters written against those trees; nothing here re-verified them against the live trees.
  Cross-repo citations therefore carry the same status chapter 28 gives unreviewed self-reports:
  recorded, not re-run — with one deliberate exception: the FC-1 worker-host diff-base statements
  were re-verified on 2026-11-17 against the pinned source itself (`upstream:hyvv@5bee1a87`
  `launcher.py`, fetched from raw.githubusercontent.com), because the sentence they replace
  contradicted the pin it cited. The planned tests named in AC-004, AC-005, AC-006, AC-007,
  AC-014, AC-015 and AC-016 are *NOT RUN* and exist only as commitments.
- `bundlebees_plugin/tools.py` appears in the audit's named file set but not in the chapters this
  document cites; its role is an open question (AC-010), stated rather than guessed.
- This document performs no implementation: no code, no schema, no test is added by this branch.
- Plan status: this is a research artifact. It becomes evidence only when the gates it names run.

## 7. Prior art actually read, known pitfalls, and rejected alternatives

**Prior art actually read (in this workspace, for this document):** chapters 03, 13, 19, 21, 22,
23, 24, 27, 28, 30 and 31; `tests/test_docs_parity.py`; `profiles/repos.json`;
`plans/backlog.json` (the F5 transition record); `.gitleaksignore`; `docs/CI.md`;
`upstream:hyvv@5bee1a87` `launcher.py` (read from the pinned raw source at
raw.githubusercontent.com on 2026-11-17, not in this workspace); the external works cited per
section above, cited from knowledge of the works and dated — not re-read from copies in this
workspace, and marked accordingly.

**Known pitfalls carried in (each from a recorded incident):**

1. Secret-shaped literals in prose examples are the two-refusal pitfall; formats are described in
   prose only, and the self-check of [§8](#8-self-check-record) is mandatory before commit.
2. Abbreviated lease paths once caused a `scope_violation` refusal; file comparisons use exactly
   the paths recorded in the pinned chapters.
3. Prose-byte-pinning conformance tests proved brittle; the planned guards (AC-001, AC-002) assert
   structure (counts, presence, dates) rather than exact sentences.
4. Never relax a validator or an authority check to make a first proposal succeed (chapter 28
   L-23); the remedies above add refusals and decision records, none relaxes one.
5. An unrun check is a status, not a zero (chapter 28 L-09); planned tests are labelled *planned,
   NOT RUN*, never counted as passing.

**Documented rejected alternatives (with reasons):**

1. *Route this research through bundlebees as a dispatched multi-lane campaign.* Rejected: the
   deliverable is one guarded document in this repository; a campaign would have the coordinator
   re-implement beat machinery for a single-artifact deliverable — committing the exact FC-4
   defect while researching it.
2. *Include worked examples of credential formats so readers can recognize what the scan
   catches.* Rejected: two prior refusals demonstrate the cost, and the scan reports shape not
   location, so examples buy recognition at the price of the document's own passability. Prose
   descriptions carry the same teaching value with none of the risk.
3. *Implement the worker-host base-diff fix in this branch now.* Rejected: there is no unapplied
   fix to port — the recorded-seed-base diff is present in the worker host at
   `upstream:hyvv@5bee1a87` (`launcher.py` `_seed_project`/`patch`, pin dated 2026-11-13); what
   remains open there is the AC-004 test lock and the AC-003 commit-owner decision, and this
   branch is plan-only with a one-file scope.

## 8. Self-check record

Before commit, this file was checked with the agreed self-check command for credential-shaped
literals (a trigger-word scan for assignment-shaped credential values) and with a standalone
high-entropy sweep in which every run over 24 characters must be a cited git revision or an
inspected path/date. The commands and their results are recorded in the delivery report of this
branch; the required CI gate (`bee-ci-secret-scan`) remains the authoritative check, and AC-017
gates on it.

## 9. Merge-time duty of this document itself

Merging this branch triggers the coverage duty this repository's own guard enforces
(`tests/test_docs_parity.py`): a registry row (or an exclusion with a reason) for this PR, with
keywords present in the changelog's Unreleased section. This branch's scope is this file only, so
that row is the merging campaign's first act under WP-6 — the document opens with its own gate
obeying it.
