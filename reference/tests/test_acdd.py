"""ACDD contract tests for the reference demo (written before reference/workflow/acdd.py)."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFERENCE))

SHA = "a" * 40


def contract(**over):
    c = {
        "contract_version": "acdd/1",
        "id": "W1-pricing",
        "title": "Add apply_tax",
        "outcome": {"summary": "Callers can add tax", "observable_behavior": ["apply_tax(1000, 10) == 1100"]},
        "interfaces": [{"name": "apply_tax", "kind": "function", "change": "add"}],
        "acceptance_criteria": [
            {"id": "AC-001", "given": "a price of 1000 cents", "when": "apply_tax(1000, 10)", "then": "it returns 1100",
             "verification": "test", "tests": ["tests/test_pricing.py::PricingTests::test_apply_tax"]},
            {"id": "AC-002", "statement": "existing discounts still pass", "verification": "test",
             "tests": ["tests/test_pricing.py::PricingTests::test_ten_percent_off"], "regression": True},
        ],
        "scope": {"assigned_files": ["shop/pricing.py"], "test_files": ["tests/test_pricing.py"], "prohibited": ["shop/labels.py"]},
        "source_rev": SHA,
        "tdd": {"applicable": True},
        "verification": {"independent": True},
        "evidence_required": ["red", "green", "integration"],
        "authorization": {"human_gates": ["merge", "release", "deploy", "publish"]},
    }
    c.update(over)
    return c


class AcddContractTests(unittest.TestCase):
    def setUp(self):
        from workflow import acdd
        self.acdd = acdd

    def assertCode(self, code, fn, *args, **kw):
        with self.assertRaises(self.acdd.ContractError) as cm:
            fn(*args, **kw)
        self.assertEqual(cm.exception.code, code)
        self.assertTrue(cm.exception.fix)
        return cm.exception

    def test_valid_contract_round_trips_without_mutation(self):
        c = contract()
        before = copy.deepcopy(c)
        out = self.acdd.validate_contract(c)
        self.assertEqual(c, before)
        self.assertEqual(out["id"], "W1-pricing")

    def test_schema_violations_name_the_field(self):
        bad = contract()
        del bad["outcome"]
        err = self.assertCode("contract_invalid", self.acdd.validate_contract, bad)
        self.assertIn("outcome", err.field + err.error)
        bad = contract()
        bad["acceptance_criteria"][0]["id"] = "1"
        self.assertCode("contract_invalid", self.acdd.validate_contract, bad)
        bad = contract()
        bad["scope"]["anything_goes"] = True
        self.assertCode("contract_invalid", self.acdd.validate_contract, bad)

    def test_code_checks(self):
        cases = [
            lambda c: c["acceptance_criteria"][1].update(id="AC-001"),
            lambda c: c["acceptance_criteria"][0].update(tests=[]),
            lambda c: c["scope"]["assigned_files"].append("tests/test_pricing.py"),
            lambda c: c.update(evidence_required=["green"]),
            lambda c: c.update(tdd={"applicable": False}),
            lambda c: c["scope"]["assigned_files"].append("../escape.py"),
            lambda c: c["scope"]["assigned_files"].append("shop/labels.py"),
            lambda c: c["authorization"].update(human_gates=["merge"]),
            lambda c: c.update(dependencies=["W1-pricing"]),
        ]
        for mutate in cases:
            c = contract()
            mutate(c)
            self.assertCode("contract_invalid", self.acdd.validate_contract, c)

    def test_hash_freeze_and_tamper_detection(self):
        c = contract()
        body = json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        self.assertEqual(self.acdd.contract_sha256(c), hashlib.sha256(body).hexdigest())
        frozen = self.acdd.freeze_contract(c, approved_by="reviewer", approved_at="2026-11-12T18:00:00Z")
        self.assertEqual(self.acdd.check_frozen(frozen), frozen["review"]["contract_sha256"])
        widened = copy.deepcopy(frozen)
        widened["scope"]["assigned_files"].append("shop/extra.py")
        self.assertCode("contract_changed", self.acdd.check_frozen, widened)
        self.assertCode("contract_not_frozen", self.acdd.check_frozen, contract())

    def test_helpers(self):
        c = contract()
        self.assertEqual(self.acdd.red_set(c), ["tests/test_pricing.py::PricingTests::test_apply_tax"])
        self.assertEqual(self.acdd.added_interfaces(c), ["apply_tax"])
        self.assertTrue(self.acdd.is_prohibited("shop/labels.py", c))

    def test_example_contract_in_templates_is_valid(self):
        path = REFERENCE.parent / "templates" / "contract.example.json"
        example = json.loads(path.read_text(encoding="utf-8"))
        self.acdd.validate_contract(example)
        self.acdd.check_frozen(example)

    def test_validator_covers_every_schema_keyword(self):
        for name in ("acdd-contract.schema.json", "tdd-evidence.schema.json"):
            schema = json.loads((REFERENCE.parent / "schemas" / name).read_text(encoding="utf-8"))
            used = set()

            def walk(node):
                if isinstance(node, dict):
                    used.update(k for k in node if not k.startswith("$"))
                    for k, v in node.items():
                        if k == "properties":
                            for child in v.values():
                                walk(child)
                        elif k not in ("enum", "const", "required", "description", "title"):
                            walk(v)
                elif isinstance(node, list):
                    for item in node:
                        walk(item)

            walk(schema)
            self.assertLessEqual(used - {"description", "title"}, set(self.acdd.SUPPORTED_KEYWORDS), name)


if __name__ == "__main__":
    unittest.main()
