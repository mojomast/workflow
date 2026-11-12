# rizzstack — Night Hive v1.0 branding decision record

> **Status: DEFERRED / NOT IMPLEMENTED.**
> These are selected creative decisions, not a completed or approved migration.
> No repository, package, plugin, tool, CLI, environment variable, data directory,
> CSS, logo, README or website has been changed. Implementation needs Kyle's
> separate, explicit approval.

- Decision date: 12 November 2026 (America/Toronto)
- Decided by: Kyle Durepos
- Asset package: Night Hive v1.0 (see `MANIFEST.md` and `archive/`)
- Branch: `docs/rizzstack-night-hive-v1-deferred` in `mojomast/workflow` (local-only archive branch)

## 1. Umbrella identity

- Umbrella brand: **rizzstack**, always lowercase.
- Primary domain: **rizz.click**.
- Theme: **Night Hive**.
- Positioning: **Agent work you can prove.**
- Architecture: four independent but interoperable layers.
- Naming style: short, four-letter product names with one consistent visual identity.

## 2. Current names and selected future names

| Layer | Current project / identifier | Selected brand name | Role |
|---|---|---|---|
| 1 (bottom) | workflow | **flww** | Methodology: ACDD, contracts, TDD, evidence and metrics |
| 2 | hyvv | **hyvv** | Worker-host runtime and versioned `/v1` API |
| 3 | bundlebees | **bzzq** | Orchestration: parallel bees, leases, verification and integration |
| 4 (top) | Orbit / orbitdesktop | **orbt** | Control surface: onboarding, board and evidence dashboard |

- **bzzq** ("buzz queue") replaces the earlier proposed **swrm** and **bzzm** names.
- The workers are still called **bees**.
- The earlier bundlebees → swrm rename proposal is **superseded** as a branding
  direction. No part of it is approved for implementation.
- Current operational names (workflow, hyvv, bundlebees, Orbit/orbitdesktop) stay
  in use in all code, PRs, CI, schemas, APIs, settings and evidence records.

## 3. Four-layer architecture mapping

```
 orbt  ── control surface            (today: Orbit / orbitdesktop)   ← honey top layer
 bzzq  ── orchestration              (today: bundlebees)
 hyvv  ── worker host + /v1 API      (today: hyvv)
 flww  ── method / contracts / proof (today: workflow)
```

## 4. Creative direction — Night Hive

Dark industrial-engineering aesthetic. Dark mode is the primary identity. Light and
monochrome variants exist for compatibility and reproduction only; the public
direction remains Night Hive.

### Palette

| Token | Hex |
|---|---|
| Base | `#0B0F14` |
| Surface | `#111821` |
| Border | `#243242` |
| Text | `#E6EDF5` |
| Muted | `#93A4B8` |
| Honey / brand accent | `#F0B86E` |
| Verified | `#54D3A1` |
| Rejected | `#F2706B` |

### Typography

- **Syne**: wordmarks, display and brand typography.
- **Geist**: UI and general interface text.
- **Geist Mono**: code, technical identifiers and evidence displays.

Font binaries must not be committed or redistributed unless their licences and
redistribution permissions have been verified. No font files are extracted into
this branch (see `MANIFEST.md` for what the original archive contains).

### Logo conventions

- Wordmark: lowercase `rizzstack`. `ri` in primary text colour, `zz` in honey,
  `stack` in a lighter weight. The `rizz` portion leads the composition.
- Master mark: four-layer stacked hex. Bottom to top: flww, hyvv, bzzq,
  orbt (honey-highlighted top layer).
- Product icons:
  - flww: flowing parallel lines
  - hyvv: layered runtime/host structure
  - bzzq: connected hexagonal cells
  - orbt: orbital ring and flight-path motif
- The supplied asset package is the reference. Do not recreate assets from memory,
  and do not regenerate, retouch, replace or reinterpret them.

## 5. Proposed naming conventions (future targets only)

Repositories (when a migration is approved):

- `mojomast/rizzstack-flww`
- `mojomast/rizzstack-hyvv`
- `mojomast/rizzstack-bzzq`
- `mojomast/rizzstack-orbt`

Product URLs:

- `rizz.click/flww`
- `rizz.click/hyvv`
- `rizz.click/bzzq`
- `rizz.click/orbt`

These are targets, not instructions. GitHub, PyPI, npm, Hermes plugin IDs, CLI
commands, package names and environment-variable names do **not** have to match the
repository convention. Those details need a separate compatibility review and approval.

## 6. Known naming and migration risks

No formal naming clearance has been done. **None of these names is legally cleared,
uniquely owned or guaranteed available.** Read-only observations (12 Nov 2026):

| Name | Observation |
|---|---|
| rizzstack | GitHub organisation `rizzstack` already exists (not ours). PyPI and npm: no exact package found. |
| rizz.click | HTTPS did not answer with a valid site; plain HTTP returned a 500 from the CDN. No working HTTPS certificate observed. |
| flww | GitHub user account `flww` exists (not ours); unrelated repos named `flww*` exist. PyPI and npm: no exact package found. |
| hyvv | Unrelated company **HYVV** (hyvv.io / HyvvApp) exists — possible similar-mark conflict. GitHub user account `hyvv` exists (not ours); several unrelated `hyvv` repos. PyPI and npm: no exact package found. Our repo is `mojomast/hyvv`. |
| bzzq | GitHub user account `bzzq` exists (not ours); unrelated repos named `bzzq*`. PyPI and npm: no exact package found. |
| orbt | GitHub organisation `orbt` exists (not ours); unrelated repos (e.g. `orbt`, `orbtk`). PyPI and npm: no exact package found. |
| swrm (superseded) | Taken on PyPI. Recorded only for history. |
| Hermes plugin catalog | No exact `flww`/`hyvv`/`bzzq`/`orbt` entry seen in the first 1,000 entries of the public plugin catalog listing (listing may be truncated). |

"No exact package found" means only that the public registry returned 404 for that
exact name on 12 Nov 2026. It says nothing about trademarks, similar marks, or
future availability.

Migration risks (detailed in `IMPLEMENTATION-DEFERRED.md`): installed Hermes plugins
see a new plugin id as a new plugin; catalog SHA pins; agent prompts and skills that
name current tools; signed evidence under current data directories; repository
redirects; secret and env names.

## 7. Conditions before implementation can begin

All of these, each with Kyle's explicit approval in his own words:

1. Naming clearance finished: GitHub, PyPI, npm, Hermes plugin/tool namespaces,
   trademarks and similar marks, domains and product names, existing users and integrations.
2. A working HTTPS setup for rizz.click (if URLs are used).
3. Open engineering PRs on the four layers landed or parked, so a rename doesn't fork them.
4. Font licences and redistribution permission verified for Syne, Geist and Geist Mono.
5. A compatibility plan chosen by Kyle (aliases, env fallback, data-dir migration,
   signed-evidence verification) — see `IMPLEMENTATION-DEFERRED.md`.
6. Separate approval for each rename, release, catalog change, site deploy and public post.

**DEFERRED — NOT IMPLEMENTED.**
