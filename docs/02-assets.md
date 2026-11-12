# 02 — Assets

Assets covers game art, the assetrizz library, catalog banners and screenshots, promo video, and voice. The rules came from Kyle directly and were applied to every project.

## 1. Rules for assets

| Rule | Source / where it came from |
|---|---|
| Game assets must be **original**: no real people, no logos, no trademarked or copyrighted characters | Kyle's standing rule; written into the assetrizz license field on every row ("original, generated for Kyle Durepos") |
| Assets need **documented provenance**, a **reproducible generation workflow** and an **authoritative rig source of truth** | Kyle, Oct 15 (CLAWPOCALYPSE NOW art work) |
| Visual before/after evidence goes in **new evidence directories**, never overwriting older ones | Kyle, Oct 15 |
| Kyle dislikes "slop"-style graphics: no generic neon-cyan HUD, soft glows, gradients-as-decoration, polka-dot backgrounds | The EOH promo restyle brief and the "no polka dots, premium style" showcase film |
| Hermes and EOH screenshots are always **dark mode**, shot on a fresh map area with Hermes driving the feature | Kyle, Nov 5; repeated in the hackathon submission brief |
| Terry (TempleOS companion) uses the **2017 cap look only**; never the early mustache-era photos | Kyle, Nov 9 |
| Voice cloning is forbidden | Comfyrizz voice decision Q4 (Oct 22) |
| Catalog images: banner at 2:1 (1200×600), at most 6 screenshots, all on raw.githubusercontent.com pinned to the same commit as the catalog `sha` | Nous catalog rules; the validator refuses a 7th screenshot |

## 2. Game art (Pizza Panic → AGENT ARMEGEDDON: CLAWPOCALYPSE NOW)

- In mid-October the agents in the Orbit group chat "THE INSANE ASSYLYM" built a browser beat-'em-up, first called Pizza Panic, renamed on Oct 15 to **AGENT ARMEGEDDON: CLAWPOCALYPSE NOW** ([mojomast/clawpocalypse-now](https://github.com/mojomast/clawpocalypse-now), live on [GitHub Pages](https://mojomast.github.io/clawpocalypse-now/)).
- Kyle asked the agents to use image generation for sprites, backgrounds and effects, and later for much bigger character sprites, a polished title sequence and longer levels.
- The Teknium and TurboFit fighters were based on rigged 3D models from the public `123mikeyd/Nous_Research_Cinematic_Universe` repo (release `rigged-models-v1`). The TurboFit rig rebuild was handed to a Gemini cloud agent on Cursor that was allowed to generate missing art and stacked its PR on PR #6.
- The repo carries rig/review tooling and pixel tests (`npm run test:pixels`, Playwright browser tests, a level-layout smoke test).

## 3. The assetrizz library (Nov 9–10)

A one-night run produced **14,641 original 2D game assets in 23 style packs and 18 categories**, now public at [mojomast/assetrizz](https://github.com/mojomast/assetrizz). Full build history in [08 Repositories](08-repositories.md#3-assetrizz). The method, from its README and `RESEARCH.md`:

- **Style-locking.** Each pack (`pixel_16bit`, `hand_painted_fantasy`, `dark_scifi`, `stained_glass`, `monochrome_1bit` …) locks a style prefix, palette, light direction, sizes and a `#FF00FF` chroma key. The image tool has no seed, so consistency comes from the locked prefix, palette snapping and sheet generation.
- **Sheets, then slicing.** Small items are generated as 4×4 sheets and larger ones as 2×2, so related assets share lighting and line weight; tiles, backgrounds and buildings stay singles.
- **Post-processing.** Alpha from the chroma key, pixel snap, thumbnails, palette, de-duplication; QA failures go to `rejected/` but stay catalogued.
- **Index.** SQLite (WAL) with FTS5, a `manifest.jsonl`, a CLI (`query.py`) and a read-only local HTTP search.
- **Parallel generation.** Workers each own a shard (`batch_index % shards == N`) with 30-minute leases reclaimed if a worker dies. The run went from 4 to 8 to 12 shards. The final snapshot shows 12 shards, 14,639 ingested and 132 rejected.
- **Milestones.** An overnight keeper routine announced the 1,000- and 2,000-asset milestones with contact sheets and recorded them in `milestones.json` so they were not re-announced.

## 4. Banners, screenshots and README art

- Each Hermes plugin got a 2:1 README/catalog banner and dark-mode screenshots. Banner URLs in catalog entries are pinned to the entry's commit; adding a banner to an already-listed plugin is a catalog PR that only changes the YAML (done for EOH and hyperrizz in #154158 and #154159).
- Screenshot sets were captured as before/after pairs at 1080p for UI work (Comfyrizz overnight UI waves had matching "before" and "after" executor runs).
- The EOH README was refreshed with new-feature screenshots by a Cursor cloud agent (EOH PR #17), then branded Public SDR shots (PR #28).

## 5. Video

| Tool | Used for | Notes |
|---|---|---|
| **Remotion** (CPU, local) | Comfyrizz explainers; the Hermes hackathon showcase film; the "Hermes BIP EP1" building-in-public film | Deterministic: frame = f(timeline, local assets, frame number); zero Google Colab spend for CPU films |
| **Google Colab GPU** (ComfyUI with FLUX 3 Klein stills, LTX-2.5 image-to-video plates) | Comfyrizz hero film plates, real Easy-mode demo, open-higgsfield-skills demo and parody video | Every run had a CU cap set by Kyle; sessions torn down and spend recorded (e.g. Δ1.01 CU, Δ0.57 CU, Δ1.88 CU) |
| **HyperFrames** | EOH hackathon promo (`promo/hyperframes/`), hyperrizz skill films | EOH promo restyle brief demanded a `STYLE.md` and key-frame stills before the full render |
| Shortrizz | Long video in, captioned 9:16 shorts out (Whisper, LLM picks, face-tracked reframe) | Kyle's defaults: tighten pauses, AI edit pass, hook text, loudness evening; music/B-roll/split-screen off |

**Hackathon demo spec** (from the submission brief): under 90 seconds (aim 80–88), H.264 yuv420p 1080p30 with AAC, faststart, about −16 LUFS, under 512 MB; never alter original files; video plugins open on a finished hero frame.

## 6. Voice

- Comfyrizz: use a video model's built-in voice when available (MiniMax), else Kokoro TTS on CPU; an opt-in MiniMax "no-clip" voice description mode was planned (VX01–VX12). Later Chatterbox voiceover was approved for porting from open-higgsfield-skills.
- EOH promo: voiced with Grok's own TTS using the voice Ash, with each scene's prompt finishing typing in a mock Hermes terminal before the map moves.
- Kyle asked for more natural voices on Comfyrizz demos (Oct 30).

## 7. Where assets live

Finished deliverables live in the repos (`docs/`, `film/delivery/`, `site/assets/`) or as release assets. Working files lived under `/workspace/<project>` on the box; large scratch (raw downloads, old builds, voice-tool environments) was periodically deleted with Kyle's OK to keep the shared disk under control.

## 8. Creative handoffs from Codex

Comfyrizz's selected double-Z concept traveled as a brand pack with source references, variants, tokens, prompts, a preview and a refinement brief; the implementation agent made the SVG masters. Terry's HD animation pack traveled with editable parts, rig and pose data, validation, previews and six silent runtime exports. All six exports were matched by Git blob hash to the plugin repository on Nov 12. See [the contribution and evidence](../contrib/codex.md).

The reusable [asset pack contract](../templates/ASSET-PACK.md) keeps the approved reference, editable source, runtime export and preview distinct. It requires target-runtime compatibility to be checked separately from file integrity. The original-game-asset rule above and the Terry tribute's specific quote/voice policy remain separate scopes.
