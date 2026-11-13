"""Tests for the bee-CI shadow report renderer.

The renderer consumes the frozen ``bee-ci/evidence/v1`` index document and
produces one static, dark-mode HTML page.  These tests cover the acceptance
criteria: every run is listed in deterministic order, bee/github state
disagreements (and missing sides) are highlighted, and the output never leaks
private hosts, addresses or credentials.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPORT_DIR = Path(__file__).resolve().parents[1] / "report"
sys.path.insert(0, str(REPORT_DIR))

from render import render  # noqa: E402


def run(repo, head_sha, job, source, state):
    return {
        "repo": repo,
        "head_sha": head_sha,
        "job": job,
        "source": source,
        "state": state,
        "exit_codes": [{"step": "make test", "exit_code": 0 if state == "success" else 1}],
        "started_at": "2026-11-13T00:00:00Z",
        "finished_at": None if state == "pending" else "2026-11-13T00:01:00Z",
        "result_path": f"evidence/{repo}/{head_sha}/{job}-{source}.json",
    }


def index(*runs):
    return {"schema": "bee-ci/evidence/v1", "runs": list(runs)}


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40


def sample_document():
    return index(
        # Identical states: must not be flagged.
        run("workflow", SHA_A, "unit", "bee", "success"),
        run("workflow", SHA_A, "unit", "github", "success"),
        # A real disagreement.
        run("bundlebees", SHA_B, "lint", "bee", "success"),
        run("bundlebees", SHA_B, "lint", "github", "failure"),
        # Bee only: the github side is missing, never a pass.
        run("orbitdesktop", SHA_C, "build", "bee", "failure"),
        # Github only: the bee side is missing, never a pass.
        run("hyvv", SHA_D, "test", "github", "pending"),
    )


def disagreement_section(html):
    match = re.search(
        r'<section id="disagreements".*?</section>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None, "page must always contain a DISAGREEMENT section"
    return match.group(0)


def test_renders_runs():
    html = render(sample_document())

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<html" in html and "</html>" in html
    assert "DISAGREEMENT" in html
    assert "<script" not in html.lower()

    for item in sample_document()["runs"]:
        assert item["repo"] in html
        assert item["head_sha"][:12] in html
        assert item["job"] in html
        assert item["source"] in html

    # Every run is one row, in deterministic order: repo, head_sha, job, source.
    expected = sorted(
        sample_document()["runs"],
        key=lambda r: (r["repo"], r["head_sha"], r["job"], r["source"]),
    )
    positions = [html.index(f'data-result-path="{item["result_path"]}"') for item in expected]
    assert positions == sorted(positions)
    assert len(re.findall(r"<tr[^>]*class=\"run", html)) == len(expected)
    assert render(sample_document()) == html


def test_highlights_disagreements():
    html = render(sample_document())
    section = disagreement_section(html)

    # Mismatched run: highlighted, and both sides are shown with both states.
    assert "bundlebees" in section
    assert SHA_B[:12] in section
    assert "lint" in section
    assert "bee" in section and "github" in section
    assert "success" in section and "failure" in section

    # Missing sides are surfaced as missing, never as a pass.
    assert "orbitdesktop" in section and "missing" in section
    assert "hyvv" in section and "missing" in section

    # Identical states are not flagged.
    assert "workflow" not in section

    # Highlight class is present on the conflict, not on the matching pair.
    assert 'class="disagreement' in section
    assert 'class="run state-success disagree"' in html


def test_no_private_hosts_in_output():
    document = sample_document()
    document["runs"].append(
        run(
            "workflow",
            SHA_A,
            "deploy http://10.20.30.40:8080/secret and box.tail1234.ts.net ghp_"
            + "A" * 36,
            "github",
            "error",
        )
    )
    document["runs"].append(
        run("workflow", SHA_A, "<script>alert('x')</script>", "bee", "pending")
    )

    html = render(document)
    lowered = html.lower()

    forbidden = [
        r"https?://",
        r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])",
        r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b",
        r"\bgh[pousr]_[a-z0-9_]{20,}\b",
        r"\bgithub_pat_[a-z0-9_]{20,}\b",
        r"\bbearer\s+[a-z0-9._-]{8,}",
        r"<script",
    ]
    for pattern in forbidden:
        assert re.search(pattern, lowered) is None, f"leaked {pattern!r}"

    # Hostile markup is escaped rather than emitted as live markup.
    assert "&lt;script&gt;" in html
    assert "tail1234" not in html
    assert "10.20.30.40" not in html


def test_accepts_a_json_path(tmp_path):
    path = tmp_path / "index.json"
    path.write_text(json.dumps(sample_document()), encoding="utf-8")
    assert render(path) == render(sample_document())


def test_missing_document_is_refused(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        render(tmp_path / "absent.json")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
