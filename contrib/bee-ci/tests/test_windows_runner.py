from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "runners" / "windows" / "run-job.ps1"
CONTRACT_RE = re.compile(
    r"# BEGIN BEE-RUN CONTRACT.*?@'\r?\n(?P<body>.*?)\r?\n'@\s*\r?\n# END BEE-RUN CONTRACT",
    re.DOTALL,
)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def runner_text() -> str:
    if not RUNNER.is_file():
        pytest.fail(f"runner is missing: {RUNNER}")
    return RUNNER.read_text(encoding="utf-8")


def load_contract() -> dict:
    match = CONTRACT_RE.search(runner_text())
    if not match:
        pytest.fail("runner does not expose the machine-readable BEE-RUN CONTRACT block")
    return json.loads(match.group("body"))


def normalize_command(value) -> str:
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("command must not be empty")
        return value
    if isinstance(value, list) and value:
        parts = []
        for item in value:
            if not isinstance(item, str) or not item:
                raise ValueError("command arguments must be non-empty strings")
            parts.append("'" + item.replace("'", "''") + "'")
        return "& " + " ".join(parts)
    raise ValueError("command must be a non-empty string or array")


def validate_timeout(value, contract: dict) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("timeout_seconds must be an integer")
    if value < 1 or value > contract["max_timeout_seconds"]:
        raise ValueError("timeout_seconds outside the permitted range")
    return value


def build_command_plan(job: dict, checkout: Path, contract: dict) -> dict:
    for field in contract["required_job_fields"]:
        if field not in job:
            raise ValueError(f"job manifest is missing {field}")
    job_id = job["job_id"]
    if not isinstance(job_id, str) or not ID_RE.match(job_id):
        raise ValueError("job_id is not a safe identifier")
    steps = job["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError("job manifest must contain at least one step")
    if len(steps) > contract["max_steps"]:
        raise ValueError("job manifest has too many steps")

    root = checkout.resolve()
    default_timeout = validate_timeout(
        job.get("timeout_seconds", contract["default_timeout_seconds"]), contract
    )
    plan_steps = []
    seen = set()
    for index, step in enumerate(steps, start=1):
        for field in contract["required_step_fields"]:
            if field not in step:
                raise ValueError(f"step {index} is missing {field}")
        step_id = step["id"]
        if not isinstance(step_id, str) or not ID_RE.match(step_id):
            raise ValueError(f"step {index} has an unsafe id")
        if step_id in seen:
            raise ValueError(f"duplicate step id: {step_id}")
        seen.add(step_id)
        timeout = validate_timeout(step.get("timeout_seconds", default_timeout), contract)
        cwd = (root / step.get("cwd", ".")).resolve()
        if cwd != root and root not in cwd.parents:
            raise ValueError(f"step {step_id} escapes the checkout")
        plan_steps.append(
            {
                "index": index,
                "id": step_id,
                "name": str(step.get("name", step_id)),
                "command": normalize_command(step["command"]),
                "cwd": str(cwd),
                "timeout_seconds": timeout,
                "continue_on_error": bool(step.get("continue_on_error", False)),
            }
        )
    return {
        "schema_version": contract["schema_version"],
        "kind": contract["plan_kind"],
        "job_id": job_id,
        "checkout": str(root),
        "failure_policy": contract["failure_policy"],
        "steps": plan_steps,
    }


def redact_text(text: str, literals, contract: dict) -> str:
    marker = contract["redaction_marker"]
    result = text
    for literal in literals:
        if literal:
            result = result.replace(literal, marker)
    for rule in contract["sensitive_output_patterns"]:
        replacement = re.sub(r"\$(\d+)", r"\\g<\1>", rule["replacement"])
        result = re.sub(rule["regex"], replacement, result)
    return result


def build_result_manifest(
    plan: dict,
    outcomes: list[dict],
    contract: dict,
    literals=(),
) -> dict:
    records = []
    failure = None
    for step, outcome in zip(plan["steps"], outcomes):
        timed_out = bool(outcome.get("timed_out", False))
        exit_code = outcome.get("exit_code")
        if timed_out:
            status = "timed_out"
        elif exit_code == 0:
            status = "passed"
        else:
            status = "failed"
        record = {
            "index": step["index"],
            "id": step["id"],
            "name": step["name"],
            "command": redact_text(step["command"], literals, contract),
            "status": status,
            "exit_code": exit_code,
            "duration_ms": int(outcome.get("duration_ms", 0)),
            "timed_out": timed_out,
            "stdout": redact_text(str(outcome.get("stdout", "")), literals, contract),
            "stderr": redact_text(str(outcome.get("stderr", "")), literals, contract),
        }
        records.append(record)
        if failure is None and status != "passed":
            failure = {
                "step_id": step["id"],
                "exit_code": exit_code,
                "reason": "timeout" if timed_out else "non_zero_exit",
            }
        if failure is not None and not step["continue_on_error"]:
            break
    return {
        "schema_version": contract["schema_version"],
        "kind": contract["result_kind"],
        "job_id": plan["job_id"],
        "checkout": plan["checkout"],
        "status": "failed" if failure else "passed",
        "failure_policy": plan["failure_policy"],
        "steps": records,
        "failure": failure,
    }


@pytest.fixture
def contract() -> dict:
    return load_contract()


def sample_job() -> dict:
    return {
        "schema_version": 1,
        "job_id": "windows-ci-001",
        "timeout_seconds": 60,
        "redact": ["literal-secret-value"],
        "steps": [
            {"id": "restore", "name": "Restore packages", "command": "dotnet restore"},
            {
                "id": "test",
                "command": ["dotnet", "test", "--no-restore"],
                "timeout_seconds": 300,
                "cwd": "src",
            },
        ],
    }


def test_contract_is_machine_readable(contract):
    assert contract["schema_version"] == 1
    assert contract["failure_policy"] == "fail-fast"
    assert contract["plan_kind"] == "bee-run/command-plan"
    assert contract["result_kind"] == "bee-run/result-manifest"
    assert "exit_code" in contract["result_step_fields"]
    assert "timed_out" in contract["result_step_fields"]
    assert contract["default_timeout_seconds"] > 0
    assert contract["max_output_chars"] > 0


def test_job_manifest_builds_command_plan(contract, tmp_path):
    plan = build_command_plan(sample_job(), tmp_path, contract)
    assert plan["kind"] == "bee-run/command-plan"
    assert plan["job_id"] == "windows-ci-001"
    assert [step["id"] for step in plan["steps"]] == ["restore", "test"]
    assert plan["steps"][0]["command"] == "dotnet restore"
    assert plan["steps"][1]["command"] == "& 'dotnet' 'test' '--no-restore'"
    assert plan["steps"][0]["timeout_seconds"] == 60
    assert plan["steps"][1]["timeout_seconds"] == 300
    assert Path(plan["steps"][1]["cwd"]) == (tmp_path / "src").resolve()


def test_command_plan_rejects_checkout_escape(contract, tmp_path):
    job = sample_job()
    job["steps"][1]["cwd"] = ".."
    with pytest.raises(ValueError, match="escapes the checkout"):
        build_command_plan(job, tmp_path, contract)


def test_records_exit_codes(contract, tmp_path):
    job = sample_job()
    job["steps"][1]["continue_on_error"] = True
    job["steps"].append({"id": "package", "command": "dotnet pack --no-build"})
    plan = build_command_plan(job, tmp_path, contract)
    outcomes = [
        {"exit_code": 0, "duration_ms": 11, "stdout": "restored"},
        {"exit_code": 7, "duration_ms": 22, "stdout": "", "stderr": "test failed"},
        {"exit_code": 0, "duration_ms": 33, "stdout": "packed"},
    ]
    result = build_result_manifest(plan, outcomes, contract)
    assert result["kind"] == "bee-run/result-manifest"
    assert [step["exit_code"] for step in result["steps"]] == [0, 7, 0]
    assert [step["status"] for step in result["steps"]] == ["passed", "failed", "passed"]
    assert result["status"] == "failed"
    assert result["failure"] == {
        "step_id": "test",
        "exit_code": 7,
        "reason": "non_zero_exit",
    }


def test_failure_propagates(contract, tmp_path):
    job = sample_job()
    job["steps"].append({"id": "package", "command": "dotnet pack --no-build"})
    plan = build_command_plan(job, tmp_path, contract)
    outcomes = [
        {"exit_code": 0, "duration_ms": 11},
        {"exit_code": 5, "duration_ms": 22, "stderr": "build failed"},
        {"exit_code": 0, "duration_ms": 33},
    ]
    result = build_result_manifest(plan, outcomes, contract)
    assert result["status"] == "failed"
    assert result["failure"] == {
        "step_id": "test",
        "exit_code": 5,
        "reason": "non_zero_exit",
    }
    assert [step["id"] for step in result["steps"]] == ["restore", "test"]
    assert result["steps"][1]["exit_code"] == 5


def test_timeout_produces_failed_manifest(contract, tmp_path):
    plan = build_command_plan(sample_job(), tmp_path, contract)
    outcomes = [
        {"exit_code": 0, "duration_ms": 10},
        {"exit_code": None, "duration_ms": 300000, "timed_out": True},
    ]
    result = build_result_manifest(plan, outcomes, contract)
    assert result["status"] == "failed"
    assert result["failure"]["step_id"] == "test"
    assert result["failure"]["reason"] == "timeout"
    assert result["steps"][1]["timed_out"] is True
    assert result["steps"][1]["status"] == "timed_out"


def test_manifest_redacts_declared_literals(contract, tmp_path):
    job = sample_job()
    plan = build_command_plan(job, tmp_path, contract)
    outcomes = [
        {
            "exit_code": 0,
            "duration_ms": 10,
            "stdout": "using literal-secret-value",
            "stderr": "Authorization: Bearer abc123",
        },
        {"exit_code": 0, "duration_ms": 10},
    ]
    result = build_result_manifest(plan, outcomes, contract, job["redact"])
    assert "literal-secret-value" not in json.dumps(result)
    assert "abc123" not in json.dumps(result)
    assert contract["redaction_marker"] in result["steps"][0]["stdout"]


def test_runner_script_implements_the_contract():
    script = runner_text()
    for token in (
        "Start-Process",
        "WaitForExit",
        "Redact-Text",
        "timed_out",
        "exit_code",
        "duration_ms",
        "taskkill",
        "fail-fast",
        "ConvertTo-Json",
    ):
        assert token in script
    assert "$script:BeeRunContract.failure_policy" in script
    assert "$script:BeeRunContract.default_timeout_seconds" in script
    assert "$script:BeeRunContract.max_output_chars" in script


@pytest.mark.skipif(
    PWSH is None,
    reason="NOT RUN: PowerShell is not installed on this Linux host; "
    "the Windows runner cannot be executed here.",
)
def test_plan_only_under_powershell(contract, tmp_path):
    job_path = tmp_path / "job.json"
    plan_path = tmp_path / "plan.json"
    (tmp_path / "src").mkdir()
    job_path.write_text(json.dumps(sample_job()), encoding="utf-8")
    completed = subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(RUNNER),
            "-JobManifest",
            str(job_path),
            "-Checkout",
            str(tmp_path),
            "-ResultManifest",
            str(plan_path),
            "-PlanOnly",
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    expected = build_command_plan(sample_job(), tmp_path, contract)
    assert plan["kind"] == "bee-run/command-plan"
    assert plan["failure_policy"] == expected["failure_policy"]
    assert [step["id"] for step in plan["steps"]] == ["restore", "test"]
    for actual, wanted in zip(plan["steps"], expected["steps"]):
        assert actual["command"] == wanted["command"]
        assert actual["timeout_seconds"] == wanted["timeout_seconds"]
        assert actual["continue_on_error"] == wanted["continue_on_error"]
        assert Path(actual["cwd"]) == Path(wanted["cwd"])


@pytest.mark.skip(
    reason="NOT RUN: requires a real Windows host (PowerShell execution, "
    "process-tree timeout and filesystem semantics); not executed on this "
    "Linux host and never reported as passing."
)
def test_real_windows_host_execution():
    assert RUNNER.is_file()
