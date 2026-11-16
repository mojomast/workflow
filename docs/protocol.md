# Protocol map (workflow mirror)

Status: live index, mirrored per the repo boundaries. The canonical protocol map
lives in the umbrella repository's docs (`mojomast/rizzstack`, `docs/protocol.md`);
the workflow repo cannot edit it from a worker lease, so this file mirrors the
rows whose artifacts live here — schema, validator, tests and chapter — and the
umbrella row for `rizzstack.memory/1` points back at this mirror. A row is added
here when its contract artifacts land in this repo, and the umbrella map is
amended by the owner's own hand in the umbrella repo.

Each row is a versioned contract: an `rizzstack.*` (or `workflow.*`, `acdd`,
`tdd-evidence`) identifier, the JSON Schema that defines its wire shape, the
validator or conformance oracle that enforces the rules a schema cannot, the
tests that keep it honest, and the chapter that specifies it. A contract without
all of those is a proposal, not a row.

| Contract | Chapter | Schema | Validator / oracle | Tests |
|---|---|---|---|---|
| `acdd/1` | [16](16-acdd-tdd.md) | [schemas/acdd-contract.schema.json](../schemas/acdd-contract.schema.json) | `reference/workflow/acdd.py` | `tests/test_feature_packet.py`, `tests/test_return_manifest.py` |
| `tdd-evidence/1` | [16](16-acdd-tdd.md) | [schemas/tdd-evidence.schema.json](../schemas/tdd-evidence.schema.json) | `reference/workflow/tdd.py` | `tests/test_feature_packet.py` |
| `rizzstack.feature-packet/1` (and `/2`) | [25](25-feature-packet.md) | [schemas/feature-packet.schema.json](../schemas/feature-packet.schema.json) | `tools/feature_packet.py` | `tests/test_feature_packet.py`, `tests/test_multi_dependency.py`, `tests/test_wave4_packets.py` |
| `rizzstack.source-resolution/1` | [25](25-feature-packet.md) | [schemas/source-resolution.schema.json](../schemas/source-resolution.schema.json) | `tools/feature_packet.py` | `tests/test_feature_packet.py` |
| `rizzstack.return/1` | [26](26-return-manifest.md) | [schemas/return-manifest.schema.json](../schemas/return-manifest.schema.json) | `tools/return_manifest.py` | `tests/test_return_manifest.py` |
| `rizzstack.recovery/1` | [27](27-recovery-protocol.md) | [schemas/recovery.schema.json](../schemas/recovery.schema.json) | `tools/recovery.py` | `tests/test_recovery_protocol.py` |
| `rizzstack.bee-landed/1` | [29](29-bee-landed.md) | [schemas/bee-landed.schema.json](../schemas/bee-landed.schema.json) | `tools/bee_landed.py` | `tests/test_bee_landed.py` |
| `rizzstack.campaign-report/1` | [30](30-campaign-closeout.md) | [schemas/campaign-report.schema.json](../schemas/campaign-report.schema.json) | `tools/campaign_report.py` | `tests/test_campaign_report.py` |
| `workflow.project-state/v1` | [18](18-parking-projects.md) | [schemas/project-state.schema.json](../schemas/project-state.schema.json) | `tools/project-state/check.py` | `tools/project-state/tests/` |
| `project.state/v1` | [18](18-parking-projects.md) | [schemas/project-state-event.schema.json](../schemas/project-state-event.schema.json) | `tools/project-state/check.py` | `tools/project-state/tests/` |
| `rizzstack.memory/1` | [32](memory-contract.md) | [schemas/memory-schema.v1.json](../schemas/memory-schema.v1.json) | `tests/test_memory_contract.py` (reference oracle; a standalone vault validator is a follow-on) | `tests/test_memory_contract.py` |

Notes on the newest row:

- `rizzstack.memory/1` is specified in `docs/memory-contract.md`: the
  semantic-memory layer of the rizzstack — a markdown, Obsidian-compatible vault
  read and written through an agent-agnostic read/query/write surface, with
  typed memories, digest-guarded writes, quarantine-by-default write zones,
  brief injection through the lease payload, per-type retention duties and a
  hybrid local retrieval stack with a documented fallback. The vault service is
  a follow-on slice and the honest gaps are tabled there.
