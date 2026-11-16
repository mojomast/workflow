# M2-canary — the M2 contract-enforcement canary

- packet_id: M2-canary
- wave: m2-canary
- status: drafted, pre-staged; dispatch blocked until F2 (require-contract) is merged
- repository: mojomast/rizzstack-m2-canary
- source_plan: plans/rizzstack-dogfood-campaign.md (recovered branch; F2 is the require-contract packet)
- drafted: 2026-11-16 (America/Toronto)
- provenance: docs/16-acdd-tdd.md §9 (the `require_contract` setting and its `contract_missing` refusal), docs/19-coordinator-playbook.md (roles, bee policy, verification), docs/23-autonomy-devplan.md (M3.5 provisioning and job↔project binding), docs/18-parking-projects.md (the archive transition), docs/26-return-manifest.md (the pending receiver decision), docs/24-autonomy-dogfood.md ("failure with accurate evidence is an acceptable outcome"); the F1–F10 packets live on the recovered campaign branch and are not in this checkout, so F2 is identified here by its require-contract content, not by a merged SHA

## Intent

Fire the contract-enforcement canary the moment F2 (require-contract) merges, so the enforcement flip is
proved on a throwaway project instead of being discovered on a real one. The canary exercises the whole
`require_contract` path end to end — a frozen `acdd/1` contract attached to the brief, dispatch refusing a
contract-less brief with `contract_missing`, one bee implementing a synthetic feature, a verifier-recorded
RED before GREEN, review, integration, and a RETURN whose receiver decision stays pending — with a blast
radius of exactly one new project: `rizzstack-m2-canary`. This packet registers the canary at the
campaign-plan layer (packet id `M2-canary`, project name `rizzstack-m2-canary`, repository
`mojomast/rizzstack-m2-canary`); runtime registration happens only in runbook Step 4, after F2 merges and
after the approver's yes. Every step, command and expected evidence is already written in
[docs/m2-canary-runbook.md](../../docs/m2-canary-runbook.md); nothing is left to invent at run time.

## Delivered and remaining

| Delivered | This packet (the canary's definition and campaign-plan registration); docs/m2-canary-runbook.md — the exact end-to-end sequence with a command and expected evidence for every step, including the negative probe, the failure-handling matrix and the rollback/cleanup path; the synthetic feature definition (the `M2-canary-wave-tally` contract embedded in the runbook: two source files, one approved test file, five criteria, no dependencies); and tests/test_m2_canary_prep.py, the RED-first structure tests that pin all of the above (they ran red against an empty tree before the artifacts existed) |
| Remaining | Everything the runbook executes once F2 is merged and the approver says yes: repo creation, seeding the synthetic feature, freezing the contract at the real `source_rev`, project registration on the worker host and in the bundlebees job store, the negative probe, the one-bee run, RED/GREEN/REVIEW/integration records, the RETURN, the receiver's decision, and the cleanup that removes the canary again |

## Acceptance criteria

- AC-001 `record_events(["dispatch", "verify", "dispatch"])` returns `{"dispatch": 2, "verify": 1}` -> proven by tests/test_meter.py::MeterTests::test_record_events_counts_kinds
- AC-002 `record_events(["dispatch", "mystery"])` raises `UnknownEventKind` and returns no tally -> proven by tests/test_meter.py::MeterTests::test_record_events_rejects_unknown_kind
- AC-003 `record_events([])` returns `{}` -> proven by tests/test_meter.py::MeterTests::test_empty_events_yield_empty_tally
- AC-004 `render_tally({"verify": 1, "dispatch": 2})` returns `"dispatch=2\nverify=1"` -> proven by tests/test_meter.py::ReportTests::test_render_tally_sorts_and_joins
- AC-005 the combined branch passes the full canary suite -> proven by evidence/2026-11-16-m2-canary/integration.json::integration_record

## Dependencies

- F2 (require-contract): the trigger; the campaign packet that turns contract enforcement on via
  bundlebees' `require_contract` machinery (docs/16 §9). Not merged — nothing in this packet dispatches
  until it is. The canary validates exactly this flip, so it must run the moment it lands.
- docs/16-acdd-tdd.md: the protocol the canary exercises — contract shape and freezing (§2), RED/GREEN
  validity (§5), failure codes (§7), enforcement (§9–10).
- docs/23-autonomy-devplan.md: M3.5 phase 1 (hyvv `POST /v1/provision/project`, receipts, cleanup) and
  phase 2 (`provision_bind`, the job↔project binding the registration uses). Where a layer is not merged
  yet, the runbook records the step NOT RUN with that reason instead of skipping it silently.
- docs/18-parking-projects.md: the `active → archived` transition and the
  `tools/project-state/check.py` validation the cleanup uses to retire the canary project.
- docs/26-return-manifest.md: the `rizzstack.return/1` shape and the rule that a generated manifest
  always carries a pending receiver decision.
- tests/test_wave4_packets.py::test_all_four_packets_exist_and_nothing_else (repo-hygiene conflict,
  recorded here because it is real, not a work dependency): adding this fifth packet to plans/packets/
  turns that Wave-4 directory-lock assertion red. The fix — extend the lock to "the four Wave-4 packets
  plus the M2 canary" — belongs to tests/test_wave4_packets.py, which is outside this packet's change
  set; it is tracked in the canary handoff so it is fixed before, not discovered after, the next
  full-suite CI run.

## Authorization needs

- Approver: Kyle Durepos (`mojomast`), repository operator — his explicit yes for (a) creating
  mojomast/rizzstack-m2-canary, (b) registering the canary project on the worker host and in the
  bundlebees job store, (c) running the canary per the runbook, and (d) archiving and cleaning it up
  afterwards. An agent's go-ahead never stands in for his.
- Human gates: merge, release, deploy, publish — all four stay human-gated; the canary repo's own merge
  after acceptance, and the archive or deletion of the canary repository, are likewise his.
- Not authorized by this packet: touching any production project — mojomast/workflow,
  mojomast/bundlebees, mojomast/orbitdesktop, mojomast/hyvv, or any customer project (comfyrizz,
  photo-to-part, EOH and the rest of docs/07) — reading their state is the only permitted contact;
  spending beyond one bee dispatch or 30 wall-clock minutes; a second bee or any retry without a fresh
  yes; flipping `require_contract` on for any project except the canary; pushing to any production
  branch; and ever editing a RETURN manifest's receiver decision.

## Next executable action

1. Confirm F2 (require-contract) is merged into the pinned bundlebees revision, then run Step 0 (preflight) of docs/m2-canary-runbook.md — nothing in this packet dispatches before that.
