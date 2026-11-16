# M2 contract-enforcement canary runbook (rizzstack-m2-canary)

**Status:** pre-staged on 2026-11-16, not executed. **Trigger:** the runbook runs the moment F2
(require-contract) merges — the campaign packet that turns contract enforcement on through bundlebees'
`require_contract` machinery (docs/16-acdd-tdd.md §9). Until that merge nothing here dispatches, and the
packet that registers this canary ([plans/packets/M2-canary.md](../plans/packets/M2-canary.md)) stays
blocked. **Base:** workflow main `9f6aa6dc7a74890ef2284d7aa4432efc9b6a4169` (fetch fresh if `origin/main`
has advanced, and re-check this runbook against the newer revision before dispatching — the packet's
provenance pins this base). **Scope:** one fresh dedicated smoke project, `rizzstack-m2-canary`, one bee,
one synthetic feature — and **no production project** is created, modified, merged, deployed or deleted by
any step below.

The protocol being exercised is defined in docs/16 (`acdd/1` contracts, freezing, RED/GREEN validity,
failure codes, enforcement); this runbook only sequences it. Approval authority: Kyle Durepos
(`mojomast`) — Steps 1, 12 and the cleanup's archive/delete need his explicit yes in his own words; an
agent's go-ahead never stands in for it.

## Command surface — documented verbs, confirmed flags

Every command below uses a verb documented in docs/16 §10 or docs/23 (`contract validate|freeze`,
`tdd red|refactor|review|report`, contract-aware `verify`, `integrate`, provisioning and the job↔project
binding). The binary name and the exact flags are confirmed in **Step 0** against the revision F2 actually
merged — this checkout does not carry the bundlebees tree, so nothing here is invented silently: where a
flag is not documented in this repository it is marked `# confirm in Step 0`, and the `--help` output
recorded in the run log is the authority for the run. If a documented layer is not merged yet (for example
hyvv provisioning, PR #4), the step is recorded **NOT RUN** with that reason — never silently skipped,
never folded into a pass.

## Prep self-check

The packet, this runbook and the cleanup path are pinned by `tests/test_m2_canary_prep.py`:

```
python3 -m pytest tests/test_m2_canary_prep.py -q
python3 -m unittest tests.test_m2_canary_prep -q   # same checks under unittest
```

The tests were written first and ran **red** (23 failures, both artifacts absent) before this runbook and
the packet existed; they must stay green whenever either artifact changes. They are structural — they parse
the packet, the step/evidence shape, the embedded contract JSON, the one-bee budget, the receiver-decision
pending rule and the cleanup guarantees. They do not run the canary and they change no production
configuration.

## Blast radius

| | |
|---|---|
| Created | the GitHub repository `mojomast/rizzstack-m2-canary` (private); its local scratch clone; one project registration on the worker host and one bundlebees project row, both named `rizzstack-m2-canary`; the run's evidence under `<clone>/evidence/2026-11-16-m2-canary/` |
| Modified | nothing outside `rizzstack-m2-canary`-named paths. Production repositories — mojomast/workflow, mojomast/bundlebees, mojomast/orbitdesktop, mojomast/hyvv — and every customer project in docs/07 are read-only for this run: preflight probes and the cleanup's untouched-checks only |
| Deleted | at cleanup only: the canary's host sandbox, the canary's registration row, the local scratch clone; the GitHub repository is archived, never deleted |

## Step 0 — Preflight (read-only; no writes anywhere)

**Command.**

```
git -C "$WORKFLOW" fetch origin
git -C "$WORKFLOW" rev-parse origin/main                 # record; must contain 9f6aa6dc... or a newer reviewed revision
bundlebees --version                                      # confirm the binary name for this run
bundlebees contract --help                                # confirm validate/freeze flags   # confirm in Step 0
bundlebees tdd --help                                     # confirm red/review/report flags # confirm in Step 0
bundlebees verify --help && bundlebees integrate --help   # confirm verify/integrate flags  # confirm in Step 0
bundlebees dispatch --help                                # confirm the brief input flags   # confirm in Step 0
bundlebees status                                         # live bee count from the worker host, not a local tally
gh pr view <F2-PR> --repo mojomast/bundlebees --json state,mergeCommit   # F2 really merged, not just approved
```

**Expected evidence.**

- F2's PR shows `state: MERGED` with a merge commit; the pinned bundlebees revision contains the
  `require_contract` gate (dispatch refuses a brief without a contract with `contract_missing`).
- The CLI verbs and flags above are recorded in the run log; every later step uses exactly these.
- Live bee count is 0; the pool cap (12, per docs/19) is not touched — this run needs exactly one bee.
- `mojomast/rizzstack-m2-canary` does not exist yet (`gh repo view mojomast/rizzstack-m2-canary` fails).
- Every production checkout probed reports a clean tree; the SHAs are recorded for the cleanup check.

## Step 1 — Authorization and repo creation (human gate)

**Command.** Ask first, then create. The approver's yes must cover creating the canary repository,
registering the canary project and running the runbook (packet `Authorization needs`). Record his words
verbatim with the time in the run log.

```
gh repo create mojomast/rizzstack-m2-canary --private --confirm    # confirm in Step 0
gh repo clone mojomast/rizzstack-m2-canary "$CANARY_SCRATCH"
```

**Expected evidence.**

- The approver's verbatim yes and its timestamp in the run log — before the repo exists.
- A private, empty `mojomast/rizzstack-m2-canary`; `$CANARY_SCRATCH` is a fresh clone of it.
- Nothing else was created: no production repository appears in any create/clone command.

## Step 2 — Seed the synthetic feature at the base revision (RED scaffolding)

The synthetic feature is a small event-tally ledger: real behavior, four approved tests, two source files —
bounded to one bee and no dependencies, and useful only inside the canary. The stubs raise
`NotImplementedError` naming the interface the contract declares (`change: add`), which docs/16 §5 defines
as the honest RED for "the function does not exist yet", so the approved tests fail for the right reason at
the base revision. The contract pins the closed set of known kinds (its assumptions); the stubs do not.

**Command.** Create exactly these files in `$CANARY_SCRATCH`.

`canary/__init__.py`:

```python
"""rizzstack-m2-canary synthetic feature package (throwaway; imported by nothing in production)."""
```

`canary/meter.py`:

```python
"""Tally canary events by kind (synthetic; contract M2-canary-wave-tally)."""


class UnknownEventKind(ValueError):
    """Raised when record_events sees a kind it does not know."""


def record_events(events):
    """Return {kind: count} for the event kinds, or raise UnknownEventKind."""
    raise NotImplementedError("canary.meter.record_events")
```

`canary/report.py`:

```python
"""Render a canary tally as sorted kind=count lines (synthetic)."""


def render_tally(tally):
    """Return newline-joined `kind=count` lines sorted by kind."""
    raise NotImplementedError("canary.report.render_tally")
```

`tests/__init__.py`: empty file.

`tests/test_meter.py` — the approved tests; committed before any implementation, never edited afterwards:

```python
"""Approved tests for contract M2-canary-wave-tally (read-only for the bee)."""

import unittest

from canary.meter import UnknownEventKind, record_events
from canary.report import render_tally


class MeterTests(unittest.TestCase):
    def test_record_events_counts_kinds(self):
        self.assertEqual(
            record_events(["dispatch", "verify", "dispatch"]),
            {"dispatch": 2, "verify": 1},
        )

    def test_record_events_rejects_unknown_kind(self):
        with self.assertRaises(UnknownEventKind):
            record_events(["dispatch", "mystery"])

    def test_empty_events_yield_empty_tally(self):
        self.assertEqual(record_events([]), {})


class ReportTests(unittest.TestCase):
    def test_render_tally_sorts_and_joins(self):
        self.assertEqual(render_tally({"verify": 1, "dispatch": 2}), "dispatch=2\nverify=1")
```

`README.md`:

```markdown
# rizzstack-m2-canary

Throwaway smoke project for the M2 contract-enforcement canary (docs/m2-canary-runbook.md in
mojomast/workflow). Not a product. Safe to archive and delete after the canary run.
```

Then commit and record the base:

```
git -C "$CANARY_SCRATCH" add README.md canary tests
git -C "$CANARY_SCRATCH" commit -m "Seed M2-canary synthetic feature: approved tests and stubs (RED scaffolding)"
git -C "$CANARY_SCRATCH" rev-parse HEAD        # record as BASE_SHA (full 40 hex)
python3 -m unittest discover -s tests -t .     # from $CANARY_SCRATCH: expect 4 failures/errors — the RED scaffold, observed manually; the verifier's RED record comes in Step 7
```

**Expected evidence.**

- `git rev-parse HEAD` prints a full 40-hex SHA — this is `BASE_SHA`, the contract's `source_rev`.
- The suite fails at this commit: all four approved tests error, because the stubs raise
  `NotImplementedError` naming the declared interface — including the `assertRaises(UnknownEventKind)`
  probe, which errors on the wrong exception rather than failing cleanly. This manual observation is
  context, not a verifier record.
- No file outside `canary/`, `tests/` and `README.md` was created.

## Step 3 — Freeze the contract

Write `contract/canary-wave-tally.json` in `$CANARY_SCRATCH` with exactly this content — it is the packet's
five criteria in `acdd/1` shape:

```json
{
  "contract_version": "acdd/1",
  "id": "M2-canary-wave-tally",
  "title": "Synthetic wave-tally ledger for the require-contract canary",
  "outcome": {
    "summary": "A caller can tally canary event kinds and render the tally as sorted kind=count lines.",
    "observable_behavior": [
      "record_events([\"dispatch\", \"verify\", \"dispatch\"]) returns {\"dispatch\": 2, \"verify\": 1}",
      "record_events([\"dispatch\", \"mystery\"]) raises UnknownEventKind and returns no tally",
      "record_events([]) returns {}",
      "render_tally({\"verify\": 1, \"dispatch\": 2}) returns \"dispatch=2\\nverify=1\""
    ]
  },
  "interfaces": [
    {
      "name": "canary.meter.record_events",
      "kind": "function",
      "change": "add",
      "notes": "record_events(events: Iterable[str]) -> dict[str, int]; sums occurrences per kind; the known kinds are the closed set dispatch, verify, report, integrate"
    },
    {
      "name": "canary.meter.UnknownEventKind",
      "kind": "class",
      "change": "add",
      "notes": "subclass of ValueError; the message names the offending kind"
    },
    {
      "name": "canary.report.render_tally",
      "kind": "function",
      "change": "add",
      "notes": "render_tally(tally: dict[str, int]) -> str; `kind=count` lines sorted by kind, joined by newline"
    }
  ],
  "acceptance_criteria": [
    {
      "id": "AC-001",
      "given": "the events [\"dispatch\", \"verify\", \"dispatch\"]",
      "when": "record_events is called",
      "then": "it returns {\"dispatch\": 2, \"verify\": 1}",
      "verification": "test",
      "tests": ["tests/test_meter.py::MeterTests::test_record_events_counts_kinds"]
    },
    {
      "id": "AC-002",
      "given": "the events [\"dispatch\", \"mystery\"]",
      "when": "record_events is called",
      "then": "it raises UnknownEventKind and returns no tally",
      "verification": "test",
      "tests": ["tests/test_meter.py::MeterTests::test_record_events_rejects_unknown_kind"]
    },
    {
      "id": "AC-003",
      "given": "no events",
      "when": "record_events is called",
      "then": "it returns {}",
      "verification": "test",
      "tests": ["tests/test_meter.py::MeterTests::test_empty_events_yield_empty_tally"]
    },
    {
      "id": "AC-004",
      "given": "the tally {\"verify\": 1, \"dispatch\": 2}",
      "when": "render_tally is called",
      "then": "it returns \"dispatch=2\\nverify=1\"",
      "verification": "test",
      "tests": ["tests/test_meter.py::ReportTests::test_render_tally_sorts_and_joins"]
    },
    {
      "id": "AC-005",
      "statement": "the combined branch passes the full canary suite",
      "verification": "integration"
    }
  ],
  "dependencies": [],
  "assumptions": [
    "the known event kinds are exactly dispatch, verify, report, integrate; every other kind is unknown and raises UnknownEventKind (AC-002)",
    "the canary repository is throwaway; nothing here is imported by production"
  ],
  "scope": {
    "assigned_files": ["canary/meter.py", "canary/report.py"],
    "test_files": ["tests/test_meter.py"],
    "read_only": ["canary/__init__.py", "README.md"],
    "prohibited": []
  },
  "source_rev": "<BASE_SHA — replaced with the 40-hex SHA recorded in Step 2 before validation; the validators refuse anything that is not 40 hex>",
  "tdd": {
    "applicable": true,
    "test_first": true
  },
  "verification": {
    "independent": true,
    "commands": ["python3 -m unittest discover -s tests -t ."],
    "integration": true
  },
  "evidence_required": ["red", "green", "integration", "review"],
  "authorization": {
    "human_gates": ["merge", "tag", "release", "deploy", "publish"],
    "authorized": [
      "one bee on mojomast/rizzstack-m2-canary per docs/m2-canary-runbook.md; 30 wall-clock minutes; no push, no merge, no retry"
    ],
    "not_authorized": [
      "any write to mojomast/workflow, mojomast/bundlebees, mojomast/orbitdesktop or mojomast/hyvv",
      "merge, tag, release, deploy or publish",
      "a second bee without a fresh yes from the approver"
    ]
  },
  "review": {
    "status": "draft"
  }
}
```

**Command.** Substitute the base revision (the only edit), validate, freeze:

```
python3 -c "import json,os,pathlib; p=pathlib.Path('contract/canary-wave-tally.json'); c=json.loads(p.read_text()); assert c['source_rev'].startswith('<BASE_SHA'); c['source_rev']=os.environ['BASE_SHA']; p.write_text(json.dumps(c, indent=2, ensure_ascii=False)+'\n')"
bundlebees contract validate contract/canary-wave-tally.json     # expect: valid (exit 0)   # confirm in Step 0
bundlebees contract freeze  contract/canary-wave-tally.json      # expect: a 64-hex contract_sha256 printed   # confirm in Step 0
PYTHONPATH="$WORKFLOW/tools/acdd-lint" python3 -m acdd_lint contract/canary-wave-tally.json    # expect: no problems; signatures reported as not checked without a key, never as passed
git -C "$CANARY_SCRATCH" add contract
git -C "$CANARY_SCRATCH" commit -m "Freeze contract M2-canary-wave-tally at the canary base revision"
```

**Expected evidence.**

- Validation and lint exit 0; the freeze prints `contract_sha256` (64 hex) — record it; the brief in Step 6
  carries exactly this id + hash pair.
- `review.status` is now `approved`, with `approved_by` naming the approver's canary authorization (his
  verbatim yes from Step 1 is the review authority for this synthetic contract) and `approved_at` set;
  the frozen hash is computed by the tooling, never typed by hand.
- The all-zeros or placeholder `source_rev` cannot survive validation — the substitute step is mandatory
  and the assert above refuses to run twice.

## Step 4 — Register the canary project (isolated; require_contract on)

Registration is what makes this a *project*, not just a repo — and it is the only place `require_contract`
is turned on. Register at every layer that exists on the merged revision, in this order; a layer that is
not merged yet is recorded **NOT RUN** with that reason (for example hyvv provisioning, PR #4, if it is
still unmerged when F2 lands) — never silently skipped.

**(a) Worker host — hyvv provisioning (docs/23 M3.5 P1).** Provision a project sandbox named
`rizzstack-m2-canary` with a bounded, isolated workspace; keep the read-only receipt.

```
curl -fsS -X POST "$HYVV_V1/provision/project" -H 'content-type: application/json' \
     --data-binary @provision/rizzstack-m2-canary.json        # credentials from the host's secret store; never printed   # confirm in Step 0
```

**(b) Orchestrator — bundlebees job store (docs/23 M3.5 P2).** Add the project row and bind jobs to it
(`provision_bind`); the row carries `require_contract: true` for this project only.

```
bundlebees project add rizzstack-m2-canary --repo mojomast/rizzstack-m2-canary --require-contract   # confirm in Step 0
```

**(c) The project's own durable state (docs/18).** Write the registration as a `workflow.project-state/v1`
file in the canary clone and commit it, then validate it with the reference checker.

```
mkdir -p "$CANARY_SCRATCH/.workflow"
cat > "$CANARY_SCRATCH/.workflow/project-state.json" <<'JSON'
{
  "schema": "workflow.project-state/v1",
  "schema_version": "v1",
  "project": "rizzstack-m2-canary",
  "state": "active",
  "at": "<RFC 3339 UTC at registration>",
  "by": "human:mojomast",
  "reason": "canary project registered per docs/m2-canary-runbook.md step 4",
  "generation": 1,
  "history": [
    {"state": "active", "at": "<RFC 3339 UTC at registration>", "by": "human:mojomast", "reason": "canary project registered per docs/m2-canary-runbook.md step 4"}
  ]
}
JSON
python3 "$WORKFLOW/tools/project-state/check.py" "$CANARY_SCRATCH"    # expect: dispatch allowed (exit 0)
git -C "$CANARY_SCRATCH" add .workflow
git -C "$CANARY_SCRATCH" commit -m "Register the canary project state (active, generation 1)"
```

**Expected evidence.**

- A provisioning receipt for `rizzstack-m2-canary` (or a NOT RUN entry naming the unmerged layer).
- A bundlebees project row whose state shows `require_contract: true` for this row — and a listing that
  shows every other project row unchanged (record it; the cleanup re-checks it).
- `tools/project-state/check.py` exits 0 on the canary clone.

## Step 5 — Negative probe: a contract-less brief must be refused

This is the step that "fires": F2's machinery must refuse to dispatch without a contract, before any bee
exists.

**Command.** Copy the Step 6 brief and delete its `CONTRACT` block (id, hash, file). Dispatch that brief:

```
bundlebees dispatch --brief briefs/m2-canary-no-contract.txt      # expect: refused   # confirm in Step 0
bundlebees status                                                  # live bee count — must still be 0
```

**Expected evidence.**

- The refusal names `contract_missing` (docs/16 §9) and happens **before** an attempt id is minted: no
  attempt, no job document, no bee started, the live bee count unchanged at 0.
- The refusal is saved as `evidence/2026-11-16-m2-canary/negative-probe.json` in the canary clone. It does
  not count against the one-bee budget — nothing was dispatched.
- **If the contract-less brief is accepted instead: STOP.** That is the canary's finding — the F2 gate did
  not fire. Record what was accepted, escalate to the approver immediately, run the cleanup, and do not
  proceed to Step 6. A canary that ends here has still done its job, with accurate evidence.

## Step 6 — Dispatch the one bee

**Command.** Dispatch exactly this brief (docs/19 template), with the frozen contract attached:

```text
GOAL
  Implement contract M2-canary-wave-tally on the canary project: a two-file event tally and
  its renderer, proven by four approved tests that already exist and fail at the base revision.

REPO / BRANCH
  repo: mojomast/rizzstack-m2-canary
  branch: canary/m2-wave-tally (new branch off main)
  source_rev: <BASE_SHA — the full 40-hex SHA recorded in Step 2>

CONTRACT (required — require_contract refuses this brief without it)
  contract_id: M2-canary-wave-tally
  contract_sha256: <the 64-hex digest printed by Step 3's freeze>
  contract file: contract/canary-wave-tally.json (frozen; read-only for the bee)

ASSIGNED FILES (lease)
  canary/meter.py, canary/report.py      # nothing else may change

CONSTRAINTS
  - tests/test_meter.py is the approved RED set: never edit, move, rename or delete it.
  - No merge, tag, release, publish, deploy, force-push, branch deletion or history rewrite.
  - Run the secret scan before every push. No push is authorized in this run.
  - Never print or commit secrets, private hosts or internal URLs.
  - Keep security checks fail-closed; never weaken a sandbox to make a test pass.
  - The stubs raise NotImplementedError naming the missing interface; replace the stubs,
    keep the declared signatures.

ACCEPTANCE (success criteria)
  AC-001 record_events(["dispatch", "verify", "dispatch"]) -> {"dispatch": 2, "verify": 1}
        proven by tests/test_meter.py::MeterTests::test_record_events_counts_kinds
  AC-002 record_events(["dispatch", "mystery"]) raises UnknownEventKind
        proven by tests/test_meter.py::MeterTests::test_record_events_rejects_unknown_kind
  AC-003 record_events([]) -> {}
        proven by tests/test_meter.py::MeterTests::test_empty_events_yield_empty_tally
  AC-004 render_tally({"verify": 1, "dispatch": 2}) -> "dispatch=2\nverify=1"
        proven by tests/test_meter.py::ReportTests::test_render_tally_sorts_and_joins
  The full suite passes on the final head.

REPORT FORMAT
  - branch, final head SHA (full)
  - for each AC id: test id, run or not run, result
  - commands actually run and their exit codes
  - anything not run, marked NOT RUN, with the reason
  - open risks and questions
```

```
bundlebees dispatch --brief briefs/m2-canary-wave-tally.txt       # confirm in Step 0
```

**Expected evidence.**

- One attempt id, one job document, a first event within the launcher's normal delay (docs/19 §3: blips
  have delayed events by 30 minutes — check the event file's age before judging "stuck").
- Budget: exactly one bee dispatch, 30 wall-clock minutes. There is **no automatic retry and no second
  dispatch**; a stuck bee is handled per docs/19 §3 (confirm, then cancel that one bee) and cancellation
  needs the approver's explicit yes naming the bee.
- The job document carries the contract id and hash; dispatch logged the `require_contract` check as passed.

## Step 7 — Record RED (verifier, not the bee)

**Command.** The verifier runs the approved tests at the base revision and records the RED:

```
bundlebees tdd red --job "$JOB" --contract contract/canary-wave-tally.json    # confirm in Step 0
```

**Expected evidence.**

- A signed `tdd-evidence/1` record with `phase: red`, saved as
  `evidence/2026-11-16-m2-canary/red.json`: `contract_sha256` equals Step 3's hash, `base_rev` equals
  `BASE_SHA`, `revision` equals `BASE_SHA` (allowed here because the approved tests already existed at the
  base — docs/16 §5), classification `behavioral_failure`, and **every** approved test failed (4/4).
- `test_fingerprints` captured — one entry per approved test. Step 8 must reproduce them exactly.

## Step 8 — Record GREEN (same tests, same fingerprints, lease intact)

**Command.** Verify the bee's implementation locally and record GREEN:

```
bundlebees verify --commit-local --job "$JOB"      # isolated worktree at the pinned base; local bb-verify/<attempt> commit; nothing pushed   # confirm in Step 0
git -C "$CANARY_SCRATCH" diff --name-only "$BASE_SHA"..bb-verify/"$ATTEMPT"    # the lease check, observed
```

**Expected evidence.**

- A signed GREEN record (`evidence/2026-11-16-m2-canary/green.json`): classification `passed`, the same
  command as the contract's `verification.commands`, `revision` descending from `BASE_SHA`, and
  `test_fingerprints` **identical** to the RED record's — no edited, deleted or substituted tests.
- The diff against `BASE_SHA` touches exactly `assigned_files` — `canary/meter.py` and
  `canary/report.py` — and nothing in `scope.test_files` or `read_only`. A patch that touches
  `tests/test_meter.py` is refused as `tests_tampered` / `scope_violation`; that refusal is a canary
  finding, recorded and escalated, not worked around.
- 4/4 approved tests pass at the implementation revision.

## Step 9 — Record REVIEW (named reviewer, never the worker or verifier)

**Command.**

```
bundlebees tdd review --reviewer "coordinator:MR.INDIA" --note "Reviewed the GREEN revision against AC-001..AC-004 and the lease; independent of the verifier run; not the approver's acceptance."   # confirm in Step 0
```

**Expected evidence.**

- A signed REVIEW record (`evidence/2026-11-16-m2-canary/review.json`) recorded **after** the valid GREEN,
  by a named reviewer with role `reviewer` — never role `worker` or `verifier` (docs/16 §5).
- The note says plainly that this is the coordinator's review, not Kyle's acceptance; the human decision is
  Step 12 and lives in the RETURN document, not in any evidence record.

## Step 10 — Integrate (full suite, in the sandbox)

**Command.**

```
bundlebees integrate --job "$JOB"      # combined branch, full suite inside the sandbox; refuses without a valid GREEN   # confirm in Step 0
```

**Expected evidence.**

- A signed integration record (`evidence/2026-11-16-m2-canary/integration.json`) with the integrated
  commit, the full suite exiting 0 (AC-005), and the accepted wave digest recorded in the run log.
- The integrated commit exists only on the canary repository's branch; nothing is pushed to, or merged
  into, any production repository.

## Step 11 — RETURN and manifest (receiver decision stays pending)

**Command.**

```
bundlebees job report "$JOB"       # writes the human RETURN (templates/RETURN.md) and the rizzstack.return/1 manifest   # confirm in Step 0
gitleaks detect --no-banner --redact       # from $CANARY_SCRATCH; expect exit 0
python3 "$WORKFLOW/tools/return_manifest.py" "$CANARY_SCRATCH/evidence/2026-11-16-m2-canary/return-manifest.json"    # expect: valid
PYTHONPATH="$WORKFLOW/tools/acdd-lint" python3 -m acdd_lint "$CANARY_SCRATCH/evidence/2026-11-16-m2-canary"    # expect: no problems
```

**Expected evidence.**

- The manifest carries: packet digest, contract id + hash, one acceptance entry per criterion with evidence
  paths (PASS rows always carry evidence — the validator refuses `PASS` with an empty array), the RED and
  GREEN references, the verification commit, the integration record, attempts, limitations, unrun steps
  with reasons, and pending approvals naming the merge.
- `receiver_decision` is exactly `{"status": "pending", "decided_by": null, "decided_at": null, "note": null}`
  — the validator refuses anything else (`receiver_decision_not_pending`); the manifest is never edited to
  record a decision.
- `evidence_digest` recomputes cleanly; gitleaks exits 0; acdd-lint reports the record chain clean.

## Step 12 — Receiver decision (human gate) and what the canary means

**Command.** Nothing executes here — the decision is the approver's, taken in his own channel, on this
checklist:

```
# No command runs in this step. Present, then wait for the approver's own words:
#   packet digest + contract id/hash:   M2-canary / M2-canary-wave-tally / <contract_sha256>
#   manifest and digest:                return-manifest.json / <evidence_digest>
#   negative probe:                     contract_missing refusal (Step 5) — or the finding that it did not happen
#   evidence chain:                     red.json -> green.json -> review.json -> integration.json
#   decision (his words, his channel):  accept / request changes / blocked, recorded in the RETURN document
```

Give the approver, in his own channel: the
packet, the contract hash, the manifest and its digest, the negative-probe refusal, the RED → GREEN →
REVIEW → integration chain, and the honest failures if any. He records **accept / request changes / blocked** in the RETURN document (templates/RETURN.md), in his own words; the manifest is never edited to
carry the decision. Only after his yes may the canary branch be merged into the canary repository's own
main — and nothing anywhere else, ever, on the strength of this run.

**Expected evidence.**

- The approver's verbatim decision and timestamp in the run log and in the RETURN document.
- The canary's verdict, recorded in the run log either way:
  - **Enforcement proven** — the negative probe was refused with `contract_missing`, and the full chain
    (RED-first acceptance, verifier-signed GREEN, review, integration, pending receiver decision) completed
    on the isolated project with zero production contact. That is the green light to plan flipping
    `require_contract` beyond the canary — a separate decision with its own yes.
  - **Enforcement gap found** — any refusal that did not happen, any gate that let a contract-less brief
    through, any signature or fingerprint mismatch: stop, record, escalate. Failure with accurate evidence
    is an acceptable outcome (docs/24); a success that needed undisclosed help is not.

## Failure handling

Every failure is classified with docs/16 §7's codes and recorded with its `failure_class`; nothing is
auto-retried:

| Failure | Code (examples) | What the canary does |
|---|---|---|
| Brief without a contract is accepted | absence of `contract_missing` | **The canary's finding.** Stop, record what was accepted, escalate to the approver, clean up |
| Contract invalid or unfrozen | `contract_invalid`, `contract_not_frozen`, `contract_changed` | Fix the contract *before* dispatch, re-freeze with a new hash; never edit a frozen contract |
| RED not valid | `red_invalid`, `unrelated_failure` | Record the classification and stop the run; the scaffolding, not the bee, is the suspect |
| Tests changed between RED and GREEN | `tests_tampered` | Stop; the lease was violated; record and escalate — never accept the patch |
| Patch outside the lease | `scope_violation` | Same as above; the refusal itself is evidence the enforcement works |
| Verification or integration failed | `verification_failed`, `integration_failed` | Record with accurate evidence; there is **no automatic retry** and no second bee without a fresh yes from the approver |
| Stuck bee | launcher event age vs. the 30-minute threshold | Confirm with the event file first (blips have delayed events 30 minutes), then cancel that one bee with the approver's yes naming it |
| A step could not run (layer unmerged, host unavailable) | — | Record **NOT RUN** with the reason in the RETURN's `unrun` list; never fold it into a pass |

A refusal that happens is a pass of that gate. A refusal that does not happen is the finding. Both are
reported as what they are — docs/19 §4: never invent metrics, never round a run up to a success.

## Rollback and cleanup

Run after Step 12 (or after any stop). It removes only canary-named state; production state is verified
untouched, never modified. Cancelling an in-flight bee is not part of this list — it needs the approver's
explicit yes naming the bee (docs/18: no implicit cancel).

**C1 — Retire the project state (docs/18).** The archived state requires a resume snapshot
(`snapshot_path`, by convention `PARKED.md`, per templates/PARKED.md). Write both in the canary clone,
commit, and validate — the reference checker must refuse new work for the archived project (exit 3):

```
python3 - <<'PY'
import datetime, json, pathlib
p = pathlib.Path(".workflow/project-state.json")
d = json.loads(p.read_text())
assert d["state"] == "active" and d["generation"] == len(d["history"]) == 1
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
reason = "canary run complete; project retired per docs/m2-canary-runbook.md cleanup"
d["state"], d["at"], d["by"], d["reason"] = "archived", now, "human:mojomast", reason
d["generation"] = 2
d["snapshot_path"] = "PARKED.md"
d["history"].append({"state": "archived", "at": now, "by": "human:mojomast", "reason": reason})
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
PY
```

Write `PARKED.md` at the root of the canary clone — every heading of templates/PARKED.md, placeholders
replaced, `none` with a reason where a section does not apply:

```markdown
# Parked project snapshot

## Identity

- Project id (`project` join key): rizzstack-m2-canary
- Display name: M2 contract-enforcement canary
- Primary repository (`owner/name`): mojomast/rizzstack-m2-canary
- State: archived
- Parked on (UTC, RFC 3339): <C1 TIME>
- Parked by (kind-prefixed id): human:mojomast
- Reason (already-scrubbed, in the human's own words when the human set it aside): canary run complete; project retired per the runbook cleanup the approver authorized

## Last SHAs

| Repository (`owner/name`) | Ref | Full SHA | Notes |
|---|---|---|---|
| mojomast/rizzstack-m2-canary | main | <INTEGRATED OR BASE SHA> | archived carrying the canary evidence under evidence/2026-11-16-m2-canary/ |

## Open pull requests

| Repository | PR number | Title | Head SHA | Base ref | State when parked |
|---|---|---|---|---|---|
| none | — | the canary pushed nothing; any canary-repo PR was the receiver's decision in Step 12 | — | — | — |

## Pending approvals

| Item | In the human's words | Status when parked |
|---|---|---|
| archive or delete the canary repository | <the approver's verbatim yes from Step 1 part (d)> | recorded in the run log |

## Queued cards

| Card id | Title | Previous column | Owner or assignee (kind-prefixed id) |
|---|---|---|---|
| none | — | the canary ran one feature, dispatched from this runbook, no board queue | — |

## In-flight bees and agents

| Bee or agent id | Card id | Branch | Status when parked | Disposition (finish-and-push / cancel-awaiting-yes / cancelled) |
|---|---|---|---|---|
| none | — | — | cleanup runs only after the bee reached a terminal state or drained | — |

## Paused routines and watchers

| Routine or watcher | Owner | Notes |
|---|---|---|
| none | — | the canary registered no routines |

## Next steps

- none: the project is archived after the run; nothing resumes without a fresh approver's yes.

## Drift notes (fill on unpark, not on park)

- none: the project is archived, not parked for later resume.
```

Then validate and commit:

```
python3 "$WORKFLOW/tools/project-state/check.py" "$CANARY_SCRATCH" --expect-generation 2    # expect: refused for new work (exit 3) — that is the archived state working
git -C "$CANARY_SCRATCH" add .workflow PARKED.md
git -C "$CANARY_SCRATCH" commit -m "Archive the canary project state (archived, generation 2)"
```

The archive transition is recorded `by: human:mojomast` — it happens on the approver's cleanup yes (Step 1
authorization part d), never as an agent's own decision.

**C2 — Tear down the canary project on the worker host.** Call the provisioning cleanup for project
`rizzstack-m2-canary` only, using the receipt from Step 4 (docs/23 M3.5 P1: cleanup is part of provision;
idempotent). Keep the receipt.

```
curl -fsS -X POST "$HYVV_V1/provision/project/rizzstack-m2-canary/cleanup"    # confirm in Step 0; Step 4's NOT RUN reason applies here too
```

**Expected evidence:** the canary sandbox gone; no other project's sandbox, lease or workspace listed as
touched.

**C3 — Remove the canary's registration row.** Delete exactly the bundlebees project row added in Step 4 —
nothing else in the job store:

```
bundlebees project remove rizzstack-m2-canary    # confirm in Step 0
bundlebees status                                 # live bee count 0; no canary jobs pending
```

**Expected evidence:** the row gone; the recorded Step 4 listing of all other project rows still matches.

**C4 — Archive the canary repository (human gate; never delete).** The archived repository is where the
evidence outlives the cleanup — the run's contract, RED/GREEN/REVIEW/integration records and the RETURN all
live in `<clone>/evidence/2026-11-16-m2-canary/`. Archive the repository — **never delete it** — after the
approver's yes:

```
gh repo archive mojomast/rizzstack-m2-canary --yes    # confirm in Step 0
```

**Expected evidence:** the repository archived, readable, with the evidence commit on its branch; no
`gh repo delete` exists in this runbook and none is authorized.

**C5 — Delete the local scratch.** Only after C4 (the archived repo keeps the evidence):

```
rm -rf "$CANARY_SCRATCH"
```

**Expected evidence:** the only deletion is the canary-named clone path.

**C6 — Verify production is untouched.** The check the whole runbook promised:

```
git -C "$WORKFLOW" status --porcelain && git -C "$WORKFLOW" rev-parse HEAD
git -C "$BUNDLEBEES" status --porcelain 2>/dev/null || true
git -C "$ORBITDESKTOP" status --porcelain 2>/dev/null || true
git -C "$HYVV" status --porcelain 2>/dev/null || true
bundlebees project list    # no rizzstack-m2-canary row; every production row as it was in Step 4's listing
```

**Expected evidence:** every production checkout reports a clean tree at the same SHA recorded in Step 0
(or its ordinary advance from other, separately authorized work — a difference from *this* run's actions is
the failure signal); the project listing matches Step 4's "everything else unchanged" record; the run log's
created-then-removed list closes out. Any drift is reported to the approver as a finding, not smoothed over.

**Rollback at any point.** Before Step 4: deleting the fresh clone and the (empty) registration removes
every trace. After dispatch: let the bee finish or drain; cancellation needs the approver's yes naming the
bee. After integration: nothing has merged anywhere, so rollback *is* the cleanup above — C1 through C6.
The runbook is additive-only by construction; there is no production state to restore.

## What this runbook must never do

- Create, modify, merge, deploy or delete anything outside `rizzstack-m2-canary`-named paths; production
  repositories are probed read-only, nothing more.
- Flip `require_contract` on for any project except the canary row.
- Dispatch a second bee, or retry a failed one, without a fresh yes from the approver.
- Edit a frozen contract, a signed evidence record, or a RETURN manifest's receiver decision.
- Print secrets, tokens or environment-file contents; credentials come from the host's secret store and
  are never echoed into the run log.
- Report an unrun step as run, or a refusal that never happened as if it had.
