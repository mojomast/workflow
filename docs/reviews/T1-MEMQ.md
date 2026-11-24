VERDICT: APPROVE

# T1-MEMQ — independent review of PR #133 (memory query CLI)

Reviewed the checkout at PR head `00231c3a8e3ad20a4f7a096dbb62ea42bec05975`
(the checkout is the single squashed commit `3d30305`). The stated base
`ae9c080262ab593e7643e2fba79cd51a018f25df` is not present in this clone, so
`git diff <base>..<head>` cannot be run. I reviewed the landed tree instead:
`rizzstack_memory/cli.py`, `rizzstack_memory/__main__.py`,
`docs/memory-query.md`, the approved test `tests/test_memory_query_cli.py`, and
the vault surfaces they call (`vault.validate_query_op`, `DiskVault.query`,
`ContractError`) plus `docs/memory-contract.md` and the bundlebees recall
protocol quoted in the brief.

The core SPEC is implemented faithfully: an existing-but-missing/non-directory
vault is refused before `DiskVault` is constructed and never created; the
optional stdin request must be a JSON object with the exact contract; caps are
taken from the request with the 8/480/4000 ceilings (defaults on empty stdin);
the query is the argv word with request fallback, stripped and cut to 500;
`DiskVault(DIR).query({"op": "query", "q": q, "k": max_items})` is used; items
are the six contract fields with capped `snippet` excerpts and a cumulative
six-field length budget; one JSON line is printed on success; `ContractError`
(and OS errors) exit 2 with empty stdout; only `query` is called — no
`write`/`promote`/`run_retention`.

## Findings

1. **minor — `rizzstack_memory/cli.py:49`** — whitespace-only stdin is treated
   as "no request" (`if not text.strip(): return {}`). SPEC says any non-empty
   stdin must be a JSON object with the exact contract, else stderr + exit 2.
   Verified: `printf '   \n\t ' | ... query --vault DIR x` exits 0 instead of
   2. No security impact (it only falls through to default caps and the argv
   query), but it is a small fail-open edge in an otherwise fail-closed path.
   Fix: test only for the truly empty string (`if not text:`), so whitespace
   reaches `json.loads` and is refused as `request_invalid`.

2. **minor — `rizzstack_memory/cli.py:73`** — `max_items` is floored at 1
   (`_cap(..., floor=1)`), so a request cap of `max_items: 0` returns one item.
   Verified against a seeded vault. SPEC says caps come from the request,
   clamped to *at most* 8; `0` should yield `"items": []`. Fix: when the clamped
   `max_items` is 0, skip the query (or pass `k=1` and slice to zero) and emit
   an empty list; note `validate_query_op` rejects `k=0`, so the query cannot be
   called with 0. Also tighten the wording at `docs/memory-query.md:32-34` if
   zero is made meaningful.

3. **minor (docs) — `docs/memory-query.md:9-10`** — "strictly read-only" is
   broader than observed behaviour: `DiskVault.__init__`
   (`rizzstack_memory/vault.py:536-544`) bootstraps `VAULT.md`, `index.md`,
   `hot.md`, `log.md` and the type directories into an existing empty
   directory, so querying an empty existing dir does create service files. The
   SPEC's own read-only definition ("never call write/promote/run_retention") is
   satisfied and `test_empty_vault_returns_no_items` relies on this bootstrap,
   so the code is correct; the concrete fix is a wording qualification
   ("does not modify a populated vault; the `DiskVault` constructor initialises
   an empty directory").

## AC-to-test mapping

| SPEC / AC | Named test | Result |
|---|---|---|
| request contract response, six item fields, first hit | `test_answers_recall_request_with_contract_items` | pass |
| request caps (max_items, excerpt) | `test_respects_request_caps` | pass |
| empty vault returns `[]` | `test_empty_vault_returns_no_items` | pass |
| empty stdin uses defaults | `test_works_without_stdin_request` | pass |
| wrong contract, missing vault, never created, empty stdout | `test_wrong_contract_or_missing_vault_fails_closed` | pass |
| query never writes | `test_query_never_writes` | pass |

Manual probes (all as expected): invalid JSON `{`, JSON array `[]`, missing
`contract`, empty query, empty argv query with empty request query, missing and
non-directory vault (exit 2, empty stdout, `does-not-exist` not created),
request-only query fallback, 600-char query, `max_total_chars: 10`, and
`max_excerpt_chars: 5`. No secrets, hostnames, IPs or absolute `/home`,
`/workspace` or `C:\` paths appear in the four reviewed files (grep clean).

## Rules checks

- Approved test file: read-only in this review; no diff baseline was available
  to prove byte-identity, but the file is the six-test approved suite described
  by the brief/CHANGELOG and no weakening was observed.
- No gate, sandbox, check or test was weakened or skipped; the suite reports
  skips that are environment-gated, not added by this PR.
- No scope creep observed in the reviewed tree (CLI, entry point, doc, test);
  `CHANGELOG.md:5` already carries the coordinator's landing bullet, which is
  the coordinator's job, not the bee's.
- Fail-closed behaviour is preserved for the contract paths; see finding 1 for
  the whitespace-only stdin edge.
- Docs match the code except the two wording/zero-cap points above.

## Test commands and exit codes

```
timeout 900 python3 -m pytest -q -p no:cacheprovider tests/test_memory_query_cli.py tests/test_memory_vault_disk.py
# exit 1 — /usr/bin/python3: No module named pytest
# (pytest is not installed in this environment; with no network/new deps
#  allowed, the equivalent unittest runs below were used instead)
```

```
timeout 900 python3 -m unittest -v tests.test_memory_query_cli tests.test_memory_vault_disk
# exit 0 — Ran 34 tests ... OK (6 query-CLI + 28 vault disk)
```

```
timeout 900 python3 -m unittest discover -s tests -t . -q
# exit 1 — Ran 622 tests ... FAILED (errors=15, skipped=28)
# All 15 errors are import errors for missing third-party modules
# (pytest / jsonschema) in unrelated modules: test_decision_queue,
# test_docs_parity, test_feature_packet, test_ground_truth_audit,
# test_multi_dependency, test_obs_bottlenecks, test_obs_decisions,
# test_obs_events_bridge, test_obs_fleet_wiring, test_obs_parallel_reads,
# test_obs_snapshot, test_observability_snapshot, test_recovery_protocol,
# test_return_manifest, test_runtime_conformance. No memory test failed.
# A source_rev comparison was not possible because the base commit object is
# absent from this checkout; the errors are environmental, not introduced here.
```

```
timeout 60 python3 -m py_compile rizzstack_memory/cli.py rizzstack_memory/__main__.py
# exit 0
```

Verdict rationale: no blocker or major finding; every acceptance behaviour is
covered by the approved tests and passes. The two minor input edge cases and the
doc wording note are non-blocking follow-ups.
