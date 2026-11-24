#!/usr/bin/env python3
"""Run the miniature reference workflow.

Usage (from the repository root):

    python3 reference/run_demo.py
    make -C reference demo

By default it runs the contract-first, test-first loop of docs/16 (ACDD
contracts, RED on the baseline plus approved tests, GREEN, REFACTOR,
integration and an acceptance report). --legacy runs the original
lease-and-verify demo. The demo is offline. It needs only Python 3 and git. It writes a throwaway
run directory (default: a temp folder, or --out DIR) and prints a summary.
--out must be new or empty; --force replaces only an earlier demo run (one
that carries the demo's marker file). Lease fingerprints are SHA-256 teaching
stand-ins, not a security control; see bundlebees for HMAC-signed leases.
Exit status is 0 only when both in-scope workers are accepted, the
out-of-scope worker is rejected, and the combined test suite passes.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# Allow `python3 reference/run_demo.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow.lifecycle import run_acdd  # noqa: E402
from workflow.orchestrator import UnsafeOutputDir, run  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline reference workflow demo.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Run directory. Must be new or empty; a non-empty folder is refused "
            "unless --force is given and it holds this demo's marker file. "
            "Default: a fresh temp directory."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an earlier demo run in --out (only if it has the demo marker file).",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Run the original lease-and-verify demo without ACDD contracts or TDD evidence.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="When using the default temp directory, do not delete it on success.",
    )
    return parser.parse_args(argv)


def format_summary(result: dict) -> str:
    lines = [
        "Reference workflow demo",
        f"  source_rev:     {result['source_rev']}",
        f"  accepted:       {', '.join(result['accepted']) or '(none)'}",
        f"  rejected:",
    ]
    for task_id, reason in result["rejected"].items():
        lines.append(f"    - {task_id}: {reason}")
    integ = result["integration"]
    lines.append(f"  integration:    {'passed' if integ.get('passed') else 'FAILED'} ({integ.get('reason')})")
    if integ.get("integration_rev"):
        lines.append(f"  integration_rev:{integ['integration_rev']}")
    metrics = result["metrics"]
    lines.extend(
        [
            "  metrics:",
            f"    cost_per_accepted_change:      {metrics['cost_per_accepted_change']}",
            f"    first_pass_verification_rate:  {metrics['first_pass_verification_rate']}",
            f"    human_interventions:           {metrics['human_interventions']}",
            f"    plan_to_accepted_seconds:      {metrics['plan_to_accepted_seconds']}",
            f"    regression_escapes:            {metrics['regression_escapes']}",
            f"    failed_worker_recovery:        {json.dumps(metrics['failed_worker_recovery'], sort_keys=True)}",
            f"  artifacts:      {result['run_dir']}",
            f"  metrics log:    {result['metrics_path']}",
            f"  result:         {'OK' if result['ok'] else 'FAILED'}",
        ]
    )
    return "\n".join(lines) + "\n"


def format_acdd_summary(result: dict) -> str:
    lines = [
        "Reference workflow demo (contract-first, test-first)",
        f"  source_rev:     {result['source_rev']}",
        f"  accepted:       {', '.join(result['accepted']) or '(none)'}",
        "  rejected at contract review:",
    ]
    lines += [f"    - {k}: {v}" for k, v in result["rejected_contracts"].items()]
    lines.append("  rejected at verification:")
    lines += [f"    - {k}: {v}" for k, v in result["rejected"].items()]
    lines.append("  evidence:")
    for cid, rep in result["reports"].items():
        phases = ", ".join(f"{p} {'not run' if s == 'unrun' else s}" for p, s in rep["phases"].items())
        lines.append(f"    - {cid}: {phases}; test-first {'yes' if rep['test_first'] else 'no'}; accepted {'yes' if rep['accepted'] else 'no'}")
    integ = result["integration"]
    lines += [
        f"  integration:    {'passed' if integ.get('passed') else 'FAILED'} ({integ.get('reason')})",
        f"  evidence:       {'HMAC-signed with a demo key in keys/ (teaching)' if result.get('evidence_signed') else 'unsigned'}",
        f"  sandbox:        {'bwrap (no network, private /tmp, home hidden)' if result.get('sandbox') == 'bwrap' else 'none (bwrap not available; runs are not sandboxed)'}",
        "  workers:        scripted (no model); reviewer: scripted (teaching)",
        f"  acceptance:     {result['acceptance_path']}",
        f"  artifacts:      {result['run_dir']}",
        f"  result:         {'OK' if result['ok'] else 'FAILED'}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tmp: tempfile.TemporaryDirectory | None = None
    if args.out is None:
        tmp = tempfile.TemporaryDirectory(prefix="workflow-reference-")
        out = Path(tmp.name) / "run"
    else:
        out = args.out
    try:
        try:
            result = run(out, force=args.force) if args.legacy else run_acdd(out, force=args.force)
        except UnsafeOutputDir as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        sys.stdout.write(format_summary(result) if args.legacy else format_acdd_summary(result))
        return 0 if result["ok"] else 1
    finally:
        if tmp is not None and not args.keep:
            tmp.cleanup()
        elif tmp is not None:
            # Persist the run dir by not cleaning the TemporaryDirectory.
            sys.stdout.write(f"  kept temp dir: {tmp.name}\n")
            tmp._finalizer.detach()  # noqa: SLF001 — keep the dir when --keep is set


if __name__ == "__main__":
    sys.exit(main())
