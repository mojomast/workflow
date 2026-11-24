"""Fail-closed verifier for bee-run CI result files.

A result is a JSON object with ``job_id``, ``head_sha`` and a non-empty
``steps`` list. It is signed with HMAC-SHA256 over the canonical JSON body
(sorted keys, compact separators, ASCII), the same scheme bundlebees uses for
signed acceptance reports. ``signature`` itself is excluded from the body.

``verify_result`` returns success only when all of these hold:

* the signature is present and valid for the configured key;
* the recorded head SHA equals the expected head;
* the recorded job id equals the dispatched job id;
* every recorded step has an integer ``exit_code`` of exactly 0.

Missing fields, malformed input, a missing key or an unexpected exception are
reported as ``error``. A validly signed result that disagrees with the dispatch
or carries a failing step is ``failure``. Nothing else becomes success.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

SIGNATURE_FIELD = "signature"
STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_ERROR = "error"

DEFAULT_KEY_ENV = "BEE_CI_RESULT_KEY"


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying one result. ``ok`` is true only for success."""

    status: str
    reason: str
    code: str

    @property
    def ok(self) -> bool:
        return self.status == STATUS_SUCCESS


def canonical_bytes(obj: Any) -> bytes:
    """Canonical JSON bytes used for signing and verification."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _key_bytes(key: str | bytes | bytearray | None) -> bytes:
    if isinstance(key, str):
        return key.encode("utf-8")
    if isinstance(key, (bytes, bytearray)):
        return bytes(key)
    return b""


def _signing_body(payload: Mapping[str, Any]) -> dict:
    return {name: value for name, value in payload.items() if name != SIGNATURE_FIELD}


def sign_payload(payload: Mapping[str, Any], key: str | bytes | bytearray) -> str:
    """Return the hex HMAC-SHA256 signature for a result payload.

    Any existing ``signature`` field is ignored so a caller can sign either a
    body or an already-signed record without changing the canonical body.
    """
    key_bytes = _key_bytes(key)
    if not key_bytes:
        raise ValueError("signing key must not be empty")
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    return hmac.new(
        key_bytes,
        canonical_bytes(_signing_body(payload)),
        hashlib.sha256,
    ).hexdigest()


def _outcome(status: str, code: str, reason: str) -> VerificationResult:
    return VerificationResult(status=status, reason=reason, code=code)


def _error(code: str, reason: str) -> VerificationResult:
    return _outcome(STATUS_ERROR, code, reason)


def _failure(code: str, reason: str) -> VerificationResult:
    return _outcome(STATUS_FAILURE, code, reason)


def verify_result(
    result: Any,
    *,
    expected_head: Any,
    expected_job: Any,
    key: str | bytes | bytearray | None,
) -> VerificationResult:
    """Verify a bee-run CI result. Fails closed on every unexpected input."""
    try:
        if not isinstance(result, Mapping):
            return _error("malformed_result", "malformed result: expected an object")

        if not _key_bytes(key):
            return _error("missing_key", "verification key is missing")

        signature = result.get(SIGNATURE_FIELD)
        if not isinstance(signature, str) or not signature.strip():
            return _error("unsigned", "unsigned result: missing signature")

        expected_signature = sign_payload(result, key)
        if not hmac.compare_digest(signature.strip().lower(), expected_signature):
            return _error("signature_invalid", "signature verification failed")

        job_id = result.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            return _error("missing_job", "missing job id")

        head_sha = result.get("head_sha")
        if not isinstance(head_sha, str) or not head_sha.strip():
            return _error("missing_head", "missing head sha")

        steps = result.get("steps")
        if not isinstance(steps, list) or not steps:
            return _error("missing_steps", "missing recorded steps")

        if not isinstance(expected_job, str) or not expected_job.strip():
            return _error("expected_job_missing", "expected dispatched job id is missing")
        if not isinstance(expected_head, str) or not expected_head.strip():
            return _error("expected_head_missing", "expected head sha is missing")

        if job_id != expected_job:
            return _failure(
                "job_mismatch",
                "job id does not match the dispatched job",
            )
        if head_sha.strip().lower() != expected_head.strip().lower():
            return _failure(
                "head_mismatch",
                "head sha does not match the expected head",
            )

        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                return _failure(
                    "malformed_step",
                    f"malformed step at index {index}: expected an object",
                )
            exit_code = step.get("exit_code")
            if type(exit_code) is not int:
                return _failure(
                    "invalid_exit_code",
                    f"invalid exit code for step at index {index}",
                )
            if exit_code != 0:
                name = step.get("name")
                label = name if isinstance(name, str) and name else str(index)
                return _failure(
                    "step_failed",
                    f"step {label!r} exited with code {exit_code}",
                )

        return _outcome(
            STATUS_SUCCESS,
            "proven",
            "signature valid, head and job match, all steps exited 0",
        )
    except Exception as exc:  # fail closed without echoing untrusted details
        return _error(
            "verification_error",
            f"verification error: {type(exc).__name__}",
        )


def load_result(path: str | os.PathLike[str]) -> Any:
    """Load a result JSON file. Raises on unreadable or invalid JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_key(args: argparse.Namespace) -> str | None:
    if args.key_file:
        try:
            return Path(args.key_file).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return os.environ.get(args.key_env) or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a signed bee-run CI result")
    parser.add_argument("result", help="path to the result JSON file")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-job", required=True)
    parser.add_argument("--key-env", default=DEFAULT_KEY_ENV)
    parser.add_argument("--key-file")
    args = parser.parse_args(argv)

    try:
        payload = load_result(args.result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "status": STATUS_ERROR, "code": "unreadable_result", "reason": type(exc).__name__}, sort_keys=True))
        return 2

    checked = verify_result(
        payload,
        expected_head=args.expected_head,
        expected_job=args.expected_job,
        key=_read_key(args),
    )
    print(
        json.dumps(
            {
                "ok": checked.ok,
                "status": checked.status,
                "code": checked.code,
                "reason": checked.reason,
            },
            sort_keys=True,
        )
    )
    if checked.status == STATUS_SUCCESS:
        return 0
    if checked.status == STATUS_FAILURE:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
