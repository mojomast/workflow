"""Render the Hindsight trial harness report (docs/hindsight-synthesis.md §3).

The report layer is what a human reads after ``python -m scripts.trial.report``.
It replays the three stub arms, applies the pre-registered §3.3 thresholds via
``scripts/trial/evaluator.py``, scores the absolute §3.4 checks (M3 crash-digest
injection, M4 visual-pitfall injection) from captured brief entries,
and prints:

- the thresholds actually applied, with their source;
- the per-arm metric table (M1 cost, probe intrusions, memory-layer spend,
  conformance violations);
- one verdict line per hypothesis with its reason;
- the H4 pairing note (memory spend compares the two MEMORY arms, b vs c - the
  no-memory arm has nothing to spend, so comparing it would be meaningless).

Hypothesis pairing (pre-registered, docs/hindsight-synthesis.md:441-443):

- the trial is between arm-b (contract-only, the baseline fixed by the brief
  at :413 and named at :277) and arm-c (hybrid, treatment), with arm-a
  (no memory) as the secondary control - not part of any H1-H4 comparison;
- every hypothesis is therefore evaluated on that one pre-registered pair:
  H1 (reconstruction cost), H2 (pitfall recall) and H3 (conformance gate)
  compare arm-b vs arm-c, and H4 (memory-layer token spend) compares the
  same two arms - the only pair where both arms have a memory layer whose
  spend can be compared.

One evaluator call over the pre-registered pair keeps every gate verdict in
the report: the call's H3 covers BOTH trial arms, so an M5-M7 violation in
arm-b or arm-c fails the report (§3.4: adopt nothing if either arm fails a
gate) instead of being silently discarded alongside an unused H4 verdict.

Exit codes (documented contract, asserted in tests):

- 0  every hypothesis PASS
- 1  any hypothesis FAIL (a real gate/missed-threshold failure)
- 2  no FAIL but at least one UNINFORMATIVE (the trial cannot conclude)

Stdlib only; no network, no clock, no filesystem writes.
"""

from __future__ import annotations

import sys

from scripts.trial import arms, evaluator, fixtures

EXIT_ALL_PASS = 0
EXIT_ANY_FAIL = 1
EXIT_INCONCLUSIVE = 2

H123_BASELINE = arms.ARM_B
H123_TREATMENT = arms.ARM_C
H4_BASELINE = arms.ARM_B
H4_TREATMENT = arms.ARM_C


def _captured_items(briefs):
    """One item list per brief. An empty context was observed; a missing one wasn't."""
    if not isinstance(briefs, list):
        return None
    captures = []
    for brief in briefs:
        context = brief.get("memory_context") if isinstance(brief, dict) else None
        items = context.get("items") if isinstance(context, dict) else None
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            return None
        captures.append(items)
    return captures


def _pinned_match(item, expected):
    return item.get("digest_pinned") is True and all(item.get(k) == v for k, v in expected.items())


def _score_absolute_checks(record) -> dict:
    """Score captured briefs only; absent instrumentation is unknown (None).

    M4 needs a visual-task capture and its independently recorded source
    digest. The two current fixtures supply neither; the F3 selector probe
    and its supersession digest are not evidence for M4.
    """
    observations = record.get("observations") if isinstance(record, dict) else None
    if not isinstance(observations, dict):
        observations = {}
    expected = fixtures.RESTART_FIXTURE["expected"]
    recovery = _captured_items(observations.get("recovery_briefs"))
    total = correct = crash_pinned = None
    if recovery is not None:
        total = len(recovery)
        correct = sum(len(items) == 1 and _pinned_match(items[0], expected["recovery_brief_item"])
                      for items in recovery)
        crash_pinned = correct == total == expected["recovery_briefs_total"]

    visual = _captured_items(observations.get("visual_briefs"))
    visual_digest = observations.get("visual_source_digest")
    visual_pinned = None
    if visual is not None and isinstance(visual_digest, str) and visual_digest.strip():
        pitfall = {"id": "pitfall-visual-acceptance", "memory_type": "pitfall",
                   "source_kind": "session-digest", "source_digest": visual_digest}
        visual_pinned = len(visual) == 1 and any(_pinned_match(item, pitfall) for item in visual[0])
    return {
        "M3_recovery_briefs_total": total,
        "M3_recovery_briefs_correct": correct,
        "M3_crash_digest_pinned": crash_pinned,
        "M4_expected_digest": visual_digest,
        "M4_pitfall_digest_pinned": visual_pinned,
    }


def build_report(metrics: dict | None = None) -> dict:
    """Build the report dict from the arm metrics (default: replay all arms)."""
    metrics = metrics if metrics is not None else arms.replay_all()
    baseline = metrics.get(H123_BASELINE, {})
    treatment = metrics.get(H123_TREATMENT, {})

    trial = evaluator.evaluate_trial(baseline, treatment)

    hypotheses = {
        "H1": trial["hypotheses"]["H1"],
        "H2": trial["hypotheses"]["H2"],
        "H3": trial["hypotheses"]["H3"],
        "H4": trial["hypotheses"]["H4"],
    }
    verdicts = {name: entry["verdict"] for name, entry in hypotheses.items()}

    if any(v == evaluator.VERDICT_FAIL for v in verdicts.values()):
        exit_code = EXIT_ANY_FAIL
    elif any(v == evaluator.VERDICT_UNINFORMATIVE for v in verdicts.values()):
        exit_code = EXIT_INCONCLUSIVE
    else:
        exit_code = EXIT_ALL_PASS

    return {
        "schema": "hindsight-trial-report/1",
        "fixtures": [
            fixtures.RESTART_FIXTURE["fixture_id"],
            fixtures.SUPERSESSION_RECALL_FIXTURE["fixture_id"],
        ],
        "pairing": {
            "H1_H2_H3": [H123_BASELINE, H123_TREATMENT],
            "H4": [H4_BASELINE, H4_TREATMENT],
            "note": (
                "Pre-registered pairing (docs/hindsight-synthesis.md:441-443): "
                "arm-b (baseline) vs arm-c (treatment) for every hypothesis; "
                "arm-a is the secondary control and is not part of any H1-H4 "
                "comparison. H4 is stated on the same pair - the two memory "
                "arms are the only ones whose memory-layer spend can be "
                "compared. The single evaluator call keeps its H3 gate "
                "verdict, which covers both trial arms, in the report."
            ),
        },
        "thresholds": trial["thresholds"],
        "verdict_precedence": trial["verdict_precedence"],
        "conformance": trial["conformance"],
        "arm_metrics": metrics,
        "absolute_checks": {arm_id: _score_absolute_checks(metrics.get(arm_id)) for arm_id in arms.ARMS},
        "hypotheses": hypotheses,
        "verdicts": verdicts,
        "exit_code": exit_code,
    }


def render(report: dict, stream=None) -> None:
    """Print the human-readable report (deterministic ordering, no clock)."""
    stream = stream or sys.stdout
    thresholds = report["thresholds"]
    print(f"Hindsight trial harness report ({report['schema']})", file=stream)
    print(f"fixtures: {', '.join(report['fixtures'])}", file=stream)
    print("", file=stream)
    print("thresholds (source: %s)" % thresholds["source"], file=stream)
    for name in (
        "H1_MIN_REDUCTION_FRACTION",
        "H1_MAX_SCROLLBACK_SOURCED_EVENTS",
        "H2_PROBE_BRIEFS_REQUIRED",
        "H2_MAX_INTRUSIONS_PER_BRIEF",
        "H3_MAX_CONFORMANCE_VIOLATIONS",
        "H4_MAX_COST_RATIO",
    ):
        print(f"  {name} = {thresholds[name]}", file=stream)
    print("", file=stream)
    print(f"{'arm':6} {'M1 tokens':>10} {'M1 turns':>9} {'intrusions':>11} {'M8 tokens':>10} {'violations':>10}"
          f" {'M3 (need 2/2)':>14} {'M4 visual':>10}", file=stream)
    for arm_id in arms.ARMS:
        record = report["arm_metrics"].get(arm_id, {})
        m1 = evaluator.complete_metric(record, "M1") or {}
        m2 = evaluator.complete_metric(record, "M2")
        m8 = evaluator.complete_metric(record, "M8") or {}
        gates = [evaluator.complete_metric(record, m) for m in evaluator.CONFORMANCE_GATE_METRICS]
        violations = sum(g["violations"] for g in gates) if all(gates) else "unknown"
        intrusions = sum(m2["intrusions_per_brief"]) if m2 else "unknown"
        checks = report["absolute_checks"][arm_id]
        recovery = (f"{checks['M3_recovery_briefs_correct']}/{checks['M3_recovery_briefs_total']}"
                    if checks['M3_crash_digest_pinned'] is not None else "unknown")
        visual = {True: "PASS", False: "FAIL", None: "unknown"}[checks["M4_pitfall_digest_pinned"]]
        print(
            f"{arm_id:6} {m1.get('reconstruction_tokens', 'unknown'):>10} {m1.get('reconstruction_turns', 'unknown'):>9}"
            f" {intrusions:>11} {m8.get('memory_layer_tokens', 'unknown'):>10} {violations:>10}"
            f" {recovery:>14} {visual:>10}",
            file=stream,
        )
    print("", file=stream)
    print(f"pairing: H1/H2/H3 = {report['pairing']['H1_H2_H3']}, H4 = {report['pairing']['H4']}", file=stream)
    print("", file=stream)
    for name in ("H1", "H2", "H3", "H4"):
        entry = report["hypotheses"][name]
        print(f"{name}: {entry['verdict']} - {entry['reason']}", file=stream)
    print("", file=stream)
    print(f"exit_code: {report['exit_code']}", file=stream)


def main(argv=None) -> int:
    """CLI entrypoint: build, render, return the documented exit code."""
    report = build_report()
    render(report)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
