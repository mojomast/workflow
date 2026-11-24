"""Command-line recall endpoint for the ``rizzstack.memory/1`` vault.

``python3 -m rizzstack_memory query --vault DIR QUERY`` answers one
lease-time recall request: a JSON request on stdin (optional) plus the query
text as the last argv word. It prints exactly one JSON object with the ranked,
capped items and never mutates the vault.

The request and response shapes are the bundlebees recall protocol:
requests carry ``contract``, ``query`` and ``caps``; responses carry
``contract``, ``vault_rev`` and ``items`` whose entries are
``{id,type,sha,path,title,excerpt}``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .vault import (
    CONTRACT,
    MAX_EXCERPT_CHARS,
    MAX_ITEMS,
    MAX_TOTAL_CHARS,
    ContractError,
    DiskVault,
)

MAX_QUERY_CHARS = 500
DEFAULT_CAPS = {
    "max_items": MAX_ITEMS,
    "max_excerpt_chars": MAX_EXCERPT_CHARS,
    "max_total_chars": MAX_TOTAL_CHARS,
}


def _refuse(code: str, message: str) -> None:
    raise ContractError(code, message)


def _read_request(stream) -> dict:
    """Read one optional JSON request from ``stream``.

    Empty (or whitespace-only) stdin means "use the defaults"; anything else
    must be a JSON object whose contract is exactly ``rizzstack.memory/1``.
    """
    text = stream.read()
    if not text.strip():
        return {}
    try:
        request = json.loads(text)
    except (ValueError, TypeError):
        _refuse("request_invalid", "the recall request is not valid JSON")
    if not isinstance(request, dict):
        _refuse("request_invalid", "the recall request must be a JSON object")
    if request.get("contract") != CONTRACT:
        _refuse("contract_mismatch", f"the recall request contract must be {CONTRACT}")
    return request


def _cap(value, default: int, ceiling: int, floor: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return max(floor, min(value, ceiling))


def _caps(request: dict) -> dict:
    supplied = request.get("caps")
    if not isinstance(supplied, dict):
        supplied = {}
    return {
        "max_items": _cap(supplied.get("max_items"), DEFAULT_CAPS["max_items"], MAX_ITEMS, floor=1),
        "max_excerpt_chars": _cap(
            supplied.get("max_excerpt_chars"), DEFAULT_CAPS["max_excerpt_chars"], MAX_EXCERPT_CHARS
        ),
        "max_total_chars": _cap(supplied.get("max_total_chars"), DEFAULT_CAPS["max_total_chars"], MAX_TOTAL_CHARS),
    }


def _query_text(argv_query, request: dict) -> str:
    q = argv_query if isinstance(argv_query, str) else ""
    if not q.strip():
        candidate = request.get("query")
        q = candidate if isinstance(candidate, str) else ""
    return q.strip()[:MAX_QUERY_CHARS]


def _items(hits: list, caps: dict) -> list:
    items = []
    total = 0
    for hit in hits:
        item = {
            "id": hit["id"],
            "type": hit["type"],
            "sha": hit["sha"],
            "path": hit["path"],
            "title": hit["title"],
            "excerpt": hit["snippet"][: caps["max_excerpt_chars"]],
        }
        size = sum(len(value) for value in item.values())
        if total + size > caps["max_total_chars"]:
            break
        items.append(item)
        total += size
    return items


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m rizzstack_memory", description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    query_parser = subparsers.add_parser("query", help="answer one recall request")
    query_parser.add_argument("--vault", required=True, help="vault root directory (must already exist)")
    query_parser.add_argument("query", nargs="?", help="query text; falls back to the request query")
    options = parser.parse_args(argv)

    try:
        if options.command != "query":
            _refuse("unknown_command", f"unknown command: {options.command}")
        if not os.path.isdir(options.vault):
            _refuse("vault_missing", f"vault directory does not exist: {options.vault}")
        request = _read_request(sys.stdin)
        caps = _caps(request)
        q = _query_text(options.query, request)
        if not q:
            _refuse("query_empty", "the recall query is empty")
        result = DiskVault(options.vault).query({"op": "query", "q": q, "k": caps["max_items"]})
        payload = {
            "contract": CONTRACT,
            "vault_rev": result["vault_rev"],
            "items": _items(result["hits"], caps),
        }
        print(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    except ContractError as err:
        print(f"memory query: {err.code}", file=sys.stderr)
        return 2
    except OSError as err:
        print(f"memory query: {err.strerror or 'io_error'}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DEFAULT_CAPS", "MAX_QUERY_CHARS", "main"]
