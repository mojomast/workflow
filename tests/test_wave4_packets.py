"""Wave-4 plan-packet validation.

Parses the four Wave-4 feature packets under plans/packets/ (F11-F14) and
fails closed on any packet that drops the F1-F10 packet shape: the header
block, Intent, Delivered and remaining, Acceptance criteria
(`AC-NNN ... -> proven by <path::test>`), Dependencies, Authorization needs
and exactly one Next executable action. The directory-contents test pins the
exact packet set: wave-4 F11-F14 plus the F15-F19 reconstruction wave plus
the README index. Also checks that cross-references
between packets resolve, that each packet's repository and dependency story
matches the recovered dogfood plan's Wave-4 scope, and that the README index
lists the packets.

Runs under pytest (`python3 -m pytest tests/test_wave4_packets.py -q`) and
under unittest (`python3 -m unittest tests.test_wave4_packets -q`); no
network, no git history and no third-party imports.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKETS = ROOT / "plans" / "packets"

WAVE4 = {
    "F11": "F11-runnable-by-anyone.md",
    "F12": "F12-connect-github-repo-picker.md",
    "F13": "F13-bifrost-optin-router.md",
    "F14": "F14-acdd-evidence-wiring.md",
}

REQUIRED_HEADER_KEYS = (
    "packet_id",
    "wave",
    "status",
    "repository",
    "source_plan",
    "drafted",
    "provenance",
)

REQUIRED_SECTIONS = (
    "Intent",
    "Delivered and remaining",
    "Acceptance criteria",
    "Dependencies",
    "Authorization needs",
    "Next executable action",
)

HUMAN_GATES = ("merge", "release", "deploy", "publish")

HEADER_RE = re.compile(r"^- ([a-z_]+): (.+)$")
TITLE_RE = re.compile(r"^# (F\d+) — (.+)$")
SECTION_RE = re.compile(r"^## (.+?)\s*$")
AC_RE = re.compile(r"^- (AC-\d{3}) (.+?) -> proven by (.+)$")
DEP_RE = re.compile(r"^- (\S[^:]*): (.+)$", re.M)
NUMBERED_RE = re.compile(r"^\d+\. (\S.*)$")


def parse_packet(path: Path) -> dict:
    """Parse one F-packet into header fields, sections and typed lines.

    Raises AssertionError with the offending line number on any shape this
    parser cannot read unambiguously, so an unparsable packet fails closed.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    parsed: dict = {"path": path, "header": {}, "sections": {}, "order": []}

    match = TITLE_RE.match(lines[0]) if lines else None
    assert match, f"{path.name}: first line is not an `# F<NN> — title` heading"
    parsed["packet_id"], parsed["title"] = match.group(1), match.group(2)
    parsed["heading"] = lines[0]

    header_done = False
    current = None
    for lineno, raw in enumerate(lines[1:], start=2):
        line = raw.rstrip()
        header = HEADER_RE.match(line) if not header_done else None
        section = SECTION_RE.match(line)
        if not line and not header_done and current is None:
            continue
        if header:
            assert not current, f"{path.name}:{lineno}: header key after the first section"
            assert header.group(1) not in parsed["header"], (
                f"{path.name}:{lineno}: duplicate header key {header.group(1)}"
            )
            parsed["header"][header.group(1)] = header.group(2).strip()
            continue
        if section:
            header_done = True
            current = section.group(1)
            assert current not in parsed["sections"], f"{path.name}:{lineno}: duplicate section {current!r}"
            parsed["sections"][current] = []
            parsed["order"].append(current)
            continue
        if line and not header_done:
            header_done = True
        assert current, f"{path.name}:{lineno}: content outside any section"
        parsed["sections"][current].append((lineno, line))
    return parsed


def text_of(parsed: dict, section: str) -> str:
    return "\n".join(line for _, line in parsed["sections"].get(section, []))


def assert_shape(parsed: dict) -> None:
    path = parsed["path"]
    for key in REQUIRED_HEADER_KEYS:
        assert key in parsed["header"], f"{path.name}: header is missing `{key}:`"
    assert parsed["packet_id"] == parsed["header"]["packet_id"], (
        f"{path.name}: title id and packet_id header disagree"
    )
    assert parsed["header"]["wave"] == "4", f"{path.name}: wave is not 4"
    assert parsed["header"]["repository"] == "mojomast/orbitdesktop", (
        f"{path.name}: repository is not mojomast/orbitdesktop"
    )
    assert parsed["header"]["status"].strip(), f"{path.name}: empty status"

    for name in REQUIRED_SECTIONS:
        assert name in parsed["sections"], f"{path.name}: missing section `## {name}`"
        assert any(line.strip() for _, line in parsed["sections"][name]), (
            f"{path.name}: section `## {name}` is empty"
        )

    remaining = text_of(parsed, "Delivered and remaining")
    assert re.search(r"^\|\s*Delivered\s*\|", remaining, re.M), (
        f"{path.name}: `Delivered and remaining` has no `| Delivered |` row"
    )
    assert re.search(r"^\|\s*Remaining\s*\|", remaining, re.M), (
        f"{path.name}: `Delivered and remaining` has no `| Remaining |` row"
    )

    ac_lines = [line for _, line in parsed["sections"]["Acceptance criteria"] if line.startswith("- ")]
    assert ac_lines, f"{path.name}: Acceptance criteria holds no criteria bullets"
    for line in ac_lines:
        assert line.startswith("- AC-"), (
            f"{path.name}: acceptance bullet is not an `AC-NNN` criterion: {line[:60]}"
        )
    matched = [m for m in (AC_RE.match(line) for line in ac_lines) if m]
    assert len(matched) == len(ac_lines), (
        f"{path.name}: an AC bullet does not match `AC-NNN ... -> proven by ...`"
    )
    assert len(matched) >= 3, f"{path.name}: fewer than three parseable `AC-NNN ... -> proven by` lines"
    ids = [m.group(1) for m in matched]
    assert len(ids) == len(set(ids)), f"{path.name}: duplicate acceptance-criterion ids"
    for m in matched:
        target = m.group(3)
        assert (
            "<" not in target and "..." not in target and "::" in target
        ), f"{path.name}: {m.group(1)} has no `path::test` proven-by target"
        assert m.group(2).strip(), f"{path.name}: {m.group(1)} states no observable behavior"

    deps = [DEP_RE.match(line) for _, line in parsed["sections"]["Dependencies"] if line.startswith("- ")]
    matched_deps = [d for d in deps if d]
    assert len(matched_deps) >= 2, f"{path.name}: fewer than two stated dependencies"

    auth = text_of(parsed, "Authorization needs")
    assert re.search(r"^- Approver:", auth, re.M), f"{path.name}: Authorization needs names no approver"
    gates = re.search(r"^- Human gates: (.+)$", auth, re.M)
    assert gates, f"{path.name}: Authorization needs has no `Human gates:` line"
    for gate in HUMAN_GATES:
        assert re.search(rf"\b{gate}\b", gates.group(1)), f"{path.name}: human gate `{gate}` is missing"
    assert re.search(r"^- Not authorized by this packet:", auth, re.M), (
        f"{path.name}: Authorization needs does not state what stays unauthorized"
    )

    numbered = [NUMBERED_RE.match(line) for _, line in parsed["sections"]["Next executable action"]]
    actions = [m for m in numbered if m]
    assert len(actions) == 1, f"{path.name}: Next executable action must hold exactly one numbered action"


class Wave4PacketTests(unittest.TestCase):
    def test_all_campaign_packets_exist_and_nothing_else(self):
        files = sorted(p.name for p in PACKETS.iterdir() if p.is_file())
        # Manifest lock: the four Wave-4 feature packets, the F15-F19
        # reconstruction wave (tests/test_f15_f19_packets.py pins those five
        # files, their shapes and their pins), plus the M2 canary prep packet
        # (wf docs/m2-canary-prep) and the README index. The M2-canary packet
        # recorded this exact lock extension as a repo-hygiene handoff because
        # the test file was outside that packet lease; the F15-F19 wave
        # extended the same lock. The exact-set rule stays: a missing packet
        # or an extra file fails closed.
        f15_f19 = (
            "F15-relay.md",
            "F16-tailcat.md",
            "F17-join-probing.md",
            "F18-revocable-tokens.md",
            "F19-live-host-join-install.md",
        )
        self.assertEqual(
            files, sorted([*WAVE4.values(), *f15_f19, "M2-canary.md", "README.md"])
        )

    def test_each_packet_parses_with_the_full_required_shape(self):
        for packet_id, name in WAVE4.items():
            with self.subTest(packet=packet_id):
                parsed = parse_packet(PACKETS / name)
                assert_shape(parsed)

    def test_packet_ids_match_filenames_and_are_the_wave4_series(self):
        for packet_id, name in WAVE4.items():
            parsed = parse_packet(PACKETS / name)
            self.assertTrue(
                parsed["heading"].startswith(f"# {packet_id} — "),
                f"{name}: heading does not start with `# {packet_id} — `",
            )
            self.assertTrue(
                parsed["title"].lower() in parsed["heading"].lower(),
                f"{name}: captured title is not part of the heading",
            )
        self.assertEqual(list(WAVE4), ["F11", "F12", "F13", "F14"])

    def test_provenance_records_the_recovered_plan_and_the_unreachable_archive(self):
        for packet_id, name in WAVE4.items():
            parsed = parse_packet(PACKETS / name)
            self.assertIn("rizzstack-dogfood-campaign", parsed["header"]["source_plan"])
            self.assertIn("recovered", parsed["header"]["source_plan"])

    def test_f11_carries_the_runnable_by_anyone_scope_left_by_orbit_25(self):
        parsed = parse_packet(PACKETS / WAVE4["F11"])
        whole = "\n".join([parsed["title"], *(text_of(parsed, s) for s in REQUIRED_SECTIONS)])
        for needle in ("Orbit #25", "hermetic tests", "agent registry", "quickstart"):
            self.assertIn(needle, whole, f"F11 is missing `{needle}`")
        self.assertIn("docs/15", whole)
        # The follow-ups are scoped to what #25 left undone, not a re-statement of it.
        self.assertIn("Orbit #25 (merged", whole)

    def test_f12_is_the_spec_of_open_orbit_27_not_a_reimplementation(self):
        parsed = parse_packet(PACKETS / WAVE4["F12"])
        whole = "\n".join([parsed["title"], *(text_of(parsed, s) for s in REQUIRED_SECTIONS)])
        for needle in ("Orbit #27", "device flow", "0600", "never logged", "repository picker"):
            self.assertIn(needle, whole, f"F12 is missing `{needle}`")
        self.assertIn("not a re-implementation", whole)
        # The operator's three repos stay data, never a shipped default.
        self.assertIn("mojomast/workflow", whole)
        self.assertIn("mojomast/bundlebees", whole)
        self.assertIn("mojomast/orbitdesktop", whole)
        self.assertIn("never as a shipped default", whole)

    def test_f13_freezes_the_bifrost_optin_router_invariants(self):
        parsed = parse_packet(PACKETS / WAVE4["F13"])
        whole = "\n".join([parsed["title"], *(text_of(parsed, s) for s in REQUIRED_SECTIONS)])
        for needle in (
            "Bifrost",
            'profiles: ["router"]',
            "digest",
            "0600",
            "LiteLLM",
            "OpenCode free models stay",
            "Docker socket",
        ):
            self.assertIn(needle, whole, f"F13 is missing `{needle}`")
        self.assertTrue(
            re.search(r"[Oo]ff[- ]by[- ]default", whole),
            "F13 never states the off-by-default rule",
        )

    def test_f14_builds_on_merged_orbit_26_and_30_for_chips_feed_and_smoke(self):
        parsed = parse_packet(PACKETS / WAVE4["F14"])
        whole = "\n".join([parsed["title"], *(text_of(parsed, s) for s in REQUIRED_SECTIONS)])
        for needle in ("Orbit #26", "Orbit #30", "Board chips", "activity feed", "smoke"):
            self.assertIn(needle, whole, f"F14 is missing `{needle}`")
        for code in ("red_invalid", "tests_tampered", "scope_violation", "integration_failed", "unrun"):
            self.assertIn(code, whole, f"F14 does not carry failure code {code}")
        self.assertIn("not a campaign closeout", whole)

    def test_dependencies_reference_existing_packets_only(self):
        known = set(WAVE4)
        for packet_id, name in WAVE4.items():
            parsed = parse_packet(PACKETS / name)
            refs = [m.group(1) for m in DEP_RE.finditer(text_of(parsed, "Dependencies"))]
            for ref in refs:
                leading = re.match(r"(F\d+)", ref)
                if leading:
                    self.assertIn(leading.group(1), known, f"{packet_id} depends on unknown packet {leading.group(1)}")
            if packet_id in ("F12", "F13", "F14"):
                self.assertTrue(
                    any(re.match(r"F\d+", ref) for ref in refs),
                    f"{packet_id} must state its dependency on another Wave-4 packet",
                )

    def test_f14_declares_the_runnable_by_anyone_gate_docs16_requires(self):
        parsed = parse_packet(PACKETS / WAVE4["F14"])
        deps = text_of(parsed, "Dependencies")
        self.assertIn("F11", deps)
        self.assertIn("runnable-by-anyone", deps)

    def test_readme_indexes_the_wave4_packets_and_the_packet_shape(self):
        readme = (PACKETS / "README.md").read_text(encoding="utf-8")
        for name in WAVE4.values():
            self.assertIn(f"]({name})", readme, f"README does not link {name}")
        for section in REQUIRED_SECTIONS:
            self.assertIn(f"`## {section}`", readme, f"README does not document the `{section}` section")
        self.assertIn("never authority", readme)
        self.assertIn("test_wave4_packets.py", readme)


if __name__ == "__main__":
    unittest.main()
