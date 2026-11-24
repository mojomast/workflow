"""rizzstack.memory/1 disk-backed vault service.

``DiskVault(root)`` reads, queries and writes a real markdown vault directory
using only the standard library. The contract text lives in
``docs/memory-contract.md`` and the normative oracle in
``tests/test_memory_contract.py``.
"""

from .vault import (
    CONTRACT,
    MAX_EXCERPT_CHARS,
    MAX_ITEMS,
    MAX_SNIPPET_CHARS,
    MAX_TOTAL_CHARS,
    MEMORY_TYPES,
    QUARANTINE_ROOT,
    RRF_K,
    TYPE_DIR,
    TYPE_POLICY,
    VAULT_DIRS,
    ContractError,
    DiskVault,
    excerpt_of,
    is_expired,
    memory_sha,
    parse_memory,
    quarantine_prefix,
    refuse,
    resolve_mode,
    serialize_memory,
    validate_frontmatter,
    validate_query_op,
    validate_query_result,
    validate_write_op,
    zone_of,
)

__all__ = [
    "CONTRACT",
    "MAX_EXCERPT_CHARS",
    "MAX_ITEMS",
    "MAX_SNIPPET_CHARS",
    "MAX_TOTAL_CHARS",
    "MEMORY_TYPES",
    "QUARANTINE_ROOT",
    "RRF_K",
    "TYPE_DIR",
    "TYPE_POLICY",
    "VAULT_DIRS",
    "ContractError",
    "DiskVault",
    "excerpt_of",
    "is_expired",
    "memory_sha",
    "parse_memory",
    "quarantine_prefix",
    "refuse",
    "resolve_mode",
    "serialize_memory",
    "validate_frontmatter",
    "validate_query_op",
    "validate_query_result",
    "validate_write_op",
    "zone_of",
]
