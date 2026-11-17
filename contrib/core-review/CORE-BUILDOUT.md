# Four-repository buildout

The build inputs are the 22 Rails packages in `workflow/plans/backlog.json`, the M2 canary runbook, and the F11–F19 feature packets in `workflow/plans/packets/`. Changes and measurements below refer to the local working trees. The tracked dispatch queue remains a historical record; local builds do not populate it with synthetic deliveries.

## Existing work reused

| Package | Source used locally |
|---|---|
| R05, BundleBees coordinator records | BundleBees PR 77, `fc6c513` |
| R06, terminal outbox adapter | BundleBees PR 78, `9601dcb` |
| R09, peer replication | BundleBees PR 79, `e0f632f` |
| R11, feedback and export | BundleBees PR 80, `12727cd` |
| R17A, operator and RETURN docs | Workflow PR 90, `0edfc3a` |

The four BundleBees PR suites passed together (84 tests) as originally integrated; the Workflow contract suite passed (84 tests, 174 subtests). Those checks did not qualify a combined deployment.

## Integration findings

- The peer reader now obtains its bearer from the launcher credential provider, uses the launcher's bounded pinned-address transport, refuses redirects, and does not expose the peer URL in status. A real temporary HTTP peer checks the header. The reader tracks the last **imported** hash instead of an advertised future head, resumes from the SQLite import receipt after restart and refuses a worker's self-asserted owner/verifier authority.
- From Workflow, `python3 -B contrib/core-review/check_rails_delivery.py` compares leased asset paths against the four checkouts and checks copies of the shared runtime against the original. Its exit status covers file presence and byte parity only.
- `python3 -B contrib/core-review/test_core_usage_roundtrip.py` exercises the separate terminal usage path, including duplicate replay.
- `python3 -B contrib/core-review/test_rails_working_trees.py` runs the package-specific suites in separate subprocesses and reports every missing or failed check. See the [four-checkout recipe](README.md) for browser, Python and Node prerequisites. A successful local run is still separate from native Windows or deployment measurements.

## Verified checkpoints

| Check | Evidence on the candidate |
|---|---|
| All 22 Rails packages, R00–R18 including R17A–D | All leased paths present. The canonical runtime manifest verified; 4 Hyvv and 12 Orbit Python modules were refreshed from the working tree. Re-run the inventory after changing a shared module. |
| End-to-end read path | At this checkpoint all 4 then-existing R18 checks passed, no skips. Chromium selected the same origin `tool.finish` ID as the BundleBees CLI. Disconnect/restart and replay preserved the origin bytes; all 7 observed envelopes and payloads validated. See [recorded results and reproduction](../../specs/rails-rollout.md). |
| Feedback and retries | An identical feedback write produced one durable row and zero interventions. R11 conflict, lost-ack and cross-process revision tests passed. R15 queue tests bound retry to a specific recovery request, budget, revision and fence; a recorded decision does not prove execution. |
| Full Workflow and Hyvv suites | `python3 -m pytest -q tests/` from each checkout. Workflow: 1,040 passed, 5 skipped, 225 subtests. Hyvv: 516 passed, 6 skipped, 97 subtests. Linux results; native Windows is a separate gate. |
| F12 / F14 | The GitHub picker persisted only selected repo names; its authorization/error paths used fixture responses. The evidence board, activity feed and inspector were exercised by Chromium against a loopback Orbit server. See `docs/ONBOARDING-GITHUB.md` in the Orbit checkout. |

The first R18 trial showed a hash-valid but schema-invalid worker envelope. The producer was corrected, vendor copies were refreshed, and the end-to-end test now rejects that mismatch. The receiver's decision in the recorded RETURN handoff is still `pending`; a synthetic run is not an owner decision.
