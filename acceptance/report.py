#!/usr/bin/env python3
"""Fill REPORT_TEMPLATE.md from a harness output directory (stdlib only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--template", required=True)
    parser.add_argument("--env", action="append", default=[], help="key=value lines for the environment table")
    args = parser.parse_args()
    out = Path(args.out)
    summary = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {"ok": False, "steps": [], "interventions": []}
    artifact = json.loads((out / "acceptance-artifact.json").read_text()) if (out / "acceptance-artifact.json").exists() else {}

    env_rows = "\n".join(f"| {k} | {v} |" for k, _, v in (e.partition("=") for e in args.env)) or "| (none) | |"
    step_rows = "\n".join(
        f"| {i} | `{s['step']}` | {'PASS' if s['ok'] else 'FAIL'} | {s.get('summary') or ''} |"
        for i, s in enumerate(summary["steps"], 1)
    ) or "| | | | harness did not record steps (see harness-error.txt) |"
    unrun = summary.get("unrun") or []
    if unrun:
        step_rows += "\n" + "\n".join(f"| - | `{u['step']}` | UNRUN | {u['why']} (not counted as passed) |" for u in unrun)
    interventions = summary.get("interventions") or []
    int_rows = "\n".join(f"| {i['kind']} | {i['what']} | {i['why']} |" for i in interventions) or "| none | | |"
    metrics = artifact.get("metrics") or {}
    text = Path(args.template).read_text(encoding="utf-8")
    values = {
        "RESULT": "PASS" if summary.get("ok") else "FAIL",
        "ELAPSED": str(summary.get("elapsed_s", "?")),
        "ENV_ROWS": env_rows,
        "STEP_ROWS": step_rows,
        "INTERVENTION_ROWS": int_rows,
        "MANUAL_COUNT": str(summary.get("manual_interventions", 0)),
        "SANDBOX": str(artifact.get("sandbox", "?")),
        "WORKER_BACKEND": str(artifact.get("worker_backend", "?")),
        "WORKFLOW_REV": str(artifact.get("workflow_rev", "?")),
        "BUNDLEBEES_REV": str(artifact.get("bundlebees_rev", "?")),
        "ARTIFACT_ACCEPTED": str(artifact.get("accepted", False)).lower(),
        "METRICS": json.dumps(metrics, indent=2, sort_keys=True),
    }
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    (out / "REPORT.md").write_text(text, encoding="utf-8")
    print(out / "REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
