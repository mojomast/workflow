"""Common envelope discriminator for observability and usage records.

Most records name their type as ``<record name>/v<major>``. The records in this
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

The collector snapshot uses its published ``rizzstack.observability/snapshot/1``
discriminator directly in ``schema``, with no ``schema_version`` field.
:func:`record_type` returns the discriminator for these shapes, and
:func:`normalize` returns a copy with ``schema`` set, leaving every original
field unchanged. Stdlib only.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}/v[0-9]+$")
_SNAPSHOT = "rizzstack.observability/snapshot/1"


class EnvelopeError(ValueError):
    """A record has no usable or a contradictory type discriminator."""


def record_type(record: Mapping[str, Any]) -> str:
    """Return the on-wire discriminator without changing the record."""
    if not isinstance(record, Mapping):
        raise EnvelopeError("record is not an object")
    schema = record.get("schema")
    version = record.get("schema_version")
    if schema == _SNAPSHOT:
        if "schema_version" in record:
            raise EnvelopeError("the assembled snapshot carries its version in schema only")
        return schema
    if schema is not None:
        if not isinstance(schema, str) or not _TYPE_RE.fullmatch(schema):
            raise EnvelopeError("schema must look like <name>/v<major>")
        if "schema_version" in record and version not in (schema, schema.rsplit("/", 1)[1]):
            raise EnvelopeError("schema_version does not match the version in schema")
        return schema
    if isinstance(version, str) and _TYPE_RE.fullmatch(version):
        return version
    raise EnvelopeError("record has no schema and no <name>/v<major> schema_version")


def normalize(record: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of *record* with ``schema`` set to its discriminator; nothing else changes."""
    out = dict(record)
    out["schema"] = record_type(record)
    return out
