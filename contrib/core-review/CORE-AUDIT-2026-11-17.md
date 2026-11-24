# Rizzstack core audit — November 17, 2026

Four upstream `main` branches were fetched and fast-forwarded. The revisions below are the audit baseline; the observations include local changes beyond those revisions. [Before/after SHAs](update-2026-11-17.json) · [Current reproduction instructions and verification limits](README.md).

| Repository | Fetched head | Commits brought in | Notable upstream developments |
|---|---|---:|---|
| workflow | `58aa969` | 195 | Rails event contracts, Observability collector updates, deployment-parity checker and Hindsight trial harness |
| bundlebees | `07cdc17` | 86 | Rails ledger, verification evidence and checkout-integrity fixes, delivery gates |
| hyvv | `9bed649` | 12 | Provider-refusal fallback, usage in landing events, lease-scoped patch collection |
| orbitdesktop | `9cb894b` | 38 | Approvals surface, Observatory fleet rendering and outbox-backed usage accounting |

## Findings addressed locally

- **Workflow / operator signals:** artifact parity now compares actual bytes and requires both sides to exist. A stopped gateway or missing local checkout evidence cannot stand in for a successful restart. The gateway row is still a restart-time proxy, not an attestation of which code was imported. Quota alerts now use the newest reading per resource, so an earlier low balance no longer survives a recovery.
- **Workflow / runner cost:** the root `tests/` suite ran four times on the same platform, Python and dependency set. It now runs once, retaining the named protocol jobs and targeted checks. In [the baseline run](https://github.com/mojomast/workflow/actions/runs/44098819345), the three removed invocations took **83 aggregate runner-seconds** (31 + 27 + 25); wall-clock savings have not been measured. At collection time the active ruleset required `bee-ci/reference`, `bee-ci/project-state` and `bee-ci/secret-scan`, but not the job owning the full suite. Consider requiring that existing check as well.
- **BundleBees / parallel integration:** independent requests used one disposable checkout and could remove it during another suite run. Checkouts now belong to the request/checkout/state combination; retries reclaim their own abandoned directory.
- **Hyvv / event delivery:** temporary storage failures previously looked like absent data, allowing cursor advancement or renumbering. The endpoint now returns a retryable 503 without advancing the cursor. Invalid or duplicate stored positions fail without rewriting the index.
- **Orbit / workspace saves:** an ambiguous first save followed by a 404 could resubmit the layout as a new operation. Orbit now holds the local backup and blocks dependent actions until it can reconcile against the saved state.

## Cross-repo usage handoff

On the fetched revisions a synthetic receipt made Hyvv emit `rizzstackusage` at the CloudEvents envelope root. The Workflow validator accepted it, BundleBees rejected the field (`event_invalid`), and the Orbit outbox reader returned `no_usage_payload`. The control event without the optional field passed both validators. Consequently even six successful GitHub Actions runs across the four fetched heads did not prove this handoff worked.

The local [four-repo regression](test_core_usage_roundtrip.py) now passes: it exercises the real Hyvv producer, Workflow validator, BundleBees validator and durable outbox, then Orbit's ingest CLI twice. A sample with 10 input tokens, 5 output tokens and an explicitly reported zero cache-read count produces exactly one ledger row on the `go` route. Counts absent from the extension are not priced as zero. The extension-only path reports unknown cost; for `free` and `agy`, the current ledger schema also requires an unknown route.

## Verification on the local changes

| Check | Result |
|---|---|
| Workflow: `python3 -B contrib/core-review/test_core_usage_roundtrip.py` | Passed; replay added no new row. Offline file handoff, no hosted workers. |
| Workflow: `python3 -m pytest -q tests/`; `python3 -m unittest discover -s observability/tests -t . -q` | 1,014 passed, 4 skipped in root tests; all 53 observability tests passed. Same 13 CI job definitions, one full-suite invocation. |
| BundleBees: revision tests, request-isolation/abandoned-worktree regressions and affirmative-suite evidence tests | 25 passed. Overlap used local Git repos and injected suite runners; no live isolation claim. |
| Hyvv: `python3 -m pytest -q tests/test_landing_export.py tests/test_landing_export_cursor.py tests/test_bee_landed_usage.py`; `python3 -m contract` | 58 passed. The in-process API contract ran 93 tests, with 3 skipped. |
| Orbit: workspace sync/events, source archive, usage accounting | 17 sync/events tests passed; 4 source-parity tests passed; 91 focused usage tests passed. A real headless Chromium 153 context with intercepted fixture HTTP observed `read → sync → read`, no second mutation, and an intact local backup. |
| Orbit: `npm run check` (Node 22.19, lockfile install using matching local Node headers) | Contract generation and build passed. Node suite: **1,413 passed, 55 failed, 14 skipped**. Failures include missing `/usr/bin/tmux`, the `sshd` fixture's `/run/sshd` ownership check, and workbench fixtures expecting npm under a conventional Node prefix. The subsequent IRC leg did not run. Re-run on a runner with those prerequisites before merging. |

BundleBees also passed 71 focused landing-event tests. Its optional usage metadata has a deliberately narrow vocabulary: nonstandard free-text stop reasons that Hyvv could emit at this stage could still be refused. The four-repo smoke covers the standard producer shape; it is not a claim that every historical receipt is ingestible. GitHub check results at collection were for the fetched commits, not the working-tree fixes.

## Priorities identified by the first pass

See the [follow-up implementation and verification](CORE-FOLLOWUP-2026-11-17.md) for the status of these items.

1. **Compatibility before rollout:** BundleBees now uses one positive suite-evidence check for wave publication and RETURN reporting. Check existing wave records for missing or ambiguous results before rollout; the old reader would accept those records.
2. **Owner approvals:** `orbitdesktop/server/approvals-route.mjs` treats journal read errors as empty history and rewrites the journal for every entry. Refuse unexpected read errors; verify route registration and durable append behavior with an actual server fixture before relying on the UI.
3. **Hyvv at fleet scale:** a one-row tail page required 100 outbox file reads with 100 retained events and 1,000 reads with 1,000 retained events (3.8 ms vs 40.0 ms median over five warm local reads, synthetic small events). Registration scans the same directory. Use the durable index to bound page work while preserving crash recovery; retain the cursor-stability tests. Add Windows cross-process coverage before relying on multiple writers sharing an index there.
4. **Cost reporting:** `bundlebees_plugin/metrics.py` can calculate cost per accepted change from partially metered attempts. Report the known subtotal and metering coverage separately rather than presenting it as a complete rate.

No hosted workers, production restarts, merges, pushes or deployments were part of this audit.
