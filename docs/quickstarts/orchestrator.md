# Quickstart: orchestrator profile

Dispatch, verify, integrate, recover, report. Bundlebees plus its two pinned protocol checkouts
(workflow and hyvv); Orbit is optional as the control surface. Manifest:
[../../profiles/orchestrator.json](../../profiles/orchestrator.json).

## 1. Clone the executor and pin its two checkouts

Bundlebees main refuses to run its mandatory suite without both pinned checkouts — that is deliberate
(fail closed), and it is gap G2 in the audit.

```bash
git clone https://github.com/mojomast/bundlebees
git clone https://github.com/mojomast/workflow workflow-pinned
git clone https://github.com/mojomast/hyvv hyvv-pinned
git -C workflow-pinned checkout 070b6c10bdfa3e9d31b84cc83a2d9d701222082f
git -C hyvv-pinned checkout 5bee1a870ffe32ee91c6a70b7be807eaa8400801
```

(Pins as recorded in chapter 23, §4 of the docs; `profiles/repos.json` carries the same values with
their citations.)

## 2. Run the mandatory suite with the pins required

```bash
cd bundlebees
WORKFLOW_SRC=../workflow-pinned REQUIRE_WORKFLOW=1 \
HYVV_SRC=../hyvv-pinned REQUIRE_HYVV=1 \
python -m pytest -rs
python scripts/measure_schemas.py
```

If either checkout is missing or at the wrong revision with the `REQUIRE_*` variables set, the run
fails instead of skipping. That is the contract.

## 3. Sandbox for verify

`hermes bundlebees verify` runs worker tests in a disposable unprivileged environment: bubblewrap is
preferred, firejail second, and `unshare` is never auto-selected. With no backend it fails closed
(`sandbox_unavailable`); the only escape is the labelled-unsafe local override, which you should use
only on a disposable single-user machine. `hermes bundlebees doctor` reports which backend is in
effect. See chapter 13, §1.

## 4. Optional: the offline end-to-end acceptance

From a workflow checkout (the harness lives there and clones bundlebees itself):

```bash
python3 -m pip install --quiet pytest
ACCEPTANCE_MODE=local acceptance/cold_start.sh /tmp/acceptance-out
```

It dispatches three parallel briefs through the real dispatch path with signed leases, proves the
verifier rejects a deliberate lease violation, integrates the honest slices and writes an acceptance
artifact. The worker is scripted; the real-adapter launcher path has never been run (gap G7).

## What this profile cannot do

- No merge, push, tag, release or deploy — those stay human-gated, always.
- No exactly-once dispatch guarantee: the launcher has no server-side idempotency; adoption reconciles
  a lost response instead.
- Contract-aware verify (ACDD + TDD evidence) is on a branch under review, not main (gap G9).
- Parked projects are not refused: the hyvv gate is a proposal, not running code (gap G11).
- Without Orbit you drive the loop from the CLI; the default `orbit-loopback` worker backend expects
  the launcher path, or you supply another backend (chapter 13, §6).
