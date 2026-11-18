# RETURN — empty-score

- schema: `rizzstack.return/1`
- job: `r18-coding`
- feature: `empty-score`
- intent packet digest: `93a5d6805821f90da44cc29380026e17cdf811ed7a4eb20a7478cc2b584d2d3c`
- workflow ref: `8f9f283f98beb01aa2d0b722085eefdc24ce0b37`
- repository: `fixture/r18`
- source revision: `fc2daa14691317bac173f165d3feee70e2068365`
- authorization: `authorizations/r18-coding.json` by `synthetic-test-intent` (m1-authorization) at 2026-11-17T22:32:43Z
- receiver decision: `pending`

## Acceptance

| Criterion | Statement | Status | Tests | Evidence |
| --- | --- | --- | --- | --- |
| `AC-001` | An empty input scores zero | PASS | test_score.py::test_empty_score | evidence/r18-score/0002-green.json, verify-results/att_0000000000000018.json, jobs/r18-coding/rails-evidence.json#sha256=5d3a2eceefa96a7a5d1925f7b2777e45a311b968b353d7062f3adc424d963e5e |

## Red / green

- test_first: `True`
- red: `{'record_path': 'evidence/r18-score/0001-red.json', 'revision': 'fc2daa14691317bac173f165d3feee70e2068365', 'phase': 'red', 'sha256': '5565ea9ecacd7924bbd2909cdc29ff96c5b094decbac101160c5e65937a9ccec'}`
- green: `{'record_path': 'evidence/r18-score/0002-green.json', 'revision': '5195f7c5ddad867e5cddc7a6f029c075c328cd26', 'phase': 'green', 'sha256': '7d8ed7e87c4c31e32c22861347a8d5476476d5b953765429e7b2aa979cf418a1'}`

## Verification

- commit: `5195f7c5ddad867e5cddc7a6f029c075c328cd26`
- base revision: `fc2daa14691317bac173f165d3feee70e2068365`
- files: `score.py`
- suite: `{"command": ["/var/tmp/rails-rc-unv0bamz/tooling/bin/python", "-m", "pytest", "-q"], "result": "PASS"}`
- gitleaks: `{"result": "PASS"}`
- record: `verify-results/att_0000000000000018.json`

## Integration

- commit: `0b6d871ae14531260cdeb21469d8263d71ea9608`
- wave: `r18-coding.w1`
- accepted wave digest: `fef02a3c93a92a190ab9a70f940b8e6cd27fc2a51cafd9011dff2f57c0f15f5f`
- evidence: waves/r18-coding.w1.json

## Transport

- none recorded (no publication is claimed)

## Attempts

| Attempt | State | Project | Source revision |
| --- | --- | --- | --- |
| `att_0000000000000018` | accepted | fixture/r18 | `fc2daa14691317bac173f165d3feee70e2068365` |

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

`ca5a7af942d30f491cb283b03e9b8aa2bf6d235c33510be77d62ef94194b527d`
