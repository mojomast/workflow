# F2 — bee-ci Actions collector + result adapters (packet draft)

**Wave 1 · feature_id `wf-f2-bee-ci-collector` · exact · mojomast/workflow**

Draft packet. Transcribe the JSON below verbatim at admission; substitute `TODO(authorization)` values from the sealed authorization; freeze via `tools/feature_packet.py`.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "wf-f2-bee-ci-collector",
  "job_id": "job_wave1_f2",
  "request": {
    "summary": "bee-ci phase-2 collectors: a GitHub Actions conclusions collector for an exact head SHA, a runner-result-to-evidence adapter, and a runner-result-to-compare adapter, closing the three operator-supplied gaps in the phase-1 shadow harness.",
    "provenance": "TODO(authorization): wave-1 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 1 F2; gap source: contrib/bee-ci/README.md 'Known gaps (phase 1)'"
  },
  "repository": {
    "identity": "mojomast/workflow",
    "branch": "feat/bee-ci-collectors"
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
    "id": "BEECI-COLLECT",
    "title": "Actions conclusions collector and result adapters for bee-ci",
    "outcome": {
      "summary": "The shadow harness can assemble its Actions side and its evidence/compare rows from real artifacts instead of operator hand-built JSON, with exact-SHA matching and no pass inflation.",
      "observable_behavior": [
        "The collector queries GitHub Actions check runs for one exact head SHA and emits the phase-1 actions.json record shape",
        "The collector never expands a shortened SHA and never treats queued, pending, skipped, neutral or unstable as success",
        "The runner-result-to-evidence adapter converts a verified signed result into exactly the nine frozen evidence fields, refusing unverified input",
        "The runner-result-to-compare adapter emits the phase-1 bee.json record shape from a verified signed result only"
      ]
    },
    "interfaces": [
      { "name": "contrib/bee-ci/actions_collect.py", "kind": "module", "change": "add" },
      { "name": "contrib/bee-ci/adapters.py", "kind": "module", "change": "add" },
      { "name": "contrib/bee-ci/collect_actions.py", "kind": "cli", "change": "add" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "Given a head SHA with check runs, the collector emits records whose sha equals the full input SHA and whose conclusion values are passed through verbatim from the API.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_actions_collect.py::ActionsCollectTests::test_collect_exact_sha_records"]
      },
      {
        "id": "AC-002",
        "statement": "The collector refuses a SHA shorter than 40 hex and emits no record for queued, pending, skipped, neutral or unstable conclusions other than their verbatim classification by compare.py.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_actions_collect.py::ActionsCollectTests::test_refuses_short_sha"]
      },
      {
        "id": "AC-003",
        "statement": "The evidence adapter refuses a result that has not passed verify_result, and produces a nine-field record with first-write-wins semantics preserved when input is verified.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_adapters.py::AdapterTests::test_evidence_adapter_requires_verified_result"]
      },
      {
        "id": "AC-004",
        "statement": "The compare adapter output fed to compare.py never classifies an unverified bee record as passed.",
        "verification": "test",
        "tests": ["contrib/bee-ci/tests/test_adapters.py::AdapterTests::test_compare_adapter_rejects_unverified"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "contrib/bee-ci/actions_collect.py",
        "contrib/bee-ci/adapters.py",
        "contrib/bee-ci/collect_actions.py",
        "contrib/bee-ci/tests/test_actions_collect.py",
        "contrib/bee-ci/tests/test_adapters.py"
      ],
      "test_files": [
        "contrib/bee-ci/tests/test_actions_collect.py",
        "contrib/bee-ci/tests/test_adapters.py"
      ],
      "read_only": [
        "contrib/bee-ci/verify_result.py",
        "contrib/bee-ci/evidence.py",
        "contrib/bee-ci/compare.py",
        "contrib/bee-ci/README.md"
      ],
      "prohibited": [".github/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (modules do not exist yet)",
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
    "contrib/bee-ci/tests/test_actions_collect.py::ActionsCollectTests::test_collect_exact_sha_records",
    "contrib/bee-ci/tests/test_actions_collect.py::ActionsCollectTests::test_refuses_short_sha",
    "contrib/bee-ci/tests/test_adapters.py::AdapterTests::test_evidence_adapter_requires_verified_result",
    "contrib/bee-ci/tests/test_adapters.py::AdapterTests::test_compare_adapter_rejects_unverified"
  ],
  "scope": {
    "lease": [
      "contrib/bee-ci/actions_collect.py",
      "contrib/bee-ci/adapters.py",
      "contrib/bee-ci/collect_actions.py",
      "contrib/bee-ci/tests/test_actions_collect.py",
      "contrib/bee-ci/tests/test_adapters.py"
    ],
    "read_only": [
      "contrib/bee-ci/verify_result.py",
      "contrib/bee-ci/evidence.py",
      "contrib/bee-ci/compare.py"
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

- GitHub reads are read-only API calls with a token from the environment only; the collector must fail closed without a token, never print it, and scrub it from errors (same discipline as `dispatch.py`).
- The collector is deliberately a separate module from `orchestrator.py` (F1) so the two leases stay disjoint; F1's orchestrator may call it after both merge.
- Disjoint-lease check vs F1: F2 owns `actions_collect.py`, `adapters.py`, `collect_actions.py` + their tests; F1 owns `orchestrator.py`, `run_orchestrated.py` + its test. No overlap.
