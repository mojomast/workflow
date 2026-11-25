#!/usr/bin/env python3
"""Validate brief and attempt JSON documents against their frozen schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATHS = {
    "rizzstack.brief/1": ROOT / "schemas" / "rizzstack-brief.schema.json",
    "rizzstack.attempt/1": ROOT / "schemas" / "rizzstack-attempt.schema.json",
}


def main(paths: list[str]) -> int:
    if not paths:
        print("usage: python tools/check_brief_schemas.py FILE [FILE ...]", file=sys.stderr)
        return 1

    validators = {}
    for kind, schema_path in SCHEMA_PATHS.items():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        validators[kind] = jsonschema.Draft202012Validator(schema)

    failed = False
    for filename in paths:
        path = Path(filename)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("the document must be a JSON object")
            kind = document.get("schema")
            if kind not in validators:
                raise ValueError(f"unsupported or missing schema: {kind!r}")
            errors = list(validators[kind].iter_errors(document))
        except (OSError, UnicodeError, ValueError) as error:
            print(f"FAIL {path}: {error}", file=sys.stderr)
            failed = True
            continue

        if errors:
            failed = True
            for error in errors:
                print(f"FAIL {path}: {error.json_path}: {error.message}", file=sys.stderr)
        else:
            print(f"OK {path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
