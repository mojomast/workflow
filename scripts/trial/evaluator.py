"""Evaluator for the Hindsight controlled trial (docs/hindsight-synthesis.md §3.3).

Given one metric record per arm (baseline, treatment), this module applies the
EXACT pre-registered §3.3 thresholds — copied into module constants named per
hypothesis and restated in every returned report — and returns a
PASS/FAIL/UNINFORMATIVE verdict per hypothesis H1-H4.

Arm records are plain dicts: {"arm_id": str, "metrics": {metric_id: {field:
value}}}. The metric shapes the evaluator reads are declared in METRIC_SHAPES;
every number comes from durable artifacts (tick records, memory_context brief
payloads, log.md receipts, the RETURN, the campaign checkpoint — §3.2
measurement discipline), never from chat transcripts. The module performs no
I/O of any kind: no network, no filesystem, no clock.

Metric ids and their §3.3 meaning:

- M1  resume reconstruction cost (H1): reconstruction_tokens,
      reconstruction_turns, scrollback_sourced_reconstruction_events
- M2  supersession/pitfall recall (H2): probe_briefs_total,
      probe_briefs_with_pitfall, intrusions_per_brief
- M5  injection honesty gate (H3): violations
- M6  write-path integrity gate (H3): violations
- M7  provenance gate (H3): violations
- M8  memory-layer token spend (H4): memory_layer_tokens

M3 (crash-digest injection, 2 of 2) and M4 (visual-pitfall injection, 1 of 1)
are absolute per-arm §3.4 decision inputs scored against the fixture
expected-answer fields; they are not part of any H1-H4 comparison and are
deliberately left to the report layer.

Verdict precedence, applied uniformly and stated in every report:

1. Gate. A conformance violation observed in an arm (M5+M6+M7 violations > 0,
   H3_MAX_CONFORMANCE_VIOLATIONS = 0) fails that arm regardless of quality
   metrics: any treatment violation FAILs H1, H2 and H4 as well as H3; a
   baseline violation FAILs H3 (the §3.4 adopt-nothing consequence is the
   report layer's to draw from H3).
2. Absent or incomplete required metric → UNINFORMATIVE. A metric dict is
   complete only when every field in METRIC_SHAPES is present with a numeric
   value (intrusions_per_brief: a list of numbers, one entry per probe brief).
   Absence is never invented into a violation (§3.5: never invented metrics).
3. Indistinguishable arms → UNINFORMATIVE. For the comparative hypotheses
   (H1, H2, H4), when both arms' deciding values are present and equal, the
   trial cannot distinguish the arms on that metric. H2's baseline probe is
   informational (§3.1), so equality is checked only when both arms report M2.
4. Threshold missed → FAIL. H1 additionally enforces the M1 fail column
   ("any reconstruction event sourced from scrollback", either arm) ahead of
   the equality check, because it is an absolute condition.
5. Otherwise → PASS. H3 is a gate, not a comparison: two clean arms PASS.
"""

THRESHOLDS_SOURCE = "docs/hindsight-synthesis.md §3.3 (pre-registered before any run)"

H1_MIN_REDUCTION_FRACTION = 0.5
H1_MAX_SCROLLBACK_SOURCED_EVENTS = 0

H2_PROBE_BRIEFS_REQUIRED = 2
H2_MAX_INTRUSIONS_PER_BRIEF = 1

H3_MAX_CONFORMANCE_VIOLATIONS = 0

H4_MAX_COST_RATIO = 2.0

CONFORMANCE_GATE_METRICS = ["M5", "M6", "M7"]

METRIC_SHAPES = {
    "M1": [
        "reconstruction_tokens",
        "reconstruction_turns",
        "scrollback_sourced_reconstruction_events",
    ],
    "M2": ["probe_briefs_total", "probe_briefs_with_pitfall", "intrusions_per_brief"],
    "M5": ["violations"],
    "M6": ["violations"],
    "M7": ["violations"],
    "M8": ["memory_layer_tokens"],
}

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_UNINFORMATIVE = "UNINFORMATIVE"


def _metrics_of(arm: dict) -> dict:
    metrics = arm.get("metrics") if isinstance(arm, dict) else None
    return metrics if isinstance(metrics, dict) else {}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _complete_metric(metrics: dict, metric_id: str):
    """Return the metric dict when complete per METRIC_SHAPES, else None."""
    metric = metrics.get(metric_id)
    if not isinstance(metric, dict):
        return None
    for field in METRIC_SHAPES[metric_id]:
        value = metric.get(field)
        if field == "intrusions_per_brief":
            if not (isinstance(value, list) and value and all(_is_number(v) for v in value)):
                return None
        elif not _is_number(value):
            return None
    return metric


def _conformance(metrics: dict) -> dict:
    per_metric = {}
    missing = []
    for metric_id in CONFORMANCE_GATE_METRICS:
        metric = metrics.get(metric_id)
        if isinstance(metric, dict) and _is_number(metric.get("violations")):
            per_metric[metric_id] = metric["violations"]
        else:
            missing.append(metric_id)
    violations = sum(count for count in per_metric.values())
    return {"violations": violations, "per_metric": per_metric, "missing_metrics": missing}


def _verdict(verdict: str, reason: str, details: dict) -> dict:
    return {"verdict": verdict, "reason": reason, "details": details}


def _evaluate_h1(baseline: dict, treatment: dict, treatment_gate: bool) -> dict:
    baseline_m1 = _complete_metric(_metrics_of(baseline), "M1")
    treatment_m1 = _complete_metric(_metrics_of(treatment), "M1")
    details = {}
    if treatment_gate:
        return _verdict(
            VERDICT_FAIL,
            "conformance gate: arm 'treatment' has contract-conformance violations; "
            "the arm fails regardless of quality metrics (§3.3 M5-M7)",
            details,
        )
    if baseline_m1 is None or treatment_m1 is None:
        missing = "baseline" if baseline_m1 is None else "treatment"
        return _verdict(
            VERDICT_UNINFORMATIVE,
            f"metric M1 absent or incomplete for arm '{missing}'",
            details,
        )
    baseline_scrollback = int(baseline_m1["scrollback_sourced_reconstruction_events"])
    treatment_scrollback = int(treatment_m1["scrollback_sourced_reconstruction_events"])
    baseline_cost = baseline_m1["reconstruction_tokens"] + baseline_m1["reconstruction_turns"]
    treatment_cost = treatment_m1["reconstruction_tokens"] + treatment_m1["reconstruction_turns"]
    details = {
        "baseline_cost": baseline_cost,
        "treatment_cost": treatment_cost,
        "scrollback_sourced_reconstruction_events": {
            "baseline": baseline_scrollback,
            "treatment": treatment_scrollback,
        },
    }
    if baseline_scrollback > H1_MAX_SCROLLBACK_SOURCED_EVENTS or treatment_scrollback > H1_MAX_SCROLLBACK_SOURCED_EVENTS:
        return _verdict(
            VERDICT_FAIL,
            "reconstruction events sourced from raw chat scrollback "
            f"(baseline={baseline_scrollback}, treatment={treatment_scrollback}, "
            f"H1_MAX_SCROLLBACK_SOURCED_EVENTS={H1_MAX_SCROLLBACK_SOURCED_EVENTS}); "
            "violates the C1/C3 rule (docs/memory-contract.md:63,115-117)",
            details,
        )
    if baseline_cost == treatment_cost:
        return _verdict(
            VERDICT_UNINFORMATIVE,
            f"arms indistinguishable on M1: equal reconstruction cost {baseline_cost} "
            "(tokens + turns)",
            details,
        )
    reduction = (baseline_cost - treatment_cost) / baseline_cost
    details["reduction"] = reduction
    if reduction < H1_MIN_REDUCTION_FRACTION:
        return _verdict(
            VERDICT_FAIL,
            f"treatment reconstruction-cost reduction {reduction} < "
            f"{H1_MIN_REDUCTION_FRACTION} (H1_MIN_REDUCTION_FRACTION)",
            details,
        )
    return _verdict(
        VERDICT_PASS,
        f"treatment reconstruction cost {treatment_cost} is {reduction} lower than "
        f"baseline {baseline_cost}, at or beyond the {H1_MIN_REDUCTION_FRACTION} threshold, "
        "with zero scrollback-sourced reconstruction events in either arm",
        details,
    )


def _evaluate_h2(baseline: dict, treatment: dict, treatment_gate: bool) -> dict:
    treatment_m2 = _complete_metric(_metrics_of(treatment), "M2")
    baseline_m2 = _complete_metric(_metrics_of(baseline), "M2")
    details = {}
    if treatment_gate:
        return _verdict(
            VERDICT_FAIL,
            "conformance gate: arm 'treatment' has contract-conformance violations; "
            "the arm fails regardless of quality metrics (§3.3 M5-M7)",
            details,
        )
    if treatment_m2 is None:
        return _verdict(
            VERDICT_UNINFORMATIVE,
            "metric M2 absent or incomplete for arm 'treatment'",
            details,
        )
    total = int(treatment_m2["probe_briefs_total"])
    present = int(treatment_m2["probe_briefs_with_pitfall"])
    intrusions = [int(count) for count in treatment_m2["intrusions_per_brief"]]
    if len(intrusions) != total:
        return _verdict(
            VERDICT_UNINFORMATIVE,
            f"metric M2 incomplete for arm 'treatment': {len(intrusions)} intrusion "
            f"entries for {total} probe briefs",
            details,
        )
    max_intrusions = max(intrusions)
    details = {
        "probe_briefs_total": total,
        "probe_briefs_with_pitfall": present,
        "max_intrusions_per_brief": max_intrusions,
    }
    if baseline_m2 is not None:
        baseline_total = int(baseline_m2["probe_briefs_total"])
        baseline_present = int(baseline_m2["probe_briefs_with_pitfall"])
        baseline_max = max(int(count) for count in baseline_m2["intrusions_per_brief"])
        if (baseline_total, baseline_present, baseline_max) == (total, present, max_intrusions):
            return _verdict(
                VERDICT_UNINFORMATIVE,
                "arms indistinguishable on M2: identical probe-brief recall "
                f"(pitfall in {present} of {total} briefs, max {max_intrusions} "
                "wrong-pitfall intrusion(s) per brief)",
                details,
            )
    if total < H2_PROBE_BRIEFS_REQUIRED or present < H2_PROBE_BRIEFS_REQUIRED:
        return _verdict(
            VERDICT_FAIL,
            f"target pitfall present in {present} of {total} probe briefs; required in "
            f"{H2_PROBE_BRIEFS_REQUIRED} of {H2_PROBE_BRIEFS_REQUIRED} "
            "(H2_PROBE_BRIEFS_REQUIRED)",
            details,
        )
    if max_intrusions > H2_MAX_INTRUSIONS_PER_BRIEF:
        return _verdict(
            VERDICT_FAIL,
            f"wrong-pitfall intrusions reach {max_intrusions} in a probe brief; max "
            f"allowed {H2_MAX_INTRUSIONS_PER_BRIEF} per brief "
            "(H2_MAX_INTRUSIONS_PER_BRIEF)",
            details,
        )
    return _verdict(
        VERDICT_PASS,
        f"target pitfall present in {present} of {total} probe briefs with max "
        f"{max_intrusions} wrong-pitfall intrusion(s) per brief "
        f"(required: {H2_PROBE_BRIEFS_REQUIRED} of {H2_PROBE_BRIEFS_REQUIRED}, at most "
        f"{H2_MAX_INTRUSIONS_PER_BRIEF} per brief); baseline probe is informational only",
        details,
    )


def _evaluate_h3(baseline: dict, treatment: dict) -> dict:
    baseline_conf = _conformance(_metrics_of(baseline))
    treatment_conf = _conformance(_metrics_of(treatment))
    details = {"baseline": baseline_conf, "treatment": treatment_conf}
    if baseline_conf["violations"] > H3_MAX_CONFORMANCE_VIOLATIONS:
        violating = [f"{mid}={count}" for mid, count in sorted(baseline_conf["per_metric"].items()) if count > 0]
        return _verdict(
            VERDICT_FAIL,
            f"conformance gate: arm 'baseline' has "
            f"{baseline_conf['violations']} contract-conformance violation(s) "
            f"({', '.join(violating)}); 100% conformance required, any single "
            "violation fails the arm regardless of quality metrics (§3.3 M5-M7)",
            details,
        )
    if treatment_conf["violations"] > H3_MAX_CONFORMANCE_VIOLATIONS:
        violating = [f"{mid}={count}" for mid, count in sorted(treatment_conf["per_metric"].items()) if count > 0]
        return _verdict(
            VERDICT_FAIL,
            f"conformance gate: arm 'treatment' has "
            f"{treatment_conf['violations']} contract-conformance violation(s) "
            f"({', '.join(violating)}); 100% conformance required, any single "
            "violation fails the arm regardless of quality metrics (§3.3 M5-M7)",
            details,
        )
    unproven = baseline_conf["missing_metrics"] + treatment_conf["missing_metrics"]
    if unproven:
        return _verdict(
            VERDICT_UNINFORMATIVE,
            "conformance gate metrics absent or incomplete: "
            f"{', '.join(sorted(unproven))}; 100% conformance cannot be confirmed",
            details,
        )
    return _verdict(
        VERDICT_PASS,
        "both arms conform on every gate metric (M5, M6, M7) with zero violations; "
        "100% conformance confirmed",
        details,
    )


def _evaluate_h4(baseline: dict, treatment: dict, treatment_gate: bool) -> dict:
    baseline_m8 = _complete_metric(_metrics_of(baseline), "M8")
    treatment_m8 = _complete_metric(_metrics_of(treatment), "M8")
    details = {}
    if treatment_gate:
        return _verdict(
            VERDICT_FAIL,
            "conformance gate: arm 'treatment' has contract-conformance violations; "
            "the arm fails regardless of quality metrics (§3.3 M5-M7)",
            details,
        )
    if baseline_m8 is None or treatment_m8 is None:
        missing = "baseline" if baseline_m8 is None else "treatment"
        return _verdict(
            VERDICT_UNINFORMATIVE,
            f"metric M8 absent or incomplete for arm '{missing}'",
            details,
        )
    baseline_tokens = baseline_m8["memory_layer_tokens"]
    treatment_tokens = treatment_m8["memory_layer_tokens"]
    details = {"baseline_tokens": baseline_tokens, "treatment_tokens": treatment_tokens}
    if baseline_tokens == treatment_tokens:
        return _verdict(
            VERDICT_UNINFORMATIVE,
            f"arms indistinguishable on M8: equal memory-layer token spend "
            f"{baseline_tokens} per canary run",
            details,
        )
    ratio = treatment_tokens / baseline_tokens
    details["ratio"] = ratio
    if ratio > H4_MAX_COST_RATIO:
        return _verdict(
            VERDICT_FAIL,
            f"treatment token spend {treatment_tokens} is {ratio}x baseline "
            f"{baseline_tokens}; exceeds the {H4_MAX_COST_RATIO}x cost gate "
            f"(H4_MAX_COST_RATIO) and fails the treatment on cost even if H1/H2 pass",
            details,
        )
    return _verdict(
        VERDICT_PASS,
        f"treatment token spend {treatment_tokens} is {ratio}x baseline "
        f"{baseline_tokens}, within the {H4_MAX_COST_RATIO}x cost gate "
        "(H4_MAX_COST_RATIO)",
        details,
    )


def evaluate_trial(baseline: dict, treatment: dict) -> dict:
    """Apply the pre-registered §3.3 thresholds to one baseline and one treatment arm."""
    baseline_conf = _conformance(_metrics_of(baseline))
    treatment_conf = _conformance(_metrics_of(treatment))
    treatment_gate = treatment_conf["violations"] > H3_MAX_CONFORMANCE_VIOLATIONS

    hypotheses = {
        "H1": _evaluate_h1(baseline, treatment, treatment_gate),
        "H2": _evaluate_h2(baseline, treatment, treatment_gate),
        "H3": _evaluate_h3(baseline, treatment),
        "H4": _evaluate_h4(baseline, treatment, treatment_gate),
    }
    return {
        "schema": "hindsight-trial-evaluator/1",
        "thresholds": {
            "source": THRESHOLDS_SOURCE,
            "H1_MIN_REDUCTION_FRACTION": H1_MIN_REDUCTION_FRACTION,
            "H1_MAX_SCROLLBACK_SOURCED_EVENTS": H1_MAX_SCROLLBACK_SOURCED_EVENTS,
            "H2_PROBE_BRIEFS_REQUIRED": H2_PROBE_BRIEFS_REQUIRED,
            "H2_MAX_INTRUSIONS_PER_BRIEF": H2_MAX_INTRUSIONS_PER_BRIEF,
            "H3_MAX_CONFORMANCE_VIOLATIONS": H3_MAX_CONFORMANCE_VIOLATIONS,
            "H4_MAX_COST_RATIO": H4_MAX_COST_RATIO,
        },
        "verdict_precedence": [
            "1. conformance gate: any observed M5/M6/M7 violation fails the arm regardless of quality metrics",
            "2. required metric absent or incomplete: UNINFORMATIVE",
            "3. comparative hypotheses with equal deciding values: UNINFORMATIVE (arms indistinguishable)",
            "4. threshold missed: FAIL",
            "5. otherwise: PASS",
        ],
        "conformance": {
            "gate_metrics": list(CONFORMANCE_GATE_METRICS),
            "baseline": baseline_conf,
            "treatment": treatment_conf,
        },
        "hypotheses": hypotheses,
        "verdicts": {name: entry["verdict"] for name, entry in hypotheses.items()},
    }
