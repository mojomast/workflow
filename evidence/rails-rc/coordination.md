# Rails integration gate — 2026-11-17

This record accompanies the four draft PRs. Its branch is separate from the candidate: adding test results to a tested commit would change the SHA being attested to. It records software checks, not receiver decisions. The coordinator owns final integration; no worker can promote their own delivery.

## Starting inputs

All four PR heads were fetched from GitHub. None had advanced since the preceding publication. All four were open drafts. The scope is the existing candidate; an unprotected branch or missing repository rule is not an approval. See `start.json` for base SHAs, published checks and timestamps. The normative inputs at the starting Workflow head are:

| File | SHA-256 |
|---|---|
| `specs/rizzstack-rails-spec.md` | `f0bcedc310b8796b43efaf9b5f355ef3e8e1b3ac01f758e018f53ee8159da3bf` |
| `schemas/return-manifest.schema.json` | `7a0a83ba1d22e412c3ee6dec49e8d5661ff2f8f682ff527b6047a2ea7f7eaddc` |
| `tools/return_manifest.py` | `88c58d5b9b6f33ad23c5c9fcaaa3235c200b71d2f0582483f79dcabd584c907a` |

## Coordination ledger

Local assignments below are not Hyvv claims, paid dispatches or remote job receipts. The production backlog and its recorded original attempts remain intact. Each worker has a bounded file lease and two correction passes before reconciliation. No live host budget is consumed by this run.

| Package / owner | File scope | Depends on | Acceptance |
|---|---|---|---|
| A / native producer | BundleBees RETURN builder, native evidence tests | frozen Workflow schema + checker | independently rebuilt native RETURN passes both validators; substituted evidence refused; both decisions pending |
| B1 / receiver | Workflow R18 and isolated premerge runner | A for GREEN | every mandated case executes on the four identified commits; no skipped case is green |
| B2 / Orbit CI | failing CI jobs / affected Orbit fixture and build files | current head and base comparisons | original CI errors explained, corrected gates pass without loosening tests |
| C / canary operator preparation | Workflow offline canary evidence | explicit worker-scoped operator authority for live work | read-only rehearsal and host evidence separated; no remote action on missing authority |
| D1 / storage | BundleBees canonical ledger + tests | original concurrency failure | ten independent first writers, replay and refusal survive reopen |
| D2 / measurements | Workflow benchmark + fixtures | exact tuple + verified client build | record workload, observed identity/counts, timings, excluded coverage; distinguish SSE receipt from visible paint |
| E / authority reviewer | read-only code review of all four diffs | exact reviewed SHAs | disposition for provenance, authority, persistence and transport defects |
| F / integration reviewer | read-only review of four diffs, prior PRs and acceptance evidence | parent release tuple for final check | content comparison, byte parity, reproducibility and open blockers |
| G / coordinator | vendor manifests, packaging, evidence branch and PR handoff | A–F | qualify immutable tuple, preserve failing evidence, reconcile reviews; human gates remain explicit |

## Sequencing and rollback

1. Review frozen Workflow contracts and the canonical BundleBees producer/runtime first. Qualify the entire tuple before recommending any merge. Never resolve divergent producer/receiver behavior by relaxing the frozen validator.
2. Keep the canonical BundleBees Git object reachable across the merge; if squash/rebase changes the intended upstream pin, regenerate both downstream pins and rerun parity, R18 and CI before activation. Incorporate overlapping PRs only once.
3. Land tested downstream Hyvv and Orbit readers with Rails disabled, then the Workflow harness/evidence pointers. Requalify merge commits if they differ from the tested trees. Review the Orbit source archive against its unpacked source and retain the last known working package.
4. Before promotion, verify installed and loaded versions, backup/restore of **copied** coordinator state and historical wave compatibility. Owner and host operator bind the worker, contract, workspace, permitted interruption, idle window and spending limit. A passing hosted Windows job does not supply those facts.
5. Stage a single Windows exporter, one coordinator import owner, then the read service and Orbit reader. Confirm chain anchors, continuous cursor/identity receipts and complete RETURN at each handoff. Owner-only feedback is a separately enrolled capability; keep retry fenced and the legacy approval route unmounted.
6. On failure, stop admitting new work; suspend the Orbit route, then the import consumer and test exporter. Preserve durable leases, database/WAL, source journal, checkpoints, private signing material and approved retention boundaries in place. Record last known good anchors before reverting binaries/config. Resume from a verified checkpoint on compatible code, not a new empty ledger. Require a separate authorized decision for merge, rollout and receiver acceptance.
