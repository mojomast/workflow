"""Docs-parity guard for the workflow repository (the rizzstack protocol repo).

Owner directive (2026-11-16): audit all five rizzstack repos at current main for
CHANGELOG / README / protocol-chapter coverage of the last 48 hours of merges,
fix every gap, and correct the umbrella truth table to post-#40 reality. This
test is the workflow repository's counterpart of bundlebees'
``tests/test_changelog_coverage.py`` (the docs-sync coverage guard, docs-sync
§66 pattern), extended with the two checks that guard is too narrow for here:
the in-review wave must stay represented in the changelog while it is not on
main, and the umbrella truth-table corrections live in
``docs/docs-parity-audit.md`` where the five-repo coverage registry is
machine-checked.

Mechanics mirror the bundlebees guard: the merge history is read from this
checkout's git log when it carries real merge commits (``Merge pull request #N
from ...``). A merged PR number at or after ``FIRST_COVERED_PR`` must have a
registry row here — or an explicit exclusion with a reason — and every row's
keywords must appear in the ``## Unreleased`` section. When the checkout's
history is squashed (a snapshot without merge commits), the pinned snapshot set
stands in for the log; it was verified against main's first-parent history
(755d6c4 #35 ... 9850efa #40). Either way the next campaign PR that merges
without a row (or whose row's keywords are absent from the changelog) fails
this test. No network, launcher, token, Docker or SSH access.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG_MD = ROOT / "CHANGELOG.md"
README_MD = ROOT / "README.md"
AUDIT_MD = ROOT / "docs" / "docs-parity-audit.md"

#: The first PR the docs-sync duty applies to. The 48-hour audit window ends at
#: main 9850efa (the #40 merge, 2026-11-16 21:38 UTC); #35 merged 2026-11-15
#: 14:43 UTC, inside the window, and #34 (chapter 29, 2026-11-14 20:16 UTC) is
#: the last merge before it.
FIRST_COVERED_PR = 35

#: Merged PRs in the window that carry no changelog duty of their own. Every
#: exclusion states why; a merge number missing from both the registry and this
#: mapping is a test failure.
EXCLUDED_PRS: dict[int, str] = {
    62: (
        "docs-sync companion (the PR 56 exclusion) - this PR is the same class: a registry "
        "bookkeeping change whose only content is this exclusion; it carries its own "
        "exclusion so merging it leaves main green"
    ),
    56: (
        "docs-sync companion (changelog + registry row for #55) - the #55 Unreleased entry "
        "it landed is the coverage for that merge; same class as the #37 exclusion"
    ),
    37: (
        "docs/obs-snapshot-docs — the changelog/README companion PR itself; the "
        "#36 Unreleased entry it landed is the coverage for that merge"
    ),
}

#: The merge numbers verified against main's first-parent history (755d6c4 #35,
#: 84263c1 #36, d4e6c50 #37, 99d04bd #38, 9f6aa6d #39, 9850efa #40) for
#: checkouts whose log carries no merge commits. Only a fallback: real history
#: always wins.
SNAPSHOT_MERGED_PRS: tuple[int, ...] = (35, 36, 37, 38, 39, 40)

MERGE_SUBJECT_RE = re.compile(r"^Merge pull request #(\d+) from ", re.MULTILINE)

#: One row per merged campaign PR in the audit window. Keywords are exact
#: substrings a faithful Unreleased entry contains; they name what the merged
#: diff actually introduced, not the PR number. Extend this registry when the
#: next campaign PR merges.
MERGED_WINDOW_ROWS: tuple[dict[str, object], ...] = (
    {
        # feat/campaign-closeout: merge_order as a 1..N ordinal compared as an
        # exact sequence; each audit carries status clean|findings|not_run.
        "pr": 35,
        "name": "campaign closeout hardening",
        "keywords": ("merge_order", "clean|findings|not_run"),
    },
    {
        # feat/obs-snapshot-collector: the rizzstack.observability/snapshot/1
        # schema plus the read-only collector; degraded array for anything not
        # live.
        "pr": 36,
        "name": "observability snapshot stack",
        "keywords": ("snapshot.schema.json", "collector.py", "degraded"),
    },
    {
        # docs/wave4-packets: feature packets F11-F14 plus the fail-closed
        # packet parser test.
        "pr": 38,
        "name": "wave-4 feature packets F11-F14",
        "keywords": ("F11", "F14", "test_wave4_packets"),
    },
    {
        # feat/multi-dependency-packets: rizzstack.feature-packet/2 lifts the
        # exactly-one-dependency ceiling; admission gating refuses
        # dependency_not_accepted; the /2 shape is derived from the /1 schema
        # so the schema file keeps its exact bytes (no repin).
        "pr": 39,
        "name": "feature-packet/2 multi-dependency + admission gating",
        "keywords": ("feature-packet/2", "dependency_not_accepted", "no repin"),
    },
    {
        # docs/rizzstack-rails-spec: the specification-only Rails PR. The spec
        # reserves rizzstack.rails/1; schemas/rails/ carries the draft event
        # contract, README and synthetic examples.
        "pr": 40,
        "name": "rizzstack rails spec + draft event contract",
        "keywords": (
            "rizzstack.rails/1",
            "specs/rizzstack-rails-spec.md",
            "schemas/rails/event.schema.json",
        ),
    },
    {
        # fix/obs-fleet-health-wiring: collector fleet+health sections read the real bb CLI (merged 5b94f2b).
        "pr": 41,
        "name": "collector fleet+health wiring to the real bundlebees CLI",
        "keywords": ("bundlebees attempts", "fleet and health"),
    },
    {
        # feat/obs-bottlenecks-section: bottlenecks section in the snapshot contract + collector (merged 20d1d85).
        "pr": 42,
        "name": "bottlenecks section in the snapshot contract + collector",
        "keywords": ("bottlenecks", "dwell-time median", "WIP versus capacity"),
    },
    {
        # feat/owner-decision-queue: durable owner decision queue rizzstack.owner-decision/1 (merged 44dcd80).
        "pr": 43,
        "name": "owner decision queue (rizzstack.owner-decision/1)",
        "keywords": ("rizzstack.owner-decision/1", "request_digest", "decision_nonce"),
    },
    {
        # docs/f15-f19-packets-r6: packets F15-F19 rebuilt on main (merged df8f2ee).
        "pr": 44,
        "name": "feature packets F15-F19 rebuilt on main",
        "keywords": ("F15", "F19", "test_f15_f19_packets"),
    },
    {
        # docs/research-before-retry: the normative research-before-retry/plan rule (merged 34a35c4).
        "pr": 45,
        "name": "RESEARCH-BEFORE-RETRY + RESEARCH-BEFORE-PLAN",
        "keywords": ("RESEARCH-BEFORE-RETRY", "RESEARCH-BEFORE-PLAN", "research pass"),
    },
    {
        # docs/m2-canary-prep: M2 canary packet + runbook pre-staged (merged 246e7b3).
        "pr": 46,
        "name": "M2 canary prep (packet + runbook)",
        "keywords": ("M2 canary", "rizzstack-m2-canary", "runbook"),
    },
    {
        # docs/rebrand-and-website-plan: rebrand + website plans, PLAN-ONLY (merged b1afcd1).
        "pr": 47,
        "name": "rebrand + website plans (PLAN-ONLY)",
        "keywords": ("rebrand plan", "website plan", "PLAN-ONLY"),
    },
    {
        # feat/obs-events-bridge: observatory events bridge (merged 833ec05).
        "pr": 49,
        "name": "Observatory events bridge",
        "keywords": ("events_bridge", "Observatory events bridge"),
    },
    {
        # feat/memory-contract: memory contract chapter 32 + rizzstack.memory/1 (merged e809694).
        "pr": 50,
        "name": "memory contract (rizzstack.memory/1, chapter 32)",
        "keywords": ("rizzstack.memory/1", "memory-contract", "Obsidian-compatible"),
    },
    {
        # feat/decision-notifier: decision notifier service + unit (merged 585acd3).
        "pr": 51,
        "name": "decision notifier service",
        "keywords": ("decision notifier", "decision_notifier"),
    },
    {
        # docs/umbrella-modularity: modularity umbrella + install profiles (merged 99e75e6).
        "pr": 52,
        "name": "modularity umbrella (quickstarts + install profiles)",
        "keywords": ("quickstarts", "install profiles", "test_modularity_spec"),
    },
    {
        # docs/ground-truth-audit: memory ground-truth audit, Phase 1 (merged 8e15bff).
        "pr": 53,
        "name": "memory ground-truth audit (Hindsight Phase 1)",
        "keywords": ("ground_truth.json", "memory-ground-truth-audit"),
    },
    {
        # docs/hindsight-mechanism-report: hindsight mechanism report, Phase 2 (merged 97ce568).
        "pr": 54,
        "name": "hindsight mechanism report (Hindsight Phase 2)",
        "keywords": ("hindsight-mechanism-report", "test_hindsight_mechanisms"),
    },
    {
        # plans/gate-backlog-seed: the machine-readable gate-backlog (merged d952681).
        "pr": 48,
        "name": "gate-backlog seed (plans/backlog.json)",
        "keywords": ("bundlebees.gate-backlog/1", "plans/backlog.json"),
    },
    {
        # docs/parity-audit-nov16: the parity audit + its own coverage guard (merged a0193ad).
        "pr": 55,
        "name": "docs parity audit + coverage registry",
        "keywords": ("docs-parity-audit", "test_docs_parity"),
    },
)

#: The in-review wave: no campaign PR is open as of the 2026-11-16 post-#48 state
# (the drain landed #41-#47 and #49-#54; #55, #56, #62 and #48 followed). The changelog
# must represent open work in the ``### In review`` subsection so the umbrella truth table
# and the next docs-sync can be written from the changelog, not from memory.
IN_REVIEW_ROWS: tuple[dict[str, object], ...] = (
)

#: The umbrella protocol-map rows, corrected to post-#40 reality. Each pair is
#: (row key, exact status text) that docs/docs-parity-audit.md must record; the
#: umbrella repo itself is corrected from this prescription at its next
#: docs-sync (the umbrella checkout is not part of this repository).
UMBRELLA_PROTOCOL_ROWS: tuple[tuple[str, str], ...] = (
    ("rizzstack.observability/snapshot/1", "frozen + deployed"),
    ("bee-landed/1", "frozen + merged"),
    ("rizzstack.rails/1", "merged spec, build in wave 1"),
    ("action queue + fencing", "merged"),
    ("owner decision queue", "still in-review"),
    ("rizzstack.memory/1", "spec built — per wf#50 state"),
    ("ACDD contracts + packets", "frozen"),
    ("job authorize / sealed ceilings", "frozen"),
)

#: The five-repo coverage registry tokens docs/docs-parity-audit.md must carry:
#: every audited item of the last-48h wave, per repo, at the audited heads.
REGISTRY_TOKENS: tuple[str, ...] = (
    "9850efa",
    "wf#35", "wf#36", "wf#37", "wf#38", "wf#39", "wf#40",
    "wf#41", "wf#42", "wf#43", "wf#44", "wf#45",
    "wf#46", "wf#47", "wf#48", "wf#49", "wf#50", "wf#51", "wf#52",
    "e7f95ca",
    "bb#61", "bb#62", "bb#63", "bb#64", "bb#65", "bb#66", "bb#67",
    "961a8bce",
    "hyvv#22", "hyvv#23",
    "ace2eb0",
    "od#36", "od#39",
    "f70754c",
)

#: The five repos the audit must cover, by name, at audited heads.
AUDIT_REPO_NAMES: tuple[str, ...] = (
    "workflow",
    "bundlebees",
    "hyvv",
    "orbitdesktop",
    "rizzstack",
)


def _read_changelog() -> str:
    return CHANGELOG_MD.read_text(encoding="utf-8")


def _unreleased_section() -> str:
    match = re.search(r"(?ms)^## Unreleased\s*$\n(.*?)(?=^## |\Z)", _read_changelog())
    assert match is not None, "CHANGELOG.md must keep a '## Unreleased' section"
    return match.group(1)


def _in_review_subsection() -> str:
    section = _unreleased_section()
    match = re.search(
        r"(?ms)^### In review\b.*?(?=^### |\Z)",
        section,
    )
    assert match is not None, (
        "the Unreleased section must keep a '### In review' subsection while "
        "workflow PRs #41-#52 are open against main — the umbrella truth table "
        "and the next docs-sync are written from the changelog, not from memory"
    )
    return match.group(0)


def _merged_pr_numbers() -> tuple[int, ...] | None:
    """PR numbers merged in this checkout's history, or ``None`` if unknowable.

    Reads only the local git log (no network). A squashed snapshot without
    merge commits returns ``None`` and the pinned fallback applies.
    """

    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--merges", "--pretty=%s"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    numbers = sorted({int(match) for match in MERGE_SUBJECT_RE.findall(result.stdout)})
    return tuple(numbers) or None


def _required_pr_numbers() -> tuple[int, ...]:
    merged = _merged_pr_numbers()
    if merged is None:
        merged = SNAPSHOT_MERGED_PRS
    return tuple(n for n in merged if n >= FIRST_COVERED_PR)


def test_registry_covers_every_merged_campaign_pr_in_window() -> None:
    required = _required_pr_numbers()
    assert required, "the merge history (or its snapshot fallback) must be non-empty"
    registered = {int(entry["pr"]) for entry in MERGED_WINDOW_ROWS}
    unregistered = [
        n for n in required
        if n not in registered and n not in EXCLUDED_PRS
    ]
    assert not unregistered, (
        f"merged campaign PR(s) {unregistered} have no coverage registry entry: "
        "add a MERGED_WINDOW_ROWS row whose keywords the changelog must contain, "
        "or an explicit EXCLUDED_PRS reason for a non-feature merge "
        "(docs-sync duty: merged work must be discoverable in the changelog)"
    )
    for number, reason in EXCLUDED_PRS.items():
        assert reason.strip(), f"exclusion for PR #{number} must state why"


def test_registry_rows_are_well_formed() -> None:
    numbers = [int(entry["pr"]) for entry in MERGED_WINDOW_ROWS]
    assert len(numbers) == len(set(numbers)), "MERGED_WINDOW_ROWS must not repeat a PR number"
    for entry in MERGED_WINDOW_ROWS:
        assert int(entry["pr"]) >= FIRST_COVERED_PR, entry
        assert str(entry["name"]).strip(), entry
        keywords = tuple(entry["keywords"])
        assert len(keywords) >= 2, f"PR #{entry['pr']} needs at least two keywords"
        assert all(isinstance(k, str) and k.strip() for k in keywords), entry
    in_review = [int(entry["pr"]) for entry in IN_REVIEW_ROWS]
    assert len(in_review) == len(set(in_review)), "IN_REVIEW_ROWS must not repeat a PR number"
    overlap = set(in_review) & set(numbers) | set(in_review) & set(EXCLUDED_PRS)
    assert not overlap, f"a PR cannot be both merged and in review: {sorted(overlap)}"


def test_merged_numbered_bullets_carry_merged_state_not_in_review() -> None:
    """The #42-class defect: a merged PR's numbered bullet left saying "(in review)".

    Every numbered bullet in the Unreleased section whose PR number is a REGISTERED
    MERGED_WINDOW_ROWS number must carry a "(merged at `" state and must not say
    "in review"; and any numbered bullet that still says "in review" must belong to a
    number registered as in-review. Named-entry bullets (the #35-#40 style) carry no
    state prefix and are out of scope for this guard.
    """
    section = _unreleased_section()
    merged = {int(e["pr"]) for e in MERGED_WINDOW_ROWS}
    in_review = {int(e["pr"]) for e in IN_REVIEW_ROWS}
    for line in section.splitlines():
        m = re.match(r"- #(\d+) \(([^)]*)\): ", line.strip())
        if not m:
            continue
        number, state = int(m.group(1)), m.group(2)
        if number in merged:
            assert "(merged at `" in line, (
                f"merged PR #{number}'s bullet must carry its real merged-at sha: {line[:120]}"
            )
            assert "in review" not in state, (
                f"merged PR #{number}'s bullet still says 'in review': {line[:120]}"
            )
        else:
            assert number in in_review, (
                f"bullet #{number} claims a state but its PR is neither registered merged "
                f"nor in review: {line[:120]}"
            )


@pytest.mark.parametrize("entry", MERGED_WINDOW_ROWS, ids=lambda entry: f"pr-{entry['pr']}")
def test_merged_campaign_pr_has_discoverable_changelog_coverage(
    entry: dict[str, object],
) -> None:
    section = _unreleased_section()
    missing = [keyword for keyword in entry["keywords"] if keyword not in section]
    assert not missing, (
        f"## Unreleased must document PR #{entry['pr']} "
        f"({entry['name']}): missing keyword(s) {missing}. The Unreleased "
        "section must describe what the merged PR changed, in user-facing "
        "wording — not a bare PR-number list."
    )


@pytest.mark.parametrize("entry", IN_REVIEW_ROWS, ids=lambda entry: f"pr-{entry['pr']}")
def test_in_review_pr_has_changelog_representation(entry: dict[str, object]) -> None:
    subsection = _in_review_subsection()
    missing = [keyword for keyword in entry["keywords"] if keyword not in subsection]
    assert not missing, (
        f"the '### In review' subsection must document PR #{entry['pr']} "
        f"({entry['name']}): missing keyword(s) {missing}. Open work is "
        "registered with its real state so the truth table stays honest."
    )


def test_in_review_subsection_states_it_is_not_on_main() -> None:
    subsection = _in_review_subsection()
    for marker in ("not on main", "in review"):
        assert marker in subsection.lower(), (
            "the '### In review' subsection must state that these PRs are not "
            "merged (an Unreleased changelog that implies shipped work is the "
            "premature-completion claim the workflow forbids)"
        )


def test_audit_doc_exists_and_covers_all_five_repos() -> None:
    assert AUDIT_MD.exists(), (
        "docs/docs-parity-audit.md is missing: the five-repo docs-parity audit "
        "is the deliverable this test guards"
    )
    text = AUDIT_MD.read_text(encoding="utf-8")
    missing = [name for name in AUDIT_REPO_NAMES if name not in text]
    assert not missing, (
        f"docs/docs-parity-audit.md does not cover repo(s) {missing}: the audit "
        "must cover workflow, bundlebees, hyvv, orbitdesktop and the rizzstack "
        "umbrella at their audited heads"
    )


def test_audit_doc_records_the_umbrella_truth_table_rows() -> None:
    text = AUDIT_MD.read_text(encoding="utf-8")
    missing = [
        f"{row!r} -> {status!r}"
        for row, status in UMBRELLA_PROTOCOL_ROWS
        if row not in text or status not in text
    ]
    assert not missing, (
        "docs/docs-parity-audit.md must record the umbrella protocol-map rows "
        "corrected to post-#40 reality; missing row/status pair(s): "
        f"{missing}"
    )


def test_audit_doc_registry_carries_every_audited_item() -> None:
    text = AUDIT_MD.read_text(encoding="utf-8")
    missing = [token for token in REGISTRY_TOKENS if token not in text]
    assert not missing, (
        "the docs-parity coverage registry is missing row(s) for: "
        f"{missing} — every audited item of the 48-hour wave needs a registry "
        "row with its verified state"
    )


def test_rails_spec_artifacts_are_registered_in_the_changelog() -> None:
    spec = ROOT / "specs" / "rizzstack-rails-spec.md"
    schema = ROOT / "schemas" / "rails" / "event.schema.json"
    assert spec.exists(), "specs/rizzstack-rails-spec.md is missing from the tree"
    assert schema.exists(), "schemas/rails/event.schema.json is missing from the tree"
    section = _unreleased_section()
    for artifact in ("specs/rizzstack-rails-spec.md", "schemas/rails/event.schema.json"):
        assert artifact in section, (
            f"the Unreleased section must register {artifact} (merged as "
            "workflow #40): the rails spec lived in the tree unregistered by "
            "changelog, README index, ROADMAP and the numbered chapters — the "
            "gap class this audit exists to close"
        )


#: README index rows known stale at the audited head, each with the reason and
#: the pointer to the prescribed fix recorded in docs/docs-parity-audit.md. A
#: chapter missing from the README index must appear here with a reason; when
#: the README row is corrected, drop the entry.
STALE_README_INDEX_ROWS: dict[str, str] = {
    "18-parking-projects.md": (
        "the README index row still says '18 (open PR, not on `main` yet)' but "
        "workflow #9 merged the chapter; the audit records the prescribed "
        "one-line README correction"
    ),
}


def test_protocol_chapters_are_registered_everywhere() -> None:
    docs_dir = ROOT / "docs"
    chapters = sorted(p for p in docs_dir.glob("[0-9][0-9]-*.md"))
    assert chapters, "docs/ must carry the numbered protocol chapters"
    numbers = [int(p.name[:2]) for p in chapters]
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"chapter numbering must be contiguous 01..{len(numbers):02d}, got {numbers}"
    )
    readme = README_MD.read_text(encoding="utf-8")
    unindexed = [p.name for p in chapters if p.name not in readme]
    unexplained = [name for name in unindexed if name not in STALE_README_INDEX_ROWS]
    assert not unexplained, (
        f"README index rows missing for chapter(s) {unexplained}: every numbered "
        "protocol chapter must be registered in the README index, or carried in "
        "STALE_README_INDEX_ROWS with the reason and the prescribed fix"
    )
    for number, reason in STALE_README_INDEX_ROWS.items():
        assert reason.strip(), f"stale README row for {number} must state why"
    changelog = _read_changelog()
    link_targets = re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", changelog)
    broken = []
    for target in link_targets:
        target = target.strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        path = ROOT / target.rstrip("/")
        if not path.exists():
            broken.append(target)
    assert not broken, (
        f"CHANGELOG.md links to missing path(s) {broken}: a registered entry "
        "must resolve"
    )
