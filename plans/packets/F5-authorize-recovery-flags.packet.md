# F5 — `job authorize` recovery-ceiling flags (packet draft)

**Wave 2 · feature_id `bb-f5-authorize-recovery-flags` · exact · mojomast/bundlebees**

Draft packet. Transcribe verbatim at admission; substitute `TODO(authorization)` values; freeze via packet validation.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "bb-f5-authorize-recovery-flags",
  "job_id": "job_wave2_f5",
  "request": {
    "summary": "Expose recovery-ceiling flags on the bare `job authorize` CLI verb so a hand-written authorization can seal attempts, corrections, selectors, file/test scope and gates instead of silently defaulting to the empty ceiling.",
    "provenance": "TODO(authorization): wave-2 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 2 F5; gap source: docs/22-autonomy-architecture.md 'the bare job authorize CLI verb does not yet expose recovery flags'"
  },
  "repository": {
    "identity": "mojomast/bundlebees",
    "branch": "feat/authorize-recovery-flags"
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
    "id": "AUTH-RECOVERY",
    "title": "Recovery-ceiling flags for job authorize",
    "outcome": {
      "summary": "An operator authorizing a job interactively can state the recovery ceiling at authorization time; the sealed body carries it and jobs may only narrow it.",
      "observable_behavior": [
        "`job authorize` accepts optional flags for max attempts, max corrections, allowed replacement selectors, recovery file scope, recovery test scope and in-force gates",
        "The flags are sealed into the signed authorization body exactly as standing-grant derivation seals them; the resulting ceiling is identical in shape",
        "Omitting the flags preserves today's behaviour exactly: the empty ceiling (one attempt, zero corrections, no selectors)",
        "A job that restates the sealed ceiling may only narrow it; widening is refused with authorization_widened as today"
      ]
    },
    "interfaces": [
      { "name": "bundlebees_plugin/job_cli.py", "kind": "cli", "change": "modify" },
      { "name": "bundlebees_plugin/job.py", "kind": "module", "change": "modify", "notes": "authorize-path sealing only; validation logic unchanged" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "Authorizing with recovery flags produces a signed authorization whose recovery block equals the flags, byte-comparable to a standing-grant-derived ceiling of the same values.",
        "verification": "test",
        "tests": ["tests/test_job_cli.py::JobCliRecoveryTests::test_flags_seal_into_authorization"]
      },
      {
        "id": "AC-002",
        "statement": "Authorizing without the flags produces the empty ceiling, byte-identical to the pre-change behaviour.",
        "verification": "test",
        "tests": ["tests/test_job_cli.py::JobCliRecoveryTests::test_no_flags_empty_ceiling_unchanged"]
      },
      {
        "id": "AC-003",
        "statement": "A job document that widens a flag-sealed ceiling is refused with authorization_widened at admission and at apply.",
        "verification": "test",
        "tests": ["tests/test_job_cli.py::JobCliRecoveryTests::test_widening_refused"]
      },
      {
        "id": "AC-004",
        "statement": "The TTY requirement is unchanged: authorize refuses without a TTY whether or not recovery flags are supplied.",
        "verification": "test",
        "tests": ["tests/test_job_cli.py::JobCliRecoveryTests::test_tty_gate_unchanged"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "bundlebees_plugin/job_cli.py",
        "bundlebees_plugin/job.py",
        "tests/test_job_cli.py"
      ],
      "test_files": [
        "tests/test_job_cli.py"
      ],
      "read_only": [
        "bundlebees_plugin/grants.py",
        "docs/AUTONOMY.md"
      ],
      "prohibited": [".github/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (flags do not exist)",
      "test_first": true
    },
    "verification": {
      "independent": true,
      "commands": ["python -m pytest tests/test_job_cli.py -q"],
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
  "acceptance_ids": ["AC-001", "AC-002", "AC-003", "AC-004"],
  "tests": [
    "tests/test_job_cli.py::JobCliRecoveryTests::test_flags_seal_into_authorization",
    "tests/test_job_cli.py::JobCliRecoveryTests::test_no_flags_empty_ceiling_unchanged",
    "tests/test_job_cli.py::JobCliRecoveryTests::test_widening_refused",
    "tests/test_job_cli.py::JobCliRecoveryTests::test_tty_gate_unchanged"
  ],
  "scope": {
    "lease": [
      "bundlebees_plugin/job_cli.py",
      "bundlebees_plugin/job.py",
      "tests/test_job_cli.py"
    ],
    "read_only": [
      "bundlebees_plugin/grants.py"
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

- `job.py` and `job_cli.py` are shared with the merged M1 surface; the no-flag path must be byte-identical (AC-002 is the regression guard). Keep the diff additive.
- Flag names should mirror the standing-grant derivation's field names so the two authoring paths converge on one ceiling shape; the executor confirms exact names from `grants.py` at contract review and records them in the decisions log.
