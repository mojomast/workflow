"""M2 canary pre-stage validation (packet, runbook, cleanup path).

RED-first: this module was written and executed against a tree that did not
yet contain the M2-canary packet or the runbook, and every test below failed
there (`FileNotFoundError` on both artifacts). It stays green only while the
pre-staged canary keeps the shape the owner decided:

- a dedicated fresh smoke project, `rizzstack-m2-canary`, defined and
  registered at the campaign-plan layer by plans/packets/M2-canary.md, with
  no production project touched anywhere in the artifacts;
- a runbook (docs/m2-canary-runbook.md) whose steps are the exact end-to-end
  sequence for the moment F2 (require-contract) merges: contract required
  end-to-end, one bee, RED-first acceptance, verify, review, receiver
  decision — each step with a command and expected evidence;
- a synthetic feature bounded to two source files and one approved test file
  with no dependencies, meaningful enough to exercise the contract boundary;
- a rollback/cleanup path that removes only canary-named state.

The tests are structural: they parse the artifacts and their embedded
contract JSON, and they fail closed when a step, an evidence expectation or a
cleanup guarantee is dropped. They do not run the canary and they do not
touch production configuration.

Runs under pytest (`python3 -m pytest tests/test_m2_canary_prep.py -q`) and
under unittest (`python3 -m unittest tests.test_m2_canary_prep -q`); standard
library only, no network, no git history.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "plans" / "packets" / "M2-canary.md"
RUNBOOK = ROOT / "docs" / "m2-canary-runbook.md"

CANARY_NAME = "rizzstack-m2-canary"
CANARY_REPO = "mojomast/rizzstack-m2-canary"
CONTRACT_ID = "M2-canary-wave-tally"
BASE_REV = "9f6aa6dc7a74890ef2284d7aa4432efc9b6a4169"

# Production repositories the canary must never write toward. They may appear
# in prose and in read-only preflight probes, never in a mutating command.
PRODUCTION_REPOS = (
    "mojomast/workflow",
    "mojomast/bundlebees",
    "mojomast/orbitdesktop",
    "mojomast/hyvv",
)

REQUIRED_PACKET_HEADER_KEYS = (
    "packet_id",
    "wave",
    "status",
    "repository",
    "source_plan",
    "drafted",
    "provenance",
)

REQUIRED_PACKET_SECTIONS = (
    "Intent",
    "Delivered and remaining",
    "Acceptance criteria",
    "Dependencies",
    "Authorization needs",
    "Next executable action",
)

HUMAN_GATES = ("merge", "release", "deploy", "publish")

HEADER_RE = re.compile(r"^- ([a-z_]+): (.+)$")
TITLE_RE = re.compile(r"^# (M2-canary) — (.+)$")
SECTION_RE = re.compile(r"^## (.+?)\s*$")
AC_RE = re.compile(r"^- (AC-\d{3}) (.+?) -> proven by (.+)$", re.M)
DEP_RE = re.compile(r"^- (\S+): (.+)$", re.M)
NUMBERED_RE = re.compile(r"^\d+\. (\S.*)$")
STEP_RE = re.compile(r"^## Step (\d+) — (.+?)\s*$")
FENCE_RE = re.compile(r"^```([A-Za-z0-9]*)\s*$")
WRITE_TOWARD_RE = re.compile(
    r"\b(git\s+push|git\s+merge|gh\s+pr\s+(create|merge|close)"
    r"|gh\s+repo\s+(create|delete|edit|archive)"
    r"|gh\s+release\s+(create|delete))\b"
)
DESTRUCTIVE_RE = re.compile(r"^\s*(sudo\s+)?(rm|rmdir|mv)\b")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_packet(text: str) -> dict:
    """Parse the M2-canary plan packet into header fields and sections.

    Raises AssertionError with the offending line number on any shape this
    parser cannot read unambiguously, so an unparsable packet fails closed.
    """
    lines = text.splitlines()
    parsed: dict = {"header": {}, "sections": {}, "order": []}

    match = TITLE_RE.match(lines[0]) if lines else None
    assert match, "packet: first line is not an `# M2-canary — title` heading"
    parsed["title"] = match.group(2)

    header_done = False
    current = None
    for lineno, raw in enumerate(lines[1:], start=2):
        line = raw.rstrip()
        header = HEADER_RE.match(line) if not header_done else None
        section = SECTION_RE.match(line)
        if not line and not header_done and current is None:
            continue
        if header:
            assert not current, f"packet:{lineno}: header key after the first section"
            assert header.group(1) not in parsed["header"], (
                f"packet:{lineno}: duplicate header key {header.group(1)}"
            )
            parsed["header"][header.group(1)] = header.group(2).strip()
            continue
        if section:
            header_done = True
            current = section.group(1)
            assert current not in parsed["sections"], f"packet:{lineno}: duplicate section {current!r}"
            parsed["sections"][current] = []
            parsed["order"].append(current)
            continue
        if line and not header_done:
            header_done = True
        assert current, f"packet:{lineno}: content outside any section"
        parsed["sections"][current].append((lineno, line))
    return parsed


def section_text(parsed: dict, name: str) -> str:
    return "\n".join(line for _, line in parsed["sections"].get(name, []))


def split_runbook_sections(text: str) -> dict:
    """Split the runbook into `## heading` sections, keyed by heading.

    Fence-aware: `## ` lines inside a fenced code block (for example the
    `PARKED.md` snapshot in the cleanup) are block content, not sections.
    """
    sections: dict = {}
    order: list = []
    current = None
    inside = False
    for line in text.splitlines():
        fence = FENCE_RE.match(line)
        if fence and not inside:
            inside = True
        elif line.strip() == "```" and inside:
            inside = False
        section = SECTION_RE.match(line) if not inside else None
        if section:
            current = section.group(1)
            assert current not in sections, f"runbook: duplicate section {current!r}"
            sections[current] = []
            order.append(current)
            continue
        if current is not None:
            sections[current].append(line)
    return {"sections": sections, "order": order}


def fenced_blocks(text: str) -> list:
    """Return the fenced code blocks of a text as (info_string, body) pairs."""
    blocks = []
    inside = None
    body: list = []
    for line in text.splitlines():
        opener = FENCE_RE.match(line)
        if opener and inside is None:
            inside = opener.group(1)
            body = []
            continue
        if line.strip() == "```" and inside is not None:
            blocks.append((inside, "\n".join(body)))
            inside = None
            continue
        if inside is not None:
            body.append(line)
    assert inside is None, "runbook: a fenced code block is never closed"
    return blocks


def command_lines(text: str) -> list:
    """Every non-empty, non-comment line of every fenced block."""
    lines = []
    for _, body in fenced_blocks(text):
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
    return lines


def extract_runbook_contract(text: str) -> dict:
    """Parse the canary's `acdd/1` contract JSON out of the runbook."""
    json_blocks = [body for info, body in fenced_blocks(text) if info == "json"]
    assert json_blocks, "runbook: no fenced ```json contract block"
    parsed = None
    for body in json_blocks:
        try:
            candidate = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("contract_version") == "acdd/1":
            assert parsed is None, "runbook: more than one acdd/1 contract block"
            parsed = candidate
    assert parsed is not None, "runbook: no acdd/1 contract JSON that parses"
    return parsed


class M2CanaryPacketTests(unittest.TestCase):
    def setUp(self):
        self.text = read(PACKET)
        self.parsed = parse_packet(self.text)

    def test_packet_exists_and_carries_the_registered_canary_identity(self):
        self.assertEqual(self.parsed["title"].lower(), "the m2 contract-enforcement canary")
        for key in REQUIRED_PACKET_HEADER_KEYS:
            self.assertIn(key, self.parsed["header"], f"header is missing `{key}:`")
        self.assertEqual(self.parsed["header"]["packet_id"], "M2-canary")
        self.assertEqual(self.parsed["header"]["repository"], CANARY_REPO)
        self.assertIn(CANARY_NAME, section_text(self.parsed, "Intent"))
        # Registration at the campaign-plan layer is what "pre-staged" means:
        # nothing is registered on the worker host until the runbook runs.
        self.assertIn("campaign-plan layer", self.text)
        self.assertIn("runtime registration", self.text)

    def test_status_blocks_dispatch_until_f2_merges(self):
        status = self.parsed["header"]["status"]
        self.assertIn("pre-staged", status)
        self.assertIn("blocked until F2", status)
        self.assertIn("merged", status)

    def test_all_required_sections_are_present_and_non_empty(self):
        for name in REQUIRED_PACKET_SECTIONS:
            self.assertIn(name, self.parsed["sections"], f"missing section `## {name}`")
            self.assertTrue(
                any(line.strip() for _, line in self.parsed["sections"][name]),
                f"section `## {name}` is empty",
            )

    def test_delivered_and_remaining_splits_prep_from_run(self):
        remaining = section_text(self.parsed, "Delivered and remaining")
        self.assertIsNotNone(re.search(r"^\|\s*Delivered\s*\|", remaining, re.M))
        self.assertIsNotNone(re.search(r"^\|\s*Remaining\s*\|", remaining, re.M))
        # The delivered side carries the pre-staged artifacts; the remaining
        # side is everything the runbook executes after F2 merges.
        self.assertIn("docs/m2-canary-runbook.md", remaining)
        self.assertIn("test_m2_canary_prep.py", remaining)

    def test_acceptance_criteria_are_the_canary_run_criteria(self):
        lines = [
            line for _, line in self.parsed["sections"]["Acceptance criteria"] if line.startswith("- ")
        ]
        self.assertGreaterEqual(len(lines), 4, "fewer than four acceptance criteria")
        matched = [AC_RE.match(line) for line in lines]
        self.assertTrue(all(matched), f"an AC bullet does not match `AC-NNN ... -> proven by ...`: {lines}")
        ids = [m.group(1) for m in matched]
        self.assertEqual(len(ids), len(set(ids)), "duplicate acceptance-criterion ids")
        for m in matched:
            target = m.group(3)
            self.assertNotIn("<", target)
            self.assertNotIn("...", target)
            self.assertIn("::", target, f"{m.group(1)} has no `path::test` proven-by target")
            self.assertTrue(m.group(2).strip(), f"{m.group(1)} states no observable behavior")
            path = target.split("::")[0]
            self.assertTrue(
                path.startswith("tests/") or path.startswith("evidence/"),
                f"{m.group(1)} is proven by `{path}`, outside the canary repo's tests/ or evidence/",
            )
        self.assertEqual(ids[:4], ["AC-001", "AC-002", "AC-003", "AC-004"])

    def test_dependencies_name_f2_the_protocol_and_the_directory_lock(self):
        deps = section_text(self.parsed, "Dependencies")
        bullets = [line for _, line in self.parsed["sections"]["Dependencies"] if line.startswith("- ")]
        self.assertGreaterEqual(len(bullets), 2, "fewer than two stated dependencies")
        self.assertIn("F2", deps)
        self.assertIn("require-contract", deps)
        self.assertIn("docs/16-acdd-tdd.md", deps)
        # The known repo-hygiene conflict is carried in the artifact itself:
        # adding a fifth file to plans/packets/ trips the Wave-4 lock test.
        self.assertIn("test_all_four_packets_exist_and_nothing_else", deps)
        self.assertIn("test_wave4_packets.py", deps)

    def test_authorization_names_the_approver_gates_and_production_hands_off(self):
        auth = section_text(self.parsed, "Authorization needs")
        self.assertIsNotNone(re.search(r"^- Approver: .*(Kyle|mojomast)", auth, re.M))
        gates = re.search(r"^- Human gates: (.+)$", auth, re.M)
        self.assertIsNotNone(gates, "Authorization needs has no `Human gates:` line")
        for gate in HUMAN_GATES:
            self.assertRegex(gates.group(1), rf"\b{gate}\b", f"human gate `{gate}` is missing")
        self.assertIsNotNone(re.search(r"^- Not authorized by this packet:", auth, re.M))
        for repo in PRODUCTION_REPOS:
            self.assertIn(repo, auth, f"Authorization needs does not name production repo {repo}")

    def test_exactly_one_next_executable_action_gated_on_f2(self):
        numbered = [
            NUMBERED_RE.match(line)
            for _, line in self.parsed["sections"]["Next executable action"]
        ]
        actions = [m for m in numbered if m]
        self.assertEqual(len(actions), 1, "Next executable action must hold exactly one numbered action")
        action = actions[0].group(1)
        self.assertIn("F2", action)
        self.assertIn("docs/m2-canary-runbook.md", action)

    def test_provenance_records_the_recovered_branch_and_the_docs16_machinery(self):
        provenance = self.parsed["header"]["provenance"]
        self.assertIn("recovered", self.parsed["header"]["source_plan"])
        self.assertIn("docs/16-acdd-tdd.md", provenance)
        self.assertIn("require_contract", provenance)


class M2CanaryRunbookTests(unittest.TestCase):
    def setUp(self):
        self.text = read(RUNBOOK)
        self.rb = split_runbook_sections(self.text)
        self.steps = {
            int(m.group(1)): (m.group(2), "\n".join(self.rb["sections"][heading]))
            for heading, body in self.rb["sections"].items()
            for m in [STEP_RE.match(f"## {heading}")]
            if m
        }

    def test_header_states_trigger_base_and_blast_radius(self):
        head = self.text[: self.text.index("## ")]
        self.assertIn("F2", head)
        self.assertIn("require-contract", head)
        self.assertIn(BASE_REV, head)
        self.assertIn(CANARY_NAME, head)
        self.assertIn("no production project", head)

    def test_steps_zero_through_twelve_exist_in_order_with_command_and_evidence(self):
        self.assertEqual(sorted(self.steps), list(range(13)), "the runbook must carry Steps 0-12 in order")
        for number, (title, body) in self.steps.items():
            blocks = fenced_blocks(body)
            self.assertTrue(blocks, f"Step {number} ({title}) has no command block")
            self.assertIn("Expected evidence", body, f"Step {number} ({title}) states no expected evidence")

    def test_step_sequence_covers_the_full_enforcement_path(self):
        titles = {number: title.lower() for number, (title, _) in self.steps.items()}
        whole = {number: body.lower() for number, (_, body) in self.steps.items()}

        def step_with(needle, haystack=None):
            pool = haystack or titles
            hits = [n for n, text in pool.items() if needle in text]
            return hits

        self.assertTrue(step_with("preflight"), "no preflight step")
        self.assertTrue(step_with("freeze"), "no contract-freeze step")
        self.assertTrue(step_with("register"), "no project-registration step")
        self.assertTrue(step_with("dispatch"), "no dispatch step")
        self.assertTrue(step_with("red"), "no RED step")
        self.assertTrue(step_with("green"), "no GREEN step")
        self.assertTrue(step_with("review"), "no review step")
        self.assertTrue(step_with("integrate"), "no integration step")
        self.assertTrue(step_with("return"), "no RETURN step")
        self.assertTrue(step_with("receiver decision"), "no receiver-decision step")
        self.assertIn("contract_missing", whole[5], "the negative probe step must name `contract_missing`")
        self.assertIn("require_contract", whole[4], "registration must turn require_contract on for the canary")
        self.assertIn("test_fingerprints", whole[8], "the GREEN step must check unchanged test fingerprints")
        self.assertIn("assigned_files", whole[8], "the GREEN step must check the lease")

    def test_budget_is_exactly_one_bee_with_no_automatic_retry(self):
        dispatch = self.steps[6][1]
        self.assertRegex(dispatch, r"[Oo]ne bee|1 dispatch|exactly one")
        whole = self.text.lower()
        self.assertIn("30 minutes", whole)
        self.assertRegex(whole, r"no (automatic |auto )?retr(y|ies)")

    def test_receiver_decision_stays_pending_and_human(self):
        body = "\n".join(body for _, body in self.steps.values())
        self.assertIn('"status": "pending"', body)
        self.assertIn("templates/RETURN.md", body)
        self.assertIn("accept / request changes / blocked", body)
        self.assertRegex(body, r"never.{0,80}manifest|manifest.{0,80}never")

    def test_cleanup_removes_only_canary_state(self):
        self.assertIn("Rollback and cleanup", self.rb["sections"], "no rollback/cleanup section")
        cleanup = "\n".join(self.rb["sections"]["Rollback and cleanup"])
        for needle in (
            ".workflow/project-state.json",
            "archived",
            "tools/project-state/check.py",
            CANARY_NAME,
        ):
            self.assertIn(needle, cleanup, f"cleanup does not carry `{needle}`")
        self.assertRegex(cleanup, r"human:(mojomast|owner)")
        # The repository is archived, never deleted: the evidence outlives the cleanup.
        self.assertRegex(cleanup, r"(?i)\barchiv")
        self.assertRegex(cleanup, r"(?i)never delet")
        for line in command_lines(cleanup):
            if DESTRUCTIVE_RE.match(line):
                self.assertIn("canary", line.lower(), f"cleanup deletes non-canary state: {line}")
        for repo in PRODUCTION_REPOS:
            self.assertNotIn(
                f"gh repo delete {repo}",
                cleanup,
                f"cleanup must never delete {repo}",
            )
        self.assertNotIn("gh repo delete", command_lines_str(self.text), "no gh repo delete anywhere in the runbook")

    def test_cleanup_verifies_production_state_is_untouched(self):
        cleanup = "\n".join(self.rb["sections"]["Rollback and cleanup"])
        self.assertIn("untouched", cleanup.lower())
        for repo in PRODUCTION_REPOS:
            self.assertIn(repo, self.text)
        probes = [line for line in command_lines(cleanup)]
        self.assertTrue(
            any(("status" in line or "rev-parse" in line or "diff" in line) for line in probes),
            "cleanup never re-checks production repository state",
        )

    def test_no_command_writes_toward_a_production_repository(self):
        for line in command_lines(self.text):
            if WRITE_TOWARD_RE.search(line):
                for repo in PRODUCTION_REPOS:
                    self.assertNotIn(
                        repo,
                        line,
                        f"a runbook command mutates production state: {line}",
                    )

    def test_command_surface_is_confirmed_against_the_merged_revision(self):
        self.assertIn("docs/16", self.text)
        self.assertIn("confirm in Step 0", self.text)
        self.assertIn("flags", self.text.lower())
        self.assertRegex(self.text, r"(?i)never.{0,80}invented|invented silently")

    def test_prep_self_check_names_the_required_test_command(self):
        self.assertIn("python3 -m pytest tests/test_m2_canary_prep.py -q", self.text)
        self.assertIn("test_m2_canary_prep.py", self.text)

    def test_failure_handling_classifies_instead_of_retrying(self):
        failure_headings = [h for h in self.rb["sections"] if h.startswith("Failure")]
        self.assertTrue(failure_headings, "no failure-handling section")
        failure = "\n".join(self.rb["sections"][failure_headings[0]]).lower()
        self.assertIn("failure_class", failure)
        self.assertIn("escalate", failure)


class M2CanaryContractTests(unittest.TestCase):
    def setUp(self):
        self.runbook = read(RUNBOOK)
        self.packet = read(PACKET)
        self.contract = extract_runbook_contract(self.runbook)

    def test_contract_identity_and_bounded_scope(self):
        self.assertEqual(self.contract["id"], CONTRACT_ID)
        self.assertEqual(self.contract["contract_version"], "acdd/1")
        self.assertEqual(self.contract["dependencies"], [], "the canary must have no dependencies")
        self.assertEqual(
            self.contract["scope"]["assigned_files"],
            ["canary/meter.py", "canary/report.py"],
            "the synthetic feature must stay a bounded two-file lease",
        )
        self.assertEqual(self.contract["scope"]["test_files"], ["tests/test_meter.py"])
        self.assertTrue(self.contract["tdd"]["applicable"])
        self.assertTrue(self.contract["tdd"]["test_first"])
        self.assertEqual(
            set(self.contract["evidence_required"]),
            {"red", "green", "integration", "review"},
        )
        self.assertTrue(self.contract["verification"]["independent"])
        self.assertTrue(self.contract["source_rev"].strip().startswith("<BASE_SHA"))

    def test_contract_acs_match_the_packet_proven_by_targets(self):
        packet_acs = dict(
            (m.group(1), m.group(3).strip())
            for m in AC_RE.finditer(section_text(parse_packet(self.packet), "Acceptance criteria"))
        )
        contract_acs = {c["id"]: c for c in self.contract["acceptance_criteria"]}
        self.assertEqual(
            sorted(contract_acs),
            sorted(packet_acs),
            "packet and contract disagree on the acceptance-criterion ids",
        )
        for ac_id, target in packet_acs.items():
            criterion = contract_acs[ac_id]
            if target.split("::")[0].startswith("tests/"):
                self.assertIn(target, criterion.get("tests", []), f"{ac_id}: test id drift between packet and contract")

    def test_authorization_inside_the_contract_matches_the_packet_gates(self):
        gates = set(self.contract["authorization"]["human_gates"])
        self.assertTrue(set(HUMAN_GATES) <= gates)
        not_authorized = " ".join(self.contract["authorization"].get("not_authorized", []))
        for repo in PRODUCTION_REPOS:
            self.assertIn(repo, not_authorized, f"contract does not forbid touching {repo}")


def command_lines_str(text: str) -> str:
    return "\n".join(command_lines(text))


if __name__ == "__main__":
    unittest.main()
