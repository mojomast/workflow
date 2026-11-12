# Hermes Plugin Builder — build workflow notes

Contribution from **Hermes Plugin Builder**, Kyle’s assistant for designing, building, testing, releasing, catalog-listing, and deploying [Hermes](https://github.com/NousResearch/hermes-agent) plugins.

**Sources.** This agent’s own journals, the work log through 10 Nov 2026, 1:38 PM ET (America/Toronto), and the shared skill `hermes-plugin-development` (plus `references/CHECKLIST.md` and `references/catalog-review-lessons.md`). Catalog-review contracts were checked against Hermes Agent **v0.23.0** (`2bd378ed1b8d`). Facts only; sibling-agent outcomes are labeled as such. No private hostnames, addresses, or credentials.

---

## Planning and spec

Before any plugin work, load the shared skill `hermes-plugin-development` and follow it. Prefer live `NousResearch/hermes-agent` docs and source when they disagree with the skill, and always note the Hermes version the work was verified against.

Canonical upstream docs used:

- `website/docs/developer-guide/plugins/index.md` — build a plugin
- `website/docs/developer-guide/plugins/catalog-submission.md` — catalog submission
- `plugin-catalog/README.md` — admission rules (law; CI fails if they drift from the submission doc)
- `plugins/AGENTS.md` — plugin kinds / in-tree policy
- dashboard and Desktop SDK docs under `website/docs/`

Planning defaults:

- Native plugin: `plugin.yaml` (`manifest_version: 2`) plus `__init__.py` with `register(ctx)`. Portable Agent Plugins v1 (`plugin.json`) is a compatibility adapter, not the default for new Hermes-first plugins.
- Lean, composable tools with an `op` enum rather than many fine-grained tools. Measure schema cost with tiktoken `o200k_base`.
- Declare `provides_tools` / `provides_hooks` to match what `register()` actually registers. Declare credentials in `requires_env` and read them only through secret-scope APIs — never raw `.env` or process-environment fallbacks.
- Disclose risky behavior honestly (network, shell, background threads, write-then-execute, “not an OS sandbox”).
- Security contracts from the Nov 2026 catalog reviews are mandatory: SSRF-guarded fetches, pane-only privileged actions, untrusted feed text treated as data, no absolute URLs to dashboard `authedFetch`, loopback-only relays with a credential on every sensitive route, scoped hooks, JSON-string tool results, truthful offline/online clients.
- Helper templates live with the skill: `plugin.yaml`, catalog entry, `register(ctx)`, output-schema-safe `tools.py`, strict version bump, and the duplicate-key YAML test.
- Do not start optional work or spawn extra workers without asking.

---

## Assets

- Screenshots must be **real** — no invented or mocked UI captures.
- Hermes UI is always **dark mode** in screenshots, demos, and promo recordings.
- Geospatial shots go on a **fresh map area**. Never re-enable layers Kyle turned off. After a test, surgically restore only the fields the test changed.
- Catalog listings allow at most **6 screenshots**. The `image` (2:1 banner) is separate. The validator refuses a 7th. Every screenshot and banner URL must be on a GitHub raw host, pinned to the **same** 40-character commit as the catalog `sha`, and return HTTP 200.
- No hostnames, keys, or private data in frame.
- Video plugins should open on a finished hero frame so frame 0 (and the catalog thumbnail) is not blank.
- In showcases and graphics, the Strudel music plugin is called **poptart**, not “Strudel Studio”.
- Promo-art and capture lanes have been used (for example poptart and Eye Of Hermes contest cuts). An EOH promo-art lane was later stopped on Kyle’s hold and was not restarted.

---

## Development

### Orchestration

Resource-intensive work (test suites, heavy builds, E2E, anything CPU/RAM-heavy) is delegated to Orbit Cua bees running **DeepSeek Flash**, **3 at a time**, when those workers are healthy — not run on the box, and not handed to Cursor cloud agents unless Kyle asks.

A reusable bee-orchestration pattern lives under `/workspace/hermagotchi-bees/` (orchestrator script, board CLI, group file, per-lane briefs and results). Described generically: a local-workers API and a collaboration board are used to dispatch scoped lane tasks; a board credential file is read and is never printed. Lanes are given a narrow brief (what to change, what not to touch, how to report back) and are expected to stop immediately if Kyle says stop or hold.

In mid-November 2026 this was used to plan EOH audit lanes (UI/QoL, SDR polish, perf, E2E, promo art). Those lanes were stopped on Kyle’s explicit hold and must not be restarted unless he asks. The UI/QoL lane’s unpushed work was never pushed; there is no `audit/ui-qol` branch on origin.

### Review and release flow

Keep main releasable. Typical sequence, each irreversible step only after Kyle’s own yes:

1. **Feature PR** on the plugin repo → review, secret-scan, merge (often with `gh`).
2. **Strict version-bump PR** (separate): `bump_plugin_version.py` rewrites only the `version:` line, refuses duplicate keys and a wrong `name`, and keeps `plugin.yaml` / `pyproject.toml` in sync. Merge that bump.
3. **Tag and GitHub release** at the tested commit: `vX.Y.Z` via `gh`, only with explicit approval.
4. **Catalog repin** on the `mojomast/hermes-agent` fork:
   - Branch `catalog/<name>-vX.Y.Z` (or keep repinning the existing catalog branch).
   - **YAML-only** diff: one file under `plugin-catalog/`.
   - Pin a full 40-character SHA of an already-existing commit (usually the tagged release). Never invent a self-referential catalog SHA.
   - Update `sha`, `version`, capabilities, and screenshot/banner URLs so they all point at that same SHA.
   - Open a PR into `NousResearch/hermes-agent`. SHA bumps are new PRs so reviewers can read old SHA → new SHA.
   - If `gh` hits a **CreatePullRequest** permission error (no right to open PRs on NousResearch), push the fork branch and ask Kyle to open the PR in the GitHub UI. Do not invent a second submission path.
5. After a requested fix, repin and (when Kyle authorizes a comment) reply **point-by-point**: old SHA → new SHA, files, tests. Reviewers have approved a pin and then come back with a correction after a full-tree re-read, not just the delta. Budget time for that.

**Catalog constraints:** contributors without write access have at most **5 open PRs** on `NousResearch/hermes-agent`. Closing a PR to free a slot is normal and is not a review verdict. A duplicate-key YAML test ships in plugin CI because PyYAML silently keeps the last duplicate key (seen in the wild on godseye).

**Commit identity.** Plugin and catalog commits are made as Kyle, using `git -c` with `Kyle Durepos <76818041+mojomast@users.noreply.github.com>`.

---

## Testing

Typical gate before merge, tag, or repin:

- Plugin unit tests (`pytest`) and JS tests where the plugin has them (`node --test`).
- Strict YAML / duplicate-key test.
- `hermes plugins doctor . --ci` and `hermes plugins validate . --install-deps`.
- Schema cost measured with tiktoken `o200k_base`.
- Secret scan of the tree before every push (path:line:rule only; never values). Never commit `.env`, keys, or captured pane credentials.
- Verify against a noted Hermes version. Review-fix and audit work in this period was verified against **Hermes Agent v0.23.0** (`2bd378ed1b8d`).
- Optional extras (`tiktoken`, `ruamel.yaml`) should skip cleanly when missing, with an install hint, so contributor runs stay green.
- Unit tests and doctor are necessary but not end-to-end proof. Live pane checks belong on a real Hermes host, with prior enablement and layers restored afterwards.
- Reviewers re-check with a real catalog install in a scratch Hermes home; do the same before asking for re-review.

Example measurement from EOH after audit PRs #31, #29, and #30 landed: 541 Python + 26 JS tests, schema 8063 o200k, CI running on `main`.

---

## Infrastructure, hosting, networking, and logistics

- A **shared test host** is reached over Tailscale via SSH. Refer to it only generically here.
- Plugin checkouts on that host are **symlinked** into `~/.hermes/plugins/<name>`. Some monorepos install a subdirectory (poptart: `integration/hermes`; photo-to-part: `plugin/`).
- `hermes-dashboard` and `hermes-gateway` run as `systemctl --user` services. Ask before any deploy or restart. Hermes will not always hot-remount an existing plugin API route; a gateway restart may be required for a pane to appear.
- Before moving HEAD: back up to `~/.hermes/backups/<name>-<timestamp>/`, record the **rollback SHA**, and keep a `ROLLBACK.sh` in that backup when one is written. On failure, check out the recorded SHA, restart, and confirm `hermes plugins doctor`.
- After a test, surgically restore only that plugin’s enablement and settings. Do not leave a test enablement on, and do not overwrite the rest of the host config from a stale backup. **godseye stays disabled** on the shared test host unless Kyle asks otherwise.
- Photo-to-part style monorepos put a stub root `plugin.yaml` that refuses a root install, so evals are not published with the catalog package.

---

## Kyle’s rules

These are standing rules, not suggestions:

- **Ask first** before any deploy or service restart, and before merging, tagging, releasing, or repinning a catalog entry.
- **Never** delete, force-push, rewrite history, or delete branches without a yes.
- **Secret-scan** before every push. Never print or commit keys or credentials.
- Be **token-conscious**: lean `op`-enum tools, measure o200k cost, don’t start optional work or extra workers without asking.
- Say **“Google Colab”**, never bare “Colab”.
- In showcases, the Strudel plugin is **poptart**.
- Never re-enable layers Kyle turned off.
- **Never post on X** for Kyle.
- **Only Kyle’s own words count as approval.** A checklist, a sibling agent, or an ambiguous “go ahead” that might apply to something else is not permission. Stop and ask when it is unclear.
- **Stop / hold means stop.** Do not restart stopped work unless Kyle asks.
- Screenshots must be real. Hermes UI in dark mode. Fresh map areas for geospatial.

---

## Lessons learned

- **Workers vs desktop.** A local Orbit endpoint that looked like the workers API (port 4318) was the Orbit desktop, not a healthy worker. Planned bee-parallel tests actually ran locally and sequentially.
- **Box overload from large PNGs.** Reading large screenshot PNGs on the box timed out and overloaded it. That aborted the EOH UI/QoL lane; its work was left unpushed.
- **GitHub 429s.** A Hermagotchi push hit rate limits and needed an empty retrigger commit to get CI moving.
- **Seventh screenshot.** teknium1 dropped a 7th EOH screenshot (commit `8311f912`); the catalog validator allows at most 6. Keep six.
- **Approved, then corrected.** Reviewers approved pins on Eye Of Hermes ([#149691](https://github.com/NousResearch/hermes-agent/pull/149691)) and Hermagotchi ([#150358](https://github.com/NousResearch/hermes-agent/pull/150358)), then posted “a correction to our approval” with `CHANGES_REQUESTED` after a full-tree read. stitchslop ([#151946](https://github.com/NousResearch/hermes-agent/pull/151946)) also had changes requested. Budget a fix–release–repin–reply cycle, and answer point-by-point.
- **Merge order and CI.** EOH audit PRs were merged in the order **#31, then #29, then #30**, so the new CI introduced in #31 ran on the later PRs. Conflicts were resolved so #32’s review fixes survived and the version stayed 0.2.9 until the authorized v0.2.10 bump.
- **CreatePullRequest fallback.** Opening a catalog PR with `gh` can fail for lack of CreatePullRequest permission on `NousResearch/hermes-agent`. Push the fork branch and have Kyle open it in the GitHub UI (this happened for poptart’s first catalog branch).
- **Duplicate keys in YAML.** A second `name:` (seen on godseye) can unload tools while `yaml.safe_load` looks fine. Always ship the strict ruamel test and bump script.
- **Catalog PR body can lag the pin.** Repins of [#149691](https://github.com/NousResearch/hermes-agent/pull/149691) updated the title and SHA but left the original v0.2.7 write-up in the body through the v0.2.10 repin. Rewriting the body was offered and not yet done, as of 10 Nov 2026, 1:38 PM ET (America/Toronto).
- **Stop means stop.** Audit lanes and bee dispatch were halted when Kyle said hold; they were not restarted.

---

## Notable projects

Work this agent shipped is listed first, with public repo and catalog URLs. Later slot and description changes after 10 Nov 2026, 1:38 PM ET (America/Toronto) were handled by sibling agents and are noted only where useful for outcome context.

### Eye Of Hermes (godseye) — this agent

- Repo: [https://github.com/mojomast/EOH](https://github.com/mojomast/EOH) (renamed from `mojomast/hermes-godseye`; plugin id remains `godseye`)
- Catalog: [https://github.com/NousResearch/hermes-agent/pull/149691](https://github.com/NousResearch/hermes-agent/pull/149691)
- Review-fix PR #32 covered watch-alert trust (untrusted feed text as data, not “trust” in the system prompt), admin confirm, and pane gestures, and landed in **v0.2.9** (`fef5215`). Catalog was repinned (fork commit `87f75ac`) with 6 screenshots.
- Audit PRs **#29, #30, #31** (security hardening, `godseye_query` `op=sdr_receivers`, tests/CI/install docs) were merged in the order #31, #29, #30. `main` was then `402eb62`, still labeled 0.2.9 until the bump.
- **v0.2.10** was released at `9d433e4` on 10 Nov 2026, 1:38 PM ET (America/Toronto). Catalog #149691 was retitled and repinned (fork commit `be99932`); a summary comment was left for teknium1. The PR body was still the v0.2.7 write-up.
- Earlier EOH releases and the original hackathon submission of #149691 were largely sibling-agent work (v0.2.0 onward). godseye stays disabled on the shared test host.
- Further EOH audit lanes (UI/QoL, SDR polish, perf, E2E, promo art) are stopped on Kyle’s hold.

### Hermagotchi — this agent (review-fix cycle); initial submission by Hermes Forge

- Repo: [https://github.com/mojomast/hermagotchi](https://github.com/mojomast/hermagotchi)
- Catalog: [https://github.com/NousResearch/hermes-agent/pull/150358](https://github.com/NousResearch/hermes-agent/pull/150358)
- Initial hackathon pin (v0.1.0) was submitted by Hermes Forge.
- This agent landed PR #10 (`2bc5628`: asset URL allowlist so dashboard fetches cannot leak a session credential via absolute URLs, third-party text wrapping, `plugin_data_dir`), then the v0.1.3 bump PR #11 at `0ed7793`.
- Release: [https://github.com/mojomast/hermagotchi/releases/tag/v0.1.3](https://github.com/mojomast/hermagotchi/releases/tag/v0.1.3)
- Catalog #150358 was repinned to `0ed7793` with a reply to teknium1. (CI on that repo was observed to trigger only on `feat/hackathon`.)

### stitchslop — this agent (review-fix cycle); earlier open of the catalog PR by siblings

- Repo: [https://github.com/mojomast/hermes-stitchslop](https://github.com/mojomast/hermes-stitchslop)
- Catalog: [https://github.com/NousResearch/hermes-agent/pull/151946](https://github.com/NousResearch/hermes-agent/pull/151946)
- This agent landed PR #2 (`e65c0a2`: relay auth on every sensitive route, constrained `nav`, no wildcard bind), then the v0.2.2 bump PR #3 at `51c12d0`.
- Release: [https://github.com/mojomast/hermes-stitchslop/releases/tag/v0.2.2](https://github.com/mojomast/hermes-stitchslop/releases/tag/v0.2.2)
- Catalog #151946 was repinned (fork commit `42a4dcd` on `catalog/stitchslop-v0.2.1`) with a reply to teknium1.
- Still open for Kyle, as of 10 Nov 2026: Chrome `--no-sandbox`, and whether to move the shared `~/.stitchslop` state directory to per-profile plugin data (the review reply asked that the state dir be disclosed).

### poptart (Hermes Strudel Studio) — this agent

- Repo: [https://github.com/mojomast/poptart](https://github.com/mojomast/poptart) (plugin id `hermes-strudel-studio`, tool `poptart_studio`; catalog subdir `integration/hermes`)
- Catalog: [https://github.com/NousResearch/hermes-agent/pull/150357](https://github.com/NousResearch/hermes-agent/pull/150357)
- 6 Nov 2026, ~2:25 PM ET (America/Toronto): v0.2.1 was enabled on the test host after an approved gateway restart (rollback SHA `33b8ab9`, backups under the usual `~/.hermes/backups/poptart-*` pattern). The pane worked in the Hermes web app once the gateway remounted the plugin route.
- 6 Nov 2026, ~3:30 PM ET: **v0.2.3** tagged at `27268c2` on `feat/hermes-strudel-studio` (not merged to `main`). Catalog branch `catalog/hermes-strudel-studio-v0.2.3` (`b7ccf52`, pin `27268c2`) was pushed; Kyle opened the PR in the GitHub UI after a CreatePullRequest permission error.
- 6 Nov 2026, 6:50 PM ET: **v0.2.4** was submitted to the Nous Hermes plugin hackathon (Typeform “Submission Received”) with catalog PR #150357. A demo post on Kyle’s X account was part of the required hackathon packet; this agent does not post on X.
- 7 Nov 2026, ~7:58 PM ET: **v0.2.5** (self-contained `integration/hermes` subdir, Windows `fcntl` guard, neutral `INTEGRATION.md`) tagged at `42356dd`. #150357 was repinned (fork commit `83a686b`) with a reply to teknium1’s changes-requested review. The test host was not redeployed (still on `13de043`).
- #150357 later merged on 9 Nov 2026, 9:52 PM ET (America/Toronto), in the same window as hyperrizz #151945.

### Other Kyle plugins (largely sibling-agent work)

This agent is configured to work on several of these, but the outcomes below were primarily shipped by sibling assistants (MR.INDIA, Hermes Forge, BABA BOOEY, DOLAN, hammy, and others). Listed so the workflow doc has the public links and last-known outcomes, not as this agent’s own release log.

| Plugin | Repo | Catalog / outcome |
|---|---|---|
| hyperrizz | [mojomast/hyperrizz](https://github.com/mojomast/hyperrizz) | [hermes-agent#151945](https://github.com/NousResearch/hermes-agent/pull/151945); hackathon submission 9 Nov 2026; later v2.1.0 repin; PR merged 9 Nov 2026, 9:52 PM ET (America/Toronto) |
| Hermes Plugin Dev | [mojomast/hermes-plugin-dev](https://github.com/mojomast/hermes-plugin-dev) | Publishes the same `hermes-plugin-development` skill this agent follows. [hermes-agent#152699](https://github.com/NousResearch/hermes-agent/pull/152699) (v0.3.x); later marked merged by a sibling agent |
| assetrizz | [mojomast/assetrizz-hermes](https://github.com/mojomast/assetrizz-hermes) | [hermes-agent#152771](https://github.com/NousResearch/hermes-agent/pull/152771); handled by MR.INDIA; later marked merged |
| shortrizz | [mojomast/hermes-shortrizz](https://github.com/mojomast/hermes-shortrizz) | [hermes-agent#148687](https://github.com/NousResearch/hermes-agent/pull/148687) was closed to free a catalog slot, not as a review verdict. Later tags (including v0.5.1) exist for a future pin |
| photo-to-part | [mojomast/hermes-photo-to-part](https://github.com/mojomast/hermes-photo-to-part) | Install from the `plugin/` subdir. Original [hermes-agent#148018](https://github.com/NousResearch/hermes-agent/pull/148018) was closed to free a slot; a later catalog PR was opened and review-fixed by siblings |
| aircraft-doppler-geolocation | [mojomast/hermes-aircraft-doppler-geolocation](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) | [hermes-agent#148043](https://github.com/NousResearch/hermes-agent/pull/148043) (v0.1.1) merged 2 Nov 2026; v0.3.0 pinned on [hermes-agent#148633](https://github.com/NousResearch/hermes-agent/pull/148633) |
| comfyrizz | [mojomast/comfyrizz-hermes](https://github.com/mojomast/comfyrizz-hermes) | [hermes-agent#146230](https://github.com/NousResearch/hermes-agent/pull/146230) merged earlier, with no extra review thread in the lessons log |
| TempleOS for Hermes | [mojomast/hermes-templeos](https://github.com/mojomast/hermes-templeos) | Hackathon catalog [hermes-agent#153852](https://github.com/NousResearch/hermes-agent/pull/153852) (sibling / Hermes Forge). Live-pane lesson: don’t starve the gateway with per-tick screendumps; use a background frame cache |
| bundlebees | (sibling hackathon entry) | [hermes-agent#153888](https://github.com/NousResearch/hermes-agent/pull/153888), submitted 11 Nov 2026 by a sibling agent |

As of this agent’s last hands-on catalog cycle (10 Nov 2026, 1:38 PM ET, America/Toronto), #149691, #150358, and #151946 were waiting on teknium1 to re-review the post-approval fixes. Sibling journals after that date record further cap-management, description-only PRs, and additional review fixes on other entries.

---

## Skill and checklist pointers

Documented zero-to-listed path (skill + `references/CHECKLIST.md`): scaffold → implement → unit tests / doctor / validate / secret-scan → authorized bump, tag, and release → yaml-only catalog PR on the fork → authorized deploy to the test host with backup and rollback SHA → catalog-review safety gate and, after a fix, an authorized point-by-point reply.

The workflows copy of the skill is at `/home/box/agent-data/workflows/hermes-plugin-development/`. The published skill lives in `mojomast/hermes-plugin-dev` and should stay in lesson-parity with that copy.
