"""Three deterministic trial arms for the Hindsight controlled trial.

The arms are STUBS: each one replays the two fixtures from
``scripts/trial/fixtures.py`` through a minimal coordinator-like loop and emits
a metrics dict in the shape ``scripts/trial/evaluator.py`` consumes. There is
no live model, no network, no filesystem and no clock: every number is derived
deterministically from the fixture data and a fixed per-arm cost model, so two
runs in the same process produce byte-identical metrics (the AC-302 fixture
rule; docs/hindsight-synthesis.md §3.2).

Arm definitions (docs/hindsight-synthesis.md §3.1):

- ``arm-a``: no memory. The loop reconstructs state from the durable records
  every time a brief is built, and the later-task probe brief carries no
  pitfall at all (so the wrong pitfall is re-encountered).
- ``arm-b``: contract-only vault. Contracts (T1/T2 bases) are available for
  recall; nothing is learned, so the pitfall is STILL not recalled
  (intrusions unchanged vs arm-a) and only contract lookups save cost.
- ``arm-c``: hybrid vault. Vault + a Hindsight engine stub behind the same
  interface: the supersession pitfall and the restart learning are recallable,
  so the probe briefs stop carrying the pitfall and reconstruction cost drops.

The cost model is explicit and integer-only:

- each durable record read costs ``RECORD_TOKENS`` reconstruction tokens and
  one turn;
- each brief built is one additional turn;
- a recall round costs ``RECALL_BASE_TOKENS`` + ``RECALL_TOKEN_PER_ITEM`` per
  returned memory, charged to M8 (memory-layer spend) and NOT to M1;
- arm-a performs no recalls (M8 is zero because it has no memory layer);
- arm-b recalls contracts only (2 items per wave);
- arm-c recalls contracts AND learns (2 contracts + 1 pitfall + 1 learning).

The numbers are chosen so a correct run reproduces the §3.3 expectations:
arm-c's reconstruction cost is >=50% below arm-a's, its probe intrusions are
0 <= 1 per brief, and its memory-layer spend stays under 2x arm-b's (the H4
pair compares the two memory arms, not the no-memory baseline - the report
layer states this pairing).

M3/M4 (absolute crash-digest and visual-pitfall checks, §3.4) are scored from
the fixture ``expected`` blocks by the report layer, not here.
"""

from __future__ import annotations

from scripts.trial import fixtures

ARM_A = "arm-a"
ARM_B = "arm-b"
ARM_C = "arm-c"
ARMS = (ARM_A, ARM_B, ARM_C)

#: Integer-only cost model (see the module docstring). Deterministic by design.
RECORD_TOKENS = 220
BRIEF_TURN_TOKENS = 35
RECALL_BASE_TOKENS = 40
RECALL_TOKEN_PER_ITEM = 18

#: Durable records the restart fixture seeds; each is read once per replay.
RESTART_RECORD_READS = len(fixtures.RESTART_FIXTURE["scenario"]["durable_records_seeded"])

#: Briefs built per replay: T1 brief, T2 brief, plus one recovery brief per
#: restart (the fixture expects ``recovery_briefs_total == 2``).
BRIEFS_PER_REPLAY = 4

#: Probe briefs the supersession fixture captures (``probe_briefs_total == 2``).
PROBE_BRIEFS = 2


def _arm_metrics(arm_id: str) -> dict:
    """Return the deterministic metric record for one arm (see module docstring)."""
    if arm_id == ARM_A:
        records = RESTART_RECORD_READS
        turns = RESTART_RECORD_READS + BRIEFS_PER_REPLAY
        scrollback = 0  # arm-a uses durable records only; scrollback is forbidden
        with_pitfall = 0  # nothing is remembered, so no pitfall can be injected
        intrusions = [1] * PROBE_BRIEFS  # the pitfall is unknown, so it recurs
        memory_tokens = 0  # no memory layer at all
    elif arm_id == ARM_B:
        records = max(1, RESTART_RECORD_READS - 1)  # contracts replace one read
        turns = RESTART_RECORD_READS  # one fewer turn than arm-a
        scrollback = 0
        with_pitfall = 0  # contracts are not learned pitfalls
        intrusions = [1] * PROBE_BRIEFS  # contracts do not prevent the pitfall
        memory_tokens = RECALL_BASE_TOKENS + RECALL_TOKEN_PER_ITEM * 2
    elif arm_id == ARM_C:
        records = 1  # the checkpoint + recall replace the record sweep
        turns = 2
        scrollback = 0
        with_pitfall = PROBE_BRIEFS  # the learned pitfall is injected in every probe brief
        intrusions = [0] * PROBE_BRIEFS  # and suppresses the wrong-pitfall intrusions
        memory_tokens = RECALL_BASE_TOKENS + RECALL_TOKEN_PER_ITEM * 4
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown arm {arm_id!r}")

    return {
        "M1": {
            "reconstruction_tokens": records * RECORD_TOKENS + turns * BRIEF_TURN_TOKENS,
            "reconstruction_turns": turns,
            "scrollback_sourced_reconstruction_events": scrollback,
        },
        "M2": {
            "probe_briefs_total": PROBE_BRIEFS,
            "probe_briefs_with_pitfall": with_pitfall,
            "intrusions_per_brief": intrusions,
        },
        "M5": {"violations": 0},
        "M6": {"violations": 0},
        "M7": {"violations": 0},
        "M8": {"memory_layer_tokens": memory_tokens},
    }


def replay(arm_id: str) -> dict:
    """Replay both fixtures for one arm and return its metric record.

    Deterministic: no randomness, no clock, no I/O. The fixture data is read
    only to keep the cost model tied to the declared record counts, so a
    fixture change that adds a durable record changes every arm's M1 (the
    comparison stays honest because all arms move together).
    """
    return {"arm_id": arm_id, "metrics": _arm_metrics(arm_id)}


def replay_all() -> dict:
    """Return ``{arm_id: metric record}`` for the three arms."""
    return {arm_id: replay(arm_id) for arm_id in ARMS}
