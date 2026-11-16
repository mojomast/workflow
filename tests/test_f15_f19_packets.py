"""F15-F19 packet validation — the wave-4 networking-and-worker-deploy slices.

Validates the five delivered packets under plans/packets/ (F15 relay, F16
tailcat, F17 join probing, F18 revocable worker credentials, F19 live-host
join-install rehearsal) against the recovered packet shape, and checks the
one thing a disposable sandbox cannot fake: the protocol pin. Every packet
must pin a workflow_ref that exists in a fresh clone of the origin repository
at the lease base — a commit that exists only inside the working sandbox is
unreachable once the sandbox dies and is forbidden (that is exactly the
workflow_ref_unknown failure official verify reported against the previous
attempt).

The reachability and schema-drift checks need git history. Where this
checkout has none (a verify copy without .git, for example), those checks skip
with a stated reason; the pin-vs-lease-base equality check never skips.

Runs under pytest (`python3 -m pytest tests/test_f15_f19_packets.py -q`) and
under unittest (`python3 -m unittest tests.test_f15_f19_packets -q`).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_wave4_packets import (  # noqa: E402
    DEP_RE,
    REQUIRED_SECTIONS,
    assert_shape,
    parse_packet,
    text_of,
)

PACKETS = ROOT / "plans" / "packets"

F15_F19 = {
    "F15": "F15-relay.md",
    "F16": "F16-tailcat.md",
    "F17": "F17-join-probing.md",
    "F18": "F18-revocable-tokens.md",
    "F19": "F19-live-host-join-install.md",
}

# The lease base of this campaign: a commit on the origin repository's main,
# carrying the enforced feature-packet and source-resolution schemas byte for
# byte. Pinning anything else — above all a commit that only the working
# sandbox has — reproduces the workflow_ref_unknown failure this delivery
# exists to repair.
WORKFLOW_PIN = "d4e6c504884fbf64c86c18033b59484137614646"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

EXPECTED_REPOSITORY = "mojomast/orbitdesktop"

CONTENT_NEEDLES = {
    "F15": (
        "one-time pairing code",
        "short-lived scoped worker credential",
        "never opens an inbound port",
        "long-poll",
        "WorkerBackend",
        "unit of trust",
        "single use",
    ),
    "F16": (
        "tailcat",
        "BSD-3-Clause",
        "no root",
        "BSD-3-Clause",
        "DERP",
        "--allow",
        "ephemeral",
        "v0.7.0",
        "self-hosted DERP",
        "power-user overlay",
    ),
    "F17": (
        "fixed order",
        "HTTPS",
        "localhost",
        "tailcat",
        "--orbit-url",
        "--ts-authkey",
        "XXXX-YYYY",
        "capabilities",
        "Docker socket",
    ),
    "F18": (
        "source of truth",
        "fails closed",
        "offline",
        "in-flight attempt",
        "quarantine",
        "second layer",
        "never required to stop claims",
    ),
    "F19": (
        "throwaway",
        "image digest",
        "pairing code",
        "revocation drill",
        "checklist",
        "live host",
        "not run",
        "explicit yes",
    ),
}


def git(*args: str, repo: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def pinned_checkout() -> Path:
    """The checkout whose history a protocol pin is validated against.

    WORKFLOW_SRC names the protocol checkout when the caller sets one (the
    validator's own convention, docs/23 §4); otherwise this checkout is it.
    """
    env = os.environ.get("WORKFLOW_SRC")
    if env and Path(env).is_dir():
        return Path(env)
    return ROOT


def packet_text(parsed: dict) -> str:
    return "\n".join([parsed["heading"], *(text_of(parsed, s) for s in REQUIRED_SECTIONS)])


class F15F19PacketTests(unittest.TestCase):
    def test_the_five_packets_exist_and_the_readme_links_them(self):
        readme = (PACKETS / "README.md").read_text(encoding="utf-8")
        for packet_id, name in F15_F19.items():
            path = PACKETS / name
            self.assertTrue(path.is_file(), f"{name} is missing under plans/packets/")
            self.assertIn(f"]({name})", readme, f"README does not link {name}")
            self.assertIn(packet_id, readme, f"README does not name {packet_id}")
        self.assertIn(WORKFLOW_PIN, readme, "README does not state the protocol pin convention")
        self.assertIn("workflow_ref_unknown", readme, "README does not warn against sandbox-only pins")

    def test_each_packet_parses_with_the_full_required_shape(self):
        for packet_id, name in F15_F19.items():
            with self.subTest(packet=packet_id):
                parsed = parse_packet(PACKETS / name)
                assert_shape(parsed)

    def test_every_packet_pins_the_workflow_lease_base_commit(self):
        for packet_id, name in F15_F19.items():
            with self.subTest(packet=packet_id):
                parsed = parse_packet(PACKETS / name)
                pin = parsed["header"].get("workflow_ref", "")
                self.assertRegex(pin, SHA_RE, f"{name}: workflow_ref is not a full 40-hex commit SHA")
                self.assertEqual(
                    pin, WORKFLOW_PIN,
                    f"{name}: workflow_ref {pin!r} is not the lease base {WORKFLOW_PIN}. "
                    f"A pin that exists only inside a disposable worker sandbox is "
                    f"forbidden: the origin remote refuses it as not our ref, no "
                    f"coordinator checkout has it, and official verify fails every "
                    f"packet carrying it with workflow_ref_unknown.",
                )

    def test_the_pinned_commit_is_reachable_and_carries_the_enforced_schema_bytes(self):
        """Reachability plus the validator drift guard, against real history.

        Needs a checkout that actually holds the pinned commit (WORKFLOW_SRC or
        this checkout). Where none does, this skips with a stated reason — the
        equality check above still applies, and reachability must then be
        proven against a fresh clone of the origin repository before shipping.
        """
        repo = pinned_checkout()
        exists = git("cat-file", "-e", f"{WORKFLOW_PIN}^{{commit}}", repo=repo)
        if exists.returncode != 0:
            self.skipTest(
                f"workflow_ref_unknown here: {WORKFLOW_PIN} is not a commit in {repo} "
                f"({(exists.stderr or 'no git history').strip().splitlines()[-1] if (exists.stderr or exists.stdout) else 'no git history'}); "
                f"reachability must be proven against a fresh clone of the origin "
                f"repository before shipping"
            )
        for schema in ("feature-packet.schema.json", "source-resolution.schema.json"):
            pinned = git("show", f"{WORKFLOW_PIN}:schemas/{schema}", repo=repo)
            self.assertEqual(pinned.returncode, 0, f"{WORKFLOW_PIN} does not bear schemas/{schema}")
            enforced = (ROOT / "schemas" / schema).read_text(encoding="utf-8")
            self.assertEqual(
                pinned.stdout, enforced,
                f"schemas/{schema} at {WORKFLOW_PIN} differs from the enforced file; "
                f"the validator drift guard (validator_mismatch) would refuse this pin",
            )

    def test_each_packet_targets_orbitdesktop_and_carries_its_scope(self):
        for packet_id, name in F15_F19.items():
            with self.subTest(packet=packet_id):
                parsed = parse_packet(PACKETS / name)
                self.assertEqual(parsed["header"]["repository"], EXPECTED_REPOSITORY)
                whole = packet_text(parsed)
                for needle in CONTENT_NEEDLES[packet_id]:
                    self.assertIn(needle, whole, f"{name} is missing `{needle}`")

    def test_the_provenance_headers_record_the_reconstruction(self):
        for packet_id, name in F15_F19.items():
            with self.subTest(packet=packet_id):
                parsed = parse_packet(PACKETS / name)
                self.assertIn("rizzstack-dogfood-campaign", parsed["header"]["source_plan"], name)
                self.assertIn("recovered", parsed["header"]["source_plan"], name)
                self.assertIn("not reachable from this checkout", parsed["header"]["provenance"], name)
                self.assertRegex(parsed["header"]["drafted"], r"2026-11-16", f"{name}: drafted date")

    def test_the_dependency_graph_is_acyclic_and_f15_is_its_root(self):
        graph = {}
        for packet_id, name in F15_F19.items():
            parsed = parse_packet(PACKETS / name)
            refs = [m.group(1) for m in DEP_RE.finditer(text_of(parsed, "Dependencies"))]
            graph[packet_id] = sorted({re.match(r"(F\d+)", r).group(1) for r in refs if re.match(r"(F\d+)", r)})
        self.assertEqual(graph["F15"], [], f"F15 depends on {graph['F15']}; the wave's foundation depends on no packet")
        self.assertEqual(graph["F16"], ["F15"], f"F16 depends on {graph['F16']}")
        self.assertEqual(graph["F17"], ["F15", "F16"], f"F17 depends on {graph['F17']}")
        self.assertEqual(graph["F18"], ["F15"], f"F18 depends on {graph['F18']}")
        self.assertEqual(graph["F19"], ["F15", "F17", "F18"], f"F19 depends on {graph['F19']}")
        # The wave's foundation is F15: every other packet must depend on it,
        # directly or transitively, and no dependency cycle may exist.
        dependents: dict[str, set[str]] = {pid: set() for pid in F15_F19}
        for node, deps in graph.items():
            for dep in deps:
                dependents.setdefault(dep, set()).add(node)

        def roots_of(pid: str, seen: frozenset[str] = frozenset()) -> set[str]:
            if pid in seen:
                return set()  # a cycle would surface in the DFS below
            found = {pid}
            for dep in graph.get(pid, ()):
                found |= roots_of(dep, seen | {pid})
            return found

        for packet_id in F15_F19:
            self.assertIn("F15", roots_of(packet_id), f"{packet_id} does not depend on F15, the wave's foundation")

        state: dict[str, int] = {}

        def visit(node: str, path: tuple[str, ...]) -> None:
            if state.get(node) == 1:
                self.fail(f"the dependency graph has a cycle through {' -> '.join((*path, node))}")
            if state.get(node) == 2:
                return
            state[node] = 1
            for dep in graph.get(node, ()):
                visit(dep, (*path, node))
            state[node] = 2

        for packet_id in F15_F19:
            visit(packet_id, ())

    def test_the_relay_slice_states_the_pairing_qr_rules_it_freezes(self):
        parsed = parse_packet(PACKETS / F15_F19["F15"])
        whole = packet_text(parsed)
        self.assertIn("no coordinator-wide credential", whole)
        self.assertIn("expiry", whole)
        self.assertIn("refresh endpoint", whole)
        self.assertIn("revoked", whole)

    def test_the_tailcat_slice_keeps_hosted_tailscale_out_of_the_default_path(self):
        parsed = parse_packet(PACKETS / F15_F19["F16"])
        whole = packet_text(parsed)
        self.assertIn("no Tailscale account", whole)
        self.assertIn("never a second coordinator", whole)
        self.assertIn("bearer", whole.lower())

    def test_the_join_probe_order_is_frozen_as_https_localhost_tailcat_mesh(self):
        parsed = parse_packet(PACKETS / F15_F19["F17"])
        whole = packet_text(parsed)
        self.assertIn("HTTPS URL, then localhost, then tailcat, then mesh-with-provided-auth", whole)
        self.assertIn("never a crash or a silent fallback", whole)
        self.assertIn("first claim", whole)

    def test_the_revocation_slice_keeps_transport_teardown_second(self):
        parsed = parse_packet(PACKETS / F15_F19["F18"])
        whole = packet_text(parsed)
        self.assertIn("no grace window", whole)
        self.assertIn("before any work item is offered", whole)
        self.assertIn("never required to stop claims", whole)

    def test_the_rehearsal_slice_keeps_the_live_host_out_of_scope(self):
        parsed = parse_packet(PACKETS / F15_F19["F19"])
        whole = packet_text(parsed)
        self.assertIn("separately approved action", whole)
        self.assertIn("never as passed", whole)
        self.assertIn("refuses a target that resolves to the live host", whole)


if __name__ == "__main__":
    unittest.main()
