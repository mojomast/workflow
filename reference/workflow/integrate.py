"""Apply accepted patches on a combined branch and run the full suite."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .toy import run_git
from .verify import _run_tests, throwaway_checkout


def integrate_accepted(
    source: Path,
    source_rev: str,
    accepted: list[dict],
) -> dict:
    """accepted items are dicts with task_id and patch."""
    tmp = Path(tempfile.mkdtemp(prefix="integrate-"))
    repo = tmp / "repo"
    try:
        throwaway_checkout(source, source_rev, repo)
        run_git(repo, "config", "user.name", "Reference Integrator")
        run_git(repo, "config", "user.email", "integrator@example.invalid")
        run_git(repo, "config", "commit.gpgsign", "false")
        run_git(repo, "checkout", "-q", "-b", "integration")
        applied = []
        for item in accepted:
            patch_file = tmp / f"{item['task_id']}.patch"
            patch_file.write_text(item["patch"], encoding="utf-8")
            check = run_git(repo, "apply", "--check", str(patch_file), check=False)
            if check.returncode != 0:
                return {
                    "passed": False,
                    "reason": f"accepted patch {item['task_id']} does not apply on the combined branch",
                    "stderr": (check.stderr or "")[-1000:],
                    "applied": applied,
                    "repo": str(repo),
                    "cleanup": str(tmp),
                }
            run_git(repo, "apply", str(patch_file))
            run_git(repo, "add", "-A")
            run_git(repo, "commit", "-q", "-m", f"integrate {item['task_id']}")
            applied.append(item["task_id"])
        tests = _run_tests(repo)
        head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
        result = {
            "passed": tests["passed"],
            "reason": "combined test suite passed" if tests["passed"] else "combined test suite failed",
            "stderr": tests["stderr"],
            "applied": applied,
            "integration_rev": head,
            "baseline": source_rev,
            "worktree": str(repo),
            "cleanup": str(tmp),
        }
        return result
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def cleanup_integration(result: dict) -> None:
    path = result.get("cleanup")
    if path:
        shutil.rmtree(path, ignore_errors=True)
