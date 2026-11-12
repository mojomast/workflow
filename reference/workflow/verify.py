"""Independent verification in a throwaway copy of the toy repo."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .contract import LeaseStore
from .toy import run_git


class VerifyRejected(Exception):
    def __init__(self, reason: str, evidence: dict):
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


def _changed_paths_from_patch(patch: str) -> list[str]:
    paths = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            # diff --git a/foo b/foo
            parts = line.split()
            if len(parts) >= 4 and parts[3].startswith("b/"):
                paths.append(parts[3][2:])
    return paths


def _run_tests(repo: Path, test_paths: list[str] | None = None) -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    args = ["python3", "-m", "unittest", "discover", "-s", "tests", "-q"]
    if test_paths:
        patterns = []
        for item in test_paths:
            name = Path(item).name
            if name not in patterns:
                patterns.append(name)
        # unittest discover accepts one -p; run once per pattern when needed.
        if len(patterns) == 1:
            args.extend(["-p", patterns[0]])
    proc = subprocess.run(
        args,
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return {
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }


def throwaway_checkout(source: Path, source_rev: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--quiet", str(source), str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(dest, "checkout", "-q", source_rev)


def verify_manifest(
    source: Path,
    lease_store: LeaseStore,
    manifest: dict,
    expected_source_rev: str,
) -> dict:
    """Verify one worker result. Leases come only from the coordinator store."""
    task_id = manifest["task_id"]
    lease = lease_store.get(task_id)
    assigned = list(lease["assigned_files"])
    evidence = {
        "task_id": task_id,
        "decision": None,
        "reason": None,
        "assigned_files": assigned,
        "observed_files": [f["path"] for f in manifest.get("observed", {}).get("files", [])],
        "worker_claimed_files": (manifest.get("worker_claims") or {}).get("assigned_files"),
        "source_rev": expected_source_rev,
        "tests": None,
    }

    if lease["source_rev"] != expected_source_rev:
        evidence.update(decision="rejected", reason="lease source_rev does not match coordinator baseline")
        raise VerifyRejected(evidence["reason"], evidence)

    stamped = manifest.get("source_rev")
    if stamped != expected_source_rev:
        evidence.update(decision="rejected", reason="manifest source_rev does not match coordinator baseline")
        raise VerifyRejected(evidence["reason"], evidence)

    patch = manifest.get("patch") or ""
    if not patch.strip():
        evidence.update(decision="rejected", reason="empty patch")
        raise VerifyRejected(evidence["reason"], evidence)

    observed = evidence["observed_files"]
    if not observed:
        evidence.update(decision="rejected", reason="empty file list")
        raise VerifyRejected(evidence["reason"], evidence)

    # Lease is the only source of allowed paths. Worker claims are ignored.
    allowed = set(assigned)
    out_of_scope = sorted(path for path in observed if path not in allowed)
    patch_paths = _changed_paths_from_patch(patch)
    patch_oos = sorted(path for path in patch_paths if path not in allowed)
    if out_of_scope or patch_oos:
        evidence["out_of_scope"] = sorted(set(out_of_scope + patch_oos))
        evidence.update(decision="rejected", reason="patch touches files outside the coordinator lease")
        raise VerifyRejected(evidence["reason"], evidence)

    tmp = Path(tempfile.mkdtemp(prefix=f"verify-{task_id}-"))
    checkout = tmp / "repo"
    try:
        throwaway_checkout(source, expected_source_rev, checkout)
        head = run_git(checkout, "rev-parse", "HEAD").stdout.strip()
        if head != expected_source_rev:
            evidence.update(decision="rejected", reason="throwaway checkout was not at source_rev")
            raise VerifyRejected(evidence["reason"], evidence)
        patch_file = tmp / "change.patch"
        patch_file.write_text(patch, encoding="utf-8")
        check = run_git(checkout, "apply", "--check", str(patch_file), check=False)
        if check.returncode != 0:
            evidence.update(
                decision="rejected",
                reason="patch does not apply",
                apply_stderr=(check.stderr or "")[-1000:],
            )
            raise VerifyRejected(evidence["reason"], evidence)
        run_git(checkout, "apply", str(patch_file))
        # Run only the leased tests when they are in the lease; otherwise the slice files.
        test_files = [p for p in assigned if p.startswith("tests/") and p.endswith(".py")]
        result = _run_tests(checkout, test_files or None)
        evidence["tests"] = {
            "passed": result["passed"],
            "returncode": result["returncode"],
            "stderr": result["stderr"],
        }
        if not result["passed"]:
            evidence.update(decision="rejected", reason="slice tests failed in the throwaway checkout")
            raise VerifyRejected(evidence["reason"], evidence)
        evidence.update(decision="accepted", reason="in-scope patch, baseline matches, slice tests passed")
        return evidence
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
