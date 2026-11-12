# Cheese — build workflow with Kyle

Writer: Cheese (Grok Bot).  
As of: 12 November 2026, America/Toronto (Eastern Time).  
Sources: my own journals, the Emurizz spec and orchestration notes I kept, test evidence I filed, and the conversation with Kyle through this date. I could not search older chat transcripts from this writing pass; if a fact was not in those sources, it is omitted.

This is a factual account of how I planned, built, tested and shipped work with Kyle. It is not a complete history of every bot in the group.

---

## 1. Planning and spec

The main planning example is **Emurizz**, a Hermes Desktop pane for true netplay (not remote video of someone else's emulator). Kyle started it on 5 November 2026. The living documents are `/workspace/emurizz-spec/SPEC.md` and `DEVPLAN.md` (revision 2, same day), plus `ORBIT-BEES-RUNBOOK.md` for how I was to run bees.

Kyle's scope override, written at the top of both documents: the project name is Emurizz; SNES is 2 players (pinned RetroArch + bsnes); N64 is 4 players (pinned RMG-K + GekkoNet rollback). The body of the spec still mentions a 2-player N64 in places; the override supersedes that. The earlier four-system streaming plan was dropped. Every player runs and loads the game locally. Network traffic is frame-numbered inputs, negotiation, bounded state, diagnostics and chat — not the other person's video.

The spec defines completion levels and acceptance criteria before implementation:

- **L0** — engines synchronize in native windows on two machines.
- **L1** — the pane controls those engines, with private rooms, preflight and authenticated direct/relay transport; external game windows must be labeled as such.
- **L2** — the intended MVP: both games displayed and controlled inside the Hermes pane (AC-10). A pane that only launches a native window does not satisfy this.

Acceptance criteria AC-01 through AC-14 cover local simulation, SNES soak, N64 rollback (a delay-only session does not pass), preflight, NAT/relay, transport security, quality, desync recovery, lifecycle, the in-pane gate, companion pairing, rooms/chat, platform claims and release provenance. Every numeric latency or quality figure in the spec is an engineering target, not a measured result. Gates are tracked as unproven, passed, failed or blocked-external. Security, rights and catalog gates are not waived for a demo.

`DEVPLAN.md` turns that into milestones with exit evidence and a proposed timebox (re-estimate after day 1; the schedule is not a hard deadline):

| Milestone | Intent |
|---|---|
| M0 | Baselines, feasibility, contracts v1, license inventory |
| M1 | Transport proof: SNES ordered protocol and N64 datagrams over encrypted direct and forced-relay paths |
| M2 | Pane-controlled sessions: pair, select local content, block mismatches, join/ready/start/leave, chat |
| M3 | In-pane local gameplay and measured presentation latency (AC-10) |
| M4 | Quality and recovery: longer soaks, loss/jitter, induced desync, rematch/teardown |
| M5 | Release: clean install, provenance, catalog package, honest level/OS labels |

M4 was never approved. Work stopped short of that quality/recovery milestone.

Approval gates in practice: I did not start the next milestone until Kyle said to proceed. After each worker wave I reported what merged, which gates were still unproven, and asked whether to continue. Lead-owned items (shared transport at first, then public relay, firewall and spend) were not dispatched to bees. I did not invent briefs or start a wave until the branch, board cards and briefs were in place.

When a real dependency was still missing, I said so rather than shipping a mock as done. Before M3, `transport/`, `connector/` and `infra/` were still placeholders and the Hermes frame/audio seam was unproven, so the M3 wave was re-scoped to those runnable prerequisites, and AC-10 was reported as blocked when the presentation path was not actually in the pane.

Later planning was written the same way, as contracts and research memos rather than improvised code:

- On 7 November 2026 I wrote research-only memos (no deploys or repo edits) on viewer-side browser emulation, the least-invasive SNES input path into the pinned RetroArch, and agentic cheats/gameplay/guides. The last of these recommended a **Solo Lab** for offline sessions only, strictly separate from any netplay controller.
- Solo Lab work was split across three feature branches (cheats, agent-play, guides) against `/workspace/emurizz-orch/solo/SOLO-CONTRACT.md`, branching from `feat/pane-e2e`. Memory and cheat tools must refuse when netplay is active. PRs were to open into `feat/pane-e2e` and not be merged without Kyle.

---

## 2. Assets

**Reference sheets.** I generated and delivered three Nous character reference sheets for Kyle: a color cyberpunk sheet, a risograph/duotone sheet, and a clean cel-anime color sheet.

**Emurizz visuals and evidence.** I made pane branding (banner and logo under the orchestration tree) and kept screenshot and measurement evidence for live sessions: frame captures, redacted live-page HTML, latency tables, N64 GPU and one-emulator-per-machine results, and rollback soaks. Test sessions used hidden X displays so they would not take over a visible desktop. Presentation credentials and live stream URLs were kept out of those captures.

**Music.** Kyle and I make music on Linux with MorningDAW. He prefers realistic, convincing instrument sounds over MIDI-sounding ones. I do not have a dated catalog in this writing pass of every track we finished, so I am not inventing titles or a discography.

---

## 3. Development

### Orchestration

Emurizz was coordinated from an Orbit collaboration board. I ran a routine, `emurizz-bee-orchestrator`, that ticked often (typically every 10 minutes during agreed hours in America/Toronto). A tick refreshed worker status, verified finished bees against their brief, merged passing work onto the current **feature** branch, and dispatched only tasks whose dependencies were already merged.

**PC bees** ran on Kyle's Windows computer through the Orbit local-workers launcher, in Cua sandboxes, on **deepseek-v4.1-flash only**, with a cap of **three** active bees. They were staggered, especially at sandbox seed time: concurrent `git fetch` against the shared PC clone timed out at 120 seconds, which looked like bee failures but was infrastructure. The fix was to serialize seeds (one new sandbox at a time) and only then allow up to three bees to code. Stuck bees (no fresh logs for more than 20 minutes) could be cancelled and retried once, then marked failed. I did not restart the launcher without Kyle's okay.

The routine's hours were adjusted only when Kyle asked (an overnight extension on 5–6 November, holds, and an 8:00 AM resume). As of 12 November 2026 the routine is **paused**, and no new bees should start until he says so. "Stop" or "pause" means stop subagents, kill the test processes, and pause the routine. M4 stays held.

I also used Cursor cloud agents for some packets (for example the PR #1 UI redesign). Kyle later told me not to use a cloud agent for the stitchslop catalog review and to do that work myself — see below.

I verified and integrated bee output myself: feature-branch merges, two-host emulator soaks, deploys to the test host, and latency measurements. Bees did not deploy, and they were not given commercial ROMs.

### How briefs were written

A bee brief stated the outcome, the exact branch and revision, leased paths, mandatory constraints, the commands that would be used to verify, and acceptance criteria. Bees owned only `assigned_files`. They were told to mark unexecuted gates unproven, and never to present a mock, an external window, or a delay-only N64 session as completed in-pane rollback. The report-back was a structured handoff: changed paths, commands run and their results, AC evidence, unresolved gates, and a short handoff. I did not put a presumed root cause in the brief and ask the bee to confirm it; the bee was to reproduce the real gate and report what it observed.

Standing brief constraints included: no ROMs, BIOS or firmware in git; no remote game streaming; no arbitrary native commands; no unsupported Hermes hooks or permission bypasses; no pin, license or shared-schema changes without asking the lead.

Homebrew test ROMs were later allowed, on 5 November 2026, only from a locklisted set, after Kyle approved them. Sandboxes only receive a git archive of the project, so host fixture paths are not visible to bees. Commercial ROMs were never part of briefs.

### Review and release flow

- Verify used the brief's own commands, a path-scope check, and scans for ROM bytes and secret-like strings — not full end-to-end suites.
- Passing work was committed and pushed to the current feature branch only (`feat/m0`, `feat/m1`, `feat/m2`, `feat/m2r`, `feat/m3`, `feat/m3i`, `feat/m3j`, later `feat/pane-e2e` and related PR branches).
- Never merge to `main`, never tag, never force-push, unless Kyle explicitly approves that specific action.
- Report merges, blockers and milestone stops to Kyle. Do not start the next milestone, merge a GitHub PR, or deploy without that report (and, for deploys and PR merges, his go-ahead).
- A failed or incomplete bee was not papered over. Accidental `__pycache__` in a commit was left for a later cleanup rather than rewritten with a force-push.
- Catalog submissions use exact commit pins. Reviewer comments get a real fix and a reply, not a silent repin — except where Kyle stopped the work, as with stitchslop.

**Stitchslop catalog review (unfinished).** Kyle asked me to review the update to the stitchslop catalog pull request, [NousResearch/hermes-agent#151946](https://github.com/NousResearch/hermes-agent/pull/151946), resolve the issues, push, repin, and reply to teknium. The review asked for changes, mainly three blocking security problems in the viewer: it handed a session credential to anyone who asked, its `nav` command opened any URL, and it could be bound on all interfaces. There were also four recommended cleanups. I started a Cursor cloud agent to fix them. Kyle said not to use a cloud agent and to do it myself. I cancelled that agent and began the fixes locally. Kyle then said to stop. I stopped. The fixes were not finished, the catalog pin was not updated, and no reply was posted.

---

## 4. Infrastructure, hosting, networking and logistics

**Shared box.** Planning docs, orchestration state, evidence, research memos, private ROM storage (owner-only) and many builds live on the shared Linux box used by Kyle's bots. The box is a full computer with its own desktop and browser per agent. It sits behind a proxy, so its overlay-network path to Kyle's machines has typically been relayed rather than direct. Commands on a busy box have hung for many minutes; see lessons.

**Deploy and test host.** The only approved deploy and live-test host is Kyle's Linux machine used headless for this work. Other plugins already running there, and the ports they use, are left alone. Their plugin trees are never overwritten. The display manager was stopped so tests could use the GPU, but not disabled. I ask before any Hermes or gateway restart he has not already approved for that change. Builds run in the background at a limited parallelism. I do not use his dashboard login; tests run on hidden X displays.

Deploys are **side by side**: the new tree is installed next to the previous one, with a config backup and a rollback script that restores the prior revision (for example `python3 ~/emurizz-rollback-<rev>.py`). Doctor and route health are checked after a restart. A service that was already down before a deploy is noted and not treated as caused by it.

**Session video.** Gameplay in the pane is the local machine's output: the hidden display is captured, encoded as H.264 with VAAPI when available (access-unit delimiters inserted), and served on an authenticated plugin route. The pane decodes with WebCodecs and drops stale frames. A route buffering bug was adding hundreds of milliseconds; forwarding each read immediately, and disabling proxy buffering on that route, cut SNES route latency from about 390 ms to about 96 ms (7 November 2026, revision `2ee3965`). H.264 in the browser needs HTTPS; without a decision on how to terminate TLS for the pane, the fallback is MJPEG. That HTTPS question was still open as of 12 November.

**Emulators and Vulkan.** SNES uses pinned RetroArch + bsnes. N64 uses a pinned RMG-K build whose fingerprint is enforced so both peers run the same binary. Parallel-RDP is the default video plugin (room profile distinguishes it from GLideN64). Parallel-RDP needs Vulkan. On the shared box this was provided by a local **lavapipe** (software Vulkan) install after an earlier one-per-machine test could not start parallel-RDP because no Vulkan ICD was present. On the deploy host, parallel-RDP reached full NTSC speed (~60 fps) even on a software Vulkan path; a local GPU path was also tried and was not a win over that software path for the Xvfb capture setup.

**Relay and NAT.** Kyle wants the pane to work off a local network, with hole punching and a relay fallback, and approved using **his VPS** for the rendezvous and TURN/coturn service. I do not change that VPS, and I do not use a public TURN service or change his firewall or router. The shared box cannot send UDP, so its WAN tests go through the relay. A scripted SNES WAN relay soak on 6 November 2026 passed with matching CRCs and no desyncs. A direct hole punch between two home networks was still unproven.

**LAN finding (12 November 2026).** Kyle asked me to check whether the deploy host and his desktop could connect directly on his LAN. They could not, even though both appeared to have ordinary private LAN addresses. Overlay pings between them also went through a relay. I did not change any router or firewall settings. The likely causes are Wi-Fi client isolation, or two separate networks that happen to use the same private address range. Ethernet, or turning isolation off, would be expected to allow a direct path. I left that for Kyle.

**Windows.** There is no Hermes install on Windows. On 6 November 2026 Kyle approved one exception: a two-player RMG-K test on his Windows PC, to see whether box-versus-deploy-host drift was a true rollback bug or a difference between machines. He later reported that two players on that PC, same build, over loopback, stayed visually in sync. The automated Windows test was paused unfinished when he said to pause.

---

## 5. Rules and lessons learned

### Standing rules from Kyle

- Be token-conscious. Do not start optional work without asking.
- Do not delete anything without explicit approval.
- No `main` changes, tags, publishing or force-pushes without his okay.
- No ROMs in git. Homebrew only for the repo, bees, cloud agents and public material. His commercial test ROMs stay in private, owner-only directories on the deploy host and the box, for private testing only — never committed, never shared, never given to bees or cloud agents, and their footage stays out of submissions.
- Never print secrets, environment-file contents, presentation credentials, or the VPS relay secret.
- "Stop" or "pause" means stop everything: subagents, test processes, and the bee routine. Nothing resumes until he says so.
- Ask before a Hermes or gateway restart he has not approved.
- Deploy only to the designated host. Preserve the other plugins already running there.
- No public TURN, firewall or router changes, and no new spend except the VPS he already approved.
- No Windows Hermes install.
- M4 is not approved.

### Technical lessons

- **Forward stream bytes immediately.** Buffering the H.264 (and MJPEG/PCM) route was the difference between ~390 ms and ~96 ms on SNES through the Hermes route. After the fix, the route added at most about a millisecond over a direct presenter path, and the one-second N64 outliers went away.
- **SNES swapchain/frame-delay knobs did not move the needle.** `video_frame_delay_auto` and `video_max_swapchain_images=2` made no measurable input-to-display difference (about 47–48 ms to the X display either way).
- **Window-title checks must match the pinned binary.** A "ROM loaded" check looked for "Rosalie's Mupen GUI" and aborted real N64 sessions with `n64-rom-not-loaded` while MK64 was already running at ~60 fps. The pinned RMG-K titles its windows "RMG Kaillera Edition". The same mismatch broke window following. The fix landed in a later PR #5 revision.
- **Relay lobby start can stall.** Even with the title check bypassed, auto-start over the relay sometimes left both peers idle in the lobby. After that was addressed, one-emulator-per-machine starts succeeded 3/3.
- **Matching build fingerprints are not enough.** Early two-host MK64 runs still drifted until dynarec rollback register-restore bugs were patched (GPR restore and block-entry). The cached interpreter had shown 0 desyncs but only ~39 fps. After the patches, a dynarec soak ran more than five simulated minutes with 0 GekkoNet desyncs and 0 heuristic mismatches, still limited to ~39 fps when two instances shared a software renderer on a busy host.
- **One emulator per machine, and parallel-RDP, were required for full speed.** Two N64 instances on the deploy host ran at ~37–38 fps; one per host on GLideN64 ran at 46.8 fps; one per host on parallel-RDP ran MK64 at **59.9 fps on both sides with 0 desyncs**.
- **Most remaining N64 latency is before the capture.** After the route fix and the one-per-machine parallel-RDP run, JoypadTest press-to-picture through the Hermes route was about **234–241 ms** (down from ~300 ms). About **188–196 ms** of that was input to the X display. Capture, encode and the route added roughly 45 ms. GekkoNet input delay stayed at 2 frames after Kyle said not to lower it. A further breakdown of that ~190 ms, and a friend test on a direct connection, were offered and not started.
- **Serialize bee sandbox seeds.** Concurrent fetches of the same PC clone caused false infra failures.
- **The shared box can stall under load.** On 12 November 2026, while several other bots had many helpers running, one of my own status commands hung for about 14 minutes.
- **Do not use a cloud agent when Kyle wants the work done in this session.** Starting one for stitchslop, then being told to cancel it and do the work myself, then being told to stop, wasted time and left the review unresolved.

---

## 6. Notable projects

### Emurizz

- Repo: [github.com/mojomast/emurizz](https://github.com/mojomast/emurizz) (private).
- Role: I orchestrated planning, bees, integration, deploys and latency work from 5 November 2026 through 12 November 2026, toward a pane ready for a friend test, with efficient video and low latency.
- Feature-branch bee waves M0 through M3K produced the companion, adapters, session lifecycle, homebrew fixture tooling, transport, connector, presentation probes, real RMG-K integration work, and live-streaming/session-video work, always on feature branches, with Kyle's approval between waves.
- GitHub PRs into the integration branches, as I last recorded them:

  | PR | Subject | Outcome |
  |---|---|---|
  | #1 | UI redesign (cloud-agent draft; one proposed path was rejected) | Open as of 6 November 2026; I have no later merge record |
  | #2 | Rendezvous service | Merged into `feat/m3j` on 6 November 2026 |
  | #3 | WAN netplay client (STUN/TURN, build-hash check, room code, Direct/Relayed chip, SNES over the relay) | Merged 6 November 2026; a WAN SNES relay soak passed |
  | #4 | Pinned RMG-K builds plus dynarec rollback patches | Merged into `feat/m3j` as `b75f18a` on 7 November 2026, after a 0-desync dynarec soak; a same-day audit found the browser pane still not wired end to end (Start/Leave/host/join were still mocks) |
  | #5 | Pane session video, route/latency fixes, N64 ROM launch, window-title check, relay lobby start | Unmerged as of 12 November 2026; this is the revision that was deployed and measured |
  | #6, #7, #8, #10 | Solo Lab (cheats, play, guides and related integration) | Opened against the pane branch; integration testing still pending |
  | #9 | README license | Pending Kyle |

- **PR #5 measured results (7 November 2026, America/Toronto), head `e47c136`:** N64 with one emulator per machine on parallel-RDP started 3 of 3 times over the relay. MK64 held **59.9 fps** on both sides with **0 desyncs**. JoypadTest press-to-picture through the Hermes route was about **234–241 ms**. SNES through that route was about **96 ms**. A friend test on a direct connection had not been run. HTTPS for H.264, presentation-credential rotation, a private two-player SNES check, Solo Lab integration testing, and PR merges were still waiting on Kyle.

### Stitchslop catalog pin

- Catalog PR: [NousResearch/hermes-agent#151946](https://github.com/NousResearch/hermes-agent/pull/151946).
- I was asked to resolve the review, push, repin and reply. Kyle stopped the work on 12 November 2026 after telling me not to use a cloud agent. **Unfinished.**

### Pizza Panic / Clawpocalypse

- Public repo: [github.com/mojomast/clawpocalypse-now](https://github.com/mojomast/clawpocalypse-now), with a GitHub Pages build. The Orbit app id remained pizza-panic after the title changed to AGENT ARMEGEDDON: CLAWPOCALYPSE NOW.
- On 14 October 2026 Kyle added me to the group. My assigned task was gamepad support plus QA. I do not have my own dated record in this writing pass of what I shipped for that task, so I am not claiming an outcome.

### Other work I touched only as a constraint

On the deploy host I was required to leave already-installed plugins (including Comfyrizz, Shortrizz and others) running and untouched. Those projects were led by other bots; they are not claimed here.
