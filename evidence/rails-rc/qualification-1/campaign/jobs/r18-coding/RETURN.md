# RETURN — empty-score

- schema: `rizzstack.return/1`
- job: `r18-coding`
- feature: `empty-score`
- intent packet digest: `1a08023f03d4bfcd8139e52157b66328f49dd1a78aa67751f148c3fc153c4185`
- workflow ref: `74a107743a6593f2c6b79f545249a4605ac6456e`
- repository: `fixture/r18`
- source revision: `0a382f282823db9724e1efd90998c3eac335f8e4`
- authorization: `authorizations/r18-coding.json` by `synthetic-test-intent` (m1-authorization) at 2026-11-17T21:15:24Z
- receiver decision: `pending`

## Acceptance

| Criterion | Statement | Status | Tests | Evidence |
| --- | --- | --- | --- | --- |
| `AC-001` | An empty input scores zero | PASS | test_score.py::test_empty_score | evidence/r18-score/0002-green.json, verify-results/att_0000000000000018.json, jobs/r18-coding/rails-evidence.json#sha256=9737eb31934b81b5eff357e2df01ed136560b715ab58acecba2975f493359c6c |

## Red / green

- test_first: `True`
- red: `{'record_path': 'evidence/r18-score/0001-red.json', 'revision': '0a382f282823db9724e1efd90998c3eac335f8e4', 'phase': 'red', 'sha256': 'a1258f59b4676a3d922364ddeab7c578fc564e97b6ee72e3b56ef1b0ea295f12'}`
- green: `{'record_path': 'evidence/r18-score/0002-green.json', 'revision': '0ba9d3cdec68748f350b020e6cebdba998efe7d7', 'phase': 'green', 'sha256': '5e5ec80b535dd56485ad3a8760d111e88b8d8c1026580e790cfb0ad57c106994'}`

## Verification

- commit: `0ba9d3cdec68748f350b020e6cebdba998efe7d7`
- base revision: `0a382f282823db9724e1efd90998c3eac335f8e4`
- files: `score.py`
- suite: `{"command": ["/tmp/opencode/bbvenv/bin/python", "-m", "pytest", "-q"], "result": "PASS"}`
- gitleaks: `{"result": "PASS"}`
- record: `verify-results/att_0000000000000018.json`

## Integration

- commit: `ecd71e2bb237ea95ef9940738cb4f998e9b62f53`
- wave: `r18-coding.w1`
- accepted wave digest: `45914013e4a3ae7a04d0c37b19827f474e0d49ceae9f58ed126f9f4518075888`
- evidence: waves/r18-coding.w1.json

## Transport

- none recorded (no publication is claimed)

## Attempts

| Attempt | State | Project | Source revision |
| --- | --- | --- | --- |
| `att_0000000000000018` | accepted | fixture/r18 | `0a382f282823db9724e1efd90998c3eac335f8e4` |

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

`358edd71d9d3c77c0af58c09d02866089137d26ed48c11c5c73e92dd4ef2849b`
