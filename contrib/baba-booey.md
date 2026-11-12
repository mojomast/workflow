# BABA BOOEY — build history with Kyle

Written 12 November 2026 (America/Toronto) for Kyle's workflow documentation repo. Facts only, from this bot's journals, standing profile rules, and the photo-to-part / hackathon work recorded in this bot's own sessions. Nothing here is invented. Gaps are left as gaps. Secrets, credentials, private hostnames, private IPs, and vault data are omitted on purpose.

BABA BOOEY (baba_booey) is a Grok Bot teammate. Kyle added this bot to the group on 14 October 2026. The work this bot actually built, released, and submitted with Kyle is **photo-to-part**. Other plugins and sites below are Kyle's projects that this bot helped list, track, or work alongside; they are attributed accordingly and are not claimed as this bot's builds.

## 1. Planning and spec

Photo-to-part is a Hermes Agent plugin: snap a photo of a physical part and get a 3D-printable model. Public repo: [mojomast/hermes-photo-to-part](https://github.com/mojomast/hermes-photo-to-part).

Planning was iterative, not a single upfront design freeze. Versions shipped fast, then were judged against a growing test battery:

- A **frozen spec** and a **scoring** pass landed in v0.1.6 (2 November 2026), together with printability checks, GrabCut, ArUco calibration, and an `evals/` suite.
- **Real-photo rounds** (r2 through r16) sat beside **sealed Hermes evals** and in-process evals. A version that failed or regressed on those was not pinned in the catalog, even if the code had already merged. v0.1.12 and v0.1.13 both regressed versus v0.1.11, so catalog PR #148018 stayed on v0.1.11 until later fixes landed.
- The tool surface grew in named steps: four tools in v0.1.1; `photo_part_measure` in v0.1.2; `photo_part_build` in v0.1.3 (six tools from that point); feature helpers for threads, knurls, and sweeps in v0.1.4.
- Recurring spec problems that later versions had to address: the 40-turn budget (agents that read plugin source burned the budget and skipped budget hints), unreliable photo overlays, bore counting on thin or L-shaped parts, hinge knuckle detection, false gap or wall warnings, and agents bypassing the plugin.
- v0.1.15 folded in review feedback (teknium1's plugin PR #6, rebased as repo PR #19 and then closed as #6): approval-gated `photo_part_build` plus a write denylist. Unattended real-photo rounds needed an explicit build-approval setting.
- v0.1.16 moved the plugin into a repo `plugin/` subdirectory, added a terminal-build approval hook and an eval read guard, and declared hooks in the catalog entry. The point of the eval guard was **zero leaks** of sealed-eval answers.
- Install for box testing used `hermes plugins install mojomast/hermes-photo-to-part/plugin --ref <sha>`. Hermes doctor was the check that tools and hooks actually registered (six tools confirmed on Hermes 0.21.7 at v0.1.7; six tools and four hooks at v0.1.15).

Hackathon planning (Nous Hermes plugin hackathon, deadline 11 November 2026) required a catalog PR, a short X demo, and a Typeform entry. The brief used 5 PM ET; the confirmation page said the hackathon ended at 1 PM PST (4 PM ET). A submission brief was kept at `/workspace/prompts/nous-hackathon-submission.md`. Approved public numbers for the v0.1.22 showcase, used in the video kit and the X caption, were: gear IoU 0.94 in under five minutes; a 70 mm hinge matching the measurement; 248 tests; 28/28 sealed evals; CI green.

This bot does not start optional planning or extra work without Kyle asking. Kyle's approval, not another agent's, is what counts for tags, releases, merges, catalog PRs, and submissions.

## 2. Assets

**Test photos.** Real-photo cases lived in workspace round folders (`/workspace/photo-to-part-test-r{2,…}`) and later in `/home/box/.p2p-archive` (rounds r2–r16). On 9 November 2026 at 7:10 PM ET, Kyle confirmed that archive is lost. Replacement photos have to be sourced. Archives are not to be deleted. **Test photos and eval answers are never committed to the public repo.**

**Video kit, for an off-host video agent.** Kyle asked for a 60-second showcase and then corrected the handoff: the video agent is on another host and cannot read box paths, so everything it needs has to be on a GitHub branch, with the details in the prompt. A zip was tried first (Python's zipfile, because `zip` was not installed on the box). The lasting approach was a public **`video-kit`** branch (commit be886d0): `video-kit/README.md` (brief, asset table with raw GitHub URLs, approved numbers, rules) and `video-kit/assets/` (three pane PNGs).

The external video agent delivered on branch **`video/showcase`** (commit 4aaab7ae5b4393ae0cb5b03e87a10d99870d2c8c), intentionally not merged to main so MP4s stay off `main`. Layout is under `film/`: `delivery/photo-to-part-1080p.mp4` (60 s, 1080p30, 10.07 MB), `photo-to-part-square.mp4`, `X-POST.txt`, `verification.json`, `HANDOFF.md`, and source. Local copies were kept at `/workspace/p2p-submit/` (MP4s, caption, frame stills, sheet) and `/workspace/p2p-video-assets/` (the zip).

**X graphics and posting.** The X connector can attach images for a post but cannot upload video for a post. The working path is a draft (card plus intent link); Kyle attaches the video himself and presses Post. This bot never posts on X for Kyle.

## 3. Development

### Orchestration

Day-to-day photo-to-part work ran on **the box**, with the GitHub CLI authenticated as mojomast. Follow-on work (merging, testing, releasing, coding) goes to Grok bots — this bot's own workers or teammate bots — not Cursor cloud agents, unless Kyle says otherwise.

Kyle's preferred split, as of 9 November 2026, is to send resource-heavy work (test rounds, evals, builds) to CUA bees running DeepSeek Flash on Kyle's PC, at most three DeepSeek bees at a time. That mode is paused for photo-to-part until the PC launcher is authorized for the plugin: after the archive loss the same day, Kyle asked for photo-to-part work to be done directly on the box. Do not restart Orbit or the PC launcher, and do not edit Kyle's PC config, without his OK.

Kyle is careful about usage and cost: do not spawn more workers than a task needs, and do not start optional work without asking.

### Pipelines used or built

- **Unit tests and CI**, growing across releases (54 tests at v0.1.2, then 62, 70, 92, 106, 116, 124, 150, 159, 163, 175 at v0.1.16, and 248 at the v0.1.22 showcase).
- **Real-photo rounds** r2–r16, scored per case (pass / partial / fail, turn-cap hits).
- **Sealed Hermes evals** and in-process evals. A clean bar first showed at v0.1.11 (8/8 real photos, 0 turn-limit hits, 18/18 sealed, 28/28 in-process). v0.1.16 recovered 8/8 real photos and 18/18 sealed with 0 leaks. The v0.1.22 public claim is 28/28 sealed evals.
- **Hermes doctor** to confirm the plugin registers.
- **Catalog validation** before a catalog PR: `scripts/validate_plugin_catalog.py` and `hermes plugins validate plugin --install-deps`.
- Catalog entries live at `plugin-catalog/<name>.yaml` on a fork branch of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent): repo URL, a **full SHA pin**, and `subdir: plugin` once the plugin moved into that subdirectory.

### Subagents, workers, bees, and how they are briefed

Box-side work is often handed to this bot's own workers or executor subagents. Bees, when used, are CUA bees on Kyle's PC, DeepSeek Flash, cap of three.

Off-host agents need a **self-contained brief**. Box paths are useless to them. The working pattern, after Kyle's correction, is: put the brief, rules, approved numbers, and assets on a **public GitHub branch** (raw URLs in an asset table), and point the agent at that branch in the prompt. That is what `video-kit` was for. A zip can be a fallback, but the branch is what actually unblocked the video agent.

### Review and release flow

Nothing is tagged, released, merged to a catalog, or submitted without **Kyle's explicit approval**. Another agent's "yes" does not count. Never force-push `main`.

Typical flow for photo-to-part:

1. Land work on the plugin repo (PR to `main`), with tests and, when relevant, a real-photo plus sealed-eval round.
2. If quality holds, ask Kyle to **tag** and cut a **GitHub release**. Example: tag v0.1.22 at `d924991f56ad4cf7b94e33f2ac5dcb6cf24fac5f`, release at [hermes-photo-to-part/releases/tag/v0.1.22](https://github.com/mojomast/hermes-photo-to-part/releases/tag/v0.1.22). Version strings must match everywhere.
3. On Kyle's yes, open or update a **Nous catalog PR** from the mojomast fork (for v0.1.22: branch `catalog/photo-to-part-v0.1.22`, file `plugin-catalog/photo-to-part.yaml`, pin the release SHA, `subdir: plugin`). The v0.1.22 PR is [NousResearch/hermes-agent #153757](https://github.com/NousResearch/hermes-agent/pull/153757). It states that it supersedes #148018. A local checkout was kept at `/workspace/catalog-photo-to-part-v0122`.
4. Run the catalog validation scripts. #153757 validated except a private-import warning (rule 9).
5. There is a cap on how many of Kyle's catalog PRs can be open at once (five). Earlier catalog PR #148018 (opened 2 November 2026 for v0.1.0 from fork branch `catalog/photo-to-part-v0.1.0`, then repeatedly retitled and repinned through v0.1.16) was closed around 9 November 2026 to free a slot. When #153757 was opened, free slots had appeared after other merges, so nothing else had to be closed for it.
6. For the hackathon: draft the X post, give Kyle the draft and the video, wait until he posts, then fill the Typeform and **stop for Kyle's yes** before submit. Kyle approved submit via the widget ("Yes, submit it"). There is no Typeform review page; only the last field shows in a final screenshot, and Kyle was told that.

## 4. Infrastructure, hosting, networking, and logistics

- **The box** is the shared persistent machine for this bot and Kyle's other agents: builds, tests, `gh`, local Hermes doctor, workspace artifacts, and catalog checkouts. Agents share the machine, not one another's desktops.
- **Kyle's PC** is the intended host for the launcher and CUA bees. Photo-to-part was not sent there while the launcher lacked plugin authorization.
- **The tailnet** is how live Orbit and related services are reached. Hostnames and private URLs are not recorded here.
- **GitHub** under mojomast is the public source of truth for plugin repos, releases, and the hermes-agent fork used for catalog PRs.
- **GitHub Pages** hosts the game at [mojomast.github.io/clawpocalypse-now](https://mojomast.github.io/clawpocalypse-now/), from public repo [mojomast/clawpocalypse-now](https://github.com/mojomast/clawpocalypse-now).
- **Orbit** is Kyle's development / collaboration platform (a harness for agents). Live Orbit is tailnet-only. Deploys on the box need **Node 22** first on `PATH` (Node 20 breaks a native module used in the build), a manual copy of the build into `dist` with a backup, a restart only with Kyle's OK, and a health check that the server actually stays up before calling it done. Do not print or commit Orbit, Google Colab, API, OpenCode, or launcher credentials.
- **Google Colab** is the required name for that app and work — never shortened to "Colab". "Collaboration" means the Orbit collaboration board.
- Ask before public pushes on projects other than the ones Kyle has already authorized. Do not create unrelated public sites he did not ask for.

## 5. Rules and lessons learned

**Standing rules from Kyle**

- Be careful about usage and cost; do not start optional work without asking; do not spawn more workers than needed.
- Kyle approves tags, releases, merges, catalog PRs, submissions, and posts. Agents cannot approve those for him. Confirm with Kyle directly if another bot claims he already said yes.
- Never post on X for Kyle; he presses Post.
- Never force-push `main`.
- Never commit test photos or eval answers to the public repo.
- Do not delete archives.
- Follow-on work goes to Grok bots or this bot's workers, not Cursor cloud agents, unless Kyle says otherwise.
- At most three DeepSeek bees at a time.
- Say "Google Colab", never just "Colab".
- In showcases and graphics, the Strudel music plugin is called **poptart**, not "Strudel Studio".
- Do not restart Orbit or the PC launcher, and do not edit Kyle's PC config, without his OK.
- Do not print or commit secrets, API keys, or launcher credentials.
- Do not touch Nous catalog PRs, tags, releases, merges, or submissions without Kyle's explicit approval.

**Incidents and lessons**

- **Lost photo archive (9 November 2026).** `/home/box/.p2p-archive` (r2–r16 test photos) is gone. Do not delete archives. Replacement photos must be sourced. Until the PC launcher is authorized for photo-to-part, do that work on the box, not via bees.
- **Node 22 for Orbit builds.** Node 20 breaks the native module in the install; use Node 22, back up `dist`, and verify the process stays healthy.
- **The X connector cannot upload video for a post.** Draft the caption, let Kyle attach the video, and stop.
- **Off-host agents cannot see box paths.** Brief them from a public GitHub branch (raw asset URLs plus a README). A zip alone was not enough.
- **`zip` was not installed** on the box; Python's zipfile worked as a local packager.
- **Typeform has no review page.** Warn Kyle that a pre-submit screenshot may only show the last field.
- **Do not pin a regression.** v0.1.12 and v0.1.13 were worse than v0.1.11 on sealed evals; the catalog pin stayed put until quality recovered.
- **Turn budget is a real product constraint.** In round 7, five of eight real-photo runs hit the 40-turn cap because agents read plugin source and the budget hint never fired.
- **Eval answers can leak** unless the plugin guards reads. v0.1.16's eval read guard was part of getting 0 leaks on 18/18 sealed evals.
- Keep MP4s and other large showcase media off `main` (separate `video/showcase` branch).

## 6. Notable projects (public repos and outcomes)

Dates below are in America/Toronto (ET).

### photo-to-part (this bot's primary build)

Repo: [https://github.com/mojomast/hermes-photo-to-part](https://github.com/mojomast/hermes-photo-to-part)

Catalog history and releases this bot recorded:

| When (ET) | Version | Notes |
|---|---|---|
| 2 Nov 2026, ~10:25 AM | v0.1.0 (main 8c43322) | First catalog submission: [NousResearch/hermes-agent #148018](https://github.com/NousResearch/hermes-agent/pull/148018) from fork branch `catalog/photo-to-part-v0.1.0`. |
| 2 Nov, ~12:00 PM | v0.1.1 (main a0e96d0, repo PR #2) | Four tools; #148018 retitled and repinned (head c63db79). |
| 2 Nov, ~1:20 PM | v0.1.2 (main 05f2056, PR #3) | Five tools including `photo_part_measure`; 54 tests; #148018 head 92bbab9. |
| 2 Nov, ~2:25 PM | v0.1.3 (main a939851, PR #4) | Six tools including `photo_part_build`; 62 tests; #148018 branch commit b0bc3ea. |
| 2 Nov, ~3:55 PM | v0.1.4 (main 4002dfd, PR #5) | 70 tests; threads / knurls / sweeps helpers; #148018 head 9b84af3. Test rounds r2–r4 in workspace. |
| 2 Nov (SHA recorded with v0.1.6) | v0.1.5 | main 127ee70. |
| 2 Nov, ~5:40 PM | v0.1.6 (main 2bc4813, PR #10) | 92 tests; scoring, frozen spec, printability, GrabCut, ArUco, `evals/`; #148018 branch commit bed3438. |
| 2 Nov, ~6:35 PM | v0.1.7 | Confirmed working in Hermes 0.21.7 (six tools). Round 6: 6/8 real photos pass, 2 partial from the 40-turn limit. Top issues: turn budget and unreliable overlays. |
| 2 Nov, ~7:40 PM | v0.1.8 (main 436cf87, PR #12) | 106 tests; validate auto-render, call-budget hints, edge-based overlay with a confidence gate, bore and median-ray wall checks, sealed evals; #148018 branch commit cf673cd. |
| 2 Nov, ~8:10 PM | v0.1.8 round 7 | 4 clean passes, 1 caveated pass, 3 fails (worse than r6); 5 of 8 hit the 40-turn cap; bore counter misses holes in L-shaped / thin parts. |
| 2 Nov, ~9:30 PM | v0.1.9 (main b31f963, PR #13) | 116 tests; 7 of 8 real-photo cases in round 8; #148018 branch commit 6d0bc78. |
| 2 Nov, ~10:45 PM | v0.1.10 (main e64fbc6, PR #14) | 124 tests; round 9: 16/16 sealed evals, 7 of 8 real-photo cases including the strap hinge; #148018 branch commit cd149e1. |
| 3 Nov, ~10:50 AM | v0.1.11 (main 6ab3e1d) | Round 10: 8/8 real photos, 0 turn-limit hits, 18/18 sealed, 28/28 in-process; #148018 branch commit 19f5cc2. |
| 3 Nov, ~12:55 PM | v0.1.12 (main 7f65735, PR #16) | 150 tests. Round 11: 8/8 real photos but 17/18 sealed (hinge knuckles ignored when outside params; new false positive; scorer missed a wrong skill id). Catalog stayed on v0.1.11. |
| 3 Nov, ~3:05 PM | v0.1.13 (main b68fdfa, PR #17) | Round 12: 7/8 real photos, 17/18 sealed. Catalog stayed on v0.1.11; both v0.1.12 and v0.1.13 had regressed. |
| 3 Nov, ~5:10 PM | v0.1.14 (main 729216b, PR #18) | 159 tests, real-mesh regression suite. Round 13: 8/8 real photos, 18/18 sealed; #148018 branch commit 99e7386. |
| 3 Nov, ~6:10 PM | v0.1.15 (main 3e2af8f, PR #19) | 163 tests; approval-gated build and write denylist (rebase of review PR #6, then #6 closed); #148018 branch commit f3f3ee3; doctor shows 6 tools and 4 hooks. |
| 3 Nov, ~8:35 PM | v0.1.16 (main 17556b8, PR #20) | 175 tests; plugin moved under `plugin/`; terminal-build approval hook; eval read guard. Round 15: 8/8 real photos, 18/18 sealed, 0 leaks; #148018 branch commit 7765872, now with `subdir: plugin` and hooks declared. |

This bot did not journal individual v0.1.17–v0.1.21 releases in the same way. Development continued after v0.1.16. Repo PR #21 (docs) was still an open decision for Kyle as of the v0.1.22 submission work. Catalog PR #148018 was later closed (~9 November 2026) to free a catalog slot.

**Hackathon package (11 November 2026):**

- Release **v0.1.22**, tag at `d924991f56ad4cf7b94e33f2ac5dcb6cf24fac5f`: [GitHub release](https://github.com/mojomast/hermes-photo-to-part/releases/tag/v0.1.22).
- Catalog PR **[#153757](https://github.com/NousResearch/hermes-agent/pull/153757)**, "plugin-catalog: add photo-to-part v0.1.22", superseding #148018. Open as of this bot's submission work that day.
- 60-second showcase on branch `video/showcase` (not merged to `main`).
- X post (Kyle posted): [x.com/ussyverse/status/2120597848089882860](https://x.com/ussyverse/status/2120597848089882860). Caption, as approved: "Snap a photo. Get a printable part. / photo-to-part v0.1.22: gear IoU 0.94 in under 5 minutes. A 70 mm hinge, exactly as measured. / 248 tests · 28/28 sealed evals · CI green. / Built for Hermes Agent by NousResearch" plus the repo URL.
- Typeform **Submission Received** at about **2:25 PM ET** on 11 November 2026.

A later shared-journal update (12 November 2026, 9:00 AM ET, recorded by MR.INDIA, not by this bot) says teknium1's review on #153757 was addressed: photo-to-part **v0.1.23** (fix PR #29, merged at af108f4) was repinned on #153757 (head 43f55fd), and it passed the validator plus a Hermes 0.23.0 smoke test. This bot did not perform that repin.

### Other Nous hackathon entries Kyle asked this bot to list

On 11 November 2026, after the photo-to-part submit, Kyle asked this bot to list his entries and then their GitHub links. The eight this bot listed, with the catalog status as of that listing, were:

- Eye Of Hermes (EOH) — [mojomast/EOH](https://github.com/mojomast/EOH). Catalog PR #149691; Typeform submitted 6 November 2026. Listed as merged.
- Hermagotchi — [mojomast/hermagotchi](https://github.com/mojomast/hermagotchi). Catalog PR #150358; Typeform submitted 6 November 2026. Listed as merged.
- poptart — [mojomast/poptart](https://github.com/mojomast/poptart). Catalog PR #150357; Typeform submitted 6 November 2026. Listed as merged. Showcase name is **poptart**, not "Strudel Studio".
- hyperrizz — [mojomast/hyperrizz](https://github.com/mojomast/hyperrizz). Catalog PR #151945; Typeform submitted 9 November 2026. Listed as merged.
- stitchslop — [mojomast/hermes-stitchslop](https://github.com/mojomast/hermes-stitchslop). Catalog PR #151946; Typeform submitted 9 November 2026. Listed as merged.
- Hermes Plugin Dev — [mojomast/hermes-plugin-dev](https://github.com/mojomast/hermes-plugin-dev). Catalog PR #152699, still open in that listing.
- assetrizz — [mojomast/assetrizz-hermes](https://github.com/mojomast/assetrizz-hermes). Catalog PR #152771, still open in that listing. Typeform submitted 10 November 2026.
- photo-to-part — as above; catalog PR #153757 open in that listing.

Those plugins were built and submitted with Kyle by other teammate bots as well as this one; this bot's first-hand build-and-submit work is photo-to-part. Shared journals after that listing record two more entries (TempleOS for Hermes and bundlebees) and later catalog-PR merges, including #152699 and #152771 merging on the evening of 11 November 2026. This bot did not submit those two extra entries.

### clawpocalypse-now and Orbit

On 14 October 2026 Kyle added BABA BOOEY to the group with a bosses task on the game then known as Pizza Panic (other bots were assigned end screens/credits and gamepad/QA). As of 15 October 2026 the game is named "AGENT ARMEGEDDON: CLAWPOCALYPSE NOW" (Orbit app id still pizza-panic) and is hosted on GitHub Pages from [mojomast/clawpocalypse-now](https://github.com/mojomast/clawpocalypse-now) at [https://mojomast.github.io/clawpocalypse-now/](https://mojomast.github.io/clawpocalypse-now/). This bot does not have a first-hand journal of shipping that bosses work, so no further outcome is recorded here.

Orbit itself is the platform these bots run against (Grok Bots app, collaboration board, Google Colab app, Activity panel). This bot follows the deploy and approval rules in section 4 and did not record a separate Orbit release of its own in the journals used for this write-up.

---

*End of BABA BOOEY contrib. Written 12 November 2026, America/Toronto.*
