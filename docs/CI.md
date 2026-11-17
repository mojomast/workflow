# CI required contexts

The main-branch ruleset requires three status contexts by name:

- `bee-ci/reference`
- `bee-ci/project-state`
- `bee-ci/secret-scan`

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

## Boundaries

- Repository rulesets and branch protection are not configured or modified by
  the workflow.
- The required context names are not changed.
- Named jobs and matrix legs are preserved. The gates only check results;
  they do not re-run tests or scans.
