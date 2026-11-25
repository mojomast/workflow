"""Deterministic fixtures for the Hindsight controlled trial.

Implements the two scenario fixtures the §3 trial scores arms on
(docs/hindsight-synthesis.md §3.2):

- RESTART_FIXTURE: the synthetic two-task feature played through an injected
  coordinator crash (F5) at a named boundary, the restart/recovery path that
  crash forces, and the restart fixture replay that closes the run (the F1/F2
  measurement surface behind H1 and M3).
- SUPERSESSION_RECALL_FIXTURE: the injected specification failure (F3) whose
  supersession must become a digest-pinned pitfall memory, plus the
  later-task probe dispatched after the first wave closes with no hint in its
  brief that the pitfall exists (the H2/M2 measurement surface).

Both fixtures are plain dicts/lists: JSON-serializable, no randomness, no
clock reads, seeded at the base revision and byte-identical across arms (the
AC-302 fixture rule, docs/m2-canary-runbook.md Step 2 pattern). Injected
failures are declared under "injected_failures" so nobody mistakes them for
real defects (docs/24-autonomy-dogfood.md:44-47).

Expected-answer fields live under "expected" so an arm's captured metrics can
be scored mechanically against what a correct run produces. The relative,
pre-registered thresholds that compare arms (>=50% reduction, 2x cost, ...)
live in scripts/trial/evaluator.py as §3.3 constants and are deliberately not
duplicated here. Metrics are read only from durable artifacts — tick records,
brief payloads (memory_context fields), log.md receipts, the RETURN, the
campaign checkpoint — never from chat transcripts
(docs/hindsight-synthesis.md §3.2, docs/31-campaign-continuity.md:70-75).
"""

BASE_SEEDING_NOTE = "seeded at the base revision; byte-identical bytes across arms"

CAMPAIGN = "rizzstack-memory-canary"
FEATURE = "synthetic two-task feature (T1, T2) with ACDD contracts"

CRASH_DIGEST = "sessions/2026-11-17-canary-crash.md"
SUPERSESSION_DIGEST = "sessions/2026-11-17-canary-supersession.md"

RESTART_FIXTURE = {
    "fixture_id": "restart-crash-recovery",
    "source": (
        "docs/hindsight-synthesis.md §3.2 items 1 and 3 plus the run shape's "
        "restart fixture replay; crash boundary class docs/24-autonomy-dogfood.md:142-156"
    ),
    "identical_across_arms": True,
    "base_seeding_note": BASE_SEEDING_NOTE,
    "failure_classes": ["F1", "F2", "F5"],
    "injected_failures": [
        {
            "id": "coordinator-kill-after-dispatch",
            "kind": "coordinator-kill",
            "boundary": "tick.after_dispatch",
            "declared": True,
            "declaration_note": (
                "declared injected failure so nobody mistakes it for a real defect "
                "(docs/24-autonomy-dogfood.md:44-47)"
            ),
        }
    ],
    "scenario": {
        "campaign": CAMPAIGN,
        "feature": FEATURE,
        "sequence": [
            "dispatch T1; T1 closes",
            "dispatch T2",
            "kill the coordinator at the tick.after_dispatch boundary",
            "restart the coordinator; the recovery path runs and recovery briefs are built",
            "finish the wave from durable records only",
            "replay this fixture once more after the later-task probe (restart fixture replay)",
        ],
        "durable_records_seeded": [
            {
                "record": "tick-record",
                "content": "T1 accepted and closed; T2 dispatched",
            },
            {
                "record": "campaign-checkpoint",
                "content": "last completed action: T1 closed; next action: supervise T2",
            },
            {
                "record": "session-digest",
                "digest_id": CRASH_DIGEST,
                "content": "digest of the session that ended in the injected crash",
            },
        ],
        "forbidden_sources": ["raw chat scrollback"],
    },
    "expected": {
        "recovery_briefs_total": 2,
        "recovery_brief_item": {
            "memory_type": "learning",
            "title": (
                "coordinator restart after a tick.after_dispatch crash recovers "
                "from the campaign checkpoint and session digest, not from chat"
            ),
            "digest_pinned": True,
            "source_kind": "session-digest",
            "source_digest": CRASH_DIGEST,
        },
        "recovery_brief_reject": {
            "memory_type": "learning",
            "note": "same learning unpinned, or pinned to a digest that is not the crash digest",
            "digest_pinned": False,
            "source_kind": "session-digest",
            "source_digest": "sessions/2026-11-17-canary-wrong-digest.md",
        },
        "max_scrollback_sourced_reconstruction_events": 0,
        "m1_metric_fields": [
            "reconstruction_tokens",
            "reconstruction_turns",
            "scrollback_sourced_reconstruction_events",
        ],
        "m3_metric_fields": ["recovery_briefs_total", "recovery_briefs_correct"],
    },
}

SUPERSESSION_RECALL_FIXTURE = {
    "fixture_id": "supersession-recall",
    "source": (
        "docs/hindsight-synthesis.md §3.2 items 1, 2 and 5; injected specification "
        "failure docs/24-autonomy-dogfood.md:32-47; five failure classes "
        "docs/27-recovery-protocol.md:32-60"
    ),
    "identical_across_arms": True,
    "base_seeding_note": BASE_SEEDING_NOTE,
    "failure_classes": ["F3"],
    "injected_failures": [
        {
            "id": "t2-contract-names-nonexistent-test",
            "kind": "specification-failure",
            "task": "T2",
            "bad_test_id": "tests/test_t2_button.py::test_t2_button_responds_to_hover",
            "bad_test_id_note": "names a test id that does not exist at the pinned base revision",
            "expected_classification": "specification",
            "supersede_count": 1,
            "redispatch_contract": "t2-contract-v2",
            "declared": True,
            "declaration_note": (
                "declared injected failure so nobody mistakes it for a real defect "
                "(docs/24-autonomy-dogfood.md:44-47)"
            ),
        }
    ],
    "scenario": {
        "campaign": CAMPAIGN,
        "feature": FEATURE,
        "sequence": [
            "dispatch T2 with contract v1 naming the bad test id",
            "the loop classifies the failure as specification",
            "supersede contract v1 exactly once",
            "re-dispatch T2 with contract v2 naming the corrected test id",
            "T2 closes and the first wave closes",
            "dispatch the later task T3 on the same surface; its brief carries no hint that the pitfall exists",
            "run the probe twice so two later-task briefs are captured (probe_briefs_total = 2)",
        ],
        "corrected_test_id": "tests/test_t2_button.py::test_t2_button_renders_and_clicks",
        "session_digest": SUPERSESSION_DIGEST,
    },
    "expected": {
        "target_pitfall": {
            "memory_type": "pitfall",
            "id": "pitfall-t2-selector-test-id",
            "title": (
                "T2 contract v1 named a nonexistent test id; accept only test ids "
                "that exist at the pinned revision"
            ),
            "digest_pinned": True,
            "source_kind": "session-digest",
            "source_digest": SUPERSESSION_DIGEST,
        },
        "wrong_pitfalls": [
            {
                "memory_type": "pitfall",
                "id": "pitfall-visual-acceptance",
                "title": "a DOM assertion is not visual acceptance",
            },
            {
                "memory_type": "pitfall",
                "id": "pitfall-stale-lease",
                "title": "a crashed workbench leaves a stale lease behind",
            },
        ],
        "probe_briefs_total": 2,
        "probe_briefs_with_target_pitfall_required": 2,
        "max_wrong_pitfall_intrusions_per_brief": 1,
        "probe_brief_must_not_hint_pitfall": True,
        "m2_metric_fields": [
            "probe_briefs_total",
            "probe_briefs_with_pitfall",
            "intrusions_per_brief",
        ],
    },
}

ALL_FIXTURES = [RESTART_FIXTURE, SUPERSESSION_RECALL_FIXTURE]


def fixture_by_id(fixture_id: str) -> dict:
    for fixture in ALL_FIXTURES:
        if fixture["fixture_id"] == fixture_id:
            return fixture
    raise KeyError(fixture_id)
