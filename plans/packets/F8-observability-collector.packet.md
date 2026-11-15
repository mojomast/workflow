# F8 — Observability phase-2 snapshot collector (packet draft)

**Wave 3 · feature_id `wf-f8-observability-collector` · exact · mojomast/workflow**

Draft packet. Transcribe verbatim at admission; substitute `TODO(authorization)` values; freeze via `tools/feature_packet.py`.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "wf-f8-observability-collector",
  "job_id": "job_wave3_f8",
  "request": {
    "summary": "Observability Phase 2: a snapshot collector that pulls board, local-workers and agent-status into append-only JSONL records validated against the frozen observability schemas, with route and fallback recorded. No dashboard.",
    "provenance": "TODO(authorization): wave-3 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 3 F8; gap source: ROADMAP.md 'Phase 2 - Snapshot collector' and observability/README.md status banner"
  },
  "repository": {
    "identity": "mojomast/workflow",
    "branch": "feat/observability-collector"
  },
  "workflow_ref": "755d6c43124c13f35541dd0356a238561627f998",
  "source_policy": {
    "kind": "exact",
    "revision": "TODO(authorization): substitute the sealed 40-hex base revision"
  },
  "authorization": {
    "reference": "TODO(authorization): auth:job_wave3",
    "approved_by": "TODO(authorization): kyle (verbatim quote recorded in RULES.md)",
    "approved_at": "TODO(authorization): RFC3339 UTC at authorization"
  },
  "contract": {
    "contract_version": "acdd/1",
    "id": "OBS-COLLECT",
    "title": "Phase-2 observability snapshot collector",
    "outcome": {
      "summary": "Board, worker and agent snapshots land as schema-valid append-only JSONL; nothing is invented and unavailable stays unavailable.",
      "observable_behavior": [
        "The collector emits board.snapshot/v1, resource.snapshot/v1 and lifecycle-bearing records into an append-only JSONL file, each validated by observability/validate.py before the write",
        "Writes are append-only with no rewrite of earlier lines; a corrupt line is reported and never silently dropped or rewritten",
        "Unknown resource values are recorded with status unavailable and null value/remaining; a genuine zero requires status ok",
        "Sources are read via injected adapters (HTTP or command) so tests run offline with fakes; no credentials in argv, tokens from the environment only",
        "No dashboard, no alert delivery, no OTLP export: the collector only writes records"
      ]
    },
    "interfaces": [
      { "name": "observability/collector.py", "kind": "module", "change": "add" },
      { "name": "observability/collect_snapshots.py", "kind": "cli", "change": "add" },
      { "name": "observability/tests/test_collector.py", "kind": "file", "change": "add" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "One collector run against fake board/worker/agent sources appends schema-valid records for each source and exits 0.",
        "verification": "test",
        "tests": ["observability/tests/test_collector.py::CollectorTests::test_run_appends_valid_records"]
      },
      {
        "id": "AC-002",
        "statement": "A record that fails validation is not appended; the run records the validation failure and exits non-zero.",
        "verification": "test",
        "tests": ["observability/tests/test_collector.py::CollectorTests::test_invalid_record_not_appended"]
      },
      {
        "id": "AC-003",
        "statement": "Unavailable values are recorded as status unavailable with null value and remaining, never as zero.",
        "verification": "test",
        "tests": ["observability/tests/test_collector.py::CollectorTests::test_unavailable_not_zero"]
      },
      {
        "id": "AC-004",
        "statement": "The JSONL file is append-only across runs: a second run adds lines and never rewrites or reorders earlier ones.",
        "verification": "test",
        "tests": ["observability/tests/test_collector.py::CollectorTests::test_append_only_across_runs"]
      },
      {
        "id": "AC-005",
        "statement": "With no source adapters configured, the collector fails closed with a named error and writes nothing.",
        "verification": "test",
        "tests": ["observability/tests/test_collector.py::CollectorTests::test_unconfigured_fails_closed"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "observability/collector.py",
        "observability/collect_snapshots.py",
        "observability/tests/test_collector.py"
      ],
      "test_files": [
        "observability/tests/test_collector.py"
      ],
      "read_only": [
        "observability/schemas/",
        "observability/validate.py",
        "observability/envelope.py",
        "observability/README.md"
      ],
      "prohibited": ["observability/schemas/", ".github/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (collector does not exist)",
      "test_first": true
    },
    "verification": {
      "independent": true,
      "commands": ["python3 -m unittest discover -s observability/tests -v"],
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
  "acceptance_ids": ["AC-001", "AC-002", "AC-003", "AC-004", "AC-005"],
  "tests": [
    "observability/tests/test_collector.py::CollectorTests::test_run_appends_valid_records",
    "observability/tests/test_collector.py::CollectorTests::test_invalid_record_not_appended",
    "observability/tests/test_collector.py::CollectorTests::test_unavailable_not_zero",
    "observability/tests/test_collector.py::CollectorTests::test_append_only_across_runs",
    "observability/tests/test_collector.py::CollectorTests::test_unconfigured_fails_closed"
  ],
  "scope": {
    "lease": [
      "observability/collector.py",
      "observability/collect_snapshots.py",
      "observability/tests/test_collector.py"
    ],
    "read_only": [
      "observability/schemas/",
      "observability/validate.py",
      "observability/envelope.py"
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

- The frozen schemas are read-only for a reason: if a collector discovers the schema cannot express a real value, it records `unavailable` and files the gap in the RETURN's `limitations` — it does not edit the schema in this lease ([observability/README.md](../../observability/README.md) privacy and stability rules).
- Adapters mirror `poll.py`'s injection pattern (HTTP base URL or command split with shlex, no shell).
