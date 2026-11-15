# F7 — Campaign report head binding + partial merge order (packet draft)

**Wave 2 · feature_id `wf-f7-report-head-binding` · exact · mojomast/workflow**

Draft packet. Transcribe verbatim at admission; substitute `TODO(authorization)` values; freeze via `tools/feature_packet.py`.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "wf-f7-report-head-binding",
  "job_id": "job_wave2_f7",
  "request": {
    "summary": "Close the two recorded campaign-report limitations: bind artifacts.performance rows to a head revision (head_sha per row), and allow recommended_merge_order to name a ready subset with an explicit field for the not-yet-ready remainder.",
    "provenance": "TODO(authorization): wave-2 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 2 F7; gap source: docs/30-campaign-closeout.md section 6.2 'Not implemented here'"
  },
  "repository": {
    "identity": "mojomast/workflow",
    "branch": "feat/report-head-binding"
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
    "id": "REPORT-BIND",
    "title": "Campaign report: performance head binding and subset merge order",
    "outcome": {
      "summary": "A campaign report cannot cite a performance number from an older commit, and can recommend merging a ready subset while naming the remainder.",
      "observable_behavior": [
        "artifacts.performance rows gain a required head_sha field; the validator refuses a performance row whose head_sha is not the final head_rev (stale performance is a refusal, like stale test runs)",
        "recommended_merge_order may be a subset of open PRs when the report sets ready_subset: true and lists the remaining open PRs in deferred_merge_order; the exact-sequence rule applies within each list",
        "The default (no ready_subset field) keeps today's behaviour: the order must name every open PR",
        "The schema and the validator carry the same rules; the existing example and tests keep passing"
      ]
    },
    "interfaces": [
      { "name": "schemas/campaign-report.schema.json", "kind": "schema", "change": "modify" },
      { "name": "tools/campaign_report.py", "kind": "module", "change": "modify" },
      { "name": "schemas/examples/campaign-report.example.json", "kind": "file", "change": "modify" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "A performance row without head_sha, or with a head_sha other than the final head_rev, is refused with a named code.",
        "verification": "test",
        "tests": ["tests/test_campaign_report.py::ReportHeadBindingTests::test_performance_row_requires_current_head"]
      },
      {
        "id": "AC-002",
        "statement": "A report with ready_subset true, a valid ordered subset, and a deferred list covering exactly the remaining open PRs validates.",
        "verification": "test",
        "tests": ["tests/test_campaign_report.py::ReportHeadBindingTests::test_subset_merge_order_valid"]
      },
      {
        "id": "AC-003",
        "statement": "A ready_subset report whose two lists do not exactly partition the open PRs is refused.",
        "verification": "test",
        "tests": ["tests/test_campaign_report.py::ReportHeadBindingTests::test_subset_must_partition_open_prs"]
      },
      {
        "id": "AC-004",
        "statement": "Without ready_subset, the existing every-open-PR rule and its refusal codes are unchanged.",
        "verification": "test",
        "tests": ["tests/test_campaign_report.py::ReportHeadBindingTests::test_default_rule_unchanged"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "schemas/campaign-report.schema.json",
        "tools/campaign_report.py",
        "schemas/examples/campaign-report.example.json",
        "tests/test_campaign_report.py"
      ],
      "test_files": [
        "tests/test_campaign_report.py"
      ],
      "read_only": [
        "docs/30-campaign-closeout.md",
        "templates/CAMPAIGN-REPORT.md"
      ],
      "prohibited": ["docs/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (head_sha not required today)",
      "test_first": true
    },
    "verification": {
      "independent": true,
      "commands": ["python3 -m unittest tests.test_campaign_report -v"],
      "integration": true
    },
    "evidence_required": ["red", "green", "integration"],
    "authorization": {
      "human_gates": ["merge", "release", "deploy", "publish"],
      "authorized": ["push feature branch via coordinator only", "open PR after integration"],
      "not_authorized": ["merge", "tag", "release", "deploy", "publish", "catalog changes"]
    }
  },
  "contract_sha256": "TODO(freeze): computed at admission after review approval",
  "acceptance_ids": ["AC-001", "AC-002", "AC-003", "AC-004"],
  "tests": [
    "tests/test_campaign_report.py::ReportHeadBindingTests::test_performance_row_requires_current_head",
    "tests/test_campaign_report.py::ReportHeadBindingTests::test_subset_merge_order_valid",
    "tests/test_campaign_report.py::ReportHeadBindingTests::test_subset_must_partition_open_prs",
    "tests/test_campaign_report.py::ReportHeadBindingTests::test_default_rule_unchanged"
  ],
  "scope": {
    "lease": [
      "schemas/campaign-report.schema.json",
      "tools/campaign_report.py",
      "schemas/examples/campaign-report.example.json",
      "tests/test_campaign_report.py"
    ],
    "read_only": [
      "docs/30-campaign-closeout.md",
      "templates/CAMPAIGN-REPORT.md"
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

- The `manual` acceptance criterion stays un-revision-bound ([docs/30 §6.2](../../docs/30-campaign-closeout.md)); only `performance` gains the binding here — `test`, `integration`, `visual`, `asset` already bind to head.
- Schema change is additive (new required field + new optional fields). If the schema bump forces example repinning, follow the [docs/25](../../docs/25-feature-packet.md) pin discipline and record the bump commit in the RETURN.
