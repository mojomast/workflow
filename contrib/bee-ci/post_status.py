"""Post a bee-ci commit status, dry-run by default.

Phase 1 never posts anything unless the caller explicitly opts in with
``dry_run=False`` *and* supplies an injected transport. The GitHub token is
read from the environment only (``BEE_CI_GITHUB_TOKEN`` then ``GITHUB_TOKEN``)
and is never placed in the status record or printed.

Both ``target_url`` and ``description`` are sanitized so they cannot carry
private hosts, tailnet names, credentials or IP addresses. Unsafe target URLs
are dropped rather than rewritten.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

from verify_result import (
    STATUS_ERROR,
    STATUS_FAILURE,
    STATUS_SUCCESS,
    load_result,
    verify_result,
)

DEFAULT_CONTEXT_PREFIX = "bee-ci"
TOKEN_ENV_NAMES = ("BEE_CI_GITHUB_TOKEN", "GITHUB_TOKEN")
MAX_DESCRIPTION = 140

JOB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_RE = re.compile(
    r"\[[0-9A-Fa-f:.]+\]|(?<![0-9A-Za-z])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f]{0,4}(?![0-9A-Za-z])"
)
PRIVATE_SUFFIXES = (
    ".local",
    ".localhost",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".intranet",
    ".private",
    ".ts.net",
    ".tailscale.net",
    ".tailnet",
)
PRIVATE_HOST_RE = re.compile(
    r"(?i)\b(?:localhost|[a-z0-9-]+(?:\.[a-z0-9-]+)*"
    r"\.(?:local|localhost|internal|lan|home|corp|intranet|private|ts\.net|tailscale\.net|tailnet))\b"
)
CREDENTIALS_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@")
URL_HOST_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)(\[[0-9a-f:.]+\]|[^/\s:?#]+)")


class StatusError(ValueError):
    """A commit status could not be built or posted safely."""


def _ip_token(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate.strip("[]"))
    except ValueError:
        return False
    return True


def _text_has_private(text: str) -> bool:
    if IPV4_RE.search(text):
        return True
    for candidate in IPV6_RE.findall(text):
        if _ip_token(candidate):
            return True
    return bool(PRIVATE_HOST_RE.search(text))


def _host_is_private(host: str) -> bool:
    name = host.strip().strip(".").lower()
    if not name:
        return True
    if name == "localhost" or name.endswith(".localhost"):
        return True
    if name.endswith(PRIVATE_SUFFIXES):
        return True
    if _ip_token(name):
        return True
    if "." not in name:
        return True
    return False


def sanitize_text(text: Any, *, limit: int = MAX_DESCRIPTION) -> str:
    """Redact private hosts, tailnet names, credentials and IPs."""
    if text is None:
        return ""
    value = str(text)
    value = CREDENTIALS_RE.sub(r"\1[redacted]@", value)
    value = IPV4_RE.sub("[redacted]", value)

    def _redact_ipv6(match: re.Match[str]) -> str:
        candidate = match.group(0)
        return "[redacted]" if _ip_token(candidate) else candidate

    value = IPV6_RE.sub(_redact_ipv6, value)

    def _redact_url_host(match: re.Match[str]) -> str:
        scheme, host = match.group(1), match.group(2)
        if _host_is_private(host) or _ip_token(host):
            return scheme + "[redacted]"
        return match.group(0)

    value = URL_HOST_RE.sub(_redact_url_host, value)
    value = PRIVATE_HOST_RE.sub("[redacted]", value)
    value = " ".join(value.split())
    if len(value) > limit:
        value = value[: max(0, limit - 3)] + "..."
    return value


def safe_target_url(url: Any) -> str:
    """Return an https public URL, or ``""`` when it is not safe to publish."""
    if not isinstance(url, str) or not url.strip():
        return ""
    raw = url.strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() != "https":
        return ""
    host = parts.hostname
    if not host or parts.username or parts.password:
        return ""
    if _host_is_private(host):
        return ""
    if _text_has_private(raw):
        return ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _verification_status(verification: Any) -> tuple[str, str]:
    if isinstance(verification, Mapping):
        status = verification.get("status")
        reason = verification.get("reason")
    else:
        status = getattr(verification, "status", None)
        reason = getattr(verification, "reason", None)
    if status not in (STATUS_SUCCESS, STATUS_FAILURE, STATUS_ERROR):
        return STATUS_ERROR, "result was not verified"
    if not isinstance(reason, str) or not reason.strip():
        reason = status
    return status, reason


def build_status(
    *,
    job: Any,
    verification: Any,
    target_url: Any = "",
    description: Any = None,
) -> dict:
    """Build a GitHub commit-status record without posting it."""
    if not isinstance(job, str) or not JOB_RE.fullmatch(job):
        raise StatusError("invalid job id for bee-ci context")
    state, reason = _verification_status(verification)
    text = reason if description is None else description
    return {
        "context": f"{DEFAULT_CONTEXT_PREFIX}/{job}",
        "state": state,
        "description": sanitize_text(text),
        "target_url": safe_target_url(target_url),
    }


def read_token(env: Mapping[str, str] | None = None) -> str | None:
    """Read the GitHub token from the environment only."""
    source = os.environ if env is None else env
    for name in TOKEN_ENV_NAMES:
        value = source.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def post_status(
    *,
    job: Any,
    verification: Any,
    dry_run: bool = True,
    transport: Callable[[dict, str], Any] | None = None,
    env: Mapping[str, str] | None = None,
    target_url: Any = "",
    description: Any = None,
) -> dict:
    """Return a status record; post only when explicitly live and injected.

    ``dry_run`` defaults to true. A live call fails closed unless a token is
    present in the environment and a transport was injected. The transport is
    called as ``transport(record, token)``.
    """
    record = build_status(
        job=job,
        verification=verification,
        target_url=target_url,
        description=description,
    )
    if dry_run:
        return {**record, "dry_run": True, "posted": False}

    token = read_token(env)
    if not token:
        raise StatusError(
            "missing token: set BEE_CI_GITHUB_TOKEN or GITHUB_TOKEN in the environment"
        )
    if transport is None:
        raise StatusError("no transport configured; refusing to post")
    transport(dict(record), token)
    return {**record, "dry_run": False, "posted": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post a bee-ci commit status (dry-run by default)"
    )
    parser.add_argument("result", help="path to the signed result JSON file")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-job", required=True)
    parser.add_argument("--key-env", default="BEE_CI_RESULT_KEY")
    parser.add_argument("--key-file")
    parser.add_argument("--target-url", default="")
    parser.add_argument("--description")
    parser.add_argument(
        "--live",
        action="store_true",
        help="leave dry-run mode (still requires an injected transport)",
    )
    args = parser.parse_args(argv)

    try:
        payload = load_result(args.result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "posted": False,
                    "dry_run": not args.live,
                    "error": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 2

    if args.key_file:
        try:
            key = Path(args.key_file).read_text(encoding="utf-8").strip() or None
        except OSError:
            key = None
    else:
        key = os.environ.get(args.key_env) or None

    checked = verify_result(
        payload,
        expected_head=args.expected_head,
        expected_job=args.expected_job,
        key=key,
    )

    try:
        record = post_status(
            job=args.expected_job,
            verification=checked,
            dry_run=not args.live,
            target_url=args.target_url,
            description=args.description,
        )
    except StatusError as exc:
        print(
            json.dumps(
                {
                    "posted": False,
                    "dry_run": not args.live,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(record, sort_keys=True))
    if record["state"] == STATUS_SUCCESS:
        return 0
    if record["state"] == STATUS_FAILURE:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
