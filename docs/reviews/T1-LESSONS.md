VERDICT: APPROVE

## Findings

1. minor (non-blocking) — `.github/workflows/ci.yml:405` — the summary's "finding count" is `wc -l` over the human-readable report rather than a count produced by `lessons_check`. Today the CLI prints exactly one line per finding (verified: 6 lines for 6 findings), so the summary is correct; a future multi-line finding or path would make the count drift. Fix: add a machine-readable count (for example a `--json` or `--count` mode) and use it, or make and test the one-line output contract explicit.

No blocker or major findings.

## Acceptance criteria

- Job exists with `name: lessons-check (advisory)`, before `ci-gate`, `runs-on: ubuntu-24.04`, `timeout-minutes: 10`, `permissions: contents: read`: met (`.github/workflows/ci.yml:383-415`).
- Same pinned `actions/checkout` (with `persist-credentials: false`) and `actions/setup-python` (Python 3.12) as `hermes-bees-python`: met.
- Unit test step runs `python3 -m unittest discover -s tests -t . -v` in `tools/lessons-check`: met; 12 tests pass.
- Report step runs the required `python3 -m lessons_check check ../.. --report-only`, appends the `## lessons-check (advisory)` heading, the finding count and a fenced findings block to `$GITHUB_STEP_SUMMARY`, and echoes the file: met; a local simulation wrote `Findings: 6`.
- Exit status propagates: there is no `|| true`, no `set +e` and no `continue-on-error`; with the runner's default `bash -e -o pipefail`, a usage error exits 2 before the summary is written (simulated: exit 2), while findings exit 0: met.
- `ci-gate` needs `lessons-check`: met; `check_ci_gate.py` exits 0, and a temporary copy with that need removed exits 1.
- README: met; it now says CI runs the advisory job, findings in the summary never block, and a usage error or failing unit test does.
- CHANGELOG: exactly one matching bullet (`CHANGELOG.md:5`): met.
- No existing job, gate, sandbox, check or test was weakened, skipped or swallowed; the new job only adds a job and a `ci-gate` dependency, and the stated changed files contain no test changes: met.
- No secrets, hostnames, IPs or absolute paths were introduced: met.

## Test commands run

- `timeout 900 python3 -m pytest -q -p no:cacheprovider tests/test_ci_lessons_check_job.py` -> exit 1: `No module named pytest` (pytest is not installed in this environment).
- `timeout 900 python3 -m unittest -v tests.test_ci_lessons_check_job` -> exit 0, 5 tests pass (fallback for the same approved test).
- `timeout 120 python3 .github/scripts/check_ci_gate.py .github/workflows/ci.yml` -> exit 0.
- `cd tools/lessons-check && timeout 300 python3 -m unittest discover -s tests -t . -v` -> exit 0, 12 tests pass.
- `timeout 2400 python3 -m pytest -q -p no:cacheprovider tests` -> exit 1: `No module named pytest` (the exact full-suite command is not runnable here).
- `timeout 2400 python3 -m unittest discover -s tests -t .` -> exit 1: 621 tests ran, 28 skipped, 15 module import errors all from missing `pytest`/`jsonschema`, 0 assertion failures.
- Local simulation of the report block with `bash --noprofile --norc -eo pipefail` in `tools/lessons-check` -> exit 0, summary `Findings: 6`; the same block with a nonexistent path -> exit 2 and no summary written.
- `timeout 120 python3 .github/scripts/check_ci_gate.py` against a temporary copy with `- lessons-check` removed -> exit 1 (`does not need: lessons-check`).

## Environment note

The checkout is a single squashed commit (`9c79330`, message `base b7f03c9...`); the stated base `ae9c080...` and head `b7f03c9...` objects are not present, so the literal base..head diff cannot be reconstructed locally. I reviewed every line of the stated changed files at the checkout and the approved test directly. `pytest` and `jsonschema` are absent, which is why the exact full-suite command cannot run; the unittest fallback shows no assertion failures, and every import error is a missing dependency rather than a PR regression.
