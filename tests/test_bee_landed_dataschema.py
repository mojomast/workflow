"""RED for wave A slice A12a (review Fix now #13, workflow half).

The bee-landed event carries four identifiers. Two are deliberate and frozen:
the CloudEvents type ``rizzstack.bee.landed.v1`` and the payload schema
``rizzstack.bee-landed/1``. The other two disagree: the schema's ``$id`` and
the ``dataschema`` URI hyvv emits, which names a misspelled host. Workflow
owns the contract, so it names the canonical ``dataschema`` (its own ``$id``)
and accepts the legacy misspelled value as deprecated, so outbox files already
on disk still validate.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bee_landed  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "bee-landed.schema.json").read_text(encoding="utf-8"))
LEGACY = "https://" + "rizstack" + ".dev/schemas/bee-landed/v1"


class DataschemaIdentity(unittest.TestCase):
    def test_canonical_dataschema_is_the_schema_id(self):
        self.assertEqual(bee_landed.DATASCHEMA, SCHEMA["$id"])

    def test_legacy_value_is_listed_as_deprecated(self):
        self.assertIn(LEGACY, bee_landed.LEGACY_DATASCHEMAS)

    def test_schema_documents_the_canonical_value(self):
        description = SCHEMA["properties"]["dataschema"]["description"]
        self.assertIn(SCHEMA["$id"], description)
        self.assertIn("deprecated", description.lower())

    def test_frozen_ids_are_unchanged(self):
        self.assertEqual(bee_landed.EVENT_TYPE, "rizzstack.bee.landed.v1")
        self.assertEqual(bee_landed.PAYLOAD_SCHEMA, "rizzstack.bee-landed/1")

    def test_chapter_names_the_canonical_value(self):
        chapter = (ROOT / "docs" / "29-bee-landed.md").read_text(encoding="utf-8")
        self.assertIn(SCHEMA["$id"], chapter)
        self.assertIn("rizstack", chapter, "the chapter must name the legacy value so readers can map old events")

    def test_dataschema_is_classified(self):
        self.assertEqual(bee_landed.dataschema_status(SCHEMA["$id"]), "canonical")
        self.assertEqual(bee_landed.dataschema_status(LEGACY), "legacy")
        self.assertEqual(bee_landed.dataschema_status("https://example.invalid/other"), "other")
        self.assertEqual(bee_landed.dataschema_status(None), "absent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
