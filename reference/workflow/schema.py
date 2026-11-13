"""A small JSON Schema (draft 2020-12 subset) validator, standard library only.

It implements exactly the keywords the two shared schemas in ``schemas/`` use
(see :data:`SUPPORTED_KEYWORDS`); a test fails if a schema starts using a
keyword this file does not implement, so nothing is skipped silently.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

SUPPORTED_KEYWORDS = frozenset({
    "type", "enum", "const", "pattern", "minLength", "maxLength", "minimum",
    "minItems", "uniqueItems", "items", "required", "properties",
    "additionalProperties", "propertyNames", "anyOf",
})

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def load(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def first_error(value: Any, spec: Mapping[str, Any], path: str) -> tuple[str, str] | None:
    """Return ``(path, problem)`` for the first violation, or None."""
    if "type" in spec:
        types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        if not any(_TYPES[t](value) for t in types):
            return path, f"must be of type {'/'.join(types)}"
    if "const" in spec and value != spec["const"]:
        return path, f"must equal {spec['const']!r}"
    if "enum" in spec and value not in spec["enum"]:
        return path, "must be one of " + ", ".join(repr(x) for x in spec["enum"])
    if isinstance(value, str):
        if len(value.strip()) < spec.get("minLength", 0):
            return path, "is too short"
        if "maxLength" in spec and len(value) > spec["maxLength"]:
            return path, "is too long"
        if "pattern" in spec and re.search(spec["pattern"], value) is None:
            return path, "does not match the required pattern"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            return path, f"must be at least {spec['minimum']}"
    if isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            return path, f"needs at least {spec['minItems']} item(s)"
        if spec.get("uniqueItems"):
            seen = [json.dumps(x, sort_keys=True) for x in value]
            if len(set(seen)) != len(seen):
                return path, "must not contain duplicates"
        if isinstance(spec.get("items"), Mapping):
            for i, item in enumerate(value):
                err = first_error(item, spec["items"], f"{path}[{i}]")
                if err:
                    return err
    if isinstance(value, dict):
        for key in spec.get("required", []):
            if key not in value:
                return f"{path}.{key}", "is required"
        props = spec.get("properties", {})
        for key, child in props.items():
            if key in value:
                err = first_error(value[key], child, f"{path}.{key}")
                if err:
                    return err
        extra = spec.get("additionalProperties", True)
        for key in value:
            if key in props:
                continue
            if extra is False:
                return f"{path}.{key}", "is not an allowed field"
            if isinstance(extra, Mapping):
                err = first_error(value[key], extra, f"{path}.{key}")
                if err:
                    return err
        if isinstance(spec.get("propertyNames"), Mapping):
            for key in value:
                err = first_error(key, spec["propertyNames"], f"{path}.{key}")
                if err:
                    return f"{path}.{key}", "is not an allowed key"
    if "anyOf" in spec:
        if all(first_error(value, alt, path) for alt in spec["anyOf"]):
            return path, "does not match any allowed shape"
    return None
