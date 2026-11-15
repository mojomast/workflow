# CHECKLIST — handoff switch, ticked in place ([docs/20 §13](../../docs/20-orchestrator-handoff.md))

## Approver (Kyle)

- [ ] Has said, in his own words, that the campaign plan is approved to execute (Wave 0)
- [ ] Has said how he will talk to the incoming coordinator
- [ ] Has confirmed which in-flight approvals still stand, verbatim
- [ ] Has approved each live-host step that needs a yes (credential placement, plugin install and restart, worker-host admin)

## Planning agent (outgoing)

- [x] Plan and packet drafts written and verified against current state
- [x] Wave-0 gate for Wave 4–6 packet drafting encoded in plan + index + kickoff prompt
- [x] Branch `docs/dogfood-campaign-plan` @ `7fab87b` pushed (secret-scanned, false positive verified)
- [x] Handoff pack written (RULES, HANDOFF, CAPABILITIES, PROPOSED-STEPS, KICKOFF-PROMPT, CHECKLIST)
- [ ] PR opened (Kyle's call, or the executor opens it after his yes)
- [x] No secrets in the pack (paths and names only)
- [x] Outgoing agent stops here: no further workstreams added

## Incoming coordinator (first session)

- [ ] Read `RULES.md` first, then the pack in order
- [ ] Re-checked live PR heads and CI; did not trust this snapshot
- [ ] Filled `CAPABILITIES.md` from real recon
- [ ] Completed the three kickoff verification actions and reported them
- [ ] Requested the Wave-0 authorization envelope; waited for Kyle's own words
- [ ] Started only the first mission, under the standing bee cap
- [ ] Asked the approver before anything not already quoted in `RULES.md`
