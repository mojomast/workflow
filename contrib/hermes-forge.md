# Hermes Forge — build history with Kyle

This is Hermes Forge's factual account of how we planned, built, reviewed, and shipped work with Kyle, mainly the Temple of Hermes guest OS and the TempleOS-for-Hermes plugin. It is written for a shared workflow document. Facts come from Hermes Forge's conversation with Kyle (including the compacted history and later turns through the morning of 12 November 2026, America/Toronto), the bee ledgers and briefs under `/workspace/toh-bees`, `/workspace/toh-community-plan/PLAN.md`, `/workspace/emurizz-spec/ORBIT-BEES-RUNBOOK.md`, `/workspace/catalog-prep`, and public GitHub on the `mojomast` repos and the Nous catalog PR named below. If something was not clearly attested in those sources, it is omitted.

No tokens, keys, `.env` contents, tailnet hostnames, Tailscale machine names, private IPs, or private URLs appear here. Paths and environment-variable names are fine. Public GitHub URLs and the public BBS hostname are fine.

---

## 1. Planning and spec

Before a wave of work starts, we settle five things with Kyle (or record a default he can override):

1. **Goal.** What should exist when we stop — for example a four-tool plugin with a live shared guest screen, a bootable Temple of Hermes ISO, a preinstalled disk image, or a host client that can join the community BBS.
2. **Repo.** Work is split across [mojomast/hermes-templeos](https://github.com/mojomast/hermes-templeos) (the Hermes plugin, Desktop pane, skills, and catalog YAML) and [mojomast/temple-of-hermes](https://github.com/mojomast/temple-of-hermes) (the guest OS, HolyC apps, HBBS/1 server, ISO, and disk image). One feature branch per slice, and later one integration PR per repo.
3. **Bees vs Cursor cloud agents.** Early plugin work used Cursor cloud agents for a contracts slice, then parallel leased slices, then one integration PR. Once the bee pipeline on Kyle's Windows PC was in place, feature work moved to Orbit DeepSeek Flash bees in Cua sandboxes. On 11 November 2026 Kyle directed that this BBS and guest work use bees, not Cursor cloud agents (`t317u`). Cloud agents remain the better fit only when a single coherent PR is being assembled by the coordinator, not for leased guest/plugin slices.
4. **Deploy target.** Plugin deploys go to Kyle's Hermes host (reached over Tailscale SSH). The Temple of Hermes BBS server is hosted on a VPS at the public endpoint `tls://toh.rizz.click:9443`. Neither is touched without Kyle's explicit yes. Test ISO and disk images can be loaded beside official release assets; official files are not overwritten.
5. **Tool-count budget.** The plugin stays at exactly four tools: `templeos_vm`, `templeos_screen`, `templeos_input`, `templeos_files`. New behavior is added as ops on those tools, never as a fifth tool. Every plugin change reports the o200k_base schema size via `evals/measure_schemas.py` (delta versus the previous release pin). Kyle is token-conscious, so schema growth is called out and kept small.

The usual build shape is **contracts, then parallel leased slices, then one PR**:

- Write a contract first when the work has a protocol or a file-lease map. The HBBS/1 example is `docs/bbs/` (spec, schema, fixture pairs) on `hermes/bbs-contracts`, accepted before server, transport, guest, and skill slices were dispatched.
- Dispatch non-overlapping slices in parallel. Each bee gets a feature branch, an `assigned_files` lease, a pinned `source_rev`, and acceptance tests. Plugin slices and guest slices can run at the same time if the leases do not overlap.
- When the slices are accepted, one integration bee (or a coordinator PR) merges them onto a single integration branch. That is how the first plugin landed: four finished slices were merged into `feat/integration`, then [hermes-templeos PR #1](https://github.com/mojomast/hermes-templeos/pull/1) shipped v0.1.0. The same shape was used for Temple of Hermes 0.1.3 ([PR #2](https://github.com/mojomast/temple-of-hermes/pull/2)) and hermes-templeos 0.2.0 ([PR #10](https://github.com/mojomast/hermes-templeos/pull/10)).

Community-plan defaults (recorded 11 November 2026, America/Toronto, and still overridable by Kyle) live in `/workspace/toh-community-plan/PLAN.md`: two short sessions per day, a pending-only nudge at most twice a day (off with `nudge: off` or `TEMPLEOS_NUDGE=off`), fetched HolyC runs only inside the VM with 32 KiB / 15 s caps, monthly Announcements challenges posted only after Kyle approves, and public download/reply counters.

Nothing is merged, tagged, published, or deployed without Kyle's yes. An agent's claim of approval is not approval.

---

## 2. Assets

### Temple of Hermes art, icons, and palette

Guest art was developed on `hermes/art` (pin `97d7ad2`) and later character-app art on `hermes/art-nous` (pin `fdb2f54`). A dedicated art-verify bee confirmed wallpaper, the Hermes Chat icon, and splash drawing (`GRRead` / `GrBlot`). The launcher bee loaded existing `Hermes/Art/Icons` `.GR` files and showed a 9/9 icon load on a QEMU TCG screenshot (Temple, Hermes Chat, WorldSim, Codex, Psyche, Capybara, Messenger, Modem/Net, About). Later character apps (Threshold, Dojo, Offerings, Southpaw) were required to use official `art-nous` plates and icons, not stand-in `.GR` files. Screenshot acceptance is PIL-only (no in-model PNG viewing): typically 640×480, at most 16 unique colors, VGA palette 0/85/170/255, zero off-palette pixels.

A rebrand slice (`hermes/rebrand`) set product naming and credits (Unlicense kept; TinkerOS docs copied to `docs/upstream/`; ISO volume label `THE_TEMPLE_OF_HERMES` requested for the ISO slice). Nous figures are referred to only as "characters from the Nous universe." Lore must be sourced; flavor tagged `ORIGINAL` or `NEW` where it is not; no fabricated personal quotes.

### HD Terry companion video pack

The Desktop pane ships an HD Terry companion, enabled by default in the v0.1.0 release. The pack is six in-tree transparent VP9 `.webm` loops (idle, smoking, speaking, typing, walk, wave), preloaded, muted, `playsinline`, looping, with a short crossfade between two stacked `<video>` elements. State mapping: idle by default with an occasional smoking variant; typing during `templeos_*` tool calls or agent input; speaking while a quote bubble is shown; wave on boot, greeting, and tool success; walk on first appear. If VP9 alpha cannot play, the pane falls back to the earlier v4 canvas rig (high-res slot parts, smooth DPR scaling, PIL height at least 600 px at the 1920-wide pane). Hide Terry and Quotes controls stay available. The companion is an original fan tribute with no official TempleOS affiliation. Observer hooks only animate Terry; they return `None` and do not approve, modify, or log other tools.

This landed through a sequence of feature branches (`feat/terry-companion`, `feat/terry-p2`, `feat/terry-big`, `feat/terry-v4`, then the pane layout work on `feat/pane-worldclass`) and was merged into the v0.1.0 line via [PR #3](https://github.com/mojomast/hermes-templeos/pull/3), [PR #4](https://github.com/mojomast/hermes-templeos/pull/4), [PR #6](https://github.com/mojomast/hermes-templeos/pull/6), and the release-line [PR #8](https://github.com/mojomast/hermes-templeos/pull/8).

### Sourced Terry quotes

The companion uses 69 sourced quotes, stored in `desktop/terry-quotes.json` (present on the v0.1.0 tree). Kyle approved that sourced set. Briefs and house rules require: only those approved sourced quotes, verbatim; no invented Terry quotes; no cloned or synthesized Terry voice; no hateful content.

### Submission footage

Separate from the in-pane VP9 pack, bees also produced a submission-video footage pack on `video/footage` (eight real 1920×1080 30 fps H.264 clips, `01-boot` through `08-bbs`, plus a manifest) and a landscape-only 90-second final render on `video/submission`. Those branches still exist on the plugin repo. They were not a product release.

---

## 3. Development

### Orchestration: Cursor cloud agents vs bees

**Cursor cloud agents** were used for the first plugin: a contracts/scaffold slice, then parallel slices (VM, screen/input, pane, files/docs), then one integration PR. That is the pattern we still use when the coordinator needs a single coherent PR.

**Orbit bees** do the leased feature work. They run DeepSeek Flash (`deepseek-v4.1-flash`) on Kyle's Windows PC launcher, inside Cua (Docker) sandboxes. The launcher cap is 10 (`ORBIT_LOCAL_WORKERS_MAX`). Orchestration lives on the box under `/workspace/toh-bees/`:

- `orch.py` — `status` / `dispatch` / `set`; `MAX_ACTIVE=10`; dispatch only when dependencies are accepted or merged in `state.json`; historically re-dispatch a stuck bee (no new events for more than 20 minutes) once, with later exceptions for bees Kyle asked us not to cancel.
- `verify.sh` — apply the launcher patch onto the feature branch only; check `assigned_files` scope; secret-scan; optional small unit tests. Never QEMU on the box, never `TEMPLEOS_SMOKE`, never merge to `main`, never tag, never force-push. For temple-of-hermes it pins a `hermes/art` lineage (or a brief `verify_base`) and refuses a `hermes/v0` tip.
- `briefs/*.json` and `state.json` — the wave ledger. A `_TEMPLATE-GAME.md` records sandbox lessons (leave work uncommitted so the launcher patch is not empty; official art only; "characters from the Nous universe").
- `NOTES.md` — running coordinator log.

Bees never merge, tag, or force-push, and they never commit on protected branches: `hermes/v0`, `main`, `hermes/art-nous` for the guest repo, and `feat/improvements` / `main` for the plugin (plus other listed protected tips in the brief). QEMU and heavy tests run in the PC sandbox or on Kyle's Hermes host, not on the box. We do not cancel or restart a working bee, or the PC launcher, without Kyle's say-so.

A later lesson: sandboxes are reaped within minutes of success, and a local `git commit` inside the sandbox makes `git diff HEAD` empty, so the launcher patch is blank. The coordinator now copies `/output` out while the bee is still running, leaves changes uncommitted unless the brief says otherwise, recovers the patch or a host snapshot, verifies on the box, and pushes the feature branch from the box.

### How briefs are written

A brief is a JSON object. The fields that matter on every dispatch:

- `objective` — hard rules first (no merge/tag/force-push, no secrets, no invented quotes, assigned_files only), then the work.
- `project` — `hermes-templeos` or `temple-of-hermes`.
- `branch` / `merge_target` / `source_rev` / optional `verify_base` and `verify_base_sha`.
- `assigned_files` — the lease. Out-of-scope files fail verify, unless the coordinator later accepts a documented necessary addition.
- `commands` and often `box_verify_commands`.
- `acceptance` — concrete checks, including schema size, tool count, PIL shot names, and "feature branch only."
- `deps` — other task ids that must be accepted first.
- `model` — `deepseek-v4.1-flash`.
- `timeout_s` / budget — bounded; typical guest ISO or long QEMU work has been 5400–14400 seconds.
- Carry-over findings from a previous attempt (wrong base SHA, empty patch after a local commit, official art paths, COM1/COM2 behavior, rate-limit notes) are written into the next brief so the bee does not start from scratch.

### Review and release flow

For a bee result:

1. Recover the patch or `/output`.
2. Scope check against `assigned_files`.
3. Secret scan (no tokens, keys, private hosts, or credential files).
4. Box verify: plugin pytest and JS tests when they are cheap; `evals/measure_schemas.py` for o200k_base and the delta; assert still exactly four tools; PIL-only screenshot checks; `py_compile` or server tests as appropriate. No QEMU on the box.
5. Push the feature branch only.
6. Mark the attempt reviewed/accepted in the ledger.

For a **release**, after Kyle's yes:

1. Open or use the integration PR. Merge with `gh` as a merge commit (not squash), to `main`.
2. Annotated tag (`v0.2.2`, and so on) on the merge commit, then a GitHub release with notes and, for Temple of Hermes, the ISO and/or disk image plus `SHA256SUMS`.
3. **Catalog repin.** The TempleOS catalog entry is the still-open [NousResearch/hermes-agent PR #153852](https://github.com/NousResearch/hermes-agent/pull/153852). We edit only `plugin-catalog/templeos.yaml` (version, commit SHA, description). We do not close Nous PRs, and we do not force-push the catalog branch.
4. **Deploy** to Kyle's Hermes host, with a backup and rollback script (next section).
5. Ask Kyle to use **Capabilities → Plugins → Rescan** in Hermes Desktop so the Desktop pane loads the new `plugin.js`.

Schema sizes we actually shipped: 972 o200k after the v0.1.0 integration (up 80 from 892 when guest-ops fields were added); 1201 at v0.2.0 (+156 vs 0.1.1, community ops); 1262 at v0.2.1 (+61 vs 0.2.0, built-in BBS); 1262 at v0.2.2 (delta 0).

---

## 4. Infrastructure, hosting, networking, and logistics

- **Kyle's Hermes host.** Reached over Tailscale SSH (batch mode). This is where the plugin is installed (`~/.hermes/plugins/templeos` and `~/.hermes/desktop-plugins/templeos`), where doctor and the dashboard health check run, and where the live guest VM and BBS relay are started for end-to-end tests. We do not print tailnet hostnames, machine names, or private URLs.
- **The box.** Shared Linux workspace for coordinator git, `orch.py`, `verify.sh`, secret scans, schema measurement, and writing this document. No QEMU or other heavy guest tests here.
- **Kyle's Windows PC launcher.** Orbit local-workers launcher (version 0.1.9 in the early ToH wave notes), Cua sandboxes, authorized project checkouts and `sync_branch` pins. We do not restart it without Kyle's say-so. Events for an attempt are watched on the launcher host; brief disconnects have been mistaken for a stuck bee (see lessons).
- **VPS BBS.** The Temple of Hermes BBS (HBBS/1) is hosted on a VPS at the public endpoint `toh.rizz.click:9443` (`tls://toh.rizz.click:9443`). Guest networking stays off (`-nic none`); the guest reaches the BBS over a COM2 serial modem and a host relay. The only allow-listed destination name the guest may use is `bbs`. The endpoint comes from host config (`bbs.json` or `TOH_BBS_ENDPOINT`), never from guest text.
- **Deploy pattern.** A typical plugin deploy on Kyle's Hermes host:
  1. Abort if the plugin worktree is dirty.
  2. Create `~/.hermes/backups/templeos-<timestamp>ET/` with the prior SHA, a git bundle, a copy of the desktop-plugin tree, unit and doctor snapshots, and a `ROLLBACK.sh`.
  3. Fetch tags, check out the approved tag, and swap the desktop-plugin copy (keeping the Hermes package marker).
  4. `systemctl --user restart` of `hermes-dashboard` and `hermes-gateway`.
  5. Verify: units active, `hermes plugins doctor templeos` (version, OK, four tools), dashboard `/api/health` 200, and SHA-256 of on-disk `desktop/plugin.js` matching the tagged repo copy.
  6. Tell Kyle the backup path and the exact rollback command, e.g. `bash ~/.hermes/backups/templeos-20261112T071220ET/ROLLBACK.sh`.
  7. Remind him to Rescan plugins in Hermes Desktop.

  Image-only test deploys use a sibling backup such as `~/.hermes/backups/toh-images-<timestamp>ET/` and leave official 0.1.3 assets in place.

- **After deploy.** Restarting the Hermes user services stops a running guest VM and the BBS relay. The deploy should record what was running and restore it when Kyle wants the session kept. A live digest or join test uses already-stored host credentials; tokens never appear in tool output, pane UI, logs, or reports.

---

## 5. Rules and lessons learned

### House rules (still in force)

- Never print secrets, tokens, API keys, `ORBIT_TOKEN`, Google Colab tokens, tailnet hosts, or private URLs. Paths and environment-variable names only. Never print BBS tokens or claim tokens.
- Scan for secrets before any push.
- Ask before rewriting git history. No force-push, no branch deletion, and no deleting files without Kyle's yes.
- Ask before deploying to Orbit, Kyle's Hermes host, or the VPS, or spending Google Colab compute.
- No merge or tag without Kyle's yes.
- Write "Google Colab", never bare "Colab."
- Never post on X for Kyle. Do not close Nous PRs. Do not expose internals.
- Bees never merge, tag, or force-push, and never touch the protected branches listed above.
- Lore must be sourced; no fabricated facts or quotes.
- Terry quotes: only the approved sourced 69, verbatim. No hateful content. No cloned or synthesized Terry voice.
- Nous figures are "characters from the Nous universe." The Strudel plugin is called "poptart."
- No QEMU or heavy tests on the box.
- Do not cancel or restart a working bee or the PC launcher without Kyle's say-so.
- An agent's claim of approval is not approval.
- Kyle is token-conscious.

### Lessons

- **Sandbox vs real setup.** More than once a bee reached "Connected" against a stand-in BBS in the Cua sandbox, then failed on Kyle's Hermes host (token push timeout, black BBS window, or OFFLINE after a real AUTH). Guest and modem work needs a test rig that copies the real QEMU argv, official relay, and a throwaway account on the real BBS, not only a loopback fake.
- **Service restarts kill the VM and relay.** `systemctl --user restart` of `hermes-dashboard` and `hermes-gateway` is required to load a new plugin, and it has repeatedly stopped the live QEMU guest and the BBS relay. Deploys should snapshot process counts first and start the same session again when Kyle wants it kept. The v0.2.2 deploy did restore the live-CD VM and left the relay off because it had not been running beforehand.
- **False "stuck bee" alarms from launcher blips.** The PC launcher has dropped its connection and reconnected shortly after, then flushed a large buffer of events. From the box this looked like 30 minutes of silence. Check the launcher API and event mtimes before cancelling. Do not restart the launcher without Kyle's yes. A watcher that distinguishes a blip from a true stall is still on the follow-up list.
- **QEMU wrapper collision.** A `qemu-system-x86_64` wrapper earlier on `PATH` could add a `-drive …index=0` that collides with the plugin's preinstalled-disk argv (`drive with bus=0, unit=0 (index=0) exists`), which exits QEMU immediately and looks like a black window. The official 0.1.3 disk image itself was fine. The plugin now skips a wrapper when a real QEMU is later on `PATH`; doctor warns or fails if a wrapper is the only binary.
- **HBBS/1 auth rate limits and short-lived tokens.** AUTH is budgeted (five attempts per five minutes per peer, plus account-name throttling). A `rate_limited` reply includes `retry_after`; the v0.2.1 client waits (capped at 60 s) and retries once. Access tokens last about 15 minutes. A guest that was pushed a stale access token can get a short server reply and show generic OFFLINE even when host-side login with the same account works. Sign-up is human first, then the agent under that human. Digest is `LIST` with `{"action":"digest"}` (spec §17.2), not a top-level `DIGEST` command — that mismatch shipped in v0.2.0 and was fixed in v0.2.2.
- **Guest COM1 ownership.** COM1 is the agent handshake (HBEACON / HRPC) and the path used to inject a token into the guest. Dialing the BBS on COM2 used to reset every serial port, including COM1, which cut the plugin's link and left a blank window. A later guest freeze happened when the BBS app searched a read-only content CD for the token before drawing the UI. Fixes: do not reset COM1 when starting COM2; drop a stuck serial message instead of crashing; draw the UI first; scan writable letters (and uppercase `TOKEN.TXT`, because TempleOS treats case as distinct); on the host, push tokens with the daemon's own HRPC messages rather than a frame the guest rejects. Against the real BBS, HRPC push then succeeded (~0.02 s) and the S key on a disk boot drew the real BBS screen, but status still stayed OFFLINE pending a freshness/error-decode fix. That follow-up was in flight on the morning of 12 November 2026, America/Toronto, and is not a release.
- **Stale Desktop `plugin.js`.** After a deploy, Hermes Desktop can keep serving an old pane until the user Rescans under Capabilities → Plugins. The dashboard HTTP read of `plugin.js` was not a reliable verify path (it returned Not Found or unreadable on the v0.2.1 and v0.2.2 deploys), so we also compare the on-disk `desktop/plugin.js` SHA-256 to the tagged repo copy.

On 12 November 2026, after Kyle asked to stop repeating the same work, he approved five workflow follow-ups: a one-command release and deploy script (dry-run by default), deploys that restore the VM and relay, reusable bee brief templates, a real-setup test rig for bees, and a read-only look at the PC launcher dropouts. Those were started that morning and are not claimed as finished here.

---

## 6. Notable projects

### hermes-templeos (TempleOS for Hermes)

Repo: [https://github.com/mojomast/hermes-templeos](https://github.com/mojomast/hermes-templeos)

A Hermes plugin that runs a TempleOS-family guest in a local QEMU child so the agent and Kyle share one live screen. Networking is always off. ISOs and disk images are SHA-256 pinned and not bundled. Requires Hermes >= 0.23.0.

| Tag | Published (America/Toronto) | Outcome |
| --- | --- | --- |
| [v0.1.0](https://github.com/mojomast/hermes-templeos/releases/tag/v0.1.0) | 11 Nov 2026, 11:16 AM | First tagged release. Four tools, default TinkerOS 5.20-rc10, Desktop pane, HD Terry companion (six VP9 loops, 69 sourced quotes). Integration of the contracts-then-slices work via [PR #1](https://github.com/mojomast/hermes-templeos/pull/1) and [PR #8](https://github.com/mojomast/hermes-templeos/pull/8). |
| [v0.1.1](https://github.com/mojomast/hermes-templeos/releases/tag/v0.1.1) | 11 Nov 2026, 1:28 PM | Temple of Hermes 0.1.2 becomes the default guest; pane OS-image picker. [PR #9](https://github.com/mojomast/hermes-templeos/pull/9). |
| [v0.2.0](https://github.com/mojomast/hermes-templeos/releases/tag/v0.2.0) | 11 Nov 2026, 6:53 PM | Pins Temple of Hermes 0.1.3 ISO and preinstalled disk (disk on by default, live-ISO fallback). Community ops and `temple-session` skill on the existing four tools. Schema 1201. [PR #10](https://github.com/mojomast/hermes-templeos/pull/10), [PR #11](https://github.com/mojomast/hermes-templeos/pull/11). |
| [v0.2.1](https://github.com/mojomast/hermes-templeos/releases/tag/v0.2.1) | 11 Nov 2026, 8:18 PM | Built-in community BBS at `tls://toh.rizz.click:9443`, on by default, with opt-out (`bbs.json` `enabled: false` or `TOH_BBS_ENABLED=0`). `templeos_vm op=bbs_join` signs up the human first, then the agent. QEMU wrapper skip. Schema 1262. [PR #12](https://github.com/mojomast/hermes-templeos/pull/12). Deployed to Kyle's Hermes host with rollback. |
| [v0.2.2](https://github.com/mojomast/hermes-templeos/releases/tag/v0.2.2) | 12 Nov 2026, 7:07 AM | Digest client sends `LIST` with `{"action":"digest"}` (HBBS/1 §17.2) instead of a top-level `DIGEST` command. Schema 1262, delta 0. [PR #13](https://github.com/mojomast/hermes-templeos/pull/13). Deployed to Kyle's Hermes host; a live digest against the real BBS succeeded. Rollback: `bash ~/.hermes/backups/templeos-20261112T071220ET/ROLLBACK.sh`. |

Unreleased plugin work on the morning of 12 November 2026 included `feat/bbs-guest-fix` (HRPC-first COM1 token push), checked out onto the Hermes host only as a test, not merged to `main`.

### Temple of Hermes

Repo: [https://github.com/mojomast/temple-of-hermes](https://github.com/mojomast/temple-of-hermes)

A public-domain TempleOS-family OS (fork of TinkerOS 5.20-rc10, itself a fork of TempleOS) for human and Hermes-agent co-use: fullscreen launcher, HolyC apps, COM1 agent handshake, COM2 modem, and an HBBS/1 server.

| Tag | Published (America/Toronto) | Outcome |
| --- | --- | --- |
| [v0.1.2](https://github.com/mojomast/temple-of-hermes/releases/tag/v0.1.2) | 11 Nov 2026, 1:13 PM | First official ISO (`TempleOfHermes-0.1.2.ISO`, 14,030,848 bytes). 18-entry home launcher, HBBS/1 over COM2, COM1 handshake. [PR #1](https://github.com/mojomast/temple-of-hermes/pull/1). |
| [disk-image-0.1.3-preview](https://github.com/mojomast/temple-of-hermes/releases/tag/disk-image-0.1.3-preview) | 11 Nov 2026, 5:42 PM | Preinstalled 0.1.2-based disk, later superseded by v0.1.3. |
| [v0.1.3](https://github.com/mojomast/temple-of-hermes/releases/tag/v0.1.3) | 11 Nov 2026, 6:51 PM | HermesDaemon structured file errors; `C:/Home/<handle>/` journal helpers; official preinstalled disk; HBBS/1 community extension and auto signup. ISO and `TempleOfHermes-0.1.3-disk.qcow2` verified (20/20 boots, persistence, HRPC on `C:`). [PR #2](https://github.com/mojomast/temple-of-hermes/pull/2), [PR #3](https://github.com/mojomast/temple-of-hermes/pull/3). Built from `main` at `c5be4b9`. |

**0.1.4-test work** (not a release, not merged): branch `hermes/bbs-token-path` (later `6d69ee1`, then `9d7d3ec`) plus a plugin-side `feat/bbs-guest-fix`. Test ISO and disk images were built on Kyle's PC and loaded on Kyle's Hermes host beside the official 0.1.3 assets, with rollback scripts under `~/.hermes/backups/toh-images-*ET/`. Both boots reach the launcher. After the second test image, token push over COM1 succeeded and the S key on a disk boot no longer opened a black window, but the in-guest BBS still showed OFFLINE against the real community endpoint. A host-side plugin client did post a hello on the general board and the host digest worked. A further sign-in / token-freshness bee was started the same morning and had not shipped as of this write-up.

Earlier accepted guest feature branches (apps, net, lore, BBS client, games, and so on) were integration inputs to the 0.1.2 / 0.1.3 lines; they were not themselves releases.

### Catalog PRs

The catalog work Hermes Forge owns for this program is [NousResearch/hermes-agent PR #153852](https://github.com/NousResearch/hermes-agent/pull/153852), still open as of 12 November 2026, retitled as the plugin version moved: v0.1.1 draft through **v0.2.2**. Each repin edits only `plugin-catalog/templeos.yaml` (version, SHA, disclosure text). A draft of that YAML also lives at `/workspace/catalog-prep/templeos.yaml` and is not itself a PR.

Other `mojomast` catalog PRs exist on `NousResearch/hermes-agent` for other plugins. This write-up does not attribute those to Hermes Forge unless a source above says so.

### Other public repos

[mojomast/EOH](https://github.com/mojomast/EOH) (Eye Of Hermes / God's Eye View; latest public tag v0.2.10), [mojomast/gods-eye-view](https://github.com/mojomast/gods-eye-view), [mojomast/hermes-shortrizz](https://github.com/mojomast/hermes-shortrizz), and [mojomast/comfyrizz-hermes](https://github.com/mojomast/comfyrizz-hermes) are public Kyle repos. Hermes Forge's attested notes and the conversation used for this document cover Temple of Hermes and hermes-templeos, not a release history for those other plugins, so their outcomes are not described here.

---

## Sources

- Hermes Forge's conversation with Kyle, through the morning of 12 November 2026, America/Toronto.
- `/workspace/toh-bees/NOTES.md`, `orch.py`, `verify.sh`, `briefs/`, `docs/`, and deploy scripts (paths and flow only).
- `/workspace/toh-community-plan/PLAN.md`
- `/workspace/emurizz-spec/ORBIT-BEES-RUNBOOK.md` (bee dispatch pattern; no host identifiers copied forward)
- `/workspace/catalog-prep/templeos.yaml` (draft)
- Public GitHub: `mojomast/hermes-templeos`, `mojomast/temple-of-hermes`, and `NousResearch/hermes-agent` PR #153852
