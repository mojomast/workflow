# plans/packets/ — Wave-4 feature packets

The `F<NN>` feature packets of the rizzstack dogfood campaign
(`plans/rizzstack-dogfood-campaign.md` on the recovered branch; the
dogfood-plan-recovery archive under `~/.hermes/plugin-data/bundlebees/campaigns/`
holds the recovered plan and the F1–F10 packets). The Wave-0 RETURN was
delivered by the 2026-11-16 acceptance run, which unblocked drafting Wave 4;
this directory carries those four drafts:

| Packet | Title | Repository | Source PR / design |
|---|---|---|---|
| [F11](F11-runnable-by-anyone.md) | Runnable-by-anyone follow-ups on Orbit | mojomast/orbitdesktop | Orbit #25 (merged) leftovers; docs/15 |
| [F12](F12-connect-github-repo-picker.md) | Connect-GitHub and the repository picker | mojomast/orbitdesktop | Orbit #27 (open) — spec of what that PR must deliver |
| [F13](F13-bifrost-optin-router.md) | Bifrost opt-in router via a Compose profile | mojomast/orbitdesktop | docs/17 §Token router |
| [F14](F14-acdd-evidence-wiring.md) | Wire the ACDD evidence view into the board, feed and a live smoke | mojomast/orbitdesktop | Orbit #26/#30 (merged); docs/16 §9–10 |

A packet is evidence and identity, never authority (docs/25): drafting one
authorizes nothing. Every packet carries the F1–F10 packet shape:

1. `## Intent` — the outcome and why it matters;
2. `## Delivered and remaining` — what is already delivered vs what remains;
3. `## Acceptance criteria` — `AC-NNN <observable behavior> -> proven by <path::test>`;
4. `## Dependencies` — other packets, PRs and chapters it depends on;
5. `## Authorization needs` — the approver, the human gates and what is not authorized;
6. `## Next executable action` — exactly one, the first thing to do.

Dispatch requires an `acdd/1` contract frozen at the authorized revision
(docs/16, docs/19) and a sealed authorization; the packets here are the
campaign-plan layer above that.

Validation: `python3 -m pytest tests/test_wave4_packets.py -q` parses all four
packets and checks the shape, the cross-references and the README index.

Note: this checkout does not contain the recovered plan branch or the archive,
so the Wave-4 scope above was reconstructed from the in-repo chapters
(docs/15, docs/16, docs/17, ROADMAP) plus the 2026-11-16 handoff notes
(Orbit #25/#26/#30 merged, #27 open). Each packet records that in its
provenance header, and F11's first executable action is to verify the
delivered-vs-remaining split against the merged #25 diff before any contract
is frozen.
