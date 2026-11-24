# 06 — Rules and lessons

## 1. Standing rules

### Approval and safety
- **Only Kyle's own words count as approval.** A checklist, a sibling bot's relay, or an ambiguous "go ahead" is not permission. Confirm relayed approvals with Kyle.
- Each of these needs an explicit yes, every time: merge, tag, release, catalog PR open or repin, upstream comments, X posts, form submits, GitHub Pages deploys, any Orbit / moltussy-1 / VPS deploy or restart, PC launcher restart, Google Colab spend, deleting anything, force-push, branch deletion, history rewrite.
- **Stop / hold means stop.** Kill subagents and test processes, pause routines, don't restart until Kyle asks.
- **Docker access is root-equivalent.** A helper container that mounts the host can change protected files and systemd units; use it only for the authorized host change, with the smallest mount and one command.
- Never post on X for Kyle. Draft the post; he attaches media and posts.
- Fill forms up to Submit, show a screenshot, submit on yes.
- Don't close other people's PRs (e.g. Nous catalog PRs) or touch work another agent owns without asking (some catalog PRs were explicitly hands-off for some bots).

### Secrets and privacy
- Never print or commit tokens or keys (Orbit token, Google Colab token, provider keys, map keys, launcher tokens, board keys, `.env` contents), tailnet hostnames, private IPs or private URLs. Refer to them by file path or env var name.
- Secret-scan before every push.
- Plugin code gets credentials only through Hermes's secret scope; child processes get a minimal, explicit environment.

### Cost and load
- Kyle is token-conscious: don't spawn more agents or workers than needed; don't start optional work without asking.
- Coding goes to DeepSeek bees or executors, not Cursor cloud agents, unless Kyle asks.
- Heavy work goes to bees on the PC, not the shared box; what runs on the box runs under `nice`/`ionice`.
- Prefer new Google Colab tests over reruns of the same film.

### Naming
| Say | Never |
|---|---|
| Google Colab | bare "Colab" |
| poptart (the Strudel music plugin; catalog key and title stay `hermes-strudel-studio` unless Kyle approves a change) | "Strudel Studio" in showcases and graphics |
| bundlebees (the bees plugin) | — |
| AGENT ARMEGEDDON: CLAWPOCALYPSE NOW (formerly Pizza Panic; Orbit app id still `pizza-panic`) | — |
| Eye Of Hermes / EOH (plugin id `godseye`; repo renamed from `hermes-godseye` to `EOH`) | — |
| "characters from the Nous universe" for Nous figures in Temple of Hermes | — |
| "collaboration" = the Orbit collaboration board | — |

### Product and style
- Hermes and EOH are always dark mode, especially before screenshots.
- Don't re-enable map layers or overlays Kyle turned off.
- Terry uses the 2017 cap look only; only the 69 approved sourced quotes, verbatim; no synthesized Terry voice.
- Game assets must be original, with provenance.
- Screenshots must be real; no placeholder text; every on-screen number real.
- No "slop" graphics.

## 2. Pitfalls and fixes

| Pitfall | What happened | Fix / rule now |
|---|---|---|
| Plugin loads with 0 tools | `register_tool(..., output_schema=…)` raised `TypeError` on Hermes 0.21.7 and aborted `register()` (photo-to-part) | Keyword-only registration with a signature check |
| Tools silently missing | A duplicate `name:` in `plugin.yaml` (EOH v0.2.4); PyYAML keeps the last key | Strict ruamel load, duplicate-key CI test, strict bump script (v0.2.5 fix) |
| Catalog PR can't be opened | `gh` lacked CreatePullRequest on NousResearch | Push the fork branch; Kyle opens the PR in the UI |
| 7th screenshot | Validator allows 6; a maintainer dropped the 7th | Keep ≤ 6 |
| Approved, then corrected | Maintainers re-read the full tree after approving EOH and Hermagotchi | Budget a fix → release → repin → reply cycle |
| Catalog PR body lags the pin | Repins changed title/SHA but left an old write-up | Description-only PRs later fixed card text |
| Plugin APIs that don't exist | bundlebees v0.1.0 called a scoped-token read and plugin config that real Hermes doesn't have; Desktop pane would have been blank | Smoke-test on a real Hermes (0.23.0) before tagging |
| Session-token leaks | `SDK.authedFetch` attaches the session token; absolute URLs would leak it (Hermagotchi) | Only relative plugin routes, `data:` or `blob:` |
| Auth on redirects | bundlebees forwarded auth headers across a cross-site redirect | Drop auth on cross-origin redirects |
| Child env leaks | photo-to-part builds inherited provider keys | Exact-name env allowlist; test with a planted fake secret |
| Global hooks | Hooks policed unrelated projects | Scope hooks to sessions that used the plugin's tools |
| Feed prompt-injection | EOH told the model to "trust" watch-alert titles | Untrusted text is quoted data (EOH PR #32) |
| Open relays | stitchslop viewer handed out credentials, opened any URL, could bind all interfaces | Token on every route, loopback bind, constrained `nav` |
| Free models stall | minimax-m3.1-flash-free stalled on PNGs; two free models stalled together | Model order and fallback rules; don't bulk-move to paid |
| Duplicate verifies | Manual verify while the orchestrator routine verified (load ~48) | Check `verify.sh` isn't running; run only the task's tests |
| Blank bee patches | Bee committed inside the sandbox | Leave changes uncommitted; copy output before reaping |
| False "stuck bee" | Launcher blips flushed 30 min of events later | Check launcher API and event mtimes before cancelling |
| Seed timeouts | Parallel `git fetch` on the PC timed out at 120 s | Seed one sandbox at a time |
| Sandbox ≠ real host | TempleOS guest connected to a fake BBS, failed on the real one | Test rig copying the real QEMU argv, relay and a throwaway real account |
| Restart kills sessions | Hermes service restarts stopped the TempleOS VM and BBS relay | Snapshot and restore on deploy |
| Stale Desktop pane | Hermes Desktop served the old `plugin.js` | Rescan plugins; compare on-disk bundle hash to the tag |
| QEMU wrapper collision | A wrapper on `PATH` added a conflicting drive index | Skip wrappers; doctor warns |
| Wrong protocol verb | `bbs_digest` sent `DIGEST`, server wanted `LIST action digest` (v0.2.0) | v0.2.2 fix |
| Stale client keys in bundles | EOH map keys were baked into the panel bundle at build time | Doctor freshness check, rebuild tool, documented env file |
| Stale deploy script | Game `deploy.sh` would have rolled back newer work | Check source paths before deploying |
| Port collision | The first candidate ports were already bound on the shared VPS | Check listening ports (`ss -ltn`); use the free port the host runbook names |
| Framed TCP behind HTTP | HBBS/1 terminates TLS itself and cannot be an nginx HTTP upstream | Use its own port or a raw `stream`/`ssl_preread` passthrough |
| Global Certbot hook | A host-wide deploy hook reloads nginx for every certificate | Separate `--config-dir` and `--no-directory-hooks`; app-specific deploy hook |
| Live SQLite copy | Copying a live database can capture a torn state | `sqlite3 .backup`, then `PRAGMA quick_check` |
| Hand-counted frame length | A 34-byte LIST body was written as 35 | Compute `len(body.encode())`, not characters or a hand count |
| Two sign-up approvers | The host autoapprove timer still ran after the app added auto mode | Disable the timer when the app owns the policy |
| Node version | Node 20 broke `better-sqlite3` in Orbit | Node 22 on `PATH` for Orbit builds |
| Box overload | Reading big PNGs on the box timed out | PIL checks; heavy image work in bees |
| GitHub 429 | Push rate-limited; CI didn't start | Empty retrigger commit |
| Spec drift | Emurizz spec said 2-player N64 after 4 became required | Record superseded spec text |
| Thin approval scope | Approvals cover named actions only | Record approved and not-approved lists in memory and briefs |

## 3. Habits that worked

- Contracts slice first, then leased parallel slices, then one integration PR.
- Approved tests before code: the coordinator commits the tests on their own, confirms they fail for the right reason, and leases only implementation files to the bees, so a bee cannot weaken the tests that judge it. The ACDD + TDD work itself was built this way on Nov 12 ([16](16-acdd-tdd.md)).
- Say when tests came after the code (`test_first: false`) instead of presenting them as test-first.
- Measure tool-schema cost (o200k) on every change and report the delta; keep tool counts fixed (TempleOS: exactly 4 tools, new behaviour as ops).
- Composable tools: EOH went from ~68–83 legacy tools to 11 composable ones.
- Keep evidence in new folders; never overwrite earlier before/after sets.
- Record every deploy's backup path and rollback in chat and memory.
- Put off-host agents' briefs and assets on a public branch.
- After a test on a shared host, restore only what the test changed.

These are rules, stated flatly because they earned it. The incident behind each one, the check that now enforces it where one exists, and whether the support is a test, an observation or only a recommendation are catalogued in [28](28-agent-lessons.md); this chapter stays the rulebook.

## 4. Lessons from the review and creative loop

- Tie every review and measurement to its revision. Doppler's first timings and final equivalence results came from different runs; [the final PR report](https://github.com/mojomast/hermes-aircraft-doppler-geolocation/pull/5) supersedes the initial performance report.
- Preserve the intended experience during planning. Streaming was not a substitute for Kyle's Emurizz netplay request; in-pane gameplay also needed its own acceptance gate.
- Deliver selected artwork with editable sources and an integration brief. Comfyrizz PNG concepts needed vector refinement; Terry's transparent videos needed a renderer and fallback in the pane.
- Keep technical and perceptual checks distinct. Decoding a video does not check natural arm movement, readable text or perceived sound quality.
- Save corrections at their proper scope. The TempleOS companion's silent loops and sourced quotes do not inherit the separate tribute-film experiment's narration choices.

These examples support the proposed [operating guide](09-reproducible-collaboration.md); they do not change the authorization rules above.

A miniature of the contract-first, test-first loop (ACDD contracts, RED, GREEN, REFACTOR, independent verification and integration) is in the [reference demo](../reference/README.md); `--legacy` runs the earlier lease-and-verify version. How that loop relates to bundlebees and Orbit is in [12](12-three-layer-architecture.md). The hardening now on bundlebees `main` (untagged), including the metrics JSONL and summary CLI, is in [13](13-bundlebees-hardening.md); those measures are not yet a live-orchestration baseline.
