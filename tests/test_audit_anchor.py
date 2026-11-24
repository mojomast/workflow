"""Contract + collector tests for rizzstack.audit-anchor/1 (BEST-PRACTICE item 3).

Owner decision 2026-11-24 15:04 ET: a Rails-side collector, not uirizz, records the
uirizz audit chain head {log_id, seq, head_hash, ts} every 100 entries and on every
rotation; uirizz's verifier recomputes the chain against those anchors. No public
transparency log. The collector only reads the audit log; it appends to its own
anchor file and refuses to anchor a chain it cannot verify.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "observability"))
from validate import SchemaError, Validator  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "audit_anchor", ROOT / "contrib" / "rizzstack-observability" / "audit_anchor.py")
aa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aa)

ZERO = "0" * 64


def digest(prev: str, body: dict) -> str:
    """The uirizz gate's chain digest, restated independently."""
    blob = prev + json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def chain(n: int, prev: str = ZERO, first: dict | None = None) -> list[dict]:
    out = []
    for i in range(n):
        body = dict(first) if (i == 0 and first) else {"type": "note", "action_id": f"act-{i}", "note": "x"}
        body.update({"seq": i + 1, "ts": "2026-11-24T20:00:00Z", "_t": 1.0, "prev": prev})
        body["hash"] = digest(prev, body)
        out.append(body)
        prev = body["hash"]
    return out


def write(path: Path, entries: list[dict]) -> None:
    path.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries), encoding="utf-8")


class AnchorContract(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(ROOT / "observability" / "schemas")

    def anchor(self, **over) -> dict:
        a = {"schema": "rizzstack.audit-anchor/1", "log_id": "a" * 64, "seq": 100,
             "head_hash": "b" * 64, "ts": "2026-11-24T20:00:00Z", "reason": "interval"}
        a.update(over)
        return a

    def test_example_and_both_reasons_validate(self) -> None:
        example = json.loads((ROOT / "observability" / "examples" / "audit-anchor.json").read_text())
        self.validator.validate_file(example, "audit-anchor.schema.json")
        self.validator.validate_file(self.anchor(reason="rotation", seq=137), "audit-anchor.schema.json")

    def test_malformed_anchors_are_rejected(self) -> None:
        bad = (self.anchor(seq=0), self.anchor(head_hash="B" * 64), self.anchor(log_id="short"),
               self.anchor(reason="manual"), self.anchor(schema="rizzstack.audit-anchor/2"),
               self.anchor(extra=1), self.anchor(ts="yesterday"))
        for doc in bad:
            with self.subTest(doc=doc), self.assertRaises(SchemaError):
                self.validator.validate_file(doc, "audit-anchor.schema.json")


class Collector(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "actions.jsonl"
        self.anchors = self.tmp / "anchors.jsonl"
        self.validator = Validator(ROOT / "observability" / "schemas")

    def run_collector(self) -> int:
        return aa.main(["--log", str(self.log), "--anchors", str(self.anchors), "--now", "2026-11-24T20:00:00Z"])

    def recorded(self) -> list[dict]:
        if not self.anchors.exists():
            return []
        return [json.loads(line) for line in self.anchors.read_text().splitlines()]

    def test_anchors_every_hundred_entries_once(self) -> None:
        entries = chain(250)
        write(self.log, entries)
        self.assertEqual(self.run_collector(), 0)
        got = self.recorded()
        self.assertEqual([(a["seq"], a["head_hash"], a["reason"]) for a in got],
                         [(100, entries[99]["hash"], "interval"), (200, entries[199]["hash"], "interval")])
        self.assertTrue(all(a["log_id"] == entries[0]["hash"] for a in got))
        for a in got:
            self.validator.validate_file(a, "audit-anchor.schema.json")
        self.assertEqual(self.run_collector(), 0)
        self.assertEqual(len(self.recorded()), 2, "a re-run must not duplicate anchors")

    def test_rotation_anchors_the_old_segment_head(self) -> None:
        old = chain(137)
        write(self.tmp / "actions.jsonl.1", old)
        new = chain(3, prev=old[-1]["hash"], first={"type": "rotated", "from_seq": 137, "carried_actions": 0})
        write(self.log, new)
        self.assertEqual(self.run_collector(), 0)
        got = {(a["log_id"], a["seq"], a["reason"]): a["head_hash"] for a in self.recorded()}
        self.assertEqual(got[(old[0]["hash"], 137, "rotation")], old[-1]["hash"])
        self.assertIn((old[0]["hash"], 100, "interval"), got)

    def test_rotation_that_does_not_continue_the_backup_is_refused(self) -> None:
        write(self.tmp / "actions.jsonl.1", chain(20))
        write(self.log, chain(3, prev="c" * 64, first={"type": "rotated", "from_seq": 20, "carried_actions": 0}))
        self.assertNotEqual(self.run_collector(), 0)
        self.assertEqual(self.recorded(), [])

    def test_broken_chain_is_never_anchored(self) -> None:
        entries = chain(150)
        entries[42]["note"] = "edited"
        write(self.log, entries)
        self.assertNotEqual(self.run_collector(), 0)
        self.assertEqual(self.recorded(), [])

    def test_unparseable_line_fails_closed(self) -> None:
        write(self.log, chain(120))
        with self.log.open("a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        self.assertNotEqual(self.run_collector(), 0)
        self.assertEqual(self.recorded(), [])

    def test_missing_log_writes_nothing(self) -> None:
        self.assertNotEqual(self.run_collector(), 0)
        self.assertFalse(self.anchors.exists())

    def test_collector_never_writes_the_audit_log(self) -> None:
        write(self.log, chain(100))
        before = self.log.read_bytes()
        self.run_collector()
        self.assertEqual(self.log.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
