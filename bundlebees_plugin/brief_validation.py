"""Brief-schema drift policy for dispatch."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

DEFAULT_MODE: Final = "report"
DEFAULT_TICKET_MODE: Final = False

_VALID_MODES: Final = ("report", "enforce")
_TICKET_MISSING_VIOLATION: Final = "brief_ticket_missing"


@dataclass(frozen=True, slots=True)
class BriefValidationPolicy:
    mode: str = DEFAULT_MODE
    ticket_mode: bool = DEFAULT_TICKET_MODE

    def __post_init__(self) -> None:
        if not isinstance(self.mode, str) or self.mode not in _VALID_MODES:
            raise ValueError("mode must be exactly 'report' or 'enforce'")
        if not isinstance(self.ticket_mode, bool):
            raise ValueError("ticket_mode must be a bool")


@dataclass(frozen=True, slots=True)
class BriefValidationDecision:
    mode: str
    proceed: bool
    refused: bool
    ticket_mode: bool
    recorded: tuple[str, ...]


def load_policy(config: Mapping[str, object] | None = None) -> BriefValidationPolicy:
    if config is None:
        config = {}
    if not isinstance(config, Mapping):
        raise ValueError("config must be a mapping or None")

    mode = config.get("mode", DEFAULT_MODE)
    if not isinstance(mode, str) or mode not in _VALID_MODES:
        raise ValueError("mode must be exactly 'report' or 'enforce'")

    ticket_mode = config.get("ticket_mode", DEFAULT_TICKET_MODE)
    if not isinstance(ticket_mode, bool):
        raise ValueError("ticket_mode must be a bool")

    return BriefValidationPolicy(mode=mode, ticket_mode=ticket_mode)


def evaluate(
    violations: Iterable[str],
    *,
    brief: Mapping[str, Any] | None = None,
    policy: BriefValidationPolicy | None = None,
    record: Callable[[dict[str, Any]], None] | None = None,
) -> BriefValidationDecision:
    active_policy = load_policy() if policy is None else policy
    recorded = list(violations)

    if active_policy.ticket_mode:
        ticket = brief.get("ticket") if isinstance(brief, Mapping) else None
        if not ticket:
            recorded.append(_TICKET_MISSING_VIOLATION)

    recorded_tuple = tuple(recorded)
    if recorded_tuple and record is not None:
        record(
            {
                "event": "brief_schema_drift",
                "mode": active_policy.mode,
                "violations": list(recorded_tuple),
            }
        )

    refused = active_policy.mode == "enforce" and bool(recorded_tuple)
    return BriefValidationDecision(
        mode=active_policy.mode,
        proceed=not refused,
        refused=refused,
        ticket_mode=active_policy.ticket_mode,
        recorded=recorded_tuple,
    )
