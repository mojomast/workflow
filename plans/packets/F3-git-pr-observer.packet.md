# F3 — Real-Git/PR read-only observer for campaign reconciliation (packet draft)

**Wave 1 · feature_id `bb-f3-git-pr-observer` · exact · mojomast/bundlebees**

Draft packet. Transcribe the JSON below verbatim at admission; substitute `TODO(authorization)` values from the sealed authorization; freeze via the bundlebees-side packet validation (`packets.py` loading `tools/feature_packet.py` from the pinned `WORKFLOW_SRC`).

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "bb-f3-git-pr-observer",
  "job_id": "job_wave1_f3",
  "request": {
    "summary": "Add a read-only Git/PR observer to campaign reconciliation: `campaign reconcile` gains an opt-in observer that compares the checkpoint's recorded refs against the real repository head and open PR states, reporting drift without ever resolving it.",
    "provenance": "TODO(authorization): wave-1 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 1 F3; gap source: docs/31-campaign-continuity.md 'Current implementation boundary'"
  },
  "repository": {
    "identity": "mojomast/bundlebees",
    "branch": "feat/campaign-git-pr-observer"
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
    "id": "CAMP-OBSERVER",
    "title": "Read-only Git/PR observer for campaign reconcile",
    "outcome": {
      "summary": "Campaign reconciliation can detect that reality moved (branch rewritten, PR merged/closed, head changed) and report it as drift, without mutating state or dispatching.",
      "observable_behavior": [
        "With the observer enabled, `campaign reconcile` runs a read-only `git rev-parse` comparison and, when a forge token is configured, a read-only `gh pr view` comparison for every recorded ref and open PR in the checkpoint",
        "Drift is classified informational (ref moved forward on the same history) versus blocking (recorded SHA no longer on ref; recorded open PR merged/closed/head-changed; recorded in-flight branch missing), mirroring the parking unpark drift rules",
        "Blocking drift stops reconciliation with a named reason; the observer never rewrites the checkpoint, never cancels work, never dispatches",
        "Without a forge token the observer degrades to Git-only checks and records the PR leg as not-checked, never as clean"
      ]
    },
    "interfaces": [
      { "name": "bundlebees_plugin/campaign_observer.py", "kind": "module", "change": "add" },
      { "name": "bundlebees_plugin/campaign.py", "kind": "module", "change": "modify", "notes": "wire the observer behind an opt-in flag; existing reconcile path unchanged when the flag is absent" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "Given a checkpoint whose recorded head still matches the repository, the observer reports no drift and reconciliation proceeds exactly as without the observer.",
        "verification": "test",
        "tests": ["tests/test_campaign_observer.py::CampaignObserverTests::test_no_drift_proceeds"]
      },
      {
        "id": "AC-002",
        "statement": "Given a recorded SHA no longer on its ref, the observer reports blocking drift, reconciliation stops with a named reason, and the checkpoint is unchanged.",
        "verification": "test",
        "tests": ["tests/test_campaign_observer.py::CampaignObserverTests::test_rewritten_ref_blocks"]
      },
      {
        "id": "AC-003",
        "statement": "Given a recorded open PR that has since merged or changed head, the observer reports blocking drift with the PR number and observed state.",
        "verification": "test",
        "tests": ["tests/test_campaign_observer.py::CampaignObserverTests::test_pr_state_change_blocks"]
      },
      {
        "id": "AC-004",
        "statement": "Without a forge token, PR legs are reported as not-checked (never clean) and Git legs still run.",
        "verification": "test",
        "tests": ["tests/test_campaign_observer.py::CampaignObserverTests::test_missing_token_reports_not_checked"]
      },
      {
        "id": "AC-005",
        "statement": "The observer performs no write operation: it opens no PR, pushes no ref, mutates no checkpoint file, and a structural test asserts the absence of mutating calls.",
        "verification": "test",
        "tests": ["tests/test_campaign_observer.py::CampaignObserverTests::test_observer_is_read_only"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "bundlebees_plugin/campaign_observer.py",
        "bundlebees_plugin/campaign.py",
        "tests/test_campaign_observer.py"
      ],
      "test_files": [
        "tests/test_campaign_observer.py"
      ],
      "read_only": [
        "bundlebees_plugin/job.py",
        "bundlebees_plugin/reconcile.py",
        "docs/CAMPAIGN-CONTINUITY.md"
      ],
      "prohibited": [".github/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (module does not exist yet)",
      "test_first": true
    },
    "verification": {
      "independent": true,
      "commands": ["python -m pytest tests/test_campaign_observer.py -q"],
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
    "tests/test_campaign_observer.py::CampaignObserverTests::test_no_drift_proceeds",
    "tests/test_campaign_observer.py::CampaignObserverTests::test_rewritten_ref_blocks",
    "tests/test_campaign_observer.py::CampaignObserverTests::test_pr_state_change_blocks",
    "tests/test_campaign_observer.py::CampaignObserverTests::test_missing_token_reports_not_checked",
    "tests/test_campaign_observer.py::CampaignObserverTests::test_observer_is_read_only"
  ],
  "scope": {
    "lease": [
      "bundlebees_plugin/campaign_observer.py",
      "bundlebees_plugin/campaign.py",
      "tests/test_campaign_observer.py"
    ],
    "read_only": [
      "bundlebees_plugin/job.py",
      "bundlebees_plugin/reconcile.py"
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

- The drift classification intentionally mirrors [docs/18 §6](../../docs/18-parking-projects.md) unpark rules (informational vs blocking) so the two protocols stay aligned.
- `campaign.py` is shared with the existing campaign CLI; the observer must be strictly additive behind a flag so the merged #25 behaviour is unchanged when the flag is absent (AC-001 asserts equivalence).
- The `gh pr view` leg is injected like `poll.py`'s launchers (command or HTTP adapter) so tests run offline with fakes.
