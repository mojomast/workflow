"""Common envelope discriminator for observability and usage records.

Every record names its type as ``<record name>/v<major>``. The records in this
package carry it in ``schema`` (for example ``agent.lifecycle/v1``) and keep
``schema_version: "v1"`` as a version-only field. The Hermes Forge usage
record is frozen as ``bee.usage/v1`` and carries its type in
``schema_version`` instead, with no ``schema`` field. Rather than break that
frozen schema, ingestion normalizes both shapes to one discriminator:

=============================  ======================  =====================
Record                         ``schema``              ``schema_version``
=============================  ======================  =====================
agent.lifecycle, failure, ...  ``agent.lifecycle/v1``  ``v1``
bee.usage (frozen)             absent                  ``bee.usage/v1``
=============================  ======================  =====================

:func:`record_type` returns the discriminator for either shape, and
:func:`normalize` returns a copy with ``schema`` set, leaving every original
field unchanged. Stdlib only.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}/v[0-9]+$")
_VERSION_RE = re.compile(r"^v[0-9]+$")


class EnvelopeError(ValueError):
    """A record has no usable or a contradictory type discriminator."""


def record_type(record: Mapping[str, Any]) -> str:
    """Return ``<name>/v<major>`` for a record in either envelope shape."""
    if not isinstance(record, Mapping):
        raise EnvelopeError("record is not an object")
    schema = record.get("schema")
    version = record.get("schema_version")
    if schema is not None:
        if not isinstance(schema, str) or not _TYPE_RE.match(schema):
            raise EnvelopeError("schema must look like <name>/v<major>")
        if isinstance(version, str) and _TYPE_RE.match(version) and version != schema:
            raise EnvelopeError("schema and schema_version name different record types")
        if isinstance(version, str) and _VERSION_RE.match(version) and not schema.endswith("/" + version):
            raise EnvelopeError("schema_version does not match the version in schema")
        return schema
    if isinstance(version, str) and _TYPE_RE.match(version):
        return version
    raise EnvelopeError("record has no schema and no <name>/v<major> schema_version")


def normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of *record* with ``schema`` set to its discriminator; nothing else changes."""
    out = dict(record)
    out["schema"] = record_type(record)
    return out
