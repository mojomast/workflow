"""Contract tests for the metrics fact records (METRICS.md).

Five records sit under the per-attempt usage ledger: one per model call
(gen_ai.inference/v1), one per tool call (gen_ai.tool_call/v1), container and
host samples (resource.sample/v1), one per finished task (task.outcome/v1) and
one per CI job (ci.run/v1). They carry counts, timings and bounded labels only:
never prompts, completions, tool arguments or results, paths, URLs or hosts.
"""

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from envelope import record_type  # noqa: E402
from validate import SchemaError, Validator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SCHEMAS = ROOT / "schemas"
CATALOG = ROOT / "METRICS.md"

RECORDS = (
    ("inference-step.json", "inference.schema.json", "gen_ai.inference/v1"),
    ("inference-unknown-usage.json", "inference.schema.json", "gen_ai.inference/v1"),
    ("tool-call.json", "tool-call.schema.json", "gen_ai.tool_call/v1"),
    ("resource-sample-container.json", "resource-sample.schema.json", "resource.sample/v1"),
    ("resource-sample-host.json", "resource-sample.schema.json", "resource.sample/v1"),
    ("task-outcome.json", "task-outcome.schema.json", "task.outcome/v1"),
    ("ci-run.json", "ci-run.schema.json", "ci.run/v1"),
)

FORBIDDEN = ("ts.net", "tailscale", "BEGIN PRIVATE", "api_key", "api-key", ".env", "http://", "https://", "C:\\\\", "/home/")


def _load(name: str) -> dict:
    with (EXAMPLES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


class RecordExamplesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def test_every_metrics_example_validates(self) -> None:
        for example, schema, _ in RECORDS:
            with self.subTest(example=example):
                self.validator.validate_file(_load(example), schema)

    def test_discriminators_follow_the_envelope(self) -> None:
        for example, schema, expected in RECORDS:
            with self.subTest(example=example):
                self.assertEqual(record_type(_load(example)), expected)
                data = json.loads((SCHEMAS / schema).read_text(encoding="utf-8"))
                self.assertEqual(data["properties"]["schema"]["const"], expected)
                self.assertFalse(data.get("additionalProperties", True))

    def test_examples_carry_no_private_material(self) -> None:
        for example, _, _ in RECORDS:
            text = (EXAMPLES / example).read_text(encoding="utf-8")
            for needle in FORBIDDEN:
                with self.subTest(example=example, needle=needle):
                    self.assertNotIn(needle, text)


class InferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)
        self.doc = _load("inference-step.json")

    def _bad(self, doc: dict) -> None:
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "inference.schema.json")

    def test_nous_and_kimi_are_valid_provider_labels(self) -> None:
        for provider in ("nous", "kimi", "opencode", "deepseek", "openrouter"):
            doc = deepcopy(self.doc)
            doc["provider"] = provider
            doc["route"] = provider
            self.validator.validate_file(doc, "inference.schema.json")

    def test_provider_label_refuses_urls_and_upper_case(self) -> None:
        for provider in ("https://api.example", "Nous", "nous portal"):
            doc = deepcopy(self.doc)
            doc["provider"] = provider
            self._bad(doc)

    def test_unknown_usage_is_null_never_zero(self) -> None:
        doc = _load("inference-unknown-usage.json")
        self.assertEqual(doc["usage_status"], "unknown")
        self.assertIsNone(doc["input_tokens"])
        self.assertIsNone(doc["output_tokens"])
        self.validator.validate_file(doc, "inference.schema.json")

    def test_negative_counts_and_timings_are_refused(self) -> None:
        for key in ("input_tokens", "output_tokens", "ttft_s", "duration_s", "output_tps"):
            doc = deepcopy(self.doc)
            doc[key] = -1
            with self.subTest(key=key):
                self._bad(doc)

    def test_content_fields_are_refused(self) -> None:
        for key in ("prompt", "completion", "messages", "text", "tool_arguments"):
            doc = deepcopy(self.doc)
            doc[key] = "anything"
            with self.subTest(key=key):
                self._bad(doc)

    def test_model_id_is_not_a_url(self) -> None:
        doc = deepcopy(self.doc)
        doc["served_model"] = "https://models.example/v1"
        self._bad(doc)

    def test_ttft_source_is_a_closed_set(self) -> None:
        doc = deepcopy(self.doc)
        doc["ttft_source"] = "sdk_span"
        self._bad(doc)


class ToolCallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)
        self.doc = _load("tool-call.json")

    def _bad(self, doc: dict) -> None:
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "tool-call.schema.json")

    def test_mcp_and_other_tool_names_are_valid(self) -> None:
        for name in ("bash", "edit", "mcp:github", "other"):
            doc = deepcopy(self.doc)
            doc["tool_name"] = name
            self.validator.validate_file(doc, "tool-call.schema.json")

    def test_tool_name_refuses_paths_and_free_text(self) -> None:
        for name in ("/usr/bin/git", "Run Tests", "a" * 65):
            doc = deepcopy(self.doc)
            doc["tool_name"] = name
            self._bad(doc)

    def test_arguments_and_results_are_refused(self) -> None:
        for key in ("arguments", "result", "output", "command"):
            doc = deepcopy(self.doc)
            doc[key] = "x"
            with self.subTest(key=key):
                self._bad(doc)

    def test_status_is_a_closed_set(self) -> None:
        doc = deepcopy(self.doc)
        doc["status"] = "timeout"
        self._bad(doc)


class ResourceSampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)

    def _bad(self, doc: dict) -> None:
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "resource-sample.schema.json")

    def test_host_alias_refuses_hostnames_and_addresses(self) -> None:
        for alias in ("moltussy-1.example.net", "100.64.0.1", "PC"):
            doc = _load("resource-sample-host.json")
            doc["host_alias"] = alias
            self._bad(doc)

    def test_oom_flag_is_boolean_or_null(self) -> None:
        doc = _load("resource-sample-container.json")
        doc["oom_killed"] = None
        self.validator.validate_file(doc, "resource-sample.schema.json")
        doc["oom_killed"] = "yes"
        self._bad(doc)

    def test_scope_is_a_closed_set(self) -> None:
        doc = _load("resource-sample-container.json")
        doc["scope"] = "vm"
        self._bad(doc)

    def test_ratios_are_bounded(self) -> None:
        doc = _load("resource-sample-host.json")
        doc["disk_free_ratio"] = 1.5
        self._bad(doc)


class TaskOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)
        self.doc = _load("task-outcome.json")

    def _bad(self, doc: dict) -> None:
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "task-outcome.schema.json")

    def test_phase_keys_are_closed(self) -> None:
        doc = deepcopy(self.doc)
        doc["phases"]["lunch"] = "2026-11-24T12:00:00Z"
        self._bad(doc)

    def test_wasted_token_causes_are_closed(self) -> None:
        doc = deepcopy(self.doc)
        doc["tokens_wasted"]["vibes"] = 10
        self._bad(doc)

    def test_outcome_is_a_closed_set(self) -> None:
        doc = deepcopy(self.doc)
        doc["outcome"] = "done"
        self._bad(doc)

    def test_unknown_phases_may_be_null(self) -> None:
        doc = deepcopy(self.doc)
        for key in doc["phases"]:
            doc["phases"][key] = None
        self.validator.validate_file(doc, "task-outcome.schema.json")


class CiRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Validator(SCHEMAS)
        self.doc = _load("ci-run.json")

    def _bad(self, doc: dict) -> None:
        with self.assertRaises(SchemaError):
            self.validator.validate_file(doc, "ci-run.schema.json")

    def test_repo_is_an_owner_name_slug(self) -> None:
        doc = deepcopy(self.doc)
        doc["repo"] = "https://github.com/mojomast/workflow"
        self._bad(doc)

    def test_sha_is_hex(self) -> None:
        doc = deepcopy(self.doc)
        doc["sha"] = "main"
        self._bad(doc)

    def test_conclusion_is_a_closed_set(self) -> None:
        doc = deepcopy(self.doc)
        doc["conclusion"] = "green"
        self._bad(doc)


class CatalogTests(unittest.TestCase):
    def test_catalog_names_every_record_and_section(self) -> None:
        text = CATALOG.read_text(encoding="utf-8")
        for _, _, record in RECORDS:
            self.assertIn(record, text)
        for heading in ("## Label allowlist", "## Histogram buckets", "## Retention", "## SLOs", "## Metric catalog", "## Privacy"):
            self.assertIn(heading, text)

    def test_catalog_uses_genai_names_where_they_exist(self) -> None:
        text = CATALOG.read_text(encoding="utf-8")
        for name in (
            "gen_ai.client.inference.duration",
            "gen_ai.client.inference.time_to_first_chunk",
            "gen_ai.client.inference.usage.input_tokens",
            "gen_ai.execute_tool.duration",
            "gen_ai.invoke_agent.tool_calls",
        ):
            self.assertIn(name, text)

    def test_catalog_carries_no_private_material(self) -> None:
        text = CATALOG.read_text(encoding="utf-8")
        for needle in ("ts.net", "tailscale", "BEGIN PRIVATE", "api_key=", "100.64."):
            self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
