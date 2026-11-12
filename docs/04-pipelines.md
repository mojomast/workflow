# 04 — Pipelines

Each pipeline we used or built, with its inputs, tools, outputs and where it lives. "Built" means we wrote it; "used" means we ran someone else's tool inside our flow.

## Summary

| Pipeline | Built / used | Input → output | Lives in |
|---|---|---|---|
| Bees (leased coding workers) | Built | Brief JSON → verified commit on a feature branch | orbitdesktop `pc-launcher/` + `docs/LOCAL_WORKERS.md`; per-project `orch.py`/`verify.sh` on the box; packaged as [bundlebees](https://github.com/mojomast/bundlebees) |
| Hermes plugin zero → listed | Built (as a skill) | Idea → released plugin + catalog entry | `hermes-plugin-development` skill; [hermes-plugin-dev](https://github.com/mojomast/hermes-plugin-dev) |
| Catalog review-fix cycle | Built (as a practice) | Maintainer review → fix PR, patch release, repin, reply | Same skill, `references/catalog-review-lessons.md` |
| Hackathon submission | Built (as a brief) | Released plugin → X post draft, demo video, Typeform | `prompts/nous-hackathon-submission.md` on the box |
| Comfyrizz film pipeline | Built | Chat brief → narrated motion-graphics MP4 | [comfyrizz](https://github.com/mojomast/comfyrizz) |
| Google Colab GPU jobs | Used (Google's `colab` CLI) + built wrappers | Hashed `jobs.json` → generated stills/plates + manifest | Comfyrizz `pipeline-py`; Orbit Google Colab app |
| Ref-watch / judge loop | Built | Generated stills/clips → judged, re-prompted, regenerated | Comfyrizz (PRs #70–#75) |
| Remotion CPU films | Used + built templates | Timeline + local assets → MP4 at 0 Google Colab CU | Comfyrizz `apps/renderer`, `examples/` |
| HyperFrames promos | Used | HTML/CSS motion scenes + VO → MP4 | EOH `promo/hyperframes/`; [hyperrizz](https://github.com/mojomast/hyperrizz) skill |
| video-director skills | Built | One prompt → video via open-weights ComfyUI workflows | [open-higgsfield-skills](https://github.com/mojomast/open-higgsfield-skills) |
| Shortrizz clipper | Built | Long video → captioned 9:16 shorts | [hermes-shortrizz](https://github.com/mojomast/hermes-shortrizz) |
| Game-asset generation | Built | Style packs × taxonomy → 14,641 catalogued PNGs | [assetrizz](https://github.com/mojomast/assetrizz) `pipeline/` |
| photo-to-part evals | Built | Real photos + sealed evals → scored rounds per release | [hermes-photo-to-part](https://github.com/mojomast/hermes-photo-to-part) |
| Temple of Hermes ISO / disk | Built | HolyC sources → verified ISO + qcow2 + SHA256SUMS | [temple-of-hermes](https://github.com/mojomast/temple-of-hermes) releases |
| Deploy with rollback | Built (as a practice + scripts) | Approved tag → running on a host, with backup and `ROLLBACK.sh` | Skill §10; Hermes Forge deploy scripts |
| Independent review and correction | Used as a practice | Pinned revision + report → reproduction, fix brief, revised evidence | [Codex/DOLAN case](../examples/doppler-review-handoff.md); [common loop](09-reproducible-collaboration.md) |
| Creative pack handoff | Used as a practice | Selected direction → editable source + exports + preview + integration brief | [Comfyrizz and Terry cases](../contrib/codex.md); [pack template](../templates/ASSET-PACK.md) |

## 1. Bees

See [03 §4](03-development-and-orchestration.md#4-deepseek-bees-cua-sandboxes-on-kyles-pc). The plugin-side verifier hardening that now lives on bundlebees `main` (untagged) is in [13](13-bundlebees-hardening.md). Planned remote-worker join (pairing, tailcat, a public URL) is in [14](14-networking-and-worker-deploy.md). Inputs: a brief per `brief.schema.json` (objective, project, branch/source rev, `assigned_files`, commands, acceptance, budget, deps). Tools: Orbit local-workers adapter, PC launcher, Cua sandbox, OpenCode with `deepseek-v4.1-flash`. Output: result manifest → `verify.sh` → commit on the feature branch → board card moved to done.

## 2. Hermes plugin zero → listed

From the skill's checklist: scaffold (`plugin.yaml` manifest v2 + `register(ctx)`) → lean composable tools with an `op` enum, measured in o200k tokens → optional skills, dashboard tab, Desktop pane (`@hermes/plugin-sdk`, SandboxedFrame) → truthful `requires_env` / capabilities → unit tests with a fake ctx + strict duplicate-key YAML test → `hermes plugins doctor . --ci` and `hermes plugins validate . --install-deps` → README with tool table, disclosure and Hermes version tested → secret scan → authorized tag/release → YAML-only catalog PR → authorized deploy on a real host. The skill's `hpd_check` adds a non-executing security preflight (path/line/rule findings only). Schema sizes we shipped ranged from 547 o200k (Buffrizz, 3 tools) to 8,063 (EOH after audits).

## 3. Catalog review-fix cycle

Review lands → list blockers for Kyle → after yes: fix PR in the plugin repo with tests → merge → patch tag + release → smoke test on a real Hermes → repin the same catalog PR (YAML-only, new SHA, images on the same SHA) → validator → point-by-point reply mapping each finding to files, commits and test evidence. Run on: EOH (v0.2.7, v0.2.9, v0.2.10), Hermagotchi v0.1.3, stitchslop v0.2.2, poptart v0.2.5, assetrizz-hermes v0.1.1, hermes-plugin-dev v0.3.1, hermes-templeos v0.2.2, photo-to-part v0.1.23, bundlebees v0.1.1.

## 4. Hackathon submission (Nous Hermes Agent Plugin Hackathon, Nov 2026)

Requirements: open catalog PR; X post under 90 s tagging @NousResearch; Typeform. Steps: confirm the catalog PR pins the latest release → make or locate the demo video (spec in [02 §5](02-assets.md#5-video)) → draft the post (hook, what it does, "Built for the @NousResearch Hermes plugin hackathon.", repo link, ≤280 chars) as a draft card → Kyle attaches the video and posts → fill the Typeform in the box browser, stop before Submit, screenshot → submit on Kyle's yes. Ten entries went through it between Nov 6 and Nov 11 (see [07](07-projects.md)).

## 5. Comfyrizz film pipeline

From the [comfyrizz README](https://github.com/mojomast/comfyrizz): "Chat in a brief. Get a narrated motion-graphics explainer."
- **Agent** (`packages/agent`): bounded tool loop (storyboard propose/edit, asset routing, SVG generation, image generation, sketch-to-render) with zod-validated tools and up to two repairs. GPU work is only planned; it runs after a spend card is approved.
- **Package as contract** (`packages/schema`): JSON Schema plus TS and Python validators.
- **Jobs** (`packages/jobs`): ordered, hashed `jobs.json` (stills before plates; LTX sizes in multiples of 64 and 8n+1 frames).
- **GPU pipeline** (`pipeline-py`): submits jobs with the Comfy SDK to Google Colab (G4) or your own ComfyUI; writes an attempt record before each submit; an atomic `out/manifest.json` is the only proof of success; lost submissions are reconciled, never blindly resubmitted.
- **Models**: FLUX 3 Klein stills (kept for the Open Source Higgsfield hackathon's open-weights rule), LTX-2.5 plates, Kokoro narration.
- **Timeline** (`packages/planner`) → **render** (`apps/renderer`, Remotion, five layout families) → rights-aware export with `CREDITS.md`.
- Built through many waves of bees and cloud agents (reliability RL01–RL12, UI overhaul, UX remediation Waves 0–4, planning stress, hackathon submission), merged to main by squash with no tags.

## 6. Google Colab GPU jobs

Google's `colab` CLI provisions a runtime (G4 used most), runs a job, retrieves outputs and tears down. Our wrappers add a watchdog, a budget formula and `stop_unconfirmed` reporting, verified against `colab sessions`. Every run had a CU cap from Kyle and spend was logged per run (e.g. the meta hero film: Δ1.01 CU, then Δ0.57; real Easy-mode demo: Δ1.88). One HF Hub 429 led to the rule "one deliberate retry, no unattended retries".

## 7. Ref-watch and the judge loop

Plan approved Oct 30: a vision model (Pi via deepseek-v4.1-flash vision) judges generated stills against the reference; caps of 2 regenerations per still and at most 6 jobs or 25% of stills. Calibrated live on Google Colab (0/15 false passes, 1/13 false holds) before merging (PR #70, default off). Judge v2 added fix verification, scene continuity, clip review and audio QA (PR #72). Judge workflow v3 (voiceover first, all stills judged in one pass) needed several capped reruns before PRs #73–#75; after one live check Kyle asked that fixes be made offline against saved clips, with no new spend without asking.

## 8. Remotion CPU films and HyperFrames promos

- Remotion: deterministic, local, zero GPU. Used for the Hermes hackathon showcase film (41 s, 1080p; stats from a JSON of commits and code lines) and the "Hermes BIP EP1" building-in-public film.
- HyperFrames: EOH promo (`promo/hyperframes/`: index.html, style.css, motion scripts, captions), with real map-pane footage and the Ash voiceover; the restyle PR (#23) is still open. hyperrizz is the skill for "distinctive HyperFrames films".

## 9. open-higgsfield-skills / video-director

Built by ComfyUI Agentic Research from 192 Open Source Higgsfield hackathon repos (plus newer sources) into agent-agnostic Agent Skills, one per capability, culminating in a `video-director` orchestrator that can package jobs for Google Colab. Public with a demo video in the README; Comfyrizz later ported last-frame chaining, Qwen Image Edit fixes, Chatterbox voiceover and BiRefNet cutouts from it.

## 10. Shortrizz

Long video → Whisper transcript → LLM picks → face-tracked 9:16 reframe → captions. Kyle's defaults: tighten pauses, AI edit pass, hook text, loudness evening, captions clear of app buttons; music, B-roll and split-screen off; optional cold open, Kokoro narrator, punch-ins, loop endings. Later releases split select → picks → render and added a Desktop preview pane (needs Hermes ≥ 0.23.0).

## 11. Game-asset generation (assetrizz)

See [02 §3](02-assets.md#3-the-assetrizz-library-nov-910) and [08 §3](08-repositories.md#3-assetrizz). Inputs: `style_packs.json`, `taxonomy.json`, `specs.jsonl`, `prompts.jsonl`. Tools: the image generation tool, Pillow post-processing, SQLite FTS5. Workers: `nice -n 15 python3 worker.py --shard N --shards K` (claim, prompt, ingest). Append-only scripts add new styles and categories to a live queue without touching existing rows.

## 12. photo-to-part evals

Per release: unit tests (54 at v0.1.2 → 248 at v0.1.22), real-photo rounds r2–r16 scored pass/partial/fail with turn-cap hits, sealed Hermes evals and in-process evals; doctor confirms registration. Details in [contrib/baba-booey.md](../contrib/baba-booey.md).

## 13. Temple of Hermes ISO and disk

Guest work by bees (QEMU only in PC sandboxes or on the Hermes host, never on the box), PIL-only screenshot acceptance (640×480, ≤16 colours, VGA palette), release artifacts with `SHA256SUMS`; v0.1.3 verified 20/20 boots plus persistence. Details in [08 §2](08-repositories.md#2-temple-of-hermes).

## 14. Deploy with rollback

Dirty-tree abort → timestamped backup (prior SHA, git bundle, copies, doctor snapshot, `ROLLBACK.sh`) → check out the approved tag → `systemctl --user restart` of the Hermes dashboard and gateway → verify (units active, doctor tool count, `/api/health` 200, deployed pane bundle hash equals the tag's) → report backup path and rollback command → ask Kyle to Rescan plugins in Hermes Desktop. Hermes Forge was asked on Nov 12 to turn this into a one-command, dry-run-by-default script.
