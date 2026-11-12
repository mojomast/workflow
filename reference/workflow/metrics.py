"""JSONL metrics log for the reference demo.

These fields match the measurement list in docs/12. The demo records a
synthetic run so the schema is visible; production collection is not
claimed here or in that chapter.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


METRIC_FIELDS = (
    "cost_per_accepted_change",
    "first_pass_verification_rate",
    "human_interventions",
    "plan_to_accepted_seconds",
    "regression_escapes",
    "failed_worker_recovery",
)


class MetricsLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")
        self.started = time.monotonic()
        self.events: list[dict] = []

    def emit(self, event: str, **fields) -> None:
        row = {"event": event, "t_s": round(time.monotonic() - self.started, 4), **fields}
        self.events.append(row)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def summarize(self, verifications: list[dict], accepted_cost: int,
                  rejected: list[dict], integration: dict) -> dict:
        first_pass = sum(1 for v in verifications if v.get("decision") == "accepted")
        attempted = len(verifications)
        rate = (first_pass / attempted) if attempted else 0.0
        elapsed = round(time.monotonic() - self.started, 4)
        accepted_count = first_pass
        cost_per = (accepted_cost / accepted_count) if accepted_count else None
        recovery = {
            "rejected": len(rejected),
            "redispatched": 0,
            "note": "the out-of-scope worker was rejected and not redispatched in this demo",
        }
        summary = {
            "event": "summary",
            "t_s": elapsed,
            "cost_per_accepted_change": cost_per,
            "cost_units_note": "synthetic scripted-worker units, not currency or model tokens",
            "first_pass_verification_rate": rate,
            "first_pass_counts": {"accepted": first_pass, "attempted": attempted},
            "human_interventions": 0,
            "plan_to_accepted_seconds": elapsed,
            "regression_escapes": 0 if integration.get("passed") else 1,
            "failed_worker_recovery": recovery,
            "integration_passed": bool(integration.get("passed")),
        }
        self.emit(**{k: v for k, v in summary.items() if k != "event"}, event="summary")
        return summary
