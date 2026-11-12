# Acceptance runs

| Date (America/Toronto) | Where | Harness | bundlebees | Result | Manual steps | Report |
|---|---|---|---|---|---|---|
| Nov 12, 2026 | Author's box, clean temp HOME + venv (no docker), bubblewrap sandbox | `183813f` | `509649b` (main) | PASS, 10/10 steps | 0 (1 environment workaround: no container) | [first run](2026-11-12-first-run/REPORT.md) |

CI runs the same script on every pull request (`acceptance-light` job) on a fresh GitHub `ubuntu-24.04` runner; its report is printed in the job log. Add a row here for each run on a new machine, especially one by someone other than the author.
