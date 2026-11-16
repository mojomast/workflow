# Website plan — the rizzstack docs site

- Status: PLAN — a reviewable design document; no site deployed
- Drafted: 2026-11-16 (America/Toronto)
- Companion: docs/rebrand-plan.md (the name mapping and the deferral boundary this site inherits)
- Provenance: rebuilt alongside docs/rebrand-plan.md under the corrected lease (r2); the r1 attempt's history, including the verify refusal and the scanner-overmatch class, is recorded in that plan's provenance note

## 1. Purpose and boundary

A static docs site that presents the workflow to the public: what it is, why it exists, how to run it, and where the protocol stands. The site renders this repository's own documentation; it invents no product claims and publishes no live data.

The deferred-branding boundary governs the site's look and naming exactly as it governs the rebrand: the selected names are NOT legally cleared, so the site ships with an unbranded baseline and applies the Night Hive theme only when branding un-defers (docs/rebrand-plan.md sections 1 and 6). Until then, real things keep their operational names, and the selected names appear only as intended future branding inside the rebrand plan, never as a brand claim on the site.

## 2. Architecture — a static docs site

The output is fully static: HTML pages, one stylesheet, at most one small script for the table of contents. There is no server-side process, no client data collection and no build-time network fetch.

- Source of truth: this repository's Markdown. The site is a rendering of it, never a fork of its content; a page that drifts from its source is a build bug.
- Generator choice: a stdlib-only Python builder (a new tools/site-build.py) that renders the documented Markdown subset this repository already uses.

Reasoning:

- The repository's tooling standard is Python 3 with the stdlib only; contrib/rizzstack-observability runs on Python 3.9+ with no dependency beyond the interpreter, and the site builder should meet the same bar — no third-party build dependencies at all.
- The docs use a constrained Markdown subset (headings, paragraphs, lists, tables, fenced code, links, emphasis, blockquotes), so a small renderer over that subset stays testable end to end.
- Fail closed: the builder refuses any construct outside the subset instead of silently mangling a page; unknown fenced languages pass through as plain code blocks, while unknown inline syntax fails the build with the file and line named.
- Zero new install steps in CI: the existing Python-only pipeline needs no Node, no Ruby and no Go toolchain for one site.

Alternatives considered:

- MkDocs or Sphinx: mature, but both add third-party dependencies and carry their own theming defaults that would fight the unbranded baseline. Revisit at un-deferral only if the subset renderer proves too small.
- Hugo or Astro: a second toolchain (Go or Node) for one static site. Rejected.
- Hand-written HTML per page: zero dependencies, but thirty-plus chapters of drift risk with every docs edit. Rejected.

Diagrams: the README and several chapters carry mermaid diagrams. The build initially renders them as styled fenced blocks that keep their textual content readable; a pre-render-to-SVG step is a later, optional addition. The build never calls a rendering service at run time.

Output layout: one HTML page per source document plus index pages per section, relative links only, so the output serves unchanged from any static host root.

## 3. Content map

Every page maps to a repository source; nothing is written for the site that is not already public in the repository.

| Section | Content | Sources | Why it is public-safe |
|---|---|---|---|
| What | one-screen description of the workflow and its layers | README.md overview, docs/12-three-layer-architecture.md | the overview is already public |
| Why | the case for contract-first, human-gated agent building | docs/21-autonomy-gap-analysis.md, docs/28-agent-lessons.md, docs/30-campaign-closeout.md | findings and lessons, no live data |
| How | the operating loop and the collaboration rhythm | docs/09-reproducible-collaboration.md, docs/10-teaching-the-workflow.md, docs/19-coordinator-playbook.md | operating guide; host specifics stay private |
| Quickstarts | run the offline reference demo; run the cold-start acceptance; teach the workflow | reference/README.md, acceptance/README.md, docs/10-teaching-the-workflow.md | both demos are offline by design |
| Architecture | three layers plus the fourth, hardening, networking, autonomy design | docs/12-three-layer-architecture.md, docs/13-bundlebees-hardening.md, docs/14-networking-and-worker-deploy.md, docs/22-autonomy-architecture.md | design chapters |
| Protocol | ACDD, feature packets, return manifests, schemas, observability records | docs/16-acdd-tdd.md, docs/25-feature-packet.md, docs/26-return-manifest.md, schemas/, observability/ | frozen contracts |
| Status | what shipped, what is planned, campaign continuity | ROADMAP.md, docs/30-campaign-closeout.md, docs/31-campaign-continuity.md | built-versus-planned markers carried over |

Per-page rule: each rendered page carries its source pointer and a generated-on date in a visible footer, so a reader can pin exactly what they read.

## 4. Hosting options and recommendation

| Option | Assessment |
|---|---|
| GitHub Pages | free, already proven in this organization (the game site runs on it), publishes behind the same human gate as every other deploy, custom domain optional later |
| The existing public application VPS | full control and already running for other static sites, but every deploy touches live-host infrastructure that docs/11 treats as a gated change with backup and rollback |
| Cloudflare Pages or Netlify | polished CI-linked deploys, but a new vendor account and a new deploy path for zero required features |

Recommendation: GitHub Pages from this repository. It is free, already in use for a static site in this organization, needs no new vendor, and keeps the publish behind the same explicit yes as every other deploy (docs/05 lists Pages among the deploy targets that ask Kyle first). The VPS stays the fallback if Pages limits are ever hit.

## 5. Night Hive theme application (when branding un-defers)

- The unbranded baseline ships first: a neutral palette with no name, no logo and no motif, so the theme is later a palette swap, not a rebuild.
- Night Hive applies as a layer of CSS custom properties over that baseline: a night-scale background and text ramp, comb-geometry accents (hexagonal edges on section markers), one amber accent family drawn from hive imagery, dark-first with a checked light fallback.
- Accessibility: every foreground and background pair meets the contrast standard for body text before the theme ships; the accent is never the only carrier of meaning.
- The theme lands inside the same un-deferral window as the renames (docs/rebrand-plan.md section 4), never before; until then it exists only as this written specification.
- Motif discipline: the bee and hive imagery appears in the masthead and section markers only, never inside technical content.

## 6. Launch checklist

1. Build the site locally from the source whitelist; the builder's public-safe scan must pass with zero hits.
2. Link check: every relative link resolves inside the output; no private URLs anywhere.
3. Preview on a loopback server; the preview stays on the operator's machine.
4. Kyle's explicit yes for the publish — docs/05 and docs/11 make every publish a gated change.
5. Publish to the recommended host; record the deployed revision in acceptance evidence.
6. Post-launch: add the site pointer to README.md, record the launch, and schedule the first content refresh against a real docs change.

## 7. Public-safe content rules (no tokens, no private hosts, no live data)

The README's standing rule is the baseline ("Secrets, tokens, tailnet hostnames, private IPs and private URLs are deliberately left out"). The site keeps it in three parts, and the builder turns it into a mechanical gate: a page with a hit does not build.

- No tokens — no credential material of any shape appears in the source whitelist or the rendered output. The build runs the repository's own scanners (the bee-landed refusal patterns and the campaign-report credential check, both in tools/) over every page it renders and fails closed on any hit; the plan author's scan over this document and its sibling plan found zero secret-shaped hits.
- No private hosts — no tailnet names, private addresses, private URLs or host-runbook contents; the source whitelist is the public repository itself.
- No live data — the site renders repository content only; it fetches nothing at build time and serves nothing dynamically; the observability collector's snapshot output stays behind its loopback-only read path and is never republished.

## 8. Validation

tests/test_website_plan.py validates this document structurally (14 checks) and shares the hygiene scan across both plan documents with tests/test_rebrand_plan.py — 31 checks in total. RED-first bar identical to the rebrand plan: every check failed against the missing documents, then passed once both plans existed.
