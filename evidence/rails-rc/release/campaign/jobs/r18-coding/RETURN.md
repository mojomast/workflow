# RETURN — empty-score

- schema: `rizzstack.return/1`
- job: `r18-coding`
- feature: `empty-score`
- intent packet digest: `820e6db8faf5386e73603aca07336b5fa811fa8890be97d22875e4b195e61b3a`
- workflow ref: `badc5591d7e5d4985fe829c3a1e39b2ee0e4c0f6`
- repository: `fixture/r18`
- source revision: `56276756d3296342b71dd814872bb7a899c107e9`
- authorization: `authorizations/r18-coding.json` by `synthetic-test-intent` (m1-authorization) at 2026-11-17T22:41:35Z
- receiver decision: `pending`

## Acceptance

| Criterion | Statement | Status | Tests | Evidence |
| --- | --- | --- | --- | --- |
| `AC-001` | An empty input scores zero | PASS | test_score.py::test_empty_score | evidence/r18-score/0002-green.json, verify-results/att_0000000000000018.json, jobs/r18-coding/rails-evidence.json#sha256=0701a07bdd50103627d57871e541b7625cd89ebd8ec2f15d9c8888c7e34754cf |

## Red / green

- test_first: `True`
- red: `{'record_path': 'evidence/r18-score/0001-red.json', 'revision': '56276756d3296342b71dd814872bb7a899c107e9', 'phase': 'red', 'sha256': 'c9fcff906fba0b99238eef06fbca8a1abcc3f7532d99f67e61f7d623c60dc696'}`
- green: `{'record_path': 'evidence/r18-score/0002-green.json', 'revision': 'cad02b6b123f7397e5ef179fc8b6c2d822b7e2df', 'phase': 'green', 'sha256': '12d84e77b33f35ea99873a9add46331cd17eff9b205ea1dc211bdd05a67227ca'}`

## Verification

- commit: `cad02b6b123f7397e5ef179fc8b6c2d822b7e2df`
- base revision: `56276756d3296342b71dd814872bb7a899c107e9`
- files: `score.py`
- suite: `{"command": ["/var/tmp/rails-rc-unv0bamz/tooling/bin/python", "-m", "pytest", "-q"], "result": "PASS"}`
- gitleaks: `{"result": "PASS"}`
- record: `verify-results/att_0000000000000018.json`

## Integration

- commit: `f2c1f30980d7c001a2402aa316f20f03b0a3e08b`
- wave: `r18-coding.w1`
- accepted wave digest: `a67d7e232469b9eb4d5cb854d842da0b2749528f6efbc6edec710187c3121533`
- evidence: waves/r18-coding.w1.json

## Transport

- none recorded (no publication is claimed)

## Attempts

| Attempt | State | Project | Source revision |
| --- | --- | --- | --- |
| `att_0000000000000018` | accepted | fixture/r18 | `56276756d3296342b71dd814872bb7a899c107e9` |

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

`3c89270df492ff9802733afe555ab7df4e098e700335e0423fa1b15878de2a82`
