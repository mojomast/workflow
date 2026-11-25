"""Quarantine-first write path tests for ``rizzstack.memory/1``.

These tests exercise the hardened write surface:

* AC-1 a bee cannot escape its own quarantine subtree;
* AC-2 a secret-bearing payload is refused before storage and the refusal is
  scrubbed;
* AC-3 promotion needs a valid grant, curated zones need a human approver and a
  bee cannot self-promote;
* AC-4 quarantine writes and promotions append fsynced receipts;
* AC-5 the normative oracle and the M1 disk suite stay untouched and green
  (run them alongside this module).

The key-shaped fixture is assembled from fragments at runtime so this source
file carries no provider-shaped literal. The stub scanner is generated in a
temporary directory and receives the marker through its environment, never
through a file in the repository.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rizzstack_memory import (  # noqa: E402
    TYPE_DIR,
    TYPE_POLICY,
    ContractError,
    DiskVault,
    quarantine_prefix,
    serialize_memory,
)
from rizzstack_memory import write_path  # noqa: E402
from tests.test_memory_contract import (  # noqa: E402
    LATER,
    WORKED_BODY,
    WRITER,
    base_record,
    grant,
    sealed,
    write_op,
)

SCANNER_MARKER_ENV = "MEMORY_WRITE_SCANNER_MARKER"
SCANNER_CAPTURE_ENV = "MEMORY_WRITE_SCANNER_CAPTURE"

STUB_SCANNER = """#!/usr/bin/env python3
import os
import sys

data = sys.stdin.buffer.read()
capture = os.environ.get("MEMORY_WRITE_SCANNER_CAPTURE")
if capture:
    with open(capture, "wb") as handle:
        handle.write(data)
marker = os.environ.get("MEMORY_WRITE_SCANNER_MARKER", "").encode("utf-8")
if marker and marker in data:
    sys.stdout.write("RuleID: generic-api-key\\n")
    sys.exit(1)
sys.exit(0)
"""


def key_shaped_literal() -> str:
    """A key-shaped fixture assembled from fragments; never a file literal."""
    return "".join(("gh", "p_", "Q7w9E2r4T6y8U0i2", "O4p6A8s0D2f4G6h8J0"))


def leaky_body(marker: str) -> str:
    return "# Leaky note\n\nObserved deploy material: " + marker + "\n"


def typed_record(memory_type: str, memory_id: str, body: str = None, **retention) -> dict:
    record = base_record(
        id=memory_id,
        type=memory_type,
        retention={"policy": TYPE_POLICY[memory_type], "expires": None, "superseded_by": None, **retention},
    )
    return sealed(record, body)


def make_stub(root, body: str = STUB_SCANNER) -> str:
    target = Path(root) / "stub-scanner"
    target.write_text(body, encoding="utf-8")
    target.chmod(0o755)
    return str(target)


def read_log(root) -> list:
    text = (Path(root) / "log.md").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class QuarantineEscapeTests(unittest.TestCase):
    """AC-1: every new memory lands in the writer's quarantine subtree."""

    def test_a_bee_writes_only_inside_its_own_quarantine_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            own = quarantine_prefix(WRITER) + "own-note.md"
            own_record = typed_record("learning", "own-note")
            receipt = write_path.write_quarantined(
                vault, write_op(path=own, record=own_record), WRITER
            )
            self.assertTrue(receipt["accepted"])
            self.assertTrue((Path(tmp) / own).is_file())
            self.assertEqual(receipt["path"], own)
            self.assertEqual(vault.receipts()[-1]["path"], own)

            outside_record = typed_record("learning", "outside-note")
            with self.assertRaises(ContractError) as caught:
                write_path.write_quarantined(
                    vault,
                    write_op(path="learnings/outside-note.md", record=outside_record),
                    WRITER,
                )
            self.assertEqual(caught.exception.code, "write_quarantined")
            self.assertFalse((Path(tmp) / "learnings" / "outside-note.md").exists())

            foreign = quarantine_prefix("agent:bee-9") + "foreign-note.md"
            with self.assertRaises(ContractError) as caught:
                write_path.write_quarantined(
                    vault,
                    write_op(path=foreign, record=typed_record("learning", "foreign-note")),
                    WRITER,
                )
            self.assertEqual(caught.exception.code, "write_quarantined")
            self.assertFalse((Path(tmp) / foreign).exists())

            direct = vault.write_envelope(
                write_op(
                    path="learnings/direct-note.md",
                    record=typed_record("learning", "direct-note"),
                )
            )
            self.assertFalse(direct["accepted"])
            self.assertEqual(direct["code"], "write_quarantined")
            self.assertFalse((Path(tmp) / "learnings" / "direct-note.md").exists())

            with self.assertRaises(ContractError) as caught:
                write_path.write_quarantined(
                    vault,
                    write_op(path=own, record=typed_record("learning", "own-note")),
                    ".quarantine/agent-bee-7",
                )
            self.assertEqual(caught.exception.code, "schema_invalid")

    def test_a_grant_cannot_be_smuggled_through_a_quarantined_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            path = quarantine_prefix(WRITER) + "smuggled.md"
            with self.assertRaises(ContractError) as caught:
                write_path.write_quarantined(
                    vault,
                    write_op(
                        path=path,
                        record=typed_record("learning", "smuggled"),
                        authority=grant(),
                    ),
                    WRITER,
                )
            self.assertEqual(caught.exception.code, "write_bad_grant")
            self.assertFalse((Path(tmp) / path).exists())


class SecretGateTests(unittest.TestCase):
    """AC-2: the gate refuses a secret before storage and scrubs the refusal."""

    def test_a_secret_payload_is_refused_before_storage_and_scrubbed(self):
        marker = key_shaped_literal()
        body = leaky_body(marker)
        with tempfile.TemporaryDirectory() as tmp:
            scanner = make_stub(tmp)
            capture = Path(tmp) / "captured-payload.bin"
            vault = DiskVault(tmp, scanner=scanner)
            record = typed_record("learning", "leaky-note", body)
            path = quarantine_prefix(WRITER) + "leaky-note.md"
            environment = {SCANNER_MARKER_ENV: marker, SCANNER_CAPTURE_ENV: str(capture)}
            with mock.patch.dict(os.environ, environment):
                with self.assertRaises(ContractError) as caught:
                    write_path.write_quarantined(
                        vault,
                        write_op(path=path, record=record, body=body),
                        WRITER,
                    )
            self.assertEqual(caught.exception.code, "secret_detected")
            self.assertFalse((Path(tmp) / path).exists())
            self.assertEqual(vault.receipts(), [])
            self.assertEqual(capture.read_bytes(), serialize_memory(record, body).encode("utf-8"))

            refusal_text = vault.refusal_log_path.read_text(encoding="utf-8")
            self.assertFalse(marker in refusal_text, "the refusal log contains the payload literal")
            self.assertFalse(marker in str(caught.exception), "the refusal message contains the payload literal")
            self.assertFalse(marker in (Path(tmp) / "log.md").read_text(encoding="utf-8"))
            self.assertIn("generic-api-key", refusal_text)
            self.assertEqual(vault.refusal_receipts()[-1]["code"], "secret_detected")

    def test_the_operation_surface_also_gates_secret_payloads(self):
        marker = key_shaped_literal()
        body = leaky_body(marker)
        with tempfile.TemporaryDirectory() as tmp:
            scanner = make_stub(tmp)
            vault = DiskVault(tmp, scanner=scanner)
            record = typed_record("learning", "surface-leak", body)
            path = quarantine_prefix(WRITER) + "surface-leak.md"
            with mock.patch.dict(os.environ, {SCANNER_MARKER_ENV: marker}):
                envelope = vault.write_envelope(write_op(path=path, record=record, body=body))
            self.assertFalse(envelope["accepted"])
            self.assertEqual(envelope["code"], "secret_detected")
            self.assertFalse(marker in envelope["message"])
            self.assertFalse((Path(tmp) / path).exists())
            self.assertEqual(vault.receipts(), [])

    def test_a_scanner_that_cannot_run_refuses_the_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp, scanner=str(Path(tmp) / "missing-scanner"))
            path = quarantine_prefix(WRITER) + "unscanned.md"
            with self.assertRaises(ContractError) as caught:
                write_path.write_quarantined(
                    vault,
                    write_op(path=path, record=typed_record("learning", "unscanned")),
                    WRITER,
                )
            self.assertEqual(caught.exception.code, "scanner_unavailable")
            self.assertFalse((Path(tmp) / path).exists())
            self.assertEqual(vault.receipts(), [])
            self.assertEqual(vault.refusal_receipts()[-1]["code"], "scanner_unavailable")

    def test_a_scanner_that_fails_to_exit_cleanly_refuses_the_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            scanner = make_stub(tmp, "#!/usr/bin/env python3\nimport sys\nsys.exit(2)\n")
            vault = DiskVault(tmp, scanner=scanner)
            path = quarantine_prefix(WRITER) + "broken-gate.md"
            with self.assertRaises(ContractError) as caught:
                write_path.write_quarantined(
                    vault,
                    write_op(path=path, record=typed_record("learning", "broken-gate")),
                    WRITER,
                )
            self.assertEqual(caught.exception.code, "scanner_unavailable")
            self.assertFalse((Path(tmp) / path).exists())


class PromotionGrantTests(unittest.TestCase):
    """AC-3: promotion needs a valid grant; curated zones need a human."""

    def test_a_bot_grant_cannot_promote_into_a_curated_zone_but_a_human_can(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            memory_id = "curated-reference"
            record = typed_record("reference", memory_id, expires=LATER)
            source = quarantine_prefix(WRITER) + f"{memory_id}.md"
            write_path.write_quarantined(vault, write_op(path=source, record=record), WRITER)
            target = Path(tmp) / TYPE_DIR["reference"] / f"{memory_id}.md"

            bad_grants = (
                None,
                grant(approved_by="orbit:coordinator"),
                grant(approved_by="bundlebees:bee-7"),
                grant(approved_by="bot:reviewer"),
                {"grant_ref": "approvals/incomplete.md"},
            )
            for bad in bad_grants:
                with self.assertRaises(ContractError) as caught:
                    write_path.promote(vault, memory_id, bad)
                self.assertEqual(caught.exception.code, "write_bad_grant")
                self.assertTrue((Path(tmp) / source).is_file())
                self.assertFalse(target.exists())

            receipt = write_path.promote(vault, memory_id, grant(approved_by="human:owner"))
            self.assertTrue(receipt["accepted"])
            self.assertEqual(receipt["path"], f"concepts/{memory_id}.md")
            self.assertTrue(target.is_file())
            self.assertFalse((Path(tmp) / source).exists())
            self.assertEqual(vault.read(receipt["path"])["record"]["id"], memory_id)

    def test_a_reviewed_zone_promotion_with_a_valid_grant_writes_one_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            memory_id = "reviewed-learning"
            record = typed_record("learning", memory_id)
            source = quarantine_prefix(WRITER) + f"{memory_id}.md"
            write_path.write_quarantined(vault, write_op(path=source, record=record), WRITER)
            before = (Path(tmp) / "log.md").read_text(encoding="utf-8")
            receipt = write_path.promote(vault, memory_id, grant(approved_by="orbit:coordinator"))
            after = (Path(tmp) / "log.md").read_text(encoding="utf-8")

            self.assertTrue(receipt["accepted"])
            self.assertEqual(receipt["path"], f"learnings/{memory_id}.md")
            self.assertTrue(after.startswith(before), "log.md must stay append-only")
            added = [line for line in after[len(before):].splitlines() if line.strip()]
            self.assertEqual(len(added), 1)
            entry = json.loads(added[0])
            self.assertEqual(entry["seq"], receipt["log_seq"])
            self.assertEqual(entry["path"], f"learnings/{memory_id}.md")
            self.assertEqual(entry["id"], memory_id)
            self.assertTrue(entry["granted"])
            self.assertEqual(entry["sha"], record["sha"])
            self.assertEqual([line["seq"] for line in read_log(tmp)], [1, 2])

    def test_a_bee_can_never_self_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            bee = "bundlebees:bee-7"
            memory_id = "bee-learning"
            record = typed_record("learning", memory_id)
            source = quarantine_prefix(bee) + f"{memory_id}.md"
            write_path.write_quarantined(
                vault,
                write_op(path=source, record=record, writer=bee),
                bee,
            )
            with self.assertRaises(ContractError) as caught:
                write_path.promote(vault, memory_id, grant(approved_by=bee))
            self.assertEqual(caught.exception.code, "write_bad_grant")
            self.assertTrue((Path(tmp) / source).is_file())
            self.assertFalse((Path(tmp) / TYPE_DIR["learning"] / f"{memory_id}.md").exists())

            with self.assertRaises(ContractError) as caught:
                write_path.promote(vault, memory_id, grant(approved_by=WRITER))
            self.assertEqual(caught.exception.code, "write_bad_grant")
            self.assertTrue((Path(tmp) / source).is_file())

    def test_a_missing_memory_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            with self.assertRaises(ContractError) as caught:
                write_path.promote(vault, "absent-memory", grant())
            self.assertEqual(caught.exception.code, "not_found")
            self.assertEqual(vault.receipts(), [])


class ReceiptTests(unittest.TestCase):
    """AC-4: receipts are append-only for accepted quarantines and promotions."""

    def test_accepted_quarantine_and_promotion_receipts_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            memory_id = "receipt-learning"
            record = typed_record("learning", memory_id)
            source = quarantine_prefix(WRITER) + f"{memory_id}.md"
            quarantine_receipt = write_path.write_quarantined(
                vault, write_op(path=source, record=record), WRITER
            )
            first_log = (Path(tmp) / "log.md").read_text(encoding="utf-8")
            promotion = write_path.promote(vault, memory_id, grant(approved_by="orbit:coordinator"))
            second_log = (Path(tmp) / "log.md").read_text(encoding="utf-8")

            self.assertEqual(quarantine_receipt["log_seq"], 1)
            self.assertEqual(promotion["log_seq"], 2)
            self.assertTrue(second_log.startswith(first_log))
            entries = read_log(tmp)
            self.assertEqual([entry["seq"] for entry in entries], [1, 2])
            self.assertEqual(entries[0]["path"], source)
            self.assertFalse(entries[0]["granted"])
            self.assertEqual(entries[1]["path"], f"learnings/{memory_id}.md")
            self.assertTrue(entries[1]["granted"])
            self.assertEqual(set(entries[1]), {"seq", "at", "writer", "path", "id", "sha", "granted"})


class OracleStaysGreenTests(unittest.TestCase):
    """AC-5: the new pipeline does not fork the digest or frontmatter rules."""

    def test_the_worked_example_still_round_trips_through_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            path = quarantine_prefix(WRITER) + "workbench-crash-resume.md"
            receipt = write_path.write_quarantined(vault, write_op(path=path), WRITER)
            self.assertEqual(receipt["sha"], sealed()["sha"])
            stored = vault.read(path)
            self.assertEqual(stored["body"], WORKED_BODY)
            self.assertEqual(stored["record"]["sha"], receipt["sha"])


if __name__ == "__main__":
    unittest.main()
