"""Loader for the bee-run CI job manifests.

The manifests are YAML documents written in the JSON-compatible subset of
YAML, so this module only needs the standard library plus ``jsonschema``. That
keeps the loader runnable on a bare bee sandbox without adding a YAML runtime
dependency.

A manifest is intentionally small: one file per repository, a list of CI legs,
and for each leg the OS, container image, architecture, Python/Node versions,
browser need and runner eligibility. macOS and arm64 legs are fail-closed as
``github-only`` in both the schema and this loader; a bee can only pick Linux
x64 legs explicitly marked ``runner: bee``.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

HERE = Path(__file__).resolve().parent
JOBS_DIR = HERE / "jobs"
SCHEMA_PATH = HERE / "schema" / "ci-job.schema.json"
REPOS = ("workflow", "bundlebees", "orbitdesktop", "hyvv")

_REPO_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ManifestError(ValueError):
    """Raised when a manifest cannot be read or does not satisfy the schema."""


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read schema {SCHEMA_PATH}: {exc}") from exc

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # pragma: no cover - schema is a checked-in artifact
        raise ManifestError(f"invalid schema {SCHEMA_PATH}: {exc}") from exc

    return Draft202012Validator(schema)


def _format_path(path: Any) -> str:
    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        elif rendered:
            rendered += f".{part}"
        else:
            rendered = str(part)
    return rendered or "<root>"


def _semantic_checks(document: Mapping[str, Any], source: str) -> None:
    jobs = document["jobs"]
    names = [job["name"] for job in jobs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ManifestError(
            f"{source}: duplicate job name(s): {', '.join(duplicates)}"
        )

    for index, job in enumerate(jobs):
        where = f"{source}: jobs[{index}] ({job['name']})"
        if job["runner"] == "bee":
            if job["os"].startswith("macos-"):
                raise ManifestError(f"{where}: macOS legs must be github-only")
            if job["arch"] != "x64":
                raise ManifestError(f"{where}: non-x64 legs must be github-only")
            if not job["os"].startswith("ubuntu-"):
                raise ManifestError(
                    f"{where}: bee legs must run on a Linux Ubuntu image"
                )


def validate_document(
    document: Any, source: str = "<memory>"
) -> dict[str, Any]:
    """Validate one manifest document and return it unchanged.

    Raises :class:`ManifestError` with the source, JSON path and the underlying
    schema message so an unknown key, missing image/OS or bad runner value is
    actionable without opening the schema.
    """

    if not isinstance(document, dict):
        raise ManifestError(f"{source}: <root>: manifest must be an object")

    errors = sorted(
        _validator().iter_errors(document),
        key=lambda error: (len(error.absolute_path), list(error.absolute_path)),
    )
    if errors:
        error: ValidationError = errors[0]
        path = _format_path(error.absolute_path)
        raise ManifestError(f"{source}: {path}: {error.message}") from None

    _semantic_checks(document, source)
    return document


def _parse_manifest(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"{path}: manifest is not JSON-compatible YAML: "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    return validate_document(document, source=str(path))


def load_repo(repo: str, jobs_dir: Path | str | None = None) -> dict[str, Any]:
    """Load and validate one repository manifest.

    ``repo`` is restricted to the mission allow-list and must be a bare name,
    never a path. That keeps a caller from reading files outside ``jobs/``.
    """

    if repo not in REPOS or not _REPO_RE.fullmatch(repo):
        raise ManifestError(
            f"unknown repository {repo!r}; expected one of {', '.join(REPOS)}"
        )

    directory = Path(jobs_dir) if jobs_dir is not None else JOBS_DIR
    path = (directory / f"{repo}.yaml").resolve()
    expected_parent = directory.resolve()
    if path.parent != expected_parent:
        raise ManifestError(f"refusing manifest path outside {expected_parent}")

    if not path.is_file():
        raise ManifestError(f"missing manifest for {repo}: {path}")

    document = _parse_manifest(path)
    if document["repo"] != repo:
        raise ManifestError(
            f"{path}: repo field {document['repo']!r} does not match {repo!r}"
        )
    return document


def load_all(jobs_dir: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load every mission manifest keyed by repository name."""

    return {repo: load_repo(repo, jobs_dir) for repo in REPOS}


def is_bee_eligible(job: Mapping[str, Any]) -> bool:
    """Return whether a bee dispatcher may pick this leg.

    The check is fail-closed: anything missing, unknown, macOS or arm64 is not
    eligible even if it somehow carries ``runner: bee``.
    """

    try:
        return (
            job["runner"] == "bee"
            and job["arch"] == "x64"
            and str(job["os"]).startswith("ubuntu-")
        )
    except (KeyError, TypeError):
        return False
