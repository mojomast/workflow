# 01 — Planning and spec

The pattern that repeats across every project: Kyle states an idea in a sentence or two, an agent researches it and writes a plan document, Kyle approves the plan (often with edits), and only then does any worker start. Approval is scoped: it names exactly what is allowed (for example "push a feature branch and open a PR") and what is not (merge, tag, release, catalog PR, deploy).

## 1. From idea to plan

| Step | What happens | Real examples |
|---|---|---|
| Idea | Kyle describes the outcome, usually in plain words and often with a reference (a video, a repo, a screenshot) | "Make a Hermes plugin for God's Eye View"; "build the CUA bees workflow as a Hermes plugin"; "turn the game-asset pipeline into a library" |
| Research | An agent reads current docs and source before writing anything. Dedicated research bots were created for big questions | **ComfyUI Agentic Research** (agentic ComfyUI best practice, later the open-higgsfield-skills collection), **Demo Hosting Research** (cheap hosts for the Comfyrizz invite demo), **Judge Demo Compute Research** (tokenized judge links and preconfigured inference). bundlebees started with `docs/RESEARCH.md`; the game-asset library started with `RESEARCH.md` (style-locking, taxonomy, SQLite FTS, with sources) |
| Plan doc | A `PLAN.md` / `SPEC.md` with numbered tasks, defaults and open questions | Comfyrizz `RELIABILITY_PLAN.md` (RL01–RL12), the MiniMax voice plan `PLAN.md` (VX01–VX12, "all 7 defaults"), the ref-watch `PLAN.md` (caps: 2 regens per still, max 6 jobs or 25% of stills), the iterative production agent (four docs: main spec, task breakdown, code audit, workflow doc), Emurizz `SPEC.md` + `DEVPLAN.md`, the Buffrizz researched plan |
| Audit-driven plans | For UI work, a strong model audits first and the plan is built from that audit | Comfyrizz's UI revamp plan was built from an Opus cloud agent's audit alone (`AUDIT.md`, `SPEC.md`, `TASKS.md`); Kyle cancelled a parallel Sonnet audit as redundant. Weaker agents then built the fixes |
| Handoff doc | When a live session exposes problems, the findings are written as a prioritized handoff with acceptance tests | The Eye Of Hermes handoff (Nov 5): P0/P1/P2 issues from a ~90-tool-call Hermes session in Montreal, each with the wanted tool or fix, plus five acceptance tests (cold token, reopen, tour, POI, route) and a "do not regress" list |
| Approval | Kyle answers in chat or through a question card; the approved scope is recorded in memory verbatim | "Kyle approved building the compose-v2 scene engine … on a feature branch that gets pushed with a PR opened … Merge, tag, release, catalog repin and deploy aren't approved." |

Kyle has also asked for plans to be written "as if there were no deadline" (the Comfyrizz iterative production agent) and then approved slices of them; and he has asked for plans to be shown before any build starts (the MiniMax "no-clip" voice mode, Kimi For Coding launcher config changes).

## 2. Slicing work for parallel agents

Kyle prefers development split across several agents in parallel. The plans that worked share a shape:

1. **Contracts first.** One task (often called Slice 0, UX00 or BB00) lands the shared interfaces, file layout and file leases before parallel work. Examples: Comfyrizz UX00 "shared contracts" (Opus, PR #45), bundlebees `docs/tasks/BB00_CONTRACTS.md`, hermes-templeos "Slice 0 contracts and plugin scaffold" then Slices A–D.
2. **Non-overlapping file leases.** Each worker task lists `assigned_files`; the verifier rejects any patch that touches other files.
3. **Waves.** Tasks with dependencies run in waves (Comfyrizz UX remediation ran Wave 0 → Wave 4; bundlebees used 4 bees in two waves). Some tasks are explicitly "held" until a dependency lands or Kyle unlocks them.
4. **Integration PR.** One PR from the feature branch to main that Kyle reviews.

## 3. What a good plan or brief includes

Drawn from the plans and briefs that ran well (see [03](03-development-and-orchestration.md) for full brief examples):

- The objective in one sentence and the repo, branch and merge target.
- Exactly which files may change.
- "Write the test first and confirm it fails" for code tasks.
- Hard rules repeated inline (no secrets, no network in tests, no merge/tag/deploy).
- A `<decisions>` block: what Kyle already approved and what he did not, plus design decisions (D1, D2 …) so workers can't re-litigate them.
- Measurable acceptance: tests that must pass, a schema token budget (e.g. "combined schema ≤ 900 o200k tokens"), media specs (e.g. "H.264 yuv420p 1080p30, AAC, about −16 LUFS, under 90 s").
- Budgets for anything that costs money (Google Colab CU caps per run, e.g. "≤ 15 CU", "fresh 5 CU cap", "within the 10 CU total cap").
- What to deliver back (PR link, SHA, test counts, file paths, what was rejected and why).

## 4. Specs that live in repos

Many specs ended up committed: Comfyrizz `docs/specs/TIMELINE_REVIEW.md` on `feat/timeline-review`; the iterative production agent docs on `docs/iterative-production-agent-spec`; `promo/hyperframes/STYLE.md` (asked for in the EOH promo restyle brief before any building); bundlebees `docs/RESEARCH.md` and task contracts. Plans that stayed on the box (`/workspace/<project>/PLAN.md`) were referenced by path in memory.

## 5. Where planning went wrong and what changed

- Free-model stalls made long plans slip (Oct 21–23): plans now state the model order and fallback rules up front (see [03 §4](03-development-and-orchestration.md#4-deepseek-bees-cua-sandboxes-on-kyles-pc)).
- A spec that changed mid-flight (Emurizz N64 went from 2 to 4 players required) left the committed spec stale; memory notes record which spec text is superseded.
- Gemini's first Comfyrizz UI overhaul was "too timid"; Kyle asked for a drastic revamp and the plan was rebuilt from a stronger model's audit.
