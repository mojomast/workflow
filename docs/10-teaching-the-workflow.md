# 10 Teaching the workflow

Teach this workflow by completing one small handoff, receiving evidence and improving the result. The learner should be able to explain why a decision was made and reproduce the relevant check without access to the original conversation. This is a proposed exercise, not a record of a completed training session.

## A runnable miniature

Someone cloning this repository can run a complete miniature of the loop without private infrastructure, models or network:

```bash
python3 reference/run_demo.py
python3 -m unittest discover -s reference/tests -v
```

The demo is documented in [reference/README.md](../reference/README.md). It writes a contract and an immutable lease, runs two scripted workers on separate slices of a tiny repo, rejects a deliberately out-of-scope patch, verifies each result in a throwaway checkout, fills [HANDOFF.md](../templates/HANDOFF.md) and [RETURN.md](../templates/RETURN.md), runs the combined test suite, and writes a metrics log. It complements the practice session below; it does not replace it, and it does not authorize any production action. The architecture behind the loop is in [12](12-three-layer-architecture.md).

## A 60 to 90 minute practice session

Use a disposable checkout and a small task with no paid generation, deployment or publishing. One learner can play both author and receiver in separate passes; a partner makes missing context easier to spot.

1. **Read an example, 10 minutes.** Read [the Doppler handoff](../examples/doppler-review-handoff.md) and identify the outcome, baseline, invariants and evidence limits. Explain why the early and final benchmark claims cannot be combined.
2. **Write a packet, 15 minutes.** Choose a tiny local change or asset correction. Complete [HANDOFF.md](../templates/HANDOFF.md), including a check that would detect the wrong result. Set a time budget and explicit stop conditions.
3. **Receive and produce, 20–30 minutes.** Give the packet to a partner or start a fresh pass with only its listed inputs. Record missing context. Produce the artifact and [RETURN.md](../templates/RETURN.md). Mark unavailable checks honestly.
4. **Review, 15–20 minutes.** Inspect the actual artifact, rerun its decisive check, and make an acceptance decision. Include at least one failure case: a malformed input for code, a loop boundary for animation, or a stale export for a film.
5. **Extract a lesson, 10 minutes.** Improve one sentence or field in the packet that would have prevented confusion. Explain where the lesson belongs and what it does not generalize to.

## Choose an exercise

| Track | Small assignment | Deliberate trap | Completion evidence |
|---|---|---|---|
| Planning | Write an implementation packet for two-player local simulation shown inside an app pane | Receiver substitutes remote streaming or an external window | Acceptance explicitly checks synchronization and in-pane presentation independently |
| Code | Make a tiny local JSON-cache reader treat an incomplete record as a miss | Matching identity is mistaken for valid contents | Valid hit, missing field and malformed JSON cases produce the specified behavior |
| Assets | Package a learner-owned transparent animation or icon with an integration note | Preview looks correct but runtime format differs | Source/export identity, dimensions, transparency and target integration check are recorded |

These exercises reproduce the decision patterns, not the original projects' full environments. The code exercise uses a local fixture and needs no real aircraft recordings. The asset exercise can reuse existing learner-owned art without generating new images.

## Completion rubric

Mark each item pass, revise or not assessed. Complete the exercise only when every applicable item passes; explain any item marked not applicable.

- **Outcome:** another person can describe the intended user-visible behavior.
- **Context:** the baseline and every necessary input are accessible and versioned.
- **Scope:** chosen decisions, file ownership, authorization and stop conditions are clear.
- **Execution:** the receiver can perform the task without reconstructing a missing conversation.
- **Evidence:** the decisive check is reproducible; failures and unrun checks are disclosed.
- **Handoff:** editable source and the delivered artifact agree; the receiver knows the next action.
- **Learning:** one concrete improvement is saved at the appropriate scope.

For a production handoff, add the project's integration and release gates from [09](09-reproducible-collaboration.md). Passing this practice exercise does not authorize publishing or prove production readiness.

## Questions for the review

Ask the learner to explain which evidence would change their conclusion. Then change one input: a new commit, a different runtime format, a reduced budget or a revised user requirement. A teachable workflow should reveal what must be rechecked and what remains valid.

Across future runs, record time to the first useful artifact, missing-context questions, review findings, revision count and whether the receiver reproduced the check. These are proposed learning measures; there is no measured baseline yet. Use them to reduce ambiguity and rework, not to reward inflated test counts or more agents.
