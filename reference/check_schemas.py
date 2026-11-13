#!/usr/bin/env python3
"""Cross-check the protocol schemas with a full JSON Schema implementation.

The reference demo validates with a small stdlib subset (workflow/schema.py).
This script, run in CI with the `jsonschema` package, checks that the schemas
are valid Draft 2020-12, that the subset accepts nothing the real validator
rejects for the example contract and the demo's evidence, and that the example
contract's hash matches its content.

Usage: python3 reference/check_schemas.py [DEMO_RUN_DIR]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))

from workflow import acdd  # noqa: E402


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    contract_schema = load(ROOT / "schemas/acdd-contract.schema.json")
    evidence_schema = load(ROOT / "schemas/tdd-evidence.schema.json")
    for schema in (contract_schema, evidence_schema):
        jsonschema.Draft202012Validator.check_schema(schema)
    contract_v = jsonschema.Draft202012Validator(contract_schema)
    evidence_v = jsonschema.Draft202012Validator(evidence_schema)

    example = load(ROOT / "templates/contract.example.json")
    contract_v.validate(example)
    acdd.check_frozen(example)
    checked = {"contracts": 1, "evidence": 0}

    if len(argv) > 1:
        run = Path(argv[1])
        for path in sorted((run / "contracts").glob("*.json")):
            contract = load(path)
            if "rejected" in contract:
                continue  # a contract the demo refused (W0-invalid); it must stay invalid
            
            errors = list(contract_v.iter_errors(contract))
            if errors:
                print(f"{path}: {errors[0].message}", file=sys.stderr)
                return 1
            checked["contracts"] += 1
        for path in sorted((run / "evidence").glob("*/*.json")):
            record = load(path)
            if record.get("evidence_version") != "tdd-evidence/1":
                continue  # reports and rejection notes are not evidence records
            errors = list(evidence_v.iter_errors(record))
            if errors:
                print(f"{path}: {errors[0].message}", file=sys.stderr)
                return 1
            checked["evidence"] += 1
        if checked["evidence"] == 0:
            print("no evidence records found under", run, file=sys.stderr)
            return 1
    print(f"schemas valid; checked {checked['contracts']} contracts and {checked['evidence']} evidence records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
