# Cold-start acceptance report

**Result: {{RESULT}}** in {{ELAPSED}} s. Accepted integration artifact: `{{ARTIFACT_ACCEPTED}}`.

## Environment

| Key | Value |
|---|---|
{{ENV_ROWS}}
| sandbox backend | {{SANDBOX}} |
| worker backend | {{WORKER_BACKEND}} |
| workflow commit | {{WORKFLOW_REV}} |
| bundlebees commit | {{BUNDLEBEES_REV}} |

## Steps

| # | Step | Result | Detail |
|---|---|---|---|
{{STEP_ROWS}}

## Interventions

Manual interventions during the run: **{{MANUAL_COUNT}}**. Environment workarounds and escape hatches are listed too, so nothing that needed a hand is hidden.

| Kind | What | Why |
|---|---|---|
{{INTERVENTION_ROWS}}

## Metrics (bundlebees summary for the run)

```json
{{METRICS}}
```

## Reviewer notes

- What failed or needed a hand, and why:
- Anything the harness could not check:
- Follow-ups:
