#!/usr/bin/env python3
"""Check a saved hyvv /v1/health response against the SHA a deploy plan named (stdlib only).

DEPLOY-CADENCE (docs/deployment-runbook.md): after every deploy, capture /v1/health
and run

    python3 scripts/check_deploy_receipt.py --health health.json --expect-rev <40-hex> \
        [--expect-version 0.1.18] [--not-before <window start, UTC>]

It prints one rizzstack.deploy-receipt-check/1 JSON record (keep it as deploy
evidence) and exits 0 only when the deployment receipt is present, valid, names the
expected full commit (and version, when given) and was written inside the window.
It reads a file; it never contacts a host.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "rizzstack.deploy-receipt-check/1"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else None


def _receipt_problems(receipt: dict, expect_rev: str, expect_version: str | None,
                      not_before: datetime | None) -> list[str]:
    problems = []
    rev = receipt.get("rev")
    if rev is None:
        problems.append("rev_missing")
    elif rev != expect_rev:
        problems.append("rev_mismatch")
    if expect_version is not None and receipt.get("version") != expect_version:
        problems.append("version_mismatch")
    deployed = _parse_utc(receipt.get("deployed_at"))
    if deployed is None:
        problems.append("deployed_at_missing")
    elif not_before is not None and deployed < not_before:
        problems.append("deployed_before_window")
    return problems


def check(health: Any, expect_rev: str, expect_version: str | None = None,
          not_before: str | None = None) -> dict[str, Any]:
    """The check record for one /v1/health body. Raises ValueError on a bad expectation."""
    if not FULL_SHA.match(expect_rev or ""):
        raise ValueError("--expect-rev must be a full 40-hex commit")
    window = _parse_utc(not_before) if not_before is not None else None
    if not_before is not None and window is None:
        raise ValueError("--not-before must be a zoned timestamp")
    receipt = health.get("deployment_receipt") if isinstance(health, dict) else None
    if not isinstance(health, dict):
        problems = ["not_json_object"]
    elif not isinstance(receipt, dict):
        problems = ["no_receipt"]
    elif receipt.get("status") == "invalid":
        problems = ["receipt_invalid"]
    else:
        problems = _receipt_problems(receipt, expect_rev, expect_version, window)
    receipt = receipt if isinstance(receipt, dict) else {}
    return {
        "schema": SCHEMA,
        "ok": not problems,
        "expected_rev": expect_rev,
        "rev": receipt.get("rev"),
        "version": receipt.get("version"),
        "deployed_at": receipt.get("deployed_at"),
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--health", required=True, type=Path, help="saved /v1/health JSON")
    parser.add_argument("--expect-rev", required=True)
    parser.add_argument("--expect-version")
    parser.add_argument("--not-before")
    args = parser.parse_args(argv)
    try:
        health = json.loads(args.health.read_text(encoding="utf-8"))
        record = check(health, args.expect_rev, args.expect_version, args.not_before)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "problems": [f"unreadable:{type(exc).__name__}"]}))
        return 1
    print(json.dumps(record, sort_keys=True))
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
