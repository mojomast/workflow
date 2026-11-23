"""Command line interface for lessons-check."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lessons_check import registry, runner


class UsageError(Exception):
    """Raised for an unusable command line or input path."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lessons-check",
        description="Report recurring review lessons as deterministic findings.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="scan JSON records for lesson findings")
    check.add_argument("paths", nargs="+", metavar="PATH")
    check.add_argument(
        "--report-only",
        action="store_true",
        help="print findings but exit 0; usage errors still exit 2",
    )

    commands.add_parser("list", help="list the packaged lessons")
    return parser


def _validate(paths: list[str]) -> None:
    for item in paths:
        path = Path(item)
        if not path.exists():
            raise UsageError(f"path does not exist: {item}")
        if not (path.is_dir() or path.is_file()):
            raise UsageError(f"path is not a file or directory: {item}")


def _check(args: argparse.Namespace) -> int:
    _validate(args.paths)
    findings = runner.check(args.paths)
    for finding in findings:
        print(f"{finding.path}: {finding.rule}: {finding.message}")
    if findings and not args.report_only:
        return 1
    return 0


def _list() -> int:
    try:
        lessons = registry.load()
    except registry.RegistryError as exc:
        print(f"lessons-check: error: {exc}", file=sys.stderr)
        return 2
    for lesson in lessons:
        print(f"{lesson['id']}: {lesson['summary']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run lessons-check and return 0 (clean), 1 (findings) or 2 (usage)."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        if args.command == "check":
            return _check(args)
        return _list()
    except UsageError as exc:
        print(f"lessons-check: error: {exc}", file=sys.stderr)
        return 2
