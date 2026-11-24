# First mission

`<APPROVER>`, `<DATE, TIME, ZONE>` (their words):

```text
<VERBATIM REQUEST FOR THE FIRST MISSION>
```

**Goal:** `<ONE PARAGRAPH: THE OUTCOME, AND WHY IT MATTERS.>`.

Hard limits (see `RULES.md`): feature branches only, tests that fail first where that is the method, never weaken tests or sandboxing, shared worker cap `<POOL_CAP>`, `nice`/`ionice`, secret scan before every push. The only merges allowed without a new yes are the ones quoted in `RULES.md`. **Do not remove existing forge CI, and do not change rulesets or branch protection, without a yes.**

## 1. Where workers run

| OS / environment | Host | Status |
|---|---|---|
| `<OS>` | `<WORKER HOST — GENERIC NAME ONLY>` | `<EXISTS / PENDING / FALLBACK>` |

Coverage the workers cannot provide (for example a macOS job with no Mac) stays on the existing forge CI until a host exists.

## 2. Jobs to cover

| Repository | Job (check name) | Needs |
|---|---|---|
| | | |

## 3. Trigger

Recommended to start: a scheduled poll of the forge (no inbound port). A webhook needs an exposed endpoint and a yes.

## 4. Reporting results

- Post optional, non-required checks or commit statuses until the approver says otherwise.
- Only the orchestrator posts. Workers never receive a forge token.
- Fail-closed: a crash, timeout, cancel, unsigned or unverifiable result, wrong head SHA, or a different job set is **failure or error (or stays pending), never success**. A missing result is not a pass.

## 5. Phases

- **Phase 0:** this pack; credentials and worker-host access.
- **Phase 1:** `<SHADOW MODE ON THE ENVIRONMENTS THAT ALREADY EXIST>`.
- **Later phases that need a yes:** `<MAKING CHECKS REQUIRED, TURNING FORGE CI OFF, RULESET CHANGES>`.

## 6. Open dependencies

1. `<CREDENTIAL, ADMIN PATH, IMAGE, TOKEN WITH NARROW SCOPE, …>`

## 7. Briefs (use the chapter 19 brief template)

Every brief carries these constraints: no merge, tag, release, publish, deploy, force-push, branch deletion or history rewrite; secret scan before every push; `nice`/`ionice`; never print or commit secrets or private hosts; keep security fail-closed; do not modify forge workflows, rulesets or branch protection unless the brief's lease and a verbatim yes say so.

**`<ID>`:** `<GOAL>`

- Repository / branch / `source_rev`: `<FILL THE FULL SHA AT DISPATCH>`
- Lease: `<PATHS>`
- Acceptance: `<AC-001 … proven by test id>`
