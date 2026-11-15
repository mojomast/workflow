# F6 — Causal regression attribution (packet draft)

**Wave 2 · feature_id `bb-f6-regression-attribution` · exact · mojomast/bundlebees**

Draft packet. Transcribe verbatim at admission; substitute `TODO(authorization)` values; freeze via packet validation.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "bb-f6-regression-attribution",
  "job_id": "job_wave2_f6",
  "request": {
    "summary": "When a combined integration suite fails, name the offending attempt(s): bisect the accepted commits in the wave, attribute the failing test(s) to the attempt whose patch introduces them, and record the attribution in the wave record instead of reporting only a failing suite.",
    "provenance": "TODO(authorization): wave-2 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 2 F6; gap source: docs/21-autonomy-gap-analysis.md transition 10 'Detection is mechanical, not causal'"
  },
  "repository": {
    "identity": "mojomast/bundlebees",
    "branch": "feat/regression-attribution"
  },
  "workflow_ref": "755d6c43124c13f35541dd0356a238561627f998",
  "source_policy": {
    "kind": "exact",
    "revision": "TODO(authorization): substitute the sealed 40-hex base revision"
  },
  "authorization": {
    "reference": "TODO(authorization): auth:job_wave2",
    "approved_by": "TODO(authorization): kyle (verbatim quote recorded in RULES.md)",
    "approved_at": "TODO(authorization): RFC3339 UTC at authorization"
  },
  "contract": {
    "contract_version": "acdd/1",
    "id": "INTEG-ATTR",
    "title": "Causal regression attribution for integration failures",
    "outcome": {
      "summary": "An integration failure produces a named suspect list with evidence, so recovery decisions classify `integration` failures against real attributions instead of a bare exit code.",
      "observable_behavior": [
        "On a failing combined suite, integrate runs a bisection over the wave's verified commits (in integration order) and records, per failing test, the earliest commit whose inclusion makes it fail",
        "The wave record gains an attribution block: failing test id, attributed attempt id(s), and the per-step suite evidence; a test failing at the base is attributed to baseline, not to an attempt",
        "Attribution is evidence, not a verdict: the wave still refuses with integration_conflict/integration_failed and the recovery request cites the attribution block",
        "Bisection runs inside the existing sandbox rules; no network, no coordinator credentials in the worktree"
      ]
    },
    "interfaces": [
      { "name": "bundlebees_plugin/integrate_job.py", "kind": "module", "change": "modify" },
      { "name": "bundlebees_plugin/attribution.py", "kind": "module", "change": "add" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "Given a wave of two accepted commits where the second breaks a test, the attribution block names the second attempt and the failing test id.",
        "verification": "test",
        "tests": ["tests/test_attribution.py::AttributionTests::test_single_offender_named"]
      },
      {
        "id": "AC-002",
        "statement": "Given two commits that each independently break different tests, each failing test is attributed to its own introducing commit.",
        "verification": "test",
        "tests": ["tests/test_attribution.py::AttributionTests::test_independent_offenders_split"]
      },
      {
        "id": "AC-003",
        "statement": "A test failing at the base revision is recorded as baseline-attributed and does not name any attempt.",
        "verification": "test",
        "tests": ["tests/test_attribution.py::AttributionTests::test_baseline_failure_not_attributed"]
      },
      {
        "id": "AC-004",
        "statement": "A passing integration produces no attribution block beyond an empty one, and the wave record shape is otherwise unchanged.",
        "verification": "test",
        "tests": ["tests/test_attribution.py::AttributionTests::test_passing_wave_shape_unchanged"]
      },
      {
        "id": "AC-005",
        "statement": "Attribution never changes the accept/reject decision: a wave with attribution still refuses exactly as it would without it.",
        "verification": "test",
        "tests": ["tests/test_attribution.py::AttributionTests::test_decision_unchanged_by_attribution"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "bundlebees_plugin/integrate_job.py",
        "bundlebees_plugin/attribution.py",
        "tests/test_attribution.py"
      ],
      "test_files": [
        "tests/test_attribution.py"
      ],
      "read_only": [
        "bundlebees_plugin/reconcile.py",
        "bundlebees_plugin/verify_local.py"
      ],
      "prohibited": [".github/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (attribution does not exist)",
      "test_first": true
    },
    "verification": {
      "independent": true,
      "commands": ["python -m pytest tests/test_attribution.py -q"],
      "integration": true
    },
    "evidence_required": ["red", "green", "integration"],
    "authorization": {
      "human_gates": ["merge", "release", "deploy", "publish"],
      "authorized": ["push feature branch via coordinator only", "open PR after integration"],
      "not_authorized": ["merge", "tag", "release", "deploy", "publish", "host changes"]
    }
  },
  "contract_sha256": "TODO(freeze): computed at admission after review approval",
  "acceptance_ids": ["AC-001", "AC-002", "AC-003", "AC-004", "AC-005"],
  "tests": [
    "tests/test_attribution.py::AttributionTests::test_single_offender_named",
    "tests/test_attribution.py::AttributionTests::test_independent_offenders_split",
    "tests/test_attribution.py::AttributionTests::test_baseline_failure_not_attributed",
    "tests/test_attribution.py::AttributionTests::test_passing_wave_shape_unchanged",
    "tests/test_attribution.py::AttributionTests::test_decision_unchanged_by_attribution"
  ],
  "scope": {
    "lease": [
      "bundlebees_plugin/integrate_job.py",
      "bundlebees_plugin/attribution.py",
      "tests/test_attribution.py"
    ],
    "read_only": [
      "bundlebees_plugin/reconcile.py",
      "bundlebees_plugin/verify_local.py"
    ]
  },
  "budget": { "bees": 2, "wall_clock_s": 5400 },
  "required_evidence": ["red", "green", "regression", "gitleaks", "integration"],
  "prohibited": [
    "push to origin",
    "merge",
    "tag",
    "release",
    "deploy",
    "publish",
    "edit approved tests",
    "force-push",
    "branch deletion",
    "history rewrite",
    "printing secrets, tokens, private hosts or internal URLs"
  ],
  "human_gates": ["merge", "release", "deploy", "publish"],
  "handoff_ref": "plans/packets/README.md",
  "return_ref": "templates/RETURN.md"
}
```

## Executor notes

- Bisection cost is bounded: attribute only when the combined suite fails, cap bisection steps at the wave's commit count, and record `attribution: not-run` with a reason when the wave aborts before bisection (fail-closed honesty, not a silent skip).
- `recovery.py` consumes the attribution block as structured evidence for `integration`-class requests; that wiring is F9's descendant dependency, not this lease.
