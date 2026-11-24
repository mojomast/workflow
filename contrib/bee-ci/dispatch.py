#!/usr/bin/env python3
"""Submit bee-run CI work items to the launcher ``/v1`` API.

The poller emits work items carrying a repository, a head SHA and a job taken
from the checked-in manifest. This module turns each item into one launcher
request and returns a small result record per submission. The HTTP transport
is injected, so tests never open a socket.

Two invariants matter more than the wire shape:

* Every submission mints a fresh ``task_id``. Reusing a job name as the id let
  one parallel dispatch supersede another (FL-2); ids are never derived from
  the job alone.
* The launcher token is read from the environment only. It is placed in the
  Authorization header and nowhere else: not in a work item, result, payload,
  exception or repr. Every error path is reduced to a fixed, scrubbed message.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import socket
import threading
import urllib.error
import urllib.request
import uuid
from typing import Any, Iterable, Mapping, Sequence

try:
    from . import manifest as _manifest
except ImportError:  # loaded as a top-level module from contrib/bee-ci
    try:
        import manifest as _manifest
    except ImportError:  # manifest helpers stay optional without jsonschema
        _manifest = None

API_PATH = "/v1/attempts"
DEFAULT_TIMEOUT = 20.0
DEFAULT_MODEL = "deepseek-v4.1-flash"
DEFAULT_JOB_TIMEOUT_S = 900
DEFAULT_ASSIGNED_FILE = "."
MODEL_ENV = "BEE_CI_MODEL"
TOKEN_ENV = "BEE_CI_LAUNCHER_TOKEN"
TOKEN_ENV_NAMES = (TOKEN_ENV, "BEE_LAUNCHER_TOKEN", "LAUNCHER_TOKEN")
TOKEN_ENV_VARS = TOKEN_ENV_NAMES
STATE_SUCCESS = "success"
STATE_ERROR = "error"
STATUS_SUCCESS = STATE_SUCCESS
STATUS_ERROR = STATE_ERROR

_FAILED_RESPONSE_STATES = frozenset(
    {"error", "errored", "failed", "failure", "rejected", "timeout", "timed_out", "timedout"}
)

_UNIQUE_LOCK = threading.Lock()
_UNIQUE_COUNTER = 0


class DispatchError(RuntimeError):
    """A safe dispatcher failure that never contains the launcher token."""

    def __init__(self, message: str, *, code: str = "dispatch_error"):
        super().__init__(message)
        self.code = code


def read_token(env: Mapping[str, str] | None = None) -> str | None:
    """Read the launcher token from the environment only."""
    source = os.environ if env is None else env
    for name in TOKEN_ENV_NAMES:
        value = source.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def read_model(env: Mapping[str, str] | None = None) -> str:
    """Return the configured default model, falling back to the built-in."""
    source = os.environ if env is None else env
    value = source.get(MODEL_ENV)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_MODEL


def scrub(text: Any, token: str | None) -> str:
    """Remove the launcher token and bearer headers from *text*."""
    value = "" if text is None else str(text)
    if token:
        for variant in {token, token.strip()}:
            if variant:
                value = value.replace(variant, "[redacted]")
    value = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [redacted]", value)
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DispatchError(f"{field} must be a non-empty string", code="invalid_work_item")
    return value.strip()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return cleaned or "job"


def new_task_id(job_name: str = "job") -> str:
    """Return a process-unique, non-empty task id for one submission."""
    global _UNIQUE_COUNTER
    with _UNIQUE_LOCK:
        _UNIQUE_COUNTER += 1
        sequence = _UNIQUE_COUNTER
    return (
        f"bee-{_slug(str(job_name))}-{os.getpid()}-{sequence}-"
        f"{uuid.uuid4().hex}"
    )


make_task_id = new_task_id
build_task_id = new_task_id
generate_task_id = new_task_id
task_id_for = new_task_id


def _job_name(job: Any) -> str:
    if isinstance(job, Mapping):
        name = job.get("name")
    else:
        name = job
    if not isinstance(name, str) or not name.strip():
        raise DispatchError("job name is missing", code="invalid_work_item")
    return name.strip()


def _job_spec(job: Any) -> dict[str, Any]:
    if isinstance(job, Mapping):
        return dict(job)
    return {"name": _job_name(job)}


class WorkItem(Mapping[str, Any]):
    """One ``(repo, head_sha, job)`` unit emitted by the poller."""

    __slots__ = ("repo", "head_sha", "job")

    def __init__(self, repo: Any, head_sha: Any, job: Any):
        object.__setattr__(self, "repo", _text(repo, "repo"))
        object.__setattr__(self, "head_sha", _text(head_sha, "head_sha"))
        _job_name(job)
        object.__setattr__(self, "job", job)

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "WorkItem":
        if not isinstance(record, Mapping):
            raise DispatchError("work item must be an object", code="invalid_work_item")
        job = record.get("job", record.get("job_name"))
        return cls(
            repo=record.get("repo"),
            head_sha=record.get("head_sha", record.get("sha")),
            job=job,
        )

    @classmethod
    def from_job(cls, repo: Any, head_sha: Any, job: Any) -> "WorkItem":
        return cls(repo=repo, head_sha=head_sha, job=job)

    @property
    def job_name(self) -> str:
        return _job_name(self.job)

    @property
    def job_spec(self) -> dict[str, Any]:
        return _job_spec(self.job)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("WorkItem is immutable")

    def __getitem__(self, key: str) -> Any:
        if key == "repo":
            return self.repo
        if key in ("head_sha", "sha"):
            return self.head_sha
        if key in ("job", "job_spec"):
            return self.job if key == "job" else self.job_spec
        if key in ("job_name", "job_id"):
            return self.job_name
        raise KeyError(key)

    def __iter__(self):
        return iter(("repo", "head_sha", "job"))

    def __len__(self) -> int:
        return 3

    def __repr__(self) -> str:
        return f"WorkItem(repo={self.repo!r}, head_sha={self.head_sha!r}, job={_job_name(self.job)!r})"


class DispatchResult(dict):
    """A JSON-friendly result record with attribute access for convenience."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def to_dict(self) -> dict[str, Any]:
        return dict(self)

    as_dict = to_dict

    @property
    def ok(self) -> bool:
        return self.get("state") == STATE_SUCCESS


def _coerce_item(item: Any) -> WorkItem:
    if isinstance(item, WorkItem):
        return item
    if isinstance(item, Mapping):
        return WorkItem.from_dict(item)
    try:
        repo, head_sha, job = item
    except (TypeError, ValueError) as exc:
        raise DispatchError(
            "work item must be a WorkItem, object or (repo, head_sha, job) tuple",
            code="invalid_work_item",
        ) from None
    return WorkItem(repo=repo, head_sha=head_sha, job=job)


def _project_name(repo: str) -> str:
    """Return the launcher project name from ``owner/name`` or a bare name."""
    return repo.rsplit("/", 1)[-1] or repo


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _job_commands(job: Mapping[str, Any]) -> list[str]:
    commands = _string_list(job.get("command"))
    if not commands:
        commands = _string_list(job.get("commands"))
    return commands


def _job_assigned_files(job: Mapping[str, Any]) -> list[str]:
    for key in ("leased_paths", "assigned_files", "lease", "paths"):
        paths = _string_list(job.get(key))
        if paths:
            return paths
    workdir = job.get("workdir")
    if isinstance(workdir, str) and workdir.strip():
        return [workdir.strip()]
    return [DEFAULT_ASSIGNED_FILE]


def _job_timeout(job: Mapping[str, Any]) -> int:
    timeout = job.get("timeout_s")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        return DEFAULT_JOB_TIMEOUT_S
    return timeout


def build_brief(item: WorkItem) -> dict[str, Any]:
    """Build a launcher brief from the manifest job carried by *item*."""
    job = item.job if isinstance(item.job, Mapping) else {"name": item.job_name}
    name = item.job_name
    workdir = job.get("workdir")
    workdir = workdir.strip() if isinstance(workdir, str) and workdir.strip() else "."

    acceptance = [
        f"The {name} job runs each command exactly as declared from {workdir}.",
        f"The {name} job reports the exit code of every command step.",
        f"Every {name} command step exits with status 0.",
    ]

    return {
        "objective": (
            f"Run the {name} job for {_project_name(item.repo)}: execute its "
            f"commands exactly as listed from {workdir} and report the exit "
            f"codes."
        ),
        "project": _project_name(item.repo),
        "source_rev": item.head_sha,
        "commands": _job_commands(job),
        "assigned_files": _job_assigned_files(job),
        "acceptance": acceptance,
        "budget": {"timeout_s": _job_timeout(job)},
    }


def build_payload(
    item: WorkItem, task_id: str, *, model: str | None = None
) -> dict[str, Any]:
    """Build the launcher request body. The token is never part of it."""
    original_job: Any = item.job
    if isinstance(original_job, Mapping):
        original_job = dict(original_job)
    return {
        "brief": build_brief(item),
        "model": model or DEFAULT_MODEL,
        "task_id": task_id,
        "repo": item.repo,
        "head_sha": item.head_sha,
        "sha": item.head_sha,
        "job": original_job,
        "job_name": item.job_name,
        "job_spec": item.job_spec,
    }


def _result(
    item: WorkItem,
    task_id: str,
    state: str,
    *,
    code: str = "",
    error: str | None = None,
    attempt_id: str | None = None,
    status_code: int | None = None,
) -> DispatchResult:
    ok = state == STATE_SUCCESS
    return DispatchResult(
        task_id=task_id,
        repo=item.repo,
        head_sha=item.head_sha,
        sha=item.head_sha,
        job=item.job_name,
        job_name=item.job_name,
        job_id=item.job_name,
        job_spec=item.job_spec,
        state=state,
        status=state,
        ok=ok,
        submitted=ok,
        code=code,
        error=error,
        attempt_id=attempt_id,
        status_code=status_code,
    )


def _endpoint(base_url: str | None, path: str) -> str:
    path = path or API_PATH
    if not path.startswith("/"):
        path = "/" + path
    if base_url and not path.startswith(("http://", "https://")):
        return base_url.rstrip("/") + path
    return path


def _bind_call(function: Any, candidates: Sequence[tuple[tuple[Any, ...], dict[str, Any]]]) -> Any:
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
        raise DispatchError("injected transport has an unsupported call signature")

    for args, kwargs in candidates:
        try:
            return function(*args, **kwargs)
        except TypeError:
            continue
    raise DispatchError("injected transport call failed", code="transport_error")


def _invoke_transport(
    transport: Any,
    *,
    url: str,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    token: str,
) -> Any:
    post = getattr(transport, "post", None)
    if callable(post):
        return _bind_call(
            post,
            (
                ((url, payload), {"headers": headers, "timeout": timeout}),
                ((url, payload), {"timeout": timeout}),
                ((url, payload), {}),
                ((path, payload), {"headers": headers, "timeout": timeout}),
                ((url, payload, headers), {"timeout": timeout}),
                ((url, payload, headers, timeout), {}),
                ((url,), {"json": payload, "headers": headers, "timeout": timeout}),
                ((path,), {"json": payload, "headers": headers, "timeout": timeout}),
                ((payload, token), {}),
                ((payload,), {}),
            ),
        )

    for name in ("submit", "dispatch", "send", "request", "post_json"):
        function = getattr(transport, name, None)
        if not callable(function):
            continue
        return _bind_call(
            function,
            (
                ((payload, token), {}),
                ((url, payload), {"headers": headers, "timeout": timeout}),
                ((url, payload, headers, timeout), {}),
                ((url, payload, token), {}),
                ((payload,), {"headers": headers, "timeout": timeout}),
                ((payload,), {}),
            ),
        )

    if callable(transport):
        return _bind_call(
            transport,
            (
                ((payload, token), {}),
                ((url, payload), {"headers": headers, "timeout": timeout}),
                ((url, payload, headers, timeout), {}),
                ((url, payload, token), {}),
                ((payload, headers, timeout), {}),
                ((payload,), {}),
            ),
        )

    raise DispatchError("transport must be callable or provide post()", code="no_transport")


def _status_code(response: Any) -> int | None:
    for attribute in ("status_code", "status", "code"):
        value = getattr(response, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    if isinstance(response, Mapping):
        for key in ("status_code", "status", "code"):
            value = response.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def _read_response(response: Any) -> Any:
    if response is None:
        return {}
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, (bytes, bytearray)):
        raw = bytes(response)
    else:
        raw = None
        reader = getattr(response, "read", None)
        if callable(reader):
            raw = reader()
        elif hasattr(response, "json") and callable(response.json):
            return response.json()

    if raw is not None:
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        except (UnicodeDecodeError, ValueError, TypeError):
            raise DispatchError("launcher returned an unreadable response", code="launcher_error") from None
    return response


def _response_error(data: Any) -> bool:
    if not isinstance(data, Mapping):
        return False
    if data.get("ok") is False:
        return True
    if data.get("error"):
        return True
    state = data.get("state", data.get("status"))
    if isinstance(state, str) and state.strip().lower() in _FAILED_RESPONSE_STATES:
        return True
    return False


def _attempt_id(data: Any, token: str | None) -> str | None:
    if not isinstance(data, Mapping):
        return None
    value = data.get("attempt_id", data.get("attempt", data.get("id")))
    if value is None:
        return None
    return scrub(value, token)


def _decode_json(raw: Any) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    except (UnicodeDecodeError, ValueError, TypeError):
        return None


def _launcher_error_text(data: Any) -> str | None:
    """Extract the launcher's own error text from a response, if present."""
    if isinstance(data, Mapping):
        for key in ("error", "detail", "message", "reason"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            nested = _launcher_error_text(value)
            if nested:
                return nested
        return None
    if isinstance(data, (list, tuple)):
        for entry in data:
            nested = _launcher_error_text(entry)
            if nested:
                return nested
        return None
    for attribute in ("error", "detail", "message"):
        value = getattr(data, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def dispatch(
    item: Any,
    *,
    transport: Any = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    env: Mapping[str, str] | None = None,
    path: str = API_PATH,
    model: str | None = None,
) -> DispatchResult | list[DispatchResult]:
    """Submit one work item, or every item in a list/tuple."""
    if isinstance(item, (list, tuple, set, frozenset)) or (
        isinstance(item, Iterable) and not isinstance(item, (str, bytes, Mapping, WorkItem))
    ):
        return dispatch_all(
            item,
            transport=transport,
            base_url=base_url,
            timeout=timeout,
            env=env,
            path=path,
            model=model,
        )

    work = _coerce_item(item)
    task_id = new_task_id(work.job_name)
    token = read_token(env)
    if not token:
        return _result(
            work,
            task_id,
            STATE_ERROR,
            code="missing_token",
            error=f"launcher token is not set; export {TOKEN_ENV}",
        )

    source = os.environ if env is None else env
    if base_url is None:
        base_url = source.get("BEE_CI_LAUNCHER_URL") or ""
    url = _endpoint(base_url, path)
    payload = build_payload(
        work, task_id, model=model or read_model(env)
    )
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "bee-run-ci-dispatcher",
        "Authorization": f"Bearer {token}",
    }

    if transport is None:
        transport = HttpTransport(base_url=base_url, timeout=timeout)

    try:
        response = _invoke_transport(
            transport,
            url=url,
            path=path,
            payload=payload,
            headers=headers,
            timeout=timeout,
            token=token,
        )
    except (TimeoutError, socket.timeout):
        return _result(
            work,
            task_id,
            STATE_ERROR,
            code="timeout",
            error=f"launcher request timed out after {timeout:g}s",
        )
    except DispatchError as exc:
        return _result(
            work,
            task_id,
            STATE_ERROR,
            code=getattr(exc, "code", "dispatch_error") or "dispatch_error",
            error=scrub(str(exc) or type(exc).__name__, token),
        )
    except Exception as exc:
        return _result(
            work,
            task_id,
            STATE_ERROR,
            code="timeout" if isinstance(exc, TimeoutError) else "transport_error",
            error=f"launcher transport failed ({type(exc).__name__})",
        )

    status_code = _status_code(response)
    try:
        data = _read_response(response)
    except DispatchError as exc:
        return _result(
            work,
            task_id,
            STATE_ERROR,
            code=getattr(exc, "code", "launcher_error"),
            error=scrub(str(exc) or type(exc).__name__, token),
            status_code=status_code,
        )

    if status_code is not None and status_code >= 400:
        message = _launcher_error_text(data)
        return _result(
            work,
            task_id,
            STATE_ERROR,
            code="launcher_error",
            error=scrub(message or f"launcher returned HTTP {status_code}", token),
            status_code=status_code,
        )

    if _response_error(data):
        message = _launcher_error_text(data)
        return _result(
            work,
            task_id,
            STATE_ERROR,
            code="launcher_error",
            error=scrub(message or "launcher reported an error", token),
            status_code=status_code,
        )

    return _result(
        work,
        task_id,
        STATE_SUCCESS,
        attempt_id=_attempt_id(data, token),
        status_code=status_code,
    )


dispatch_one = dispatch
dispatch_item = dispatch
dispatch_work_item = dispatch
submit = dispatch
submit_item = dispatch
submit_work_item = dispatch


def dispatch_all(
    items: Iterable[Any],
    *,
    transport: Any = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    env: Mapping[str, str] | None = None,
    path: str = API_PATH,
    model: str | None = None,
) -> list[DispatchResult]:
    results: list[DispatchResult] = []
    for item in items:
        result = dispatch(
            item,
            transport=transport,
            base_url=base_url,
            timeout=timeout,
            env=env,
            path=path,
            model=model,
        )
        if isinstance(result, list):
            results.extend(result)
        else:
            results.append(result)
    return results


dispatch_items = dispatch_all
dispatch_work_items = dispatch_all
dispatch_many = dispatch_all
dispatch_workflow = dispatch_all
submit_all = dispatch_all


def work_items_for_repo(
    repo: str, head_sha: str, jobs_dir: str | os.PathLike[str] | None = None
) -> list[WorkItem]:
    """Load one manifest and return its bee-eligible jobs as work items."""
    if _manifest is None:
        raise DispatchError(
            "manifest support is unavailable; install jsonschema",
            code="manifest_unavailable",
        )
    document = _manifest.load_repo(repo, jobs_dir)
    return [
        WorkItem(repo=document["repo"], head_sha=head_sha, job=job)
        for job in document["jobs"]
        if _manifest.is_bee_eligible(job)
    ]


def dispatch_repo(
    repo: str,
    head_sha: str,
    *,
    transport: Any = None,
    jobs_dir: str | os.PathLike[str] | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    env: Mapping[str, str] | None = None,
    path: str = API_PATH,
    model: str | None = None,
) -> list[DispatchResult]:
    return dispatch_all(
        work_items_for_repo(repo, head_sha, jobs_dir),
        transport=transport,
        base_url=base_url,
        timeout=timeout,
        env=env,
        path=path,
        model=model,
    )


dispatch_manifest = dispatch_repo
work_items = work_items_for_repo
load_work_items = work_items_for_repo
LauncherError = DispatchError


class HttpTransport:
    """Small stdlib launcher transport used only when nothing is injected."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        opener: Any = None,
    ):
        self.base_url = (
            base_url or os.environ.get("BEE_CI_LAUNCHER_URL") or ""
        ).rstrip("/")
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def __repr__(self) -> str:
        return f"HttpTransport(configured={bool(self.base_url)})"

    def post(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        if url.startswith(("http://", "https://")):
            target = url
        elif self.base_url:
            target = self.base_url + url
        else:
            raise DispatchError("launcher endpoint is not configured", code="no_endpoint")

        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        request = urllib.request.Request(
            target, data=body, headers=dict(headers), method="POST"
        )
        try:
            with self._opener(request, timeout=timeout) as response:
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = b""
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            message = _launcher_error_text(_decode_json(raw))
            raise DispatchError(
                message or f"launcher returned HTTP {exc.code}",
                code="launcher_error",
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DispatchError(
                f"launcher request failed ({type(exc).__name__})",
                code="timeout" if isinstance(exc, (TimeoutError, socket.timeout)) else "transport_error",
            ) from None

        data = _decode_json(raw)
        if isinstance(status, int) and status >= 400:
            message = _launcher_error_text(data)
            raise DispatchError(
                message or f"launcher returned HTTP {status}",
                code="launcher_error",
            )
        if not raw:
            return {}
        if data is None:
            raise DispatchError(
                "launcher returned an unreadable response", code="launcher_error"
            ) from None
        return data


UrllibTransport = HttpTransport
LauncherTransport = HttpTransport
HttpLauncher = HttpTransport


class Dispatcher:
    """Reusable dispatcher that keeps the token out of its own state."""

    def __init__(
        self,
        transport: Any = None,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        env: Mapping[str, str] | None = None,
        path: str = API_PATH,
        model: str | None = None,
    ):
        self.transport = transport
        self.base_url = base_url
        self.timeout = timeout
        self.path = path
        self._env = env
        self._model = model

    def __repr__(self) -> str:
        return (
            f"Dispatcher(transport={type(self.transport).__name__}, "
            f"base_url={'configured' if self.base_url else self.base_url!r}, "
            f"timeout={self.timeout!r})"
        )

    def dispatch(self, item: Any) -> DispatchResult | list[DispatchResult]:
        return dispatch(
            item,
            transport=self.transport,
            base_url=self.base_url,
            timeout=self.timeout,
            env=self._env,
            path=self.path,
            model=self._model,
        )

    def dispatch_all(self, items: Iterable[Any]) -> list[DispatchResult]:
        return dispatch_all(
            items,
            transport=self.transport,
            base_url=self.base_url,
            timeout=self.timeout,
            env=self._env,
            path=self.path,
            model=self._model,
        )


LauncherDispatcher = Dispatcher
BeeCiDispatcher = Dispatcher


__all__ = [
    "API_PATH",
    "BeeCiDispatcher",
    "DEFAULT_ASSIGNED_FILE",
    "DEFAULT_JOB_TIMEOUT_S",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT",
    "DispatchError",
    "DispatchResult",
    "Dispatcher",
    "HttpLauncher",
    "HttpTransport",
    "LauncherDispatcher",
    "LauncherError",
    "LauncherTransport",
    "STATE_ERROR",
    "STATE_SUCCESS",
    "STATUS_ERROR",
    "STATUS_SUCCESS",
    "TOKEN_ENV",
    "TOKEN_ENV_NAMES",
    "TOKEN_ENV_VARS",
    "MODEL_ENV",
    "UrllibTransport",
    "WorkItem",
    "build_brief",
    "build_payload",
    "build_task_id",
    "dispatch",
    "dispatch_all",
    "dispatch_item",
    "dispatch_items",
    "dispatch_many",
    "dispatch_manifest",
    "dispatch_one",
    "dispatch_repo",
    "dispatch_work_item",
    "dispatch_work_items",
    "dispatch_workflow",
    "generate_task_id",
    "load_work_items",
    "make_task_id",
    "new_task_id",
    "read_model",
    "read_token",
    "scrub",
    "submit",
    "submit_all",
    "submit_item",
    "submit_work_item",
    "task_id_for",
    "work_items",
    "work_items_for_repo",
]
