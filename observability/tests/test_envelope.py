"""Review P3: one envelope discriminator across these records and bee.usage/v1."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from envelope import EnvelopeError, normalize, record_type  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class EnvelopeTests(unittest.TestCase):
    def test_every_example_has_a_discriminator(self) -> None:
        for path in sorted(EXAMPLES.glob("*.json")):
            with self.subTest(example=path.name):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assertRegex(record_type(doc), r"^[a-z][a-z0-9_.-]*/v[0-9]+$")

    def test_frozen_usage_record_maps_without_changing_it(self) -> None:
        usage = {"schema_version": "bee.usage/v1", "key": "attempt:att_1", "route": "go"}
        self.assertEqual(record_type(usage), "bee.usage/v1")
        normalized = normalize(usage)
        self.assertEqual(normalized["schema"], "bee.usage/v1")
        self.assertEqual(normalized["schema_version"], "bee.usage/v1")
        self.assertNotIn("schema", usage)

    def test_package_records_use_schema(self) -> None:
        doc = {"schema": "agent.lifecycle/v1", "schema_version": "v1"}
        self.assertEqual(record_type(doc), "agent.lifecycle/v1")

    def test_contradictions_and_missing_types_are_refused(self) -> None:
        for bad in (
            {},
            {"schema_version": "v1"},
            {"schema": "agent.lifecycle/v1", "schema_version": "v2"},
            {"schema": "agent.lifecycle/v1", "schema_version": "bee.usage/v1"},
            {"schema": "Agent Lifecycle"},
        ):
            with self.subTest(record=bad), self.assertRaises(EnvelopeError):
                record_type(bad)


if __name__ == "__main__":
    unittest.main()
