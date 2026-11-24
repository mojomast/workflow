# Memory query CLI

Status: implements the recall endpoint of `rizzstack.memory/1`. The contract's
normative rules live in [memory-contract.md](memory-contract.md); this page
documents the operator-facing command.

`python3 -m rizzstack_memory query` answers one lease-time recall request for a
bundlebees client. It queries the vault, caps the result, prints one JSON object
and exits. It is strictly read-only: it never calls `write`, `promote` or
`run_retention`, and it never creates a missing vault.

## Usage

```sh
python3 -m rizzstack_memory query --vault <vault-dir> QUERY
```

The vault directory must already exist. The query text is the last argv word. If
stdin carries a recall request, its `query` field is a fallback for a missing
argv word.

A request on stdin is optional. When present it must be one JSON object:

```json
{
  "contract": "rizzstack.memory/1",
  "query": "stale lease",
  "caps": {"max_items": 8, "max_excerpt_chars": 480, "max_total_chars": 4000}
}
```

Empty stdin means the defaults above. The query is stripped and truncated to 500
characters. Caps are clamped to at most 8 items, 480 excerpt characters and 4000
total characters; an empty or missing `caps` object uses those same defaults.

The response is exactly one JSON line:

```json
{"contract":"rizzstack.memory/1","vault_rev":"gen-42","items":[{"id":"lease-recovery","type":"learning","sha":"64 lowercase hex characters","path":"learnings/lease-recovery.md","title":"Lease recovery","excerpt":"Re-read the lease file before the next wave."}]}
```

Each item carries `id`, `type`, `sha`, `path`, `title` and `excerpt`. Items stop
before the summed length of those six fields would exceed `max_total_chars`. An
empty vault returns `"items": []` — an honest empty, never padding.

## bundlebees wiring

`BUNDLEBEES_MEMORY_QUERY` names the program the recall client runs:

```sh
export BUNDLEBEES_MEMORY_QUERY="python3 -m rizzstack_memory query --vault <vault-dir>"
```

Replace `<vault-dir>` with the real vault location on the host. The client
appends the query text as the last argv word and may send the request JSON on
stdin.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | one response object printed to stdout |
| `2` | refused: missing or non-directory vault, invalid or wrong-contract request, empty query, or a vault contract error |

On exit `2` the reason is a short line on stderr and stdout is empty. A missing
vault path is never created.

## MEMORY_ENABLED stays off

This command does not change the rollout state. `MEMORY_ENABLED` stays off until
the owner turns it on; wiring `BUNDLEBEES_MEMORY_QUERY` only makes the recall
program available, it does not enable recall.
