# RETURN — empty-score

- schema: `rizzstack.return/1`
- job: `r18-coding`
- feature: `empty-score`
- intent packet digest: `bdf72546a2d20d4e52a75d77dc941a24ec4fd208180ee295d6e03e97d606d98a`
- workflow ref: `8f9f283f98beb01aa2d0b722085eefdc24ce0b37`
- repository: `fixture/r18`
- source revision: `66aa0061edd27ff9005d3438cf45a445ee79ebd9`
- authorization: `authorizations/r18-coding.json` by `synthetic-test-intent` (m1-authorization) at 2026-11-17T22:04:20Z
- receiver decision: `pending`

## Acceptance

| Criterion | Statement | Status | Tests | Evidence |
| --- | --- | --- | --- | --- |
| `AC-001` | An empty input scores zero | PASS | test_score.py::test_empty_score | evidence/r18-score/0002-green.json, verify-results/att_0000000000000018.json, jobs/r18-coding/rails-evidence.json#sha256=0539965b117df0c105d04ecf07f09647acd1abd90c1d08378dcb5d03ac9bb68d |

## Red / green

- test_first: `True`
- red: `{'record_path': 'evidence/r18-score/0001-red.json', 'revision': '66aa0061edd27ff9005d3438cf45a445ee79ebd9', 'phase': 'red', 'sha256': '449d337ff8e6d54f12a0261429c38f61df2e9cb64e2943879c7f80a360c3a533'}`
- green: `{'record_path': 'evidence/r18-score/0002-green.json', 'revision': '989c16b80052b145dc5b75c0363db5eeeface283', 'phase': 'green', 'sha256': 'd1d41d533c52fc4375797a42c1fbd3087fc614ce559b6512fb6203658f437b50'}`

## Verification

- commit: `989c16b80052b145dc5b75c0363db5eeeface283`
- base revision: `66aa0061edd27ff9005d3438cf45a445ee79ebd9`
- files: `score.py`
- suite: `{"command": ["/var/tmp/rails-rc-unv0bamz/tooling/bin/python", "-m", "pytest", "-q"], "result": "PASS"}`
- gitleaks: `{"result": "PASS"}`
- record: `verify-results/att_0000000000000018.json`

## Integration

- commit: `a5ec6c056a139b6866f3077a6caa6514427034fc`
- wave: `r18-coding.w1`
- accepted wave digest: `969a581b8f3a69d2d7ee06429c6b57ded356edbdb6285e83d57f885e23459677`
- evidence: waves/r18-coding.w1.json

## Transport

- none recorded (no publication is claimed)

## Attempts

| Attempt | State | Project | Source revision |
| --- | --- | --- | --- |
| `att_0000000000000018` | accepted | fixture/r18 | `66aa0061edd27ff9005d3438cf45a445ee79ebd9` |

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

`691a797ebe8b4b9d2cd581363f2dae1a78e5d3b707721b59c825ee5041776c57`
