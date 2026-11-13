"""Contract tests for the bee-run CI job manifests.

These tests are the acceptance gate for contrib/bee-ci. They intentionally
exercise the public loader surface rather than the YAML files directly, so the
schema and the loader cannot drift apart.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from manifest import (  # noqa: E402
    ManifestError,
    is_bee_eligible,
    load_all,
    load_repo,
    validate_document,
)

REPOS = ("workflow", "bundlebees", "orbitdesktop", "hyvv")

EXPECTED_JOBS = {
    "workflow": (
        "reference",
        "project-state",
        "observability",
        "acceptance-light",
        "secret-scan",
        "macos-docs",
        "arm64-smoke",
    ),
    "bundlebees": (
        "plugin-tests",
        "js-tests",
        "verify-sandbox",
        "macos-plugin",
        "arm64-plugin",
    ),
    "orbitdesktop": (
        "unit",
        "browser-e2e",
        "python-launcher",
        "macos-desktop",
        "arm64-desktop",
    ),
    "hyvv": (
        "unit",
        "contract",
        "release-assets",
        "installer-dry-run",
        "scan",
        "macos-unit",
        "arm64-unit",
    ),
}


def _load_json_copy(repo: str) -> dict:
    path = ROOT / "jobs" / f"{repo}.yaml"
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_repos_declared():
    manifests = load_all(ROOT / "jobs")

    assert set(manifests) == set(REPOS), (
        "every mission repo must have exactly one job manifest; "
        f"found {sorted(manifests)}"
    )

    for repo in REPOS:
        manifest = load_repo(repo)
        assert manifest["repo"] == repo
        jobs = manifest["jobs"]
        assert jobs, f"{repo} must declare at least one job"

        names = tuple(job["name"] for job in jobs)
        assert names == EXPECTED_JOBS[repo], (
            f"{repo} jobs {names!r} do not match FIRST-MISSION section 2 "
            f"expectation {EXPECTED_JOBS[repo]!r}"
        )
        assert len(set(names)) == len(names), f"{repo} has duplicate job names"

        for job in jobs:
            where = f"{repo}/{job['name']}"
            assert job["os"], f"{where} is missing an OS"
            assert job["image"], f"{where} is missing an image"
            assert job["arch"] in ("x64", "arm64"), f"{where} has a bad arch"
            assert job["python"] is None or isinstance(job["python"], str)
            assert job["node"] is None or isinstance(job["node"], str)
            assert job["browser"] in ("none", "chromium", "firefox", "webkit"), (
                f"{where} has a bad browser need"
            )
            assert job["runner"] in ("bee", "github-only"), (
                f"{where} has a bad runner value"
            )


def test_github_only_legs():
    manifests = load_all(ROOT / "jobs")
    seen_macos = False
    seen_arm = False

    for repo, manifest in manifests.items():
        for job in manifest["jobs"]:
            where = f"{repo}/{job['name']}"
            macos = job["os"].startswith("macos-")
            arm = job["arch"] == "arm64"

            if macos:
                seen_macos = True
            if arm:
                seen_arm = True

            if macos or arm:
                assert job["runner"] == "github-only", (
                    f"{where} is a macOS or arm leg and must be github-only"
                )
                assert is_bee_eligible(job) is False, (
                    f"{where} must not be reported as bee-eligible"
                )
            else:
                assert job["runner"] == "bee", (
                    f"{where} is a Linux x64 leg and should be bee-eligible"
                )
                assert is_bee_eligible(job) is True, (
                    f"{where} should be reported as bee-eligible"
                )

    assert seen_macos, "the mission requires macOS github-only legs"
    assert seen_arm, "the mission requires arm github-only legs"


def test_rejects_unknown():
    base = _load_json_copy("workflow")

    unknown = copy.deepcopy(base)
    unknown["jobs"][0]["cache"] = True
    with pytest.raises(ManifestError, match="cache"):
        validate_document(unknown, source="workflow.yaml")

    unknown_top = copy.deepcopy(base)
    unknown_top["dispatcher"] = "later"
    with pytest.raises(ManifestError, match="dispatcher"):
        validate_document(unknown_top, source="workflow.yaml")

    missing_image = copy.deepcopy(base)
    del missing_image["jobs"][0]["image"]
    with pytest.raises(ManifestError, match="image"):
        validate_document(missing_image, source="workflow.yaml")

    missing_os = copy.deepcopy(base)
    del missing_os["jobs"][0]["os"]
    with pytest.raises(ManifestError, match="os"):
        validate_document(missing_os, source="workflow.yaml")

    bad_runner = copy.deepcopy(base)
    bad_runner["jobs"][0]["runner"] = "probably"
    with pytest.raises(ManifestError, match="runner"):
        validate_document(bad_runner, source="workflow.yaml")


def test_loader_rejects_files_outside_repo_allowlist():
    with pytest.raises(ManifestError):
        load_repo("../workflow")
