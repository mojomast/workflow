# F9 — Observability phase-3 failure-class consumption (packet draft)

**Wave 3 · feature_id `wf-f9-failure-class-consumption` · DESCENDANT · mojomast/workflow · depends on `bb-f6-regression-attribution`**

This is the pack's first **descendant** packet: its revision cannot be named at intake because it consumes F6's attribution work, which does not exist yet. It carries an unfrozen `contract_template` at the authorized root; the source-bound frozen contract is created by the `rizzstack.source-resolution/1` record after F6's accepted commit exists ([docs/25](../../docs/25-feature-packet.md)). Transcribe verbatim at admission; substitute `TODO(authorization)` values.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "wf-f9-failure-class-consumption",
  "job_id": "job_wave3_f9",
  "request": {
    "summary": "Observability Phase 3: consume the authorized bundlebees failure-class and attribution evidence into classified failure/v1 records with clean denominators - environmental failures separated from real regressions, unavailable separated from zero, no fork of the bundlebees metrics fix.",
    "provenance": "TODO(authorization): wave-3 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 3 F9; gap source: ROADMAP.md 'Phase 3 - Failure class and clean denominators'"
  },
  "repository": {
    "identity": "mojomast/workflow",
    "branch": "feat/observability-failure-class"
  },
  "workflow_ref": "755d6c43124c13f35541dd0356a238561627f998",
  "source_policy": {
    "kind": "descendant",
    "root_revision": "TODO(authorization): substitute the sealed 40-hex root revision",
    "dependencies": ["bb-f6-regression-attribution"],
    "policy_id": "TODO(authorization): enrolled descendant policy id"
  },
  "authorization": {
    "reference": "TODO(authorization): auth:job_wave3",
    "approved_by": "TODO(authorization): kyle (verbatim quote recorded in RULES.md)",
    "approved_at": "TODO(authorization): RFC3339 UTC at authorization"
  },
  "contract_template": {
    "contract_version": "acdd/1",
    "id": "OBS-FAILCLASS",
    "title": "Phase-3 failure-class consumption with clean denominators",
    "outcome": {
      "summary": "Bundlebees metrics and attribution evidence become classified failure/v1 records whose denominators are explicit and whose unavailable values stay unavailable.",
      "observable_behavior": [
        "A converter reads bundlebees metrics JSONL (and the attribution block where present) and emits failure/v1 records with the classified class per the frozen schema",
        "Environmental failures (sandbox unavailable, launcher blip, timeout) are class environmental; regressions introduced by an attempt are class regression with the attributed attempt id",
        "Every emitted record carries explicit denominators (attempted, verified, accepted) and never divides by an implicit count",
        "Values the runtime does not report are null with usage_status unknown or partial, never zero",
        "The converter is a consumer: it imports nothing from bundlebees and defines no second metrics schema"
      ]
    },
    "interfaces": [
      { "name": "observability/failure_class.py", "kind": "module", "change": "add" },
      { "name": "observability/tests/test_failure_class.py", "kind": "file", "change": "add" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "A metrics JSONL containing one environmental failure and one regression produces two failure/v1 records with the correct classes.",
        "verification": "test",
        "tests": ["observability/tests/test_failure_class.py::FailureClassTests::test_classes_emitted"]
      },
      {
        "id": "AC-002",
        "statement": "An attribution block naming an attempt maps to a regression record carrying that attempt id; a failure without attribution maps to class unknown, never to regression.",
        "verification": "test",
        "tests": ["observability/tests/test_failure_class.py::FailureClassTests::test_attribution_mapping"]
      },
      {
        "id": "AC-003",
        "statement": "Denominators are explicit fields on every emitted summary; a zero denominator is refused rather than producing a rate.",
        "verification": "test",
        "tests": ["observability/tests/test_failure_class.py::FailureClassTests::test_explicit_denominators"]
      },
      {
        "id": "AC-004",
        "statement": "Missing numeric values are null with usage_status unknown or partial, never zero.",
        "verification": "test",
        "tests": ["observability/tests/test_failure_class.py::FailureClassTests::test_unavailable_never_zero"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "observability/failure_class.py",
        "observability/tests/test_failure_class.py"
      ],
      "test_files": [
        "observability/tests/test_failure_class.py"
      ],
      "read_only": [
        "observability/schemas/failure.schema.json",
        "observability/schemas/common.schema.json",
        "observability/validate.py",
        "observability/README.md"
      ],
      "prohibited": ["observability/schemas/", ".github/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex root revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (converter does not exist)",
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
  "acceptance_ids": ["AC-001", "AC-002", "AC-003", "AC-004"],
  "tests": [
    "observability/tests/test_failure_class.py::FailureClassTests::test_classes_emitted",
    "observability/tests/test_failure_class.py::FailureClassTests::test_attribution_mapping",
    "observability/tests/test_failure_class.py::FailureClassTests::test_explicit_denominators",
    "observability/tests/test_failure_class.py::FailureClassTests::test_unavailable_never_zero"
  ],
  "scope": {
    "lease": [
      "observability/failure_class.py",
      "observability/tests/test_failure_class.py"
    ],
    "read_only": [
      "observability/schemas/failure.schema.json",
      "observability/schemas/common.schema.json",
      "observability/validate.py"
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

- **Admission order matters:** F9 cannot be admitted until `bb-f6-regression-attribution` has an accepted commit — the queue resolves it via the source-resolution record. Do not force-admit.
- The template's `source_rev` is the authorized **root**; the frozen contract's `source_rev` will be F6's accepted integration commit. Only those two fields plus the review block may differ between template and derived contract ([docs/25](../../docs/25-feature-packet.md)) — everything else must be byte-equal.
- The attribution block's field names come from F6's merged wave record; the executor reads them from F6's RETURN before freezing, and records any naming mismatch as a `specification` recovery request rather than editing either side silently.
