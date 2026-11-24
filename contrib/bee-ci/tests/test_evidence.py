import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence


INDEX_REL = Path("evidence") / "index.json"
SHA = "a" * 40


def _run(**overrides):
    data = {
        "repo": "workflow",
        "head_sha": SHA,
        "job": "unit",
        "source": "bee",
        "state": "success",
        "exit_codes": [{"step": "python -m pytest", "exit_code": 0}],
        "started_at": "2026-11-13T00:00:00Z",
        "finished_at": "2026-11-13T00:01:00Z",
        "result_path": "evidence/workflow/" + SHA + "/unit-bee.json",
    }
    data.update(overrides)
    return data


def test_append_dedupes(tmp_path):
    index = tmp_path / INDEX_REL

    assert evidence.append(index, _run()) is True
    original = index.read_bytes()

    assert evidence.append(index, _run()) is False
    assert index.read_bytes() == original

    assert evidence.append(index, _run(state="failure", finished_at=None)) is False
    assert index.read_bytes() == original

    assert evidence.append(index, _run(job="other")) is True
    doc = evidence.load(index)
    assert doc["schema"] == "bee-ci/evidence/v1"
    assert [run["job"] for run in doc["runs"]] == ["unit", "other"]
    assert doc["runs"][0]["state"] == "success"
    assert doc["runs"][1]["job"] == "other"


def test_atomic_write_and_validation(tmp_path, monkeypatch):
    index = tmp_path / INDEX_REL
    evidence.append(index, _run())
    before = index.read_bytes()

    real_replace = os.replace
    calls = []

    def recording_replace(src, dst):
        calls.append((Path(src), Path(dst)))
        real_replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(evidence.os, "replace", recording_replace)
        assert evidence.append(index, _run(job="atomic")) is True

    assert calls
    assert calls[-1][1] == index
    assert calls[-1][0].parent == index.parent

    written = index.read_bytes()

    def failing_replace(src, dst):
        raise OSError("interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(evidence.os, "replace", failing_replace)
        with pytest.raises(OSError):
            evidence.append(index, _run(job="interrupted"))

    assert index.read_bytes() == written
    parsed = json.loads(index.read_text(encoding="utf-8"))
    assert parsed["schema"] == "bee-ci/evidence/v1"
    assert [run["job"] for run in parsed["runs"]] == ["unit", "atomic"]
    assert not [path for path in index.parent.iterdir() if path.name.endswith(".tmp")]

    parsed["runs"][0]["state"] = "ok"
    index.write_text(json.dumps(parsed), encoding="utf-8")
    with pytest.raises(ValueError):
        evidence.load(index)


def test_no_invented_values(tmp_path):
    index = tmp_path / INDEX_REL
    minimal = {
        "repo": "hyvv",
        "head_sha": SHA,
        "job": "smoke",
        "source": "github",
        "state": None,
        "exit_codes": None,
        "started_at": None,
        "finished_at": None,
        "result_path": None,
    }

    assert evidence.append(index, minimal) is True
    doc = evidence.load(index)
    assert doc["schema"] == "bee-ci/evidence/v1"
    assert doc["runs"][0] == minimal
    assert doc["runs"][0]["state"] is None
    assert doc["runs"][0]["finished_at"] is None
    assert doc["runs"][0]["result_path"] is None

    partial = {"repo": "workflow", "head_sha": None, "job": None, "source": None}
    assert evidence.append(index, partial) is True
    stored = evidence.load(index)["runs"][1]
    assert stored["state"] is None
    assert stored["exit_codes"] is None
    assert stored["started_at"] is None
    assert stored["finished_at"] is None
    assert stored["result_path"] is None
    assert stored["head_sha"] is None

    assert evidence.append(index, _run(job="partial-exit", exit_codes=[{"step": "make"}])) is True
    stored = evidence.load(index)["runs"][2]
    assert stored["exit_codes"] == [{"step": "make", "exit_code": None}]
