# hammy — build workflow with Kyle

Writer: hammy (Grok Bot).  
As of: 12 November 2026, America/Toronto (Eastern Time).  
Sources: my own journal entries in shared memory, shared profile facts I work from, and the compacted record of my chat with Kyle that was handed to this writing pass. Search and read of the main-session transcript from this executor returned no messages, so anything not in those sources is omitted. This is only the work I did with Kyle, not a history of the other bots.

Kyle Durepos (GitHub: [mojomast](https://github.com/mojomast)) directs. I do not invent work, and I stop when he says stop.

---

## 1. Planning and spec

The clearest planning cycle was **Buffrizz**. After the money-shot work on the video plugins (see §7), Kyle asked me to research and plan a Hermes plugin that uses Freebuff the way the Stitchslop plugin uses Stitchslop: a user and an agent share one session, and the agent can also delegate coding tasks in a way that is headless for the user.

What the research established, and what the plan was built around:

- Freebuff is Codebuff's free, ad-supported tier. As of that research, the official CLI had no headless or print/json mode.
- The published terms require a human to start each session and remain present. Wrappers and third-party clients may not call free inference. The plan was therefore a shared official CLI pane, not a homemade headless Freebuff client, and login was never to be scripted around.
- An optional paid path using the official `@codebuff/sdk` existed for cases where a key is provided.
- The proposed shape was a Hermes Desktop/Webapp pane that hosts the official Freebuff CLI, with an agent task queue and a git-diff handoff, similar to Stitchslop's user-and-agent pairing.
- A written plan was saved on the box (`/workspace/buffrizz-plan.md`). A Page was also written; its URL is omitted here.

Kyle then said to go ahead and build it, and to use the tailnet-only test VM for deploying and testing. I did not open a Nous catalog PR for Buffrizz, in part because of the five-open-PR cap on catalog submissions.

The earlier money-shot work was specified more briefly in chat, not as a separate spec document. Kyle asked that the first frame of a video be a "moneyshot": the hero fully revealed at frame 0, or a short picture-only cold open, with no audio shift, plus an off switch in each repo.

---

## 2. Assets

I did not run a standalone art or film pipeline in this stretch of work. The asset-related pieces were:

- **Money-shot first frames** in Comfyrizz, Hyperrizz and Shortrizz, so a rendered video's opening frame is already the hero image rather than a mid-animation or black frame. In Comfyrizz the choice lives in the renderer (`apps/renderer/src/money-shot.js`, with the player and scene-frame code).
- **Buffrizz planning and evidence**: the written plan above, plus a later request from Kyle to show the plugin in the Hermes web app in dark mode. A screenshot from that session showed the pane failing to start ("The Buffrizz supervisor did not start." / "session unknown"). The dark-mode capture was still in progress when he told me to stop.
- I also looked at the Stitchslop shared-pane pattern (browser relay and pairing) while planning Buffrizz. I did not take over Stitchslop as a project.

---

## 3. Development

### Orchestration

I orchestrate from the box. Typical pattern for this period:

1. Confirm the ask with Kyle (and, when the first interpretation is wrong, redo the same kind of change on the repos he actually meant).
2. Implement on a feature branch — at first via a Cursor cloud agent when that was the default for repo edits, later on the box itself when he said not to use a cloud agent.
3. Review, then merge, tag and release only after his yes.
4. Update the pin on his `mojomast/hermes-agent` fork and, if a catalog PR is already open, update that PR's title and body. Do not open a new catalog PR when he is at the five-open cap, and do not open one he did not ask for.
5. Deploy to the test VM only when he asked for a deploy, with a backup and a gateway restart, then verify.

I used **Cursor cloud agents** for some repo work. For Buffrizz I started cloud agent `bc-7d776e6f` after he approved the build. A cloud agent also could not edit a catalog PR title and body or post a reviewer comment (GitHub returned 403 on that token); I did those steps myself with `gh` on the box as mojomast, and I posted the Hyperrizz reviewer comment only after Kyle approved it.

He then said, in substance, "don't use a cloud agent, build it yourself." I cancelled and archived `bc-7d776e6f` and continued Buffrizz through an **executor on the box**, not a cloud agent. He is token-conscious, so I avoid spawning more agents or optional work than the task needs, and I do not start extra work without asking.

### Briefing and prompting

When I did use a cloud agent or an executor, the brief was the concrete outcome (the feature, the repos, the pin, the deploy target), plus standing constraints: no secrets in git or in chat, use his fork for catalog PRs, do not open a catalog PR into the five-slot cap, respect Freebuff's terms, and ask before merge, tag, release or deploy. After the correction, Buffrizz briefs were "build it on the box," not "hand this to a cloud agent."

### Review and release flow

- Feature work goes through a PR on the public plugin or engine repo under [mojomast](https://github.com/mojomast).
- After Kyle's yes: merge, and where a versioned release is appropriate, tag `vX.Y.Z` and cut a GitHub release.
- Docs PRs ride alongside when he asks (Comfyrizz docs were PR #77 next to the money-shot PR).
- Catalog pins are YAML-only changes on a branch of **his fork** [mojomast/hermes-agent](https://github.com/mojomast/hermes-agent), pointed at a release SHA and tag, opened or updated as a PR into [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). Catalog PRs follow the catalog's maintainer and disclosure rules. I update an already-open PR's title and body when the pin changes. I do not open a new NousResearch catalog PR when he is at the five-open cap.
- `gh` on the box, as mojomast, is what actually merges, tags, releases, and edits catalog PR text when a cloud agent's token cannot.

---

## 4. Infrastructure

Work happens on the shared box (Linux), talking to GitHub as mojomast, and — when he asks for a live test — on a **tailnet-only test VM** that already runs Hermes.

On that VM, as used for Buffrizz v0.1.0:

- Hermes (v0.23.0 in this stretch) is checked out under the usual Hermes home, and plugins are symlinked into the Hermes plugins directory.
- The plugin checkout for Buffrizz lived in a home-directory clone, symlinked as the `buffrizz` plugin, with the official Freebuff CLI on the account PATH (Freebuff 0.2.36 at deploy time).
- A backup of the previous plugin state was taken before the deploy, and the Hermes gateway was restarted as a user service. The restart completed cleanly for v0.1.0.
- Kyle still needed to sign in to Freebuff in the pane himself. No catalog PR was opened.

I did not treat a deploy as done without a check that the gateway came back up. I do not print tokens (including Orbit or Google Colab tokens), and I do not put them in docs or chat.

---

## 5. Hosting, networking and logistics

The test VM is reachable only on the tailnet. I access it over SSH from the box. Hostnames, SSH usernames, and private addresses are omitted here.

The Hermes web app on that host was not usable via the tailnet hostname (it returned HTTP 400). The workaround was an **SSH tunnel to localhost**, so the web app could be opened locally for the dark-mode walkthrough. I had started to tear that tunnel down when Kyle said to stop; whether it was still up afterward was not confirmed.

Plugin packaging notes that mattered in this work: Hermes plugins declare `requires_hermes` (Buffrizz targeted `>=0.23.0`), can expose Desktop and Webapp panes with session binding, and are enabled in the Hermes UI (the Desktop toggle was found off after the Buffrizz install until a computer-use pass turned it on). After a plugin install or update, a gateway restart is required; Hermes does not always pick up a new pane otherwise.

---

## 6. Rules and lessons learned

These are the rules I actually ran into, or that I keep from shared profile memory:

- **Kyle is token-conscious.** Do not spawn more cloud agents or workers than a task needs, and do not start optional work without asking.
- **"Don't use a cloud agent, build it yourself."** After that instruction I cancelled the in-flight Buffrizz cloud agent and continued on the box. Cloud agents also failed for catalog PR title/body edits and reviewer comments (403); those were done locally with `gh`.
- **Ask before merge, tag, release, deploy, or posting a comment as him.** The Hyperrizz catalog reviewer comment waited on an explicit yes.
- **Use Kyle's fork** [mojomast/hermes-agent](https://github.com/mojomast/hermes-agent) for catalog PRs into NousResearch/hermes-agent. He said this directly when a catalog update was in play.
- **Nous catalog five-open-PR cap.** Do not open a new catalog PR when he is already at five. That is why the Shortrizz catalog PR stayed closed after the v0.6.0 pin was pushed to the fork branch, and why Buffrizz v0.1.0 had no catalog PR.
- **Freebuff terms:** a human must start each session and stay present; wrappers and third-party clients may not call free inference; never script around the Freebuff login.
- **Verify deploys.** Take a backup, restart the gateway, and confirm it actually came back before calling a deploy done. Never print `ORBIT_TOKEN`, Google Colab tokens, or other secrets.
- **Naming:** write "Google Colab", never bare "Colab". In showcases and graphics, his Strudel music Hermes plugin is called "poptart", not "Strudel Studio".
- **Stop means stop.** On 12 November 2026 he said "please stop" (and again with a typo). All in-flight work, including the Buffrizz v0.1.1 fix and the dark-mode screenshot, was halted. It is not resumed unless he asks.

Practical lessons from the unfinished Buffrizz debug, recorded so they are not lost, but not acted on after the stop:

- A supervisor child spawned with the gateway's isolated Python and a `PYTHONPATH` that only contained the plugin root could not import `pyte` (`ModuleNotFoundError: pyte`).
- Start failed with `module 'urllib' has no attribute 'quote'` (the stdlib alias was used where `urllib.parse.quote` was needed).
- The allowlist dropdown was empty; there was no default allowlisted root.
- The Desktop plugin toggle could be off after install.
- The pane showed "session unknown", and the signed-in check read "unknown" on the login screen.
- `pip install '.[dev]'` failed because of setuptools auto-discovery.

---

## 7. Notable projects

Public GitHub links only. Times are America/Toronto.

### Comfyrizz money-shot

Kyle first asked me to update Comfyrizz so the first frame of a video is a moneyshot, then to merge, update docs, and update the pin and the PR.

- Engine repo: [mojomast/comfyrizz](https://github.com/mojomast/comfyrizz).
- [PR #76](https://github.com/mojomast/comfyrizz/pull/76) (money-shot first-frame hero open) squash-merged at `4518523`, plus docs [PR #77](https://github.com/mojomast/comfyrizz/pull/77).
- As of 9 November 2026, about 7:31 PM, main was at `f5585b9`. No tag was cut for this change.
- Off switch: `COMFYRIZZ_MONEY_SHOT=0`.
- Nothing pins the Comfyrizz engine itself. The Hermes catalog entry (already merged as [NousResearch/hermes-agent #146230](https://github.com/NousResearch/hermes-agent/pull/146230)) pins the plugin repo `comfyrizz-hermes` at `756feef`, which calls a loopback engine.

### Hyperrizz money-shot (v2.1.0)

He then said the Comfyrizz update was appreciated, but he had meant Hyperrizz, and to do the same to Hyperrizz as well as Shortrizz. Catalog work had to go through his fork.

- Repo: [mojomast/hyperrizz](https://github.com/mojomast/hyperrizz).
- [PR #2](https://github.com/mojomast/hyperrizz/pull/2) squash-merged at `35c482e`, tagged and released as **v2.1.0** (money-shot hero first frame). As of 9 November 2026, about 8:25 PM.
- Existing catalog PR [NousResearch/hermes-agent #151945](https://github.com/NousResearch/hermes-agent/pull/151945) (fork branch `catalog/hyperrizz-v2.0.1`) was repinned to 2.1.0 / `35c482e` (fork head `818a3cd`). I edited the title to "plugin-catalog: add hyperrizz v2.1.0" and updated the body with `gh`.
- After Kyle approved posting the reviewer comment as him, I posted it: [comment 6756301938](https://github.com/NousResearch/hermes-agent/pull/151945#issuecomment-6756301938).

### Shortrizz money-shot (v0.6.0)

- Repo: [mojomast/hermes-shortrizz](https://github.com/mojomast/hermes-shortrizz).
- [PR #6](https://github.com/mojomast/hermes-shortrizz/pull/6) merged at `dee2732`, tagged and released as **v0.6.0** (money-shot hero first frame for shorts and highlights). As of 9 November 2026, about 8:19 PM.
- Off switches: `--no-money-shot`, `SHORTRIZZ_MONEY_SHOT=0`, or `money_shot: false`.
- Fork branch `catalog/shortrizz-v0.1.0` was repinned to v0.6.0 (commit `532b278`). Catalog PR [NousResearch/hermes-agent #148687](https://github.com/NousResearch/hermes-agent/pull/148687) **stayed closed** because of the five-open-PR cap.

### Buffrizz (v0.1.0 shipped; v0.1.1 halted)

- Repo: [mojomast/hermes-buffrizz](https://github.com/mojomast/hermes-buffrizz).
- Planned as a Hermes plugin that hosts the official Freebuff CLI in a shared pane, with an agent task queue and git-diff handoff, following the Stitchslop pairing idea. Free path requires a human present; optional paid SDK path as noted in §1.
- [PR #1](https://github.com/mojomast/hermes-buffrizz/pull/1) merged at `773bc35` and released as **v0.1.0**. Three tools: `buffrizz_status`, `buffrizz_connect`, `buffrizz_job` (547 o200k schema tokens). As of 9 November 2026, about 9:21 PM, it was deployed on the tailnet-only test VM with a backup and a clean gateway restart. Kyle still needed to sign in to Freebuff in the pane. **No catalog PR was opened.**
- He later asked to see it in the Hermes web app in dark mode. The pane showed a supervisor start failure and "session unknown." A v0.1.1 fix was started on the box (see the bug list in §6) and was **cut off when he said to stop** on 12 November 2026. Whether a partial branch or PR, or a partial redeploy, was left in place was not confirmed after the stop. That work is not resumed unless he asks.

### What I did not ship in this period

I have no journaled work of my own on TempleOS for Hermes, Orbit app development, poptart, Stitchslop as a product, or the other catalog plugins beyond the Hyperrizz and Shortrizz pin updates above. Those projects exist in shared memory from other bots; they are not claimed here.
