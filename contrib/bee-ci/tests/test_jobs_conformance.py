"""Conformance tests for the checked-in bee-CI job declarations.

The tests read every manifest under ``contrib/bee-ci/jobs`` directly so a
hand-edited job file cannot drift away from the schema or the loader. They pin
three things: schema validity, resolvable runner/path declarations, and the
fail-closed rule that only macOS and arm64 legs may be ``github-only``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parents[1]
JOBS_DIR = HERE / "jobs"
SCHEMA_PATH = HERE / "schema" / "ci-job.schema.json"
REPO_ROOT = HERE.parent.parent

sys.path.insert(0, str(HERE))

from manifest import REPOS, is_bee_eligible, validate_document  # noqa: E402

EXPECTED_RUNNERS = frozenset({"bee", "github-only"})
PATH_KEYS = frozenset(
    {
        "path",
        "paths",
        "script",
        "scripts",
        "file",
        "files",
        "workflow",
        "run",
        "cwd",
        "working_directory",
    }
)
SCRIPT_SUFFIXES = (
    ".sh",
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".cfg",
    ".ini",
    ".rb",
    ".go",
    ".rs",
    ".java",
)


def _job_files() -> list[Path]:
    return sorted(JOBS_DIR.glob("*.yaml"))


def _load_document(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path.name}: manifest must be an object"
    return document


def _runner_targets(schema: dict) -> frozenset[str]:
    return frozenset(schema["$defs"]["job"]["properties"]["runner"]["enum"])


def _iter_string_values(
    node: object, key: str | None = None
) -> Iterator[tuple[str | None, str]]:
    if isinstance(node, dict):
        for child_key, child in node.items():
            yield from _iter_string_values(child, child_key)
    elif isinstance(node, list):
        for child in node:
            yield from _iter_string_values(child, key)
    elif isinstance(node, str):
        yield key, node


def _looks_like_repo_path(key: str | None, text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if key in PATH_KEYS:
        return True
    if "://" in text or text.startswith("${{"):
        return False
    return (
        "/" in text
        or text.startswith(("./", "../"))
        or text.lower().endswith(SCRIPT_SUFFIXES)
    )


def _assert_repo_path_exists(reference: str, where: str) -> None:
    reference = reference.strip()
    assert "://" not in reference, (
        f"{where}: expected a repository path, found URL {reference!r}"
    )
    assert not reference.startswith("/"), (
        f"{where}: expected a repository-relative path, found {reference!r}"
    )
    root = REPO_ROOT.resolve()
    candidate = (root / reference).resolve()
    assert candidate == root or root in candidate.parents, (
        f"{where}: path {reference!r} escapes the repository"
    )
    assert candidate.exists(), (
        f"{where}: referenced path {reference!r} does not exist in the repository"
    )


def test_job_files_validate():
    paths = _job_files()
    assert paths, f"no job manifests found under {JOBS_DIR}"

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    for path in paths:
        document = _load_document(path)
        errors = sorted(
            validator.iter_errors(document),
            key=lambda error: (
                len(error.absolute_path),
                [str(part) for part in error.absolute_path],
            ),
        )
        assert not errors, f"{path.name}: {errors[0].message}"

        validate_document(document, source=path.name)

        assert document["repo"] == path.stem, (
            f"{path.name}: repo field {document['repo']!r} does not match "
            f"file name {path.stem!r}"
        )
        assert document["repo"] in REPOS, (
            f"{path.name}: repo {document['repo']!r} is not in the manifest "
            f"allow-list {REPOS!r}"
        )
        assert isinstance(document["jobs"], list) and document["jobs"], (
            f"{path.name}: must declare at least one job"
        )
        for job in document["jobs"]:
            assert job.get("name"), f"{path.name}: job without a name"


def test_declared_paths_exist():
    paths = _job_files()
    assert paths, f"no job manifests found under {JOBS_DIR}"

    stems = {path.stem for path in paths}
    assert stems == set(REPOS), (
        "every manifest repository must have exactly one job file and no "
        f"orphan files; files={sorted(stems)}, repos={sorted(REPOS)}"
    )

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    runner_targets = _runner_targets(schema)
    assert runner_targets == EXPECTED_RUNNERS, (
        f"schema runner targets {sorted(runner_targets)} do not match the "
        f"manifest contract {sorted(EXPECTED_RUNNERS)}"
    )

    for path in paths:
        document = _load_document(path)
        assert document["repo"] in REPOS, (
            f"{path.name}: repo {document['repo']!r} is not a manifest target"
        )
        for job in document["jobs"]:
            where = f"{path.name}:{job['name']}"
            assert job["runner"] in runner_targets, (
                f"{where}: runner {job['runner']!r} is not one of "
                f"{sorted(runner_targets)}"
            )
            for key, value in _iter_string_values(job):
                if _looks_like_repo_path(key, value):
                    _assert_repo_path_exists(value, where)


def test_github_only_set_is_exact():
    paths = _job_files()
    assert paths, f"no job manifests found under {JOBS_DIR}"

    github_only: set[str] = set()
    macos_or_arm: set[str] = set()
    saw_macos = False
    saw_arm = False

    for path in paths:
        document = _load_document(path)
        for job in document["jobs"]:
            where = f"{document['repo']}/{job['name']}"
            macos = job["os"].startswith("macos-")
            arm = job["arch"] == "arm64"
            is_github_only = job["runner"] == "github-only"

            saw_macos = saw_macos or macos
            saw_arm = saw_arm or arm

            if macos or arm:
                macos_or_arm.add(where)
            if is_github_only:
                github_only.add(where)

            if macos or arm:
                assert is_github_only, (
                    f"{where} is a macOS or arm64 leg and must be github-only"
                )
                assert not is_bee_eligible(job), (
                    f"{where} must never be reported as bee-eligible"
                )
            else:
                assert job["runner"] == "bee", (
                    f"{where} is a Linux x64 leg and must be bee-eligible"
                )
                assert is_bee_eligible(job), (
                    f"{where} should be reported as bee-eligible"
                )

    assert saw_macos, "the manifests must contain macOS github-only legs"
    assert saw_arm, "the manifests must contain arm64 github-only legs"
    assert github_only == macos_or_arm, (
        "the github-only set must be exactly the macOS and arm64 legs; "
        f"github-only={sorted(github_only)}, "
        f"macos-or-arm={sorted(macos_or_arm)}"
    )
