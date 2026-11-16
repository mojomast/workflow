# plans/packets/ — Wave-4 feature packets

The `F<NN>` feature packets of the rizzstack dogfood campaign
(`plans/rizzstack-dogfood-campaign.md` on the recovered branch; the
dogfood-plan-recovery archive under `~/.hermes/plugin-data/bundlebees/campaigns/`
holds the recovered plan and the F1–F10 packets). The Wave-0 RETURN was
delivered by the 2026-11-16 acceptance run, which unblocked drafting Wave 4;
this directory carries those four drafts and the five-packet F15–F19
reconstruction wave:

| Packet | Title | Repository | Source PR / design |
|---|---|---|---|
| [F11](F11-runnable-by-anyone.md) | Runnable-by-anyone follow-ups on Orbit | mojomast/orbitdesktop | Orbit #25 (merged) leftovers; docs/15 |
| [F12](F12-connect-github-repo-picker.md) | Connect-GitHub and the repository picker | mojomast/orbitdesktop | Orbit #27 (open) — spec of what that PR must deliver |
| [F13](F13-bifrost-optin-router.md) | Bifrost opt-in router via a Compose profile | mojomast/orbitdesktop | docs/17 §Token router |
| [F14](F14-acdd-evidence-wiring.md) | Wire the ACDD evidence view into the board, feed and a live smoke | mojomast/orbitdesktop | Orbit #26/#30 (merged); docs/16 §9–10 |
| [F15](F15-relay.md) | Coordinator-hosted relay as the product default | mojomast/orbitdesktop | docs/14 §Recommendation / §Why this default |
| [F16](F16-tailcat.md) | tailcat as the default zero-account NAT fallback | mojomast/orbitdesktop | docs/14 §What tailcat is / §Fit for this workflow |
| [F17](F17-join-probing.md) | One-liner join command that probes transports in a fixed order | mojomast/orbitdesktop | docs/14 §Worker deploy sketch; ROADMAP §hyvv repo |
| [F18](F18-revocable-tokens.md) | Immediate worker-credential revocation in the Orbit Workers list | mojomast/orbitdesktop | docs/14 §How to revoke a worker; docs/06 (open-relay lesson) |
| [F19](F19-live-host-join-install.md) | Live-host join install, rehearsed on a throwaway target first | mojomast/orbitdesktop | docs/14 §Worker deploy sketch / §How to revoke; docs/17 §SSH hosts |

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

Protocol pins: every packet's `workflow_ref` must be the full 40-hex SHA of
the campaign's workflow lease base, `d4e6c504884fbf64c86c18033b59484137614646`
— a commit on the origin repository's main that carries the enforced
feature-packet and source-resolution schemas byte for byte. A pin that exists
only inside a disposable worker sandbox is forbidden: the origin remote
refuses it, no coordinator checkout has it, and official verify fails every
packet carrying it with `workflow_ref_unknown`. The F15–F19 packets pin
exactly that commit; `tests/test_f15_f19_packets.py` enforces the pin
equality, checks reachability and the schema drift guard against real history
(where the checkout has none, that check skips with a stated reason and
reachability must be proven against a fresh clone of the origin repository
before shipping), and validates the dependency graph (F15 is the wave's
foundation; F16 ← F15; F17 ← F15, F16; F18 ← F15; F19 ← F15, F17, F18).

Validation: `python3 -m pytest tests/test_wave4_packets.py -q` parses the
four F11–F14 packets and checks the shape, the cross-references and the
README index; `python3 -m pytest tests/test_f15_f19_packets.py -q` parses
the five F15–F19 packets, their pins, provenance and dependency graph. The
directory carries exactly these nine campaign packets plus this README —
nothing else.

Note: this checkout does not contain the recovered plan branch or the archive,
so the Wave-4 scope above was reconstructed from the in-repo chapters
(docs/15, docs/16, docs/17, ROADMAP) plus the 2026-11-16 handoff notes
(Orbit #25/#26/#30 merged, #27 open), and the F15–F19 scope from
docs/14-networking-and-worker-deploy.md plus the same handoff notes. Each
packet records that in its provenance header, and F11's first executable
action is to verify the delivered-vs-remaining split against the merged #25
diff before any contract is frozen.
