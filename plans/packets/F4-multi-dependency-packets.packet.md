# F4 — Multi-dependency descendant packets (packet draft)

**Wave 2 · feature_id `wf-f4-multi-dep-packets` · exact · mojomast/workflow**

Draft packet. Transcribe the JSON below verbatim at admission; substitute `TODO(authorization)` values from the sealed wave-2 authorization; freeze via `tools/feature_packet.py`.

```json
{
  "packet_version": "rizzstack.feature-packet/1",
  "feature_id": "wf-f4-multi-dep-packets",
  "job_id": "job_wave2_f4",
  "request": {
    "summary": "Lift the one-dependency limit on descendant feature packets: allow a descendant packet to name N dependencies, resolve each against its accepted commit, and refuse when any resolution cannot prove ancestry, scope and budget equality.",
    "provenance": "TODO(authorization): wave-2 authorization reference; source request: plans/rizzstack-dogfood-campaign.md Wave 2 F4; gap source: docs/25-feature-packet.md 'multi-dependency support is not claimed' and docs/21-autonomy-gap-analysis.md transition 2 PARTIAL"
  },
  "repository": {
    "identity": "mojomast/workflow",
    "branch": "feat/multi-dependency-packets"
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
    "id": "PKT-MULTIDEP",
    "title": "Multi-dependency descendant feature packets",
    "outcome": {
      "summary": "A descendant packet may declare multiple dependencies; the source-resolution record binds all of them, and the derived revision must descend from every accepted dependency commit.",
      "observable_behavior": [
        "feature-packet.schema.json accepts a descendant source_policy.dependencies array with 1..N entries (schema version bump)",
        "validate_source_resolution refuses a resolution that omits any declared dependency or binds an accepted commit that is not an ancestor of the derived revision",
        "The derived contract must equal the template except source_rev and the review block, for every dependency's resolution path",
        "Pinned examples gain a two-dependency case; the existing one-dependency examples keep validating unchanged"
      ]
    },
    "interfaces": [
      { "name": "schemas/feature-packet.schema.json", "kind": "schema", "change": "modify" },
      { "name": "schemas/source-resolution.schema.json", "kind": "schema", "change": "modify" },
      { "name": "tools/feature_packet.py", "kind": "module", "change": "modify" },
      { "name": "schemas/examples/feature-descendant-multi.json", "kind": "file", "change": "add" }
    ],
    "acceptance_criteria": [
      {
        "id": "AC-001",
        "statement": "A descendant packet with two dependencies validates, and its resolution record binds both dependency features and both accepted commits.",
        "verification": "test",
        "tests": ["tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_two_dependency_packet_and_resolution"]
      },
      {
        "id": "AC-002",
        "statement": "A resolution that omits one declared dependency, or whose derived revision does not descend from every accepted commit, is refused with a named code.",
        "verification": "test",
        "tests": ["tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_missing_or_non_ancestor_dependency_refused"]
      },
      {
        "id": "AC-003",
        "statement": "The one-dependency examples and tests from the current schema still pass unchanged (backward compatibility).",
        "verification": "test",
        "tests": ["tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_single_dependency_examples_unchanged"]
      },
      {
        "id": "AC-004",
        "statement": "The pinned example's workflow_ref pin is bumped to the commit that bears the new schema bytes, and the pin test passes for both schemas.",
        "verification": "test",
        "tests": ["tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_examples_repinned_to_schema_commit"]
      }
    ],
    "dependencies": [],
    "scope": {
      "assigned_files": [
        "schemas/feature-packet.schema.json",
        "schemas/source-resolution.schema.json",
        "tools/feature_packet.py",
        "schemas/examples/feature-descendant-multi.json",
        "tests/test_feature_packet.py"
      ],
      "test_files": [
        "tests/test_feature_packet.py"
      ],
      "read_only": [
        "docs/25-feature-packet.md",
        "schemas/examples/feature-descendant.json",
        "schemas/examples/feature-exact.json"
      ],
      "prohibited": ["docs/"]
    },
    "source_rev": "TODO(authorization): substitute the sealed 40-hex base revision",
    "tdd": {
      "applicable": true,
      "reason": "approved tests exist and fail at the baseline (multi-dependency refused today)",
      "test_first": true
    },
    "verification": {
      "independent": true,
      "commands": ["python3 -m unittest tests.test_feature_packet -v"],
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
    "tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_two_dependency_packet_and_resolution",
    "tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_missing_or_non_ancestor_dependency_refused",
    "tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_single_dependency_examples_unchanged",
    "tests/test_feature_packet.py::FeaturePacketMultiDepTests::test_examples_repinned_to_schema_commit"
  ],
  "scope": {
    "lease": [
      "schemas/feature-packet.schema.json",
      "schemas/source-resolution.schema.json",
      "tools/feature_packet.py",
      "schemas/examples/feature-descendant-multi.json",
      "tests/test_feature_packet.py"
    ],
    "read_only": [
      "schemas/examples/feature-descendant.json",
      "schemas/examples/feature-exact.json"
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

- This is a schema-version change: per [docs/16 §8](../../docs/16-acdd-tdd.md) validators refuse unknown versions, so the packet version string stays `rizzstack.feature-packet/1` only if the schema change is additive; otherwise bump to `/2` and keep a `/1` acceptance path. The executor decides at contract review and records it in the decisions log.
- The bundlebees queue consumes the schema via `WORKFLOW_SRC` pin; bundlebees CI's pin bump is a separate follow-up PR in the *bundlebees* repo (not this lease) — record it in the RETURN's `pending_approvals`.
