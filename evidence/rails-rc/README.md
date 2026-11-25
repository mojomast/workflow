# Rails qualification record

**Release decision: HOLD.** Start with the [executive decision, gap matrix and reproduction instructions](release/DECISION.md), the [four full release SHAs](release.json) and the [exact-tuple result](release/summary.json). The native RETURN was repaired and independently verified. The required four-checkout software gate passed 665 cases with zero skips. The live Windows, production attribution and human decision gates remain open.

Superseded in part by [DECISION-2026-11-24-index-default.md](release/DECISION-2026-11-24-index-default.md): the attempt index is the default for new ledgers, while the HOLD stands unchanged.

| Capture | Observation |
|---|---|
| [`start.json`](start.json), [`before/`](before/) | Four fetched draft heads. All five original R18 cases passed; the frozen validator independently rejected the native RETURN with nine diagnostics across seven paths. The producer's verifier and receiver did not agree. |
| [`native/`](native/) | Producer and unchanged Workflow validator agreed on the corrected report. The receiver refused four disposable substitutions. Both real decisions in the synthetic run remained pending. |
| [`qualification-1/summary.json`](qualification-1/summary.json) | Local, clean four-checkout run: 458 JUnit test cases, zero failed, zero skipped. Separate Chromium owner-proxy check passed. Exact tuple, tool versions and checksums retained. This run predates subsequent authority corrections. |
| [`qualification-1/offline-replay.json`](qualification-1/offline-replay.json) | From the delivered fixture and a separate capture of its expected pins, a new receiver independently got RED on baseline and GREEN on both the verified and the integrated revision. No access to the worker, issuer database or signing key. |
| [`qualification-2/`](qualification-2/) | A later clean run failed 1/156 Workflow cases before the remaining suites. Removing a private fingerprint from error diagnostics exposed the lack of a proper coordinator verification-receipt commitment. Accepting any digest occurrence in an origin chain was insufficient. This failure must not be fixed by restoring the private diagnostic digest. |
| [`qualification-3/`](qualification-3/) | 483 cases, zero failures or skips. Both wheels were built from the named revisions and tested in both import orders. A receiver used the [separately retained verifier and dispatch pins](qualification-3/receiver-pins.json) to verify the synthetic packet and [re-execute its approved test](qualification-3/offline-replay.json). Later changes to the tick, notifier and proof classifier still require final-tuple qualification. |
| [`qualification-4/`](qualification-4/) | Expanded exact-tuple gate: **664 passed, zero skipped**. Signed GREEN, exact commit, case membership and sealed wave were checked. Independent review then identified a distinct issue in pre-candidate progress reports and the factory's interrupted first-ref publication. |
| [`qualification-5/`](qualification-5/) | Requiring a verified candidate closed the provisional progress-report gap and invalidated one positive native test fixture. The local gate stopped at that fixture (474 passed, one failed, no skips, remaining suites not run). Hosted BundleBees also failed that case; the other three component PRs passed. See the [recovery review](qualification-5/ref-publication-review.md) for the separate direct-replay correction. |
| [`qualification-6/`](qualification-6/) | 665 passed locally and in the hosted test step. The [hosted artifact upload failed](https://github.com/mojomast/workflow/actions/runs/44190916964/job/134419754691) because an original ledger-event filename contained `:`. The fix packs the unchanged fixture bytes and names into one checksummed archive. |
| [`release/`](release/) | Fresh exact heads after the CI packaging fix. Component CI, local JUnit, the issued native report and the independent receiver replay are retained. The disposition remains HOLD. |

For the complete starting review, see the [findings ledger](findings.md); [coordination](coordination.md) gives owners, package budgets, merge sequencing and rollback. The [Windows handoff](https://github.com/mojomast/workflow/blob/c61ff1c122ba649ea59ff7807cc8e671ed080b33/evidence/rails-rc/windows-canary.md) records exactly why no live run took place and what the operator needs to supply.

## Reproduce the public handoff independently

Use fresh clean clones of the evidence branch and the Workflow SHA in `release.json`. On Linux, supply Git and Python with pytest and jsonschema installed. No environment credentials are needed. From the evidence checkout:

```sh
python3 -B evidence/rails-rc/verify_fixture.py \
  evidence/rails-rc/release /path/to/clean-pinned-workflow
```

The check verifies the captured Git bundle hash, uses Workflow's commit-pinned receiver, compares exact test and source bytes against the frozen synthetic scenario, and re-executes the approved test on three revisions. `receiver-pins.json` is the coordinator's capture for this disposable run, not a live signed external anchor. Full `SHA256SUMS` includes private-run scratch logs not needed by this replay.

For a **new full tuple**, check out all four source SHAs under one parent and run the tested Workflow revision's `scripts/rails_tuple.py --help`. The runner rejects dirty inputs and missing/failed/skipped required cases; it writes the JUnit, checksums and both trace and campaign handoffs. Use `pr_checks.py tuple.json` separately to re-observe the PR checks; not every green component produces a conforming handoff.

## Overlapping pull requests

| PR | Content comparison and disposition |
|---|---|
| Workflow #90 `0edfc3a774a2b313baa59f0c324d8232929abe35` | Superseded **by content** in #91. Two paths are identical; the observability README retains the older changes and adds usage/recovery material. Do not apply both. |
| BundleBees #76 `8c6ec241488357f87557e05559b0b878319c183c` | Originally independent. Its own regression reproduced the default-workdir `NameError` on starting #82. Incorporated explicitly via `e2c01ec` (`cherry-pick -x`); its regression then passed. Apply only once. |
| BundleBees #77–80 | Prefer #82's revised, integrated source adapter, outbox reader, authenticated peer reader, and feedback implementation. Not verbatim cherry-picks; the integrations add checked provenance, cursor/fence, bounded read and privacy behavior. Retire older drafts only after reviewed superseding content lands. |
| BundleBees #81 `b7d3f3852062c51e53bbcb9d68492e4362d7b17a` | Independent delivery/reconciliation feature, absent from #82; review and rebase separately. It is not part of this release proof. |

No earlier PR has been closed or merged by this qualification. A separate human decision is required for accepting a RETURN, merging, enabling fleet capabilities, or deploying.
