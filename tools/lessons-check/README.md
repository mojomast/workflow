# lessons-check

A small, standard-library-only, advisory checker that turns recurring review
lessons into deterministic findings. It needs Python 3.12+. It is not wired
into CI; run it by hand and treat its output as a report.

```sh
cd tools/lessons-check
python3 -m lessons_check check PATH...
python3 -m lessons_check check PATH... --report-only
python3 -m lessons_check list
python3 -m unittest discover -s tests -t . -v
```

Directories are walked for `*.json`. Any directory whose name starts with `.`
is skipped, as are `node_modules`, `__pycache__`, `venv` and `.venv`. Symlinked
directories are not followed. A file that cannot be read or parsed as JSON is
skipped rather than fatal.

## Rules

| Rule | Meaning |
|---|---|
| `contract-test-ref` | A `*.contract.json` file whose `acceptance_criteria[].tests` entry has no `::`, so it is not a class-qualified pytest node id. One finding per bad entry. |
| `evidence-absolute-path` | A JSON file under a directory named `evidence` whose string values contain an absolute machine path: a home directory, a workspace directory or a Windows drive path. One finding per file. |
| `brief-may-create` | A JSON file under a directory named `briefs` whose `objective` contains "may create" case-insensitively. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean, or findings only while `--report-only` is set. |
| `1` | Findings were printed. |
| `2` | Usage error, such as a missing or nonexistent path, or an unreadable registry. Always `2`, even with `--report-only`. |

`list` prints `id: summary` for every lesson in the packaged `lessons.json`.
The registry is validated strictly: a malformed, non-list or duplicate-id
registry fails closed with exit `2`.
