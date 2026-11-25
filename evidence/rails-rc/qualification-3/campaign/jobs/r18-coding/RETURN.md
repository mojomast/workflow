# RETURN — empty-score

- schema: `rizzstack.return/1`
- job: `r18-coding`
- feature: `empty-score`
- intent packet digest: `793c4e5b9f869e343d78d6b1029f3594329505b5a22a2937fa23d8d720afbe27`
- workflow ref: `2974e7999b3221d268d1394d6d38b1435cd23668`
- repository: `fixture/r18`
- source revision: `ef7ba3a95a0bd8f026cb0c1323550b4c0caa8702`
- authorization: `authorizations/r18-coding.json` by `synthetic-test-intent` (m1-authorization) at 2026-11-17T21:47:02Z
- receiver decision: `pending`

## Acceptance

| Criterion | Statement | Status | Tests | Evidence |
| --- | --- | --- | --- | --- |
| `AC-001` | An empty input scores zero | PASS | test_score.py::test_empty_score | evidence/r18-score/0002-green.json, verify-results/att_0000000000000018.json, jobs/r18-coding/rails-evidence.json#sha256=057eef5249eaebf85892710692ebdb442a8a52bee450e11a9b67e6eb22d836ab |

## Red / green

- test_first: `True`
- red: `{'record_path': 'evidence/r18-score/0001-red.json', 'revision': 'ef7ba3a95a0bd8f026cb0c1323550b4c0caa8702', 'phase': 'red', 'sha256': '4d10d8c6bb19078e83de1b95a3dbd45ecaa62ad67b007f1d19430208b4a915c9'}`
- green: `{'record_path': 'evidence/r18-score/0002-green.json', 'revision': '5ba87f2a1cf26b286e98960eefab03d7bdc6d7c0', 'phase': 'green', 'sha256': '2c57b478009bb93461fcc619168819e4967fefa5914d7369bd71d405a2074fb0'}`

## Verification

- commit: `5ba87f2a1cf26b286e98960eefab03d7bdc6d7c0`
- base revision: `ef7ba3a95a0bd8f026cb0c1323550b4c0caa8702`
- files: `score.py`
- suite: `{"command": ["/var/tmp/rails-rc-unv0bamz/tooling/bin/python", "-m", "pytest", "-q"], "result": "PASS"}`
- gitleaks: `{"result": "PASS"}`
- record: `verify-results/att_0000000000000018.json`

## Integration

- commit: `6495978e1d161437035fe60461785d3816da5b3d`
- wave: `r18-coding.w1`
- accepted wave digest: `8c1999b06175175b005d5b0ed9c492f6efc267d7c25932cb23b38582c5e83093`
- evidence: waves/r18-coding.w1.json

## Transport

- none recorded (no publication is claimed)

## Attempts

| Attempt | State | Project | Source revision |
| --- | --- | --- | --- |
| `att_0000000000000018` | accepted | fixture/r18 | `ef7ba3a95a0bd8f026cb0c1323550b4c0caa8702` |

## Unrun

- transport receipt

## Pending approvals

- deploy
- merge
- publish
- release

## Limitations

- The authorization reference names a sealed local record; BundleBees does not authenticate the person.
- receiver_decision stays pending: bundlebees records the producer's evidence, never the receiver's decision
- worker claims are self-reported; only verification, wave and transport records count as evidence

## Evidence digest

`6fa6579244d635005e56dd428624cc2ffe2d78fc43d2830116b34d7187889ce8`
