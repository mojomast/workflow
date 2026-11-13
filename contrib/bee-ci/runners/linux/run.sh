#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    printf 'usage: %s JOB_MANIFEST RESULT_MANIFEST\n' "$0" >&2
    exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'error: python3 is required to run bee-ci jobs\n' >&2
    exit 2
fi

exec python3 - "$1" "$2" <<'PY'
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

SCHEMA = "bee-ci.result.v1"
MAX_MANIFEST_BYTES = 1024 * 1024
UNSAFE_KEYS = {
    "mount",
    "mounts",
    "volume",
    "volumes",
    "bind_mount",
    "bind_mounts",
    "secret",
    "secrets",
    "credential",
    "credentials",
}
LIMIT_FILES = {
    "cpu": ("cpu.max", "cpu/cpu.cfs_quota_us", "cpu/cpu.cfs_period_us"),
    "memory": ("memory.max", "memory/memory.limit_in_bytes"),
    "pids": ("pids.max", "pids/pids.max"),
}
ISOLATION_NETWORK = {
    "status": "unverified",
    "measured": False,
    "isolated": False,
    "reason": "network isolation is not measured by this runner",
}


class ManifestError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_manifest(path):
    size = os.stat(path).st_size
    if size > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest is larger than 1 MiB")
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest is larger than 1 MiB")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError("manifest is not valid JSON: %s" % exc.msg) from None
    if not isinstance(value, dict):
        raise ManifestError("manifest must be a JSON object")
    return value


def find_unsafe_key(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in UNSAFE_KEYS:
                return key
            found = find_unsafe_key(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_unsafe_key(child)
            if found is not None:
                return found
    return None


def parse_timeout(value, label):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ManifestError("%s must be a positive number of seconds" % label)
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        raise ManifestError("%s must be a positive number of seconds" % label) from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise ManifestError("%s must be a positive number of seconds" % label)
    return timeout


def validate_steps(manifest):
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ManifestError("manifest must contain a non-empty steps list")
    default_timeout = parse_timeout(manifest.get("timeout_s"), "timeout_s")
    normalized = []
    for index, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict):
            raise ManifestError("step %d must be a JSON object" % index)
        command = raw.get("run")
        if not isinstance(command, str) or not command.strip():
            raise ManifestError("step %d must contain a non-empty run string" % index)
        if "\x00" in command:
            raise ManifestError("step %d contains a NUL byte" % index)
        step_id = raw.get("id", "step-%d" % index)
        if not isinstance(step_id, str) or not step_id:
            raise ManifestError("step %d id must be a non-empty string" % index)
        timeout = parse_timeout(
            raw.get("timeout_s", default_timeout), "step %d timeout_s" % index
        )
        normalized.append(
            {"id": step_id, "command": command, "timeout_s": timeout}
        )
    return normalized


def network_isolation_requested(manifest):
    values = [manifest.get("network_isolation"), manifest.get("network")]
    isolation = manifest.get("isolation")
    if isinstance(isolation, dict):
        values.append(isolation.get("network"))
        values.append(isolation.get("network_isolation"))
    for value in values:
        if value is True:
            return True
        if isinstance(value, str):
            if value.strip().lower() in {"required", "isolated", "none", "deny", "blocked"}:
                return True
    return manifest.get("require_network_isolation") is True


def cgroup_bases(root):
    bases = [root]
    try:
        with open("/proc/self/cgroup", "r", encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split(":", 2)
                if len(parts) == 3 and parts[0] == "0":
                    relative = parts[2].strip("/")
                    if relative:
                        candidate = os.path.join(root, relative)
                        if candidate not in bases:
                            bases.append(candidate)
                    break
    except OSError:
        pass
    return bases


def read_limit(bases, names):
    for base in bases:
        for name in names:
            path = os.path.join(base, name)
            try:
                if not os.path.isfile(path):
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    value = handle.read(4096).strip()
            except OSError:
                continue
            if value:
                return {
                    "status": "observed",
                    "value": value,
                    "source": name,
                }
    return {
        "status": "unverified",
        "value": "unverified",
        "reason": "limit file is not readable from this container",
    }


def read_limits():
    root = os.environ.get("BEE_CI_CGROUP_ROOT", "/sys/fs/cgroup")
    try:
        bases = cgroup_bases(root)
    except Exception:
        bases = [root]
    return {name: read_limit(bases, names) for name, names in LIMIT_FILES.items()}


def execute(argv, timeout):
    process = subprocess.Popen(argv, start_new_session=True)
    try:
        return process.wait(timeout=timeout), False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        return None, True


def command_argv(command, step_id):
    if os.environ.get("BEE_CI_TEST_MODE") == "1":
        fake = os.environ.get("BEE_CI_TEST_COMMAND_RUNNER")
        if fake:
            return [fake, command, step_id]
    return ["/bin/bash", "-c", command]


def write_result(path, result):
    parent = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(parent):
        raise OSError("result directory does not exist")
    fd, temporary = tempfile.mkstemp(prefix=".bee-ci-result.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def base_result(job_id, started_at):
    return {
        "schema": SCHEMA,
        "runner": "linux",
        "job_id": job_id,
        "status": "failed",
        "reason": None,
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": 0,
        "failing_step": None,
        "steps": [],
        "limits": read_limits(),
        "isolation": {"network": dict(ISOLATION_NETWORK)},
    }


def finish(result, started_monotonic, status, exit_code):
    result["status"] = status
    result["finished_at"] = utc_now()
    result["duration_ms"] = round((time.monotonic() - started_monotonic) * 1000, 3)
    return exit_code


def main():
    manifest_path, result_path = sys.argv[1], sys.argv[2]
    started_at = utc_now()
    started_monotonic = time.monotonic()

    try:
        manifest = read_manifest(manifest_path)
    except (OSError, ManifestError) as exc:
        result = base_result(None, started_at)
        result["reason"] = "cannot read manifest: %s" % exc
        result["status"] = "invalid"
        result["finished_at"] = utc_now()
        result["duration_ms"] = round((time.monotonic() - started_monotonic) * 1000, 3)
        write_result(result_path, result)
        print("bee-ci: invalid manifest -> %s" % result_path)
        return 2

    job_id = manifest.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        job_id = None

    result = base_result(job_id, started_at)
    unsafe = find_unsafe_key(manifest)
    if unsafe is not None:
        result["reason"] = (
            "manifest requests %s, which this runner cannot provide; no host paths "
            "are mounted and no credentials are read" % unsafe
        )
        result["status"] = "refused"
        result["finished_at"] = utc_now()
        result["duration_ms"] = round((time.monotonic() - started_monotonic) * 1000, 3)
        write_result(result_path, result)
        print("bee-ci: refused -> %s" % result_path)
        return 2

    if network_isolation_requested(manifest):
        result["reason"] = (
            "network isolation was requested but cannot be verified; "
            "this runner does not claim network isolation"
        )
        result["status"] = "refused"
        result["finished_at"] = utc_now()
        result["duration_ms"] = round((time.monotonic() - started_monotonic) * 1000, 3)
        write_result(result_path, result)
        print("bee-ci: refused -> %s" % result_path)
        return 2

    try:
        steps = validate_steps(manifest)
    except ManifestError as exc:
        result["reason"] = str(exc)
        result["status"] = "invalid"
        result["finished_at"] = utc_now()
        result["duration_ms"] = round((time.monotonic() - started_monotonic) * 1000, 3)
        write_result(result_path, result)
        print("bee-ci: invalid manifest -> %s" % result_path)
        return 2

    failed = False
    exit_code = 0
    for step in steps:
        if failed:
            result["steps"].append(
                {
                    "id": step["id"],
                    "command": step["command"],
                    "status": "skipped",
                    "exit_code": None,
                    "duration_ms": 0,
                }
            )
            continue

        step_started = time.monotonic()
        code, timed_out = execute(
            command_argv(step["command"], step["id"]), step["timeout_s"]
        )
        duration_ms = round((time.monotonic() - step_started) * 1000, 3)
        if timed_out:
            status = "timeout"
            failed = True
            exit_code = 1
        elif code == 0:
            status = "passed"
        else:
            status = "failed"
            failed = True
            exit_code = 1

        result["steps"].append(
            {
                "id": step["id"],
                "command": step["command"],
                "status": status,
                "exit_code": code,
                "duration_ms": duration_ms,
            }
        )
        if failed:
            result["failing_step"] = step["id"]

    final_status = "failed" if failed else "passed"
    finish(result, started_monotonic, final_status, exit_code)
    write_result(result_path, result)
    print("bee-ci: %s -> %s" % (final_status, result_path))
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write("bee-ci: internal error: %s\n" % exc)
        sys.exit(2)
PY
