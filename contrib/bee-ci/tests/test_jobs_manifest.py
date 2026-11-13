"""Contract tests for the runnable bee-CI job manifest schema.

These tests pin the extended schema (``command``, ``workdir``, ``requires`` and
``timeout_s``) and the real hyvv job set copied from hyvv's CI definition. They
read the checked-in manifests directly, so a hand edit cannot silently drop a
command or rename a leg.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parents[1]
JOBS_DIR = HERE / "jobs"
SCHEMA_PATH = HERE / "schemas" / "job-manifest.schema.json"

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
