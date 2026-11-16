# Quickstart: contracts profile

Protocol only. Author and check ACDD contracts, lint TDD evidence and run the reference demo — all
offline, no workers, no UI, no services. Manifest: [../../profiles/contracts.json](../../profiles/contracts.json).

## 1. Clone and run the reference demo

```bash
git clone https://github.com/mojomast/workflow
cd workflow
python3 reference/run_demo.py --out /tmp/acdd-demo
python3 reference/check_schemas.py /tmp/acdd-demo
python3 -m unittest discover -s reference/tests -v
```

`check_schemas.py` needs `jsonschema`:

```bash
python3 -m pip install --quiet jsonschema==4.23.0
```

(Commands as run by the CI reference leg; see `contrib/bee-ci/jobs/workflow.yaml` and
`.github/workflows/ci.yml` in this checkout.)

## 2. Run the checkers

```bash
# acdd-lint: tests, then lint the checked-in build evidence
(cd tools/acdd-lint && python3 -m unittest discover -s tests -t . -v)
(cd tools/acdd-lint && python3 -m acdd_lint ../../evidence/2026-11-12-acdd-build)

# project-state: the parking-contract checker
python3 -m unittest discover -s tools/project-state/tests -t tools/project-state -v

# observability envelope validation
python3 -m unittest discover -s observability/tests -t . -v
```

## 3. Author a contract

Start from `templates/CONTRACT.md` and the worked example in `templates/contract.example.json`, validate
the draft against `schemas/acdd-contract.schema.json` (same checker as above), freeze it by hash before
work starts, and record RED, then GREEN, then REFACTOR evidence per `schemas/tdd-evidence.schema.json`.
The practice is chapter 16 of the docs; the portable loop is chapter 9.

## 4. Optional: the offline cold-start acceptance

This step reaches out to clone bundlebees; everything above is fully offline.

```bash
python3 -m pip install --quiet pytest
ACCEPTANCE_MODE=local acceptance/cold_start.sh /tmp/acceptance-out
```

Requirements: git, python3, and bubblewrap or firejail on the host (docker also works with
`ACCEPTANCE_MODE=docker`). The output folder must be new or empty. See `acceptance/README.md`.

## What this profile cannot do

- No dispatch, no workers, no verify loop — that needs the orchestrator profile.
- The parked-project checker is advisory: no layer enforces a parked state yet.
- The acceptance step exercises the real bundlebees verify sandbox, but its ACDD step reports UNRUN
  unless bundlebees is ACDD-capable (that work is on a branch under review, not main).
