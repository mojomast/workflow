#!/usr/bin/env python3
"""One bee-CI pipeline: poll, dispatch, verify, compare.

The pipeline is inert by default. Each stage is imported from the existing
modules rather than reimplemented:

* :mod:`poll` lists open pull-request heads and dedupes them on disk;
* :mod:`dispatch` submits bee-eligible manifest jobs with fresh task ids;
* :mod:`verify_result` verifies the signed result fail-closed;
* :mod:`post_status` builds (and, only when explicitly live, posts) the
  commit status;
* :mod:`compare` compares the verified outcome with GitHub Actions.

``run(config)`` returns one structured JSON-friendly report. Every external
effect is injectable (GitHub reader, launcher adapter, dispatch transport,
result provider, Actions provider, status transport, result key), so tests
never touch the network, git, or a real launcher.

Dry-run is the default. A live run requires ``live=True`` *and* injected
transports where the stage needs them. A caller cannot turn on live behaviour
with ``dry_run=False`` alone.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # loaded as a package
    from . import compare as _compare
    from . import dispatch as _dispatch
    from . import manifest as _manifest
    from . import poll as _poll
    from . import post_status as _post_status
    from . import verify_result as _verify_result
except ImportError:  # loaded as a top-level module from contrib/bee-ci
    import compare as _compare
    import dispatch as _dispatch
    import manifest as _manifest
    import poll as _poll
    import post_status as _post_status
    import verify_result as _verify_result

SCHEMA_VERSION = 1
TOOL = "bee-ci-pipeline"
DRY_RUN_TOKEN = "bee-ci-dry-run"
STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"


class PipelineError(RuntimeError):
    """Base class for safe, non-secret-bearing pipeline failures."""


class PipelineConfigError(PipelineError):
    """The injected configuration cannot be used safely."""


class _NullGitHub:
    """A dry-run GitHub reader that never leaves the process."""

    def list_open_prs(self, repo: str) -> list[dict[str, Any]]:
        return []


class _NullLauncher:
    """A dry-run launcher adapter with zero capacity and no dispatch."""

    def status(self) -> dict[str, int]:
        return {"active": 0, "max": 0}

    def bee_count(self) -> int:
        return 0

    def capacity(self) -> int:
        return 0

    def dispatch(self, item: Mapping[str, Any]) -> Any:
        raise PipelineError("launcher dispatch is unavailable in dry-run")


class _DryRunTransport:
    """Records the request locally and returns a synthetic success."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        self.calls.append(dict(payload))
        return {"ok": True, "dry_run": True}


def _safe_reason(value: Any) -> str:
    """Sanitize an untrusted failure message with the status scrubber."""
    try:
        return _post_status.sanitize_text(value, limit=240)
    except Exception:
        return ""


def _error_payload(
    exc: BaseException | None = None,
    *,
    code: str | None = None,
    reason: str | None = None,
) -> dict[str, str]:
    if code is None:
        code = type(exc).__name__ if exc is not None else "pipeline_error"
    if reason is None:
        reason = _safe_reason(exc) if exc is not None else ""
    return {"code": str(code), "reason": str(reason)}


def _call_flexible(
    function: Callable[..., Any],
    candidates: Sequence[tuple[tuple[Any, ...], dict[str, Any]]],
) -> Any:
    """Call an injected callback using the first signature it accepts."""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        for args, kwargs in candidates:
            try:
                signature.bind(*args, **kwargs)
            except TypeError:
                continue
            return function(*args, **kwargs)
        raise PipelineConfigError("injected callback has an unsupported signature")
    last: BaseException | None = None
    for args, kwargs in candidates:
        try:
            return function(*args, **kwargs)
        except TypeError as exc:
            last = exc
            continue
    raise PipelineConfigError("injected callback could not be called") from last


def _normalise_repos(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        raw = list(_poll.DEFAULT_REPOS)
    if isinstance(raw, (str, bytes)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise PipelineConfigError("repos must be a sequence of repository slugs")
    entries: list[dict[str, str]] = []
    for value in raw:
        if isinstance(value, str):
            slug = value.strip()
            if not slug:
                raise PipelineConfigError("repos must not contain empty values")
            entries.append({"slug": slug, "name": slug.rsplit("/", 1)[-1]})
            continue
        if isinstance(value, Mapping):
            slug = value.get("slug") or value.get("full_name") or value.get("repo")
            name = value.get("manifest") or value.get("name") or value.get("repo")
            if not isinstance(slug, str) or not slug.strip():
                raise PipelineConfigError("repo entry is missing a slug")
            slug = slug.strip()
            if not isinstance(name, str) or not name.strip():
                name = slug.rsplit("/", 1)[-1]
            entries.append({"slug": slug, "name": name.strip()})
            continue
        raise PipelineConfigError("repo entries must be strings or objects")
    if not entries:
        raise PipelineConfigError("at least one repository is required")
    return entries


def _default_state_path(dry_run: bool) -> Path:
    if not dry_run:
        return _poll.default_state_path()
    return Path(tempfile.mkdtemp(prefix="bee-ci-pipeline-")) / "state.json"


def _job_name(job: Any) -> str:
    if isinstance(job, Mapping):
        name = job.get("name")
    else:
        name = job
    if not isinstance(name, str) or not name.strip():
        raise PipelineConfigError("manifest job is missing a name")
    return name.strip()


def _load_document(name: str, slug: str, config: Mapping[str, Any]) -> Any:
    loader = config.get("manifest_loader")
    if callable(loader):
        return _call_flexible(
            loader,
            (
                ((), {"repo": name}),
                ((), {"name": name}),
                ((name,), {}),
                ((slug,), {}),
                ((), {}),
            ),
        )
    jobs = config.get("jobs")
    if isinstance(jobs, Mapping):
        if name in jobs:
            return jobs[name]
        if slug in jobs:
            return jobs[slug]
        raise PipelineConfigError(f"no manifest was supplied for {name}")
    return _manifest.load_repo(name)


def _result_lookup(
    source: Any,
    *,
    repo: str,
    head_sha: str,
    job: str,
    task_id: str,
) -> Any:
    if source is None:
        return None
    if callable(source):
        return _call_flexible(
            source,
            (
                (
                    (),
                    {
                        "repo": repo,
                        "head_sha": head_sha,
                        "job": job,
                        "task_id": task_id,
                    },
                ),
                ((repo, head_sha, job, task_id), {}),
                ((repo, head_sha, job), {}),
                ((repo, head_sha), {}),
                ((repo,), {}),
            ),
        )
    if isinstance(source, Mapping):
        for key in (
            task_id,
            (repo, head_sha, job),
            (head_sha, job),
            job,
            head_sha,
        ):
            try:
                found = key in source
            except TypeError:
                found = False
            if found:
                value = source[key]
                return value() if callable(value) else value
        return None
    raise PipelineConfigError("results must be a provider, mapping or null")


def _actions_lookup(source: Any, repo: str, records: list[dict[str, Any]]) -> Any:
    if source is None:
        return {"records": []}
    if callable(source):
        return _call_flexible(
            source,
            (
                ((), {"repo": repo, "records": records}),
                ((repo, records), {}),
                ((repo,), {}),
                ((records,), {}),
                ((), {}),
            ),
        )
    if isinstance(source, Mapping):
        if "records" in source or "results" in source:
            return source
        if repo in source:
            return source[repo]
        name = repo.rsplit("/", 1)[-1]
        if name in source:
            return source[name]
        return {"records": []}
    if isinstance(source, list):
        return source
    raise PipelineConfigError("actions must be a payload, mapping, list or callable")


def _new_record(repo: str, sha: str, item: Mapping[str, Any], job: Any) -> dict[str, Any]:
    job_name = _job_name(job)
    return {
        "repo": repo,
        "sha": sha,
        "head_sha": sha,
        "job": job_name,
        "job_spec": dict(job) if isinstance(job, Mapping) else job,
        "pr": item.get("pr", 0),
        "task_id": None,
        "status": STATUS_PENDING,
        "stage": "dispatch",
        "dispatch": None,
        "verification": None,
        "comparison": None,
        "verdict": None,
        "github_status": None,
        "error": None,
    }


def _summary(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    def count_status(value: str) -> int:
        return sum(1 for record in records if record.get("status") == value)

    def count_verdict(value: str) -> int:
        return sum(1 for record in records if record.get("verdict") == value)

    def dispatched(record: Mapping[str, Any]) -> bool:
        result = record.get("dispatch")
        return isinstance(result, Mapping) and result.get("state") == _dispatch.STATE_SUCCESS

    def verified(record: Mapping[str, Any]) -> bool:
        result = record.get("verification")
        return (
            isinstance(result, Mapping)
            and result.get("status") == _verify_result.STATUS_SUCCESS
        )

    return {
        "total": len(records),
        "success": count_status(STATUS_SUCCESS),
        "failure": count_status("failure"),
        "error": count_status(STATUS_ERROR),
        "dispatched": sum(1 for record in records if dispatched(record)),
        "verified": sum(1 for record in records if verified(record)),
        "agree": count_verdict("agree"),
        "disagree": count_verdict("disagree"),
        "inconclusive": count_verdict("inconclusive"),
    }


def _report(
    *,
    dry_run: bool,
    live: bool,
    repos: Sequence[str],
    status: str,
    stage: str | None,
    poll: Any,
    jobs: list[dict[str, Any]],
    comparisons: Mapping[str, Any],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = _summary(jobs)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL,
        "dry_run": dry_run,
        "live": live,
        "repos": list(repos),
        "status": status,
        "stage": stage,
        "poll": poll,
        "jobs": jobs,
        "comparisons": dict(comparisons),
        "summary": summary,
        "errors": errors,
    }


def run(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run poll -> dispatch -> verify -> compare and return one report."""
    if config is None:
        config = {}
    if not isinstance(config, Mapping):
        raise PipelineConfigError("config must be a mapping")

    # Live behaviour needs the explicit boolean flag. dry_run=False alone is
    # not consent to post or to contact a real launcher.
    live = config.get("live") is True and not bool(config.get("dry_run", False))
    dry_run = not live

    entries = _normalise_repos(config.get("repos"))
    slugs = [entry["slug"] for entry in entries]

    github = config.get("github")
    if github is None:
        github = _poll.GitHubClient() if live else _NullGitHub()
    launcher = config.get("launcher")
    if launcher is None:
        launcher = _poll.default_launcher() if live else _NullLauncher()

    state_path = config.get("state_path")
    if state_path is None:
        state_path = _default_state_path(dry_run)

    # Poll only: cap 0 keeps the poller from submitting to the launcher. The
    # pipeline dispatches the manifest jobs itself in the next stage.
    try:
        poller = _poll.Poller(
            repos=slugs,
            state_path=state_path,
            github=github,
            launcher=launcher,
            cap=0,
        )
        poll_result = poller.poll()
    except Exception as exc:
        payload = _error_payload(exc)
        return _report(
            dry_run=dry_run,
            live=live,
            repos=slugs,
            status="error",
            stage="poll",
            poll=None,
            jobs=[],
            comparisons={},
            errors=[{"stage": "poll", **payload}],
        )

    jobs: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    names = {entry["slug"]: entry["name"] for entry in entries}

    for item in poll_result.get("new", []) or []:
        if not isinstance(item, Mapping):
            continue
        repo = str(item.get("repo") or "")
        sha = str(item.get("head_sha") or "")
        if not repo or not sha:
            continue
        name = names.get(repo, repo.rsplit("/", 1)[-1])
        try:
            document = _load_document(name, repo, config)
            manifest_jobs = document.get("jobs", []) if isinstance(document, Mapping) else []
            selected = [job for job in manifest_jobs if _manifest.is_bee_eligible(job)]
        except Exception as exc:
            payload = _error_payload(exc)
            record = {
                "repo": repo,
                "sha": sha,
                "head_sha": sha,
                "job": "*",
                "job_spec": None,
                "pr": item.get("pr", 0),
                "task_id": None,
                "status": STATUS_ERROR,
                "stage": "dispatch",
                "dispatch": None,
                "verification": None,
                "comparison": None,
                "verdict": None,
                "github_status": None,
                "error": payload,
            }
            jobs.append(record)
            errors.append({"repo": repo, "sha": sha, "job": "*", "stage": "dispatch", **payload})
            continue
        for job in selected:
            units.append({"repo": repo, "sha": sha, "item": item, "job": job, "record": None})

    # ---- dispatch ----
    transport = config.get("transport")
    if dry_run and transport is None:
        transport = _DryRunTransport()
    dispatch_env = (
        {"BEE_CI_LAUNCHER_TOKEN": DRY_RUN_TOKEN} if dry_run else config.get("env")
    )
    base_url = config.get("base_url")

    for unit in units:
        record = _new_record(unit["repo"], unit["sha"], unit["item"], unit["job"])
        unit["record"] = record
        jobs.append(record)
        try:
            work_item = _dispatch.WorkItem(
                repo=unit["repo"], head_sha=unit["sha"], job=unit["job"]
            )
            result = _dispatch.dispatch(
                work_item,
                transport=transport,
                base_url=base_url,
                env=dispatch_env,
            )
        except Exception as exc:
            payload = _error_payload(exc)
            record["status"] = STATUS_ERROR
            record["stage"] = "dispatch"
            record["error"] = payload
            errors.append(
                {
                    "repo": record["repo"],
                    "sha": record["sha"],
                    "job": record["job"],
                    "stage": "dispatch",
                    **payload,
                }
            )
            continue

        if isinstance(result, list):
            result = result[0] if result else {}
        dispatch_result = dict(result) if isinstance(result, Mapping) else {}
        record["dispatch"] = dispatch_result
        record["task_id"] = dispatch_result.get("task_id")
        if dispatch_result.get("state") != _dispatch.STATE_SUCCESS:
            payload = _error_payload(
                code=dispatch_result.get("code") or "dispatch_error",
                reason=_safe_reason(dispatch_result.get("error") or "dispatch failed"),
            )
            record["status"] = STATUS_ERROR
            record["stage"] = "dispatch"
            record["error"] = payload
            errors.append(
                {
                    "repo": record["repo"],
                    "sha": record["sha"],
                    "job": record["job"],
                    "stage": "dispatch",
                    **payload,
                }
            )

    # ---- verify (and build/post the status) ----
    key = config.get("key")
    if key is None:
        key = os.environ.get(_verify_result.DEFAULT_KEY_ENV)
    status_transport = config.get("status_transport")
    status_env = None if dry_run else config.get("env")

    for unit in units:
        record = unit.get("record")
        if not isinstance(record, dict) or record["status"] != STATUS_PENDING:
            continue
        task_id = record.get("task_id")
        try:
            payload = _result_lookup(
                config.get("results"),
                repo=unit["repo"],
                head_sha=unit["sha"],
                job=record["job"],
                task_id=str(task_id or ""),
            )
        except Exception as exc:
            payload = None
            lookup_error = exc
        else:
            lookup_error = None

        if lookup_error is not None:
            verification = {
                "status": _verify_result.STATUS_ERROR,
                "code": "result_lookup_error",
                "reason": _safe_reason(lookup_error),
            }
        elif payload is None:
            verification = {
                "status": _verify_result.STATUS_ERROR,
                "code": "missing_result",
                "reason": "no result was returned for the dispatched task",
            }
        else:
            try:
                checked = _verify_result.verify_result(
                    payload,
                    expected_head=unit["sha"],
                    expected_job=str(task_id or ""),
                    key=key,
                )
                verification = {
                    "status": checked.status,
                    "code": checked.code,
                    "reason": checked.reason,
                }
            except Exception as exc:
                verification = {
                    "status": _verify_result.STATUS_ERROR,
                    "code": "verification_error",
                    "reason": _safe_reason(exc),
                }

        record["verification"] = verification
        if verification["status"] != _verify_result.STATUS_SUCCESS:
            record["status"] = STATUS_ERROR
            record["stage"] = "verify"
            record["error"] = {
                "code": verification["code"],
                "reason": verification["reason"],
            }
            errors.append(
                {
                    "repo": record["repo"],
                    "sha": record["sha"],
                    "job": record["job"],
                    "stage": "verify",
                    "code": verification["code"],
                    "reason": verification["reason"],
                }
            )
            continue

        try:
            status_record = _post_status.post_status(
                job=record["job"],
                verification=verification,
                dry_run=dry_run,
                transport=status_transport,
                env=status_env,
                target_url=unit["item"].get("url", ""),
            )
            record["github_status"] = status_record
        except Exception as exc:
            payload = _error_payload(exc)
            record["status"] = STATUS_ERROR
            record["stage"] = "verify"
            record["error"] = payload
            record["github_status"] = {
                "posted": False,
                "dry_run": dry_run,
                "error": payload["code"],
            }
            errors.append(
                {
                    "repo": record["repo"],
                    "sha": record["sha"],
                    "job": record["job"],
                    "stage": "verify",
                    **payload,
                }
            )
            continue

        record["status"] = STATUS_SUCCESS
        record["stage"] = "verify"

    # ---- compare ----
    groups: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        record = unit.get("record")
        if isinstance(record, dict) and record["status"] == STATUS_SUCCESS:
            groups.setdefault(unit["repo"], []).append(unit)

    comparisons: dict[str, Any] = {}
    for repo, group in groups.items():
        bee_records = [
            {
                "sha": unit["sha"],
                "job": _job_name(unit["job"]),
                "state": "passed",
                "exit_code": 0,
            }
            for unit in group
        ]
        try:
            actions_payload = _actions_lookup(config.get("actions"), repo, bee_records)
            comparison = _compare.compare(bee_records, actions_payload)
        except Exception as exc:
            payload = _error_payload(exc)
            for unit in group:
                record = unit["record"]
                record["status"] = STATUS_ERROR
                record["stage"] = "compare"
                record["error"] = payload
                errors.append(
                    {
                        "repo": record["repo"],
                        "sha": record["sha"],
                        "job": record["job"],
                        "stage": "compare",
                        **payload,
                    }
                )
            continue

        comparisons[repo] = comparison
        rows = {
            (str(row.get("sha", "")).lower(), row.get("job")): row
            for row in comparison.get("rows", [])
            if isinstance(row, Mapping)
        }
        for unit in group:
            record = unit["record"]
            row = rows.get((unit["sha"].lower(), record["job"]))
            record["comparison"] = row
            record["verdict"] = row.get("verdict") if isinstance(row, Mapping) else "inconclusive"
            record["stage"] = "compare"

    jobs.sort(key=lambda record: (record["repo"], record["sha"], record["job"]))
    errors.sort(
        key=lambda entry: (
            str(entry.get("repo", "")),
            str(entry.get("sha", "")),
            str(entry.get("job", "")),
            str(entry.get("stage", "")),
        )
    )
    summary = _summary(jobs)
    overall = "ok" if summary["error"] == 0 else "error"
    return _report(
        dry_run=dry_run,
        live=live,
        repos=slugs,
        status=overall,
        stage="compare" if groups else ("verify" if units else "dispatch"),
        poll=poll_result,
        jobs=jobs,
        comparisons=comparisons,
        errors=errors,
    )


__all__ = [
    "DRY_RUN_TOKEN",
    "PipelineConfigError",
    "PipelineError",
    "SCHEMA_VERSION",
    "TOOL",
    "run",
]
