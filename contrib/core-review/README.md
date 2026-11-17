# Four-checkout core review — November 17, 2026

[Initial audit](CORE-AUDIT-2026-11-17.md) · [Follow-up](CORE-FOLLOWUP-2026-11-17.md) · [Buildout](CORE-BUILDOUT.md) · [Fetched revisions](update-2026-11-17.json)

These are advisory observations from successive working trees. The revision JSON identifies the four upstream **bases**, not the candidate bytes. Use matching revisions of all four draft PRs when reproducing a result. No deployed worker, native Windows run or owner acceptance is implied.

## Reproduce from sibling checkouts

Place `workflow/`, `bundlebees/`, `hyvv/`, and `orbitdesktop/` under one parent. Run these commands **from `workflow/`**. The scripts resolve the other repos relative to this checkout. No credentials or remote service configuration are needed. Use Linux, Git, an active Python test environment with the projects' test dependencies, and private scratch outside the source trees.

```sh
python3 -B contrib/core-review/check_rails_delivery.py
python3 -B contrib/core-review/test_core_usage_roundtrip.py
python3 -B contrib/core-review/rehearse_m2.py
```

The inventory checks leased files and vendor bytes; the handoff sends a synthetic terminal receipt through Hyvv, Workflow, BundleBees, Orbit and back to the collector. The M2 rehearsal starts a loopback registry and uses temporary file-only Git fixtures. A red/green reference edit and refusal checks do not dispatch or authorize a job.

For the Rails package suites, provide Node >=22.12 and matching installed native dependencies in Orbit, plus local Chromium (`CHROMIUM_EXECUTABLE` or a compatible `PLAYWRIGHT_BROWSERS_PATH`). `pytest` must be installed in the active Python environment, not only in the user site. Build fresh browser assets and use the same build for both browser tests:

```sh
python3 -I -m pytest --version
scratch=$(mktemp -d "${TMPDIR:-/var/tmp}/core-rails.XXXXXXXX") || exit 1
export TMPDIR="$scratch"
export RAILS_R18_BROWSER_DIST="$scratch/dist" ORBIT_RAILS_TEST_DIST="$scratch/dist"
(cd ../orbitdesktop && npm run build -- --dest "$scratch/dist") &&
  python3 -B contrib/core-review/test_rails_working_trees.py
```

The package runner exits nonzero for failed checks or skipped Python packet cases. For release qualification, run [`scripts/rails_tuple.py`](../../scripts/rails_tuple.py) against four fresh checkouts and an external JSON object containing their four full Git SHAs. It provisions the browser build and records required test names, JUnit counts, tool versions, handoffs and checksums. See [R18 rollout](../../specs/rails-rollout.md) for the browser/CLI identity assertion. For Orbit's separate **full** `npm run check`, use the [offline container recipe](orbit-check/README.md).

## Known results and open gates

| Check | Advisory result |
|---|---|
| Publication smoke | All 22 packages inventoried, no vendor drift. Replayed terminal usage produced one ledger row, one request and unknown cost. M2 rehearsal passed: four expected seed failures, four reference passes, zero attempts, operator decision pending. |
| Publication Rails package run | With a fresh Orbit build and isolated pytest environment, all **5 R18 cases** and the separate Orbit browser check passed. The aggregate command still exited 1: the BundleBees ten-writer ledger test hit a SQLite lock during initialization. That test passed on an immediate standalone rerun. Repeat the aggregate command at the PR heads before relying on it. |
| Linux buildout suites | Workflow: 1,040 passed, 5 skipped. Hyvv: 516 passed, 6 skipped. These are earlier working-tree runs; Windows is a separate gate. |
| BundleBees broad suite | Earlier host run: 2,025 passed, 121 failed, 268 skipped. Later offline rerun: 73 of those 121 passed; 47 still need a strong sandbox and one needs Python 3.12. Use the pinned-source instructions in the BundleBees README on an approved isolated runner; keep its production isolation checks enabled. |
| Orbit broad suite | The follow-up container passed (1,486 desktop + 78 IRC). A later buildout snapshot had 1,527 desktop passes, **2 failures**, 18 skips; both failures needed a missing historical Git fixture tree. The runner now includes the whole schema-11 fixture tree. Publication preflight: **13/13** focused tests and **78/78** IRC passed. Preflight does not establish a full-suite pass for the PR tree. |
