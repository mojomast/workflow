VERDICT: APPROVE

# Review — workflow PR #144 (ROADMAP refresh)

SPEC coverage (a)–(f) lands, in order: #7 is Done with `contrib/hermes-forge.md`
named (ROADMAP.md:29, 223-227); the release prep PRs, the hyvv merge and the
absence of new tags are recorded (180-192); Orbit onboarding states decision #25
option B, the M-A/M-B split, #27 retargeted to `main`, and #17/#18 closed as
superseded (161-175); memory records the query CLI and lessons seeder (152-157);
Rails records #84 as the default, links the dated superseding decision, and names
the P1 pagination runs next (55-67); quality gates records the advisory
lessons-check job (139-144). The "checked against GitHub on 24 November 2026,
America/Toronto" line is updated (7-8). Structure, section headings and voice are
preserved. The diff touches only `ROADMAP.md` and `CHANGELOG.md`, adds no host,
IP, private path or secret, and the CHANGELOG bullet sits first under
`## Unreleased` and reads like its neighbours.

## Findings

1. minor — `ROADMAP.md:186-188`: "No tags yet." is immediately followed by "The
   only release tags remain …", which reads as a contradiction before the reader
   works out that the first clause means the four bumped versions.
   Fix: replace "No tags yet." with "None of those four versions is tagged yet."

2. minor — `ROADMAP.md:64`: after the reorder, "Its paging numbers" has no clear
   antecedent (the nearest nouns are the index, the ledgers and the migration).
   Fix: replace "Its paging numbers against the 500 ms p95 target:" with "The
   index's paging numbers against the 500 ms p95 target:".

3. minor — `ROADMAP.md:175`: "**Closed:** Orbit #17 and #18 as superseded." is
   the only PR mention in the section without links, unlike #25/#27/#46.
   Fix: "- **Closed:** [Orbit #17](https://github.com/mojomast/orbitdesktop/pull/17)
   and [#18](https://github.com/mojomast/orbitdesktop/pull/18) as superseded."
   (URLs follow the section's existing orbitdesktop convention.)

4. minor — `ROADMAP.md:161`: "decision #25" is ambiguous next to "Orbit #25"
   (the install PR) on line 167.
   Fix: replace "decision #25 is option B" with "owner decision #25 is option B".

No blocker or major finding.

## Commands run

- `timeout 300 python3 -m unittest tests.test_rebrand_plan tests.test_website_plan`
  → exit 0 (Ran 31 tests, OK).
- `git status --porcelain` before writing → empty (the review file is the only
  addition).
- `tests/test_docs_parity.py` was not run: pytest is absent from this sandbox,
  as stated in the supplied facts (coordinator: exit 0 at both base and head).

## Accuracy pass

Accepted — all three corrections are accurate, not out of scope:

- **Memory.** #133 (`ebc22ca`) and #136 (`70392e5`) merged on 24 November, after
  base `ae9c080`. Leaving them "in progress" would be false for a document whose
  stated verification date is 24 November. I note that `rizzstack_memory/cli.py`,
  `rizzstack_memory/__main__.py` and `scripts/seed_memory_from_lessons.py` are
  not in this checkout; the "Done" wording rests on the supplied verified merge
  facts, which is acceptable for this review.
- **Quality gates.** #135 (`da73322`) merged on 24 November and adds the advisory
  `lessons-check` job; "advisory … never a required check" is the right
  characterisation, and the claim is consistent with the supplied facts even
  though `.github/workflows/ci.yml` in this head predates it.
- **Releases.** hyvv #41 (0.1.18) merged on 24 November; workflow #132,
  bundlebees #258 and orbitdesktop #91 are open; none of the four target versions
  is tagged. "In progress" plus "No tags yet" is accurate.

The two merged-state lines and the DECISION-2026-11-24 link are not verifiable
from this head, but they are covered by the supplied facts: #134 carries that
file and is queued ahead of this PR, so the link resolves once both land. The
only tree-visible caveat is the reading order in finding 1, not a factual error.
