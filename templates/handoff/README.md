# Orchestrator handoff kit

This kit is for moving **coordination itself** from one agent to another mid-stream. It is not the single-outcome brief in [`../HANDOFF.md`](../HANDOFF.md).

How to use it:

1. Read [docs/20-orchestrator-handoff.md](../../docs/20-orchestrator-handoff.md).
2. Copy this folder to a directory on the incoming host, and keep a copy the approver can read.
3. Fill every placeholder (`<APPROVER>`, `<OUTGOING>`, `<INCOMING>`, `<REPO LIST>`, …). Delete a section only when you can say why it does not apply.
4. Quote the approver verbatim in `RULES.md`. Never paste tokens, private hosts, private IPs, internal URLs or environment-file values into any of these files.
5. Give the incoming coordinator `KICKOFF-PROMPT.md` and point it at the pack. Live forge state wins over every snapshot.

Suggested reading order for the incoming coordinator: `RULES.md`, `HANDOFF.md`, `CAPABILITIES.md`, `PROPOSED-STEPS.md`, `FIRST-MISSION.md`, `PLAYBOOK.md`. `STATUS-SNAPSHOT.md` is older by definition; where it disagrees with `HANDOFF.md`, `HANDOFF.md` wins.
