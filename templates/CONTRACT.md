# ACDD contract (acdd/1)

Write this before any code. A reviewer approves it, the contract is frozen by its hash, approved tests are committed on their own (RED), and only then does a worker implement against it. Protocol: [docs/16](../docs/16-acdd-tdd.md). Machine-readable schema: [`schemas/acdd-contract.schema.json`](../schemas/acdd-contract.schema.json). Filled-in example: [`contract.example.json`](contract.example.json).

Fill the human-readable form below, then transcribe it into JSON (or write the JSON directly). Validate and freeze it with the reference (`workflow.acdd.validate_contract`, `freeze_contract`) or with bundlebees (`bundlebees contract validate` / `freeze`, on the `feat/acdd-tdd` branch until it is merged).

---

## Contract `<ID>` — <title>

**Outcome.** <one sentence: what a caller or user can do afterwards>

Observable behaviour:
- <behaviour 1>
- <behaviour 2>

**Interfaces.**

| Name | Kind | Change | Notes |
|---|---|---|---|
| `<name>` | function / class / module / cli / http / file / config | add / modify / remove / none | <signature, contract> |

**Acceptance criteria.** Every criterion has a unique id and says how it is verified. `test` criteria list the approved tests that prove them (`path::name`); mark existing behaviour that must keep passing as a regression.

| ID | Given | When | Then | Verification | Tests | Regression |
|---|---|---|---|---|---|---|
| AC-001 | <state> | <action> | <result> | test | `tests/test_x.py::XTests::test_y` | no |
| AC-002 | — | — | <statement> | test | `…` | yes |
| AC-003 | — | — | the combined branch passes the full suite | integration | — | — |

**Dependencies.** <other contract ids, or none> · **Assumptions.** <anything that would change the result>

**Scope.**
- Assigned files (the worker's lease): <paths>
- Approved test files (read-only for the implementer; never also assigned): <paths>
- Read-only: <paths>
- Prohibited (globs): <patterns>

**Baseline.** `source_rev`: <full commit SHA of the tests-only RED commit>

**TDD.** Applicable: yes / no (reason: <why not>). Test-first: yes / no. Say **no** when the tests were written after the code; the evidence then records `test_first: false` and no RED is claimed.

**Verification.** Independent: yes (always). Commands: <commands>. Integration: yes / no.

**Evidence required.** red, green, refactor, integration, review, security (choose; green is required when TDD applies, and red unless test-first is no).

**Authorization.**
- Human gates (must include merge, release, deploy, publish): merge, tag, release, deploy, publish
- Authorized: <what the worker may do>
- Not authorized: <editing the approved tests, merge, release, deploy, publish, …>

**Review.** Status: draft → approved. Approved by: <name>. Approved at: <UTC time>. `contract_sha256`: <filled by freeze>.

---

## Notes

- **Freezing.** `contract_sha256` is the SHA-256 of the canonical JSON (keys sorted, no spaces, ASCII) of everything except `review`. Any change after approval gives `contract_changed`; re-approve and re-freeze instead of editing a frozen contract.
- **Placeholder in the example.** `contract.example.json` uses an all-zero `source_rev` because the toy repository is generated fresh on every demo run; the demo fills in the real commit and re-freezes. A real contract always names a real commit.
- **Briefs without a contract** still run in legacy mode and are labelled "no ACDD contract; TDD evidence not required".
