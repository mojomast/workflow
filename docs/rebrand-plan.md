# Rebrand plan — the rizzstack umbrella and the four product names

- Status: PLAN-ONLY — a reviewable decision document; no renames executed
- Drafted: 2026-11-16 (America/Toronto)
- Owner: Kyle Durepos (mojomast); every decision in section 6 needs his explicit yes (docs/06-rules-and-lessons.md)
- Companion: docs/website-plan.md (the site this umbrella launches through)
- Provenance: rebuilt under the corrected lease (r2). The r1 attempt completed this deliverable — RED-first validation, 31 failing checks to 31 passing at the r1 content, worker checks green — but the official verify refused it on a scanner-overmatch finding: credential-adjacent prose in the website plan and the two test files tripped the value-shape heuristic, while the coordinator-side value-shape scan over the same reported content found zero secret-shaped hits. The r1 patch was not retrievable, so this revision rebuilds both plans and both test files under the mandated scanner-hygiene criteria: no literal secret-shaped values anywhere; credential guidance stays prose, with value-free colon lines and non-triggering property names where a shape is unavoidable.

## 1. Scope and the deferred-branding boundary

This plan describes a future rebrand and executes nothing. The boundary it lives inside is the one the handoff template already states: deferred names are mentioned only as intended future branding, and nothing is implemented until the approver says so (templates/handoff/HANDOFF.md, section 1). docs/06-rules-and-lessons.md carries the same rule for the catalog: catalog keys and titles stay as they are unless Kyle approves a change.

The selected names are NOT legally cleared. No trademark screening, no domain or handle availability check and no legal review have been done. Until the un-deferral decision (section 6, D2 and D3), the operational names stay exactly as they are: this repository keeps its name, bundlebees keeps its name, Orbit keeps its name, and every catalog key and title keeps its current value. Every branding-adjacent claim below — the mapping, the theme, the launch sequencing — is written inside that boundary and cites it.

## 2. The selected names and the mapping

**Umbrella: rizzstack.** The rationale is already in the record: the protocol namespace is rizzstack — the schemas and record names (rizzstack.feature-packet/1, rizzstack.return/1, rizzstack.observability/snapshot/1), the urn identifiers and contrib/rizzstack-observability all use it. The umbrella brand aligns with a namespace that already exists, so adopting it renames nothing structural: schemas, identifiers and urn strings stay as they are. The umbrella is a brand and a namespace, not a fifth repository; it launches through the docs site (docs/website-plan.md, section 4).

**Products and theme:**

| Current operational name | Layer | Selected name | Notes |
|---|---|---|---|
| mojomast/workflow (this repository) | method and protocol (docs/12) | flww | the protocol chapters, schemas and tools live here |
| mojomast/bundlebees | execution system (docs/12, docs/13) | bzzq | supersedes the proposed swrm rename in ROADMAP, which never started |
| mojomast/orbitdesktop | coordination interface (docs/12, docs/15, docs/17) | orbt | orbit-control-plane stays outside the four-product mapping; whether it joins the orbt family is part of D1 |
| mojomast/hyvv | worker-host runtime, the fourth layer (ROADMAP) | hyvv | already the selected name; approved work in progress by Hermes Forge |

**Theme: Night Hive.** The selected visual theme for the umbrella and its site. It is deferred with the names: nothing visual changes until un-deferral, and the application spec lives in docs/website-plan.md section 5.

## 3. The complete migration checklist

### 3.1 Repo renames and GitHub redirects

- Each rename happens in the repository's GitHub settings; GitHub then serves automatic redirects from the old name to the new one, and clones, remotes, stars, issues, releases and tags follow the renamed repository.
- A redirect breaks when the old name is re-used by a new repository or when the repository is renamed again, so the window ends with an explicit redirect verification per repository, recorded in evidence, never assumed.
- Pages URLs follow the repository name (the organization pages path includes the repository name), so any Pages site under a renamed repository gets its URL checked in the same window.
- Published URLs in docs/08-repositories.md and elsewhere keep working through redirects; the reference-update pass (3.3 and 3.4) rewrites them in place afterward, and a redirect alone never counts as a rename done.

### 3.2 Catalog

- The Nous catalog records (plugin ids, titles, the catalog branch naming such as catalog/name-vX.Y.Z) keep the name in effect at submission; historical catalog pull requests are never edited to chase a rename.
- The standing rule from docs/06-rules-and-lessons.md applies unchanged: catalog keys and titles stay as they are unless Kyle approves a change (D4).
- Open catalog pull requests that name a renamed repository get a comment or a fresh pull request only if the approver asks for one; the default is to leave them and record the rename in the closeout instead.

### 3.3 Docs

- README.md and the index it carries; ROADMAP.md (the hyvv entry stays; the swrm proposal closes as superseded and never started, per D8); docs/06-rules-and-lessons.md naming table; docs/08-repositories.md (each renamed row gains a was-the-old-name note, the precedent being the EOH row); docs/12, docs/13, docs/15 and docs/17 wherever a layer is named; templates/handoff/HANDOFF.md (the four-layer table and the deferred-names placeholder).
- The deferred-names placeholder in templates/handoff/HANDOFF.md keeps carrying the selected names as deferred until D3 lands; only in the un-deferral commit does the layer table switch from operational names to the selected names.

### 3.4 Code references

- contrib/bee-ci/manifest.py names the four repositories in its REPOS tuple, and contrib/bee-ci/tests (test_manifest.py, test_run_shadow.py, test_evidence.py, test_jobs_manifest.py) mirror those names; all five files change in the same commit as the repo renames, so the manifest never names a repository that does not exist.
- contrib/rizzstack-observability already carries the umbrella name and needs no rename, only a pointer from the site.
- Protocol identifiers do not change: the schemas, the urn identifiers and the rizzstack.* record names are already the umbrella namespace.
- Plugin ids do not follow repository names; the precedent is EOH, renamed from hermes-godseye while its plugin id stayed.

### 3.5 The umbrella repo element table

| Element | Layer | Current name | Selected name | Redirect | Owner decision |
|---|---|---|---|---|---|
| umbrella brand and docs site | umbrella | this repository as host | rizzstack | not a rename, a launch (website plan section 4) | D1 and D5 |
| method and protocol repository | method | mojomast/workflow | flww | automatic; verify the redirect | D1 and D3 |
| worker-host runtime | fourth layer | mojomast/hyvv | hyvv | not needed (name unchanged) | D1 |
| execution plugin | execution | mojomast/bundlebees | bzzq | automatic; verify the redirect | D1 and D3 |
| coordination interface | coordination | mojomast/orbitdesktop | orbt | automatic; verify the redirect | D1 and D3 |

### 3.6 Historical names in campaign records

Campaign records keep the names in effect when they were recorded. Chapter 30 closeouts, campaign-report documents, chapter 31 checkpoints, lease and job documents and the acceptance results are sealed evidence: a rename never rewrites a sealed record. New records use the selected names and carry a formerly-the-old-name pointer; the docs/08 historical accounts keep the old name in the narrative with the rename noted beside it, which is exactly how the EOH row already reads.

## 4. At-once sequencing with the umbrella launch

All four repository renames happen in one coordinated window — a single sitting after the full decision checklist is approved. A mixed state, where some repositories are renamed and others are not, is the worst state for the docs, the bee-ci manifest and the catalog records, and the hardest to roll back coherently; the umbrella launch is what makes the whole rename set coherent in public.

The order inside the window:

1. Pre-flight: a repo-wide reference inventory for the four operational names is recorded into acceptance evidence, with a hit count per file, so the follow-up update pass is checkable against it.
2. A staging branch prepares every doc and code reference update from 3.3 and 3.4; it merges only after the renames.
3. The four repository renames execute in one sitting; each redirect is verified and recorded (3.1).
4. The umbrella launch: the docs site goes live under the rizzstack brand in the same window (docs/website-plan.md section 6), as the first public moment of the new names.
5. The staging branch merges; the reference-update pass runs; evidence records before-and-after counts against the pre-flight inventory.

Nothing in this sequence runs until the decision checklist (section 6) is fully approved.

## 5. Rollback story

- A repository rename is reversible: rename back in GitHub settings and the old name returns; the automatic redirects then follow the newest name. The known caveat stands: a redirect pointing at the old name breaks once the old name is re-used or the repository is renamed again, so a rollback verifies redirects, it never assumes them.
- Git history, commits, tags and releases are untouched by renames; no force-push and no history rewrite is part of this plan, ever.
- Doc and code changes revert through git revert of the un-deferral commit set; the staging-branch structure keeps that commit set small and reviewable.
- The site rolls back to its unbranded baseline (docs/website-plan.md section 5) or unpublished, per the approver's call.
- Catalog: open catalog pull requests updated for the rename get withdrawn or corrected; merged catalog records stay as history per 3.2.
- Every rollback step is recorded in acceptance evidence like any other live-host change (docs/11-working-together.md rhythm).

## 6. The owner decision checklist

Every item needs Kyle's own words, given directly — an explicit yes, never a relayed one (docs/06-rules-and-lessons.md approval gates).

- D1 — Confirm the mapping: umbrella rizzstack; flww, hyvv, bzzq and orbt as tabled in section 2, including the orbit-control-plane disposition.
- D2 — Authorize the legal and availability screening (trademark, domains, organization handles) before any rename; the names are NOT legally cleared until this passes.
- D3 — Authorize the at-once rename window and its date, contingent on D2 passing.
- D4 — Decide the catalog keys and titles; the default is that they stay as they are (docs/06 rule).
- D5 — Authorize the umbrella launch and the hosting choice from docs/website-plan.md section 4.
- D6 — Confirm the Night Hive theme timing: applied only when branding un-defers (docs/website-plan.md section 5).
- D7 — Approve the historical-name preservation rule for campaign records (section 3.6).
- D8 — Close the superseded swrm proposal in ROADMAP as never-started, replaced by bzzq.

## 7. Public-safe content rules for this plan and the future site

The repository's standing rule is the baseline (README: secrets, tokens, tailnet hostnames, private IPs and private URLs are deliberately left out). This plan and the future site keep it: no tokens, no private hosts, no live data. Credential guidance stays prose, with value-free colon lines and non-triggering property names where a shape is unavoidable; the build-side mechanical gate is specified in docs/website-plan.md section 7.

## 8. Validation

tests/test_rebrand_plan.py validates this document structurally (17 checks) and scans both plan documents for secret-shaped or private content; tests/test_website_plan.py does the same for the website plan (14 checks), 31 checks in total. RED-first: the checks were written first and failed against the missing documents, then both plans were written to satisfy them — 31 failing to 31 passing, the same bar the r1 attempt met.
