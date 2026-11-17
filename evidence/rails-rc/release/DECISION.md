# Release decision: HOLD

The four draft heads in [`release.json`](../release.json) form a reproducible software candidate. The unchanged Workflow validator accepts its native RETURN. **Do not merge for release, dispatch a live canary, or deploy on this evidence.** The current dispatcher cannot provide the required pre-dispatch worker assignment, and the supplied authorization does not bind the Windows worker and permitted interruption. Owner decisions are pending.

## What ran

| Check | Result / evidence |
|---|---|
| Clean four-checkout gate | [665 cases](summary.json): Workflow 156, BundleBees 320, Hyvv 77, Orbit Python 25 and Node 87. Zero failures, errors or skips. The separate [Chromium check](orbit-browser.log) passed. The exact toolchain, wheel hashes and lockfile digest are in the summary. |
| Hosted four-checkout gate | [GitHub Actions run 44192354558](https://github.com/mojomast/workflow/actions/runs/44192354558) passed the same 665 required cases with no failures/errors/skips. The [download and independent replay](hosted-replay.json) verified the archive, its internal checksums, and its own generated RETURN. Archive SHA-256: `5b425838c35ac50fa8a051b1c053c8894a94307ee6c8cb6bdb44f91fc2d44940`. |
| Component CI | [64 successful checks](ci.json) at the four release heads: Workflow 14, BundleBees 4, Hyvv 14, Orbit 32. Counts are reported check jobs, not test cases. [BundleBees' sandbox suite](https://github.com/mojomast/bundlebees/actions/runs/44190910945/job/134419736161) passed 2,537 with 16 skips. Those skips are not counted as passes in the required cross-stack gate. |
| Native RETURN | [Actual report](campaign/jobs/r18-coding/return.json) SHA-256 `6058fa382132dfb728908e47ddb519fc15a3d9241a21bd083b717482a9e3c585`; [sidecar](campaign/jobs/r18-coding/rails-evidence.json) SHA-256 `0701a07bdd50103627d57871e541b7625cd89ebd8ec2f15d9c8888c7e34754cf` resolves from `acceptance[0].evidence`. Body digest `3c89270df492ff9802733afe555ab7df4e098e700335e0423fa1b15878de2a82`. Manifest and sidecar decisions are `pending`. |
| Independent receiver | Recomputed both origin chains; checked the retained dispatch and verifier pins, approved Git blob and candidate/integrated revisions; refused substituted tests, evidence, receipt bytes, worker authority and receiver decisions, as well as six foreign receipt scopes. [Re-execution](offline-replay.json) got RED (`56276756`), verified GREEN (`cad02b6b`), integrated GREEN (`f2c1f309`). The fixture's automated review is a coordinator observation, not an authenticated human review. |
| Windows / historical waves | [Hosted native Windows](https://github.com/mojomast/hyvv/actions/runs/44183310292/job/134393082037) passed. [Offline canary rehearsal](offline-m2.json) exercised the four expected seed failures, four reference passes, and `contract_missing` with zero attempts. [One synthetic wave](copied-synthetic-wave.json) was suite-compatible. No historical production copy or authorized live worker was supplied. |

The original five green tests had hidden [nine schema diagnostics at seven distinct paths](../before/frozen-check.json). The later [receipt gap](../qualification-2/), [compatibility failure](../qualification-5/), and [ref-publication finding](../qualification-5/ref-publication-review.md) are retained. None was converted into an allowed skip. The CI archive correction preserves every original filename, including colons in ledger event URNs, inside one checksum-addressed tarball.

## Authenticated pagination on the release heads

Two fresh private 100,000-event SQLite ledgers; ten independent producers; one warm-up per lane and 100 measured logical 500-row pages per surface. Each physical response was authenticated, opened a fresh read-only snapshot, stayed under 32 KiB, and was checked against writer receipts. The threshold is **500 ms p95**.

| Configuration | Events | View | Result |
|---|---:|---:|---|
| [Default](http-default.json) | 1,614.091 ms | 525.956 ms | **FAIL** on both surfaces. |
| [Optional index installed before first append](http-indexed.json) | 499.716 ms | 189.422 ms | **PASS in this run.** Events had 0.284 ms of headroom. |

The [prior repeated indexed run](../performance/coordinator-replay-100.json) recorded 670.749 ms for events, so this is not a reliable deployment-wide pass. The indexed procedure is opt-in, and no deployed ledger was changed. Local-only attempts and ten appenders do not establish mixed-origin, production-hardware or multi-host performance.

## Gap closure and owners

| Gate | Software disposition | Remaining dependency |
|---|---|---|
| E1, E4, E7, E8: native proof | Schema and semantic validation are enforced. A frozen non-regression criterion needs its own RED; contract PASS needs complete signed GREEN on a verified candidate. An unsigned receipt or self-declared reviewer cannot grant PASS. | Authenticate a separately appointed reviewer for any real review criterion and retain verifier pins through a protected handoff. |
| E2, E5: owner feedback and board | First feedback write revalidates authority and expiry at the writer boundary. Historical board evidence is labeled accordingly. | Operator enrolls owner authority. Browser retry remains disabled until a consumer checks it at claim and commit. |
| E3, E6, E12, E13: storage and recovery | First-write contention handled before transactions; contradictory peer halted; notifier replays pinned content; integration uses the tested head and a one-shot pending publication. [Closing recovery review](recovery-last.md) covered 60 tests (0 skips) and three independent process-crash checks. | Provide a **copied** historical state and run the compatibility preflight before rollout. Process restart is not a physical power-loss guarantee. |
| E9: worker attribution | A worker observation cannot become attributed dispatch evidence merely by matching an enrolled chain. Untagged real leases refuse criterion attribution. | Coordinator owner must record endpoint, worker/ledger, job/project, contract and revision in a pre-POST intent, then bind the returned attempt to that assignment. Host operator supplies enrollment. [Source review](../dispatch-prerequisite.md). |
| E10, E11: privacy / publication | Private error fingerprints no longer authenticate receipts. Verifier retains its scoped commitment at write time. Companions are checked as a stable set before consumption. | Atomicity is per file; consumers must verify a retained generation. No atomic multi-file or physical-power-loss claim. |
| M1/M2 / activation | M1a exercised actual local servers, CLI and Chromium; the offline campaign produced real Git/test receipts. | Live worker, human feedback/acceptance, multi-host transport, qualified performance configuration and deployment/rollback rehearsal remain outstanding. [Operator handoff](https://github.com/mojomast/workflow/blob/c61ff1c122ba649ea59ff7807cc8e671ed080b33/evidence/rails-rc/windows-canary.md). |

**Independent review.** Hy4 Flash Free reviewed the retained release tuple. Its closing verdict was **HOLD**: it confirmed the 665-case gate, independent receiver replay, closure of the unsigned-receipt PASS finding (#8) and ref-publication correction. It withdrew its earlier assessment based on older pins. Its verdict is a software review, not a receiver decision or owner authorization.

## Reproduce

Use four **fresh** sibling repos at the full SHAs in `release.json`. For the independent replay, use the pinned Workflow checkout plus a separate checkout of this evidence branch. The commands below were exercised on Linux; the repository guides specify the Node, Python, Chromium, Git and gitleaks prerequisites.

```sh
e=/path/to/evidence-checkout/evidence/rails-rc
cd /path/to/four-checkouts
python3 -B workflow/scripts/rails_tuple.py --tuple "$e/release.json" --orbit-kit "$OFFLINE_ORBIT_KIT" --out "$SCRATCH/new-run"
python3 -B "$e/verify_fixture.py" "$e/release" "$PWD/workflow"
python3 -B "$e/pr_checks.py" "$e/release.json"
python3 -B workflow/scripts/bench_rails.py --tuple "$e/release.json" --temp-parent "$SCRATCH" --output "$SCRATCH/bench.json" --node-modules "$OFFLINE_ORBIT_MODULES" --chromium "$CHROMIUM_EXECUTABLE" --attempt-index --events 100000 --samples 100 --soak-seconds 1800
python3 -B "$e/performance/fresh_http.py" "$PWD" "$e/release.json" "$SCRATCH" "$SCRATCH/indexed-http.json" --indexed
# Default deployment configuration: repeat fresh_http.py with a new output path and no --indexed.
```

**Next decision:** keep all four PRs in draft. Follow the [merge sequence and reverse-order rollback](../coordination.md#sequencing-and-rollback) only after the software and owner gates clear. Start live preflight only when the operations owner supplies the dated, nonsecret worker/contract/workspace binding, capacity window, read grant, and interruption/recovery authority. The earlier approval alone does not satisfy those conditions. No merge, live attempt, release or deployment was performed.
