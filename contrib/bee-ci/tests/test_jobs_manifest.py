"""Contract tests for the runnable bee-CI job manifest schema.

These tests pin the extended schema (``command``, ``workdir``, ``requires`` and
``timeout_s``) and the real hyvv job set copied from hyvv's CI definition. They
read the checked-in manifests directly, so a hand edit cannot silently drop a
command or rename a leg.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parents[1]
JOBS_DIR = HERE / "jobs"
SCHEMA_PATH = HERE / "schemas" / "job-manifest.schema.json"
REPO_ROOT = HERE.parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

sys.path.insert(0, str(HERE))

from manifest import validate_document  # noqa: E402

HYVV_COMMANDS = {
    "unit": [
        "uv sync --frozen --no-dev || uv sync --no-dev",
        "uv run python -m unittest discover -s tests -v",
    ],
    "contract": [
        "uv run python -m contract -v",
    ],
    "release-assets": [
        "rm -rf dist release-assets",
        "uv build",
        "uv run python scripts/build_release_assets.py --dist dist --out release-assets",
        'test "$(ls dist | wc -l | tr -d " ")" = 2',
    ],
    "installer-dry-run": [
        "sh scripts/install.sh --dry-run",
    ],
    "scan": [
        "gitleaks detect --source . --redact --verbose --exit-code 1",
        "scripts/scan-secrets.sh",
    ],
}

HYVV_GITHUB_ONLY = {
    "macos-unit": "macos-15",
    "arm64-unit": "ubuntu-24.04-arm",
}


def _job_files() -> list[Path]:
    return sorted(JOBS_DIR.glob("*.yaml"))


def _load(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path.name}: manifest must be an object"
    return document


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_every_manifest_matches_the_schema():
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    paths = _job_files()
    assert paths, f"no job manifests found under {JOBS_DIR}"

    for path in paths:
        document = _load(path)
        errors = sorted(
            validator.iter_errors(document),
            key=lambda error: (
                len(error.absolute_path),
                [str(part) for part in error.absolute_path],
            ),
        )
        assert not errors, f"{path.name}: {errors[0].message}"
        validate_document(document, source=path.name)


def _ci_job_names() -> list[str]:
    """Read the job keys under the top-level ``jobs:`` block of ci.yml.

    The workflow is plain enough that a YAML dependency would be heavier than
    the parse: job keys are the only two-space-indented ``key:`` lines directly
    under ``jobs:``.
    """

    names: list[str] = []
    in_jobs = False
    for line in CI_WORKFLOW.read_text(encoding="utf-8").splitlines():
        if not in_jobs:
            if line == "jobs:":
                in_jobs = True
            continue
        if line and not line[0].isspace():
            break
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            names.append(match.group(1))
    return names


def test_workflow_manifest_matches_ci():
    document = _load(JOBS_DIR / "workflow.yaml")
    jobs = {job["name"]: job for job in document["jobs"]}

    ci_jobs = _ci_job_names()
    assert ci_jobs, f"could not read any job names from {CI_WORKFLOW}"

    missing = [name for name in ci_jobs if name not in jobs]
    assert not missing, (
        f"workflow.yaml is missing ci.yml jobs {missing!r}; "
        f"declared jobs are {sorted(jobs)!r}"
    )

    for name in ci_jobs:
        job = jobs[name]
        assert job["runner"] == "bee", (
            f"workflow/{name} is defined by ci.yml and must run on a bee"
        )
        commands = job.get("command")
        assert isinstance(commands, list) and commands, (
            f"workflow/{name} is bee-hosted and needs at least one command"
        )
        assert all(
            isinstance(command, str) and command.strip() for command in commands
        ), f"workflow/{name} has an empty command step"

    assert jobs["acceptance-light"].get("requires") == ["docker"], (
        "acceptance-light builds containers and must declare docker"
    )
    assert jobs["secret-scan"].get("requires") == ["gitleaks"], (
        "secret-scan must declare the gitleaks tool it needs"
    )

    for name in ("macos-docs", "arm64-smoke"):
        job = jobs[name]
        assert job["runner"] == "github-only", (
            f"workflow/{name} must stay github-only"
        )
        assert "command" not in job, (
            f"workflow/{name} stays a GitHub-only leg and must not carry "
            f"bee commands"
        )


def test_hyvv_jobs_carry_real_commands():
    document = _load(JOBS_DIR / "hyvv.yaml")
    jobs = {job["name"]: job for job in document["jobs"]}

    assert set(jobs) == set(HYVV_COMMANDS) | set(HYVV_GITHUB_ONLY)

    for name, expected in HYVV_COMMANDS.items():
        job = jobs[name]
        assert job["command"] == expected, (
            f"hyvv/{name} commands {job.get('command')!r} do not match the "
            f"real CI steps {expected!r}"
        )
        assert job.get("workdir", ".") == ".", (
            f"hyvv/{name} must run from the repository root"
        )
        assert job["runner"] == "bee"

    assert jobs["scan"].get("requires") == ["gitleaks"], (
        "hyvv/scan must declare the gitleaks tool it needs"
    )
    assert all(
        not jobs[name].get("requires")
        for name in HYVV_COMMANDS
        if name != "scan"
    ), "only hyvv/scan requires an external tool"

    for name, os_name in HYVV_GITHUB_ONLY.items():
        job = jobs[name]
        assert job["runner"] == "github-only"
        assert job["os"] == os_name
        assert "command" not in job, (
            f"hyvv/{name} stays a GitHub-only leg and must not carry bee commands"
        )
