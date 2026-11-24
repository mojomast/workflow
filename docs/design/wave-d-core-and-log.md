# Wave D design: one core, one log, one loop

Status: **accepted as design** (Kyle, chat t1650u). Design only. Wave D of the Nov 24 next-level review ([rizzstack #17](https://github.com/mojomast/rizzstack/pull/17)). Absorbs `NEXT.md` W4-4 and W1-7. Owner decisions taken: delete `pc-launcher/` and `server/checkpoints.mjs`; move the trial harness to `contrib/trial` and the other unwired bundlebees modules to `contrib/`; decide `verify_workers` after its shadow run.

## Why workflow owns this

workflow already carries the Rails spec (`specs/rizzstack-rails-spec.md`, `schemas/rails/`) and the
cross-repo schemas, and the other repos vendor from a pinned source with a
`rizzstack.vendor-manifest/1` (see `hyvv/contrib/rizzstack_rails/vendor-manifest.json`). A shared
core library is the same kind of artifact, so it is specified and published here and vendored by
hyvv, bundlebees and orbitdesktop the same way.

## Problem (counts from the review, re-checked on main 24 Nov)

- Helpers rewritten many times: ~50 `os.replace` atomic writers in ~40 bundlebees modules, 23
  `flock` sites, 13 canonical-JSON hashers, 12 git runners, two timestamp formats (`Z` and `+00:00`).
- Canonical JSON disagrees on `ensure_ascii` (hyvv `launcher.py:259`, `reference.py:92` use False;
  `rizzstack_rails/contracts.py:96` and bundlebees `tdd.py:685` use True), so digests of non-ASCII
  payloads differ between repos. Wave C's ticket digest needs one form.
- About 44 secret-scrubber definitions with 12 regex tables; the minimum `sk-` key length ranges
  from 4 to 20 characters.
- Five hash-chained logs: `rizzstack_rails`, uirizz `gate.py`, orbitdesktop `host-audit.mjs`,
  bundlebees `metrics.py`, workflow reference `tdd.py`.
- Four control loops polling state files: the scout, the beat sweep, the gate watcher and the scout
  hook.
- ~6,000 lines with no production caller in bundlebees (nine modules), the 1,003-line legacy
  `pc-launcher/launcher.py` and the zero-importer `server/checkpoints.mjs` in orbitdesktop.
- Git calls without timeouts: wave A slice A8 fixes `integrate_job._git`; the other ~54 git call
  sites move to the core git runner here.

## Decision (proposed)

1. **`rizzstack_core`** (Python; a small JS twin for Orbit and the control plane), vendored with a
   manifest and a CI drift check, offering:
   - `atomic_write_json` / `atomic_write_text` (fsync, `os.replace`, mode bits)
   - `locked(path)` (flock, with a timeout)
   - `canonical_json` = RFC 8785 JCS, plus `sha256_jcs`
   - `scrub(text)`, with gitleaks' rules as the shared source of patterns
   - `git(args, cwd, timeout_s)` (bounded and scrubbed env)
   - `utc_now()` and one timestamp format (`Z`)
   The vendor drift check replaces W4-4's slop-lint-specific refresh check and covers every
   vendored package.
2. **Rails is the only log.** Attempts, verdicts, board moves and approvals are Rails events. The
   uirizz audit chain and Orbit's host audit become Rails event streams; bundlebees metrics read
   from Rails instead of keeping their own chain.
3. **One driver.** The scout, the beat sweep, the gate watcher and the scout hook fold into one
   driver that reads a Rails cursor and runs each duty when its input changes, so no duty polls
   files.
4. **Unwired code out.** Move `trial_harness` and `trial_simulated_driver` to bundlebees
   `contrib/trial`; wire `verify_workers` (the shadow-mode bee) or delete it; delete or move the
   rest after the owner decides. Delete orbitdesktop `pc-launcher/` (W1-7) and `server/checkpoints.mjs`.

## Slices (each RED first; migration order)

| Slice | What | Notes |
|---|---|---|
| D1 | `rizzstack_core` package + vendor manifest + drift check | no callers yet |
| D2 | canonical JSON switch, with a digest-compatibility window (accept old and new for one release) | prerequisite for wave C |
| D3 | git runner adoption in bundlebees (the ~54 sites), one module at a time | mechanical |
| D4 | atomic writer / lock adoption | mechanical |
| D5 | Rails event emission next to today's files (dual write) | no behaviour change |
| D6 | the one driver, behind a flag; the old loops stay until D6 runs a week clean | owner gate to switch |
| D7 | deletions and moves of unwired code | owner decision |

## Exit

One control loop; one implementation of each helper (a CI grep proves no new copies).

## Decisions for the owner

- Delete or move to `contrib/` the nine unwired bundlebees modules, `pc-launcher/` and
  `server/checkpoints.mjs`.
- Whether the JS twin lives in workflow or in orbitdesktop.
