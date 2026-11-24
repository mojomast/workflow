#!/usr/bin/env python3
"""Shadow-runner CLI for the bee-CI phase 1 harness.

Wires the real adapters in one place and keeps every external effect
injectable:

* GitHub PR heads and Actions conclusions come from ``gh`` via subprocess;
* dispatch, capacity and result polling go to the launcher ``/v1`` API with
  the token read from ``BUNDLEBEES_LAUNCHER_TOKEN`` only;
* verified outcomes are appended to the evidence index through ``record.py``
  and rendered with the bundled report.

Dry-run is the default: it prints the plan and never constructs a launcher.
A live run requires the token and a successful capacity check, dispatches only
bee-eligible manifest legs, polls results with a bounded timeout and verifies
each one with ``verify_result.py``. Phase 1 never posts a commit status, and
any ``--post-status``-style flag is refused before any external call.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

try:  # imported as part of the bee-ci package
    from . import dispatch as _dispatch
    from . import manifest as _manifest
    from . import record as _record
    from . import verify_result as _verify_result
except ImportError:  # imported as a top-level module from contrib/bee-ci
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dispatch as _dispatch
    import manifest as _manifest
    import record as _record
    import verify_result as _verify_result

TOOL = "bee-ci-shadow-runner"
SCHEMA_VERSION = 1
TOKEN_ENV = "BUNDLEBEES_LAUNCHER_TOKEN"
URL_ENV = "BUNDLEBEES_LAUNCHER_URL"
KEY_ENV = "BEE_CI_RESULT_KEY"
HERMES_LAUNCHER_KEY = "plugins.entries.bundlebees.settings.launcher_url"
HERMES_ARGS = ("config", "get", HERMES_LAUNCHER_KEY)
DEFAULT_TIMEOUT = 60.0
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_INDEX = Path("evidence") / "index.json"
DEFAULT_REPORT = Path("evidence") / "report.html"

_PASS = "success"
_FAILURE = "failure"
_ERROR = "error"
_SKIPPED = "skipped"
_PENDING = "pending"
_PLANNED = "planned"
_NOT_RUN = "not_run"
_MISSING_REQUIRED_TOOL = "missing_required_tool"

DEFAULT_WORKDIR = "."
DEFAULT_JOB_TIMEOUT_S = 900

_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class ShadowError(RuntimeError):
    """A safe shadow-runner failure that never carries secrets or hosts."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "shadow_error",
        status: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_int(data: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
    return None


def _env_value(env: Mapping[str, str] | None, name: str) -> str | None:
    source = os.environ if env is None else env
    return _text(source.get(name))


def _manifest_names(jobs_dir: Any = None) -> tuple[str, ...]:
    directory = Path(jobs_dir) if jobs_dir is not None else _manifest.JOBS_DIR
    try:
        names = sorted(
            path.stem for path in directory.glob("*.yaml") if path.is_file()
        )
    except OSError:
        names = []
    return tuple(names) or tuple(_manifest.REPOS)


def _resolve_repo(repo: Any, jobs_dir: Any = None) -> tuple[str, str]:
    """Return ``(slug, manifest_name)`` for owner/name or a manifest name."""

    slug = _text(repo)
    if slug is None:
        raise ShadowError(
            "repo must be owner/name or a bare manifest name", code="invalid_repo"
        )
    slug = slug.strip("/")
    parts = slug.split("/") if slug else []
    if len(parts) == 1 and parts[0]:
        name = parts[0]
    elif len(parts) == 2 and all(parts):
        name = parts[1]
    else:
        raise ShadowError(
            "repo must be owner/name or a bare manifest name", code="invalid_repo"
        )
    known = _manifest_names(jobs_dir)
    if name not in known:
        raise ShadowError(
            f"unknown repository {name!r}; expected one of {', '.join(known)}",
            code="unknown_repo",
        )
    return slug, name


def _strip_quotes(value: str) -> str | None:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    return text or None


def _hermes_launcher_url(
    runner: Callable[[list[str]], Any] | None,
    env: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> str | None:
    """Resolve the launcher URL from hermes config, fail-closed to ``None``."""

    args = list(HERMES_ARGS)
    try:
        if runner is not None:
            outcome: Any = runner(args)
        else:
            completed = subprocess.run(
                ["hermes", *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=None if env is None else {**os.environ, **env},
            )
            if completed.returncode != 0:
                return None
            outcome = completed.stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if isinstance(outcome, str):
        return _strip_quotes(outcome)
    stdout = getattr(outcome, "stdout", None)
    if isinstance(stdout, str):
        return _strip_quotes(stdout)
    return None


def _head_sha(value: Any) -> str:
    sha = _text(value)
    if sha is None or not _SHA_RE.fullmatch(sha):
        raise ShadowError("PR head is not a full 40-character sha", code="invalid_head")
    return sha


def _job_spec_name(job: Any) -> str:
    name = job.get("name") if isinstance(job, Mapping) else None
    return name if isinstance(name, str) and name else "job"


def build_bee_brief(job: Any, *, repo: str | None = None) -> dict[str, Any]:
    """Build the bee brief for one manifest job from its command steps."""
    if not isinstance(job, Mapping):
        raise ShadowError("job must be a mapping", code="invalid_job")

    name = _job_spec_name(job)

    raw_commands = job.get("command")
    commands: list[str] = []
    if isinstance(raw_commands, list):
        commands = [
            step.strip()
            for step in raw_commands
            if isinstance(step, str) and step.strip()
        ]

    raw_workdir = job.get("workdir")
    workdir = (
        raw_workdir.strip()
        if isinstance(raw_workdir, str) and raw_workdir.strip()
        else DEFAULT_WORKDIR
    )

    raw_requires = job.get("requires")
    requires: list[str] = []
    if isinstance(raw_requires, list):
        requires = [
            tool.strip()
            for tool in raw_requires
            if isinstance(tool, str) and tool.strip()
        ]

    timeout_s = job.get("timeout_s", DEFAULT_JOB_TIMEOUT_S)
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, int) or timeout_s < 1:
        timeout_s = DEFAULT_JOB_TIMEOUT_S

    where = f" for {repo}" if repo else ""
    acceptance_criteria = [
        f"The {name} job runs every command step from {workdir}.",
        f"Every {name} command step exits with status 0.",
        f"The {name} job result records an exit code for each step.",
    ]
    if requires:
        acceptance_criteria.append(
            f"The {name} job runs only after these tools exist: "
            f"{', '.join(requires)}."
        )

    return {
        "objective": (
            f"Run the {name} job{where} by executing the manifest command "
            f"steps in order from {workdir} and report the result."
        ),
        "repo": repo,
        "job": name,
        "commands": commands,
        "workdir": workdir,
        "requires": requires,
        "timeout_s": timeout_s,
        "acceptance_criteria": acceptance_criteria,
    }


def _path_tool_checker(name: str) -> bool:
    """Default checker: ask the real PATH for the executable."""
    return shutil.which(name) is not None


def _tool_checker(config: Mapping[str, Any]) -> Callable[[str], bool]:
    for key in ("tool_checker", "which", "tool_exists"):
        checker = config.get(key)
        if callable(checker):
            return checker

    tools = config.get("tools")
    if isinstance(tools, Mapping):
        return lambda name: bool(tools.get(name))
    if isinstance(tools, (list, tuple, set, frozenset)):
        available = {str(tool) for tool in tools}
        return lambda name: name in available

    return _path_tool_checker


def _missing_required_tools(
    job: Any, checker: Callable[[str], bool]
) -> list[str]:
    requires = job.get("requires") if isinstance(job, Mapping) else None
    if not isinstance(requires, list):
        return []

    missing: list[str] = []
    for tool in requires:
        if not isinstance(tool, str) or not tool.strip():
            continue
        name = tool.strip()
        try:
            available = bool(checker(name))
        except Exception:
            available = False
        if not available:
            missing.append(name)
    return missing


def _mark_not_run(row: dict[str, Any], missing: list[str]) -> None:
    row["state"] = _NOT_RUN
    row["code"] = _MISSING_REQUIRED_TOOL
    row["missing_tools"] = list(missing)
    row["detail"] = "NOT RUN: missing required tool(s): " + ", ".join(missing)


class GitHubCLI:
    """GitHub adapter backed by ``gh`` subprocess calls, never a shell."""

    def __init__(
        self,
        gh: str = "gh",
        timeout: float = 30.0,
        runner: Callable[[list[str]], Any] | None = None,
    ):
        self._gh = gh
        self._timeout = timeout
        self._runner = runner

    def __repr__(self) -> str:
        return "GitHubCLI()"

    def _call(self, args: list[str]) -> Any:
        if self._runner is not None:
            return self._runner(args)
        try:
            completed = subprocess.run(
                [self._gh, *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (OSError, subprocess.SubprocessError):
            raise ShadowError("gh is unavailable", code="github_unavailable") from None
        if completed.returncode != 0:
            raise ShadowError(
                f"gh exited with code {completed.returncode}", code="github_error"
            )
        try:
            return json.loads(completed.stdout or "null")
        except (TypeError, ValueError):
            raise ShadowError("gh returned invalid JSON", code="github_invalid_json") from None

    def pr_head(self, repo: str, pr: int) -> dict[str, Any]:
        data = self._call(
            [
                "pr",
                "view",
                str(pr),
                "--repo",
                repo,
                "--json",
                "number,headRefOid,state,isDraft,title,url",
            ]
        )
        if not isinstance(data, Mapping):
            raise ShadowError("gh returned no PR head", code="github_error")
        return {
            "number": data.get("number", pr),
            "head_sha": _text(data.get("headRefOid")) or _text(data.get("head_sha")) or "",
            "state": _text(data.get("state")) or "open",
            "draft": bool(data.get("isDraft") or data.get("draft")),
            "title": _text(data.get("title")) or "",
            "url": _text(data.get("url")) or "",
        }

    def actions_conclusions(self, repo: str, head_sha: str) -> list[dict[str, Any]]:
        data = self._call(
            [
                "run",
                "list",
                "--repo",
                repo,
                "--commit",
                head_sha,
                "--limit",
                "100",
                "--json",
                "name,conclusion,headSha,status",
            ]
        )
        if not isinstance(data, list):
            return []
        return [dict(item) for item in data if isinstance(item, Mapping)]


class LauncherClient:
    """Launcher ``/v1`` adapter; the token never leaves the request header."""

    def __init__(
        self,
        base_url: str | None,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
        opener: Callable[..., Any] | None = None,
    ):
        self._base_url = (base_url or "").rstrip("/")
        self._token = token
        self._timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def __repr__(self) -> str:
        return f"LauncherClient(configured={bool(self._base_url)})"

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        if not self._base_url:
            raise ShadowError("launcher endpoint is not configured", code="no_endpoint")
        data = None
        headers = {"Accept": "application/json", "User-Agent": TOOL}
        if payload is not None:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            self._base_url + path, data=data, headers=headers, method=method
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ShadowError(
                f"launcher returned HTTP {exc.code}",
                code="launcher_error",
                status=exc.code,
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ShadowError("launcher request failed", code="launcher_error") from None
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ShadowError("launcher returned invalid JSON", code="launcher_error") from None

    def capacity(self) -> Any:
        return self._request("GET", "/v1/health")

    def dispatch(self, item: Mapping[str, Any]) -> dict[str, Any]:
        work = _dispatch.WorkItem.from_dict(item)
        transport = _dispatch.HttpTransport(
            self._base_url, timeout=self._timeout, opener=self._opener
        )
        result = _dispatch.dispatch(
            work,
            transport=transport,
            base_url=self._base_url,
            timeout=self._timeout,
            env={_dispatch.TOKEN_ENV: self._token},
        )
        if isinstance(result, list):
            result = result[0] if result else {}
        return dict(result) if isinstance(result, Mapping) else {}

    def attempt(self, task_id: str) -> Any:
        path = "/v1/attempts/" + urllib.parse.quote(str(task_id), safe="")
        return self._request("GET", path)

    def result(self, task_id: str) -> Any:
        path = (
            "/v1/attempts/"
            + urllib.parse.quote(str(task_id), safe="")
            + "/result"
        )
        try:
            return self._request("GET", path)
        except ShadowError as exc:
            if exc.status == 409:
                try:
                    self.attempt(task_id)
                except ShadowError:
                    pass
                return None
            raise


def _capacity_state(info: Any) -> tuple[bool, str | None]:
    """Read the launcher health body; pass only while active < max_concurrent."""

    if not isinstance(info, Mapping):
        return False, "capacity_unknown"
    maximum = _first_int(info, ("max_concurrent",))
    active = _first_int(info, ("active",))
    if maximum is None or active is None:
        return False, "capacity_unknown"
    if maximum <= 0:
        return False, "capacity_full"
    if active < maximum:
        return True, None
    return False, "capacity_full"


def _poll_result(
    launcher: Any,
    task_id: str,
    *,
    timeout: float,
    interval: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> Any:
    deadline = clock() + max(0.0, float(timeout))
    while True:
        payload = launcher.result(task_id)
        if payload is not None:
            return payload
        remaining = deadline - clock()
        if remaining <= 0:
            return None
        sleep(min(max(interval, 0.0), remaining))


def _exit_codes(payload: Any) -> list[dict[str, Any]] | None:
    if not isinstance(payload, Mapping):
        return None
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return None
    codes: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        name = step.get("name")
        code = step.get("exit_code")
        codes.append(
            {
                "step": name if isinstance(name, str) and name else None,
                "exit_code": code if type(code) is int else None,
            }
        )
    return codes or None


def _record_run(
    *,
    index_path: Path,
    report: dict[str, Any],
    repo_name: str,
    head_sha: str,
    job: str,
    state: str,
    payload: Any,
    result_path: Any = None,
) -> None:
    entry = {
        "repo": repo_name,
        "head_sha": head_sha,
        "job": job,
        "source": "bee",
        "state": state,
        "exit_codes": _exit_codes(payload),
        "result_path": result_path,
    }
    try:
        _record.record_job(entry, index_path=str(index_path))
    except Exception:
        report["record_error"] = "failed to append bee evidence"


def _render(index_path: Path, report_path: Path) -> str:
    if index_path.exists():
        return _record.render_report(str(index_path), str(report_path))
    empty = {"schema": "bee-ci/evidence/v1", "runs": []}
    return _record.render_report(empty, str(report_path))


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        _PASS: 0,
        _FAILURE: 0,
        _ERROR: 0,
        _SKIPPED: 0,
        _PENDING: 0,
        _PLANNED: 0,
        _NOT_RUN: 0,
    }
    for row in rows:
        state = row.get("state")
        if state in counts:
            counts[state] += 1
    return {"total": len(rows), **counts}


def run(config: Mapping[str, Any]) -> dict[str, Any]:
    """Plan or execute one shadow pass and return a JSON-friendly report."""
    if not isinstance(config, Mapping):
        raise ShadowError("config must be a mapping", code="invalid_config")

    repo, repo_name = _resolve_repo(config.get("repo"), config.get("jobs_dir"))
    try:
        pr = int(config.get("pr"))
    except (TypeError, ValueError):
        raise ShadowError("pr must be a positive integer", code="invalid_pr") from None
    if pr <= 0:
        raise ShadowError("pr must be a positive integer", code="invalid_pr")

    live = config.get("live") is True
    env = config.get("env")
    github = config.get("github")
    if github is None:
        github = GitHubCLI()

    try:
        document = _manifest.load_repo(repo_name, config.get("jobs_dir"))
    except Exception:
        raise ShadowError("cannot load the manifest", code="manifest_error") from None

    try:
        pr_info = github.pr_head(repo, pr)
    except ShadowError:
        raise
    except Exception:
        raise ShadowError("GitHub PR lookup failed", code="github_error") from None
    if not isinstance(pr_info, Mapping):
        raise ShadowError("GitHub PR lookup returned no data", code="github_error")
    head_sha = _head_sha(pr_info.get("head_sha"))

    rows: list[dict[str, Any]] = []
    specs: dict[str, Any] = {}
    checker = _tool_checker(config)
    for job in document.get("jobs", []):
        name = _job_spec_name(job)
        eligible = _manifest.is_bee_eligible(job)
        specs[name] = job
        row = {
            "job": name,
            "eligible": eligible,
            "eligibility": _text(job.get("runner")) or "github-only",
            "state": _PLANNED if eligible else _SKIPPED,
            "code": "planned" if eligible else "not_bee_eligible",
            "detail": "",
        }
        if eligible:
            missing = _missing_required_tools(job, checker)
            if missing:
                _mark_not_run(row, missing)
        rows.append(row)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL,
        "dry_run": not live,
        "live": live,
        "repo": repo,
        "manifest": repo_name,
        "pr": pr,
        "head_sha": head_sha,
        "pr_state": _text(pr_info.get("state")) or "open",
        "jobs": rows,
        "eligible": [row["job"] for row in rows if row["eligible"]],
        "excluded": [row["job"] for row in rows if not row["eligible"]],
        "actions": [],
        "posted_status": False,
        "status": _PLANNED,
        "evidence_index": None,
        "report_path": None,
        "summary": {},
    }

    if not live:
        report["summary"] = _summary(rows)
        return report

    token = _env_value(env, TOKEN_ENV)
    if not token:
        for row in rows:
            if row["eligible"] and row["state"] != _NOT_RUN:
                row["state"] = _SKIPPED
                row["code"] = "missing_token"
                row["detail"] = "launcher token is not set"
        report["status"] = _SKIPPED
        report["summary"] = _summary(rows)
        return report

    launcher = config.get("launcher")
    if launcher is None:
        base_url = _text(config.get("base_url")) or _env_value(env, URL_ENV)
        if not base_url:
            base_url = _hermes_launcher_url(config.get("hermes"), env)
        if not base_url:
            for row in rows:
                if row["eligible"] and row["state"] != _NOT_RUN:
                    row["state"] = _SKIPPED
                    row["code"] = "no_launcher_endpoint"
                    row["detail"] = "launcher endpoint is not configured"
            report["status"] = _SKIPPED
            report["summary"] = _summary(rows)
            return report
        launcher = LauncherClient(
            base_url,
            token,
            timeout=float(config.get("timeout") or DEFAULT_TIMEOUT),
            opener=config.get("opener"),
        )

    try:
        capacity = launcher.capacity()
    except Exception:
        capacity = None
        capacity_ok, capacity_code = False, "capacity_check_failed"
    else:
        capacity_ok, capacity_code = _capacity_state(capacity)

    if not capacity_ok:
        for row in rows:
            if row["eligible"] and row["state"] != _NOT_RUN:
                row["state"] = _SKIPPED
                row["code"] = capacity_code or "capacity_unknown"
                row["detail"] = "launcher capacity check did not pass"
        report["status"] = _SKIPPED
        report["summary"] = _summary(rows)
        return report

    actions = getattr(github, "actions_conclusions", None)
    if callable(actions):
        try:
            report["actions"] = actions(repo, head_sha) or []
        except Exception:
            report["actions"] = []
            report["actions_error"] = "GitHub Actions lookup failed"

    key = config.get("key")
    if key is None:
        key = _env_value(env, KEY_ENV)
    index_path = Path(config.get("evidence_index") or DEFAULT_INDEX)
    report_path = Path(config.get("report_path") or DEFAULT_REPORT)
    timeout = float(config.get("timeout") if config.get("timeout") is not None else DEFAULT_TIMEOUT)
    interval = float(config.get("poll_interval") if config.get("poll_interval") is not None else DEFAULT_POLL_INTERVAL)
    clock = config.get("clock") or time.monotonic
    sleep = config.get("sleep") or time.sleep

    for row in rows:
        if not row["eligible"] or row["state"] == _NOT_RUN:
            continue
        name = row["job"]
        missing = _missing_required_tools(specs[name], checker)
        if missing:
            _mark_not_run(row, missing)
            continue
        brief = build_bee_brief(specs[name], repo=repo)
        job_payload = dict(specs[name])
        job_payload["brief"] = brief
        item = {
            "repo": repo,
            "head_sha": head_sha,
            "job": job_payload,
            "brief": brief,
        }
        try:
            dispatched = launcher.dispatch(item)
        except Exception:
            dispatched = {}
            dispatch_error = True
        else:
            dispatch_error = False

        if not isinstance(dispatched, Mapping) or dispatched.get("state") != _dispatch.STATE_SUCCESS:
            row["state"] = _ERROR
            row["code"] = (
                "dispatch_failed"
                if dispatch_error
                else str(dispatched.get("code") or "dispatch_failed")
                if isinstance(dispatched, Mapping)
                else "dispatch_failed"
            )
            launcher_message = (
                _text(dispatched.get("error"))
                if isinstance(dispatched, Mapping)
                else None
            )
            row["detail"] = launcher_message or "launcher did not accept the work item"
            _record_run(
                index_path=index_path,
                report=report,
                repo_name=repo_name,
                head_sha=head_sha,
                job=name,
                state=_ERROR,
                payload=None,
            )
            continue

        task_id = _text(dispatched.get("attempt_id")) or _text(dispatched.get("task_id"))
        if not task_id:
            row["state"] = _ERROR
            row["code"] = "missing_task_id"
            row["detail"] = "launcher did not return a task id"
            _record_run(
                index_path=index_path,
                report=report,
                repo_name=repo_name,
                head_sha=head_sha,
                job=name,
                state=_ERROR,
                payload=None,
            )
            continue
        row["task_id"] = task_id

        poll_error = None
        try:
            payload = _poll_result(
                launcher,
                task_id,
                timeout=timeout,
                interval=interval,
                clock=clock,
                sleep=sleep,
            )
        except ShadowError as exc:
            payload = None
            poll_error = exc.code or "launcher_error"
        except Exception:
            payload = None
            poll_error = "launcher_error"

        if payload is None:
            row["state"] = _ERROR
            row["code"] = poll_error or "timeout"
            row["detail"] = (
                "result polling failed"
                if poll_error
                else "no result before the poll deadline"
            )
            _record_run(
                index_path=index_path,
                report=report,
                repo_name=repo_name,
                head_sha=head_sha,
                job=name,
                state=_ERROR,
                payload=None,
            )
            continue

        try:
            checked = _verify_result.verify_result(
                payload,
                expected_head=head_sha,
                expected_job=task_id,
                key=key,
            )
        except Exception:
            checked = None

        if checked is None:
            state, code, detail = _ERROR, "verification_error", "verification raised"
        elif checked.status == _verify_result.STATUS_SUCCESS:
            state, code, detail = _PASS, checked.code, checked.reason
        elif checked.status == _verify_result.STATUS_FAILURE:
            state, code, detail = _FAILURE, checked.code, checked.reason
        else:
            state, code, detail = _ERROR, checked.code, checked.reason

        row["state"] = state
        row["code"] = code
        row["detail"] = detail
        _record_run(
            index_path=index_path,
            report=report,
            repo_name=repo_name,
            head_sha=head_sha,
            job=name,
            state=state,
            payload=payload,
            result_path=config.get("result_path"),
        )

    try:
        _render(index_path, report_path)
    except Exception:
        report["render_error"] = "failed to render the report"
    report["evidence_index"] = str(index_path)
    report["report_path"] = str(report_path)

    states = {row["state"] for row in rows if row["eligible"]}
    if report.get("record_error") or report.get("render_error"):
        report["status"] = _ERROR
    elif states == {_PASS}:
        report["status"] = "ok"
    elif _ERROR in states:
        report["status"] = _ERROR
    elif _FAILURE in states:
        report["status"] = _FAILURE
    elif _NOT_RUN in states:
        report["status"] = _SKIPPED
    elif _SKIPPED in states:
        report["status"] = _SKIPPED
    else:
        report["status"] = _ERROR
    report["summary"] = _summary(rows)
    return report


def _exit_code(report: Mapping[str, Any]) -> int:
    if report.get("dry_run"):
        return 0
    status = report.get("status")
    if status == "ok":
        return 0
    if status == _SKIPPED:
        return 2
    return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bee-CI shadow pass (dry-run by default)"
    )
    parser.add_argument("--repo", required=True, help="owner/name or manifest name")
    parser.add_argument("--pr", required=True, type=int, help="pull request number")
    parser.add_argument(
        "--live",
        action="store_true",
        help="dispatch to the launcher (requires BUNDLEBEES_LAUNCHER_TOKEN)",
    )
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="evidence index path")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="rendered report path")
    parser.add_argument("--jobs-dir", default=None, help="override the manifest directory")
    parser.add_argument(
        "--launcher-url", default=None, help="launcher base URL (never printed)"
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument(
        "--post-status",
        "--post-commit-status",
        "--post-github-status",
        "--commit-status",
        "--github-status",
        "--status",
        dest="post_status",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    github: Any = None,
    launcher: Any = None,
    out: Any = None,
    err: Any = None,
    env: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
    tool_checker: Callable[[str], bool] | None = None,
    which: Callable[[str], bool] | None = None,
    tools: Any = None,
    hermes: Callable[[list[str]], Any] | None = None,
) -> int:
    """CLI entry point. Every adapter is injectable for offline tests."""
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    args = _parser().parse_args(argv)

    if args.post_status:
        print(
            "bee-ci shadow-runner: refusing to post a commit status in phase 1",
            file=err,
        )
        return 2

    config = {
        "repo": args.repo,
        "pr": args.pr,
        "live": args.live,
        "evidence_index": args.index,
        "report_path": args.report,
        "jobs_dir": args.jobs_dir,
        "base_url": args.launcher_url,
        "timeout": args.timeout,
        "poll_interval": args.poll_interval,
        "github": github,
        "launcher": launcher,
        "env": env,
        "opener": opener,
        "tool_checker": tool_checker,
        "which": which,
        "tools": tools,
        "hermes": hermes,
    }
    try:
        report = run(config)
    except ShadowError as exc:
        print(f"bee-ci shadow-runner: {exc}", file=err)
        print(
            json.dumps(
                {
                    "tool": TOOL,
                    "schema_version": SCHEMA_VERSION,
                    "status": _ERROR,
                    "code": exc.code,
                    "posted_status": False,
                },
                sort_keys=True,
            ),
            file=out,
        )
        return 2

    print(json.dumps(report, sort_keys=True, default=str), file=out)
    return _exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
