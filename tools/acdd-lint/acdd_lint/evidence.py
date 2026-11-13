"""Protocol checks for ``tdd-evidence/1`` histories.

A history is the ordered set of records for one contract id.  The checks here
cover RED before GREEN, test-fingerprint equality, contract-hash staleness,
orphans and (when a key is supplied) HMAC signatures.  Inputs are plain
dictionaries and the functions never import bundlebees.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping

Problem = dict[str, str]

_AUTHORITY_ROLES = {"verifier", "human"}


def canonical(record: Mapping[str, Any]) -> bytes:
    """Return the canonical signed bytes for *record*."""
    body = {
        key: value
        for key, value in record.items()
        if key not in ("signature", "_path")
    }
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return text.encode("utf-8")


def record_digest(record: Mapping[str, Any]) -> str:
    """Return the canonical sha256 of *record*, including its signature.

    Private keys starting with ``_`` are ignored so a record's digest does not
    depend on where it was loaded from.
    """
    body = {
        key: value
        for key, value in record.items()
        if not str(key).startswith("_")
    }
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_signature(record: Mapping[str, Any], key: bytes) -> bool:
    """True only when *record* carries the HMAC-SHA256 made with *key*."""
    if not isinstance(record, Mapping):
        return False
    signature = record.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    expected = hmac.new(bytes(key), canonical(record), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _problem(code: str, where: str, message: str) -> Problem:
    return {"code": code, "where": where, "message": message}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _role(record: Mapping[str, Any]) -> str:
    return str(_mapping(record.get("produced_by")).get("role") or "")


def _phase(record: Mapping[str, Any]) -> str:
    return str(record.get("phase") or "")


def _sequence(record: Mapping[str, Any]) -> int | None:
    """Return the signed sequence number, or None when it is not an integer."""
    value = _mapping(record).get("sequence")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _time_sort_key(item: tuple[str, Mapping[str, Any]]) -> tuple[str, str]:
    filename, record = item
    return (str(_mapping(record).get("at") or ""), filename)


def _sequence_sort_key(item: tuple[str, Mapping[str, Any]]) -> tuple[int, str]:
    filename, record = item
    return (_sequence(record) or 0, filename)


def _stale(record: Mapping[str, Any], expected_sha: str) -> bool:
    return str(_mapping(record).get("contract_sha256") or "") != expected_sha


def _expected_contract_sha(contract: Mapping[str, Any]) -> str:
    return str(_mapping(contract.get("review")).get("contract_sha256") or "")


def _test_first(contract: Mapping[str, Any]) -> bool:
    return _mapping(contract.get("tdd")).get("test_first") is not False


def _is_valid_red(record: Mapping[str, Any]) -> bool:
    return (
        _phase(record) == "red"
        and _role(record) in _AUTHORITY_ROLES
        and record.get("classification") == "behavioral_failure"
    )


def _check_sequence_order(items: list[tuple[str, Mapping[str, Any]]]) -> list[Problem]:
    """Return order_invalid problems when the signed sequence chain is broken."""
    offending: list[str] = []
    seen: set[str] = set()

    def mark(filename: str) -> None:
        if filename not in seen:
            seen.add(filename)
            offending.append(filename)

    sequences = [_sequence(record) for _, record in items]
    counts: dict[Any, int] = {}
    first_index: dict[Any, int] = {}
    for index, value in enumerate(sequences):
        counts[value] = counts.get(value, 0) + 1
        first_index.setdefault(value, index)

    for index, (filename, _) in enumerate(items):
        value = sequences[index]
        if value != index + 1:
            mark(filename)
        if counts[value] > 1 and first_index[value] != index:
            mark(filename)

    for index, (filename, record) in enumerate(items):
        previous = _mapping(record).get("prev_sha256")
        if index == 0:
            if previous is not None:
                mark(filename)
            continue
        if sequences[index] != (sequences[index - 1] or 0) + 1:
            mark(filename)
        if previous != record_digest(items[index - 1][1]):
            mark(filename)

    return [
        _problem(
            "order_invalid",
            filename,
            "evidence sequence is not a gap-free signed chain from 1; re-record the history with contiguous sequence numbers and matching prev_sha256 links",
        )
        for filename in offending
    ]


def check_history(
    contract: Mapping[str, Any] | None,
    records: list[tuple[str, Mapping[str, Any]]],
    key: bytes | None = None,
) -> list[Problem]:
    """Check one contract's evidence history and return its protocol problems."""
    items = [(filename, record) for filename, record in records]
    sequenced = bool(items) and all(_sequence(record) is not None for _, record in items)
    if sequenced:
        items.sort(key=_sequence_sort_key)
        order_problems = _check_sequence_order(items)
    else:
        items.sort(key=_time_sort_key)
        order_problems = []

    if contract is None:
        return [
            _problem(
                "evidence_orphan",
                filename,
                "evidence record names no known contract; add the contract or move the record to the right evidence directory",
            )
            for filename, _ in items
        ]

    expected_sha = _expected_contract_sha(contract)
    require_test_first = _test_first(contract)
    problems: list[Problem] = list(order_problems)
    last_valid_red: Mapping[str, Any] | None = None

    valid_reds: list[tuple[str, Mapping[str, Any]]] = []
    if not sequenced:
        for filename, record in items:
            record = _mapping(record)
            if not _stale(record, expected_sha) and _is_valid_red(record):
                valid_reds.append((filename, record))

    for filename, item in items:
        record = _mapping(item)
        stale = _stale(record, expected_sha)
        if stale:
            problems.append(
                _problem(
                    "evidence_stale",
                    filename,
                    "record was produced against a different contract hash; re-run the check against the frozen contract",
                )
            )
        if key is not None and not verify_signature(record, key):
            problems.append(
                _problem(
                    "evidence_tampered",
                    filename,
                    "record signature is missing or invalid; re-record it with the coordinator key",
                )
            )
        if stale:
            continue

        role = _role(record)
        if _phase(record) == "red" and role in _AUTHORITY_ROLES:
            if record.get("classification") != "behavioral_failure":
                classification = record.get("classification")
                problems.append(
                    _problem(
                        "red_invalid",
                        f"{filename}: classification",
                        f"RED classified as {classification!r}, expected behavioral_failure; fix the test environment so only the missing behavior fails",
                    )
                )
            else:
                last_valid_red = record
            continue

        if _phase(record) == "green" and role in _AUTHORITY_ROLES:
            if record.get("classification") != "passed":
                classification = record.get("classification")
                problems.append(
                    _problem(
                        "green_failed",
                        f"{filename}: classification",
                        f"GREEN classified as {classification!r}, expected passed; make the implementation pass the approved tests without editing them",
                    )
                )

            if sequenced:
                candidate = last_valid_red
                if require_test_first and candidate is None:
                    problems.append(
                        _problem(
                            "red_missing",
                            filename,
                            "GREEN has no earlier verifier behavioral_failure RED; record RED on the baseline or set tdd.test_first: false honestly",
                        )
                    )
            else:
                at = str(record.get("at") or "")
                earlier = [
                    red
                    for _, red in valid_reds
                    if str(_mapping(red).get("at") or "") < at
                ]
                same_second = [
                    red
                    for _, red in valid_reds
                    if str(_mapping(red).get("at") or "") == at
                ]
                candidate = earlier[-1] if earlier else (same_second[-1] if same_second else None)
                if require_test_first and not earlier:
                    if same_second:
                        problems.append(
                            _problem(
                                "order_unproven",
                                filename,
                                "GREEN shares its timestamp with a valid RED but no signed sequence orders them; add sequence and prev_sha256 or record RED before GREEN",
                            )
                        )
                    else:
                        problems.append(
                            _problem(
                                "red_missing",
                                filename,
                                "GREEN has no earlier verifier behavioral_failure RED; record RED on the baseline or set tdd.test_first: false honestly",
                            )
                        )

            if candidate is not None and record.get("test_fingerprints") != candidate.get("test_fingerprints"):
                problems.append(
                    _problem(
                        "tests_tampered",
                        f"{filename}: test_fingerprints",
                        "GREEN test fingerprints differ from RED; rerun the same approved test files unchanged",
                    )
                )

    return problems
