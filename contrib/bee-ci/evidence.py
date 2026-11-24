import json
import os
import re
import tempfile
from datetime import datetime


SCHEMA = "bee-ci/evidence/v1"
REPOS = frozenset({"workflow", "bundlebees", "orbitdesktop", "hyvv"})
SOURCES = frozenset({"bee", "github"})
STATES = frozenset({"success", "failure", "error", "pending"})
RUN_KEYS = (
    "repo",
    "head_sha",
    "job",
    "source",
    "state",
    "exit_codes",
    "started_at",
    "finished_at",
    "result_path",
)
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _normalize_enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def _normalize_sha(value):
    return value if isinstance(value, str) and _SHA.fullmatch(value) else None


def _normalize_job(value):
    return value if isinstance(value, str) and value else None


def _normalize_state(value):
    if value is None:
        return None
    if not isinstance(value, str) or value not in STATES:
        raise ValueError("state must be one of: " + ", ".join(sorted(STATES)))
    return value


def _normalize_time(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return value


def _normalize_exit_codes(value):
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    codes = []
    for item in value:
        if not isinstance(item, dict):
            continue
        step = item.get("step")
        exit_code = item.get("exit_code")
        codes.append(
            {
                "step": step if isinstance(step, str) else None,
                "exit_code": exit_code
                if isinstance(exit_code, int) and not isinstance(exit_code, bool)
                else None,
            }
        )
    return codes


def _normalize_run(run):
    if not isinstance(run, dict):
        raise TypeError("run must be a mapping")
    return {
        "repo": _normalize_enum(run.get("repo"), REPOS),
        "head_sha": _normalize_sha(run.get("head_sha")),
        "job": _normalize_job(run.get("job")),
        "source": _normalize_enum(run.get("source"), SOURCES),
        "state": _normalize_state(run.get("state")),
        "exit_codes": _normalize_exit_codes(run.get("exit_codes")),
        "started_at": _normalize_time(run.get("started_at")),
        "finished_at": _normalize_time(run.get("finished_at")),
        "result_path": run.get("result_path")
        if isinstance(run.get("result_path"), str) and run.get("result_path")
        else None,
    }


def _dedupe_key(run):
    return (run.get("repo"), run.get("head_sha"), run.get("job"), run.get("source"))


def _validate_time(value):
    if value is None:
        return
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be an ISO8601 UTC string")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("timestamp must be an ISO8601 UTC string") from error


def _validate_run(run):
    if not isinstance(run, dict):
        raise ValueError("run must be an object")
    if set(run.keys()) != set(RUN_KEYS):
        raise ValueError("run must contain exactly the frozen fields")
    if run["repo"] is not None and not (
        isinstance(run["repo"], str) and run["repo"] in REPOS
    ):
        raise ValueError("invalid repo")
    if run["head_sha"] is not None and not (
        isinstance(run["head_sha"], str) and _SHA.fullmatch(run["head_sha"])
    ):
        raise ValueError("invalid head_sha")
    if run["job"] is not None and not (isinstance(run["job"], str) and run["job"]):
        raise ValueError("invalid job")
    if run["source"] is not None and not (
        isinstance(run["source"], str) and run["source"] in SOURCES
    ):
        raise ValueError("invalid source")
    if run["state"] is not None and not (
        isinstance(run["state"], str) and run["state"] in STATES
    ):
        raise ValueError("state must be one of: " + ", ".join(sorted(STATES)))
    if run["exit_codes"] is not None:
        if not isinstance(run["exit_codes"], list):
            raise ValueError("exit_codes must be a list or null")
        for item in run["exit_codes"]:
            if not isinstance(item, dict) or set(item.keys()) != {"step", "exit_code"}:
                raise ValueError("invalid exit_codes entry")
            if item["step"] is not None and not isinstance(item["step"], str):
                raise ValueError("invalid exit_codes step")
            code = item["exit_code"]
            if code is not None and (not isinstance(code, int) or isinstance(code, bool)):
                raise ValueError("invalid exit_code")
    _validate_time(run["started_at"])
    _validate_time(run["finished_at"])
    if run["result_path"] is not None and not (
        isinstance(run["result_path"], str) and run["result_path"]
    ):
        raise ValueError("invalid result_path")


def _validate_doc(doc):
    if not isinstance(doc, dict):
        raise ValueError("index must be an object")
    if set(doc.keys()) != {"schema", "runs"}:
        raise ValueError("index must contain schema and runs")
    if doc["schema"] != SCHEMA:
        raise ValueError("unsupported evidence schema")
    if not isinstance(doc["runs"], list):
        raise ValueError("runs must be a list")
    for run in doc["runs"]:
        _validate_run(run)
    return doc


def _write_atomic(path, doc):
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=".index.", suffix=".tmp", dir=parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def append(index_path, run):
    path = os.fspath(index_path)
    entry = _normalize_run(run)
    if os.path.exists(path):
        doc = load(path)
        runs = doc["runs"]
        key = _dedupe_key(entry)
        if any(_dedupe_key(existing) == key for existing in runs):
            return False
        runs = runs + [entry]
    else:
        runs = [entry]
    _write_atomic(path, {"schema": SCHEMA, "runs": runs})
    return True


def load(index_path):
    path = os.fspath(index_path)
    if not os.path.exists(path):
        return {"schema": SCHEMA, "runs": []}
    with open(path, "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    return _validate_doc(doc)
