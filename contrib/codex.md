# Codex collaboration with Kyle

Writer: Codex, reconstructed from the accessible collaboration record.

As of: 12 November 2026, America/Toronto.

Scope: Comfyrizz, aircraft Doppler geolocation, Emurizz planning, and Terry artwork and animation. This account adds the research, review and creative-production work that fed the builders' accounts; it does not claim their implementation or release work.

## What this collaboration contributes

Kyle brings a goal, reference or another agent's report. In these sessions we research the options, inspect the actual project, make an artifact or a specific review, and package the next action for another agent. Kyle chooses the direction and carries the handoff between conversations. The builder implements; results come back for another review. Sometimes the deliverable is already usable artwork, rather than instructions to build something.

The recurring contribution is a portable decision plus evidence: a revised spec, an asset pack, a reproduction of a bug, or a brief tied to a particular commit. The tools differ between projects; that pattern is transferable.

## Comfyrizz from assessment to brand handoff

In **Assess Comfyrizz repository** (21 October), Kyle requested a candid source review, returned after more commits had landed, asked about hackathon fit, and then requested four logo concepts. He selected the third, the kinetic double-Z, and asked for a pack to give the implementation agent.

The delivered pack contained the selected reference, light/dark/monochrome variants, a standalone symbol, social artwork, palette tokens, generation prompts, a preview and an agent brief. The PNGs were explicitly working references; the brief asked the implementer to create consistent editable SVG masters.

The current public [brand guide](https://github.com/mojomast/comfyrizz/blob/f5585b97a671808070c98859094a0ec99858dcff/brand/README.md) describes hand-built vector masters derived from the approved concept and source tokens. This corroborates the handoff's destination without attributing the SVG implementation to this session.

The source review also changed when the code changed: findings from an earlier revision were checked again instead of repeated as current defects. Product advice focused the demonstration on one complete user journey with a precise edit and export. The [current README](https://github.com/mojomast/comfyrizz/blob/f5585b97a671808070c98859094a0ec99858dcff/README.md) documents the film-and-retake demo and its disclosed edits.

**Transferable method:** inspect the product, offer concrete alternatives, let Kyle select, preserve that selection in a pack, and state exactly what the receiving agent must refine. A concept, a production master and an integrated UI are three different acceptance states.

## Doppler review that changed the implementation

In **Analyze and improve efficiency** (3 November), the initial source review at `1d06ae614fe7ce2935808dd5ae426e6adb586f25` identified repeated numerical work, detection reuse and memory opportunities. Kyle requested a prompt for the building bot. The handoff named files, invariants, benchmark requirements and held-out evaluation limits.

DOLAN implemented an efficiency branch and returned timing and equivalence claims through Kyle. Review of the first report found two concrete problems:

1. A vectorized broadband recurrence accumulated float32 scores where the previous implementation accumulated float64. A near-tie synthetic input selected a different ridge.
2. A matching cache entry with incomplete contents could pass validation and then crash, rather than trigger recomputation.

The follow-up brief included reproductions and required regression tests. [PR #5](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/5), final head `1fd0bee10bf4516661d12bca13aec86b3e50b4a9`, records both fixes and documentation corrections. Its revised report gives **2,073 → 746 seconds, about 2.8×**, across seven tuning clips, with zero observed output differences in that comparison. These are the builder's reported measurements, not an independent full-pipeline rerun by Codex. Held-out equivalence remained unverified; the warm-cache measurements predated the review fixes.

The first report's **2,279 → 960 seconds** and a small event discrepancy describe an earlier run. Combining that timing with the final exact-equivalence result would mix revisions. The isolated detrending benchmark and full-pipeline timings also answer different questions.

**Transferable method:** request the base and head, reproduce suspicious behavior narrowly, return a testable finding, and update the claim after the fix. Faster execution passes only if the required outputs still agree. See the [worked handoff](../examples/doppler-review-handoff.md).

## Emurizz correcting the plan before implementation

In **Plan retro emulator plugin MVP** (5 November), the first proposal chose host-streamed play. Kyle clarified that he wanted real netplay, then selected SNES and N64. The revised `SPEC.md` and `DEVPLAN.md` replaced streaming with local emulation and synchronized inputs, separated engine feasibility from in-pane presentation, and defined L0/L1/L2 completion levels. The documents were delivered together as a ZIP.

[Cheese's account](cheese.md) independently describes revision 2, the same completion levels and the subsequent implementation work. It also records Kyle's later four-player N64 override. The locally retained revision 2 still says two players, so it is historical input, not today's authoritative specification. The private Emurizz repository was inaccessible in this review; its latest implementation was not audited.

**Transferable method:** preserve the user's intended experience when choosing an easier architecture. If a requirement changes, update the spec, dependent tasks and acceptance gates together. A native-window prototype is not evidence that gameplay is embedded in the pane.

## Terry from artwork to integrated animation

In **Create Terry companion artwork** (9–11 November), Kyle iterated on appearance, resolution, scene variety, smoking, arm movement and typing. The production exposed real failures: one composition overlaid a second arm, and later arm motion needed a better rig. Those failures led to corrected artwork, continuous sleeve deformation, hand/prop attachment checks and a two-handed keyboard loop.

The final HD typing pack included editable parts, `rig.json`, pose data, the renderer, `RIGGING.md`, `VALIDATION.json`, previews and six silent transparent VP9 loops. It documented its limits: whole-hand images rather than articulated fingers, a front-facing 2D approximation, and incompatibility with the original small atlas format without integration work.

On 12 November, all six local export Git blob hashes matched the files in [hermes-templeos at `0e3167e`](https://github.com/mojomast/hermes-templeos/tree/0e3167ea8014e7187fdf86d2a4f973bc0f0d18ea/desktop/assets/companion/terry/v5/exports):

| File | Git blob SHA |
|---|---|
| `idle.webm` | `a00c43c2d5d7f9d3e9ed29b9260985eb20665b2a` |
| `smoking.webm` | `0c2dd5c6db000b1d65bd83b844b6e7fa77e4d383` |
| `speaking.webm` | `07455317fc3a93845771f18a9adf2bfba74fd7e2` |
| `typing.webm` | `c38143d6f10433c45f1674eba8d5f8f4e15b2919` |
| `walk.webm` | `ee184469d588ce4c7f30ee67a3b4f9ef598ce2c8` |
| `wave.webm` | `7080139046987ef0bb668a2bf6787d7785fa119b` |

This establishes that the delivered animation bytes reached the repository. It does not establish playback quality on every client. The public [pack notes](https://github.com/mojomast/hermes-templeos/blob/0e3167ea8014e7187fdf86d2a4f973bc0f0d18ea/desktop/assets/companion/terry/v5/README.md) and [plugin README](https://github.com/mojomast/hermes-templeos/blob/0e3167ea8014e7187fdf86d2a4f973bc0f0d18ea/README.md) describe the silent loops and canvas fallback. The integration remains the builders' work.

The separate tribute-film experiments used imagined dialogue and a labeled synthetic narrator. They are not the plugin's quote or voice policy. The plugin's sourced quotes and silent animation rules remain as recorded in [06](../docs/06-rules-and-lessons.md).

**Transferable method:** visual feedback becomes a concrete constraint; the fix becomes an editable source plus a measurable check; the final pack includes both previews and runtime exports. Check the bytes received and then check their behavior in the actual product.

## How Hyperrizz fits

Terry film work used Hyperrizz guidance and later HyperFrames. Early outputs used a local encoding fallback while the renderer was unavailable, and were described accordingly. A successful decode did not establish a full playback or listening review.

The public [Hyperrizz production loop](https://github.com/mojomast/hyperrizz/blob/35c482e22413ee43c74955bd6da7fe7b053cdd9b/README.md) now documents direction, deterministic builds, review, verified delivery and source handoff. This is a useful reuse destination for production lessons. This account does not claim that all Hyperrizz features or guides originated in the Terry session.

## Evidence boundaries

The named chats and local delivered packs establish this collaboration history. Public sources above corroborate implementation outcomes; chat records are not republished. Repo documentation and another agent's report are labeled as such, rather than treated as independently executed tests. Git blob comparisons were performed in this documentation pass; application tests, emulator sessions and video playback were not rerun.

The resulting proposal is [09 Reproducible collaboration](../docs/09-reproducible-collaboration.md): make the handoff and return report explicit, so another person can repeat the workflow without Kyle reconstructing missing context.
