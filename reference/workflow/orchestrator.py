"""Coordinator: contracts, leases, dispatch of scripted workers, verify, integrate.

Teaching code. The lease fingerprints written here are plain SHA-256 hashes
stored next to the data (see :mod:`workflow.contract`); anyone who can edit the
store can recompute them. Real deployments should use bundlebees' HMAC-signed
coordinator leases instead.

Output safety: :func:`prepare_run_dir` never deletes a folder the demo did not
create. A non-empty ``--out`` is refused unless ``force=True`` *and* the folder
holds the demo's own marker file; ``/``, home, the repository root, the
current directory and its parents, and symlinked targets are always refused.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .contract import LeaseStore, lease_record, validate_brief
from .integrate import cleanup_integration, integrate_accepted
from .metrics import MetricsLog
from .packets import write_handoff, write_return
from .toy import create_toy_repo
from .verify import VerifyRejected, verify_manifest
from .workers import work_labels, work_out_of_scope, work_pricing


TASKS = [
    {
        "task_id": "W1-pricing",
        "title": "Add apply_tax to the pricing module",
        "assigned_files": ["shop/pricing.py", "tests/test_pricing.py"],
        "acceptance": [
            "apply_tax(1000, 10) == 1100",
            "apply_tax rejects a negative rate",
            "existing discount tests still pass",
        ],
        "user_visible": "Callers can add a tax rate to a price in cents.",
        "worker": "pricing",
    },
    {
        "task_id": "W2-labels",
        "title": "Add format_receipt_line to the labels module",
        "assigned_files": ["shop/labels.py", "tests/test_labels.py"],
        "acceptance": [
            "format_receipt_line('Tea', 199) == 'Tea: $1.99'",
            "blank names are rejected",
            "existing format_price tests still pass",
        ],
        "user_visible": "A receipt line can be formatted as 'name: $x.yy'.",
        "worker": "labels",
    },
    {
        "task_id": "W3-out-of-scope",
        "title": "Deliberate out-of-scope attempt (must be rejected)",
        "assigned_files": ["shop/pricing.py"],
        "acceptance": [
            "This worker is expected to be rejected for crossing its lease.",
        ],
        "user_visible": "No change: this attempt is a negative test of verification.",
        "worker": "out_of_scope",
    },
]


#: Marker file the demo writes into every run directory it owns.
MARKER_NAME = ".workflow-reference-demo"
MARKER_TEXT = "workflow reference demo run directory; safe to replace with --force\n"
REPO_ROOT = Path(__file__).resolve().parents[2]


class UnsafeOutputDir(ValueError):
    """The requested run directory is refused to protect unrelated files."""


def _is_same_or_parent(candidate: Path, path: Path) -> bool:
    """True when *candidate* is *path* or one of its ancestors."""
    return candidate == path or candidate in path.parents


def _protected_paths(cwd: Path | None, home: Path | None, repo_root: Path | None) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = [("the filesystem root", Path("/"))]
    for label, value in (
        ("your home directory", home if home is not None else Path.home()),
        ("the repository root", repo_root if repo_root is not None else REPO_ROOT),
        ("the current directory", cwd if cwd is not None else Path.cwd()),
    ):
        try:
            out.append((label, Path(value).resolve()))
        except OSError:
            continue
    return out


def prepare_run_dir(
    run_dir: Path,
    *,
    force: bool = False,
    cwd: Path | None = None,
    home: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Validate and claim *run_dir* for a demo run; return its resolved path.

    * A missing or empty folder is created/claimed and gets the marker file.
    * A non-empty folder is refused unless ``force`` is true **and** it already
      contains the regular-file marker this demo wrote; only then are its
      contents replaced (symlinks inside are unlinked, never followed).
    * ``/``, home, the repository root, the current directory, and any parent
      of those are always refused, as is a ``run_dir`` that is itself a
      symlink or resolves through one onto a protected path.
    """
    raw = Path(os.path.abspath(os.fspath(run_dir)))
    if raw.is_symlink():
        raise UnsafeOutputDir(f"refusing --out {run_dir}: it is a symlink; pass the real directory")
    resolved = raw.resolve()
    for label, protected in _protected_paths(cwd, home, repo_root):
        if _is_same_or_parent(resolved, protected):
            raise UnsafeOutputDir(
                f"refusing --out {run_dir}: it is {label} or one of its parents"
            )
    if resolved.exists() and not resolved.is_dir():
        raise UnsafeOutputDir(f"refusing --out {run_dir}: it exists and is not a directory")

    marker = resolved / MARKER_NAME
    if resolved.is_dir() and any(resolved.iterdir()):
        if not force:
            raise UnsafeOutputDir(
                f"refusing --out {run_dir}: the folder is not empty. Pick a new or empty "
                "folder, or pass --force to replace an earlier demo run."
            )
        if marker.is_symlink() or not marker.is_file():
            raise UnsafeOutputDir(
                f"refusing --force on {run_dir}: it has no {MARKER_NAME} marker, so it was "
                "not created by this demo. Nothing was deleted."
            )
        for child in resolved.iterdir():
            if child.is_symlink() or not child.is_dir():
                child.unlink()
            else:
                shutil.rmtree(child)
    resolved.mkdir(parents=True, exist_ok=True)
    marker.write_text(MARKER_TEXT, encoding="utf-8")
    return resolved


def _write_brief(path: Path, task: dict, source_rev: str) -> dict:
    brief = {
        "title": task["title"],
        "source_rev": source_rev,
        "assigned_files": list(task["assigned_files"]),
        "acceptance": list(task["acceptance"]),
        "task_id": task["task_id"],
        "model": "scripted-worker",
        "network": "none",
    }
    validate_brief(brief)
    path.write_text(json.dumps(brief, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return brief


def run(run_dir: Path, *, force: bool = False) -> dict:
    """Execute the full miniature workflow. Returns a result dict.

    *run_dir* must be new, empty, or (with ``force``) an earlier demo run that
    carries the marker file; see :func:`prepare_run_dir`.
    """
    run_dir = prepare_run_dir(Path(run_dir), force=force)

    toy = run_dir / "toy-shop"
    source_rev = create_toy_repo(toy)
    contracts = run_dir / "contracts"
    contracts.mkdir()
    packets = run_dir / "packets"
    packets.mkdir()
    workers_dir = run_dir / "workers"
    workers_dir.mkdir()
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir()

    leases = LeaseStore(contracts / "leases.json")
    metrics = MetricsLog(run_dir / "metrics.jsonl")
    metrics.emit("plan", source_rev=source_rev, tasks=[t["task_id"] for t in TASKS])

    briefs = {}
    for task in TASKS:
        brief = _write_brief(contracts / f"{task['task_id']}.brief.json", task, source_rev)
        briefs[task["task_id"]] = brief
        leases.put(lease_record(task["task_id"], source_rev, task["assigned_files"]))
        write_handoff(
            packets / f"{task['task_id']}.HANDOFF.md",
            {
                "project_owner": "reference/toy-shop, orchestrator",
                "user_visible": task["user_visible"],
                "why": "Demonstrate contracts, leases and verification on a disposable example.",
                "acceptance": "; ".join(task["acceptance"]),
                "baseline": f"toy-shop @ {source_rev}",
                "target": "integration branch in the throwaway run directory",
                "spec": f"brief {task['task_id']} at {source_rev}",
                "inputs": "the toy-shop git repo created by this demo (no network)",
                "prior": "none",
                "direction": "Implement only the leased files; tests first in spirit, scripted here.",
                "superseded": "none",
                "authorized": "This reference demo is documentation; it does not authorize a production deploy.",
                "not_authorized": "merge to mojomast/workflow main, tag, release, deploy, catalog, network use",
                "assigned": ", ".join(task["assigned_files"]),
                "budget": "offline, stdlib + git, one scripted worker, stop on lease violation",
                "assumptions": "Python 3 and git are available locally.",
                "deliverable": "unified diff + result manifest",
                "checks": "throwaway checkout at source_rev, scope check against the coordinator lease, unittest",
                "invariants": "files outside the lease stay untouched; existing tests keep passing",
                "visual": "not applicable",
                "unavailable": "no model, no Orbit, no production verifier sandbox",
            },
        )
        metrics.emit("contract_written", task_id=task["task_id"])

    worker_fns = {
        "pricing": work_pricing,
        "labels": work_labels,
        "out_of_scope": work_out_of_scope,
    }

    manifests = {}
    verifications = []
    accepted = []
    rejected = []
    for task in TASKS:
        tid = task["task_id"]
        fn = worker_fns[task["worker"]]
        manifest = fn(toy, source_rev, workers_dir, tid, task["assigned_files"])
        (evidence_dir / f"{tid}.manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        manifests[tid] = manifest
        metrics.emit("worker_finished", task_id=tid, cost_units=manifest["cost_units"])
        try:
            ev = verify_manifest(toy, leases, manifest, source_rev)
        except VerifyRejected as exc:
            ev = exc.evidence
            rejected.append({"task_id": tid, "reason": exc.reason, "evidence": ev})
            metrics.emit("verified", task_id=tid, decision="rejected", reason=exc.reason)
        else:
            accepted.append({"task_id": tid, "patch": manifest["patch"], "evidence": ev})
            metrics.emit("verified", task_id=tid, decision="accepted")
        verifications.append(ev)
        (evidence_dir / f"{tid}.verify.json").write_text(
            json.dumps(ev, indent=2) + "\n", encoding="utf-8"
        )

        decision = ev["decision"]
        write_return(
            packets / f"{tid}.RETURN.md",
            {
                "outcome": "complete" if decision == "accepted" else "blocked",
                "deliverable": str((evidence_dir / f"{tid}.manifest.json").relative_to(run_dir)),
                "revisions": f"base {source_rev}",
                "paths": ", ".join(ev.get("observed_files") or []),
                "decisions": ev.get("reason") or "",
                "limits": ev.get("reason") if decision != "accepted" else "none",
                "deferred": "none",
                "checkpoint": "none",
                "next_action": "integrate accepted patches" if decision == "accepted" else "leave rejected work unapplied",
                "new_auth": "none",
                "reviewed": tid,
                "decision": "accept" if decision == "accepted" else "request changes",
                "reproduced": "yes: throwaway checkout ran the slice tests" if decision == "accepted" else "yes: verifier rejected the patch",
                "findings": ev.get("reason") or "",
                "integrated": "recorded after the integration step",
                "lesson": "verification uses the coordinator lease, never the worker's claimed file list",
            },
            [
                {
                    "criterion": "; ".join(task["acceptance"]),
                    "check": "git apply in a throwaway clone at source_rev, then python3 -m unittest on leased tests",
                    "revision": source_rev,
                    "result": "passed" if decision == "accepted" else "failed",
                    "location": str((evidence_dir / f"{tid}.verify.json").relative_to(run_dir)),
                    "who": "reference verifier (independent of the worker)",
                }
            ],
        )

    # Integration uses only accepted patches, in task order.
    integration = integrate_accepted(toy, source_rev, accepted)
    (evidence_dir / "integration.json").write_text(
        json.dumps({k: v for k, v in integration.items() if k != "cleanup"}, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics.emit("integrated", passed=integration["passed"], applied=integration.get("applied"))

    accepted_cost = sum(manifests[item["task_id"]]["cost_units"] for item in accepted)
    summary = metrics.summarize(verifications, accepted_cost, rejected, integration)

    rejected_ids = [item["task_id"] for item in rejected]
    accepted_ids = [item["task_id"] for item in accepted]
    ok = (
        integration["passed"]
        and "W3-out-of-scope" in rejected_ids
        and "W1-pricing" in accepted_ids
        and "W2-labels" in accepted_ids
        and len(accepted_ids) == 2
    )

    result = {
        "ok": ok,
        "run_dir": str(run_dir),
        "source_rev": source_rev,
        "accepted": accepted_ids,
        "rejected": {item["task_id"]: item["reason"] for item in rejected},
        "integration": {k: v for k, v in integration.items() if k not in {"cleanup", "worktree"}},
        "metrics": summary,
        "metrics_path": str(run_dir / "metrics.jsonl"),
        "_integration_cleanup": integration,
    }
    (run_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in result.items() if not k.startswith("_")}, indent=2) + "\n",
        encoding="utf-8",
    )
    cleanup_integration(integration)
    result.pop("_integration_cleanup", None)
    return result
