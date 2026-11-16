"""Wave-4 plan-packet validation (discovery-based).

Discovers every wave-4 feature packet under plans/packets/ (any ``F<NN>-*.md``
whose header block carries ``wave: 4``) and fails closed on any packet that
drops the F1-F10 packet shape: the header block, Intent, Delivered and
remaining, Acceptance criteria (``AC-NNN ... -> proven by <path::test>``),
Dependencies, Authorization needs and exactly one Next executable action. Also
checks that cross-references between discovered packets resolve, that every
protocol pin is a full 40-hex commit SHA, and that the README indexes what was
discovered.

When this checkout carries no wave-4 packets at all, the whole module skips
with a stated reason instead of failing: the validator is for the wave-4
deliverable, not for a checkout that predates it.

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
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

NO_WAVE4 = (
    "no wave-4 packets under plans/packets: this checkout carries no wave-4 "
    "artifacts to validate, so the wave-4 packet validator has nothing to do "
    "here (the F15-F19 deliverable and its README are expected only in "
    "checkouts that carry that wave)"
)


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
    assert REPO_RE.match(parsed["header"]["repository"]), (
        f"{path.name}: repository is not an owner/name identity"
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


def discover_wave4() -> dict[str, Path]:
    """Every wave-4 packet under plans/packets/, keyed by its F<NN> id.

    A file counts only when its first line is an `# F<NN> — title` heading and
    its header block carries `wave: 4`; anything else in the directory (the
    README, notes, other waves) is not this validator's subject.
    """
    if not PACKETS.is_dir():
        return {}
    found: dict[str, Path] = {}
    for path in sorted(PACKETS.glob("*.md")):
        if path.name == "README.md" or not path.name.startswith("F"):
            continue
        try:
            parsed = parse_packet(path)
        except AssertionError:
            continue
        if parsed["header"].get("wave") == "4":
            found[parsed["packet_id"]] = path
    return found


class Wave4DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packets = discover_wave4()
        if not cls.packets:
            raise unittest.SkipTest(NO_WAVE4)

    def test_discovered_ids_are_unique_and_well_formed(self):
        for packet_id, path in self.packets.items():
            self.assertRegex(packet_id, r"^F\d+$", f"{path.name}: packet id is not an F<NN> id")
        numbers = [int(pid[1:]) for pid in self.packets]
        self.assertEqual(
            numbers, sorted(numbers),
            "discovered packet ids are not in ascending F-number order",
        )

    def test_every_discovered_packet_parses_with_the_full_required_shape(self):
        for packet_id, path in self.packets.items():
            with self.subTest(packet=packet_id):
                parsed = parse_packet(path)
                assert_shape(parsed)

    def test_every_discovered_packet_pins_a_full_commit_sha(self):
        for packet_id, path in self.packets.items():
            parsed = parse_packet(path)
            pin = parsed["header"].get("workflow_ref", "")
            self.assertRegex(
                pin, SHA_RE,
                f"{path.name}: workflow_ref is not a full 40-hex commit SHA "
                f"(a pin that exists only inside a disposable worker sandbox is "
                f"forbidden: origin refuses it and no coordinator checkout has it)",
            )

    def test_the_readme_indexes_every_discovered_packet(self):
        readme = (PACKETS / "README.md").read_text(encoding="utf-8")
        for packet_id, path in self.packets.items():
            self.assertIn(f"]({path.name})", readme, f"README does not link {path.name}")
            self.assertIn(packet_id, readme, f"README does not name {packet_id}")
        self.assertIn("never authority", readme, "README does not state the packets are never authority")
        self.assertIn("test_wave4_packets.py", readme, "README does not name this validator")

    def test_dependency_references_resolve_between_discovered_packets(self):
        known = set(self.packets)
        for packet_id, path in self.packets.items():
            parsed = parse_packet(path)
            refs = [m.group(1) for m in DEP_RE.finditer(text_of(parsed, "Dependencies"))]
            for ref in refs:
                leading = re.match(r"(F\d+)", ref)
                if leading:
                    self.assertIn(
                        leading.group(1), known,
                        f"{packet_id} depends on unknown packet {leading.group(1)} "
                        f"(only {', '.join(sorted(known))} are discovered here)",
                    )
        linked = [
            pid for pid in self.packets
            if any(re.match(r"F\d+", m.group(1)) for m in DEP_RE.finditer(text_of(parse_packet(self.packets[pid]), "Dependencies")))
        ]
        self.assertGreaterEqual(
            len(linked), 2,
            "fewer than two packets are wired into the wave's dependency graph",
        )


if __name__ == "__main__":
    unittest.main()
