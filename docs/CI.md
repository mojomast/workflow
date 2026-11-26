# CI required contexts

The main-branch ruleset requires these status contexts by name:

- `ci-gate`
- `bee-ci/reference`
- `bee-ci/project-state`
- `bee-ci/secret-scan`

`ci-gate` is the overall job gate: it passes only when every job in
`.github/workflows/ci.yml` succeeded, including `lease-tamper`. It cannot
report success on its own.

The substantive work in `.github/workflows/ci.yml` keeps its existing job IDs and
check names. Three additional gate jobs carry the required context names and
depend on the substantive jobs, so requiring these contexts does not weaken
coverage or duplicate the work.

## Mapping

| Required context | Gate job ID | Depends on | Substantive coverage behind the gate |
| --- | --- | --- | --- |
| `bee-ci/reference` | `bee-ci-reference` | `reference`, `feature-packet` | Reference demos, schema/evidence/`acdd-lint` checks, feature-packet checks and the single full `pytest -q tests/` sweep. Both jobs must succeed. |
| `bee-ci/project-state` | `bee-ci-project-state` | `project-state` (matrix: `ubuntu-24.04`, `windows-latest`) | Project-state schema tests with jsonschema required. The gate consumes the matrix job's aggregate result, so a failure in either matrix leg fails the required context. |
| `bee-ci/secret-scan` | `bee-ci-secret-scan` | `secret-scan` | Checksum-verified gitleaks 8.21.2 full-history scan (`fetch-depth: 0`). |

The gate job's `name` is the exact required context. The underlying jobs keep
their existing names (`reference demo + tests`, `project-state schemas +
reference checker (<os>)`, `gitleaks`) and remain visible as their own checks.

## Failure propagation

Each gate uses:

```yaml
needs: <substantive job>
if: always()
```

The gate's only step compares `needs.<job>.result` with `success` and exits
non-zero for any other value (`failure`, `cancelled`, `skipped`, and so on). It
does not run the substantive job's commands again and never reports success
unconditionally. For `project-state`, `needs.project-state.result` is the
aggregate over the matrix legs, so a failed or cancelled leg fails
`bee-ci/project-state`.

## Lease/tamper

`lease-tamper` is a required member of `ci-gate`. It classifies the pull
request first: a **slice** is a PR that a frozen lease committed on the base
branch names (by `pull_request`, `branch` or `slice`/`id`); every other
change — including any PR that adds or edits `.rizzstack/leases/**`,
`.rizzstack/contracts/**` or `.rizzstack/lease.json` — is **non-slice** and
passes only with an independent review at its exact head (`APPROVED`, or a
`COMMENTED` review whose first line starts `APPROVE` and names an independent
review). Labels and PR-body lines never select a lease or move the verify
boundary. A lease is usable only when it declares `review.status`
`approved`/`frozen`, a `contract_sha256`, and the matching approved contract
sits at `.rizzstack/contracts/<contract_sha256>.json` on base with the same
`source_rev` and scope lists. A slice is then judged against that lease: any
commit after the verify boundary that touches a file outside
`scope.assigned_files`, or a frozen test in `scope.test_files` /
`scope.prohibited` / `scope.read_only`, fails; a wildcard in
`scope.assigned_files` fails `lease_glob_scope`. A lease that is not frozen,
or whose contract hash is missing/unapproved/mismatched, fails closed. The
rule applies to every author, including the coordinator and triage lanes;
triage lanes have no test edit rights. Full behavior and the failure text:
[`32-lease-tamper-gate.md`](32-lease-tamper-gate.md). The bypass regression
suite is `.github/scripts/lease_tamper_poc.py` (all five cases must exit 1).

## Boundaries

- Repository rulesets and branch protection are not configured or modified by
  the workflow.
- The required context names are not changed.
- Named jobs and matrix legs are preserved. The gates only check results;
  they do not re-run tests or scans.
