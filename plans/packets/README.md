# plans/packets/ — Wave-4 feature packets (F15–F19)

The `F<NN>` feature packets of the rizzstack dogfood campaign
(`plans/rizzstack-dogfood-campaign.md` on the recovered branch; the
dogfood-plan-recovery archive under `~/.hermes/plugin-data/bundlebees/campaigns/`
holds the recovered plan and the F1–F10 packets). The F11–F14 drafts of this
same wave live on the `docs/wave4-packets` branch of the origin repository and
are not repeated here. This directory carries the wave's networking-and-worker-
deploy slices, scoped from docs/14:

| Packet | Title | Repository | Source design |
|---|---|---|---|
| [F15](F15-relay.md) | Coordinator-hosted relay as the product default | mojomast/orbitdesktop | docs/14 §Recommendation, §Why this default |
| [F16](F16-tailcat.md) | tailcat as the default zero-account NAT fallback | mojomast/orbitdesktop | docs/14 §What tailcat is |
| [F17](F17-join-probing.md) | One-liner join command probing transports in a fixed order | mojomast/orbitdesktop | docs/14 §Worker deploy sketch |
| [F18](F18-revocable-tokens.md) | Immediate worker-credential revocation in the Orbit Workers list | mojomast/orbitdesktop | docs/14 §How to revoke a worker |
| [F19](F19-live-host-join-install.md) | Live-host join install, rehearsed on a throwaway target first | mojomast/orbitdesktop | docs/14 §Worker deploy sketch; docs/17 §SSH hosts |

A packet is evidence and identity, never authority (docs/25): drafting one
authorizes nothing. Every packet carries the F1–F10 packet shape:

1. `## Intent` — the outcome and why it matters;
2. `## Delivered and remaining` — what is already delivered vs what remains;
3. `## Acceptance criteria` — `AC-NNN <observable behavior> -> proven by <path::test>`;
4. `## Dependencies` — other packets, PRs and chapters it depends on;
5. `## Authorization needs` — the approver, the human gates and what is not authorized;
6. `## Next executable action` — exactly one, the first thing to do.

## The protocol pin

Every packet in this directory carries a `- workflow_ref:` line in its header:
the full 40-hex commit of the workflow protocol the packet was validated
against. This delivery pins
`d4e6c504884fbf64c86c18033b59484137614646`, the lease base of this campaign.
That commit exists on the origin repository's `main` and carries the enforced
`feature-packet` and `source-resolution` schemas byte for byte, so the
validator's drift guard (`validator_mismatch`) cannot fire against it. A pin
that exists only inside a disposable worker sandbox is forbidden: once the
sandbox dies, the pin is unverifiable and every packet carrying it fails with
`workflow_ref_unknown` outside that sandbox. Before shipping, reachability is
proven against a fresh clone of the origin repository, not against the working
copy.

Validation:

```bash
python3 -m pytest tests/test_f15_f19_packets.py -q   # the five packets above
python3 -m pytest tests/test_wave4_packets.py -q     # discovery over plans/packets/
```

`tests/test_wave4_packets.py` discovers every wave-4 packet under this
directory and validates shape, cross-references and the README index; it skips
with a stated reason when this checkout carries no wave-4 packets at all.

Note: this checkout does not contain the recovered plan branch or the archive,
so the Wave-4 scope above was reconstructed from the in-repo chapters
(docs/05, docs/13, docs/14, docs/15, docs/17, ROADMAP) plus the 2026-11-16
handoff notes. Each packet records that in its provenance header. Sequencing
inside the wave is the packets' own judgement: F15 first (relay and pairing),
F16 and F17 against it, F18 with the relay, F19 last because it rehearses the
other four.
