# 32 — Memory contract (`rizzstack.memory/1`)

Status: draft, normative for the memory layer's contract, schema and integration
points. The vault service that implements the operations is a follow-on slice;
the honest split is in [Gaps](#gaps-what-is-design-only-vs-implemented).

The memory layer is the rizzstack's semantic memory: a plain, Obsidian-compatible
markdown vault that any agent can read, search and write through one small,
agent-agnostic contract. The design follows the research digest the owner
approved:

- **Files plus search is the mainstream convergence.** Every serious agent-memory
  system in the wild landed on plain files plus a real search path, not a bespoke
  store. Markdown in a vault is inspectable by the human, versioned by git, and
  usable by any harness without a driver.
- **The operating loop is capture, distill, inject.** Hooks capture; an
  extraction step distills; recall injects the result into the next brief.
- **Transcripts are never treated as knowledge.** A raw session transcript is
  source material. Only a distilled memory with named sources may be served back,
  and every memory carries the provenance of every claim it makes.

- Wire contract: `rizzstack.memory/1`
- Schema: `schemas/memory-schema.v1.json`
- Conformance oracle: `tests/test_memory_contract.py`
- Protocol map (workflow mirror): `docs/protocol.md`

## The rulebook comes first

The vault is its own manual. `VAULT.md` at the vault root is the rulebook, and it
is the first thing any consumer reads — human or agent — before touching anything
else in the vault. It states the layout below, the write zones, the retention
duties and the scrubbing rule in vault-relative terms, so a worker that only has
the vault still knows how to behave inside it. The rulebook is maintained by the
vault service; it is never written through the operation surface.

## The contract surface

Three operations over the vault, shaped so any harness consumes the contract
without learning stack internals:

| Operation | In | Out |
|---|---|---|
| `read` | a vault-relative path, optional `expected_sha` | the frontmatter record and the markdown body; a mismatching `expected_sha` warns the reader the file moved under it |
| `query` | `q`, optional `types`, `k`, `mode`, `include_expired` | a `query-result`: `mode_used` plus ranked hits, each with `id`, `type`, `path`, `title`, `sha`, `score`, `snippet` |
| `write` | the `write-op` envelope below | a `write-result`: an accepted receipt or a refusal with a code |

Agent-agnostic means: the envelopes carry ids, paths, digests and types — never
harness names, model names, sandbox details or transcript dumps. A bee on a
sandbox, an executor on the box and the owner's own session all speak the same
three operations. The umbrella protocol row (`rizzstack.memory/1`) is the
portable half; the workflow repo carries the schema and the oracle.

## The vault layout

| Path | What lives there | Zone |
|---|---|---|
| `concepts/` | distilled, stable reference knowledge — what a thing is and how it works, with sources | curated |
| `entities/` | `env-fact` memories: checked facts about concrete things in the environment (a host, a service, a repo, a tool) | reviewed |
| `decisions/` | `decision` memories: chosen directions and why | curated |
| `learnings/` | `learning` memories: durable insights about how work behaves | reviewed |
| `pitfalls/` | `pitfall` memories: confirmed traps and their fixes | reviewed |
| `projects/` | `project-state` memories: where a project stands and what is next | reviewed |
| `sessions/` | episodic session digests written by the capture hook — source material, never served as knowledge | service-owned |
| `index.md` | the hand-built index of entries and wikilinks | curated |
| `hot.md` | the always-injected slice: the small set of facts every brief should start from | curated |
| `log.md` | the append-only receipt log: every accepted write, expiry and promotion, with its sequence number | service-owned |
| `VAULT.md` | the rulebook (see above) | service-owned |

One file per memory, named `<id>.md`, in the directory its type maps to
(`decision` → `decisions/`, `learning` → `learnings/`, `pitfall` → `pitfalls/`,
`env-fact` → `entities/`, `project-state` → `projects/`,
`reference` → `concepts/`). Writing a memory into a directory its type does not
map to is refused.

## Memory types and frontmatter

Every memory is a markdown file with YAML frontmatter. The parsed frontmatter is
exactly the record `schemas/memory-schema.v1.json` describes:

```yaml
---
schema: rizzstack.memory/1
id: workbench-crash-resume
type: learning
created: 2026-11-14T18:20:00Z
modified: 2026-11-14T18:20:00Z
retention:
  policy: learning-until-superseded
  expires: null
  superseded_by: null
sources:
  - kind: session-digest
    ref: sessions/2026-11-14-workbench-crash.md
    note: operator diagnosis narration
sha: 64 lowercase hex characters
---
# Workbench crash resume

A workbench crash mid-wave leaves a stale lease behind.

- Resume from the recovery digest, never from chat scrollback.
- Re-read the lease file before dispatching the next wave.
```

| Field | Meaning |
|---|---|
| `schema` | always `rizzstack.memory/1`, so a reader knows the contract before anything else |
| `id` | lowercase kebab slug, unique across the vault; renaming is refused, supersession replaces |
| `type` | one of `decision`, `learning`, `pitfall`, `env-fact`, `project-state`, `reference` |
| `created`, `modified` | RFC 3339 instants; `created` never after `modified` |
| `retention` | `policy` plus `expires` and `superseded_by` (both nullable) — see [Retention](#retention-discipline-decided-upfront) |
| `sources` | one to twelve provenance entries: `kind` (`session-digest`, `operator-note`, `pull-request`, `file`, `tool-output`, `external`), `ref`, optional scrubbed `note` |
| `sha` | the memory digest (below) |

A memory with no source is refused. A raw transcript is never a source; the
`session-digest` kind points at the distilled digest a human or the extraction
step wrote, not at the scrollback.

## The digest and the sha guard

`sha` is sha256 over the canonical JSON of the frontmatter **without the `sha`
field itself** (sorted keys, compact separators), then a newline, then the
markdown body. Any consumer can recompute it; it rotates on every content
change, including frontmatter-only edits such as a new `modified` instant.

Every write carries `expected_sha` — the digest the writer last read:

- **Create** (`path` not in the vault): `expected_sha` must be null.
- **Update**: `expected_sha` must equal the stored digest.
- On mismatch the write is refused with code `sha_conflict`, the refusal names
  `current_sha`, and `reread_required` is true: the writer must re-read the
  memory and reapply its edit on the current version.

This is the agent-notes pattern that makes multi-agent conflict safe: two
writers who read the same memory and both try to edit it cannot clobber each
other — the second write is refused with the current digest in hand, and the
loser merges instead of overwriting. A write whose own frontmatter digest does
not match its body is refused as `sha_mismatch` before anything is stored.

## The write contract: quarantine and grants

Writes are quarantined by default. A `write-op` names its `writer` as a
kind-prefixed id (`agent:bee-7`); without an explicit grant the write may only
target the writer's own subtree, `.quarantine/<writer-slug>/` (the writer id
with the kind separator replaced by a hyphen). Anything else is refused with
`write_quarantined`.

A write outside the subtree carries an `authority` grant:

```json
{
  "grant_ref": "approvals/2026-11-14-memory-promotion.md",
  "approved_by": "human:owner",
  "approved_at": "2026-11-15T09:00:00Z"
}
```

`grant_ref` names the durable approval record, `approved_by` is a
kind-prefixed id, and writers cannot approve their own grants: the approver is
one of `human`, `orbit` or `bundlebees`. Curated zones (`concepts/`,
`decisions/`, `hot.md`, `index.md`) additionally require a **human** approver —
a bot cannot self-authorize into the zones every other agent will trust.
Service-owned paths (`sessions/`, `log.md`, `VAULT.md`) are never written
through the operation surface at all.

## Brief injection

The dispatch-brief path gains a memory-context step. Before a lease is
granted, the recall step queries the vault, caps the result, and puts the
payload in the lease payload under `memory_context`. The worker never assembles
it itself; it receives typed, digest-pinned excerpts:

```json
{
  "contract": "rizzstack.memory/1",
  "items": [
    {
      "id": "workbench-crash-resume",
      "type": "learning",
      "sha": "64 lowercase hex characters",
      "title": "Workbench crash resume",
      "path": "learnings/workbench-crash-resume.md",
      "excerpt": "Resume from the recovery digest, never from chat scrollback."
    }
  ],
  "caps": {"max_items": 8, "max_excerpt_chars": 480, "max_total_chars": 4000},
  "vault_rev": "gen-42"
}
```

Caps are part of the contract, not a courtesy: at most **8** items
(`max_items`), at most **480** characters per excerpt (`max_excerpt_chars`), at
most **4000** characters in total (`max_total_chars`). A brief with nothing
relevant carries an empty list — an honest empty, not padding. Every item pins
the digest of the memory it came from, so a worker that needs more can `read`
the path and detect drift if the memory changed since injection.

**Worked example — the workbench recovery digest.** A workbench crash mid-wave
used to leave the next attempt reconstructing state from chat scrollback. Under
this contract: the capture hook writes a session digest to `sessions/`; the
distillation beat distills the diagnosis into
`learnings/workbench-crash-resume.md` with the digest as its source; the
recovery step that builds the resume brief injects it as a `memory_context`
item, digest-pinned and size-capped. The next attempt starts from the durable
diagnosis, not from a transcript.

## Retention discipline, decided upfront

Expiry is a per-type policy decided at write time, not a background cleanup
guessing later. A memory is **expired** when `superseded_by` is set or
`expires` has passed; queries hide expired memories unless they opt in with
`include_expired`.

| Type | Policy | The duty: who sets what, when |
|---|---|---|
| `decision` | `decision-permanent` | never auto-expires; a newer decision sets `superseded_by` |
| `learning` | `learning-until-superseded` | persists until a newer learning sets `superseded_by`; `expires` must stay null |
| `pitfall` | `pitfall-until-fixed` | the fixer sets `expires` when the fix is verified |
| `env-fact` | `env-fact-until-fix` | expires when the environment changes: the replacement fact is written and `superseded_by` points at it |
| `project-state` | `project-state-until-done` | expires on completion: the coordinator sets `expires` when the project is parked or archived |
| `reference` | `reference-refresh` | carries a re-verify deadline; refreshing updates the digest and re-sets `expires` |

The schema enforces the pairing both ways: each type accepts only its own
policy, a decision or learning with a deadline is refused, and a reference
without a re-verify deadline is refused.

**The distillation duty is a beat-documented step, not noise accumulation.** At
each session close (and again at campaign closeout), a documented step walks the
new digests in `sessions/` and, for each one, either promotes a memory (with the
digest as its source), supersedes an older one, or records an explicit decision
in `log.md` to keep nothing. Only after distillation may the beat prune the
digests it consumed — episodic material becomes semantic memory or it is
consciously dropped. Nothing writes to the vault on a timer, and no hook
promotes its own captures.

## Hybrid retrieval at our scale

A vault is hundreds of small markdown files, not millions of documents, so the
retrieval stack is local, boring and honest about degradation:

- **Keyword leg:** an SQLite FTS5 index over the vault, updated incrementally on
  every accepted write.
- **Semantic leg:** a small local embedding model over title plus body. No cloud
  services, no external calls at query time — the whole stack runs on the box
  that holds the vault.
- **Fusion:** reciprocal rank fusion over the two rankings, with the standard
  constant `k = 60`: `score(hit) = sum over rankings of 1 / (60 + rank(hit))`.
  The fused order is what `query` returns under `mode_used: hybrid`.
- **Fallback:** when an engine is unavailable the vault falls down the chain and
  says so. `hybrid` or `semantic` without embeddings falls to `keyword` (the
  FTS5 index); without the index it falls to `grep`: ripgrep over the markdown
  plus traversal of `index.md` and the wikilinks between files. `grep` is always
  available and never leaves the machine. `mode_used` always names the engine
  that actually ran — a degraded result is labelled, never silent.

## What the vault must never store

A memory never quotes a credential, an environment file, or a private endpoint;
those live in the environment and the authorized host runbook. Scrubbing
happens before write, and the verify gate enforces the same discipline over this
repository itself: every added line of every leased file is scanned against the
gate's refusal rules, and this document deliberately shows placeholders (such as
`64 lowercase hex characters`) wherever a realistic literal would trip them.

## Gaps: what is design-only vs implemented

| Piece | State | Where |
|---|---|---|
| Frontmatter schema, operation envelopes, injection payload | implemented | `schemas/memory-schema.v1.json` |
| Digest, sha-guard refusals, quarantine zones, grant rules, injection capping, expiry evaluation, fallback resolution | implemented as the reference oracle | `tests/test_memory_contract.py` (in-memory) |
| JSON Schema cross-check of the oracle's fixtures | implemented, run when jsonschema is installed | `tests/test_memory_contract.py` |
| The vault service itself (read/query/write over disk, log.md receipts, vault_rev) | design-only | follow-on slice |
| FTS5 indexing, local embeddings, RRF fusion, ripgrep fallback | design-only | the contract defines shapes and the fallback chain; the service implements them |
| Capture hooks and the distillation beat runner | design-only | the contract defines the duty; the runner is unbuilt |
| Umbrella protocol map row | mirrored here; the canonical map lives in the umbrella repo's docs | `docs/protocol.md` (workflow mirror) |

## What the tests enforce

`tests/test_memory_contract.py` is the normative oracle. It validates every
fixture memory, op and payload against the schema (when jsonschema is present)
and against hand rules that are the contract's semantic half: digest
determinism and rotation, stale-digest refusals with the re-read requirement,
quarantine and grant rules including the human-only curated gate, injection
caps, the per-type expiry table, the fallback chain, the layout and rulebook
rules this document must satisfy, and the gate-exact scanner self-scan over
every line of every leased file.
