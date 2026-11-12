# 08 — Repositories

Part 1 lists every repository we worked on in the documented period (mid-October to Nov 12, 2026). Part 2 has deep build histories for four of them: **Eye Of Hermes**, **Temple of Hermes**, **assetrizz** and the **aircraft Doppler geolocation** plugin.

Dates and times are America/Toronto (GitHub's UTC timestamps converted). PR, tag and release data comes from `gh` on Nov 12; the narrative comes from bot memory, the DOLAN transcript (for the Doppler plugin) and the contrib accounts.

## Part 1 — All repositories

| Repo | Visibility | Purpose | Status (Nov 12) |
|---|---|---|---|
| [orbitdesktop](https://github.com/mojomast/orbitdesktop) | Public | Agent-shaped browser desktop powered by Hermes; also our coordination layer (Grok Bots app, Collab board, Google Colab app, local-workers launcher) | Live on the box from local integration branches |
| [orbit-control-plane](https://github.com/mojomast/orbit-control-plane) | Public | Observability/control dashboard for Orbit boards, workers and chat over Tailscale | Started Oct 20 |
| [clawpocalypse-now](https://github.com/mojomast/clawpocalypse-now) | Public | AGENT ARMEGEDDON: CLAWPOCALYPSE NOW (formerly Pizza Panic), browser beat-'em-up built by the asylum agents | Live on GitHub Pages |
| [comfyrizz](https://github.com/mojomast/comfyrizz) | Public | Chat in a brief → narrated motion-graphics explainer (ComfyUI on Google Colab or BYO GPU, Remotion) | Active; Open Source Higgsfield hackathon entry; main via squash merges, no tags |
| [comfyrizz-hermes](https://github.com/mojomast/comfyrizz-hermes) | Public | Portable Hermes plugin for Comfyrizz (MCP + skill) | Listed in the Nous catalog (#146230) |
| [open-higgsfield-skills](https://github.com/mojomast/open-higgsfield-skills) | Public | Agent-agnostic video skills + video-director orchestrator | Published with demo video |
| [hermes-photo-to-part](https://github.com/mojomast/hermes-photo-to-part) | Public | Photos/measurements/scan → printable STL or CAD | v0.1.23; catalog #153757 open |
| [hermes-aircraft-doppler-geolocation](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) | Public | Geolocate a recording from aircraft Doppler flyovers matched to ADS-B tracks | v0.3.1 listed; PR #10 open. 17 stars |
| [hermes-shortrizz](https://github.com/mojomast/hermes-shortrizz) | Public | Self-hosted AI clipper: long video → captioned 9:16 shorts | v0.5.x; catalog PR closed to free a slot |
| [EOH](https://github.com/mojomast/EOH) (was `hermes-godseye`) | Public | Eye Of Hermes: God's Eye View globe inside Hermes | v0.2.10 listed |
| [gods-eye-view](https://github.com/mojomast/gods-eye-view) | Public fork of `bilawalsidhu/gods-eye-view` | The globe app, with Hermes HUD/embed patches and the public SDR layer | Main at PR #5 |
| [emurizz](https://github.com/mojomast/emurizz) | Private | SNES/N64 netplay Hermes pane (Cheese) | PR #5 measured; bee routine paused |
| [poptart](https://github.com/mojomast/poptart) | Public | Strudel music studio Hermes plugin (catalog key `hermes-strudel-studio`) | Listed (#150357) |
| [hermagotchi](https://github.com/mojomast/hermagotchi) | Public | Multiplayer agent-pet Hermes plugin | Listed (#150358) |
| [hyperrizz](https://github.com/mojomast/hyperrizz) | Public | Agent skill for distinctive HyperFrames films | Listed (#151945) |
| [hermes-stitchslop](https://github.com/mojomast/hermes-stitchslop) | Public | Drive the Stitch Slop embroidery digitizer from Hermes | Listed (#151946) |
| [hermes-templeos](https://github.com/mojomast/hermes-templeos) | Public | TempleOS-family guest in a QEMU VM shared by Hermes and the user | v0.2.2; catalog #153852 open |
| [temple-of-hermes](https://github.com/mojomast/temple-of-hermes) | Public fork of `tinkeros/TinkerOS` | The Temple of Hermes guest OS, HolyC apps, HBBS/1 BBS server, ISO and disk image | v0.1.3 |
| [hermes-buffrizz](https://github.com/mojomast/hermes-buffrizz) | Public | Freebuff CLI inside a Hermes pane with a task queue (hammy) | v0.1.0, deployed to moltussy-1; no catalog PR |
| [assetrizz](https://github.com/mojomast/assetrizz) | Public | 14,641 original 2D game assets + the pipeline that made them | v0.1.0 |
| [assetrizz-hermes](https://github.com/mojomast/assetrizz-hermes) | Public | Hermes plugin to search the library and compose scenes | v0.2.0 listed (#152771) |
| [hermes-plugin-dev](https://github.com/mojomast/hermes-plugin-dev) | Public | The Hermes plugin-building skill + scaffold/lint plugin | v0.3.1 listed (#152699) |
| [bundlebees](https://github.com/mojomast/bundlebees) | Public | The CUA bees workflow as a Hermes plugin | v0.1.1; catalog #153888 open |
| [hermes-hackathon-showcase](https://github.com/mojomast/hermes-hackathon-showcase) | Public | Asset pack + static site for the ten hackathon entries | Showcase PR #1 awaiting Kyle |
| [hermes-morningdaw](https://github.com/mojomast/hermes-morningdaw) | Private | Hermes plugin for headless song making with MorningDAW | Private; no further record in memory |
| [nous-application](https://github.com/mojomast/nous-application) | Private | Drafts for Kyle's Nous Research application | Private |
| `mojomast/hermes-agent` (fork of NousResearch/hermes-agent) | Public fork | Catalog branches (`catalog/<name>-vX.Y.Z`, `catalog/desc-*`) | Working fork |
| [workflow](https://github.com/mojomast/workflow) | Public (GitHub metadata checked Nov 12) | This documentation | New |

Kyle's many older repos (Sept 2026 and earlier, e.g. hermesdashboard, COCS, the Ussyverse sites) predate the bots' memory and aren't covered here.

---

## Part 2 — Deep build histories

## 1. Eye Of Hermes

**Repos:** [mojomast/EOH](https://github.com/mojomast/EOH) (plugin id `godseye`, renamed from `hermes-godseye`), [mojomast/gods-eye-view](https://github.com/mojomast/gods-eye-view) (fork of the upstream app). **Catalog:** [#149691](https://github.com/NousResearch/hermes-agent/pull/149691) (merged), description/banner [#154158](https://github.com/NousResearch/hermes-agent/pull/154158) (merged). **Built by:** MR.INDIA (prototype → v0.2.6, deploys, hackathon submission) with Cursor cloud agents; Hermes Plugin Builder (review fixes, SDR, audits, v0.2.8–v0.2.10).

### Origin and goal
On Nov 4 Kyle wanted Hermes to be able to drive God's Eye View, an open-source "spy satellite simulator" globe with real public data, and answer questions about what it shows. The goal: a live 3D globe pane inside Hermes that the agent can steer, with public-data tools and the app's HUD summarised by Hermes's own inference.

### Spec and planning
- First pass (Nov 4 evening): wrap the app as a plugin: tools, a Desktop pane through SandboxedFrame, HUD via `ctx.llm`, voice off.
- Two upstream patches were needed (full app controls in the Hermes pane; HUD summary through Hermes). Kyle approved opening them upstream as part of the catalog submission.
- Nov 5: the `feat/v0.2` plan added six features, EOH branding and grounded pins, then a "composable catalog" plan to collapse dozens of fine-grained tools into a few `op`-enum tools.
- A live Hermes session in Montreal (ramen restaurants, a street-level tour) produced the **Nov 5 handoff**: P0 (annotations vanish on pane reopen; photoreal imagery unreachable until the panel is rebuilt with its keys; no tour primitive), P1, P2, five acceptance tests and a do-not-regress list. It drove PRs #11–#16.

### Architecture
- Hermes plugin (`plugin.yaml` + `register(ctx)`) with tools, hooks, a dashboard API and a Desktop pane that hosts the app's MCP Apps globe panel inside SandboxedFrame (no framing of the app URL).
- A loopback overlay/relay between plugin and pane, token-gated.
- The app runs as a separate service (fork of gods-eye-view) with runtime config, hidden-pane pause, an opt-in performance profile, a HUD summary endpoint pointed at Hermes, and a full-UI embed mode.
- Tool count: ~30 in the prototype → 97 on `feat/v0.2` → **11 composable tools** at v0.2.0 (`godseye_view`, `godseye_query`, `godseye_nav` …), cutting schema tokens (the skill credits EOH with going from ~68–83 legacy tools to 11).

### How it was built

| When (ET) | What | Who / how |
|---|---|---|
| Nov 4, ~8:15 PM | First commit: "God's Eye View as a Hermes plugin (tools, desktop pane, HUD via ctx.llm)", then HUD bridge, public-URL and SandboxedFrame panel commits | MR.INDIA on the box |
| Nov 4, 10:46 PM | [v0.1.0](https://github.com/mojomast/EOH/releases/tag/v0.1.0) released; upstream PRs #1571 and #1572 opened on bilawalsidhu/gods-eye-view | MR.INDIA |
| Nov 4 | Catalog PR refused by a CreatePullRequest permission error; fork branch `catalog/godseye-v0.1.0` waited for a manual PR | — |
| Nov 5, 12:33 PM–3:08 PM | PRs [#1](https://github.com/mojomast/EOH/pull/1)–[#9](https://github.com/mojomast/EOH/pull/9): per-turn map state and fix-it errors, GeoJSON/KML export with replayed fixtures, composable `godseye_view`/`godseye_query`, README rewrite, WebGL context recovery, the eleven-tool catalog, timeline slider, v0.2.0 prep; GEV fork PRs [#1](https://github.com/mojomast/gods-eye-view/pull/1)–[#2](https://github.com/mojomast/gods-eye-view/pull/2) | Cursor cloud agents (branches `cursor/*`), merged by MR.INDIA with Kyle's yes |
| Nov 5, 3:08 PM | [v0.2.0](https://github.com/mojomast/EOH/releases/tag/v0.2.0): 11 tools, 215 tests, secret scan clean | — |
| Nov 5, 3:20 PM | Catalog [#149691](https://github.com/NousResearch/hermes-agent/pull/149691) opened | MR.INDIA |
| Nov 5, 3:33 PM–8:18 PM | [#10](https://github.com/mojomast/EOH/pull/10) brand/logo, [#11](https://github.com/mojomast/EOH/pull/11) control room, [#12](https://github.com/mojomast/EOH/pull/12) Street View route walk, [#13](https://github.com/mojomast/EOH/pull/13) Hermes wishlist ops, [#14](https://github.com/mojomast/EOH/pull/14) GEV v0.3 ideas (imagery A/B, weather, transit, fire-perimeter watches), [#15](https://github.com/mojomast/EOH/pull/15) Director scenes/pin clips/fire check, [#16](https://github.com/mojomast/EOH/pull/16) overlay manager sidebar; GEV [#3](https://github.com/mojomast/gods-eye-view/pull/3) upstream sync and [#4](https://github.com/mojomast/gods-eye-view/pull/4) restore Hermes patches | Cloud agents in two waves; each merge deployed to moltussy-1 with a backup and rollback SHA |
| Nov 5, 9:47 PM | [#17](https://github.com/mojomast/EOH/pull/17) README with recent pane screenshots (shot in dark mode on the moltussy Webapp) | Cloud agent |
| Nov 6, 2:35 AM–4:43 AM | [#19](https://github.com/mojomast/EOH/pull/19) polish → [v0.2.2](https://github.com/mojomast/EOH/releases/tag/v0.2.2); [#20](https://github.com/mojomast/EOH/pull/20) compare "black globe" → [v0.2.3](https://github.com/mojomast/EOH/releases/tag/v0.2.3); [#21](https://github.com/mojomast/EOH/pull/21) street-level keys, pane capture, OSM Overpass fallback → [v0.2.4](https://github.com/mojomast/EOH/releases/tag/v0.2.4); [#22](https://github.com/mojomast/EOH/pull/22) duplicate `name:` → [v0.2.5](https://github.com/mojomast/EOH/releases/tag/v0.2.5) | MR.INDIA |
| Nov 6, 11:47 AM | [#18](https://github.com/mojomast/EOH/pull/18) HyperFrames hackathon promo merged; catalog repinned to v0.2.5 with a disclosure about the key env-file fallback | MR.INDIA |
| Nov 6, 3:24 PM | [#24](https://github.com/mojomast/EOH/pull/24) street-level keys through Hermes `secret_scope` → [v0.2.6](https://github.com/mojomast/EOH/releases/tag/v0.2.6) | — |
| Nov 6, 6:23 PM | Hackathon submission: [X post](https://x.com/ussyverse/status/2118845028910915846) (82 s cut, posted by Kyle) + Typeform | MR.INDIA, via the submission brief |
| Nov 8, 10:00 AM | [#25](https://github.com/mojomast/EOH/pull/25) catalog security review fixes + bounded capture (v0.2.7, untagged); repin | MR.INDIA |
| Nov 9, 12:17–3:09 PM | Public SDR receivers layer: GEV [#5](https://github.com/mojomast/gods-eye-view/pull/5), EOH [#26](https://github.com/mojomast/EOH/pull/26) → [v0.2.8](https://github.com/mojomast/EOH/releases/tag/v0.2.8) and repin; [#27](https://github.com/mojomast/EOH/pull/27)/[#28](https://github.com/mojomast/EOH/pull/28) README and branded SDR shots | Hermes Plugin Builder |
| Nov 10, 11:31 AM | [#32](https://github.com/mojomast/EOH/pull/32) post-approval review fix (stop trusting watch-alert feed titles; admin confirm; pane gestures) → [v0.2.9](https://github.com/mojomast/EOH/releases/tag/v0.2.9), repin with 6 screenshots | Hermes Plugin Builder |
| Nov 10, 1:16–1:36 PM | Audit PRs merged in order [#31](https://github.com/mojomast/EOH/pull/31) (tests, CI, install docs), [#29](https://github.com/mojomast/EOH/pull/29) (security/correctness), [#30](https://github.com/mojomast/EOH/pull/30) (capabilities, `op=sdr_receivers`) → [v0.2.10](https://github.com/mojomast/EOH/releases/tag/v0.2.10), repin | Hermes Plugin Builder |
| Nov 10, 7:06 PM | Catalog #149691 merged | Nous maintainers |
| Nov 11–12 | Description-only PR #154158 with a 2:1 banner pinned to the listed version; merged Nov 12, 5:56 AM | MR.INDIA |

148 commits on EOH as of Nov 12.

### Assets and media
EOH logo and README banner (PR #10); dark-mode pane screenshots from the moltussy Hermes Webapp (overlays sidebar, Director, pin drawer); branded Public SDR shots; the HyperFrames promo with real map-pane footage, a mock Hermes terminal per scene (prompt finishes typing before the map moves), a simulated Hermes reply for the "what am I looking at" scene and the Ash voiceover; an 82 s contest cut. The "Cartographer's field instrument" restyle ([#23](https://github.com/mojomast/EOH/pull/23)) is still open.

### Testing
Fake-ctx registration tests, replayed service fixtures (VCR-style), JS tests, strict YAML test after the duplicate-key bug; 215 tests at v0.2.0 and 541 Python + 26 JS after the audits, with CI on main; schema 8,063 o200k at that point. Live checks on moltussy-1 through the Webapp in dark mode.

### Hosting and deploy
moltussy-1 runs the app as a user service and the plugin as a symlinked checkout. Every deploy on Nov 5–6 recorded a backup folder and rollback target (e.g. "rollback plugin to 865f7df"). Restarts covered the Hermes dashboard and gateway and the app service. After later tests, godseye was left **disabled** on the shared host, and map layers Kyle turned off are never re-enabled.

### Catalog submission and review fixes
Opened at v0.2.0 and repinned at v0.2.2, v0.2.5, v0.2.7, v0.2.8, v0.2.9 and v0.2.10. Review themes: untrusted feed text treated as instructions, session-token handling, relay auth, secret access through `secret_scope`, screenshot count (a 7th screenshot was dropped by the maintainer; max 6). The PR was approved, then reopened as "a correction to our approval" after a full-tree read, and merged after v0.2.10. The PR body lagged the pin, fixed later by the description PR.

### Problems and fixes
| Problem | Fix |
|---|---|
| CreatePullRequest refused for the catalog PR | Fork branch + manual PR |
| Lost WebGL context froze the pane | Recover in place (EOH #5), then replace the viewer (GEV #2) |
| Control room showed the app as down (root JSON probe got 404) | Fixed in the follow-up cloud-agent PR |
| Fork main lacked the Hermes HUD/embed patches after an upstream sync | GEV #4 restored them before deploy |
| Compare/timeline view rendered a black globe | v0.2.3 |
| Duplicate `name:` in `plugin.yaml` silently dropped tools | v0.2.5 + strict YAML test |
| Client map keys baked into the panel bundle at build time; photoreal unreachable until rebuilt | Handoff P0-2: doctor freshness check, rebuild tool, documented env file; then keys via `secret_scope` (v0.2.6) |
| GEV CI hung (a browser test leaked an HTTP server when Chrome was missing) | Fixed in `19913e6` |
| Feed titles trusted in the system prompt | #32 |

### Current state
v0.2.10 is listed in the Nous catalog with an improved description and banner. Promo restyle #23 open. Further audit lanes (UI/QoL, SDR polish, perf, E2E, promo art) were stopped on Kyle's hold.

---

## 2. Temple of Hermes

**Repos:** [mojomast/hermes-templeos](https://github.com/mojomast/hermes-templeos) (the plugin), [mojomast/temple-of-hermes](https://github.com/mojomast/temple-of-hermes) (fork of `tinkeros/TinkerOS`: guest OS, HolyC apps, HBBS/1 server, ISO, disk image). **Catalog:** [#153852](https://github.com/NousResearch/hermes-agent/pull/153852) (open, v0.2.2). **Built by:** Hermes Forge (owner, coordinator) with Cursor cloud agents then DeepSeek bees; MR.INDIA built the Terry companion PR. Kyle and Codex developed the HD artwork/animation pack whose six exports match the later plugin files; see [asset provenance](../contrib/codex.md). Full first-person implementation account: [contrib/hermes-forge.md](../contrib/hermes-forge.md).

### Origin and goal
A TempleOS-family OS running in a local QEMU VM inside Hermes so the agent and the user share one live screen, with networking always off, ISOs and disks SHA-256 pinned, and a community BBS reachable only through a serial modem and a host relay. It grew into a branded guest OS ("Temple of Hermes") with its own launcher, apps, journal and BBS, plus a Terry A. Davis tribute companion.

### Spec and planning
- Fixed budget: exactly **four tools** (`templeos_vm`, `templeos_screen`, `templeos_input`, `templeos_files`); new behaviour becomes ops, never a fifth tool; every change reports o200k schema size and delta.
- Shape: **contracts → parallel leased slices → one integration PR**. The plugin started with "Slice 0 contracts and plugin scaffold" (Nov 9, 2:08 PM), then Slice A (VM lifecycle, QMP, serial, doctor) and Slice D (serial file protocol, operator skill, README); the BBS started with a protocol contract (`docs/bbs/`: spec, schema, fixtures) before server, transport, guest and skill slices.
- Community defaults in a plan doc: two short sessions a day, a pending-only nudge at most twice a day, fetched HolyC only inside the VM with size/time caps, monthly challenges only after Kyle approves.
- Terry: Kyle (Nov 9) reframed a standalone pet idea into a feature of the TempleOS plugin, enabled by default with a hide toggle, 2017 cap look only, only approved sourced quotes.

### Architecture
- Plugin: QEMU child process, QMP + serial, a Desktop pane with the guest screen, Agent Log below it, Terry docked right with speech bubbles, an OS picker; a background frame cache so pane polling doesn't starve the Hermes gateway.
- Guest: COM1 is the agent handshake (HBEACON/HRPC, token injection); COM2 is the modem to the BBS relay; the only allow-listed destination name is `bbs`; the endpoint comes from host config, never guest text.
- BBS: HBBS/1 over TLS at `toh.rizz.click`, containerized on a VPS; human signs up first, then the agent under that human; access tokens last about 15 minutes; AUTH is rate-limited.

### How it was built

| When (ET) | What |
|---|---|
| Nov 9, 1:57 PM | `hermes-templeos` created; Slice 0 → A → D by Cursor cloud agents; integration PR [#1](https://github.com/mojomast/hermes-templeos/pull/1) opened 2:52 PM |
| Nov 9, 3:23 PM | `temple-of-hermes` fork created |
| Nov 9, 8:03 PM–10:57 PM | Terry companion: MR.INDIA built [#3](https://github.com/mojomast/hermes-templeos/pull/3) (`feat/terry-companion`, motion atlases, `TerryCompanion.say`), handed off to Hermes Forge, who reconciled it with P2/P4 and merged into `feat/improvements` |
| Nov 10 | Fixes [#4](https://github.com/mojomast/hermes-templeos/pull/4) (Terry bundle load, guest screen fit) and [#5](https://github.com/mojomast/hermes-templeos/pull/5) (Agent Log under the screen); HD Terry pack of six transparent VP9 loops with a canvas-rig fallback; 69 sourced quotes |
| Nov 11, 10:35 AM–11:16 AM | [#6](https://github.com/mojomast/hermes-templeos/pull/6) pane + HD Terry + README; [#7](https://github.com/mojomast/hermes-templeos/pull/7) catalog prep (admission disclosure, pinned fetches, secret-scope token); [#8](https://github.com/mojomast/hermes-templeos/pull/8) release line → **[v0.1.0](https://github.com/mojomast/hermes-templeos/releases/tag/v0.1.0)** (11:16 AM) |
| Nov 11, 1:12 PM | temple-of-hermes [#1](https://github.com/mojomast/temple-of-hermes/pull/1) → **[v0.1.2](https://github.com/mojomast/temple-of-hermes/releases/tag/v0.1.2)**: first official ISO, 18-entry launcher, HBBS/1 over COM2 |
| Nov 11, 1:28 PM | [#9](https://github.com/mojomast/hermes-templeos/pull/9) → **[v0.1.1](https://github.com/mojomast/hermes-templeos/releases/tag/v0.1.1)**: Temple of Hermes 0.1.2 as default guest, OS picker |
| Nov 11, 2:51–2:56 PM | Kyle's [X post](https://x.com/ussyverse/status/2120605050871455858) (90 s landscape video); catalog **#153852** opened (v0.1.1); Typeform submitted |
| Nov 11, 5:42 PM | `disk-image-0.1.3-preview` pre-release (preinstalled disk) |
| Nov 11, 5:53–6:51 PM | temple-of-hermes [#2](https://github.com/mojomast/temple-of-hermes/pull/2) (daemon file-op fix, preinstalled disk, home journal, BBS community) and [#3](https://github.com/mojomast/temple-of-hermes/pull/3) → **[v0.1.3](https://github.com/mojomast/temple-of-hermes/releases/tag/v0.1.3)** (ISO + qcow2, 20/20 boots verified) |
| Nov 11, 5:59–6:53 PM | hermes-templeos [#10](https://github.com/mojomast/hermes-templeos/pull/10) (community ops, temple-session skill, disk on by default) and [#11](https://github.com/mojomast/hermes-templeos/pull/11) → **[v0.2.0](https://github.com/mojomast/hermes-templeos/releases/tag/v0.2.0)** (schema 1,201); repin; deployed to moltussy-1 with `ROLLBACK.sh` |
| Nov 11, ~7:07 PM | BBS v0.1.3 deployed on the VPS (previous container kept, backup taken); live sign-up, digest and logout tested from Kyle's PC |
| Nov 11, 8:18 PM | [#12](https://github.com/mojomast/hermes-templeos/pull/12) → **[v0.2.1](https://github.com/mojomast/hermes-templeos/releases/tag/v0.2.1)**: built-in BBS on by default with opt-out, `op=bbs_join`, QEMU wrapper skip (schema 1,262); repin; deploy |
| Nov 12, 7:07 AM | [#13](https://github.com/mojomast/hermes-templeos/pull/13) → **[v0.2.2](https://github.com/mojomast/hermes-templeos/releases/tag/v0.2.2)**: digest uses `LIST` with `action: digest`; repin; deploy; live digest against the real BBS worked |

Bees: after the first cloud-agent slices, guest and BBS work ran as DeepSeek bees on Kyle's PC (Kyle directed bees, not cloud agents, for this work on Nov 11), coordinated from a `toh-bees` folder (`orch.py` with `MAX_ACTIVE=10`, `verify.sh` with scope check and secret scan, `briefs/*.json`, a game-app brief template, a running `NOTES.md`). QEMU never ran on the box. 66 plugin commits as of Nov 12. Open: [#2](https://github.com/mojomast/hermes-templeos/pull/2) "plugin improvements" (gateway-safe frame cache, aborts, first boot, Pillow 13).

### Assets and media
Guest wallpaper, icons and splash in the 16-colour VGA palette (PIL-only acceptance: 640×480, ≤16 colours, zero off-palette pixels); later character apps use official art plates; HD Terry VP9 loops (idle, smoking, speaking, typing, walk, wave); a footage pack of eight real 1080p30 clips and a 90 s landscape submission video. Nous figures are "characters from the Nous universe"; lore must be sourced.

### Testing
Plugin pytest + JS tests (281 py / 69 JS at v0.2.0; 300 / 72 at v0.2.2), schema measurement, tool-count assertion, PIL screenshot checks, ISO/disk verification (20/20 boots, persistence, HRPC on `C:`), and live tests on moltussy-1 against the real BBS.

### Hosting and deploy
Plugin on moltussy-1 (dashboard + gateway user services, Desktop plugin copy), deployed with a backup folder containing the prior SHA, a git bundle, a desktop-plugin copy, doctor snapshots and `ROLLBACK.sh`; verified by units active, doctor showing four tools, dashboard health 200 and the on-disk `plugin.js` hash matching the tag; then Kyle rescans plugins in Hermes Desktop. The BBS runs on the VPS.

### Catalog submission and review fixes
#153852 was opened at v0.1.1 and repinned to v0.2.0, v0.2.1 and v0.2.2, each time editing only `plugin-catalog/templeos.yaml`. The digest-verb bug found after v0.2.1 was handled before any maintainer review.

### Problems and fixes
Sandbox BBS ≠ real BBS (bees passed against a stand-in, failed on the real host) → a real-setup test rig is a follow-up. Hermes restarts killed the VM and relay → snapshot and restore. Launcher blips looked like stuck bees. A QEMU wrapper on `PATH` collided with the disk drive index → skip wrappers. COM2 dialling reset COM1 and cut the agent link; the BBS app froze scanning a read-only CD for its token → don't reset COM1, draw the UI first, scan writable drives, push tokens via HRPC. Stale Desktop pane until Rescan. Bee commits inside the sandbox produced empty patches.

### Current state
hermes-templeos v0.2.2 and Temple of Hermes v0.1.3 released; catalog #153852 open; BBS live. In flight on Nov 12: an in-guest BBS sign-in/token-freshness fix on test branches (not released), and five workflow follow-ups Kyle approved (one-command release/deploy script, deploys that restore the VM and relay, reusable brief templates, a real-setup bee test rig, a read-only look at launcher dropouts).

---

## 3. assetrizz

**Repos:** [mojomast/assetrizz](https://github.com/mojomast/assetrizz) (library + pipeline), [mojomast/assetrizz-hermes](https://github.com/mojomast/assetrizz-hermes) (plugin). **Catalog:** [#152771](https://github.com/NousResearch/hermes-agent/pull/152771) (merged, v0.2.0). **Built by:** MR.INDIA (pipeline, generation workers, keeper routine, plugin, catalog), DeepSeek bees (compose-v2).

### Origin and goal
On Nov 9 Kyle opened an unlimited image-generation window (until 5:00 AM ET Nov 10) and wanted an agent-searchable library of **original** 2D game assets: consistent style packs, real metadata, searchable by agents, eventually a Hermes plugin.

### Spec and planning
`RESEARCH.md` (Nov 9) set the approach with sources: lock a style sheet per pack and change only the subject; generate related items together as sheets; feed accepted winners back as references; one pixel density per pack; flat chroma-key backgrounds; SQLite FTS5 for search with embeddings later. `style_packs.json`, `taxonomy.json`, `specs.jsonl` and `prompts.jsonl` define the queue.

### Architecture
- Pipeline (`pipeline/` in the repo): `build_specs.py`, append-only `append_styles*.py` / `append_categories.py`, `worker.py` (claim + ingest), `process.py` (alpha, pixel snap, thumbs, palette, dedupe), `db.py` (SQLite WAL + FTS5), `query.py`, `serve.py`, `gallery.py`.
- Library: `library/{style}/{category}/{subcategory}/{subject}_{variant}.png` with thumbnails and contact sheets.
- Plugin (assetrizz-hermes): tools `assetrizz_search` and `assetrizz_scene`, a dark compose pane, on-demand asset fetch from the pinned library release into a user-only local install; from v0.1.1 the catalog ships as plain `db/assets.jsonl` and the plugin builds its SQLite index on first run. compose-v2 adds layer bands, y-sort, a declarative spec with `op=compose`, HUD docks, a lint pass and genre templates.

### How it was built

| When (ET) | What |
|---|---|
| Nov 9 evening | Workers started on 4 shards, then 8, then 12 (`nice -n 15 python3 worker.py --shard N --shards K`); each claims batches, calls the image tool with the locked prompt, converts and ingests. 30-minute leases reclaimed if a worker dies |
| Nov 9, 10:40 PM / 11:12 PM | Overnight keeper routine announced 1,000 and 2,000 accepted assets with contact sheets; milestones recorded so they weren't re-announced |
| Nov 9, 11:46 PM | `mojomast/assetrizz` created (private) with the pipeline code; 15 style packs, then 10 new categories and a third wave of eight packs via append-only queues |
| Nov 10, 12:39 AM | Repo made public at 14,641 assets with the DB, README and banner |
| Nov 10, 9:45 AM | Plugin opened as assetrizz [#1](https://github.com/mojomast/assetrizz/pull/1) (`plugin/`: 2 tools at 902 o200k tokens, dark compose pane, 27 tests) |
| Nov 10, 11:04 AM | #1 merged, [assetrizz v0.1.0](https://github.com/mojomast/assetrizz/releases/tag/v0.1.0) |
| Nov 10, 11:12–11:19 AM | Kyle approved splitting the plugin into its own small repo; `assetrizz-hermes` created and released as [v0.1.0](https://github.com/mojomast/assetrizz-hermes/releases/tag/v0.1.0) (5.5 MB, assets pinned to assetrizz v0.1.0); catalog branch validated and installed in 21 s |
| Nov 10, 11:22 AM | Catalog **#152771** opened (filled Kyle's 5th slot); hackathon submission at 11:31 AM with Kyle's [X post](https://x.com/ussyverse/status/2120191163764449283) |
| Nov 10, 3:07 PM | Kyle approved compose-v2 with DeepSeek bees on a feature branch |
| Nov 11, 8:24 AM | Review fix: replace the compressed `assets.db.xz` (not scannable) with plain JSONL → [#1](https://github.com/mojomast/assetrizz-hermes/pull/1), [v0.1.1](https://github.com/mojomast/assetrizz-hermes/releases/tag/v0.1.1), repin, reply to teknium1 (47 tests, 931 o200k) |
| Nov 11, 3:04 PM | compose-v2 [#2](https://github.com/mojomast/assetrizz-hermes/pull/2) merged (86 tests, 970 o200k) |
| Nov 11, 3:16 PM | [v0.2.0](https://github.com/mojomast/assetrizz-hermes/releases/tag/v0.2.0); validate, doctor and clean install pass; repin approved |
| Nov 11, 6:48 PM | #152771 merged |

35 commits on assetrizz and 13 on assetrizz-hermes.

### Assets and media
23 style packs × 18 categories; final pipeline snapshot: 12 shards, 5,204 batches, 14,639 ingested, 132 rejected. Every row is licensed "original, generated for Kyle Durepos"; no real people, logos or trademarked characters. README banner and style gallery; example scene in the plugin docs; a 2:1 catalog banner.

### Testing
Pipeline QA at ingest (rejections catalogued); plugin pytest (27 → 47 → 86 tests), schema budget measured each time, `hermes plugins validate` + doctor + a clean scratch install. The compose pane was not live-tested in Hermes Desktop before the first release.

### Hosting and deploy
No server: the library is a GitHub release the plugin fetches on demand into a user-only local folder; nothing was deployed to moltussy-1.

### Catalog submission and review fixes
One review round: the compressed database couldn't be scanned → plain JSONL + build-on-first-run (v0.1.1). Then repinned to v0.2.0 for compose-v2 and merged.

### Problems and fixes
The image tool ignores filenames and returns JPEGs (convert and copy to the expected PNG path); no seeds (consistency from the locked prefix and palette snap); adding styles mid-run without disturbing claims (append-only scripts); keeping the plugin small (split repo, fetch assets on demand).

### Current state
assetrizz v0.1.0 public; assetrizz-hermes v0.2.0 listed in the Nous catalog. The compose-v2 bees worktree is still on the box.

---

## 4. Aircraft Doppler geolocation

**Repo:** [mojomast/hermes-aircraft-doppler-geolocation](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) (17 stars, the most of Kyle's plugin repos). **Catalog:** [#148043](https://github.com/NousResearch/hermes-agent/pull/148043) (v0.1.1, merged Nov 2), [#148633](https://github.com/NousResearch/hermes-agent/pull/148633) (bumped to v0.3.1, merged Nov 5). **Built by:** DOLAN, on the box, at Kyle's direction. Also saved as the reusable `aircraft-doppler-geolocation` skill.

### Origin: the video
On Nov 2 Kyle sent DOLAN a YouTube video, [**"I discovered a sound that leaks your exact location (and it's everywhere)"**](https://www.youtube.com/watch?v=UytYrhYLOKI), and asked for it as an agent skill that could become a Hermes skill. DOLAN pulled the transcript and found the technique wasn't electrical hum: the creator located a recording from the faint **Doppler pitch curves of planes flying over**, matched against public flight-tracking (**ADS-B**) data, and got a security-camera clip down to about 100 m.

### From video to method
1. **Doppler curve extraction.** Trace a flyover's engine tone in the spectrogram and fit the classic Doppler curve to get the aircraft's speed and closest-approach distance.
2. **ADS-B track matching.** For candidate locations, predict the Doppler curve each real flight would have produced and score the candidates.
3. **Self-test** with synthetic data: the fit landed within 1 m of the true closest distance; with a known time the true spot ranked first; without a time the best spot was ~1.4 km off along the flight path, the same ambiguity the video describes, so the skill requires a known time or a second plane.

The first deliverable was the skill with three scripts (`doppler_track.py`, `score_candidates.py`, `make_synthetic_test.py`) in Hermes's skill format.

### Spec and build steps
| When (ET) | What |
|---|---|
| Nov 2 morning | Skill written and self-tested; Kyle asked to "finish what's needed for the submission"; DOLAN started an `optional-skills/` PR into Hermes itself. Kyle clarified: "i want it to be a hermes plugin" |
| Nov 2, 11:09 AM | Repo created, laid out like photo-to-part (skill, scripts, tests); Kyle asked for real screenshots: spectrogram with fitted curve, candidate heatmap, passing tests |
| Nov 2, 11:12 AM | [v0.1.0](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/releases/tag/v0.1.0); catalog **#148043** opened 11:14 AM (5 tests, validator "safe") |
| Nov 2 | Kyle: "test this on some random outdoor youtube videos". Real audio worked when tones were clean (a Cessna 421 at ~122 kt, ~300 m; a light plane at 1.5–2 km) with no false hits in a plane-free city clip, but the test found a bug: noise and a jet's broadband roar were reported as fits |
| Nov 2, 12:37 PM | [#1](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/1) detection gate → [v0.1.1](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/releases/tag/v0.1.1) (6 tests); catalog repinned; README states real-world limits |
| Nov 2 | Kyle: "research best practice … figure out how to automate everything". Research plan: free historical ADS-B from adsb.lol daily files, elevation from Copernicus, temperature from Open-Meteo, a harmonic-summing multi-tone detector, track-based curve modelling (handles turns), and one `locate(recording, date?, region?)` tool |
| Nov 2, 1:08 PM | [#2](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/2) v0.2.0: automatic detection, data fetching and caching, track-based scoring, `locate` CLI and two Hermes tools (21 tests). Then calibrated likelihood, miss costs and a fix for skipped UTC days |
| Nov 2–3 | Evaluation on 12 → 37 dated clips (YouTube plane spotting, then Freesound and Radio aporee field recordings with exact pins and times), with held-out sets never tuned on. Honest result: ~1 km on clean multi-flyover clips (Carlsbad, Long Beach) but a ~10–13 km median on held-out clips; livestream audio has commentary and cut lows; most jet passes show only a broadband roar |
| Nov 3 | Kyle: "research best practice and go ahead". New **broadband detector** reading Lloyd's-mirror ground-reflection interference bands (after published single-microphone aircraft tracking work by Lo and Ferguson) → draft [#4](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/4): two Manchester recordings went from no answer / 10 km to 0.19 and 0.33 km; held-out within 3 km went 1/14 → 2/18, answers 8 → 11, 95% areas contained the truth in 8/11 |
| Nov 3, 3:03–3:04 PM | #4 and #2 merged → [v0.3.0](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/releases/tag/v0.3.0) with `docs/broadband.md` and `docs/evaluation.md`; #148043 had already merged at v0.1.1, so a new catalog PR **#148633** was opened (YAML-only) |
| Nov 3, 6:41–6:46 PM | Efficiency pass [#5](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/5) merged after precision/cache review fixes. Final author-reported run: 2,073 s → 746 s on 7 tuning clips, zero observed output differences; held-out equivalence unverified. The earlier 2,279 s → 960 s report is superseded. Community PR #3 by @Bortlesboat (`--smooth-s` for jittery ADS-B) reworked as [#6](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/6) with his authorship kept and a changelog credit |
| Nov 3, 8:23–8:44 PM | [#7](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/7) CI (ruff + offline tests), [#8](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/8) small efficiency pass, [#9](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/9) new 1280×640 banner from synthetic data → [v0.3.1](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/releases/tag/v0.3.1) (94 tests, 2 skipped, CI green); #148633 repinned |
| Nov 4 | Installed into Hermes on the box (config backed up first); [#10](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/10) opened so tools return plots as inline media and to fix a dependency pin conflict with Hermes |
| Nov 5, 2:48 PM | #148633 merged by Nous |

63 commits as of Nov 12. Most work items were Kyle's one-line asks ("test on random outdoor videos", "automate everything", "find more clips", "make sure documentation is up to date") turned by DOLAN into plans, PRs and honest reports; merges, releases and repins each waited on his "go ahead".

### Assets and demo video
README screenshots from real runs, real spectrograms, the summary charts, the banner script in the repo. Kyle then asked for a narrated YouTube-style walkthrough "using the comfyrizz stuff among others", with "the best possible voice … no kokoro". DOLAN built it with Comfyrizz for assembly, tested Chatterbox and F5-TTS voices on Google Colab (about 1 CU total), checked every sentence with Whisper, and recorded a real Hermes chat where Hermes ran the tools and showed the plots inline. v1 (3:56) ran the plugin on a 75-minute Manchester clip and landed 0.10 km from the true spot; v3 (3:40) added the Hermes chat, whose answer landed about 60 m away. Nothing was uploaded.

### Testing
Synthetic self-tests, noise-rejection test, unit tests (5 → 94), held-out evaluation on dated real recordings with tuning/test splits, bit-identical regression checks for performance work, CI on PRs and main.

The performance review crossed agents: Kyle brought Codex's efficiency brief to DOLAN and returned the results for independent review. The near-tie precision reproduction and incomplete-cache finding became fixes recorded in PR #5. Full-pipeline timings remained builder-reported; the warm-cache figures predated those fixes. See [the worked handoff](../examples/doppler-review-handoff.md).

### Current state
v0.3.1 listed in the Nous catalog. PR #10 (inline plots, dependency fix) open, proposed as v0.3.2. Documented limits: dependable on clean, close, multi-flyover recordings with a known time; not yet dependable on new places; the "ok" rating isn't reliable out of sample.
