# F10 — Observability phase-4 resource snapshots + alert delivery (packet draft)

**Wave 3 · feature_id `wf-f10-alert-delivery` · exact · mojomast/workflow**

Draft packet. Transcribe verbatim at admission; substitute `TODO(authorization)` values; freeze via `tools/feature_packet.py`.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "wf-f10-alert-delivery",
  "job_id": "job_wave3_f10",
  "request": {
    "summary": "Observability Phase 4: evaluate the frozen alert thresholds against collected snapshots and deliver alerts to the Orbit dashboard and a board note only - no chat, no Discord; warn-only at the bee cap; operators may override thresholds via the existing override document.",
    "provenance": "TODO(authorization): wave-3 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 3 F10; gap source: ROADMAP.md 'Phase 4 - Resource snapshots and alerts' and observability/README.md 'They do not fire today'"
  },
  "repository": {
    "identity": "mojomast/workflow",
    "branch": "feat/observability-alerts"
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
    "id": "OBS-ALERTS",
    "title": "Phase-4 alert evaluation and delivery",
    "outcome": {
      "summary": "Thresholds fire as dashboard alerts and board notes; nothing is sent to chat; pausing bees stays out of scope.",
      "observable_behavior": [
        "An evaluator compares resource snapshots against alert.thresholds/v1 (defaults or an operator override loaded by observability.alerts.load_thresholds) and emits alert records for each breached threshold",
        "Delivery writes to two destinations only: the Orbit dashboard API (injected adapter) and a board note (injected adapter); no chat or Discord transport exists in the module",
        "At the bee cap (bees_in_flight_warn_at) the action is warn only; no pausing, no dispatch refusal",
        "Unknown values never fire an alert: a threshold whose operand is unavailable produces no alert and no silent zero comparison",
        "Alert records carry the threshold key, observed value or unavailability, the threshold, and the snapshot reference; dedupe by (key, window) so one breach does not spam repeats within the window"
      ]
    },
    "interfaces": [
      { "name": "observability/alerts_eval.py", "kind": "module", "change": "add" },
      { "name": "observability/alerts_cli.py", "kind": "cli", "change": "add" },
      { "name": "observability/tests/test_alerts_eval.py", "kind": "file", "change": "add" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "A resource snapshot breaching a default threshold produces exactly one alert record for that key with the observed value and threshold.",
        "verification": "test",
        "tests": ["observability/tests/test_alerts_eval.py::AlertsEvalTests::test_breach_emits_alert"]
      },
      {
        "id": "AC-002",
        "statement": "An operator override document changes the evaluated threshold without editing defaults; omitted keys keep defaults.",
        "verification": "test",
        "tests": ["observability/tests/test_alerts_eval.py::AlertsEvalTests::test_override_applies"]
      },
      {
        "id": "AC-003",
        "statement": "An unavailable operand produces no alert and no zero-comparison; the run records the unavailability.",
        "verification": "test",
        "tests": ["observability/tests/test_alerts_eval.py::AlertsEvalTests::test_unavailable_never_fires"]
      },
      {
        "id": "AC-004",
        "statement": "Delivery writes only to the two injected destinations; a structural test asserts the module has no chat or Discord transport and no other egress.",
        "verification": "test",
        "tests": ["observability/tests/test_alerts_eval.py::AlertsEvalTests::test_delivery_destinations_limited"]
      },
      {
        "id": "AC-005",
        "statement": "Repeated breaches within the dedupe window emit one alert; a breach after the window emits again.",
        "verification": "test",
        "tests": ["observability/tests/test_alerts_eval.py::AlertsEvalTests::test_dedupe_window"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "observability/alerts_eval.py",
        "observability/alerts_cli.py",
        "observability/tests/test_alerts_eval.py"
      ],
      "test_files": [
        "observability/tests/test_alerts_eval.py"
      ],
      "read_only": [
        "observability/alerts.py",
        "observability/alerts.defaults.json",
        "observability/schemas/alert-thresholds.schema.json",
        "observability/schemas/alert-thresholds-override.schema.json",
        "observability/schemas/resource-snapshot.schema.json",
        "observability/README.md"
      ],
      "prohibited": ["observability/schemas/", ".github/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (evaluator does not exist)",
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
    "observability/tests/test_alerts_eval.py::AlertsEvalTests::test_breach_emits_alert",
    "observability/tests/test_alerts_eval.py::AlertsEvalTests::test_override_applies",
    "observability/tests/test_alerts_eval.py::AlertsEvalTests::test_unavailable_never_fires",
    "observability/tests/test_alerts_eval.py::AlertsEvalTests::test_delivery_destinations_limited",
    "observability/tests/test_alerts_eval.py::AlertsEvalTests::test_dedupe_window"
  ],
  "scope": {
    "lease": [
      "observability/alerts_eval.py",
      "observability/alerts_cli.py",
      "observability/tests/test_alerts_eval.py"
    ],
    "read_only": [
      "observability/alerts.py",
      "observability/alerts.defaults.json",
      "observability/schemas/alert-thresholds.schema.json",
      "observability/schemas/alert-thresholds-override.schema.json",
      "observability/schemas/resource-snapshot.schema.json"
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

- The Orbit dashboard destination needs an orbitdesktop route; if none exists on `main` at admission, the dashboard leg is delivered as an injected adapter with a documented no-op default and the real route wiring is recorded in `pending_approvals` (Orbit-side follow-up), keeping this lease inside the workflow repo.
- DeepSeek/Go balances arrive via resource snapshots (F8's collector), not direct API calls in this lease; the evaluator never fetches credentials.
- Pausing non-priority bees at the cap is explicitly a later phase with its own yes ([ROADMAP.md](../../ROADMAP.md)) — out of this lease.
