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
    131: (
        "docs-sync companion (the workflow #130 coverage row + its Unreleased bullet: the "
        "ci-gate aggregate check): a registry bookkeeping change; it carries its own "
        "exclusion so merging it leaves main green"
    ),
    123: (
        "docs-sync companion (registry rows + Unreleased bullets for the wave-2 PRs 120/121/122): "
        "a bookkeeping change with no feature content of its own"
    ),
    118: (
        "docs-sync companion (registry rows + Unreleased bullets for the slop-lint wave-1 PRs "
        "115/116/117): a bookkeeping change with no feature content of its own"
    ),
    119: (
        "docs-sync companion of 118: carries its own exclusion for 118 so merging it leaves "
        "main green"
    ),
    99: (
        "docs-sync companion (the workflow #98 coverage row + its Unreleased bullet: the "
        "memory vault service DiskVault landing with its 89-test disk suite) - same class "
        "as 37/56/62/64/67/72/73/77/78/79/81/84/85/86/87/89: a registry bookkeeping change "
        "whose only content is this exclusion plus the #98 coverage row; it carries its "
        "own exclusion so merging it leaves main green"
    ),
    89: (
        "docs-sync companion (the workflow #88 coverage row + its Unreleased bullet: the "
        "trial-harness arms/report landing with the att_f9e680d217bb458b repair and the "
        "att_b9ad60999d524dbd round-2 APPROVE evidence) - same class as 84/85/86/87: a "
        "registry bookkeeping change whose only content is this exclusion plus the #88 "
        "coverage row; it carries its own exclusion so merging it leaves main green"
    ),
    87: (
        "docs-sync companion (the rails landing batch adoption: R03-done completion, R13 "
        "two-PR lane, R04/R10/R08 dispatch transitions with the recorded zero-delivery loss "
        "and base-deviation disclosures) - same class as 84/85/86: a registry bookkeeping "
        "change whose only content is this exclusion plus the adoption transitions; it "
        "carries its own exclusion so merging it leaves main green"
    ),
    86: (
        "docs-sync companion (the RAILS-R02 backlog adoption: planned->dispatched with the "
        "att_f67c7573 / bb PR 70 merged-as-9287d91 evidence chain) - same class as 81/84/85: a "
        "registry bookkeeping change whose only content is this exclusion plus the adoption "
        "transition; it carries its own exclusion so merging it leaves main green"
    ),
    85: (
        "docs-sync companion (the RAILS-R03 backlog adoption: planned->dispatched with the "
        "att_4be4db64 / od PR 43 coordinator-apply evidence chain) - same class as 81/84: a "
        "registry bookkeeping change whose only content is this exclusion plus the adoption "
        "transition; it carries its own exclusion so merging it leaves main green"
    ),
    84: (
        "docs-sync companion (the PR 82 + PR 83 coverage rows, their merged-window bullets and "
        "the RAILS-R01 backlog adoption) - same class: a registry bookkeeping change whose only "
        "content is this exclusion plus the #82/#83 registry rows, bullets and the R01 adoption; it "
        "carries its own exclusion so merging it leaves main green"
    ),
    81: (
        "docs-sync companion (the PR 80 coverage row + its merged-window bullet) - same "
        "class: a registry bookkeeping change whose only content is this exclusion plus "
        "the #80 registry row and bullet; it carries its own exclusion so merging it "
        "leaves main green"
    ),
    79: (
        "docs-sync companion (the PR 74 coverage row + its merged-window bullet) - same "
        "class: a registry bookkeeping change whose only content is this exclusion plus "
        "the #74 registry row and bullet; it carries its own exclusion so merging it "
        "leaves main green"
    ),
    78: (
        "docs-sync companion (the PR 70 coverage row + its merged-window bullet) - same "
        "class: a registry bookkeeping change whose only content is this exclusion plus "
        "the #70 registry row and bullet; it carries its own exclusion so merging it "
        "leaves main green"
    ),
    77: (
        "docs-sync companion (the PR 75 coverage row + its merged-window bullet) - same "
        "class: a registry bookkeeping change whose only content is this exclusion plus "
        "the #75 registry row and bullet; it carries its own exclusion so merging it "
        "leaves main green"
    ),
    73: (
        "docs-sync companion (the PR 69 coverage row + its Unreleased bullet) - same "
        "class: a registry bookkeeping change whose only content is this exclusion plus "
        "the #69 registry row and bullet; it carries its own exclusion so merging it "
        "leaves main green"
    ),
    72: (
        "docs-sync companion (the PR 68 coverage row) - same class: a registry "
        "bookkeeping change whose only content is this exclusion plus the #68 "
        "registry row; it carries its own exclusion so merging it leaves main green"
    ),
    67: (
        "docs-sync companion (the main Unreleased-heading repair after the #57 self-"
        "registration mangle) - same class: a changelog-truth repair whose own coverage "
        "is this exclusion; it carries its own exclusion so merging it leaves main green"
    ),
    64: (
        "docs-sync companion (the PR 48 coverage row + entry) - same class: a registry "
        "bookkeeping change whose test-file diff is exclusions plus the #48 registry row; "
        "it carries its own exclusion so merging it leaves main green"
    ),
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
    {
        # docs/hindsight-synthesis: Phase 3 gap analysis + trial design + gated plan.
        "pr": 57,
        "name": "hindsight synthesis (Phase 3: trial design + gated plan)",
        "keywords": ("hindsight-synthesis", "controlled trial", "WP-0"),
    },
    {
        # docs/rebrand-execution-runbook: recovery path + same-place mapping + parallel operation.
        "pr": 58,
        "name": "rebrand execution runbook",
        "keywords": ("rebrand-execution-runbook", "same-place mapping", "parallel operation"),
    },
    {
        # docs/rails-w2-conversions-r3: R00/R01 destruction evidence + re-dispatch remedy.
        "pr": 59,
        "name": "rails R00/R01 conversion r3",
        "keywords": ("rails-w2-conversions", "re-dispatch remedy", "destruction evidence"),
    },
    {
        # docs/coordinator-failure-report-2026-11-16: the failure report + packaged
        # evidence (merged e356b3d).
        "pr": 68,
        "name": "coordinator failure report 2026-11-16",
        "keywords": ("coordinator-failure-report-2026-11-16", "failure-evidence-2026-11-16"),
    },
    {
        # contrib/obs-fleet-delta: the observability fleet delta ported onto the
        # main collector (merged 77f98cb).
        "pr": 69,
        "name": "observability fleet delta port",
        "keywords": ("lease-store fallback", "clock-type normalization", "empty-state contract"),
    },
    {
        # contrib/rizzstack-observability: /obs-snapshot alias for deploy parity
        # (merged a9e1ffd).
        "pr": 75,
        "name": "collector obs-snapshot alias",
        "keywords": ("obs-snapshot", "alias", "deploy parity", "auth bypass"),
    },
    {
        # docs/coordination-reliability-research: the FC-1..FC-6
        # coordination-reliability research doc with the D-1 correction: the
        # pinned launcher's diff base is the recorded seed commit, not sandbox
        # HEAD (verified in review against hyvv@5bee1a87 and hyvv main).
        "pr": 70,
        "name": "coordination-reliability research doc",
        "keywords": ("coordination-reliability", "FC-1", "seed commit", "5bee1a87"),
    },
    {
        # docs/rails-wave2-backlog: the 22-slice RAILS wave-2 seed - the real
        # loader accepts it (24 slices, budget lanes:7/bees:8) and dependency
        # gating rides exact RAILS-* depends_on edges (r3 canonicalization).
        "pr": 74,
        "name": "rails wave-2 backlog seed",
        "keywords": ("RAILS-R00", "depends_on", "load_backlog", "vendor-manifest.json"),
    },
    {
        # rails R00 feasibility: pinned source matrix + sanitized trace/shape
        # descriptors + file+line hook citations (Q2 explicitly UNRESOLVED),
        # RED-first suite 15/15; review mutation-proved the RED property.
        "pr": 80,
        "name": "rails R00 feasibility slice",
        "keywords": ("RAILS-R00", "rails-feasibility", "source-matrix", "UNRESOLVED"),
    },
    {
        # docs/hindsight-trial-harness: trial-harness PART 1 (fixtures +
        # evaluator + tests) - the F1 per-file-commit remedy delivery,
        # coordinator-reconciled after the staleness window; PART 2 follows
        # against the same branch.
        "pr": 82,
        "name": "trial harness PART 1 fixtures + evaluator + tests",
        "keywords": ("trial-harness", "test_trial_harness", "att_e1f3fb747b354685", "PART 1"),
    },
    {
        # rails/r01-contract: the RAILS-R01 contract layer (schemas + hash
        # vectors + RED-first contract tests) - the F1-remedy attempt 2,
        # coordinator-reconciled after the staleness window.
        "pr": 83,
        "name": "rails R01 contract layer",
        "keywords": ("RAILS-R01", "test_rails_contract", "att_e0cff87d85a644e5", "hash-vectors"),
    },
    {
        # docs/hindsight-trial-harness-arms: the Hindsight trial harness PART 2
        # (three deterministic arms + the report layer) landed after one RED-first
        # worker repair (att_f9e680d217bb458b: B1 baseline pairing restored to
        # ARM_B, B2 single evaluator call, M8-mirror hack removed) and an
        # independent round-2 re-review (att_b9ad60999d524dbd, APPROVE zero
        # blocking; CI 14/14 at the repaired head).
        "pr": 88,
        "name": "trial harness PART 2 arms + report",
        "keywords": ("arms.py", "evaluate_trial", "H123_BASELINE", "exit 0/1/2"),
    },
    {
        # feat/memory-vault-service: the disk-backed vault service for the
        # rizzstack.memory/1 contract - DiskVault(root) over the contract
        # layout, append-only log.md receipts with sequence numbers, vault_rev
        # advancing on every accepted write; query is honest grep (M2 owns the
        # index); no runtime wiring, MEMORY_ENABLED stays off.
        "pr": 98,
        "name": "memory vault service M1",
        "keywords": ("rizzstack_memory", "DiskVault", "vault_rev", "test_memory_vault_disk"),
    },
    {
        # docs/readme-visuals: the README poster redrawn from main's code as a
        # Night Hive render, with the HTML source and the render script shipped
        # beside the PNG and the alt text, caption and mermaid flow updated.
        "pr": 100,
        "name": "workflow poster redraw",
        "keywords": ("Night Hive", "render.mjs", "workflow-map.html"),
    },
    {
        # perf/collector-parallel-cli: the collector's independent CLI reads
        # (fleet attempts/status, per-repo gh) run in a thread pool, so a cold
        # snapshot costs the slowest read instead of their sum (~10.8 s -> ~3.6 s);
        # --cli-workers 1 restores strictly sequential reads.
        "pr": 107,
        "name": "collector independent CLI reads concurrent",
        "keywords": ("independent CLI reads", "test_obs_parallel_reads", "concurrently"),
    },
    {
        # tools/slop-lint: stdlib slop linter with a per-file+rule baseline ratchet (wave 1).
        "pr": 116,
        "name": "slop-lint engine, baseline ratchet and CLI",
        "keywords": ("slop-lint", "baseline ratchet", "swallowed-exception"),
    },
    {
        # .github/workflows/slop-lint.yml: report-only CI job for slop-lint (wave 1).
        "pr": 115,
        "name": "slop-lint report-only workflow",
        "keywords": ("slop-lint.yml", "report-only", "job summary"),
    },
    {
        # contrib/bee-ci/report/pr_summary.py: escaped, redacted PR summary renderer (wave 1).
        "pr": 117,
        "name": "PR summary renderer",
        "keywords": ("pr_summary", "render_pr_summary", "GAP"),
    },
    {
        # schemas/tdd-evidence.schema.json: optional metrics object synced from bundlebees (wave 2).
        "pr": 120,
        "name": "evidence schema optional metrics object",
        "keywords": ("tdd-evidence.schema.json", "optional `metrics` object", "review_findings"),
    },
    {
        # slop-baseline.json + CI path fix: report-only baseline adoption (wave 2).
        "pr": 121,
        "name": "slop-lint baseline adoption",
        "keywords": ("slop-baseline.json", "repo root", "report-only baseline"),
    },
    {
        # tools/lessons-check: recurring review findings as deterministic checks (wave 2).
        "pr": 122,
        "name": "lessons-check",
        "keywords": ("lessons-check", "contract-test-ref", "evidence-absolute-path"),
    },
    {
        # slop-lint becomes a blocking ratchet (owner approved): stable job name, CODEOWNERS.
        "pr": 124,
        "name": "slop-lint blocking ratchet",
        "keywords": ("blocking ratchet", "--pass-on-unpruned", "CODEOWNERS"),
    },
    {
        # fork-safe PR summary comment: build workflow + privileged workflow_run commenter (wave 2).
        "pr": 127,
        "name": "fork-safe PR summary comment",
        "keywords": ("pr-summary-comment", "workflow_run", "pr_comment.py"),
    },    {
        # ROADMAP.md rewrite: done / open PR / planned as of 24 Nov, PR numbers re-verified.
        "pr": 129,
        "name": "ROADMAP status refresh",
        "keywords": ("ROADMAP.md", "done / open PR / planned", "24 November 2026"),
    },
    {
        # ci-gate aggregate job for the main ruleset (rizzstack decision 1).
        "pr": 130,
        "name": "ci-gate aggregate check",
        "keywords": ("ci-gate", "check_ci_gate.py", "main ruleset"),
    },
)

#: The in-review wave: no coordinator-dispatched campaign PR is open as of the
# 2026-11-16 post-#48 state (the drain landed #41-#47 and #49-#54; the follow-ups
# #55, #56, #62 and #48 have merged since). The concurrent actor's lanes #57/#58/#59
# are open; the changelog's In-review prose names them, and their changelog coverage
# (registry rows or exclusions) is a duty of the docs-sync that follows their merges -
# the self-coverage pattern this PR established for companion PRs. The changelog must
# represent open work in the ``### In review`` subsection so the umbrella truth table
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


#: The untagged release-candidate section(s) whose entries still count as
#: "Unreleased" for coverage: a dated heading prepared for a tag that does not
#: exist yet (26-coordinated-release.md). Remove the version once it is tagged.
UNTAGGED_CANDIDATE_VERSIONS = ("0.1.0",)


def _unreleased_section() -> str:
    text = _read_changelog()
    match = re.search(r"(?ms)^## Unreleased\s*$\n(.*?)(?=^## |\Z)", text)
    assert match is not None, "CHANGELOG.md must keep a '## Unreleased' section"
    parts = [match.group(1)]
    for version in UNTAGGED_CANDIDATE_VERSIONS:
        candidate = re.search(
            rf"(?ms)^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$\n(.*?)(?=^## |\Z)",
            text,
        )
        if candidate is not None:
            parts.append(candidate.group(1))
    return "\n".join(parts)


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
