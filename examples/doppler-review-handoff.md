# Worked example of the Doppler review handoff

This is a retrospective teaching example based on [PR #5](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/5) and the collaboration account in [contrib/codex.md](../contrib/codex.md). It describes completed historical review work; it is not an instruction to reopen that work or dispatch an agent.

## Outcome and baseline

Make detection and location search faster while preserving event extraction, chosen locations and uncertainty outputs. The base was `1d06ae614fe7ce2935808dd5ae426e6adb586f25`; the reviewed initial head was `38d30c487bd7ac1902918f826d1c7c477fa9216c`. Kyle requested a brief for DOLAN, then returned DOLAN's results for review.

Scope: numerical work, event caching and prepared scoring. Preserve algorithms, precision, search coverage and the evaluation policy. Review and correction did not by themselves authorize merge, tag or release.

## Finding 1 preserve accumulation precision

**Expected:** the vectorized broadband path selects the same ridge as the base implementation on near-tied float32 input.

**Observed in the isolated review:** the old path selected ridge 70; the initial vectorized path selected ridge 5. The accumulation had changed to float32.

Reproduction input for the two implementations of `track_segments`, with `max_jump=30` and other defaults:

```python
Z = np.zeros((2000, 80), dtype=np.float32)
Z[:, 5] = 4.1
Z[:, 70] = 4.1
Z[0, 70] = 4.10001
```

This is an input fixture, not a standalone runnable benchmark. Use each revision's function and compare selected tracks. The returned correction asked for preserved float64 accumulation and regression coverage on the reproduction, longer inputs and randomized inputs. The PR records the fix in `4f44970`.

## Finding 2 validate cached contents

**Expected:** malformed cached data causes a miss and recomputation.

**Observed:** valid JSON with matching key material and `events: []`, but no `rejected` field, was accepted and then caused a `KeyError` downstream.

The correction required full payload/event validation, including missing fields, malformed events, invalid duration and truncated JSON. The PR records the fix in `bd79749` and parameterized malformed-input tests.

## Returned evidence and acceptance limits

At final head `1fd0bee10bf4516661d12bca13aec86b3e50b4a9`, the PR author reported 84 passed tests, two skipped network tests, and zero observed differences across the seven tuning clips. The revised timing sum was 2,073 → 746 seconds. Held-out equivalence was not rerun; warm-cache figures were from before the review fixes. The reviewer did not independently rerun that full recording benchmark.

The initial 2,279 → 960 second report belongs to a different run and revision. The initially reported event discrepancy was later attributed to the precision bug and disappeared after the fix. Keep each number attached to its evidence rather than combining the most favorable parts of both reports.

## What a learner should copy

Copy the structure: pin the artifact, state an invariant, show a minimal failure, request a focused fix, compare results, and retain the limits. Do not copy the speedup as a promise for another environment. The important reusable artifact is the review contract, not the benchmark number.
