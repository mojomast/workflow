# 07 — Projects

What shipped, in order, with links and outcomes. Dates and times are America/Toronto. This covers mid-October to Nov 12, 2026, the period in the bots' memory; Kyle's earlier repos (listed in [08](08-repositories.md)) predate it, and the earlier Nous catalog PRs (Orbit Desktop, Afterforge, hermes-session-warmer, Sept 2026) are only known from GitHub.

## Timeline

| Date | Project | What happened |
|---|---|---|
| Oct 13–16 | [Orbit Desktop](https://github.com/mojomast/orbitdesktop) | Grok Bot as an agent provider, Grok Bots app (group chats, @mentions, ⚡ Activity, subagent phases), Google Colab app (PR #18), Collab orchestration; deployed from local integration branches with numbered rollbacks; PR #23 parity features merged and deployed Oct 16 |
| Oct 14–16 | Pizza Panic → [CLAWPOCALYPSE NOW](https://github.com/mojomast/clawpocalypse-now) | Built by the asylum group chat from a collaboration board; renamed Oct 15; PRs #1–#9 merged and deployed to [GitHub Pages](https://mojomast.github.io/clawpocalypse-now/) after Kyle's yes |
| Oct 20 | Local workers | Cua + OpenCode bees on Kyle's PC verified; [orbit-control-plane](https://github.com/mojomast/orbit-control-plane) started |
| Oct 20–Nov 3 | [Comfyrizz](https://github.com/mojomast/comfyrizz) | Reliability plan RL01–RL12, character creator, UI overhaul and density, iterative-levels UI waves, UX remediation Waves 0–4 (Opus/Sonnet cloud agents + DeepSeek bees), Easy Studio, hackathon submission (PR #53, merged Oct 28), marketing site `comfy.rizz.click`, ref-watch (PR #70), skills port (#71), judge loop v2 (#72), judge workflow v3 (#73–#75). Squash merges, no tags |
| Oct 28–29 | [comfyrizz-hermes](https://github.com/mojomast/comfyrizz-hermes) | Portable Hermes plugin; catalog [#146230](https://github.com/NousResearch/hermes-agent/pull/146230) merged by Nous |
| Oct 30 | [open-higgsfield-skills](https://github.com/mojomast/open-higgsfield-skills) | 192 hackathon repos distilled into agent-agnostic skills + video-director; demo video funded from a 20 CU budget |
| Nov 2–12 | [hermes-photo-to-part](https://github.com/mojomast/hermes-photo-to-part) (BABA BOOEY) | v0.1.0 → v0.1.22 with real-photo and sealed evals; catalog #148018 (closed to free a slot), then [#153757](https://github.com/NousResearch/hermes-agent/pull/153757); review fixes in v0.1.23 (Nov 12) |
| Nov 2–5 | [hermes-aircraft-doppler-geolocation](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) (DOLAN) | Catalog [#148043](https://github.com/NousResearch/hermes-agent/pull/148043) merged Nov 2; [#148633](https://github.com/NousResearch/hermes-agent/pull/148633) (v0.3.1) merged Nov 5. Kyle's most-starred plugin repo (17 stars at time of writing) |
| Nov 3–10 | [hermes-shortrizz](https://github.com/mojomast/hermes-shortrizz) | v0.2.1 (Nov 4) → v0.5.0 (Nov 9); catalog #148687 closed to free a slot |
| Nov 4–12 | **Eye Of Hermes** ([EOH](https://github.com/mojomast/EOH)) | See [08 §1](08-repositories.md#1-eye-of-hermes). v0.1.0 Nov 4 → v0.2.10 Nov 10; catalog [#149691](https://github.com/NousResearch/hermes-agent/pull/149691) merged Nov 10; hackathon entry #1 (Nov 6) |
| Nov 5–12 | Emurizz (private, Cheese) | SNES/N64 netplay pane; bee waves M0–M3K; PR #5 measured MK64 at 59.9 fps, 0 desyncs; routine paused. See [contrib/cheese.md](../contrib/cheese.md) |
| Nov 6–11 | [poptart](https://github.com/mojomast/poptart) | v0.2.3 → v0.2.5; catalog [#150357](https://github.com/NousResearch/hermes-agent/pull/150357) merged Nov 9; hackathon entry |
| Nov 6–11 | [Hermagotchi](https://github.com/mojomast/hermagotchi) | Hermes Forge submission, Hermes Plugin Builder review fixes to v0.1.3; catalog [#150358](https://github.com/NousResearch/hermes-agent/pull/150358) merged Nov 10; hackathon entry |
| Nov 9–11 | [hyperrizz](https://github.com/mojomast/hyperrizz), [hermes-stitchslop](https://github.com/mojomast/hermes-stitchslop) | Catalog [#151945](https://github.com/NousResearch/hermes-agent/pull/151945) (merged Nov 9) and [#151946](https://github.com/NousResearch/hermes-agent/pull/151946) (merged Nov 10); hackathon entries Nov 9 |
| Nov 9–12 | **Temple of Hermes** ([hermes-templeos](https://github.com/mojomast/hermes-templeos), [temple-of-hermes](https://github.com/mojomast/temple-of-hermes)) | See [08 §2](08-repositories.md#2-temple-of-hermes). Plugin v0.1.0 → v0.2.2, OS v0.1.2 → v0.1.3, BBS live; catalog [#153852](https://github.com/NousResearch/hermes-agent/pull/153852) open; hackathon entry Nov 11 |
| Nov 9 | [hermes-buffrizz](https://github.com/mojomast/hermes-buffrizz) (hammy) | Freebuff CLI in a Hermes pane; v0.1.0 released and deployed to moltussy-1; no catalog PR |
| Nov 9–11 | **assetrizz** ([assetrizz](https://github.com/mojomast/assetrizz), [assetrizz-hermes](https://github.com/mojomast/assetrizz-hermes)) | See [08 §3](08-repositories.md#3-assetrizz). 14,641 assets overnight; plugin v0.1.0 → v0.2.0; catalog [#152771](https://github.com/NousResearch/hermes-agent/pull/152771) merged Nov 11; hackathon entry |
| Nov 10–11 | [hermes-plugin-dev](https://github.com/mojomast/hermes-plugin-dev) | The plugin-building skill + scaffold/lint plugin; v0.3.0 → v0.3.1; catalog [#152699](https://github.com/NousResearch/hermes-agent/pull/152699) merged Nov 11; hackathon entry |
| Nov 11–12 | [bundlebees](https://github.com/mojomast/bundlebees) | The bees workflow as a Hermes plugin, built by 4 bees in two waves; v0.1.0 → v0.1.1 after a 7-blocker review; catalog [#153888](https://github.com/NousResearch/hermes-agent/pull/153888) open; hackathon entry #10 |
| Nov 11–12 | [hermes-hackathon-showcase](https://github.com/mojomast/hermes-hackathon-showcase) | Asset pack and static site for the ten entries; deployment prompt for `hermes.rizz.click` |
| Nov 11–12 | Catalog descriptions | Description-only PRs [#154158](https://github.com/NousResearch/hermes-agent/pull/154158) (EOH) and [#154159](https://github.com/NousResearch/hermes-agent/pull/154159) (hyperrizz) with banners, merged Nov 12 |

## Nous Hermes Agent Plugin Hackathon — ten entries

| # | Entry | Submitted | Catalog PR | Status (Nov 12) |
|---|---|---|---|---|
| 1 | Eye Of Hermes | Nov 6 | #149691 | Merged |
| 2 | poptart | Nov 6 | #150357 | Merged |
| 3 | Hermagotchi | by Nov 9 | #150358 | Merged |
| 4 | hyperrizz | Nov 9 | #151945 | Merged |
| 5 | stitchslop | Nov 9 | #151946 | Merged |
| 6 | Hermes Plugin Dev | Nov 10 | #152699 | Merged |
| 7 | assetrizz | Nov 10 | #152771 | Merged |
| 8 | photo-to-part | Nov 11 | #153757 | Open (review fixed, v0.1.23) |
| 9 | TempleOS for Hermes | Nov 11 | #153852 | Open (v0.2.2) |
| 10 | bundlebees | Nov 11 | #153888 | Open (review fixed, v0.1.1) |

Submissions closed Nov 11; judging was in progress as of Nov 12.
