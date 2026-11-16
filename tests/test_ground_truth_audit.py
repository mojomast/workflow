"""Structural validation for the Phase-1 ground-truth audit (Hindsight brief).

The audit classifies every evidence system named in the brief into exactly one
of SPECIFIED / IMPLEMENTED+TESTED / INTEGRATED / DEPLOYED / VERIFIED-IN-OPERATION
and backs every classification with citations. These tests are RED-first: they
failed before docs/memory-ground-truth-audit.md and ground_truth.json existed,
and they now keep the table and the machine-readable companion honest.

They validate structure only, never the truth of a claim: a row that says
VERIFIED-IN-OPERATION must cite a recorded runtime observation, and this module
checks that the citation is present and shaped correctly — it cannot re-run the
observed system.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "memory-ground-truth-audit.md"
JSON = ROOT / "ground_truth.json"

LEVELS = [
    "SPECIFIED",
    "IMPLEMENTED+TESTED",
    "INTEGRATED",
    "DEPLOYED",
    "VERIFIED-IN-OPERATION",
]

# Every evidence system the Hindsight brief names, as this audit rows it.
# The brief's compound row "bee-landed events + usage payloads" and the two
# halves of "campaign records" are split so each gets exactly one level.
REQUIRED_SYSTEM_IDS = {
    "bee-landed",
    "usage-payloads",
    "attempt-records",
    "recovery-digests",
    "feature-packets",
    "acdd-contracts",
    "return-manifests",
    "review-findings",
    "ci-receipts",
    "action-queue",
    "obs-snapshots",
    "observatory",
    "campaign-report-format",
    "campaign-records-store",
    "lease-payloads",
    "deploy-provenance",
    "memory-contract",
}

ROW_RE = re.compile(
    r"^\| (?P<name>[^|]+?) \| `(?P<id>[a-z0-9-]+)` \| "
    r"(?P<level>[A-Z][A-Z+\-]+) \| (?P<evidence>.+?) \| \S+ \|$"
)
# A citation is a repo-relative file, optionally with a line or range anchor.
CITATION_RE = re.compile(
    r"(?:[\w./~-]+/)?[\w.-]+\.(?:py|md|json|ya?ml|service|sh)(?::\d+(?:-\d+)?)?"
)
RUNTIME_RE = re.compile(r"RUNTIME:\s*\d{4}-\d{2}-\d{2}")
LIVE_RE = re.compile(r"LIVE-VERIFIED:\s*\d{4}-\d{2}-\d{2}")
TEST_RE = re.compile(r"tests/test_[\w./:-]+|contrib/[\w/-]+/tests/test_[\w./:-]+")


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert DOC.exists(), "docs/memory-ground-truth-audit.md is missing"
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rows(doc_text: str) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []
    for line in doc_text.splitlines():
        match = ROW_RE.match(line.strip())
        if not match:
            continue
        row_id = match.group("id")
        if row_id in found:
            duplicates.append(row_id)
        found[row_id] = match.groupdict()
    assert not duplicates, f"duplicate classification rows: {duplicates}"
    return found


def test_the_audit_doc_and_companion_exist() -> None:
    assert DOC.exists(), "docs/memory-ground-truth-audit.md is missing"
    assert JSON.exists(), "ground_truth.json is missing"


def test_every_brief_named_system_has_exactly_one_row(
    rows: dict[str, dict[str, str]],
) -> None:
    missing = REQUIRED_SYSTEM_IDS - set(rows)
    extra = set(rows) - REQUIRED_SYSTEM_IDS
    assert not missing, f"classification rows missing for: {sorted(missing)}"
    assert not extra, f"classification rows outside the brief's systems: {sorted(extra)}"


def test_every_row_is_exactly_one_allowed_level(
    rows: dict[str, dict[str, str]],
) -> None:
    for row_id, row in rows.items():
        assert row["level"] in LEVELS, (
            f"{row_id}: level {row['level']!r} is not one of {LEVELS}"
        )


def test_every_row_carries_file_citations(rows: dict[str, dict[str, str]]) -> None:
    for row_id, row in rows.items():
        citations = CITATION_RE.findall(row["evidence"])
        assert citations, f"{row_id}: no file:line citation in the evidence cell"
        assert len(citations) >= 2, (
            f"{row_id}: needs at least two citations, found {citations}"
        )


def test_no_level_above_specified_rests_on_pr_merge_alone(
    rows: dict[str, dict[str, str]],
) -> None:
    """A level above SPECIFIED must cite a test, a recorded runtime observation,
    or a live-verified probe. A merge/PR reference by itself justifies nothing."""
    for row_id, row in rows.items():
        if row["level"] == "SPECIFIED":
            continue
        evidence = row["evidence"]
        holds = (
            TEST_RE.search(evidence)
            or RUNTIME_RE.search(evidence)
            or LIVE_RE.search(evidence)
        )
        assert holds, (
            f"{row_id}: level {row['level']} has no test citation, no RUNTIME "
            f"observation and no LIVE-VERIFIED probe in its evidence cell"
        )


def test_deployed_and_verified_rows_carry_runtime_observations(
    rows: dict[str, dict[str, str]],
) -> None:
    for row_id, row in rows.items():
        if row["level"] in ("DEPLOYED", "VERIFIED-IN-OPERATION"):
            assert RUNTIME_RE.search(row["evidence"]), (
                f"{row_id}: level {row['level']} must cite a dated RUNTIME "
                f"observation, found: {row['evidence']}"
            )


def test_memory_contract_row_reports_no_default_branch_artifacts(
    rows: dict[str, dict[str, str]],
) -> None:
    row = rows["memory-contract"]
    assert row["level"] == "SPECIFIED"
    assert "not merged" in row["evidence"].lower(), (
        "memory-contract row must state the contract is not merged into a "
        "default branch"
    )
    assert "39f340c6" in row["evidence"], (
        "memory-contract row must cite the verified branch head"
    )


def test_companion_json_parses_and_declares_its_shape() -> None:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    assert data["schema"] == "ground-truth-audit/1"
    audit = data["audit"]
    for key in ("date", "base", "method"):
        assert key in audit, f"audit.{key} missing"
    base = audit["base"]
    assert base["upstream_head"] == (
        "9f6aa6dc7a74890ef2284d7aa4432efc9b6a4169"
    ), "the audit must pin the workflow head it classifies against"


def test_companion_json_heads_match_live_verification() -> None:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    heads = data["heads"]
    verified = heads["verified"]
    assert verified["workflow"] == (
        "9f6aa6dc7a74890ef2284d7aa4432efc9b6a4169"
    )
    assert verified["bundlebees"] == (
        "e7f95ca5bfba96734ab5dba89aced9b1fbbd6d30"
    )
    assert verified["orbitdesktop"] == (
        "ace2eb0009af4fccc510ca569bb9715218bd9517"
    )
    # The brief's hyvv and umbrella heads are ancestors, not current main.
    stale = heads["brief_heads_now_ancestors"]
    assert "47d25c2" in stale["hyvv"]["brief_head"]
    assert stale["hyvv"]["current_main"] == (
        "961a8bce501d0ce38922baeb6e5c10347d1f7efd"
    )
    assert "5bf5174" in stale["rizzstack"]["brief_head"]
    assert stale["rizzstack"]["current_main"] == (
        "f70754cce953117bf734588ec1a6f833b2009324"
    )


def test_companion_json_systems_match_the_table(
    rows: dict[str, dict[str, str]],
) -> None:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    systems = {s["id"]: s for s in data["systems"]}
    assert set(systems) == REQUIRED_SYSTEM_IDS
    for row_id, row in rows.items():
        assert systems[row_id]["classification"] == row["level"], (
            f"{row_id}: json level {systems[row_id]['classification']!r} "
            f"disagrees with the table's {row['level']!r}"
        )


def test_companion_json_every_system_carries_evidence_citations() -> None:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    for system in data["systems"]:
        flat = json.dumps(system.get("evidence", {}))
        citations = CITATION_RE.findall(flat)
        assert citations, f"{system['id']}: no file citation anywhere in evidence"
        if system["classification"] != "SPECIFIED":
            holds = (
                TEST_RE.search(flat)
                or RUNTIME_RE.search(flat)
                or LIVE_RE.search(flat)
            )
            assert holds, (
                f"{system['id']}: level above SPECIFIED without a test, RUNTIME "
                f"or LIVE-VERIFIED citation"
            )


def test_companion_json_runtime_probes_recorded_with_results() -> None:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    probes = data["runtime_probes"]
    assert isinstance(probes, list) and len(probes) >= 4, (
        "the audit must probe live state (ingest service, observatory serving, "
        "launcher paths, coordinator store)"
    )
    for probe in probes:
        assert probe.get("probe"), "each probe needs a description"
        assert probe.get("result"), "each probe needs its observed result"
        assert probe.get("separates", ""), (
            "each probe must name the deployed/verified distinction it informs"
        )


def test_companion_json_marks_the_umbrella_as_entry_point_only() -> None:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    umbrella = data["umbrella"]
    assert umbrella["role"] == "protocol-distribution-entry-point"
    assert umbrella["runtime_element"] is False
    assert "systems" not in umbrella or not umbrella["systems"], (
        "the umbrella must not be listed as a runtime element of the stack"
    )


def test_companion_json_records_the_environment_constraints() -> None:
    data = json.loads(JSON.read_text(encoding="utf-8"))
    constraints = data["constraints"]
    text = json.dumps(constraints)
    assert "no sibling repos" in text.lower() or "sibling repos absent" in text.lower()
    assert "~/.hermes" in text, "the absent coordinator store must be recorded"
    assert "squashed" in text.lower(), "the single-commit history must be recorded"


def test_doc_states_the_ladder_definitions_and_the_live_verification_date(
    doc_text: str,
) -> None:
    for level in LEVELS:
        assert level in doc_text, f"the doc never defines {level}"
    assert "2026-11-16" in doc_text, (
        "the doc must date the live verification pass"
    )
    assert "merged" in doc_text.lower() and "operational" in doc_text.lower(), (
        "the doc must separate merged from operational"
    )
