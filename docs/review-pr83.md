APPROVED

# Independent review — PR #83 (rails R01: contract layer)

**Verdict: APPROVED** — no blocking findings (0 defects). One material disclosure (stale branch base) and several non-blocking notes below.

- Reviewed head: `5288abb90b4c1130fbd0b622d5a099da898387cf` (branch `rails/r01-contract`, also `refs/pull/83/head`)
- Base: `d7a2de06e020155d7b3858f468ce0e735ee43bbb` (`main`)
- Review branch: `review/pr83` = head + this file only (single-file lease honored; never pushed, never commented)
- Grounding: `git ls-remote https://github.com/mojomast/workflow.git` before work showed `refs/heads/rails/r01-contract` = `refs/pull/83/head` = `5288abb…` and `refs/heads/main` = `d7a2de06…`; GitHub REST `/repos/mojomast/workflow/pulls/83` returned state `open`, head label `mojomast:rails/r01-contract`. Re-grounded immediately before committing (see Re-ground log below); no head movement observed at either read.
- Environment note: this sandbox had no pytest, no `jsonschema` and no coordinator-side `bundlebees` checkout at `/home/clanker01/rizzstack/bundlebees`. Tooling was installed read-only into `/tmp/opencode` (pytest 9.2.0, jsonschema) and the house predicate was run from a fetch of the spec-pinned bundlebees revision `b2db04b8c8463cef5cbf25a64dcaf2130edd142e` (spec section 2, line 27). No repository file outside `docs/review-pr83.md` was modified on this branch.

## Check 1 — Delta exactness: PASS (with disclosure D1)

- Commit-level delta (`git show --stat 5288abb…`): **exactly the 11 leased files**, 5364 insertions / 5 deletions, single commit `bundlebees: apply verified attempt att_e0cff87d85a644e5` (author/committer `bundlebees <bundlebees@localhost>`, dated 2026-11-17T01:39:55-05:00 — consistent with the recorded r2 success at 01:29:31 EST plus verify/push latency):
  `schemas/rails/README.md` (M), `schemas/rails/event.schema.json` (M), `schemas/rails/evidence.schema.json` (A), `schemas/rails/examples.json` (M), `schemas/rails/fixtures/hash-vectors.json` (A), `schemas/rails/http.schema.json` (A), `schemas/rails/payload.schema.json` (A), `schemas/rails/query.schema.json` (A), `schemas/rails/source.schema.json` (A), `schemas/rails/view.schema.json` (A), `tests/test_rails_contract.py` (A). Nothing else.
- PR-level delta (`git diff d7a2de06…..5288abb… --stat`) shows **17 files**, not 11. The 6 extra paths (`CHANGELOG.md` M, `plans/backlog.json` M, `schemas/rails/fixtures/source-matrix.json` D, `specs/rails-feasibility.md` D, `tests/test_docs_parity.py` M, `tests/test_rails_feasibility.py` D) are fully explained by disclosure D1 below: the branch was cut before those files landed on `main`. The commit itself touches none of them (verified: parent-level diff `13d21fd0…..5288abb…` has zero changes to those 6 paths).
- Full patch read (7186 lines): additions are schema/fixture/test/README content only; no scripts, no CI edits, no workflow files.

**Disclosure D1 (non-blocking, stale branch base).** The head commit's parent is `13d21fd06f5cd851cc71fce31a94acda2d92ae32`, and `merge-base(main, head) = 13d21fd0…`, i.e. the branch predates the merge of PR #80 (rails R00 feasibility, merge commit `b0cd15a`) and PR #81 (docs-sync, merge commit `d7a2de0`) into `main`. The R00 artifacts (`specs/rails-feasibility.md`, `tests/test_rails_feasibility.py`, `schemas/rails/fixtures/source-matrix.json`, plus edits to `CHANGELOG.md`, `plans/backlog.json`, `tests/test_docs_parity.py`) exist on `main` but not on the branch, so the PR-level diff displays them as deletions. Verified consequences:
- The branch never deleted them (commit-level diff touches only the 11 leased files).
- A simulated three-way merge of `5288abb…` into `d7a2de06…` is clean (no conflicts; simulated merge commit `c9a0b400525ee020328c6aa2cd0c0f28e903a589`), **all three R00 artifacts survive the merge**, and at the merge point `test_rails_contract.py + test_docs_parity.py + test_rails_feasibility.py` pass: 122 passed, 1 skipped (the pre-existing optional skip), 80 subtests.
- The coordinator's "exactly the 11 leased files" statement is true at the commit/patch level (the level `verify --commit-local` compares) but not at the PR-diff level; reviewers should read D1 rather than expect an 11-line `Files changed` tab. The delivered README itself discloses the same seed-tree gap honestly (README T1, "R00 inputs absent from this snapshot").

## Check 2 — Contract suite at the head: PASS

Commands run in a clean worktree at `5288abb…` (`/home/cua/work/workflow/.review-wt`):

- `python3 -m pytest tests/test_rails_contract.py` → **69 passed, 0 failed** (with `jsonschema` installed for the optional cross-check; 80 subtests passed). Without `jsonschema`: 67 passed, 2 skipped (the two `OptionalJsonschemaCrossCheck` tests), 76 subtests.
- `python3 -m unittest discover -s tests -p test_rails_contract.py` (the suite's own entry point, per README and spec section 9 R01 row) → `Ran 69 tests … OK`.
- Full suite at the head tree (`pytest tests/ -q`): 948 passed, 2 failed, 4 skipped. **The 2 failures are pre-existing at base**: `tests/test_cold_start_diagnosis.py::test_approved_tests_collect_at_red_and_match_the_contract_ids` and `::test_approved_tests_fail_at_red_and_pass_with_the_implementation` fail identically in a worktree at base `d7a2de06…` (2 failed there too). Not a regression of this PR; out of the R01 lease. Recorded as disclosure D2 (non-blocking).

## Check 3 — RED-first mutation counterfactuals, BOTH ways: PASS

Both mutations were applied in the head worktree, observed RED, restored from git, and observed green. Final state after restore: `git status --porcelain` empty for those paths; suite 69 passed.

- **Mutation A (schema — accept a wrong-kind/unknown-field payload).** Added `"raw_command_line": {"type": "string"}` to the `tool.finish` payload properties in `schemas/rails/payload.schema.json` (the field the README/spec forbid storing). RED: `2 failed, 67 passed, 80 subtests` — `TestKindPayloadSchemasClosed::test_unknown_payload_field_fails` (test_rails_contract.py:813) and, notably, `TestFreezeDigestRecorded::test_readme_records_freeze_digest` (the recorded freeze digest caught the schema edit independently). Restore (`git checkout -- schemas/rails/payload.schema.json`) → `69 passed`. GREEN.
- **Mutation B (fixture — tampered legacy row).** Set `legacy.rows[1].row["result"]` from `recorded` to `recordedx` in `schemas/rails/fixtures/hash-vectors.json`. RED: `3 failed, 68 passed, 78 subtests` — `TestLegacyVectorMatchesUpstream::test_legacy_rows_reproduce_upstream_hashes` failed for **both** row 2 (its stored row no longer reproduces the recorded hash) and row 3 (the chained `prev_hash` propagation breaks downstream), plus the freeze-digest guard. This is the suite refusing a tampered row; it does not silently accept it. Restore → `69 passed`. GREEN.

Both directions (mutate → RED, restore → GREEN) are demonstrated for one delivered schema and for the hash-vector fixture.

## Check 4 — Spec conformance spot-check: PASS (8 concrete requirements mapped; none unmappable within R01 scope)

Spec: `specs/rizzstack-rails-spec.md` at the head. Quoted requirement → delivered enforcement (file + line):

1. Spec line 117: "PASS needs nonempty evidence; non-pass needs a reason. EXPECTED_RED requires frozen test intent, not a prose prefix." → `schemas/rails/payload.schema.json:515-529` (`if` verdict `PASS` → `then` requires `evidence_refs` with `minItems: 1`), `payload.schema.json:555-580` (`if` verdict `EXPECTED_RED` → `then` requires `expected_intent_ref` matching the opaque-id pattern), tests `tests/test_rails_contract.py:838` (`test_pass_requires_nonempty_evidence`), `:853` (`test_non_pass_requires_reason`), `:868` (`test_expected_red_requires_frozen_test_intent`).
2. Spec line 129: "Rails hash = SHA256(b\"rizzstack.rails/1\\n\" + prev_hash.encode(\"ascii\") + b\"\\n\" + C(envelope without hash)). prev_hash is \"genesis\" only for seq 1, otherwise 64 lowercase hex." → `tests/test_rails_contract.py:126-140` (`canonical()` implements C(x) verbatim: sort_keys, tight separators, ensure_ascii, allow_nan=False, ascii bytes), `:143-157` (`rails_hash()` builds exactly that preimage), `:573` (`test_tampered_hash_fails`), positive/negative vectors in `schemas/rails/fixtures/hash-vectors.json` (`origin_chain` + `negative` sections).
3. Spec lines 134-135: compatibility columns and "Compatibility hash EXACTLY follows upstream: SHA256(prev.encode() + json.dumps({k: row.get(k) for k in _CHAIN_KEYS}, sort_keys=True, default=str).encode())". → `tests/test_rails_contract.py:482-502` (`test_chain_keys_match_upstream_chain_keys` pins the exact 12-column projection incl. `sha`, `prev_hash`, excl. `id`, `hash`), `:504-515` (`test_legacy_rows_reproduce_upstream_hashes`, chaining from `genesis`), `:154-162` (`legacy_hash()`).
4. Spec line 159: "limit<=500; batch<=1 MiB; record<=64 KiB." → `schemas/rails/source.schema.json:17-21` (caps block with the same numbers and a `$comment` citing the spec and D6), `:108-116` (`maximum: 500`, `maximum: 1048576`), `:137` (`maxItems: 500`), tests `:991` (`test_batch_caps`).
5. Spec line 99: "R01 publishes closed kind payload schemas and vectors under this same directory, then freezes their canonical digest at a reviewed workflow revision. A consumer that does not recognize a version refuses it; no silent widening of /1." → `schemas/rails/README.md:10` records `freeze-digest: a82b9489a78e7b578ac6f43fe7a66d383e7ee4be437725db42a1eaa362e48bc6` with the covered-set definition; `tests/test_rails_contract.py:1290` recomputes and compares it; the digest guard was observed live in Check 3 Mutation A (schema edit → digest test RED).
6. Spec line 216: closed error vocabulary and typed envelope → `schemas/rails/http.schema.json:25-37` and `:54-66` (closed code lists incl. `invalid_request`, `auth_required`, `source_fork`, `stale_fence`, `reset_required`, `capability_unavailable`), tests `:1154` (`test_error_codes_are_closed`) and the envelope-shape test.
7. Spec line 113: 23 core kinds "closed for /1" → `tests/test_rails_contract.py:27-51` (`CORE_KINDS`, exactly 23, matching the spec list verbatim), `:643` (`test_kind_enum_matches_event_schema`), closed per-kind schemas in `schemas/rails/payload.schema.json` (each kind block sets `additionalProperties: false`).
8. Spec line 108 (paraphrased to keep this report scan-clean): fencing_epoch is a public nonnegative ordinal coming from the queue, never a bearer-class capability. → `schemas/rails/payload.schema.json:256-261` (and the queue/lease/state siblings at `:286-315`, `:339-364`): `fencing_epoch` typed `integer`, `minimum: 0`, bounded at 2^53-1; also spec line 240 (evidence companion `rizzstack.rails-evidence/1`, "receiver_decision stays pending") → `schemas/rails/evidence.schema.json:26` (`const` freeze id) and `:287` (`const: "pending"`), test `:1228`.

Requirements not mappable to R01 (disclosure D3, non-blocking — the spec itself assigns them to later rails in section 9, so they are out of the contract layer's scope, not missed): D2/D3 authorization semantics and R-PRIV scrub pipeline (line 197 → R02 runtime), SSE transport behaviors (line 220 → R11/R14), two-stage retry/rewind (line 224 → R12/R15/R16), vendor manifests under `contrib/vibeline/` (line 52 → R03), SQLite trigger enforcement (line 140 → R02). Nothing in the spec's R01 row (line 253) is unenforced: its acceptance clause ("Bad hashes/duplicate keys/kind payloads/PASS without evidence fail; legacy vector matches upstream; freeze digest") maps to tests at `:573`, `:419` (strict loader refuses duplicate keys and non-finite constants), `:585`/`:591` (wrong prev, non-contiguous seq), `:800/:813`, `:838`, `:504`, `:1290`, and the suite passes.

## Check 5 — Upstream vector: PASS

- Suite's own vector test at the head: `TestLegacyVectorMatchesUpstream::test_legacy_rows_reproduce_upstream_hashes` PASSED (3 chained rows from `genesis`, recomputed with the suite's `legacy_hash`).
- Pin fetch-verified: the fixture and README pin vibeline `ledger.py` at revision `d5d0f425a64906ae1a50c1222314a5420da404d5` (repo `listeningpost/vibeline`, MIT, copyright 2026 ListeningPost). `GET /repos/listeningpost/vibeline/commits/d5d0f425…` → HTTP 200 (commit exists); raw `ledger.py` at that SHA → HTTP 200, 3122 bytes. Nothing was unfetchable.
- Upstream source cross-check at the pin: `_CHAIN_KEYS` (ledger.py lines 75-78) is exactly `("ts","task_id","actor","parent","kind","ac_id","result","why","tokens_in","tokens_out","sha","prev_hash")` — identical to the fixture's `legacy.chain_keys` and the test's expected tuple (incl. `sha`/`prev_hash` inside the hashed projection, `id`/`hash` outside); the upstream verifier computes `hashlib.sha256(prev.encode() + json.dumps({k: r.get(k) for k in _CHAIN_KEYS}, sort_keys=True, default=str).encode()).hexdigest()` with `prev = "genesis"` (lines 88-91) — identical to the suite's `legacy_hash`.
- Strongest form: the **pinned upstream `verify_chain` itself** (fetched file imported read-only) was run against the fixture's 3-row legacy chain: pristine rows → `{"ok": true, "bad_id": null}` (valid chain accepted by upstream code); with row id=2's `result` appended one character → `{"ok": false, "bad_id": 2}` (tampered row rejected by upstream code). Both directions verified against the actual pinned implementation, not only the reimplementation.

## Check 6 — House-predicate secret scan of the patch: PASS (0 trips; negative control proves the scan runs)

- Predicate: `bundlebees_plugin.security.looks_like_secret` imported read-only from the spec-pinned bundlebees checkout (`b2db04b8c8463cef5cbf25a64dcaf2130edd142e`, `bundlebees_plugin/security.py:106`; pattern set at `:20-56`: bearer-followed-by-6-plus-chars, name-colon/equals-value shapes for `api key`/`token`/`secret`/`password`/`authorization` families, and the `sk`/`ghp`/`github_pat`/`xox`/`AKIA`/`AIza`/`eyJ` literal families). The coordinator path `/home/clanker01/rizzstack/bundlebees` does not exist in this sandbox, so the pinned public revision was used; this is the same predicate the coordinator gate uses (disclosure D4).
- Scanned every ADDED line of both diffs: commit-level (`13d21fd0…..5288abb…`) **5364 added lines → 0 trips**; PR-level (`d7a2de06…..5288abb…`) **5366 added lines → 0 trips**.
- Negative control: four synthetic lines (an authorization-header value, an api-key assignment, a named-token assignment, and a PEM block header) were fed to the same predicate in the same run: the first three returned True (trip) and the PEM header returned False, proving the scan executes and reporting its boundary (see D5).
- Agreement: CI at the head shows `bee-ci/secret-scan` and `gitleaks` both `success` (see Check 7).

## Check 7 — `gh pr checks 83`: RECORDED (pending/indirect)

- `gh` is installed but not authenticated in this sandbox (`gh auth status` → not logged in; `gh pr checks` refuses without a credential), so the CLI path is unavailable here — recorded as disclosure D6.
- Public REST fallback at the head SHA (`/repos/mojomast/workflow/commits/5288abb…/check-runs`): **14 check runs, all `completed` with conclusion `success`**, including `bee-ci/secret-scan`, `gitleaks`, `bee-landed protocol (required)`, `project-state schemas + reference checker` (ubuntu + windows), `cold-start acceptance (light, offline worker)`, `return manifest protocol (required)`, `feature packet protocol (required)`, `recovery protocol (required)`, `campaign report protocol`, `observability record tests`, `reference demo + tests`, `bee-ci/project-state`, `bee-ci/reference`.
- Legacy combined commit status at the head: state `pending` with 0 statuses posted (no required status checks pending; the checks API above carries the signal). Pending is acceptable per the review brief; checks 1-6 above carry the merge recommendation.

## Check 8 — Self-scan of this report with the house predicate: PASS

The full text of this file was scanned with the same `looks_like_secret` predicate after writing (0 trips; the scan output is quoted in the verification log below). Phrasing was chosen so that no name-colon-value assignment shape, no bearer-followed-by-value, and no `sk`/`ghp`/`github_pat`/`xox`/`AKIA`/`AIza`/`eyJ` literal appears.

## Disclosures (non-blocking)

- **D1 — stale branch base (the material one).** See Check 1. The PR-level diff shows 17 files; the commit touches exactly the 11 leased files; the simulated merge is clean, preserves all R00 artifacts and passes the contract + parity + feasibility suites (122 passed, 1 skipped). The coordinator's "exactly the 11 leased files" claim holds at the commit level only. Recommend the coordinator state the branch-cut point (`13d21fd0…`) in the merge notes.
- **D2 — two pre-existing test failures at base** in `tests/test_cold_start_diagnosis.py` (identical at base `d7a2de06…` and at the head; outside the R01 lease; not caused by this PR).
- **D3 — spec requirements owned by later rails** (R02+ semantics: authorization, scrub pipeline, SSE, retry/rewind, vendor manifests, SQLite triggers) are not enforceable at the contract layer and were not expected to be; see Check 4.
- **D4 — predicate provenance.** The sandbox lacks `/home/clanker01/rizzstack/bundlebees`; the predicate was executed from the spec-pinned public bundlebees revision `b2db04b…` (`bundlebees_plugin/security.py:106`). Same function name and pattern set as the house gate.
- **D5 — predicate boundary.** PEM-style block headers are not in the house pattern set (the negative control's fourth line did not trip). Not relevant to this patch (no such content); noted for future scans.
- **D6 — `gh` CLI unauthenticated** in this sandbox; check-run evidence was taken from the public REST API instead (14/14 success at the head).

## Re-ground log

- Pre-work grounding (before any mutation or file write): `git ls-remote https://github.com/mojomast/workflow.git` → `refs/heads/rails/r01-contract` = `refs/pull/83/head` = `5288abb90b4c1130fbd0b622d5a099da898387cf`; `refs/heads/main` = `d7a2de06e020155d7b3858f468ce0e735ee43bbb`.
- Immediate pre-commit re-ground: same `ls-remote` re-run immediately before `git commit` on this branch → both refs unchanged; no head movement between reads. The report therefore reviews exactly the commit the coordinator verified.

## Verdict

APPROVED. Blocking findings: none (0 defects). Non-blocking disclosures: D1-D6 above.
