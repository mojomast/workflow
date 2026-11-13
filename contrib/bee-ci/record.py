"""Bridge pipeline run results into the bee-CI evidence index and report.

``record.py`` is deliberately thin.  It does not re-implement the frozen
``bee-ci/evidence/v1`` contract; every append goes through
:func:`evidence.append`.  It also does not re-implement the HTML report; it
calls :func:`report.render.render`.

Honesty rules:

* a job with a recorded failing step or a non-zero exit code is ``failure``;
* a job that reports ``error`` stays ``error``;
* a job with no usable state or no passing evidence is ``pending``;
* absent fields are stored as ``null`` (the evidence layer's decision), never
  guessed from the repo, SHA or job name.

The accepted result shape is a mapping with a ``jobs`` list, where each job
has ``job``, ``state``, ``exit_codes`` and optional timestamps/result path.
A single job mapping, a list of results, and the compare.py ``records`` shape
are accepted too.  ``steps`` with ``exit_code`` fields are understood as well.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # imported as part of the bee-ci package
    from . import evidence as _evidence
    from .report.render import render as _render
except ImportError:  # imported as a top-level module from contrib/bee-ci
    import evidence as _evidence

    try:
        from report.render import render as _render
    except ImportError:  # report/ is a namespace directory on some layouts
        sys.path.insert(0, str(Path(__file__).resolve().parent / "report"))
        from render import render as _render

SUCCESS = "success"
FAILURE = "failure"
ERROR = "error"
PENDING = "pending"

_PASS_STATES = frozenset({"success", "passed", "pass", "ok", "green", "succeeded"})
_FAIL_STATES = frozenset({"failure", "failed", "fail", "red"})
_ERROR_STATES = frozenset(
    {
        "error",
        "errored",
        "cancelled",
        "canceled",
        "timed_out",
        "timedout",
        "timeout",
    }
)
_PENDING_STATES = frozenset(
    {
        "pending",
        "queued",
        "in_progress",
        "in-progress",
        "running",
        "neutral",
        "skipped",
        "unknown",
        "",
    }
)

_JOB_KEYS = ("job", "job_name", "job_id", "name", "id")
_SHA_KEYS = ("head_sha", "sha", "head")
_STATE_KEYS = ("state", "status", "conclusion", "result")
_LISTS = ("jobs", "results", "records", "outcomes")


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _first(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping:
            value = mapping[key]
            if value is not None:
                return value
    return None


def _explicit_state(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if token in _PASS_STATES:
        return SUCCESS
    if token in _FAIL_STATES:
        return FAILURE
    if token in _ERROR_STATES:
        return ERROR
    if token in _PENDING_STATES:
        return PENDING
    return None


def _raw_state(job: Mapping[str, Any]) -> Any:
    value = _first(job, _STATE_KEYS)
    if value is not None:
        return value
    verification = job.get("verification")
    if isinstance(verification, Mapping):
        return _first(verification, ("status", "state", "conclusion"))
    return None


def _exit_source(job: Mapping[str, Any]) -> Any:
    if "exit_codes" in job:
        return job.get("exit_codes")
    if "exit_code" in job:
        return [
            {
                "step": job.get("step", job.get("name")),
                "exit_code": job.get("exit_code"),
            }
        ]
    if "steps" in job:
        return job.get("steps")
    return None


def _exit_outcome(raw: Any) -> str:
    """Return ``pass``, ``fail``, ``unknown`` or ``none`` for recorded steps."""
    if raw is None:
        return "none"
    if not isinstance(raw, list):
        return "unknown"
    if not raw:
        return "none"
    outcome = "pass"
    for item in raw:
        if not isinstance(item, Mapping):
            outcome = "unknown"
            continue
        code = item.get("exit_code")
        if type(code) is not int:
            outcome = "unknown"
        elif code != 0:
            return "fail"
    return outcome


def _exit_codes(raw: Any) -> list[dict[str, Any]] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    codes: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        step = item.get("step", item.get("name"))
        code = item.get("exit_code")
        codes.append(
            {
                "step": step if isinstance(step, str) and step else None,
                "exit_code": code
                if type(code) is int
                else None,
            }
        )
    return codes


def _verified(job: Mapping[str, Any]) -> bool | None:
    value = job.get("verified")
    if isinstance(value, bool):
        return value
    verification = job.get("verification")
    if isinstance(verification, Mapping):
        value = verification.get("verified")
        if isinstance(value, bool):
            return value
    return None


def _resolve_state(job: Mapping[str, Any]) -> str:
    """Resolve one honest state from the recorded outcome."""
    explicit = _explicit_state(_raw_state(job))
    outcome = _exit_outcome(_exit_source(job))
    verified = _verified(job)

    if explicit == ERROR:
        return ERROR
    if explicit == FAILURE:
        return FAILURE
    if outcome == "fail":
        return FAILURE
    if explicit == PENDING:
        return PENDING
    if verified is False:
        return PENDING
    if explicit == SUCCESS:
        if outcome == "unknown":
            return PENDING
        return SUCCESS
    if outcome == "pass":
        return SUCCESS
    if outcome == "unknown":
        return PENDING
    return PENDING


def _pick(job: Mapping[str, Any], overrides: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = overrides.get(key)
        if value is not None:
            return value
    return _first(job, keys)


def _entry(job: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "repo": _pick(job, overrides, ("repo",)),
        "head_sha": _pick(job, overrides, _SHA_KEYS),
        "job": _pick(job, overrides, _JOB_KEYS),
        "source": _pick(job, overrides, ("source",)),
        "state": _resolve_state(job),
        "exit_codes": _exit_codes(_exit_source(job)),
        "started_at": _pick(job, overrides, ("started_at",)),
        "finished_at": _pick(job, overrides, ("finished_at",)),
        "result_path": _pick(job, overrides, ("result_path",)),
    }


def _merge(base: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(item)
    return merged


def _iter_jobs(result: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(result, Mapping):
        for key in _LISTS:
            value = result.get(key)
            if isinstance(value, list):
                base = {name: field for name, field in result.items() if name != key}
                for item in value:
                    if isinstance(item, Mapping):
                        yield _merge(base, item)
                    else:
                        yield base
                return
        yield result
        return
    if isinstance(result, (list, tuple)):
        for item in result:
            yield from _iter_jobs(item)
        return
    raise TypeError("result must be a mapping or a list of mappings")


def _resolve_paths(result: Any, index_path: Any, index: Any) -> tuple[Any, Any]:
    if isinstance(result, (str, Path)) and isinstance(index_path, Mapping):
        result, index_path = index_path, result
    if index_path is None:
        index_path = index
    if index_path is None:
        raise TypeError("an evidence index path is required")
    return result, index_path


def record_result(
    result: Any,
    index_path: str | Path | None = None,
    *,
    index: str | Path | None = None,
    repo: Any = None,
    head_sha: Any = None,
    job: Any = None,
    source: Any = None,
    started_at: Any = None,
    finished_at: Any = None,
    result_path: Any = None,
) -> int:
    """Append every job in *result* to the evidence index.

    Returns the number of entries actually appended.  Re-recording the same
    ``(repo, head_sha, job, source)`` is a no-op, because ``evidence.append``
    owns the dedupe key and the atomic write.
    """
    result, index_path = _resolve_paths(result, index_path, index)
    overrides = {
        "repo": repo,
        "head_sha": head_sha,
        "job": job,
        "source": source,
        "started_at": started_at,
        "finished_at": finished_at,
        "result_path": result_path,
    }
    appended = 0
    for item in _iter_jobs(result):
        if _evidence.append(index_path, _entry(item, overrides)):
            appended += 1
    return appended


def render_report(index_path: Any, out_path: str | Path | None = None) -> str:
    """Render the evidence index with ``report/render.py``.

    ``index_path`` may be a path or an already-decoded document.  When
    ``out_path`` is given the HTML is also written there.
    """
    page = _render(index_path)
    if out_path is not None:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
    return page


def write_report(index_path: Any, out_path: str | Path | None = None) -> Path:
    """Render the index to *out_path* (default: same stem with .html)."""
    target = (
        Path(out_path)
        if out_path is not None
        else Path(str(index_path)).with_suffix(".html")
    )
    render_report(index_path, target)
    return target


def record_and_render(
    result: Any,
    index_path: str | Path,
    out_path: str | Path | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Record a result, then render (and optionally write) the report."""
    appended = record_result(result, index_path, **overrides)
    page = render_report(index_path, out_path)
    return {"appended": appended, "html": page}


def record_job(
    run: Any,
    index_path: str | Path | None = None,
    *,
    index: str | Path | None = None,
    **overrides: Any,
) -> bool:
    """Append one already-shaped run entry; returns whether it was new."""
    run, index_path = _resolve_paths(run, index_path, index)
    return _evidence.append(index_path, _entry(run, overrides))


def _load_result(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a pipeline run into bee-CI evidence")
    parser.add_argument("result", help="path to the pipeline run result JSON")
    parser.add_argument(
        "--index",
        default=str(Path("evidence") / "index.json"),
        help="evidence index path (default: evidence/index.json)",
    )
    parser.add_argument("--render", metavar="HTML", help="also write the rendered report")
    args = parser.parse_args(argv)

    appended = record_result(_load_result(args.result), args.index)
    page = render_report(args.index, args.render)
    summary = {
        "appended": appended,
        "index": args.index,
        "rendered": bool(page),
        "report": args.render,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


# Friendly aliases for callers that name the operation differently.
append = record_result
append_result = record_result
append_run = record_result
record = record_result
record_run = record_result
record_pipeline_result = record_result
render = render_report
render_index = render_report


if __name__ == "__main__":
    raise SystemExit(main())
