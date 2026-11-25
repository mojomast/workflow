from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _type_matches(value: Any, declared: str) -> bool:
    if declared == "object":
        return isinstance(value, dict)
    if declared == "array":
        return isinstance(value, list)
    if declared == "string":
        return isinstance(value, str)
    if declared == "integer":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            or isinstance(value, float)
            and value.is_integer()
        )
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "null":
        return value is None
    raise ValueError(f"unsupported JSON Schema type {declared!r}")


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return False


def _check(
    instance: Any,
    schema: dict[str, Any] | bool,
    path: str,
    problems: list[str],
) -> None:
    if schema is True:
        return
    if schema is False:
        problems.append(f"{path}: value is disallowed by the schema")
        return

    if "type" in schema:
        declared = schema["type"]
        names = declared if isinstance(declared, list) else [declared]
        if not any(_type_matches(instance, name) for name in names):
            problems.append(f"{path}: expected type {declared!r}")

    if "const" in schema and not _json_equal(instance, schema["const"]):
        problems.append(f"{path}: expected const {schema['const']!r}")

    if "enum" in schema and not any(
        _json_equal(instance, option) for option in schema["enum"]
    ):
        problems.append(f"{path}: value {instance!r} is not in the allowed enum")

    if isinstance(instance, str):
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            problems.append(f"{path}: does not match pattern {schema['pattern']!r}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            problems.append(
                f"{path}: length is below minLength {schema['minLength']}"
            )
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            problems.append(
                f"{path}: length exceeds maxLength {schema['maxLength']}"
            )

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            problems.append(f"{path}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            problems.append(f"{path}: value exceeds maximum {schema['maximum']}")

    for branch in schema.get("allOf", []):
        _check(instance, branch, path, problems)

    if "if" in schema:
        condition_problems: list[str] = []
        _check(instance, schema["if"], path, condition_problems)
        if not condition_problems and "then" in schema:
            _check(instance, schema["then"], path, problems)
        elif condition_problems and "else" in schema:
            _check(instance, schema["else"], path, problems)

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                problems.append(f"{path}: missing required property {key!r}")

        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                _check(value, properties[key], f"{path}.{key}", problems)
            elif "additionalProperties" in schema:
                additional = schema["additionalProperties"]
                if additional is False:
                    problems.append(f"{path}: unexpected property {key!r}")
                elif isinstance(additional, dict):
                    _check(value, additional, f"{path}.{key}", problems)

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            problems.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            problems.append(f"{path}: more than maxItems {schema['maxItems']}")
        if "items" in schema:
            for index, item in enumerate(instance):
                _check(item, schema["items"], f"{path}[{index}]", problems)
        if schema.get("uniqueItems"):
            for index, item in enumerate(instance):
                if any(_json_equal(item, previous) for previous in instance[:index]):
                    problems.append(f"{path}: duplicate item at index {index}")


def _validate(document: Any, schema_name: str, schema_dir: str | Path | None) -> list[str]:
    directory = (
        Path(schema_dir)
        if schema_dir is not None
        else Path(__file__).resolve().parents[2] / "schemas"
    )
    with (directory / schema_name).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    problems: list[str] = []
    _check(document, schema, "$", problems)
    return problems


def validate_brief(
    document: Any, *, schema_dir: str | Path | None = None
) -> list[str]:
    return _validate(document, "rizzstack-brief.schema.json", schema_dir)


def validate_attempt(
    document: Any, *, schema_dir: str | Path | None = None
) -> list[str]:
    return _validate(document, "rizzstack-attempt.schema.json", schema_dir)
