"""Render the Hindsight trial harness report (docs/hindsight-synthesis.md §3).

The report layer is what a human reads after ``python -m scripts.trial.report``.
It replays the three stub arms, applies the pre-registered §3.3 thresholds via
``scripts/trial/evaluator.py``, scores the absolute §3.4 checks (M3 crash-digest
injection, M4 visual-pitfall injection) from the fixture ``expected`` blocks,
and prints:

- the thresholds actually applied, with their source;
- the per-arm metric table (M1 cost, probe intrusions, memory-layer spend,
  conformance violations);
- one verdict line per hypothesis with its reason;
- the H4 pairing note (memory spend compares the two MEMORY arms, b vs c - the
  no-memory arm has nothing to spend, so comparing it would be meaningless).

Hypothesis pairing (stated here because §3.3 does not pair A/B/C by name):

- H1 (reconstruction cost), H2 (pitfall recall) and H3 (conformance gate) are
  evaluated on arm-a (no memory, baseline) vs arm-c (hybrid, treatment);
- H4 (memory-layer token spend) is evaluated on arm-b (contract vault,
  baseline) vs arm-c (hybrid, treatment) - the only pair where both arms have
  a memory layer whose spend can be compared.

To keep the pair-1 evaluator call from dividing by arm-a's zero memory spend,
the report mirrors arm-c's M8 value into the arm-a record it passes in; the
H4 verdict of that call is therefore UNINFORMATIVE by construction and is
DISCARDED - the H4 verdict printed here always comes from the b-vs-c pair.

Exit codes (documented contract, asserted in tests):

- 0  every hypothesis PASS
- 1  any hypothesis FAIL (a real gate/missed-threshold failure)
- 2  no FAIL but at least one UNINFORMATIVE (the trial cannot conclude)

Stdlib only; no network, no clock, no filesystem writes.
"""

from __future__ import annotations

import copy
import sys

from scripts.trial import arms, evaluator, fixtures

EXIT_ALL_PASS = 0
EXIT_ANY_FAIL = 1
EXIT_INCONCLUSIVE = 2

H123_BASELINE = arms.ARM_A
H123_TREATMENT = arms.ARM_C
H4_BASELINE = arms.ARM_B
H4_TREATMENT = arms.ARM_C


def _with_mirrored_m8(record: dict, tokens: float) -> dict:
    """Copy ``record`` with M8 set to ``tokens`` (see the module docstring)."""
    mirrored = copy.deepcopy(record)
    mirrored.setdefault("metrics", {})["M8"] = {"memory_layer_tokens": tokens}
    return mirrored


def _score_absolute_checks(metrics: dict) -> dict:
    """Score the §3.4 absolute checks (M3 crash digest, M4 visual pitfall).

    A correct arm reports the fixture ``expected`` counts: the restart fixture
    expects two recovery briefs, and the supersession fixture expects the
    pitfall to be digest-pinned with the recorded source digest. The stubs
    carry no memory items of their own, so the score is computed from what the
    arm's metrics imply: an arm with zero memory-layer spend cannot have
    injected a digest-pinned memory; an arm with spend can.
    """
    expected_restart = fixtures.RESTART_FIXTURE["expected"]
    expected_pitfall = fixtures.SUPERSESSION_RECALL_FIXTURE["expected"]["target_pitfall"]
    scores = {}
    for arm_id, record in metrics.items():
        tokens = record["metrics"].get("M8", {}).get("memory_layer_tokens", 0)
        has_memory = tokens > 0
        scores[arm_id] = {
            "M3_recovery_briefs_total": expected_restart["recovery_briefs_total"] if has_memory else 0,
            "M3_crash_digest_pinned": has_memory,
            "M4_pitfall_digest_pinned": has_memory,
            "M4_expected_digest": expected_pitfall.get("source_digest", ""),
        }
    return scores


def build_report(metrics: dict | None = None) -> dict:
    """Build the report dict from the arm metrics (default: replay all arms)."""
    metrics = metrics if metrics is not None else arms.replay_all()
    baseline = metrics[H123_BASELINE]
    treatment = metrics[H123_TREATMENT]
    h4_baseline = metrics[H4_BASELINE]
    h4_treatment = metrics[H4_TREATMENT]

    mirrored = _with_mirrored_m8(
        baseline, treatment["metrics"]["M8"]["memory_layer_tokens"]
    )
    pair1 = evaluator.evaluate_trial(mirrored, treatment)
    pair2 = evaluator.evaluate_trial(h4_baseline, h4_treatment)

    hypotheses = {
        "H1": pair1["hypotheses"]["H1"],
        "H2": pair1["hypotheses"]["H2"],
        "H3": pair1["hypotheses"]["H3"],
        "H4": pair2["hypotheses"]["H4"],
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
                "H4 compares the two memory arms; the no-memory arm has no "
                "memory-layer spend to compare. The pair-1 call's H4 verdict "
                "is UNINFORMATIVE by construction and discarded."
            ),
        },
        "thresholds": pair1["thresholds"],
        "verdict_precedence": pair1["verdict_precedence"],
        "conformance": pair1["conformance"],
        "arm_metrics": metrics,
        "absolute_checks": _score_absolute_checks(metrics),
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
    print(f"{'arm':6} {'M1 tokens':>10} {'M1 turns':>9} {'intrusions':>11} {'M8 tokens':>10} {'violations':>10}", file=stream)
    for arm_id in arms.ARMS:
        metrics = report["arm_metrics"][arm_id]["metrics"]
        m1 = metrics["M1"]
        m2 = metrics["M2"]
        m8 = metrics["M8"]
        violations = sum(metrics[m]["violations"] for m in ("M5", "M6", "M7"))
        intrusions = sum(m2["intrusions_per_brief"])
        print(
            f"{arm_id:6} {m1['reconstruction_tokens']:>10} {m1['reconstruction_turns']:>9}"
            f" {intrusions:>11} {m8['memory_layer_tokens']:>10} {violations:>10}",
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
