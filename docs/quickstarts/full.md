# Quickstart: full profile

All four elements at their recorded revisions: protocol (workflow), worker host (hyvv), execution
system (bundlebees), control surface (orbitdesktop). Manifest:
[../../profiles/full.json](../../profiles/full.json). This is the maintainer-shaped stack — it is **not**
a one-command newcomer install, and the audit says so honestly (gap G8).

## 0. What you need

- Python 3.12, git, `uv` (for hyvv), pytest and jsonschema.
- bubblewrap or firejail for the sandboxed verify (docker also works for the acceptance run).
- Node 22 and a chromium-capable environment only if you run the Orbit browser-e2e leg.

## 1. Clone all four, pin the two protocol checkouts

```bash
git clone https://github.com/mojomast/workflow
git clone https://github.com/mojomast/hyvv
git clone https://github.com/mojomast/bundlebees
git clone https://github.com/mojomast/orbitdesktop
git -C workflow checkout 070b6c10bdfa3e9d31b84cc83a2d9d701222082f
git -C hyvv checkout 5bee1a870ffe32ee91c6a70b7be807eaa8400801
```

The pins are the revisions the bundlebees CI requires (chapter 23, §4). The executor refuses to run
its mandatory suite without them.

## 2. Protocol layer (workflow)

```bash
cd workflow
python3 reference/run_demo.py --out /tmp/acdd-demo
python3 reference/check_schemas.py /tmp/acdd-demo
python3 -m unittest discover -s reference/tests -v
(cd tools/acdd-lint && python3 -m unittest discover -s tests -t . -v)
python3 -m unittest discover -s tools/project-state/tests -t tools/project-state -v
```

## 3. Worker host (hyvv)

```bash
cd ../hyvv
uv sync --frozen --no-dev || uv sync --no-dev
uv run python -m unittest discover -s tests -v
uv run python -m contract -v
```

## 4. Execution system (bundlebees, pinned to both checkouts)

```bash
cd ../bundlebees
WORKFLOW_SRC=../workflow REQUIRE_WORKFLOW=1 \
HYVV_SRC=../hyvv REQUIRE_HYVV=1 \
python -m pytest -rs
python scripts/measure_schemas.py
```

## 5. Control surface (orbitdesktop)

```bash
cd ../orbitdesktop
git log --oneline -1
```

Then follow the checkout's own QUICKSTART and CONFIG documents. The one-command first-run path is in
progress upstream (chapter 15); this umbrella will not quote install commands it cannot verify.

## 6. Optional: the offline end-to-end acceptance

From the workflow checkout:

```bash
cd ../workflow
python3 -m pip install --quiet pytest
ACCEPTANCE_MODE=local acceptance/cold_start.sh /tmp/acceptance-out
```

This is the only proven end-to-end loop today: real dispatch path, signed leases, sandboxed verify that
must reject a lease violation, integration and an acceptance artifact — with a scripted worker. The
real-adapter path through the launcher has never been run (gap G7), and Orbit's UI is not exercised by
it (acceptance README).

## What the full profile still cannot do

- No merge, push, tag, release, deploy or budget-widening without the human owner's explicit yes; a
  relayed approval is not approval.
- Contract-aware verify is branch-only upstream (gap G9); the real-model recovery and wake-up paths are
  supervised-only and never run in CI.
- No one-command stranger install yet (gap G8); bundlebees hardening is untagged on main.
- Parked projects are not refused anywhere yet (gap G11); hyvv provisioning is branch-only and
  Windows-unproven (gap G10).
