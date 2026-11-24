"""Fail-closed tests for the bee-run CI verifier and commit-status poster.

The verifier signs/checks the same canonical HMAC-SHA256 payload bundlebees
uses for signed acceptance reports. The poster is dry-run by default, reads
its token from the environment only, and is exercised with an injected
transport so no test touches the network.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import sys
from pathlib import Path

import pytest

BEE_CI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BEE_CI))

from post_status import (  # noqa: E402
    StatusError,
    build_status,
    post_status,
    safe_target_url,
    sanitize_text,
)
from verify_result import (  # noqa: E402
    VerificationResult,
    canonical_bytes,
    sign_payload,
    verify_result,
)

KEY = "unit-test-key-not-a-secret"
HEAD = "a" * 40
JOB = "checkout-api"

ZERO_STEPS = [
    {"name": "install", "exit_code": 0},
    {"name": "test", "exit_code": 0},
]

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_RE = re.compile(r"\[[0-9A-Fa-f:.]+\]|(?<![0-9A-Za-z])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f]{0,4}(?![0-9A-Za-z])")
PRIVATE_HOST_RE = re.compile(
    r"(?i)\b(?:localhost|[a-z0-9-]+(?:\.[a-z0-9-]+)*"
    r"\.(?:local|internal|lan|home|corp|intranet|private|ts\.net|tailscale\.net|tailnet))\b"
)


def contains_ip(text: str) -> bool:
    if IPV4_RE.search(text):
        return True
    for candidate in IPV6_RE.findall(text):
        try:
            ipaddress.ip_address(candidate.strip("[]"))
        except ValueError:
            continue
        return True
    return False


def leaks_private(text: str) -> bool:
    return bool(
        contains_ip(text)
        or PRIVATE_HOST_RE.search(text)
        or "localhost" in text.lower()
    )


def result_body(*, job: str = JOB, head: str = HEAD, steps=None) -> dict:
    source = ZERO_STEPS if steps is None else steps
    copied = [dict(step) if isinstance(step, dict) else step for step in source]
    return {
        "job_id": job,
        "head_sha": head,
        "steps": copied,
    }


def sign(body: dict, key: str = KEY) -> dict:
    payload = dict(body)
    payload["signature"] = sign_payload(body, key)
    return payload


def test_fail_closed_matrix():
    """Unsigned, tampered, wrong-head or missing-job results never succeed."""

    tampered_after_signing = sign(result_body())
    tampered_after_signing["steps"] = [{"name": "test", "exit_code": 1}]

    matrix = [
        (
            "unsigned",
            result_body(),
            ("signature",),
        ),
        (
            "empty signature",
            {**result_body(), "signature": ""},
            ("signature",),
        ),
        (
            "tampered payload after signing",
            tampered_after_signing,
            ("signature",),
        ),
        (
            "signed with a different key",
            sign(result_body(), "a-different-key"),
            ("signature",),
        ),
        (
            "wrong recorded head",
            sign(result_body(head="b" * 40)),
            ("head",),
        ),
        (
            "wrong job id",
            sign(result_body(job="other-job")),
            ("job",),
        ),
        (
            "missing job id",
            sign({"head_sha": HEAD, "steps": ZERO_STEPS}),
            ("job",),
        ),
        (
            "missing head",
            sign({"job_id": JOB, "steps": ZERO_STEPS}),
            ("head",),
        ),
        (
            "missing steps",
            sign({"job_id": JOB, "head_sha": HEAD}),
            ("step",),
        ),
        (
            "empty steps",
            sign(result_body(steps=[])),
            ("step",),
        ),
        (
            "non-zero exit code",
            sign(result_body(steps=[{"name": "test", "exit_code": 2}])),
            ("exit",),
        ),
        (
            "string exit code",
            sign(result_body(steps=[{"name": "test", "exit_code": "0"}])),
            ("exit",),
        ),
        (
            "malformed step",
            sign(result_body(steps=["not-a-mapping"])),
            ("step",),
        ),
        (
            "malformed result",
            ["not", "a", "mapping"],
            (),
        ),
    ]

    for name, payload, expected_reason_tokens in matrix:
        checked = verify_result(
            payload,
            expected_head=HEAD,
            expected_job=JOB,
            key=KEY,
        )
        assert isinstance(checked, VerificationResult), name
        assert checked.ok is False, f"{name} must not succeed"
        assert checked.status in {"failure", "error"}, name
        if expected_reason_tokens:
            reason = checked.reason.lower()
            assert any(token in reason for token in expected_reason_tokens), (
                name,
                checked.reason,
            )


def test_success_only_when_proven():
    """A valid signature plus all-zero exits is the only success path."""
    # Pin the bundlebees-compatible canonical HMAC-SHA256 scheme.
    assert canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
    expected_signature = hmac.new(
        KEY.encode("utf-8"), canonical_bytes(result_body()), hashlib.sha256
    ).hexdigest()
    assert sign_payload(result_body(), KEY) == expected_signature

    good = verify_result(
        sign(result_body()),
        expected_head=HEAD,
        expected_job=JOB,
        key=KEY,
    )
    assert good.ok is True
    assert good.status == "success"

    failed_step = verify_result(
        sign(result_body(steps=[{"name": "test", "exit_code": 1}])),
        expected_head=HEAD,
        expected_job=JOB,
        key=KEY,
    )
    assert failed_step.ok is False
    assert failed_step.status == "failure"

    calls = []

    def transport(record, token):
        calls.append((record, token))

    # Dry run is the default and must never call the transport.
    dry = post_status(
        job=JOB,
        verification=good,
        transport=transport,
        env={"GITHUB_TOKEN": "environment-token"},
    )
    assert dry["dry_run"] is True
    assert dry["posted"] is False
    assert dry["context"] == f"bee-ci/{JOB}"
    assert dry["state"] == "success"
    assert calls == []

    # Dry run of a failed result also cannot become success.
    dry_failed = post_status(
        job=JOB,
        verification=failed_step,
        transport=transport,
        env={"GITHUB_TOKEN": "environment-token"},
    )
    assert dry_failed["dry_run"] is True
    assert dry_failed["state"] != "success"
    assert calls == []

    # The live switch posts only through the injected transport and uses the
    # environment token.
    live = post_status(
        job=JOB,
        verification=good,
        dry_run=False,
        transport=transport,
        env={"GITHUB_TOKEN": "environment-token"},
    )
    assert live["dry_run"] is False
    assert live["posted"] is True
    assert len(calls) == 1
    record, token = calls[0]
    assert token == "environment-token"
    assert record == {
        "context": f"bee-ci/{JOB}",
        "state": "success",
        "description": good.reason,
        "target_url": "",
    }
    assert "environment-token" not in json.dumps(live)

    # Live without a token fails closed and never calls the transport.
    calls.clear()
    with pytest.raises(StatusError):
        post_status(
            job=JOB,
            verification=good,
            dry_run=False,
            transport=transport,
            env={},
        )
    assert calls == []

    # Live without an injected transport also fails closed.
    with pytest.raises(StatusError):
        post_status(
            job=JOB,
            verification=good,
            dry_run=False,
            transport=None,
            env={"GITHUB_TOKEN": "environment-token"},
        )


def test_no_private_hosts():
    """target_url and description never carry private hosts, tailnets or IPs."""
    unsafe_urls = [
        "http://10.1.2.3:8080/ci",
        "https://192.168.0.10/ci",
        "https://172.20.0.1/ci",
        "https://build-box.tailnet.ts.net/ci",
        "https://runner.tailscale.net/ci",
        "https://localhost/ci",
        "https://build-box.internal/ci",
        "http://[fe80::1]/ci",
        "https://user:password@example.com/ci",
        "https://example.com/10.0.0.5/run",
        "https://build-box/ci",
    ]
    for url in unsafe_urls:
        assert safe_target_url(url) == "", url

    public = "https://github.com/mojomast/workflow/actions/runs/1"
    assert safe_target_url(public) == public

    dirty = (
        "runner 10.0.0.5 host.internal box.tailnet.ts.net "
        "192.168.1.9 [fe80::1] http://localhost:8080 "
        "http://build-box:8080/run"
    )
    cleaned = sanitize_text(dirty)
    assert not leaks_private(cleaned), cleaned
    assert "10.0.0.5" not in cleaned
    assert "host.internal" not in cleaned
    assert "tailnet" not in cleaned
    assert "localhost" not in cleaned
    assert "build-box" not in cleaned

    checked = verify_result(
        sign(result_body()),
        expected_head=HEAD,
        expected_job=JOB,
        key=KEY,
    )
    record = build_status(
        job=JOB,
        verification=checked,
        target_url="https://10.0.0.5/ci",
        description=dirty,
    )
    assert record["context"] == f"bee-ci/{JOB}"
    assert record["target_url"] == ""
    assert not leaks_private(record["target_url"])
    assert not leaks_private(record["description"])
