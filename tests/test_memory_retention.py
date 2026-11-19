"""Tests for the rizzstack.memory/1 retention runner.

Every scenario builds a tempfile-backed vault. The fixtures are written as raw
markdown so the runner's pairing refusals can be exercised for records the
write path itself would reject; valid records use the same serialiser and
digest as the vault service.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rizzstack_memory import DiskVault, memory_sha, parse_memory, serialize_memory  # noqa: E402
from rizzstack_memory import retention  # noqa: E402
from rizzstack_memory.vault import TYPE_POLICY  # noqa: E402

CONTRACT = "rizzstack.memory/1"
NOW = "2026-11-14T18:20:00Z"
LATER = "2026-11-15T09:00:00Z"
PAST = "2026-01-01T00:00:00Z"
BODY = (
    "# Retention fixture\n"
    "\n"
    "A lease retention pass needle lives here.\n"
)


def make_record(
    memory_type: str,
    memory_id: str,
    *,
    expires=None,
    superseded_by=None,
    policy=None,
    body: str = BODY,
) -> dict:
    record = {
        "schema": CONTRACT,
        "id": memory_id,
        "type": memory_type,
        "created": NOW,
        "modified": NOW,
        "retention": {
            "policy": TYPE_POLICY[memory_type] if policy is None else policy,
            "expires": expires,
            "superseded_by": superseded_by,
        },
        "sources": [{"kind": "operator-note", "ref": "tests/test_memory_retention.py"}],
        "sha": "",
    }
    record["sha"] = memory_sha(record, body)
    return record


def write_raw(vault: DiskVault, path: str, record: dict, body: str = BODY) -> Path:
    target = Path(vault.root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_memory(record, body), encoding="utf-8")
    return target


def read_log(vault: DiskVault) -> list:
    text = (Path(vault.root) / "log.md").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def by_id(records: list) -> dict:
    return {record["id"]: record for record in records}


class RetentionRunnerTests(unittest.TestCase):
    def test_stale_items_are_hidden_by_default_and_returned_with_include_expired(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            stale_ref = make_record("reference", "stale-reference", expires=PAST)
            superseded = make_record("learning", "superseded-learning", superseded_by="newer-learning")
            fresh = make_record("learning", "fresh-learning")
            write_raw(vault, "concepts/stale-reference.md", stale_ref)
            write_raw(vault, "learnings/superseded-learning.md", superseded)
            fresh_path = write_raw(vault, "learnings/fresh-learning.md", fresh)

            decisions = retention.run(vault, NOW)
            decided = by_id(decisions)
            self.assertEqual(decided["stale-reference"]["reason"], "expiry")
            self.assertEqual(decided["stale-reference"]["action"], "logged")
            self.assertEqual(decided["superseded-learning"]["reason"], "supersession")
            self.assertEqual(decided["superseded-learning"]["action"], "logged")
            self.assertEqual(decided["fresh-learning"]["action"], "active")

            self.assertEqual([record["id"] for record in vault.active_records(NOW)], ["fresh-learning"])
            shown = by_id(vault.active_records(NOW, include_expired=True))
            self.assertEqual(set(shown), {"stale-reference", "superseded-learning", "fresh-learning"})
            self.assertEqual(shown["stale-reference"]["retention"], stale_ref["retention"])
            self.assertEqual(shown["superseded-learning"]["retention"], superseded["retention"])

            default_hits = vault.query({"op": "query", "q": "needle"}, now=NOW)
            self.assertEqual([hit["id"] for hit in default_hits["hits"]], ["fresh-learning"])
            all_hits = vault.query({"op": "query", "q": "needle", "include_expired": True}, now=NOW)
            self.assertEqual(
                sorted(hit["id"] for hit in all_hits["hits"]),
                ["fresh-learning", "stale-reference", "superseded-learning"],
            )

            log = read_log(vault)
            self.assertEqual([entry["seq"] for entry in log], [1, 2])
            self.assertTrue(all(entry["kind"] == "retention" for entry in log))
            self.assertEqual(fresh_path.read_text(encoding="utf-8"), serialize_memory(fresh, BODY))

    def test_a_second_run_with_the_same_clock_appends_no_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            write_raw(vault, "concepts/stale-reference.md", make_record("reference", "stale-reference", expires=PAST))
            write_raw(
                vault,
                "learnings/superseded-learning.md",
                make_record("learning", "superseded-learning", superseded_by="newer-learning"),
            )

            first = by_id(retention.run(vault, NOW))
            first_log = read_log(vault)
            self.assertEqual(
                [first[memory_id]["seq"] for memory_id in ("stale-reference", "superseded-learning")],
                [1, 2],
            )

            second = by_id(retention.run(vault, NOW))
            self.assertEqual(second["stale-reference"]["action"], "unchanged")
            self.assertEqual(second["superseded-learning"]["action"], "unchanged")
            self.assertEqual(read_log(vault), first_log)

    def test_one_receipt_per_state_change_with_strictly_increasing_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            fresh = make_record("learning", "fresh-learning")
            vault.write(
                {
                    "op": "write",
                    "writer": "agent:bee-7",
                    "path": "learnings/fresh-learning.md",
                    "memory": fresh,
                    "body": BODY,
                    "expected_sha": None,
                    "authority": {
                        "grant_ref": "approvals/2026-11-14-retention.md",
                        "approved_by": "orbit:coordinator",
                        "approved_at": LATER,
                    },
                }
            )
            write_raw(vault, "concepts/stale-a.md", make_record("reference", "stale-a", expires=PAST))
            write_raw(vault, "concepts/stale-b.md", make_record("reference", "stale-b", expires=PAST))
            write_raw(
                vault,
                "learnings/superseded-learning.md",
                make_record("learning", "superseded-learning", superseded_by="newer-learning"),
            )

            retention.run(vault, NOW)
            log = read_log(vault)
            retention_entries = [entry for entry in log if entry.get("kind") == "retention"]
            self.assertEqual([entry["seq"] for entry in log], [1, 2, 3, 4])
            self.assertEqual([entry["seq"] for entry in retention_entries], [2, 3, 4])
            self.assertEqual(len({entry["id"] for entry in retention_entries}), 3)
            self.assertEqual(
                sorted(entry["id"] for entry in retention_entries),
                ["stale-a", "stale-b", "superseded-learning"],
            )
            for entry in retention_entries:
                self.assertIn(entry["event"], ("expiry", "supersession"))
                self.assertEqual(entry["at"], NOW)
                self.assertIn("fingerprint", entry)
                self.assertIn("retention", entry)
                self.assertEqual(parse_memory(Path(tmp, entry["path"]).read_text(encoding="utf-8"))[0]["id"], entry["id"])

    def test_a_decision_with_a_deadline_is_refused_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            bad = make_record("decision", "bad-decision", expires=PAST)
            path = write_raw(vault, "decisions/bad-decision.md", bad)
            before = path.read_text(encoding="utf-8")
            log_before = (Path(tmp) / "log.md").read_text(encoding="utf-8")

            decisions = retention.run(vault, NOW)
            self.assertEqual(len(decisions), 1)
            decision = decisions[0]
            self.assertEqual(decision["action"], "refused")
            self.assertEqual(decision["code"], "policy_mismatch")
            self.assertEqual(decision["id"], "bad-decision")
            self.assertEqual(decision["policy"], "decision-permanent")
            self.assertIn("bad-decision", decision["message"])
            self.assertIn("decision-permanent", decision["message"])
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertEqual((Path(tmp) / "log.md").read_text(encoding="utf-8"), log_before)

    def test_a_reference_without_a_deadline_is_refused_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            no_deadline = make_record("reference", "no-deadline", expires=None)
            write_raw(vault, "concepts/no-deadline.md", no_deadline)
            log_before = (Path(tmp) / "log.md").read_text(encoding="utf-8")

            decisions = retention.run(vault, NOW)
            self.assertEqual(len(decisions), 1)
            decision = decisions[0]
            self.assertEqual(decision["action"], "refused")
            self.assertEqual(decision["code"], "policy_mismatch")
            self.assertEqual(decision["id"], "no-deadline")
            self.assertEqual(decision["policy"], "reference-refresh")
            self.assertIn("no-deadline", decision["message"])
            self.assertIn("reference-refresh", decision["message"])
            self.assertEqual((Path(tmp) / "log.md").read_text(encoding="utf-8"), log_before)

    def test_a_fresh_learning_survives_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            fresh = make_record("learning", "fresh-learning")
            path = write_raw(vault, "learnings/fresh-learning.md", fresh)
            before = path.read_text(encoding="utf-8")

            decisions = retention.run(vault, NOW)
            self.assertEqual([decision["action"] for decision in decisions], ["active"])
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertEqual(read_log(vault), [])
            self.assertEqual([record["id"] for record in vault.active_records(NOW)], ["fresh-learning"])

    def test_a_dry_run_returns_decisions_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            write_raw(vault, "concepts/stale-reference.md", make_record("reference", "stale-reference", expires=PAST))
            write_raw(vault, "learnings/fresh-learning.md", make_record("learning", "fresh-learning"))

            decisions = by_id(vault.run_retention(NOW, dry_run=True))
            self.assertEqual(decisions["stale-reference"]["action"], "would_log")
            self.assertEqual(decisions["fresh-learning"]["action"], "active")
            self.assertEqual(read_log(vault), [])

    def test_the_documented_command_runs_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            write_raw(vault, "concepts/stale-reference.md", make_record("reference", "stale-reference", expires=PAST))

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "rizzstack_memory.retention",
                    "--vault",
                    tmp,
                    "--now",
                    NOW,
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["decisions"][0]["action"], "logged")
            self.assertEqual(payload["decisions"][0]["reason"], "expiry")
            log = read_log(vault)
            self.assertEqual(len(log), 1)
            self.assertEqual(log[0]["id"], "stale-reference")


if __name__ == "__main__":
    unittest.main()
