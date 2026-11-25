# Memory retention runner

Status: implements the retention slice of `rizzstack.memory/1`. The contract's
normative rules live in [memory-contract.md](memory-contract.md); this page
documents the operator-facing pass.

## What the runner does

`rizzstack_memory.retention` scans a markdown vault once and classifies every
memory against the retention block its writer already decided:

- **supersession** — `retention.superseded_by` is set;
- **expiry** — `retention.expires` is at or before the supplied `--now`;
- **active** — neither condition holds.

It appends exactly one `log.md` receipt for each expiry or supersession it has
not receipted before, then stops. It never rewrites memory frontmatter: the
existing `active_records` and `query` paths already hide expired records through
`is_expired`, and they stay authoritative. `include_expired=True` still returns
those records together with their `retention` block.

The pass is idempotent by construction. A receipt carries a `fingerprint` of the
retention state (`id`, `type`, `policy`, `expires`, `superseded_by`, `reason`);
a later run with the same clock sees that fingerprint in `log.md` and writes
nothing for the same item. A genuinely new state — a different
`superseded_by`, a new deadline — produces a new receipt and the next sequence
number.

## Per-type policy duties

The runner enforces the pairing the contract decides at write time. It never
invents an expiry for a type that must not have one.

| Type | Policy | Duty enforced at expiry time |
|---|---|---|
| `decision` | `decision-permanent` | never carries `expires`; a newer decision sets `superseded_by` |
| `learning` | `learning-until-superseded` | `expires` stays null; a newer learning sets `superseded_by` |
| `pitfall` | `pitfall-until-fixed` | the fixer sets `expires` when the fix is verified |
| `env-fact` | `env-fact-until-fix` | the replacement fact is written and `superseded_by` points at it |
| `project-state` | `project-state-until-done` | the coordinator sets `expires` when the project is parked or archived |
| `reference` | `reference-refresh` | always carries a re-verify deadline; refreshing moves `expires` |

A record that breaks the pairing is a typed refusal (`policy_mismatch`): a
decision or learning carrying `expires`, or a reference without one. The
decision names the memory id and the policy, and nothing is written for that
record — no receipt, no frontmatter edit.

## Documented invocation

```sh
python -m rizzstack_memory.retention --vault <path> --now <rfc3339> [--dry-run]
```

Examples:

```sh
# Inspect the decisions without touching log.md.
python -m rizzstack_memory.retention --vault ./vault --now 2026-11-15T09:00:00Z --dry-run

# Apply the pass: append one receipt per new expiry or supersession.
python -m rizzstack_memory.retention --vault ./vault --now 2026-11-15T09:00:00Z
```

The command prints one JSON object with `vault`, `now`, `dry_run` and a
`decisions` list. Each decision carries the memory `id`, `path`, `type`,
`policy`, its `retention` block, whether it is `expired`, the `reason`
(`expiry` or `supersession`), the `action` (`active`, `logged`, `unchanged`,
`would_log` or `refused`), and the refusal `code`/`message` when applicable.
`--dry-run` returns the same decisions with `would_log` in place of `logged`
and writes nothing.

The same pass is available in-process as `DiskVault.run_retention(now,
dry_run=False)` or `rizzstack_memory.retention.run(vault, now, dry_run=False)`.

## Receipt format

Every entry is one JSON object on its own line in `log.md`, appended through
the vault's existing fsynced receipt writer so it shares the monotonic
`seq` counter with write receipts:

```json
{
  "at": "2026-11-15T09:00:00Z",
  "event": "expiry",
  "fingerprint": "sha256 of the retention state",
  "id": "stale-reference",
  "kind": "retention",
  "path": "concepts/stale-reference.md",
  "policy": "reference-refresh",
  "reason": "expiry",
  "retention": {
    "expires": "2026-11-01T00:00:00Z",
    "policy": "reference-refresh",
    "superseded_by": null
  },
  "seq": 7,
  "type": "reference"
}
```

`event` and `reason` are both `expiry` or `supersession`; the duplication keeps
the receipt readable on its own. Sequence numbers are strictly increasing and
never reused.

## Seeding from the agent lessons

`scripts/seed_memory_from_lessons.py` turns every `### L-NN · Title` section in
[28-agent-lessons.md](28-agent-lessons.md) into one `learning` memory with id
`lesson-l-nn`. It writes as `agent:lessons-seed` without an authority grant, so
the records land in that writer's quarantine subtree
(`.quarantine/agent-lessons-seed/`) and need a human grant to promote them into
the reviewed or curated zones. Re-running is idempotent; `--dry-run` lists the
ids and touches nothing.

```sh
python3 scripts/seed_memory_from_lessons.py --vault <vault-path> [--now <rfc3339>] [--dry-run]
```

The last stdout line is a JSON summary with the writer, the number written and
unchanged, and whether the run was a dry run.

## Scheduling is an operator decision

This slice ships **no cron entry, systemd timer, daemon or background job**. The
runner is a documented, replayable command: an operator decides when and where
it runs, inspects the decisions (with `--dry-run` first if desired), and checks
the receipts. Nothing mutates the vault on a hidden schedule.

## Rejected alternative

**A background daemon that rewrites the vault on a timer.** Rejected because the
contract makes retention a decided-upfront per-write policy and an idempotent,
documented pass — not an opaque process mutating user knowledge. A command an
operator can inspect, replay and diff is auditable; a daemon is not.
