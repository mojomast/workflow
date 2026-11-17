"""R01 contract-freeze tests for schemas/rails (spec: specs/rizzstack-rails-spec.md).

RED-first acceptance per spec section 9, row R01:
- bad hashes fail, duplicate keys fail, wrong-kind payloads fail,
  PASS without evidence fails, the legacy vector matches upstream,
  the freeze digest is recorded.

Everything here is standard-library-only. The optional ``jsonschema`` package is
used only to cross-check the in-test subset validator when it is installed.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAILS = ROOT / "schemas" / "rails"
FIXTURES = RAILS / "fixtures"

try:  # jsonschema is optional; the semantic checks never depend on it.
    import jsonschema  # noqa: F401
except ImportError:  # pragma: no cover - exercised on minimal installs
    jsonschema = None

SCHEMA_TAG = "rizzstack.rails/1"
CANONICAL_PREFIX = b"rizzstack.rails/1\n"
INT64_MAX = 9007199254740991  # 2**53 - 1

CORE_KINDS = [
    "lane.open",
    "lane.spawn",
    "lane.close",
    "tool.start",
    "tool.finish",
    "decision.recorded",
    "attempt.state",
    "job.state",
    "queue.transition",
    "lease.recorded",
    "verification.result",
    "review.result",
    "integration.result",
    "merge.result",
    "acceptance.result",
    "usage.observed",
    "feedback.recorded",
    "intervention.requested",
    "intervention.result",
    "history.superseded",
    "source.gap",
    "source.checkpoint",
    "source.error",
]

CONTRACT_FILES = [
    "event.schema.json",
    "source.schema.json",
    "query.schema.json",
    "view.schema.json",
    "http.schema.json",
    "payload.schema.json",
    "evidence.schema.json",
]


# --------------------------------------------------------------------------
# Canonical bytes and hashing (spec section 4: canonical bytes, tamper evidence)
# --------------------------------------------------------------------------


def _reject_constant(name: str):
    raise ValueError("non-finite JSON constant rejected: %s" % name)


def _no_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError("duplicate JSON object key: %r" % key)
        seen.add(key)
    return dict(pairs)


def loads_strict(text: str):
    """Parse JSON refusing duplicate keys and NaN/Infinity literals."""
    return json.loads(
        text,
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_constant,
    )


def _check_canonical_value(value, path: str) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, float):
        raise ValueError("float value not allowed in canonical envelope at %s" % path)
    if isinstance(value, int):
        if not (-(INT64_MAX) <= value <= INT64_MAX):
            raise ValueError("integer outside +/-2**53-1 at %s" % path)
        return
    if isinstance(value, str):
        for char in value:
            code = ord(char)
            if 0xD800 <= code <= 0xDFFF:
                raise ValueError("lone surrogate at %s" % path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_canonical_value(item, "%s[%d]" % (path, index))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("non-string object key at %s" % path)
            _check_canonical_value(item, "%s.%s" % (path, key))
        return
    raise ValueError("unsupported canonical value at %s: %r" % (path, value))


def canonical(value):
    """Rails canonicalization C(x) from spec section 4.

    C(x) = json.dumps(x, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
    with the envelope value domain enforced first.
    """
    _check_canonical_value(value, "$")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def rails_hash(prev_hash: str, envelope_without_hash: dict) -> str:
    """Rails origin hash: SHA256(prefix + prev + '\\n' + C(envelope without hash))."""
    preimage = (
        CANONICAL_PREFIX
        + prev_hash.encode("ascii")
        + b"\n"
        + canonical(envelope_without_hash)
    )
    return hashlib.sha256(preimage).hexdigest()


def legacy_hash(prev: str, row: dict, chain_keys) -> str:
    """Upstream vibeline compatibility hash, exactly as the pinned ledger.py computes it.

    SHA256(prev.encode() + json.dumps({k: row.get(k) for k in chain_keys},
    sort_keys=True, default=str).encode()) with json.dumps defaults
    (separators (', ', ': '), ensure_ascii=True).
    """
    projection = {key: row.get(key) for key in chain_keys}
    encoded = json.dumps(projection, sort_keys=True, default=str).encode()
    return hashlib.sha256(prev.encode() + encoded).hexdigest()


# --------------------------------------------------------------------------
# Minimal JSON Schema subset validator (draft 2020-12 features actually used)
# --------------------------------------------------------------------------


def _type_ok(instance, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "null":
        return instance is None
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    raise ValueError("unsupported type keyword: %s" % expected)


def validate_schema(instance, schema, path="$"):
    """Validate against the JSON Schema subset the rails schemas are limited to."""
    errors = []

    def fail(message: str) -> None:
        errors.append("%s: %s" % (path, message))

    if schema is True:
        return errors
    if schema is False:
        fail("schema forbids this value")
        return errors

    if "type" in schema:
        expected = schema["type"]
        ok = [_type_ok(instance, one) for one in ([expected] if isinstance(expected, str) else expected)]
        if not any(ok):
            fail("expected type %s" % expected)
            return errors

    if "const" in schema and instance != schema["const"]:
        fail("expected const %r" % (schema["const"],))

    if "enum" in schema:
        matched = False
        for option in schema["enum"]:
            if isinstance(instance, bool) == isinstance(option, bool) and instance == option:
                matched = True
        if not matched:
            fail("value not in enum")

    if isinstance(instance, str):
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            fail("pattern mismatch")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            fail("shorter than minLength")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            fail("longer than maxLength")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            fail("below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            fail("above maximum")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            fail("fewer than minItems")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            fail("more than maxItems")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(instance):
                errors.extend(validate_schema(item, item_schema, "%s[%d]" % (path, index)))

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                fail("missing required property %r" % key)
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate_schema(value, properties[key], "%s.%s" % (path, key)))
            else:
                additional = schema.get("additionalProperties", True)
                if additional is False:
                    fail("unexpected property %r" % key)
                elif additional is not True and isinstance(additional, dict):
                    errors.extend(validate_schema(value, additional, "%s.%s" % (path, key)))

    if "anyOf" in schema:
        options = []
        for index, option in enumerate(schema["anyOf"]):
            option_errors = validate_schema(instance, option, path)
            if not option_errors:
                matched = True
                break
            options.append(option_errors)
        else:
            fail("no anyOf branch matched (%d alternatives)" % len(options))

    for branch in schema.get("allOf", []):
        errors.extend(validate_schema(instance, branch, path))

    if "if" in schema:
        condition_errors = validate_schema(instance, schema["if"], path)
        branch = None
        if not condition_errors:
            branch = schema.get("then")
        else:
            branch = schema.get("else")
        if branch is not None:
            errors.extend(validate_schema(instance, branch, path))

    return errors


def load_json(path: Path):
    """Load a contract artifact with duplicate-key and NaN rejection."""
    return loads_strict(path.read_text(encoding="utf-8"))


def make_envelope(**overrides):
    """Synthetic valid tool.finish envelope (payload filled by caller)."""
    envelope = {
        "schema": SCHEMA_TAG,
        "chain_id": "worker-1.ledger-vector",
        "seq": 1,
        "event_id": "worker-1.ledger-vector:1",
        "dedupe_key": "vector.case",
        "source": {
            "adapter": "launcher-log",
            "instance": "worker-1",
            "record_id": "vector.case.1",
            "revision": "r1",
        },
        "scope": {
            "repo": "mojomast/hyvv",
            "campaign_id": "campaign-vector",
            "job_id": "job-vector",
            "task_id": "task-vector",
            "attempt_id": "att-vector",
            "session_id": None,
            "action_id": None,
            "contract_sha256": None,
            "code_rev": "a" * 40,
        },
        "lane_id": "worker-1.att-vector",
        "parent_lane_id": "coordinator-1.job-vector",
        "parent_event_id": None,
        "kind": "tool.finish",
        "occurred_at": "2026-11-16T12:00:00.000000Z",
        "recorded_at": "2026-11-16T12:00:01.000000Z",
        "duration_ms": 2100,
        "timing_quality": "measured",
        "authority": "worker_report",
        "payload": {
            "call_id": "call-1",
            "tool_name": "terminal",
            "command_family": "pytest",
            "outcome": "ok",
            "summary": "Named test command completed",
            "evidence_ref": "artifact-vector-1",
        },
        "redaction_policy": "rails-safe/1",
        "prev_hash": "genesis",
    }
    envelope.update(overrides)
    return envelope


def strip_hash(envelope: dict) -> dict:
    return {key: value for key, value in envelope.items() if key != "hash"}


# --------------------------------------------------------------------------
# Test cases
# --------------------------------------------------------------------------


class TestContractArtifactsExist(unittest.TestCase):
    """Every R01 leased artifact exists, parses strictly and is closed."""

    def test_all_leased_schema_files_exist_and_parse(self):
        for name in CONTRACT_FILES:
            with self.subTest(file=name):
                data = load_json(RAILS / name)
                self.assertIsInstance(data, dict)
                self.assertIn("$schema", data)
                self.assertIn("$id", data)
                self.assertIn("title", data)
                self.assertEqual(data.get("additionalProperties"), False)

    def test_examples_parse_and_reference_freeze_ids(self):
        examples = load_json(RAILS / "examples.json")
        self.assertIsInstance(examples, list)
        self.assertGreaterEqual(len(examples), 3)
        kinds = {example["kind"] for example in examples}
        self.assertIn("tool.finish", kinds)
        self.assertIn("verification.result", kinds)
        self.assertIn("feedback.recorded", kinds)
        for example in examples:
            self.assertEqual(example["schema"], SCHEMA_TAG)

    def test_hash_vectors_fixture_exists(self):
        vectors = load_json(FIXTURES / "hash-vectors.json")
        for section in ("provenance", "canonical", "origin_chain", "negative", "legacy"):
            self.assertIn(section, vectors)


class TestCanonicalization(unittest.TestCase):
    """C(x) determinism, ordering, escaping and value-domain rejection."""

    def test_deterministic_and_compact(self):
        value = {"b": 1, "a": [True, None, "x"]}
        self.assertEqual(canonical(value), b'{"a":[true,null,"x"],"b":1}')
        self.assertEqual(canonical(value), canonical({"a": [True, None, "x"], "b": 1}))

    def test_reorder_invariance(self):
        one = {"k1": "v", "k2": {"y": 2, "x": 1}}
        two = {"k2": {"x": 1, "y": 2}, "k1": "v"}
        self.assertEqual(canonical(one), canonical(two))

    def test_unicode_is_escaped_ascii(self):
        data = canonical({"k": "café ☂"})
        self.assertTrue(data.isascii())
        self.assertEqual(data, '{"k":"caf\\u00e9 \\u2602"}'.encode("ascii"))

    def test_floats_rejected(self):
        with self.assertRaises(ValueError):
            canonical({"x": 1.5})
        with self.assertRaises(ValueError):
            canonical({"x": 2.0})

    def test_integer_boundary(self):
        self.assertEqual(canonical({"n": INT64_MAX}), b'{"n":9007199254740991}')
        self.assertEqual(canonical({"n": -INT64_MAX}), b'{"n":-9007199254740991}')
        with self.assertRaises(ValueError):
            canonical({"n": INT64_MAX + 1})
        with self.assertRaises(ValueError):
            canonical({"n": -(INT64_MAX + 1)})

    def test_lone_surrogate_rejected(self):
        with self.assertRaises(ValueError):
            canonical({"x": "bad \ud800 pair"})

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            canonical({"x": float("nan")})

    def test_strict_loader_rejects_duplicates_and_constants(self):
        with self.assertRaises(ValueError):
            loads_strict('{"a": 1, "a": 2}')
        with self.assertRaises(ValueError):
            loads_strict('{"a": 1, "b": {"c": true, "c": false}}')
        with self.assertRaises(ValueError):
            loads_strict('{"a": NaN}')


class TestOriginHashVectors(unittest.TestCase):
    """Positive and negative origin-chain vectors from the fixture."""

    @classmethod
    def setUpClass(cls):
        cls.vectors = load_json(FIXTURES / "hash-vectors.json")

    def test_canonical_vectors_reproduce(self):
        for case in self.vectors["canonical"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(canonical(case["input"]), case["expected"].encode("ascii"))

    def test_positive_origin_chain_reproduces(self):
        chain = self.vectors["origin_chain"]
        envelopes = chain["envelopes"]
        expected = chain["expected_hashes"]
        self.assertEqual(len(envelopes), len(expected))
        self.assertEqual(envelopes[0]["prev_hash"], "genesis")
        for index, envelope in enumerate(envelopes):
            with self.subTest(seq=envelope["seq"]):
                self.assertEqual(
                    rails_hash(envelope["prev_hash"], strip_hash(envelope)),
                    expected[index],
                )
            if index > 0:
                self.assertEqual(envelope["prev_hash"], expected[index - 1])
                self.assertEqual(envelope["seq"], envelopes[index - 1]["seq"] + 1)

    def test_negative_vectors_do_not_match(self):
        for case in self.vectors["negative"]:
            with self.subTest(case=case["name"]):
                computed = rails_hash(case["prev_hash"], case["envelope"])
                self.assertNotEqual(computed, case["claimed_hash"])

    def test_unexpected_field_changes_hash(self):
        base = strip_hash(make_envelope())
        base_hash = rails_hash(base["prev_hash"], base)
        extended = dict(base)
        extended["unexpected_field"] = "added"
        self.assertNotEqual(rails_hash(base["prev_hash"], extended), base_hash)


class TestLegacyVectorMatchesUpstream(unittest.TestCase):
    """Compatibility hash must match the pinned upstream ledger.py algorithm."""

    @classmethod
    def setUpClass(cls):
        cls.vectors = load_json(FIXTURES / "hash-vectors.json")

    def test_legacy_section_pins_upstream_revision(self):
        legacy = self.vectors["legacy"]
        self.assertIn("d5d0f425a64906ae1a50c1222314a5420da404d5", legacy["source_pin"])
        self.assertIn("ledger.py", legacy["source_file"])

    def test_chain_keys_match_upstream_chain_keys(self):
        # Exact upstream _CHAIN_KEYS tuple from vibeline ledger.py at the pinned
        # revision (includes sha and prev_hash in the hashed projection; id and
        # hash are not part of it). Order matters because the projection dict is
        # sorted anyway, but the key SET must match exactly.
        legacy = self.vectors["legacy"]
        expected_columns = [
            "ts",
            "task_id",
            "actor",
            "parent",
            "kind",
            "ac_id",
            "result",
            "why",
            "tokens_in",
            "tokens_out",
            "sha",
            "prev_hash",
        ]
        self.assertEqual(legacy["chain_keys"], expected_columns)

    def test_legacy_rows_reproduce_upstream_hashes(self):
        legacy = self.vectors["legacy"]
        self.assertGreaterEqual(len(legacy["rows"]), 2)
        prev = "genesis"
        for row_case in legacy["rows"]:
            with self.subTest(row=row_case["row"].get("id")):
                self.assertEqual(row_case["prev"], prev)
                self.assertEqual(
                    legacy_hash(row_case["prev"], row_case["row"], legacy["chain_keys"]),
                    row_case["expected"],
                )
                prev = row_case["expected"]

    def test_legacy_vector_chain_is_tamper_evident(self):
        legacy = self.vectors["legacy"]
        rows = legacy["rows"]
        tampered = json.loads(json.dumps(rows[0]["row"]))
        tampered["result"] = tampered["result"] + "x"
        self.assertNotEqual(
            legacy_hash(rows[0]["prev"], tampered, legacy["chain_keys"]),
            rows[0]["expected"],
        )


class TestChainIntegrity(unittest.TestCase):
    """Bad hashes, bad linkage and non-contiguous sequences are refused."""

    def verify_chain(self, envelopes):
        errors = []
        prev = "genesis"
        expected_seq = 1
        for envelope in envelopes:
            if envelope["seq"] != expected_seq:
                errors.append("seq %d is not contiguous" % envelope["seq"])
            if envelope["event_id"] != "%s:%d" % (envelope["chain_id"], envelope["seq"]):
                errors.append("event_id does not match chain_id:seq")
            if envelope["prev_hash"] != prev:
                errors.append("prev_hash mismatch at seq %d" % envelope["seq"])
            computed = rails_hash(envelope["prev_hash"], strip_hash(envelope))
            if computed != envelope.get("hash"):
                errors.append("hash does not recompute at seq %d" % envelope["seq"])
            prev = envelope["hash"]
            expected_seq += 1
        return errors

    def build_chain(self):
        first = make_envelope()
        first["hash"] = rails_hash(first["prev_hash"], strip_hash(first))
        second = make_envelope(
            seq=2,
            event_id="worker-1.ledger-vector:2",
            dedupe_key="vector.case.2",
            kind="tool.start",
            payload={
                "call_id": "call-2",
                "tool_name": "terminal",
                "command_family": "pytest",
                "outcome": "pending",
                "summary": "Named test command started",
                "evidence_ref": None,
            },
        )
        second["prev_hash"] = first["hash"]
        second["hash"] = rails_hash(second["prev_hash"], strip_hash(second))
        return [first, second]

    def test_valid_chain_verifies(self):
        self.assertEqual(self.verify_chain(self.build_chain()), [])

    def test_tampered_hash_fails(self):
        chain = self.build_chain()
        chain[1]["hash"] = chain[1]["hash"][:-2] + ("00" if not chain[1]["hash"].endswith("00") else "11")
        errors = self.verify_chain(chain)
        self.assertTrue(any("hash does not recompute" in e for e in errors))

    def test_tampered_payload_byte_fails(self):
        chain = self.build_chain()
        chain[0]["payload"]["summary"] = chain[0]["payload"]["summary"] + "!"
        errors = self.verify_chain(chain)
        self.assertTrue(any("hash does not recompute" in e for e in errors))

    def test_wrong_prev_hash_fails(self):
        chain = self.build_chain()
        chain[1]["prev_hash"] = "0" * 64
        errors = self.verify_chain(chain)
        self.assertTrue(any("prev_hash mismatch" in e for e in errors))

    def test_non_contiguous_seq_fails(self):
        chain = self.build_chain()
        chain[1]["seq"] = 3
        chain[1]["event_id"] = "worker-1.ledger-vector:3"
        errors = self.verify_chain(chain)
        self.assertTrue(any("not contiguous" in e for e in errors))

    def test_event_id_mismatch_fails(self):
        chain = self.build_chain()
        chain[0]["event_id"] = "worker-1.ledger-vector:9"
        errors = self.verify_chain(chain)
        self.assertTrue(any("event_id does not match" in e for e in errors))

    def test_examples_hash_correctly(self):
        examples = load_json(RAILS / "examples.json")
        by_chain = {}
        for example in examples:
            by_chain.setdefault(example["chain_id"], []).append(example)
        for chain_id, events in by_chain.items():
            events.sort(key=lambda item: item["seq"])
            prev = "genesis"
            for event in events:
                with self.subTest(chain=chain_id, seq=event["seq"]):
                    self.assertEqual(event["prev_hash"], prev)
                    self.assertEqual(
                        rails_hash(event["prev_hash"], strip_hash(event)),
                        event["hash"],
                    )
                    prev = event["hash"]


class TestKindPayloadSchemasClosed(unittest.TestCase):
    """payload.schema.json closes every core kind; wrong-kind payloads fail."""

    @classmethod
    def setUpClass(cls):
        cls.payload_schema = load_json(RAILS / "payload.schema.json")
        cls.event_schema = load_json(RAILS / "event.schema.json")

    def test_payload_schema_declares_freeze_id(self):
        self.assertEqual(self.payload_schema["properties"]["schema"]["const"], "rizzstack.rails-payload/1")

    def test_every_core_kind_has_closed_schema(self):
        kinds = self.payload_schema["properties"]["kinds"]
        self.assertEqual(set(kinds["required"]), set(CORE_KINDS))
        self.assertEqual(kinds.get("additionalProperties"), False)
        for kind in CORE_KINDS:
            fragment = kinds["properties"][kind]
            with self.subTest(kind=kind):
                self.assertEqual(fragment.get("type"), "object")
                self.assertEqual(fragment.get("additionalProperties"), False)

    def test_kind_enum_matches_event_schema(self):
        declared = self.event_schema["properties"]["kind"]["enum"]
        self.assertEqual(set(declared), set(CORE_KINDS))

    def payload_errors(self, kind, payload):
        fragment = self.payload_schema["properties"]["kinds"]["properties"][kind]
        return validate_schema(payload, fragment)

    def test_valid_payloads_pass(self):
        valid = {
            "tool.start": {
                "call_id": "c1",
                "tool_name": "terminal",
                "command_family": "pytest",
                "outcome": "pending",
                "summary": "started",
                "evidence_ref": None,
            },
            "tool.finish": {
                "call_id": "c1",
                "tool_name": "terminal",
                "command_family": "pytest",
                "outcome": "ok",
                "summary": "done",
                "evidence_ref": "a1",
            },
            "verification.result": {
                "ac_id": "AC-1",
                "contract_sha256": "b" * 64,
                "code_rev": "a" * 40,
                "run_id": "r1",
                "phase": "green",
                "verdict": "PASS",
                "evidence_refs": ["e1"],
                "reason": "",
            },
            "review.result": {
                "review_id": "rev1",
                "reviewer": "reviewer-1",
                "author": "worker-1",
                "reviewed_head": "a" * 40,
                "review_verdict": "approve",
                "independent": True,
                "basis": "ran the suite on a separate checkout",
            },
            "queue.transition": {
                "from_state": "queued",
                "to_state": "running",
                "operation_id": "op-1",
                "fencing_epoch": 3,
                "code": "queue_ok",
                "evidence_ref": "q-ev-1",
            },
            "lease.recorded": {
                "from_state": None,
                "to_state": "leased",
                "operation_id": "op-2",
                "fencing_epoch": 4,
                "code": "lease_ok",
                "evidence_ref": None,
            },
            "attempt.state": {
                "from_state": None,
                "to_state": "succeeded",
                "operation_id": "op-3",
                "fencing_epoch": 0,
                "code": "attempt_state",
                "evidence_ref": None,
            },
            "job.state": {
                "from_state": "running",
                "to_state": "done",
                "operation_id": "op-4",
                "fencing_epoch": 0,
                "code": "job_state",
                "evidence_ref": None,
            },
            "usage.observed": {
                "usage_record_id": "u1",
                "metric_scope": "att-vector",
                "input_tokens": 10,
                "output_tokens": 20,
                "thinking_tokens": None,
                "usage_basis": "delta",
                "provider": "provider-x",
                "model": "model-x",
            },
            "feedback.recorded": {
                "target_event_id": "worker-1.ledger-vector:1",
                "rating": -1,
                "note": "repeated command",
                "category": "both",
                "actor": "owner-1",
                "supersedes_event_id": None,
            },
            "intervention.requested": {
                "request_id": "req-1",
                "target_event_id": "worker-1.ledger-vector:1",
                "operation": "retry",
                "queue_action_id": None,
                "decision": "pending",
                "reason": "stuck lane",
                "authority_ref": None,
            },
            "intervention.result": {
                "request_id": "req-1",
                "target_event_id": "worker-1.ledger-vector:1",
                "operation": "retry",
                "queue_action_id": "qa-1",
                "decision": "completed",
                "reason": "queue accepted",
                "authority_ref": "auth-ref-1",
            },
            "history.superseded": {
                "old_event_ids": ["worker-1.ledger-vector:1"],
                "replacement_event_id": "worker-1.ledger-vector:5",
                "replacement_lane_id": "worker-1.att-vector-2",
                "operation_id": "op-5",
            },
            "source.gap": {
                "source_id": "launcher-log:worker-1",
                "cursor": None,
                "range_start": 10,
                "range_end": 12,
                "code": "gap_detected",
                "count": 2,
                "digest": None,
            },
            "source.checkpoint": {
                "source_id": "launcher-log:worker-1",
                "cursor": "cursor-0007",
                "range_start": 0,
                "range_end": 6,
                "code": "import_ok",
                "count": 7,
                "digest": "c" * 64,
            },
            "source.error": {
                "source_id": "hermes-session:coordinator-1",
                "cursor": None,
                "range_start": None,
                "range_end": None,
                "code": "unsupported_source_version",
                "count": 0,
                "digest": None,
            },
            "lane.open": {"status": "open"},
            "lane.close": {"status": "closed"},
            "lane.spawn": {"child_lane_id": "worker-1.att-vector.child"},
            "decision.recorded": {"summary": "chose option A for reason R"},
            "integration.result": {"status": "integrated", "summary": "merged"},
            "merge.result": {"status": "merged", "summary": "merge complete"},
        }
        for kind, payload in valid.items():
            with self.subTest(kind=kind):
                self.assertEqual(self.payload_errors(kind, payload), [])

    def test_wrong_kind_payload_fails(self):
        tool_payload = {
            "call_id": "c1",
            "tool_name": "terminal",
            "command_family": "pytest",
            "outcome": "ok",
            "summary": "done",
            "evidence_ref": "a1",
        }
        self.assertTrue(self.payload_errors("verification.result", tool_payload))
        self.assertTrue(self.payload_errors("tool.finish", {"ac_id": "AC-1", "verdict": "PASS"}))
        self.assertTrue(self.payload_errors("feedback.recorded", tool_payload))

    def test_unknown_payload_field_fails(self):
        payload = {
            "call_id": "c1",
            "tool_name": "terminal",
            "command_family": "pytest",
            "outcome": "ok",
            "summary": "done",
            "evidence_ref": None,
            "raw_command_line": "should never be stored",
        }
        self.assertTrue(self.payload_errors("tool.finish", payload))

    def test_tool_start_outcome_is_pending_and_finish_is_not(self):
        start = {
            "call_id": "c1",
            "tool_name": "terminal",
            "command_family": "pytest",
            "outcome": "pending",
            "summary": "started",
            "evidence_ref": None,
        }
        self.assertEqual(self.payload_errors("tool.start", start), [])
        finish_pending = dict(start)
        self.assertTrue(self.payload_errors("tool.finish", finish_pending))

    def test_pass_requires_nonempty_evidence(self):
        verdict_payload = {
            "ac_id": "AC-1",
            "contract_sha256": "b" * 64,
            "code_rev": "a" * 40,
            "run_id": "r1",
            "phase": "green",
            "verdict": "PASS",
            "evidence_refs": [],
            "reason": "",
        }
        self.assertTrue(self.payload_errors("verification.result", verdict_payload))
        missing = {key: value for key, value in verdict_payload.items() if key != "evidence_refs"}
        self.assertTrue(self.payload_errors("verification.result", missing))

    def test_non_pass_requires_reason(self):
        fail_payload = {
            "ac_id": "AC-1",
            "contract_sha256": "b" * 64,
            "code_rev": "a" * 40,
            "run_id": "r1",
            "phase": "red",
            "verdict": "FAIL",
            "evidence_refs": [],
            "reason": "",
        }
        self.assertTrue(self.payload_errors("verification.result", fail_payload))
        fail_payload["reason"] = "two checks did not pass"
        self.assertEqual(self.payload_errors("verification.result", fail_payload), [])

    def test_expected_red_requires_frozen_test_intent(self):
        red_payload = {
            "ac_id": "AC-1",
            "contract_sha256": "b" * 64,
            "code_rev": "a" * 40,
            "run_id": "r1",
            "phase": "red",
            "verdict": "EXPECTED_RED",
            "evidence_refs": [],
            "reason": "deliberate first failure",
        }
        self.assertTrue(self.payload_errors("verification.result", red_payload))
        red_payload["expected_intent_ref"] = "intent-1"
        self.assertEqual(self.payload_errors("verification.result", red_payload), [])

    def test_review_independent_requires_basis(self):
        review = {
            "review_id": "rev1",
            "reviewer": "reviewer-1",
            "author": "worker-1",
            "reviewed_head": "a" * 40,
            "review_verdict": "approve",
            "independent": True,
            "basis": "",
        }
        self.assertTrue(self.payload_errors("review.result", review))
        review["basis"] = "separate execution of the suite"
        self.assertEqual(self.payload_errors("review.result", review), [])

    def test_examples_validate_against_kind_payloads(self):
        examples = load_json(RAILS / "examples.json")
        for example in examples:
            with self.subTest(kind=example["kind"]):
                self.assertEqual(self.payload_errors(example["kind"], example["payload"]), [])


class TestEventEnvelopeContract(unittest.TestCase):
    """The envelope schema accepts well-formed events and rejects violations."""

    @classmethod
    def setUpClass(cls):
        cls.event_schema = load_json(RAILS / "event.schema.json")

    def validate_event(self, envelope):
        return validate_schema(envelope, self.event_schema)

    def test_valid_event_passes(self):
        envelope = make_envelope()
        envelope["hash"] = rails_hash(envelope["prev_hash"], strip_hash(envelope))
        self.assertEqual(self.validate_event(envelope), [])

    def test_pass_without_evidence_fails_at_envelope_level(self):
        envelope = make_envelope(
            kind="verification.result",
            payload={
                "ac_id": "AC-1",
                "contract_sha256": "b" * 64,
                "code_rev": "a" * 40,
                "run_id": "r1",
                "phase": "green",
                "verdict": "PASS",
                "evidence_refs": [],
                "reason": "",
            },
        )
        self.assertTrue(self.validate_event(envelope))

    def test_unexpected_envelope_field_fails(self):
        envelope = make_envelope()
        envelope["unexpected"] = 1
        self.assertTrue(self.validate_event(envelope))

    def test_bad_timestamp_format_fails(self):
        envelope = make_envelope(recorded_at="2026-11-16 12:00:01")
        self.assertTrue(self.validate_event(envelope))

    def test_out_of_range_integer_fails(self):
        envelope = make_envelope(duration_ms=INT64_MAX + 1)
        self.assertTrue(self.validate_event(envelope))

    def test_unknown_kind_fails(self):
        envelope = make_envelope(kind="tool.retry")
        self.assertTrue(self.validate_event(envelope))

    def test_unknown_authority_fails(self):
        envelope = make_envelope(authority="self_declared_owner")
        self.assertTrue(self.validate_event(envelope))

    def test_scope_requires_at_least_one_grouping_id(self):
        envelope = make_envelope()
        for key in ("campaign_id", "job_id", "task_id", "attempt_id", "session_id", "action_id"):
            envelope["scope"][key] = None
        self.assertTrue(self.validate_event(envelope))


class TestSourceAdapterContract(unittest.TestCase):
    """rizzstack.rails-source/1 shapes and caps."""

    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(RAILS / "source.schema.json")

    def find_subschema(self, schema_name: str):
        for branch in self.schema["anyOf"]:
            const = branch.get("properties", {}).get("schema", {}).get("const")
            if const == schema_name:
                return branch
        raise AssertionError("subschema %s not found" % schema_name)

    def test_declares_source_interface_version(self):
        self.assertTrue(any(
            branch.get("properties", {}).get("schema", {}).get("const") == "rizzstack.rails-source/1"
            for branch in self.schema["anyOf"]
        ))

    def test_candidate_excludes_ledger_assigned_fields(self):
        candidate = self.find_subschema("rizzstack.rails-candidate/1")
        properties = candidate["properties"]
        for forbidden in ("chain_id", "seq", "event_id", "hash", "recorded_at"):
            self.assertNotIn(forbidden, properties)
        self.assertEqual(candidate.get("additionalProperties"), False)
        self.assertIn("dedupe_key", candidate.get("required", []))

    def test_batch_caps(self):
        read_batch = self.find_subschema("rizzstack.rails-read-batch/1")
        limit = read_batch["properties"]["limit"]
        self.assertLessEqual(limit["maximum"], 500)
        caps = self.schema.get("caps", {})
        self.assertLessEqual(caps.get("batch_max_bytes", 10**9), 1048576)
        self.assertLessEqual(caps.get("record_max_bytes", 10**9), 65536)


class TestQueryContract(unittest.TestCase):
    """rizzstack.rails-query/1 request and rizzstack.rails-result/1 response."""

    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(RAILS / "query.schema.json")

    def find_subschema(self, schema_name: str):
        for branch in self.schema["anyOf"]:
            const = branch.get("properties", {}).get("schema", {}).get("const")
            if const == schema_name:
                return branch
        raise AssertionError("subschema %s not found" % schema_name)

    def test_selector_kinds_are_closed(self):
        request = self.find_subschema("rizzstack.rails-query/1")
        selector = request["properties"]["selector"]
        self.assertEqual(
            set(selector["properties"]["kind"]["enum"]),
            {"attempt", "job", "campaign", "session", "event"},
        )
        self.assertEqual(selector.get("additionalProperties"), False)

    def test_query_defaults_and_caps(self):
        request = self.find_subschema("rizzstack.rails-query/1")
        self.assertEqual(request["properties"]["limit"]["maximum"], 500)
        self.assertEqual(request["properties"]["max_bytes"]["maximum"], 32768)
        include = request["properties"]["include"]
        self.assertEqual(
            set(include["items"]["enum"]),
            {"tools", "verification", "review", "feedback"},
        )

    def test_valid_query_request(self):
        request = self.find_subschema("rizzstack.rails-query/1")
        query = {
            "schema": "rizzstack.rails-query/1",
            "selector": {"kind": "attempt", "id": "att_example"},
            "format": "markdown",
            "after": None,
            "limit": 100,
            "max_bytes": 32768,
            "include": ["tools", "verification"],
            "show_tokens": False,
        }
        self.assertEqual(validate_schema(query, request), [])
        query["limit"] = 501
        self.assertTrue(validate_schema(query, request))

    def test_result_envelope_fields(self):
        result = self.find_subschema("rizzstack.rails-result/1")
        for field in (
            "schema",
            "ok",
            "items",
            "markdown",
            "next_cursor",
            "has_more",
            "truncated",
            "completeness",
            "missing_sources",
            "integrity",
            "warnings",
        ):
            self.assertIn(field, result["required"])
        response = {
            "schema": "rizzstack.rails-result/1",
            "ok": True,
            "items": [],
            "markdown": "",
            "next_cursor": None,
            "has_more": False,
            "truncated": False,
            "completeness": "partial",
            "missing_sources": ["launcher-log"],
            "integrity": {"status": "unchecked", "checked_through": None},
            "warnings": [],
        }
        self.assertEqual(validate_schema(response, result), [])


class TestViewContract(unittest.TestCase):
    """rizzstack.rails-view/1 presentation projection."""

    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(RAILS / "view.schema.json")

    def test_view_declares_freeze_id(self):
        self.assertEqual(self.schema["properties"]["schema"]["const"], "rizzstack.rails-view/1")

    def test_lane_tree_fields(self):
        lanes = self.schema["properties"]["lanes"]
        lane_items = lanes["items"]
        for field in ("lane_id", "parent_lane_id", "status", "source_status", "marks"):
            self.assertIn(field, lane_items["properties"])
        statuses = lane_items["properties"]["status"]["enum"]
        self.assertIn("orphan", statuses)
        marks = lane_items["properties"]["marks"]["items"]
        for field in ("event_id", "kind", "timing_quality"):
            self.assertIn(field, marks["properties"])

    def test_valid_view_document(self):
        view = {
            "schema": "rizzstack.rails-view/1",
            "generated_at": "2026-11-16T12:00:00.000000Z",
            "lanes": [
                {
                    "lane_id": "worker-1.att-vector",
                    "parent_lane_id": "coordinator-1.job-vector",
                    "status": "open",
                    "source_status": "live",
                    "marks": [
                        {
                            "event_id": "worker-1.ledger-vector:1",
                            "kind": "tool.finish",
                            "occurred_at": "2026-11-16T12:00:00.000000Z",
                            "duration_ms": 2100,
                            "timing_quality": "measured",
                            "outcome": "ok",
                            "evidence_refs": ["a1"],
                            "ghost": False,
                        }
                    ],
                }
            ],
            "completeness": "complete",
            "missing_sources": [],
            "integrity": {"status": "unchecked", "checked_through": None},
        }
        self.assertEqual(validate_schema(view, self.schema), [])


class TestHttpContract(unittest.TestCase):
    """rizzstack.rails-http/1 routes, error envelope, append and export shapes."""

    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(RAILS / "http.schema.json")

    def test_route_table_matches_spec(self):
        paths = {route["path"] for route in self.schema["routes"]}
        for expected in (
            "/v1/health",
            "/v1/events",
            "/v1/view",
            "/v1/stream",
            "/v1/feedback/export",
            "/v1/append",
            "/v1/feedback",
            "/v1/interventions",
        ):
            self.assertIn(expected, paths)

    def test_error_codes_are_closed(self):
        codes = self.schema["properties"]["error_codes"]["items"]["enum"]
        for expected in (
            "invalid_request",
            "auth_required",
            "forbidden",
            "not_found",
            "conflict",
            "source_fork",
            "stale_fence",
            "too_large",
            "capacity",
            "source_unavailable",
            "storage_full",
            "reset_required",
            "capability_unavailable",
        ):
            self.assertIn(expected, codes)

    def test_error_envelope_shape(self):
        envelope = self.schema["properties"]["error_envelope"]
        errors = validate_schema(
            {"ok": False, "error": {"code": "invalid_request", "retryable": False, "request_id": "r-1"}},
            envelope,
        )
        self.assertEqual(errors, [])
        self.assertTrue(validate_schema({"ok": False}, envelope))

    def test_append_shapes(self):
        append_request = self.schema["properties"]["append_request"]
        append_response = self.schema["properties"]["append_response"]
        request = {
            "schema": "rizzstack.rails-append/1",
            "records": [
                {
                    "dedupe_key": "launcher.att-x.run1.event1",
                    "kind": "tool.finish",
                }
            ],
        }
        self.assertEqual(validate_schema(request, append_request), [])
        response = {
            "ok": True,
            "receipts": [{"event_id": "c:1", "seq": 1, "hash": "a" * 64, "duplicate": False}],
            "committed_cursor": 1,
        }
        self.assertEqual(validate_schema(response, append_response), [])

    def test_export_page_shape(self):
        export = self.schema["properties"]["export_page"]
        page = {
            "schema": "rizzstack.rails-export/1",
            "chain_id": "worker-1.ledger-x",
            "after": 0,
            "events": [],
            "next_cursor": 5,
            "head": {"seq": 5, "hash": "a" * 64},
            "has_more": False,
        }
        self.assertEqual(validate_schema(page, export), [])

    def test_request_and_feedback_caps(self):
        limits = self.schema["properties"]["limits"]
        self.assertLessEqual(limits["properties"]["request_max_bytes"]["maximum"], 1048576)
        self.assertLessEqual(limits["properties"]["feedback_max_bytes"]["maximum"], 8192)


class TestEvidenceContract(unittest.TestCase):
    """rizzstack.rails-evidence/1 RETURN companion."""

    @classmethod
    def setUpClass(cls):
        cls.schema = load_json(RAILS / "evidence.schema.json")

    def test_declares_freeze_id_and_pending_decision(self):
        self.assertEqual(self.schema["properties"]["schema"]["const"], "rizzstack.rails-evidence/1")
        self.assertEqual(
            self.schema["properties"]["receiver_decision"]["const"],
            "pending",
        )

    def test_required_evidence_fields(self):
        for field in (
            "generated_at",
            "machines",
            "ledgers",
            "origin_heads",
            "imported_checkpoints",
            "source_coverage",
            "selected_event_ids",
            "code_rev",
            "contract_sha256",
            "redaction_policy",
            "intervention_count",
            "verification_links",
            "receiver_decision",
        ):
            self.assertIn(field, self.schema["required"])

    def test_valid_evidence_document(self):
        document = {
            "schema": "rizzstack.rails-evidence/1",
            "generated_at": "2026-11-16T12:00:00.000000Z",
            "machines": [{"alias": "worker-1", "role": "worker"}],
            "ledgers": [{"machine": "worker-1", "ledger_uuid": "0f0e0d0c-0b0a-4948-8726-000000000001"}],
            "origin_heads": [{"chain_id": "worker-1.ledger-x", "seq": 12, "hash": "a" * 64}],
            "imported_checkpoints": [
                {"chain_id": "worker-1.ledger-x", "seq": 12, "hash": "a" * 64, "source": "launcher-log"}
            ],
            "source_coverage": [{"adapter": "launcher-log", "status": "covered", "gaps": []}],
            "selected_event_ids": ["worker-1.ledger-x:1"],
            "code_rev": "a" * 40,
            "contract_sha256": "b" * 64,
            "redaction_policy": "rails-safe/1",
            "intervention_count": 0,
            "verification_links": [],
            "receiver_decision": "pending",
        }
        self.assertEqual(validate_schema(document, self.schema), [])


class TestFreezeDigestRecorded(unittest.TestCase):
    """The canonical digest of the frozen contract set is recorded in README."""

    FREEZE_FILES = CONTRACT_FILES + ["examples.json", "fixtures/hash-vectors.json"]

    def compute_digest(self) -> str:
        hasher = hashlib.sha256()
        for name in sorted(self.FREEZE_FILES):
            path = RAILS / name
            hasher.update(name.encode("ascii"))
            hasher.update(b"\n")
            hasher.update(path.read_bytes())
            hasher.update(b"\n")
        return hasher.hexdigest()

    def test_readme_records_freeze_digest(self):
        readme = (RAILS / "README.md").read_text(encoding="utf-8")
        match = re.search(r"freeze-digest:\s*([0-9a-f]{64})", readme)
        self.assertIsNotNone(match, "README.md must record the freeze digest")
        self.assertEqual(match.group(1), self.compute_digest())

    def test_readme_documents_upstream_provenance(self):
        readme = (RAILS / "README.md").read_text(encoding="utf-8")
        self.assertIn("d5d0f425a64906ae1a50c1222314a5420da404d5", readme)
        self.assertIn("ledger.py", readme)


class OptionalJsonschemaCrossCheck(unittest.TestCase):
    """Cross-check the subset validator against jsonschema when installed."""

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_event_schema_is_valid_draft_2020_12(self):
        import jsonschema as js

        schema = load_json(RAILS / "event.schema.json")
        js.Draft202012Validator.check_schema(schema)

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_examples_pass_real_validator(self):
        import jsonschema as js

        schema = load_json(RAILS / "event.schema.json")
        validator = js.Draft202012Validator(schema)
        for example in load_json(RAILS / "examples.json"):
            with self.subTest(kind=example["kind"]):
                validator.validate(example)


if __name__ == "__main__":
    unittest.main()
