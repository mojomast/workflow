"""Build the fork-safe PR summary comment body from a PR's changed files.

Only paths reported as changed by the pull request are considered, and every
path is treated as untrusted input: absolute paths, backslashes, parent
segments, symlinks and non-regular files are ignored. Nothing from the PR is
executed; the only renderer is :func:`pr_summary.render_pr_summary`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pr_summary

MARKER = "<!-- workflow-pr-summary:v1 -->"
MAX_DIRECTORIES = 5
MAX_BODY_BYTES = 60000
TRUNCATED = "(truncated)"
CONTRACT_SUFFIX = ".contract.json"
PR_NUMBER_RE = re.compile(r"[0-9]{1,9}")


def _safe_relpath(raw: object) -> str | None:
    """Return a POSIX repo-relative path, or None when it is unsafe."""
    if not isinstance(raw, str) or not raw:
        return None
    if raw.startswith("/") or "\\" in raw:
        return None
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return raw


def _regular_file(root: Path, root_real: Path, rel: str) -> bool:
    candidate = root / rel
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return False
        real = candidate.resolve(strict=True)
    except OSError:
        return False
    if real != root_real and root_real not in real.parents:
        return False
    return True


def _classify(rel: str) -> tuple[str, str, str] | None:
    """Return ``(kind, directory, id)`` for a contract or evidence file name, else None."""
    name = rel.rsplit("/", 1)[-1]
    directory = rel.rsplit("/", 1)[0] if "/" in rel else ""
    if name.endswith(CONTRACT_SUFFIX):
        stem = name[: -len(CONTRACT_SUFFIX)]
        return ("contract", directory, stem) if stem else None
    for phase in pr_summary.PHASES:
        suffix = f".{phase}.json"
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            return ("evidence", directory, stem) if stem else None
    return None


def _usable_entries(changed_files: object, root: Path, root_real: Path) -> list[str]:
    try:
        entries = list(changed_files)
    except TypeError:
        return []
    usable = []
    for raw in entries:
        rel = _safe_relpath(raw)
        if rel is not None and _regular_file(root, root_real, rel):
            usable.append(rel)
    return usable


def _qualifying_directories(changed_files: object, root: Path) -> list[str]:
    try:
        root_real = root.resolve(strict=True)
    except OSError:
        return []
    if not root_real.is_dir():
        return []
    found: dict[str, dict[str, set[str]]] = {"contract": {}, "evidence": {}}
    for rel in _usable_entries(changed_files, root, root_real):
        item = _classify(rel)
        if item is not None:
            kind, directory, stem = item
            found[kind].setdefault(directory, set()).add(stem)
    qualified = [
        directory
        for directory, ids in found["contract"].items()
        if ids & found["evidence"].get(directory, set())
    ]
    return sorted(qualified)[:MAX_DIRECTORIES]


def _truncate(body: str) -> str:
    data = body.encode("utf-8")
    if len(data) <= MAX_BODY_BYTES:
        return body
    tail = "\n" + TRUNCATED
    budget = MAX_BODY_BYTES - len(tail.encode("utf-8"))
    if budget < 0:
        budget = 0
    head = data[:budget]
    while head:
        try:
            decoded = head.decode("utf-8")
            break
        except UnicodeDecodeError:
            head = head[:-1]
    else:
        decoded = ""
    return decoded + tail


def build_comment(changed_files: object, root: object) -> str | None:
    """Return the comment body for a PR, or None when nothing qualifies."""
    root_path = Path(root)
    directories = _qualifying_directories(changed_files, root_path)
    if not directories:
        return None
    sections = [
        pr_summary.render_pr_summary(root_path / directory)
        for directory in directories
    ]
    body = MARKER + "\n" + "\n\n---\n\n".join(sections)
    return _truncate(body)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--changed-files", required=True)
    parser.add_argument("--pr", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if PR_NUMBER_RE.fullmatch(args.pr) is None:
        return 2
    try:
        text = Path(args.changed_files).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 2
    body = build_comment(text.splitlines(), Path(args.root))
    if body is None:
        return 0
    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "comment.md").write_text(body, encoding="utf-8")
        (out / "pr-number.txt").write_text(args.pr + "\n", encoding="utf-8")
    except OSError:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
