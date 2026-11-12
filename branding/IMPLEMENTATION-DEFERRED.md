# rizzstack Night Hive — deferred implementation notes

> **Status: DEFERRED. Nothing in this document has been executed or approved.**
> It lists future migration work, likely breakage points and possible compatibility
> approaches. It does not choose a migration on Kyle's behalf. Every step that
> renames, merges, tags, releases, deploys, posts or touches the Nous catalog needs
> Kyle's own explicit yes. Naming clearance (see `DECISIONS.md` §6–7) comes first.

## Superseded: bundlebees → swrm proposal

An earlier read-only plan (12 Nov 2026) proposed renaming bundlebees to **swrm**.
That direction is **SUPERSEDED by bzzq**. It is not an approved technical migration
plan, and no part of it may be implemented unless Kyle explicitly reauthorises it.
Its inventory of where the `bundlebees` name appears is still useful input for any
future bzzq review; its name choices, ordering and branch strategy are not decisions.

## 1. GitHub repository renames

- Targets (proposed): `mojomast/rizzstack-flww`, `-hyvv`, `-bzzq`, `-orbt`.
- Breakage: clone URLs in docs and scripts (e.g. acceptance `cold_start.sh`),
  `hermes plugins install mojomast/<repo> --ref <sha>`, badges, CI references,
  cross-repo links.
- Options: GitHub rename keeps web/clone/API redirects as long as no new repo is
  created under the old name. Alternatively keep repo names and brand only the docs.
- Open PRs survive a rename, but large renames conflict with open branches; land or park them first.

## 2. Package and distribution names

- Current: Python distribution `bundlebees` (pyproject), package `bundlebees_plugin`,
  client `bundlebees_client`; other layers have their own names.
- Exact names `flww`, `hyvv`, `bzzq`, `orbt` returned 404 on PyPI and npm on
  12 Nov 2026 — not a clearance. Prefixed names (e.g. `rizzstack-bzzq`) are an option.
- Breakage: import paths, entry points, editable installs, test fixtures.
- Options: keep import package names and change only distribution names; or ship a
  shim package that re-exports the old import path for one release.

## 3. Hermes plugin ID and tool names

- Current plugin id `bundlebees`; tools `bundlebees_status`, `bundlebees_dispatch`,
  `bundlebees_attempt`, `bundlebees_host_prompt`; skill `bundlebees:bundlebees-operator`.
- Breakage: a new plugin id is a new plugin to Hermes — settings, stored secret and
  plugin data don't carry over; two enabled plugins register duplicate tools; skills,
  routines, briefs and host prompts that name old tools fail quietly.
- Options: keep the plugin id and change display name only; or rename with
  "formerly bundlebees" in the skill text and tool_search keywords, avoiding duplicate
  tool registration (tool-schema budget roughly doubles otherwise).

## 4. CLI commands and aliases

- Current: `hermes bundlebees verify | integrate | metrics | deploy | doctor`.
- Options: hidden alias for one release that prints a rename notice and runs the
  same command; or keep the current command permanently.

## 5. Environment variables and configuration

- Current examples: `BUNDLEBEES_LAUNCHER_TOKEN`, `BUNDLEBEES_ALLOW_WEAK_UNSHARE`,
  `BUNDLEBEES_SENTINEL_SECRET` (names only; no values recorded here).
- Breakage: live worker hosts and launchers read these names; changing them is a live
  configuration change and needs separate approval.
- Options: read new name, fall back to old with a one-time warning; keep security
  controls fail-closed (a missing secret must still refuse, never default open).

## 6. Data directories

- Current: `plugin_data_dir("bundlebees")` holds signed leases, waves and metrics.
- Options: copy (never move) old state on first run when the new dir is empty; or keep
  the old directory name. Never delete old state without approval.

## 7. Signed evidence verification

- Existing leases, integration records and evidence were signed under current names.
- Requirement: verifiers must continue to accept historical records; do not re-sign
  old records; do not weaken verification to make a rename pass tests.
- Contract schemas and evidence formats should not change only for branding.

## 8. Cross-repository references

- workflow docs (e.g. `docs/13-bundlebees-hardening.md`, docs 03/12/14, README index),
  acceptance harness, `contrib/hermes-bees`; hyvv README; orbitdesktop panes and docs.
- Options: pointer files at old doc paths; update after open PRs land so counts don't fork.

## 9. README banners and social assets

- Source: the archived Night Hive v1.0 package only (`archive/`, `MANIFEST.md`).
- Do not regenerate, retouch or approximate assets. Public README changes and social
  cards need separate approval; nothing is posted from this branch.

## 10. Orbit / orbt application branding and CSS

- Night Hive tokens exist in the package (see `MANIFEST.md` for token file paths).
- Breakage: existing Orbit dark-mode theme, screenshots in tests/docs, pane titles.
- Options: introduce tokens behind the current theme first, then swap names/logos.
  Orbit, Hermes and EOH stay dark mode either way.

## 11. Documentation and site deployment

- rizz.click: no working HTTPS observed on 12 Nov 2026. Site work, DNS and certificates
  need separate approval; nothing here deploys anything.

## 12. Nous plugin catalog update

- Open catalog PR `plugin-catalog: add bundlebees v0.1.0` (NousResearch/hermes-agent
  #153888) is SHA-pinned and has changes requested. **Do not modify it** as part of
  branding. A rename would mean a repin and restarting maintainer review; any catalog
  push or comment needs Kyle's yes.

## 13. Tests, rollback and release sequencing

- Tests that assert names (e.g. checkout dir named `bundlebees`, CLI lookups by name)
  must be updated deliberately, never deleted or weakened.
- Rollback: GitHub renames can be reverted while redirects are intact; package names
  on PyPI/npm cannot be reclaimed once published — publish nothing until cleared.
- Sequencing (to be decided by Kyle): clearance → land/park open PRs → compatibility
  layer → per-repo rename PRs → releases → catalog → site → announcement.
  Each arrow is a separate approval.

**DEFERRED — NOT IMPLEMENTED.**
