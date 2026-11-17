APPROVED

Independent review of PR #80 (rails: R00 feasibility - pinned sources, sanitized trace/session shape, proxy+auth+queue hooks, slice RAILS-R00). Review performed 2026-11-17 from a clean checkout grounded against the public origin.

## Grounding

- `git ls-remote https://github.com/mojomast/workflow.git refs/pull/80/head` returned `cd1e687009a4a18cc8eea760f1f564745c34257a` at review start and again immediately before committing this report: no head movement. `refs/heads/main` read `13d21fd06f5cd851cc71fce31a94acda2d92ae32` (advanced past the review base; irrelevant to the delta, which is reviewed against the PR's actual merge base).
- The GitHub REST pull record (`GET /repos/mojomast/workflow/pulls/80`) confirms the same head SHA, title and open state.
- The review base `84881eb356a0959bfbebd9e947dbdc4c23965830` was fetched from the origin and verified as the direct parent (and merge-base) of `cd1e687`. The review worktree tree hash equals the head tree hash (`bf5cb8c3585a40a4ab007fc3d1a81c26141698df` both sides), so all file-level checks ran on genuine head content.

## Check 1 - delta exactness (PASS)

`git diff 84881eb356a0959bfbebd9e947dbdc4c23965830..cd1e687009a4a18cc8eea760f1f564745c34257a --stat`:

```
 schemas/rails/fixtures/source-matrix.json | 1001 +++++++++++++++++++++++++++++
 specs/rails-feasibility.md                |  215 +++++++
 tests/test_rails_feasibility.py           |  413 ++++++++++++
 3 files changed, 1629 insertions(+)
```

- The full patch (saved and read in full: 1647 lines incl. headers) contains exactly these three paths, all new-file additions, no deletions, no modifications to any other file. `--numstat` agrees.
- Cross-checked against `GET /repos/mojomast/workflow/pulls/80/files`: GitHub reports the same 3 files with identical `added` status and identical add/delete counts. Delta is EXACTLY the three leased files and nothing else.

## Check 2 - RED-first property by mutation (PASS)

Executed in a scratch copy at `/tmp/opencode/r80/scratch` (full copy of the head tree); the leased working tree was never mutated.

1. Baseline at head: `python -m unittest discover -s tests -p test_rails_feasibility.py` -> `Ran 15 tests ... OK`.
2. Mutation A - fixture removed (moved out of the tree): suite FAILS with `FAILED (failures=1, errors=11)`, first failure the intended assertion `missing fixture: .../schemas/rails/fixtures/source-matrix.json`. RED confirmed.
3. Mutation B - pinned version entry dropped (the hyvv source entry deleted from `sources` in the fixture): suite FAILS with `FAILED (failures=2)`, including `matrix missing pinned source: hyvv`. RED confirmed.
4. Restore (fixture returned to tree): suite returns to `Ran 15 tests ... OK`. The RED->GREEN cycle is genuine and driven by the leased artifacts.

## Check 3 - every matrix entry pins a real version + trace + session shape (PASS)

- All five sources carry a 40-char lowercase-hex `pinned_commit`, `project_version`, `version_source`, https origin, `verified_at`, `verify_method`, and `role`.
- Every pin was fetched from its stated origin and checked out at the exact SHA (all five exist): workflow `9f6aa6dc...`, bundlebees `b2db04b8...`, hyvv `316bd975...`, orbitdesktop `8530a14b...`, vibeline `d5d0f425...`. For vibeline the origin default-branch head equals the pin, matching the matrix's own claim.
- Claimed versions verified at the pins: bundlebees `pyproject.toml` `version = "0.1.1"`; hyvv `launcher.py` `VERSION = "0.1.17"`; orbitdesktop `package.json` `version` `0.3.1`; vibeline `plugin.yaml` `version: 0.2.0`; workflow commit-pinned per the spec revision table. The five pins in `specs/rizzstack-rails-spec.md` section 2 (lines 33-37) match the matrix pins exactly.
- Trace + session shape: the hyvv entry carries a `native_trace` block (observed shape with lseq/ts/kind, state/heartbeat/worker-prefixed kinds, synthetic record list, explicit no-tool-events finding, wire shape, final receipt) and the vibeline entry carries a `session_shape` block (sessions/messages column descriptors, pairing rule, active-flag fallback, topology, version vector). Both are present and sanitized (structural scan in Check 6).

## Check 4 - hook citations resolve (PASS, one disclosed scope nuance)

Method: all four external repos were cloned and checked out at their exact pins; the package's deep tier was run with `RAILS_SOURCE_ROOTS` pointing at all five checkouts (`Ran 15 tests ... OK`), which mechanically verifies for every citation that the recorded digest matches sha256 of the anchor and that the anchor is present at the cited line. Independently, every one of the 98 unique citations (68 source hooks + 30 uncertainty citations, 30 of which reuse source hooks) was extracted and each cited file+line was opened in the actual pinned source; the actual line was compared with the anchor and the note's claim.

- 97 of 98 unique citations resolve against their pinned source with the anchor found at the cited line, and the note matches the construct in every case examined, including the load-bearing ones: the constant-time credential comparison in hyvv's request auth path (the cited line sits inside a guard that also requires the credential header's scheme prefix); the orbitdesktop owner-route boundary (origin/host gate + scheme prefix + constant-time match -> 403 `permission_denied`); the owner credential generated at boot, written mode 0o600 and installed by atomic rename with an explicit never-logged comment; the `serveApp` static serving layer with realpath rooting; the launcher redaction regex (sk-shaped, scheme-prefixed and long-opaque substrings) applied before storage; the append-only per-attempt JSONL, offset-indexed incremental reads, worker-kind prefixing, heartbeat shape, paged-200 upstream reads; the vibeline read-only URI connect, pairing-by-tool_call_id index, active-flag fallback, subagent topology, chain canonicalization and hash rule, unbounded load, query-string credential acceptance, and mutation-route list.
- Both absence checks reproduce at the pins: `git grep obs-snapshot` over the orbitdesktop tree at the pin exits with no matches (0 files), and a case-insensitive grep for fencing over `bundlebees_plugin/*.py` at the pin finds 0 matches. The doc's Q1/Q2 claims built on these absences are therefore evidence-backed, not guessed.
- The 98th citation is `schemas/rails/event.schema.json:3` (workflow). The file does not exist at the workflow pin `9f6aa6dc...`; it exists in the working tree (and at the review head), where the cited line matches the anchor exactly. This is not a guessed hook: the matrix's own `verify_method` for the workflow source states that its citations "resolve against this working tree", the doc's source table says the working tree carries the cited files, and the hook note ("draft rails envelope already in tree; R01 completes the closed schemas") is true at the review head. Recorded below as a non-blocking disclosure (D1).
- Spot-check of one loose-worded note: the orbitdesktop `AGENTS.md:9` note mentions bundle parity; line 9 carries the real-browser-testing requirement (the anchor matches) and the parity language appears two lines below (archive regeneration and parity verification). The cited construct exists; wording spans adjacent lines. Non-blocking.

## Check 5 - Q1-Q4 verdicts (PASS)

- Q1 verdict: resolved - five citations into the orbitdesktop pin; the deployed `/obs-snapshot` proxy is absent (absence check reproduced); the actual serving layer and the extension seam are cited; a deployment-side residual is explicitly stated.
- Q2 verdict: unresolved - with an explicit reason: the fenced action-queue interface does not exist at the pin (feature-queue pointer, lock-file claim serialization, an adapter comment stating no server-enforced exactly-once guarantee, zero fencing matches), the in-flight module is not in the tree, and the refusal to guess is stated. Downstream rule (capability_unavailable until real interface) is fixed.
- Q3 verdict: resolved - ten citations; attempt-level stream, no tool-level records, no rotation, terminal receipt via the durable landed CloudEvent with crash replay and durable export positions; downstream parser rules stated.
- Q4 verdict: resolved - eight citations; consumed columns, pairing, topology, active-flag fallback; residual (installed Hermes application is not a pinned repo) explicitly stated.
- The doc states each verdict verbatim (enforced by `test_doc_and_matrix_agree_on_verdicts`), and every resolved verdict carries at least one citation while the unresolved one carries a reason (enforced by `test_q1_through_q4_each_carry_a_verdict`).

## Check 6 - secret scan (PASS)

The house predicate was implemented exactly as specified and run over all three added files: name/value shapes for the listed credential words as word-tail followed by separator plus a value; the credential-scheme keyword followed by 6+ characters of the value charset; and literal prefixes for the known provider shapes (with the minimum-length qualifiers that distinguish a real value from a bare denylist word; hash digests and hex strings, which the matrix is full of, are correctly not flagged). Result: 0 hits in `specs/rails-feasibility.md`, 0 in `schemas/rails/fixtures/source-matrix.json`, 0 in `tests/test_rails_feasibility.py`.

- Negative control: planted sample lines (a key assignment, a scheme-prefixed header value, an AWS-style and a JWT-style literal) are all caught by the same scanner.
- The package's own, independent structural guard (`test_doc_is_sanitized`, `test_matrix_is_sanitized`, plus the trace/shape descriptor scans) also passes.
- This report was scanned with the same predicate immediately before committing: 0 hits.

## Check 7 - suite at the head (PASS)

`python -m unittest discover -s tests -p test_rails_feasibility.py` at the head worktree: `Ran 15 tests in 0.008s - OK` (15/15, 0 failures, 0 errors). The structural tier plus in-repo workflow citation verification needs no external setup. The deep tier (external anchors against pinned trees) also passes when `RAILS_SOURCE_ROOTS` is configured with checkouts at the five pins - reproduced during this review. The deep tier requires cloning four sibling repositories, which is an environment/setup precondition disclosed in the test docstring, not a defect.

## Check 8 - PR checks (PASS, recorded)

The `gh` CLI is installed but unauthenticated in this environment, so the public REST API was used instead: `GET /repos/mojomast/workflow/commits/cd1e687.../check-runs` reports 14 check runs at the head, all `completed` / `success` (including the repo's secret-scan and gitleaks checks, the schema/reference checkers on two OS images, the protocol checks and the cold-start acceptance job). Nothing pending. The legacy combined status endpoint reads `pending` with zero statuses, which is superseded by the check-runs result above.

## Classification and findings

Blocking count: 0 (DEFECTS only; environment-class and pre-existing-infra items are disclosures).

- D1 (DISCLOSURE, non-blocking): the workflow source's `event.schema.json:3` citation does not exist at the workflow pin commit `9f6aa6dc...`; it resolves in the working tree as the matrix's `verify_method` explicitly scopes it ("citations below resolve against this working tree") and as the doc's source table states. The hook's own claim ("draft rails envelope already in tree") is true at the review head. A reader expecting all four workflow citations to resolve at the bare pin should read `verify_method` first; no action required for this PR.
- D2 (DISCLOSURE, non-blocking, environment-class): deep verification of the 94 external citations requires local checkouts of the four sibling repos at their pins (`RAILS_SOURCE_ROOTS`); reproduced successfully by this reviewer, and the mechanism (per-anchor digest + line match) is documented in the test docstring for independent reproduction.
- D3 (DISCLOSURE, non-blocking): the orbitdesktop `AGENTS.md:9` note compresses requirements that live on lines 9 and 11 of that file (real browser tests on 9; archive parity on 11). The cited anchor exists at the cited line; only the note's summary spans two lines.
- No DEFECTs found. The delta is exactly the lease; the fixture, doc and tests are mutually consistent; verdicts are evidence-backed including the honest `unresolved` on Q2; sanitized artifacts contain no credential-shaped content; and the suite is GREEN at the head with a demonstrated RED under mutation.

## Verdict

APPROVED - no blocking findings. Numbered blocking findings: none.

## JSON summary

```json
{"verdict": "APPROVED", "blocking_count": 0, "checks_passed": 8, "checks_total": 8}
```
