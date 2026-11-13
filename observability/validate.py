"""Stdlib-only JSON Schema checker for the observability records.

This is a deliberately small subset of draft 2020-12: type, const, enum,
properties, required, additionalProperties, items, min/max items, min/max
length, pattern, minimum, maximum, oneOf, anyOf, allOf, if/then, and $ref to local
files or in-document $defs. It exists so these contracts can be tested
without adding a dependency or editing CI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


class SchemaError(ValueError):
    """A document failed schema validation."""


def _type_ok(value: Any, declared: str) -> bool:
    if declared == "object":
        return isinstance(value, dict)
    if declared == "array":
        return isinstance(value, list)
    if declared == "string":
        return isinstance(value, str)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "null":
        return value is None
    raise SchemaError(f"unsupported type name {declared!r}")


class Validator:
    def __init__(self, schema_dir: Path = SCHEMA_DIR) -> None:
        self.schema_dir = Path(schema_dir)
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, name: str) -> dict[str, Any]:
        path = self.schema_dir / name
        key = str(path.resolve())
        if key not in self._cache:
            with path.open(encoding="utf-8") as handle:
                self._cache[key] = json.load(handle)
        return self._cache[key]

    def validate(self, instance: Any, schema: dict[str, Any], *, base: Path | None = None) -> None:
        self._check(instance, schema, base or self.schema_dir, path="$", doc=schema)

    def validate_file(self, instance: Any, schema_name: str) -> None:
        schema = self.load(schema_name)
        self.validate(instance, schema, base=self.schema_dir)

    def _resolve(self, ref: str, doc: dict[str, Any], base: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
        url, frag = urldefrag(ref)
        if url:
            if url.startswith("https://"):
                name = Path(url).name
                target = self.load(name)
                new_base = self.schema_dir
                new_doc = target
            else:
                path = (base / url).resolve()
                if not path.exists():
                    path = (self.schema_dir / Path(url).name).resolve()
                key = str(path)
                if key not in self._cache:
                    with path.open(encoding="utf-8") as handle:
                        self._cache[key] = json.load(handle)
                target = self._cache[key]
                new_base = path.parent
                new_doc = target
        else:
            target = doc
            new_base = base
            new_doc = doc
        if frag:
            node: Any = target
            parts = [p for p in frag.split("/") if p]
            if parts and parts[0] == "":
                parts = parts[1:]
            for part in parts:
                if part.startswith("#"):
                    continue
                if not isinstance(node, dict) or part not in node:
                    raise SchemaError(f"unresolved $ref {ref!r}")
                node = node[part]
            if not isinstance(node, dict):
                raise SchemaError(f"$ref {ref!r} did not resolve to an object")
            return node, new_base, new_doc
        return target, new_base, new_doc

    def _check(self, instance: Any, schema: dict[str, Any], base: Path, path: str, doc: dict[str, Any]) -> None:
        if "$ref" in schema:
            resolved, new_base, new_doc = self._resolve(schema["$ref"], doc, base)
            rest = {k: v for k, v in schema.items() if k != "$ref"}
            self._check(instance, resolved, new_base, path, new_doc)
            if rest:
                self._apply(instance, rest, base, path, doc)
            return
        self._apply(instance, schema, base, path, doc)

    def _apply(self, instance: Any, schema: dict[str, Any], base: Path, path: str, doc: dict[str, Any]) -> None:
        if "type" in schema:
            declared = schema["type"]
            names = declared if isinstance(declared, list) else [declared]
            if not any(_type_ok(instance, name) for name in names):
                raise SchemaError(f"{path}: expected type {declared!r}, got {type(instance).__name__}")
        if "const" in schema and instance != schema["const"]:
            raise SchemaError(f"{path}: expected const {schema['const']!r}")
        if "enum" in schema and instance not in schema["enum"]:
            raise SchemaError(f"{path}: {instance!r} is not in enum")
        if "pattern" in schema and isinstance(instance, str):
            if re.search(schema["pattern"], instance) is None:
                # JSON Schema pattern is unanchored unless the pattern itself anchors
                raise SchemaError(f"{path}: does not match pattern")
        # Use fullmatch when pattern starts with ^ and ends with $
        if "minLength" in schema and isinstance(instance, str) and len(instance) < schema["minLength"]:
            raise SchemaError(f"{path}: shorter than minLength")
        if "maxLength" in schema and isinstance(instance, str) and len(instance) > schema["maxLength"]:
            raise SchemaError(f"{path}: longer than maxLength")
        if "minimum" in schema and isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if instance < schema["minimum"]:
                raise SchemaError(f"{path}: below minimum")
        if "maximum" in schema and isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if instance > schema["maximum"]:
                raise SchemaError(f"{path}: above maximum")
        if "oneOf" in schema:
            ok = 0
            errors = []
            for index, option in enumerate(schema["oneOf"]):
                try:
                    self._check(instance, option, base, f"{path}/oneOf/{index}", doc)
                    ok += 1
                except SchemaError as exc:
                    errors.append(str(exc))
            if ok != 1:
                raise SchemaError(f"{path}: expected exactly one oneOf branch to match (got {ok})")
        if "anyOf" in schema:
            for index, option in enumerate(schema["anyOf"]):
                try:
                    self._check(instance, option, base, f"{path}/anyOf/{index}", doc)
                    break
                except SchemaError:
                    continue
            else:
                raise SchemaError(f"{path}: no anyOf branch matched")
        if "allOf" in schema:
            for index, option in enumerate(schema["allOf"]):
                self._check(instance, option, base, f"{path}/allOf/{index}", doc)
        if "if" in schema:
            try:
                self._check(instance, schema["if"], base, f"{path}/if", doc)
                matched = True
            except SchemaError:
                matched = False
            if matched and "then" in schema:
                self._check(instance, schema["then"], base, f"{path}/then", doc)
            if not matched and "else" in schema:
                self._check(instance, schema["else"], base, f"{path}/else", doc)
        if isinstance(instance, dict) and ("properties" in schema or "required" in schema or "additionalProperties" in schema or "minProperties" in schema):
            props = schema.get("properties") or {}
            required = schema.get("required") or []
            for key in required:
                if key not in instance:
                    raise SchemaError(f"{path}: missing required property {key!r}")
            additional = schema.get("additionalProperties", True)
            for key, value in instance.items():
                if key in props:
                    self._check(value, props[key], base, f"{path}.{key}", doc)
                elif additional is False:
                    raise SchemaError(f"{path}: unexpected property {key!r}")
                elif isinstance(additional, dict):
                    self._check(value, additional, base, f"{path}.{key}", doc)
            if "minProperties" in schema and len(instance) < schema["minProperties"]:
                raise SchemaError(f"{path}: fewer than minProperties")
        if isinstance(instance, list) and ("items" in schema or "minItems" in schema or "maxItems" in schema or "uniqueItems" in schema):
            if "minItems" in schema and len(instance) < schema["minItems"]:
                raise SchemaError(f"{path}: fewer than minItems")
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                raise SchemaError(f"{path}: more than maxItems")
            if "items" in schema:
                for index, item in enumerate(instance):
                    self._check(item, schema["items"], base, f"{path}[{index}]", doc)
            if schema.get("uniqueItems"):
                for index, item in enumerate(instance):
                    if item in instance[:index]:
                        raise SchemaError(f"{path}: duplicate item at index {index}")


def validate_instance(instance: Any, schema_name: str, schema_dir: Path | None = None) -> None:
    Validator(schema_dir or SCHEMA_DIR).validate_file(instance, schema_name)
