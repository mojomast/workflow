#!/usr/bin/env python3
"""Bee-run CI poller.

Runs from Hermes cron every 5-10 minutes. For each configured repo it lists
open pull requests, ignores drafts and anything closed or merged, and treats a
head SHA as a work item exactly once. New heads are remembered in a small JSON
state file. The launcher's live bee count decides whether a work item is
dispatched now or left on the persistent queue.

GitHub, the launcher and the clock are injected, so tests never touch the
network, a shell, or the real launcher. The default adapters are stdlib-only:
urllib for GitHub and either a configured HTTP launcher endpoint or a
configured launcher command passed through ``shlex`` (never ``shell=True``).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

DEFAULT_REPOS = (
    "mojomast/bundlebees",
    "mojomast/hermes-templeos",
    "mojomast/assetrizz-hermes",
    "mojomast/EOH",
)
DEFAULT_CAP = 3
STATE_VERSION = 1
GITHUB_API = "https://api.github.com"


class PollerError(RuntimeError):
    """Base class for safe, non-secret-bearing poller failures."""


class GitHubError(PollerError):
    pass


class LauncherError(PollerError):
    pass


class StateError(PollerError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _first_int(data: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalise_pr(repo: str, raw: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None

    number = _int_or_none(raw.get("number", raw.get("pr")))
    head = raw.get("head")
    sha = raw.get("head_sha") or raw.get("headRefOid")
    if not sha and isinstance(head, Mapping):
        sha = head.get("sha")
    if not sha and isinstance(raw.get("head"), str):
        sha = raw.get("head")
    if not isinstance(sha, str) or not sha.strip():
        return None
    sha = sha.strip()

    state = str(raw.get("state", "open")).strip().lower()
    merged = bool(
        raw.get("merged")
        or raw.get("merged_at")
        or state in {"merged", "closed", "draft"}
    )
    draft = bool(raw.get("draft") or raw.get("isDraft") or raw.get("is_draft"))

    title = raw.get("title")
    url = raw.get("html_url") or raw.get("url") or raw.get("permalink")

    return {
        "repo": repo,
        "pr": number or 0,
        "head_sha": sha,
        "state": state,
        "draft": draft,
        "merged": merged,
        "title": title if isinstance(title, str) else "",
        "url": url if isinstance(url, str) else "",
    }


def _skip_reason(pr: Mapping[str, Any]) -> str | None:
    if pr.get("state") != "open":
        return "closed_or_merged"
    if pr.get("merged"):
        return "closed_or_merged"
    if pr.get("draft"):
        return "draft"
    return None


def _item_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "repo": record.get("repo", ""),
        "pr": record.get("pr", 0),
        "head_sha": record.get("head_sha", ""),
        "title": record.get("title", ""),
        "url": record.get("url", ""),
        "status": record.get("status", ""),
    }


def _item_from_pr(pr: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "repo": pr["repo"],
        "pr": pr["pr"],
        "head_sha": pr["head_sha"],
        "title": pr["title"],
        "url": pr["url"],
    }


class StateStore:
    """Persistent dedupe state with an exclusive lock and atomic replacement."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()

    @contextlib.contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.path.with_name(self.path.name + ".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": STATE_VERSION, "queued": {}}
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateError(f"state is unreadable: {type(exc).__name__}") from None
        if not text.strip():
            return {"version": STATE_VERSION, "queued": {}}
        try:
            data = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise StateError(f"state is not valid JSON: {type(exc).__name__}") from None
        if isinstance(data, list):
            data = {
                "version": STATE_VERSION,
                "queued": {
                    str(sha): {
                        "head_sha": str(sha),
                        "repo": "",
                        "pr": 0,
                        "title": "",
                        "url": "",
                        "status": "queued",
                    }
                    for sha in data
                },
            }
        if not isinstance(data, dict):
            raise StateError("state is not an object")
        queued = data.setdefault("queued", {})
        if not isinstance(queued, dict):
            raise StateError("state queued entry is not an object")
        if not all(isinstance(value, dict) for value in queued.values()):
            raise StateError("state contains a non-object queued record")
        data.setdefault("version", STATE_VERSION)
        return data

    def save(self, data: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(
            prefix="." + self.path.name + ".",
            suffix=".tmp",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        except BaseException as exc:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            if isinstance(exc, OSError):
                raise StateError(f"state could not be written ({type(exc).__name__})") from None
            raise


class GitHubClient:
    """Minimal read-only GitHub PR client using urllib."""

    def __init__(
        self,
        token: str | None = None,
        api_base: str = GITHUB_API,
        timeout: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen

    def _request(self, repo: str, page: int) -> tuple[list[Any], Any]:
        quoted = urllib.parse.quote(repo, safe="/")
        url = (
            f"{self.api_base}/repos/{quoted}/pulls"
            f"?state=open&per_page=100&page={page}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "bee-run-ci-poller",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = response.read()
                link = response.headers.get("Link", "") if response.headers else ""
        except urllib.error.HTTPError as exc:
            raise GitHubError(f"{repo}: GitHub HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubError(f"{repo}: GitHub request failed ({type(exc).__name__})") from None
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise GitHubError(f"{repo}: GitHub returned invalid JSON ({type(exc).__name__})") from None
        if not isinstance(data, list):
            raise GitHubError(f"{repo}: GitHub returned a non-list payload")
        return data, link

    def list_open_prs(self, repo: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for page in range(1, 11):
            batch, link = self._request(repo, page)
            results.extend(batch)
            if len(batch) < 100:
                break
            if 'rel="next"' not in (link or ""):
                break
        return results


class HttpLauncher:
    """Launcher adapter for a configured HTTP endpoint (URL never printed)."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("BEE_CI_LAUNCHER_URL")
            or ""
        ).rstrip("/")
        self.token = token or os.environ.get("BEE_CI_LAUNCHER_TOKEN")
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen

    def _call(self, method: str, path: str, payload: Any = None) -> Any:
        if not self.base_url:
            raise LauncherError("launcher endpoint is not configured")
        url = self.base_url + path
        body = None
        headers = {"Accept": "application/json", "User-Agent": "bee-run-ci-poller"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LauncherError(f"launcher request failed ({type(exc).__name__})") from None
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise LauncherError(f"launcher returned invalid JSON ({type(exc).__name__})") from None

    def status(self) -> Any:
        return self._call("GET", "/status")

    def bee_count(self) -> Any:
        return self.status()

    def capacity(self) -> int | None:
        data = self.status()
        if isinstance(data, Mapping):
            return _first_int(data, ("max", "capacity", "limit", "max_active"))
        return None

    def dispatch(self, item: Mapping[str, Any]) -> Any:
        return self._call("POST", "/dispatch", dict(item))


class CommandLauncher:
    """Launcher adapter for configured commands, split with shlex and no shell."""

    def __init__(
        self,
        status_command: str | None = None,
        dispatch_command: str | None = None,
        timeout: float = 20.0,
    ):
        self.status_command = status_command or os.environ.get("BEE_CI_LAUNCHER_STATUS_CMD")
        self.dispatch_command = dispatch_command or os.environ.get("BEE_CI_LAUNCHER_DISPATCH_CMD")
        self.timeout = timeout

    def _run(self, command: str | None, extra: Sequence[str] = ()) -> Any:
        if not command:
            raise LauncherError("launcher command is not configured")
        argv = shlex.split(command) + [str(value) for value in extra]
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={"PATH": os.environ.get("PATH", "")},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LauncherError(f"launcher command failed ({type(exc).__name__})") from None
        if completed.returncode != 0:
            raise LauncherError(f"launcher command exited {completed.returncode}")
        output = completed.stdout.strip()
        if not output:
            return {}
        try:
            return json.loads(output)
        except ValueError:
            return output

    def status(self) -> Any:
        return self._run(self.status_command)

    def bee_count(self) -> Any:
        return self.status()

    def capacity(self) -> int | None:
        data = self.status()
        if isinstance(data, Mapping):
            return _first_int(data, ("max", "capacity", "limit", "max_active"))
        return None

    def dispatch(self, item: Mapping[str, Any]) -> Any:
        return self._run(self.dispatch_command, [json.dumps(item, sort_keys=True)])


class UnconfiguredLauncher:
    def status(self) -> Any:
        raise LauncherError("launcher is not configured")

    def bee_count(self) -> Any:
        raise LauncherError("launcher is not configured")

    def capacity(self) -> int | None:
        return None

    def dispatch(self, item: Mapping[str, Any]) -> Any:
        raise LauncherError("launcher is not configured")


def default_launcher(timeout: float = 20.0):
    if os.environ.get("BEE_CI_LAUNCHER_URL"):
        return HttpLauncher(timeout=timeout)
    if os.environ.get("BEE_CI_LAUNCHER_STATUS_CMD") or os.environ.get(
        "BEE_CI_LAUNCHER_DISPATCH_CMD"
    ):
        return CommandLauncher(timeout=timeout)
    return UnconfiguredLauncher()


def default_state_path() -> Path:
    configured = os.environ.get("BEE_CI_STATE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "state" / "bee-run" / "queued.json"


class Poller:
    """One poll: list open PRs, dedupe heads on disk, then dispatch or queue."""

    def __init__(
        self,
        repos: Sequence[str] | None = None,
        state_path: str | os.PathLike[str] | None = None,
        github: Any = None,
        launcher: Any = None,
        cap: int | None = None,
        clock: Callable[[], str] | None = None,
    ):
        self.repos = list(repos) if repos else list(DEFAULT_REPOS)
        if not all(isinstance(repo, str) and "/" in repo for repo in self.repos):
            raise PollerError("repos must be owner/name strings")
        self.store = StateStore(state_path or default_state_path())
        self.github = github if github is not None else GitHubClient()
        self.launcher = launcher if launcher is not None else default_launcher()
        if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap < 0):
            raise PollerError("cap must be a non-negative integer")
        self.cap = cap
        self.clock = clock or _utc_now

    def _launcher_snapshot(self) -> tuple[int | None, int, bool, str | None]:
        raw: Any = None
        maximum: int | None = None
        try:
            if hasattr(self.launcher, "status"):
                raw = self.launcher.status()
            elif hasattr(self.launcher, "bee_count"):
                raw = self.launcher.bee_count()
            else:
                raise LauncherError("launcher exposes no status")
            if isinstance(raw, Mapping):
                active = _first_int(raw, ("active", "bees", "busy", "count", "in_use"))
                maximum = _first_int(raw, ("max", "capacity", "limit", "max_active"))
                if active is None:
                    raise LauncherError("launcher status has no active count")
            else:
                active = _int_or_none(raw)
                if active is None:
                    raise LauncherError("launcher status is not a count")
            if active < 0:
                raise LauncherError("launcher active count is negative")
        except Exception as exc:
            return None, 0, False, type(exc).__name__

        cap = self.cap
        if cap is None and maximum is not None:
            cap = maximum
        if cap is None and hasattr(self.launcher, "capacity"):
            try:
                cap = _int_or_none(self.launcher.capacity())
            except Exception:
                cap = None
        if cap is None:
            cap = _int_or_none(os.environ.get("BEE_CI_CAP"))
        if cap is None:
            cap = DEFAULT_CAP
        if cap < 0:
            cap = 0
        return active, cap, True, None

    def _collect(
        self,
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        current: dict[str, dict[str, Any]] = {}
        skipped: list[dict[str, Any]] = []
        for repo in self.repos:
            try:
                rows = self.github.list_open_prs(repo)
            except PollerError:
                raise
            except Exception as exc:
                raise GitHubError(f"{repo}: PR lookup failed ({type(exc).__name__})") from None
            if not isinstance(rows, list):
                raise GitHubError(f"{repo}: PR lookup returned a non-list")
            for raw in rows:
                normalised = _normalise_pr(repo, raw)
                if normalised is None:
                    skipped.append({"repo": repo, "pr": 0, "reason": "missing_head_sha"})
                    continue
                reason = _skip_reason(normalised)
                if reason is not None:
                    skipped.append(
                        {
                            "repo": repo,
                            "pr": normalised["pr"],
                            "head_sha": normalised["head_sha"],
                            "reason": reason,
                        }
                    )
                    continue
                sha = normalised["head_sha"]
                if sha in current:
                    skipped.append(
                        {
                            "repo": repo,
                            "pr": normalised["pr"],
                            "head_sha": sha,
                            "reason": "duplicate_head",
                        }
                    )
                    continue
                current[sha] = normalised
        return current, skipped

    def poll(self) -> dict[str, Any]:
        with self.store.locked():
            state = self.store.load()
            queued = state["queued"]
            now = self.clock()
            current, skipped = self._collect()

            new_records: list[dict[str, Any]] = []
            for sha, pr in current.items():
                if sha in queued:
                    continue
                record = _item_from_pr(pr)
                record.update(
                    {
                        "status": "queued",
                        "first_seen": now,
                        "updated_at": now,
                    }
                )
                queued[sha] = record
                new_records.append(record)

            self.store.save(state)

            active, cap, launcher_available, launcher_error = self._launcher_snapshot()
            dispatched: list[dict[str, Any]] = []
            waiting: list[dict[str, Any]] = []
            closed: list[dict[str, Any]] = []
            stuck: list[dict[str, Any]] = []
            configured = set(self.repos)

            for sha, record in list(queued.items()):
                status = record.get("status", "queued")
                if status == "closed":
                    continue
                if status == "dispatching":
                    stuck.append(_item_from_record(record))
                    continue
                if status != "queued":
                    continue
                if sha not in current:
                    if record.get("repo") in configured:
                        record["status"] = "closed"
                        record["reason"] = "pr_not_open"
                        record["updated_at"] = now
                        closed.append(_item_from_record(record))
                    continue
                if launcher_available and active is not None and active < cap:
                    record["status"] = "dispatching"
                    record["updated_at"] = now
                    self.store.save(state)
                    try:
                        self.launcher.dispatch(_item_from_pr(current[sha]))
                    except Exception as exc:
                        record["status"] = "queued"
                        record["last_error"] = type(exc).__name__
                        record["updated_at"] = now
                        self.store.save(state)
                        raise LauncherError(
                            f"dispatch failed for {record.get('repo', '')}"
                            f"#{record.get('pr', 0)} ({type(exc).__name__})"
                        ) from None
                    record["status"] = "dispatched"
                    record["dispatched_at"] = now
                    record["updated_at"] = now
                    record.pop("last_error", None)
                    active += 1
                    dispatched.append(_item_from_record(record))
                else:
                    waiting.append(_item_from_record(record))

            self.store.save(state)

            new_items = [_item_from_record(record) for record in new_records]
            return {
                "repos": list(self.repos),
                "active_before": active,
                "cap": cap,
                "launcher_available": launcher_available,
                "launcher_error": launcher_error,
                "new": new_items,
                "dispatched": dispatched,
                "queued": waiting,
                "closed": closed,
                "stuck": stuck,
                "skipped": skipped,
            }


def poll_once(
    repos: Sequence[str] | None = None,
    state_path: str | os.PathLike[str] | None = None,
    github: Any = None,
    launcher: Any = None,
    cap: int | None = None,
) -> dict[str, Any]:
    return Poller(
        repos=repos,
        state_path=state_path,
        github=github,
        launcher=launcher,
        cap=cap,
    ).poll()


def _repos_from_env() -> list[str]:
    raw = os.environ.get("BEE_CI_REPOS", "")
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Queue new bee work from open PR heads.")
    parser.add_argument("--state", default=None, help="persistent dedupe state file")
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="owner/name to poll (repeatable; defaults to four configured repos)",
    )
    parser.add_argument("--cap", type=int, default=None, help="shared launcher bee cap")
    parser.add_argument("--timeout", type=float, default=20.0, help="network timeout seconds")
    args = parser.parse_args(argv)

    repos = args.repo or _repos_from_env() or list(DEFAULT_REPOS)
    try:
        poller = Poller(
            repos=repos,
            state_path=args.state,
            github=GitHubClient(timeout=args.timeout),
            launcher=default_launcher(timeout=args.timeout),
            cap=args.cap,
        )
        result = poller.poll()
    except PollerError as exc:
        print(f"bee-ci: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"bee-ci: poll failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
