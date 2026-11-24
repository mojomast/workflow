import json
import os
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_SH = REPO_ROOT / "contrib" / "bee-ci" / "runners" / "linux" / "run.sh"


def write_fake_runner(directory: Path) -> Path:
    path = directory / "fake-command-runner"
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import sys
            import time

            command = sys.argv[1]
            log = os.environ["FAKE_COMMAND_LOG"]
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(command + "\\n")
            if command.startswith("fail-now"):
                sys.exit(7)
            if command.startswith("slow-command"):
                time.sleep(10)
            sys.exit(0)
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def run_runner(tmp_path, manifest: dict, cgroup_root: Path | None = None):
    fake_runner = write_fake_runner(tmp_path)
    log = tmp_path / "commands.log"
    manifest_path = tmp_path / "job.json"
    result_path = tmp_path / "result.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "BEE_CI_TEST_MODE": "1",
            "BEE_CI_TEST_COMMAND_RUNNER": str(fake_runner),
            "FAKE_COMMAND_LOG": str(log),
            "BEE_CI_CGROUP_ROOT": str(cgroup_root or (tmp_path / "missing-cgroup")),
        }
    )
    completed = subprocess.run(
        ["bash", str(RUN_SH), str(manifest_path), str(result_path)],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    logged = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return completed, result, logged


def test_records_steps(tmp_path) -> None:
    manifest = {
        "job_id": "ordered-job",
        "timeout_s": 5,
        "steps": [
            {"id": "build", "run": "echo build"},
            {"id": "test", "run": "echo test"},
            {"id": "scan", "run": "echo scan"},
        ],
    }

    completed, result, logged = run_runner(tmp_path, manifest)

    assert completed.returncode == 0, completed.stderr
    assert result["status"] == "passed"
    assert [step["id"] for step in result["steps"]] == ["build", "test", "scan"]
    assert [step["command"] for step in result["steps"]] == [
        "echo build",
        "echo test",
        "echo scan",
    ]
    assert [step["exit_code"] for step in result["steps"]] == [0, 0, 0]
    assert all(step["duration_ms"] >= 0 for step in result["steps"])
    assert logged == ["echo build", "echo test", "echo scan"]
    assert result["isolation"]["network"]["status"] == "unverified"
    assert not result["isolation"]["network"]["isolated"]
    for name in ("cpu", "memory", "pids"):
        assert name in result["limits"]
        assert result["limits"][name]["status"] in {"observed", "unverified"}
        if result["limits"][name]["status"] == "unverified":
            assert result["limits"][name]["value"] == "unverified"


def test_failure_and_unknown_caps(tmp_path) -> None:
    manifest = {
        "job_id": "failing-job",
        "steps": [
            {"id": "first", "run": "echo first"},
            {"id": "second", "run": "fail-now"},
            {"id": "third", "run": "echo third"},
        ],
    }

    completed, result, logged = run_runner(tmp_path, manifest)

    assert completed.returncode != 0
    assert result["status"] == "failed"
    assert result["failing_step"] == "second"
    assert [step["status"] for step in result["steps"]] == ["passed", "failed", "skipped"]
    assert result["steps"][1]["exit_code"] == 7
    assert result["steps"][2]["exit_code"] is None
    assert logged == ["echo first", "fail-now"]
    for name in ("cpu", "memory", "pids"):
        assert result["limits"][name]["status"] == "unverified"
        assert result["limits"][name]["value"] == "unverified"
    assert result["isolation"]["network"]["status"] == "unverified"


def test_refuses_unverified_isolation(tmp_path) -> None:
    manifest = {
        "job_id": "isolation-job",
        "isolation": {"network": "required"},
        "steps": [{"id": "must-not-run", "run": "echo should-not-run"}],
    }

    completed, result, logged = run_runner(tmp_path, manifest)

    assert completed.returncode != 0
    assert result["status"] == "refused"
    assert result["isolation"]["network"]["status"] == "unverified"
    assert not result["isolation"]["network"]["isolated"]
    assert "network" in result["reason"].lower()
    assert logged == []


def test_timeout_is_failure(tmp_path) -> None:
    manifest = {
        "job_id": "timeout-job",
        "timeout_s": 0.4,
        "steps": [
            {"id": "slow", "run": "slow-command"},
            {"id": "after", "run": "echo after"},
        ],
    }

    completed, result, logged = run_runner(tmp_path, manifest)

    assert completed.returncode != 0
    assert result["status"] == "failed"
    assert result["failing_step"] == "slow"
    assert result["steps"][0]["status"] == "timeout"
    assert result["steps"][0]["exit_code"] is None
    assert result["steps"][0]["duration_ms"] < 5000
    assert result["steps"][1]["status"] == "skipped"
