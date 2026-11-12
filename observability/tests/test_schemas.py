"""Validation tests for the observability record contracts."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate import SchemaError, Validator

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SCHEMAS = ROOT / "schemas"

EXAMPLES_AND_SCHEMAS = (
    ("lifecycle-bee-running.json", "lifecycle.schema.json"),
    ("lifecycle-fallback.json", "lifecycle.schema.json"),
    ("failure-rate-limit.json", "failure.schema.json"),
    ("failure-environmental.json", "failure.schema.json"),
    ("vcs-snapshot.json", "vcs-snapshot.schema.json"),
    ("board-snapshot.json", "board-snapshot.schema.json"),
    ("resource-snapshot.json", "resource-snapshot.schema.json"),
)

FORBIDDEN = (
    "ts.net",
    "tailscale",
    "BEGIN PRIVATE",
    "api_key=",
    "api-key=",
    ".env",
)


def _load_example(name: str) -> dict:
    with (EXAMPLES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


class ExamplesValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_every_example_matches_its_schema(self) -> None:
        for example, schema in EXAMPLES_AND_SCHEMAS:
            with self.subTest(example=example):
                self.validator.validate_file(_load_example(example), schema)

    def test_schema_files_are_json_objects(self) -> None:
        names = sorted(path.name for path in SCHEMAS.glob("*.schema.json"))
        self.assertEqual(
            names,
            [
                "board-snapshot.schema.json",
                "common.schema.json",
                "failure.schema.json",
                "lifecycle.schema.json",
                "resource-snapshot.schema.json",
                "vcs-snapshot.schema.json",
            ],
        )
        for name in names:
            with (SCHEMAS / name).open(encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertIsInstance(data, dict)
            self.assertTrue(data["$id"].startswith(
                "https://github.com/mojomast/workflow/observability/schemas/"
            ))

    def test_this_package_does_not_define_a_usage_schema(self) -> None:
        for path in SCHEMAS.glob("*.json"):
            self.assertNotIn("usage", path.name.lower())
            data = json.loads(path.read_text(encoding="utf-8"))
            rec = data.get("properties", {}).get("record_type", {})
            const = str(rec.get("const") or "")
            self.assertNotIn("usage", const.lower())
            for item in rec.get("enum") or []:
                self.assertNotIn("usage", str(item).lower())
            schema_ver = data.get("properties", {}).get("schema_version", {})
            self.assertNotEqual(schema_ver.get("const"), "bee.usage/v1")
            self.assertNotIn("bee.usage/v1", [schema_ver.get("const")] + list(schema_ver.get("enum") or []))


class JoinKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_lifecycle_accepts_the_five_join_keys(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        for key in ("attempt_id", "card_id", "run_id", "project", "role"):
            self.assertIn(key, doc)
            self.assertIsInstance(doc[key], str)
        self.assertEqual(doc["role"], "work")
        self.validator.validate_file(doc, "lifecycle.schema.json")

    def test_snapshots_may_leave_join_keys_null(self) -> None:
        doc = _load_example("vcs-snapshot.json")
        for key in ("attempt_id", "card_id", "run_id", "project", "role"):
            self.assertIsNone(doc[key])
        self.validator.validate_file(doc, "vcs-snapshot.schema.json")

    def test_unknown_role_is_rejected(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        doc["role"] = "worker"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "lifecycle.schema.json")


class FailureClassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_rate_limit_fallback_is_not_a_regression(self) -> None:
        doc = _load_example("failure-rate-limit.json")
        self.assertEqual(doc["class"], "rate-limit")
        self.assertEqual(doc["fallback_to"], "deepseek")
        self.assertTrue(doc["http_429"])
        self.validator.validate_file(doc, "failure.schema.json")

    def test_environmental_class_is_distinct_from_regression(self) -> None:
        doc = _load_example("failure-environmental.json")
        self.assertEqual(doc["class"], "environmental")
        self.assertNotEqual(doc["class"], "regression")
        self.validator.validate_file(doc, "failure.schema.json")

    def test_invented_failure_class_is_rejected(self) -> None:
        doc = _load_example("failure-environmental.json")
        doc["class"] = "timeout"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "failure.schema.json")


class ResourceUnknownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)
        self.doc = _load_example("resource-snapshot.json")

    def test_unavailable_row_uses_null_not_zero(self) -> None:
        go2 = next(row for row in self.doc["resources"] if row.get("resource_id") == "go-2")
        self.assertEqual(go2["status"], "unavailable")
        self.assertIsNone(go2["value"])
        self.assertIsNone(go2["remaining"])
        self.validator.validate_file(self.doc, "resource-snapshot.schema.json")

    def test_genuine_zero_is_allowed_when_status_is_ok(self) -> None:
        cloud = next(row for row in self.doc["resources"] if row["kind"] == "cursor_cloud_agents")
        self.assertEqual(cloud["status"], "ok")
        self.assertEqual(cloud["value"], 0)
        self.validator.validate_file(self.doc, "resource-snapshot.schema.json")

    def test_unavailable_with_zero_value_is_rejected(self) -> None:
        doc = deepcopy(self.doc)
        for row in doc["resources"]:
            if row.get("resource_id") == "go-2":
                row["value"] = 0
                row["remaining"] = 0
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "resource-snapshot.schema.json")

    def test_both_go_keys_are_distinct_labeled_rows(self) -> None:
        go_rows = [row for row in self.doc["resources"] if row["kind"] == "go_allowance"]
        self.assertEqual({row["resource_id"] for row in go_rows}, {"go-1", "go-2"})
        for row in go_rows:
            self.assertNotIn("sk-", str(row))
            self.assertNotIn("key", (row.get("resource_id") or ""))

    def test_shared_bee_cap_is_twelve_in_the_example(self) -> None:
        self.assertEqual(self.doc["bee_cap"], 12)
        bees = next(row for row in self.doc["resources"] if row["kind"] == "bees_in_flight")
        self.assertEqual(bees["cap"], 12)

    def test_unexpected_property_is_rejected(self) -> None:
        doc = deepcopy(self.doc)
        doc["token"] = "should-not-be-here"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "resource-snapshot.schema.json")


class LifecycleRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_go_and_deepseek_routes_are_accepted(self) -> None:
        running = _load_example("lifecycle-bee-running.json")
        fallback = _load_example("lifecycle-fallback.json")
        self.assertEqual(running["route"], "go")
        self.assertFalse(running["fallen_back"])
        self.assertEqual(fallback["route"], "deepseek")
        self.assertTrue(fallback["fallen_back"])
        self.validator.validate_file(running, "lifecycle.schema.json")
        self.validator.validate_file(fallback, "lifecycle.schema.json")

    def test_unknown_route_is_rejected(self) -> None:
        doc = _load_example("lifecycle-bee-running.json")
        doc["route"] = "openrouter"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "lifecycle.schema.json")


class PrivacyTests(unittest.TestCase):
    def test_examples_and_schemas_have_no_host_or_secret_markers(self) -> None:
        allowed_urls = (
            "https://json-schema.org",
            "https://github.com/mojomast/workflow/observability/schemas/",
        )
        for folder in (EXAMPLES, SCHEMAS):
            for path in folder.glob("*"):
                if not path.is_file():
                    continue
                raw = path.read_text(encoding="utf-8")
                lowered = raw.lower()
                for token in FORBIDDEN:
                    self.assertNotIn(token.lower(), lowered, f"{path.name} contains {token!r}")
                remainder = raw
                for url in allowed_urls:
                    remainder = remainder.replace(url, "")
                self.assertNotIn("://", remainder, f"{path.name} has an unexpected URL")
                self.assertNotRegex(raw, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


class BoardAndVcsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_board_without_blockers_uses_null_age(self) -> None:
        doc = _load_example("board-snapshot.json")
        doc["open_blocker_count"] = 0
        doc["oldest_blocker_age_s"] = None
        self.validator.validate_file(doc, "board-snapshot.schema.json")

    def test_vcs_rejects_a_clone_url(self) -> None:
        doc = _load_example("vcs-snapshot.json")
        doc["repos"][0]["repo"] = "https://github.com/mojomast/workflow"
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "vcs-snapshot.schema.json")

    def test_missing_required_field_is_rejected(self) -> None:
        doc = _load_example("board-snapshot.json")
        del doc["group"]
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "board-snapshot.schema.json")


if __name__ == "__main__":
    unittest.main()
