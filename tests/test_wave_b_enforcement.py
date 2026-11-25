"""RED for Wave B slice B6: report-first enforcement, tickets still off.

Wave B (``docs/design/wave-b-worker-contract.md``) ships validators in B3 but
does **not** switch enforcement on. B6 is the switch: brief validation defaults
to report, a report-mode drift is recorded and the dispatch proceeds, enforce
mode refuses the same dispatch, and ``ticket_mode`` (the Wave C signed dispatch
ticket) stays off until an owner turns it on explicitly. There is no implicit
path to either switch: no environment variable, no alias key, no config value
that merely resembles the flag.

The contract this module freezes
--------------------------------

``bundlebees_plugin/brief_validation.py`` is the reference policy the dispatch
path vendors. It does not validate documents by itself; B3's validator produces
the problem list and this module decides what dispatch does with it::

    DEFAULT_MODE = "report"
    DEFAULT_TICKET_MODE = False
    load_policy(config: Mapping[str, object] | None = None) -> BriefValidationPolicy
    evaluate(violations, *, brief=None, policy=None, record=None) -> BriefValidationDecision

``BriefValidationPolicy`` carries ``mode`` (exactly ``"report"`` or
``"enforce"``) and ``ticket_mode`` (exactly a bool). ``load_policy`` accepts
only the exact keys ``mode`` and ``ticket_mode``; an unknown key is ignored, a
non-boolean ``ticket_mode`` or an unknown mode raises ``ValueError``, and the
process environment is never consulted.

``evaluate`` returns a decision with ``mode``, ``proceed``, ``refused``,
``ticket_mode`` and ``recorded`` (the violations it acted on, as a tuple).
``record`` is called once with ``{"event": "brief_schema_drift", "mode": ...,
"violations": [...]}`` whenever there is at least one violation, in both modes.
In ``report`` mode ``proceed`` is always true. In ``enforce`` mode any
violation makes ``proceed`` false and ``refused`` true. When ``ticket_mode`` is
on and the brief has no ``ticket``, ``evaluate`` adds the violation
``"brief_ticket_missing"`` before deciding; the mode still governs whether that
is only recorded (report) or refused (enforce).

RED now: the module does not exist.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
POLICY_MODULE = ROOT / "bundlebees_plugin" / "brief_validation.py"

MINIMAL_BRIEF: dict[str, Any] = {
    "schema": "rizzstack.brief/1",
    "objective": "Decide what dispatch does with a schema drift.",
    "project": "workflow",
    "source_rev": "0123456789abcdef0123456789abcdef01234567",
    "assigned_files": ["docs/README.md"],
    "acceptance": {"criteria": ["the brief validates"]},
    "risk": {"tier": "low"},
}

VIOLATIONS = ("$.assigned_files: [] does not meet minItems 1",)


def _load_policy():
    assert POLICY_MODULE.is_file(), (
        f"{POLICY_MODULE.relative_to(ROOT)} is missing; B6 has not landed"
    )
    spec = importlib.util.spec_from_file_location("wave_b_brief_validation", POLICY_MODULE)
    assert spec is not None and spec.loader is not None, f"cannot load {POLICY_MODULE}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Recorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)


# --------------------------------------------------------------------------
# report is the default
# --------------------------------------------------------------------------


def test_brief_validation_defaults_to_report_mode() -> None:
    module = _load_policy()
    assert module.DEFAULT_MODE == "report", f"DEFAULT_MODE is {module.DEFAULT_MODE!r}"
    assert module.load_policy().mode == "report", "load_policy() did not default to report"
    assert module.load_policy({}).mode == "report", "an empty config did not default to report"
    assert module.load_policy(None).mode == "report", "an absent config did not default to report"
    assert module.load_policy({"mode": "report"}).mode == "report"
    assert module.load_policy({"mode": "enforce"}).mode == "enforce", (
        "an explicit enforce mode was not honoured"
    )


def test_an_unknown_mode_is_refused_rather_than_coerced() -> None:
    module = _load_policy()
    for bad in ("Report", "ENFORCE", "strict", "enforced", "", None, True, 1):
        with pytest.raises(ValueError):
            module.load_policy({"mode": bad})


def test_evaluate_uses_the_report_default_when_no_policy_is_given() -> None:
    module = _load_policy()
    decision = module.evaluate(list(VIOLATIONS))
    assert decision.mode == "report"
    assert decision.proceed is True, "a drift refused dispatch without an explicit enforce policy"


# --------------------------------------------------------------------------
# report records and proceeds; enforce refuses
# --------------------------------------------------------------------------


def test_report_mode_records_the_drift_and_dispatch_proceeds() -> None:
    module = _load_policy()
    recorder = Recorder()
    decision = module.evaluate(
        list(VIOLATIONS),
        policy=module.load_policy({"mode": "report"}),
        record=recorder,
    )

    assert decision.proceed is True, "report mode refused the dispatch"
    assert decision.refused is False, "report mode reported a refusal"
    assert tuple(decision.recorded) == VIOLATIONS

    assert len(recorder.events) == 1, f"expected one drift record, got {recorder.events}"
    event = recorder.events[0]
    assert event.get("event") == "brief_schema_drift", f"unexpected event: {event}"
    assert event.get("mode") == "report", f"the event does not name the mode: {event}"
    assert list(event.get("violations", [])) == list(VIOLATIONS), (
        f"the event does not carry the violations: {event}"
    )


def test_enforce_mode_records_the_drift_and_refuses_the_dispatch() -> None:
    module = _load_policy()
    recorder = Recorder()
    decision = module.evaluate(
        list(VIOLATIONS),
        policy=module.load_policy({"mode": "enforce"}),
        record=recorder,
    )

    assert decision.proceed is False, "enforce mode proceeded with a drift"
    assert decision.refused is True, "enforce mode did not record the refusal"
    assert tuple(decision.recorded) == VIOLATIONS
    assert len(recorder.events) == 1 and recorder.events[0].get("event") == "brief_schema_drift", (
        f"enforce mode did not record the drift: {recorder.events}"
    )
    assert recorder.events[0].get("mode") == "enforce"


def test_a_clean_brief_proceeds_in_both_modes_and_records_nothing() -> None:
    module = _load_policy()
    for mode in ("report", "enforce"):
        recorder = Recorder()
        decision = module.evaluate([], policy=module.load_policy({"mode": mode}), record=recorder)
        assert decision.proceed is True, f"{mode} refused a clean brief"
        assert decision.refused is False, f"{mode} reported a refusal for a clean brief"
        assert tuple(decision.recorded) == ()
        assert recorder.events == [], f"{mode} recorded a drift for a clean brief"


# --------------------------------------------------------------------------
# ticket mode stays off unless explicitly turned on
# --------------------------------------------------------------------------


def test_ticket_mode_is_off_by_default() -> None:
    module = _load_policy()
    assert module.DEFAULT_TICKET_MODE is False, (
        f"DEFAULT_TICKET_MODE is {module.DEFAULT_TICKET_MODE!r}"
    )
    for config in (None, {}, {"mode": "enforce"}, {"mode": "report"}):
        policy = module.load_policy(config)
        assert policy.ticket_mode is False, f"ticket_mode turned on by {config!r}"

    decision = module.evaluate([], brief=copy.deepcopy(MINIMAL_BRIEF), policy=module.load_policy())
    assert decision.proceed is True, "a brief without a ticket was refused while ticket_mode is off"
    assert decision.ticket_mode is False
    assert tuple(decision.recorded) == (), "a missing ticket was recorded while ticket_mode is off"


@pytest.mark.parametrize(
    "implicit",
    (
        {"ticket-mode": True},
        {"tickets": True},
        {"require_ticket": True},
        {"ticketMode": True},
        {"ticket": True},
        {"wave_c": True},
        {"wave_c": {"ticket_mode": True}},
        {"mode": "enforce", "ticket": {"required": True}},
    ),
    ids=(
        "hyphenated-key",
        "tickets",
        "require-ticket",
        "camel-case",
        "ticket",
        "wave-c",
        "wave-c-nested",
        "nested-ticket-object",
    ),
)
def test_no_config_alias_turns_ticket_mode_on(implicit: dict[str, Any]) -> None:
    module = _load_policy()
    policy = module.load_policy(implicit)
    assert policy.ticket_mode is False, f"ticket_mode turned on implicitly by {implicit!r}"


def test_garbage_ticket_mode_values_are_refused_rather_than_coerced() -> None:
    module = _load_policy()
    for bad in ("true", "1", 1, 0, None, [], {}):
        with pytest.raises(ValueError):
            module.load_policy({"ticket_mode": bad})


def test_the_environment_cannot_turn_on_enforcement_or_tickets(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_policy()
    for name in (
        "RIZZSTACK_BRIEF_VALIDATION_MODE",
        "BUNDLEBEES_BRIEF_VALIDATION_MODE",
        "RIZZSTACK_BRIEF_TICKET_MODE",
        "BUNDLEBEES_TICKET_MODE",
    ):
        monkeypatch.setenv(name, "enforce" if "MODE" in name and "TICKET" not in name else "1")
    policy = module.load_policy({})
    assert policy.mode == "report", "an environment variable turned enforcement on"
    assert policy.ticket_mode is False, "an environment variable turned ticket_mode on"


def test_ticket_mode_adds_a_violation_and_report_still_proceeds() -> None:
    module = _load_policy()
    policy = module.load_policy({"ticket_mode": True})
    assert policy.ticket_mode is True, "the explicit ticket_mode key did not turn the mode on"
    assert policy.mode == "report", "ticket_mode changed the validation mode"

    recorder = Recorder()
    decision = module.evaluate([], brief=copy.deepcopy(MINIMAL_BRIEF), policy=policy, record=recorder)
    assert decision.proceed is True, "report mode refused a missing ticket instead of recording it"
    assert "brief_ticket_missing" in tuple(decision.recorded), (
        f"the missing ticket was not recorded: {decision.recorded}"
    )
    assert recorder.events and recorder.events[0].get("event") == "brief_schema_drift"


def test_ticket_mode_on_refuses_a_brief_without_a_ticket_under_enforce() -> None:
    module = _load_policy()
    policy = module.load_policy({"mode": "enforce", "ticket_mode": True})

    refused = module.evaluate([], brief=copy.deepcopy(MINIMAL_BRIEF), policy=policy)
    assert refused.proceed is False, "enforce mode proceeded without the required ticket"
    assert "brief_ticket_missing" in tuple(refused.recorded), (
        f"the missing ticket was not recorded: {refused.recorded}"
    )

    ticketed = {**copy.deepcopy(MINIMAL_BRIEF), "ticket": "header.payload.signature"}
    allowed = module.evaluate([], brief=ticketed, policy=policy)
    assert allowed.proceed is True, "ticket_mode on refused a brief that carries a ticket"
    assert tuple(allowed.recorded) == ()
