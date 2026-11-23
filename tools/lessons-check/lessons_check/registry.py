"""Strict loading of the packaged lessons registry."""

from __future__ import annotations

import json
from pathlib import Path

FIELDS = ("id", "source", "summary", "fix")
REGISTRY_FILE = Path(__file__).with_name("lessons.json")


class RegistryError(Exception):
    """Raised when the lessons registry cannot be read, parsed or validated."""


def load(path=None) -> list[dict[str, str]]:
    """Load and strictly validate a lessons registry.

    ``path`` defaults to the ``lessons.json`` shipped beside this module. Any
    read, parse or shape problem raises :class:`RegistryError`; nothing is
    guessed or silently dropped.
    """
    location = Path(path) if path is not None else REGISTRY_FILE
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryError(f"cannot read registry {location}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise RegistryError(f"registry {location} is not valid UTF-8: {exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RegistryError(f"registry {location} is not valid JSON: {exc}") from exc
    return _validated(data, location)


def _validated(data, location: Path) -> list[dict[str, str]]:
    if not isinstance(data, list):
        raise RegistryError(f"registry {location} must be a JSON list")
    lessons: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise RegistryError(f"registry {location}: lesson {index} must be a JSON object")
        lesson: dict[str, str] = {}
        for field in FIELDS:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RegistryError(
                    f"registry {location}: lesson {index} has no non-empty string {field}"
                )
            lesson[field] = value
        if lesson["id"] in seen:
            raise RegistryError(f"registry {location}: duplicate lesson id {lesson['id']}")
        seen.add(lesson["id"])
        lessons.append(lesson)
    return lessons
