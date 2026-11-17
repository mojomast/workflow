"""RED-first tests for the Hindsight trial harness (docs/hindsight-synthesis.md §3).

Written before implementation, per the trial harness brief. The assertions pin:

- scripts/trial/fixtures.py — the restart fixture and the supersession-recall
  fixture from §3.2 as plain, deterministic scenario data carrying
  expected-answer fields so arms can be scored against them;
- scripts/trial/evaluator.py — the exact §3.3 thresholds copied into module
  constants named per hypothesis (H1-H4), stated in the returned report, with
  PASS/FAIL/UNINFORMATIVE verdicts: FAIL when a threshold is missed,
  UNINFORMATIVE when arms are indistinguishable on the metric (equal values)
  or a metric is absent, and a conformance gate under which ANY
  contract-conformance violation in an arm fails that arm regardless of
  quality metrics;
- Level A hygiene: neither module ever touches the network (the fixtures are
  committed data and the evaluator is pure arithmetic over per-arm metric
  dicts).
"""

from __future__ import annotations

import importlib.util
import json
import socket
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

PLAIN_TYPES = (dict, list, str, int, float, bool, type(None))


def _load(name: str, filename: str):
    path = ROOT / "scripts" / "trial" / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "module spec must load"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = _load("trial_fixtures", "fixtures.py")
evaluator = _load("trial_evaluator", "evaluator.py")


def _assert_plain_data(testcase: unittest.TestCase, value) -> None:
    testcase.assertIsInstance(value, PLAIN_TYPES)
    if isinstance(value, dict):
        for key, item in value.items():
            testcase.assertIsInstance(key, str)
            _assert_plain_data(testcase, item)
    elif isinstance(value, list):
        for item in value:
            _assert_plain_data(testcase, item)


def _m1(tokens: int, turns: int, scrollback: int = 0) -> dict:
    return {
        "reconstruction_tokens": tokens,
        "reconstruction_turns": turns,
        "scrollback_sourced_reconstruction_events": scrollback,
    }


def _m2(total: int, present: int, intrusions: list) -> dict:
    return {
        "probe_briefs_total": total,
        "probe_briefs_with_pitfall": present,
        "intrusions_per_brief": list(intrusions),
    }


def _violations(n: int) -> dict:
    return {"violations": n}


def _m8(tokens: int) -> dict:
    return {"memory_layer_tokens": tokens}


def _baseline_metrics() -> dict:
    return {
        "M1": _m1(2000, 20),
        "M2": _m2(2, 0, [0, 0]),
        "M5": _violations(0),
        "M6": _violations(0),
        "M7": _violations(0),
        "M8": _m8(1000),
    }


def _treatment_metrics() -> dict:
    return {
        "M1": _m1(800, 8),
        "M2": _m2(2, 2, [0, 0]),
        "M5": _violations(0),
        "M6": _violations(0),
        "M7": _violations(0),
        "M8": _m8(1500),
    }


def _arm(arm_id: str, metrics: dict) -> dict:
    return {"arm_id": arm_id, "metrics": metrics}


def _separated_arms() -> tuple:
    return _arm("baseline", _baseline_metrics()), _arm("treatment", _treatment_metrics())


class FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        if fixtures is None:
            self.fail("scripts/trial/fixtures.py does not exist yet (RED phase)")

    def test_restart_fixture_exists_and_is_plain_deterministic_data(self):
        data = fixtures.RESTART_FIXTURE
        _assert_plain_data(self, data)
        self.assertEqual(json.loads(json.dumps(data)), data)

    def test_restart_fixture_declares_the_injected_crash(self):
        declared = [
            entry
            for entry in fixtures.RESTART_FIXTURE["injected_failures"]
            if entry["kind"] == "coordinator-kill"
        ]
        self.assertEqual(len(declared), 1)
        crash = declared[0]
        self.assertEqual(crash["boundary"], "tick.after_dispatch")
        self.assertIs(crash["declared"], True)

    def test_restart_fixture_carries_expected_answers_for_m1_and_m3(self):
        expected = fixtures.RESTART_FIXTURE["expected"]
        self.assertEqual(expected["recovery_briefs_total"], 2)
        item = expected["recovery_brief_item"]
        self.assertEqual(item["memory_type"], "learning")
        self.assertIs(item["digest_pinned"], True)
        self.assertEqual(item["source_kind"], "session-digest")
        self.assertTrue(item["source_digest"])
        self.assertEqual(expected["max_scrollback_sourced_reconstruction_events"], 0)
        self.assertEqual(
            expected["m1_metric_fields"],
            [
                "reconstruction_tokens",
                "reconstruction_turns",
                "scrollback_sourced_reconstruction_events",
            ],
        )

    def test_supersession_fixture_declares_the_specification_failure(self):
        fixture = fixtures.SUPERSESSION_RECALL_FIXTURE
        declared = [
            entry
            for entry in fixture["injected_failures"]
            if entry["kind"] == "specification-failure"
        ]
        self.assertEqual(len(declared), 1)
        failure = declared[0]
        self.assertEqual(failure["task"], "T2")
        self.assertTrue(failure["bad_test_id"].startswith("tests/"))
        self.assertEqual(failure["expected_classification"], "specification")
        self.assertEqual(failure["supersede_count"], 1)
        self.assertIs(failure["declared"], True)

    def test_supersession_fixture_carries_expected_probe_answers(self):
        expected = fixtures.SUPERSESSION_RECALL_FIXTURE["expected"]
        pitfall = expected["target_pitfall"]
        self.assertEqual(pitfall["memory_type"], "pitfall")
        self.assertIs(pitfall["digest_pinned"], True)
        self.assertEqual(expected["probe_briefs_total"], 2)
        self.assertEqual(expected["probe_briefs_with_target_pitfall_required"], 2)
        self.assertEqual(expected["max_wrong_pitfall_intrusions_per_brief"], 1)
        self.assertIs(expected["probe_brief_must_not_hint_pitfall"], True)
        self.assertTrue(expected["wrong_pitfalls"])
        self.assertEqual(
            expected["m2_metric_fields"],
            ["probe_briefs_total", "probe_briefs_with_pitfall", "intrusions_per_brief"],
        )

    def test_both_fixtures_declare_identical_seeding_across_arms(self):
        for fixture in (fixtures.RESTART_FIXTURE, fixtures.SUPERSESSION_RECALL_FIXTURE):
            self.assertIs(fixture["identical_across_arms"], True)

    def test_fixture_metric_fields_match_evaluator_shapes(self):
        if evaluator is None:
            self.fail("scripts/trial/evaluator.py does not exist yet (RED phase)")
        self.assertEqual(
            set(fixtures.RESTART_FIXTURE["expected"]["m1_metric_fields"]),
            set(evaluator.METRIC_SHAPES["M1"]),
        )
        self.assertEqual(
            set(fixtures.SUPERSESSION_RECALL_FIXTURE["expected"]["m2_metric_fields"]),
            set(evaluator.METRIC_SHAPES["M2"]),
        )


class ThresholdConstantTests(unittest.TestCase):
    def setUp(self) -> None:
        if evaluator is None:
            self.fail("scripts/trial/evaluator.py does not exist yet (RED phase)")

    def test_h1_constants_match_section_3_3(self):
        self.assertEqual(evaluator.H1_MIN_REDUCTION_FRACTION, 0.5)
        self.assertEqual(evaluator.H1_MAX_SCROLLBACK_SOURCED_EVENTS, 0)

    def test_h2_constants_match_section_3_3(self):
        self.assertEqual(evaluator.H2_PROBE_BRIEFS_REQUIRED, 2)
        self.assertEqual(evaluator.H2_MAX_INTRUSIONS_PER_BRIEF, 1)

    def test_h3_constants_match_section_3_3(self):
        self.assertEqual(evaluator.H3_MAX_CONFORMANCE_VIOLATIONS, 0)
        self.assertEqual(tuple(evaluator.CONFORMANCE_GATE_METRICS), ("M5", "M6", "M7"))

    def test_h4_constants_match_section_3_3(self):
        self.assertEqual(evaluator.H4_MAX_COST_RATIO, 2.0)

    def test_report_states_the_preregistered_thresholds(self):
        baseline, treatment = _separated_arms()
        report = evaluator.evaluate_trial(baseline, treatment)
        thresholds = report["thresholds"]
        self.assertEqual(thresholds["H1_MIN_REDUCTION_FRACTION"], 0.5)
        self.assertEqual(thresholds["H1_MAX_SCROLLBACK_SOURCED_EVENTS"], 0)
        self.assertEqual(thresholds["H2_PROBE_BRIEFS_REQUIRED"], 2)
        self.assertEqual(thresholds["H2_MAX_INTRUSIONS_PER_BRIEF"], 1)
        self.assertEqual(thresholds["H3_MAX_CONFORMANCE_VIOLATIONS"], 0)
        self.assertEqual(thresholds["H4_MAX_COST_RATIO"], 2.0)


class VerdictTests(unittest.TestCase):
    def setUp(self) -> None:
        if evaluator is None:
            self.fail("scripts/trial/evaluator.py does not exist yet (RED phase)")

    def test_well_separated_arms_pass_every_hypothesis(self):
        baseline, treatment = _separated_arms()
        report = evaluator.evaluate_trial(baseline, treatment)
        self.assertEqual(
            report["verdicts"], {"H1": "PASS", "H2": "PASS", "H3": "PASS", "H4": "PASS"}
        )

    def test_losing_treatment_fails_h1(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M1"] = _m1(1500, 15)
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["verdicts"]["H1"], "FAIL")

    def test_h1_fails_when_either_arm_cites_raw_chat_scrollback(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M1"] = _m1(200, 2, scrollback=1)
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["verdicts"]["H1"], "FAIL")

        treatment = _arm("treatment", _treatment_metrics())
        baseline_metrics = _baseline_metrics()
        baseline_metrics["M1"] = _m1(2000, 20, scrollback=2)
        report = evaluator.evaluate_trial(_arm("baseline", baseline_metrics), treatment)
        self.assertEqual(report["verdicts"]["H1"], "FAIL")

    def test_losing_treatment_fails_h2_when_pitfall_misses_a_probe_brief(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M2"] = _m2(2, 1, [0, 0])
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["verdicts"]["H2"], "FAIL")

    def test_losing_treatment_fails_h2_on_wrong_pitfall_intrusions(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M2"] = _m2(2, 2, [2, 0])
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["verdicts"]["H2"], "FAIL")

    def test_losing_treatment_fails_h4_on_token_spend(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M8"] = _m8(3000)
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["verdicts"]["H4"], "FAIL")

    def test_h2_treats_the_baseline_probe_as_informational_only(self):
        baseline_metrics = _baseline_metrics()
        del baseline_metrics["M2"]
        baseline = _arm("baseline", baseline_metrics)
        report = evaluator.evaluate_trial(baseline, _arm("treatment", _treatment_metrics()))
        self.assertEqual(report["verdicts"]["H2"], "PASS")

    def test_identical_arms_are_uninformative(self):
        shared = _treatment_metrics()
        report = evaluator.evaluate_trial(_arm("baseline", shared), _arm("treatment", dict(shared)))
        self.assertEqual(report["verdicts"]["H1"], "UNINFORMATIVE")
        self.assertEqual(report["verdicts"]["H2"], "UNINFORMATIVE")
        self.assertEqual(report["verdicts"]["H4"], "UNINFORMATIVE")
        self.assertEqual(report["verdicts"]["H3"], "PASS")

    def test_missing_metric_is_uninformative(self):
        baseline, treatment = _separated_arms()

        treatment_without_m1 = dict(treatment["metrics"])
        del treatment_without_m1["M1"]
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_without_m1))
        self.assertEqual(report["verdicts"]["H1"], "UNINFORMATIVE")

        baseline_without_m1 = dict(baseline["metrics"])
        del baseline_without_m1["M1"]
        report = evaluator.evaluate_trial(_arm("baseline", baseline_without_m1), treatment)
        self.assertEqual(report["verdicts"]["H1"], "UNINFORMATIVE")

        treatment_without_m2 = dict(treatment["metrics"])
        del treatment_without_m2["M2"]
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_without_m2))
        self.assertEqual(report["verdicts"]["H2"], "UNINFORMATIVE")

        treatment_without_m8 = dict(treatment["metrics"])
        del treatment_without_m8["M8"]
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_without_m8))
        self.assertEqual(report["verdicts"]["H4"], "UNINFORMATIVE")

        treatment_without_m5 = dict(treatment["metrics"])
        del treatment_without_m5["M5"]
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_without_m5))
        self.assertEqual(report["verdicts"]["H3"], "UNINFORMATIVE")

    def test_incomplete_metric_record_is_uninformative(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M1"] = {"reconstruction_tokens": 800, "reconstruction_turns": 8}
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["verdicts"]["H1"], "UNINFORMATIVE")

    def test_empty_arm_records_are_uninformative(self):
        report = evaluator.evaluate_trial(_arm("baseline", {}), _arm("treatment", {}))
        for hypothesis in ("H1", "H2", "H3", "H4"):
            self.assertEqual(report["verdicts"][hypothesis], "UNINFORMATIVE")


class ConformanceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        if evaluator is None:
            self.fail("scripts/trial/evaluator.py does not exist yet (RED phase)")

    def test_single_treatment_violation_fails_that_arm_regardless_of_quality(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M1"] = _m1(200, 2)
        treatment_metrics["M5"] = _violations(1)
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["verdicts"]["H1"], "FAIL")
        self.assertEqual(report["verdicts"]["H2"], "FAIL")
        self.assertEqual(report["verdicts"]["H4"], "FAIL")
        self.assertEqual(report["verdicts"]["H3"], "FAIL")

    def test_single_baseline_violation_fails_the_baseline_arm_gate(self):
        baseline_metrics = _baseline_metrics()
        baseline_metrics["M6"] = _violations(1)
        baseline = _arm("baseline", baseline_metrics)
        report = evaluator.evaluate_trial(baseline, _arm("treatment", _treatment_metrics()))
        self.assertEqual(report["verdicts"]["H3"], "FAIL")
        self.assertEqual(report["verdicts"]["H1"], "PASS")

    def test_gate_covers_every_conformance_metric(self):
        for metric in ("M5", "M6", "M7"):
            with self.subTest(metric=metric):
                baseline = _arm("baseline", _baseline_metrics())
                treatment_metrics = _treatment_metrics()
                treatment_metrics[metric] = _violations(1)
                report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
                self.assertEqual(report["verdicts"]["H3"], "FAIL")

    def test_report_names_the_violating_arm_and_metric(self):
        baseline = _arm("baseline", _baseline_metrics())
        treatment_metrics = _treatment_metrics()
        treatment_metrics["M5"] = _violations(1)
        report = evaluator.evaluate_trial(baseline, _arm("treatment", treatment_metrics))
        self.assertEqual(report["conformance"]["treatment"]["violations"], 1)
        self.assertEqual(report["conformance"]["treatment"]["per_metric"]["M5"], 1)
        self.assertIn("treatment", report["hypotheses"]["H3"]["reason"])
        self.assertIn("M5", report["hypotheses"]["H3"]["reason"])


class NoNetworkTests(unittest.TestCase):
    def setUp(self) -> None:
        if fixtures is None:
            self.fail("scripts/trial/fixtures.py does not exist yet (RED phase)")
        if evaluator is None:
            self.fail("scripts/trial/evaluator.py does not exist yet (RED phase)")

    def test_fixtures_and_evaluator_never_touch_the_network(self):
        def refuse(*args, **kwargs):
            raise AssertionError("network access attempted")

        with mock.patch.object(socket, "socket", refuse), mock.patch.object(
            socket, "create_connection", refuse
        ), mock.patch.object(socket, "getaddrinfo", refuse):
            _assert_plain_data(self, fixtures.RESTART_FIXTURE)
            _assert_plain_data(self, fixtures.SUPERSESSION_RECALL_FIXTURE)
            json.dumps({"restart": fixtures.RESTART_FIXTURE, "supersession": fixtures.SUPERSESSION_RECALL_FIXTURE})

            baseline, treatment = _separated_arms()
            report = evaluator.evaluate_trial(baseline, treatment)
            self.assertEqual(report["verdicts"]["H4"], "PASS")

            losing = _treatment_metrics()
            losing["M8"] = _m8(5000)
            report = evaluator.evaluate_trial(baseline, _arm("treatment", losing))
            self.assertEqual(report["verdicts"]["H4"], "FAIL")


if __name__ == "__main__":
    unittest.main()
