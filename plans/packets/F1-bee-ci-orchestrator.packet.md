# F1 — bee-ci phase-2 orchestrator (packet draft)

**Wave 1 · feature_id `wf-f1-bee-ci-orchestrator` · exact · mojomast/workflow**

Draft packet. The JSON below is the packet body; the executor transcribes it verbatim to `plans/packets/F1-bee-ci-orchestrator.json` at admission, substitutes the `TODO(authorization)` values from the sealed wave-1 authorization, computes `contract_sha256` with `tools/feature_packet.py` after review approval, and validates. A draft contract cannot be cited as frozen evidence ([docs/16 §2](../../docs/16-acdd-tdd.md)).

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "wf-f1-bee-ci-orchestrator",
  "job_id": "job_wave1_f1",
  "request": {
    "summary": "bee-ci phase-2 orchestrator: one command runs poll -> dispatch -> runner -> verify -> compare -> evidence -> report, preserving every phase-1 fail-closed gate (verified-result-only success, no GitHub writes without an injected transport, skipped-is-not-passed).",
    "provenance": "TODO(authorization): wave-1 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 1 F1; gap source: contrib/bee-ci/README.md 'Known gaps (phase 1)'"
  },
  "repository": {
    "identity": "mojomast/workflow",
    "branch": "feat/bee-ci-orchestrator"
  },
  "workflow_ref": "755d6c43124c13f35541dd0356a238561627f998",
  "source_policy": {
    "kind": "exact",
    "revision": "TODO(authorization): substitute the sealed 40-hex base revision"
  },
  "authorization": {
    "reference": "TODO(authorization): auth:job_wave1",
    "approved_by": "TODO(authorization): kyle (verbatim quote recorded in RULES.md)",
    "approved_at": "TODO(authorization): RFC3339 UTC at authorization"
  },
  "contract": {
    "contract_version": "acdd/1",
    "id": "BEECI-ORCH",
    "title": "Single-command bee-ci shadow orchestrator",
    "outcome": {
      "summary": "One CLI command executes the full phase-1 shadow pipeline in order and stops fail-closed at the first non-verified stage.",
      "observable_behavior": [
        "Running the orchestrator executes poll, dispatch, runner, verify, compare, evidence append and report render in that order for one configured repo/head",
        "The orchestrator exits non-zero and writes no evidence row when verify_result returns anything but success",
        "The orchestrator performs no GitHub write in any code path; status posting remains a separate dry-run-only step",
        "Each stage's existing CLI/module contract is reused, not reimplemented; the orchestrator only sequences and passes files"
      ]
    },
    "interfaces": [
      { "name": "contrib/bee-ci/orchestrator.py", "kind": "module", "change": "add" },
      { "name": "contrib/bee-ci/run_orchestrated.py", "kind": "cli", "change": "add" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "The orchestrator runs all seven stages in order against the reference leg and produces a rendered report and an evidence index containing exactly one bee row and one github row for the same head.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_full_pipeline_order_and_outputs"]
      },
      {
        "id": "AC-002",
        "statement": "When verify_result returns failure or error, the orchestrator stops, exits non-zero, appends no evidence row, and the failure reason is carried to the run log.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_unverified_result_stops_pipeline"]
      },
      {
        "id": "AC-003",
        "statement": "No orchestrator code path posts to GitHub: the module imports no transport and a test asserts the absence of a live-posting branch.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_no_github_write_path"]
      },
      {
        "id": "AC-004",
        "statement": "A dispatch-stage error (missing token, launcher unavailable) leaves items queued and exits non-zero without running later stages.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_dispatch_error_stops_pipeline"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "contrib/bee-ci/orchestrator.py",
        "contrib/bee-ci/run_orchestrated.py",
        "contrib/bee-ci/tests/test_orchestrator.py"
      ],
      "test_files": [
        "contrib/bee-ci/tests/test_orchestrator.py"
      ],
      "read_only": [
        "contrib/bee-ci/poll.py",
        "contrib/bee-ci/dispatch.py",
        "contrib/bee-ci/verify_result.py",
        "contrib/bee-ci/compare.py",
        "contrib/bee-ci/evidence.py",
        "contrib/bee-ci/report/render.py",
        "contrib/bee-ci/README.md"
      ],
      "prohibited": ["contrib/bee-ci/post_status.py"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (module does not exist yet)",
      "test_first": true
    },
    "verification": {
      "independent": true,
      "commands": ["python3 -m pytest contrib/bee-ci/tests -q"],
      "integration": true
    },
    "evidence_required": ["red", "green", "integration"],
    "authorization": {
      "human_gates": ["merge", "release", "deploy", "publish"],
      "authorized": ["push feature branch via coordinator only", "open PR after integration"],
      "not_authorized": ["merge", "tag", "release", "deploy", "publish", "catalog changes"]
    }
  },
  "contract_sha256": "TODO(freeze): computed by tools/feature_packet.py at admission after review approval",
  "acceptance_ids": ["AC-001", "AC-002", "AC-003", "AC-004"],
  "tests": [
    "contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_full_pipeline_order_and_outputs",
    "contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_unverified_result_stops_pipeline",
    "contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_no_github_write_path",
    "contrib/bee-ci/tests/test_orchestrator.py::OrchestratorTests::test_dispatch_error_stops_pipeline"
  ],
  "scope": {
    "lease": [
      "contrib/bee-ci/orchestrator.py",
      "contrib/bee-ci/run_orchestrated.py",
      "contrib/bee-ci/tests/test_orchestrator.py"
    ],
    "read_only": [
      "contrib/bee-ci/poll.py",
      "contrib/bee-ci/dispatch.py",
      "contrib/bee-ci/verify_result.py",
      "contrib/bee-ci/compare.py",
      "contrib/bee-ci/evidence.py",
      "contrib/bee-ci/report/render.py"
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

- The lease deliberately excludes `post_status.py` (prohibited in contract scope): the orchestrator must not grow a live-posting path.
- AC-003's "no live-posting branch" test is a structural assertion (e.g. no `post_status` import, no transport parameter in the orchestrator's public API).
- The `github` evidence row comes from F2's collector; until F2 lands, the orchestrator accepts an operator-supplied Actions JSON exactly as the phase-1 walkthrough does — AC-001 must pass in that mode.
