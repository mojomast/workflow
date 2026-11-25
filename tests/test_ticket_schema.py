"""RED for the ``rizzstack.ticket/1`` claims schema.

Wave C, slice C1. The signed dispatch ticket (hyvv ADR 0002) is a compact JWS
whose claims set is fixed here. The schema lands in workflow next to the other
cross-repo contracts: ``schemas/rizzstack-ticket.schema.json``, with examples
under ``schemas/examples/rizzstack-ticket-*.json``.

The claims are the ADR's list and nothing else:

* ``brief_sha256`` (64 hex), ``assigned_files_sha256`` (64 hex) and
  ``contract_sha256`` (64 hex or null) - digests;
* ``project``, ``source_rev`` (40 lower-case hex);
* ``risk_tier`` in ``low``/``medium``/``high``;
* ``assignment`` - the worker binding, null-only in v1;
* ``aud``, ``iat``, ``exp`` (integer seconds, ``exp`` after ``iat``), ``jti``
  (single use), ``kid`` (issuer key id).

This module is the RED half: the schema and the example do not exist yet, so
every test fails now. It is also the acceptance suite for the GREEN: stdlib plus
``jsonschema`` only, no crypto and no key material (wave C does not sign here).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "rizzstack-ticket.schema.json"
EXAMPLES = ROOT / "schemas" / "examples"

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

#: Every claim the ticket must carry. Kept explicit: the test is the frozen
#: contract, so it must not read the answer back out of the schema.
REQUIRED_CLAIMS = (
    "brief_sha256",
    "project",
    "source_rev",
    "assigned_files_sha256",
    "risk_tier",
    "contract_sha256",
    "assignment",
    "aud",
    "iat",
    "exp",
    "jti",
    "kid",
)

DIGEST_FIELDS = ("brief_sha256", "assigned_files_sha256", "contract_sha256")

VALID_CLAIMS = {
    "brief_sha256": "a" * 64,
    "project": "workflow",
    "source_rev": "b" * 40,
    "assigned_files_sha256": "c" * 64,
    "risk_tier": "medium",
    "contract_sha256": None,
    "assignment": None,
    "aud": "hyvv",
    "iat": 1764000000,
    "exp": 1764000600,
    "jti": "6d1c0f5a2b7e4c3d9a8f0e1b2c3d4e5f",
    "kid": "coordinator-2026-11",
}


def _load(path: Path) -> dict:
    assert path.is_file(), f"{path.relative_to(ROOT)} is missing"
    return json.loads(path.read_text(encoding="utf-8"))


def _validator() -> jsonschema.Draft202012Validator:
    schema = _load(SCHEMA)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _problems(validator: jsonschema.Draft202012Validator, claims: object) -> list[str]:
    return [f"{list(error.path)}: {error.message}" for error in validator.iter_errors(claims)]


def test_ticket_schema_exists_and_is_draft_2020_12() -> None:
    assert SCHEMA.is_file(), "schemas/rizzstack-ticket.schema.json is missing"
    schema = _load(SCHEMA)
    assert schema.get("$schema") == DRAFT_2020_12, (
        f"$schema is {schema.get('$schema')!r}, not {DRAFT_2020_12}"
    )
    validator_class = jsonschema.validators.validator_for(schema)
    assert validator_class is jsonschema.Draft202012Validator, (
        f"the document resolves to {validator_class.__name__}"
    )
    # Raises jsonschema.SchemaError if the document is not a valid 2020-12 schema.
    jsonschema.Draft202012Validator.check_schema(schema)


def test_a_valid_claims_set_validates() -> None:
    problems = _problems(_validator(), VALID_CLAIMS)
    assert not problems, f"the control claims set does not validate: {problems}"


def test_every_ticket_example_validates() -> None:
    paths = sorted(EXAMPLES.glob("rizzstack-ticket-*.json"))
    assert paths, "no schemas/examples/rizzstack-ticket-*.json example exists"
    validator = _validator()
    for path in paths:
        claims = json.loads(path.read_text(encoding="utf-8"))
        problems = _problems(validator, claims)
        assert not problems, f"{path.name} does not validate: {problems}"
        assert isinstance(claims.get("iat"), int) and isinstance(claims.get("exp"), int), (
            f"{path.name}: iat and exp must be integer seconds"
        )
        assert claims["exp"] > claims["iat"], (
            f"{path.name}: exp ({claims['exp']}) is not after iat ({claims['iat']})"
        )


def test_a_missing_claim_is_rejected() -> None:
    validator = _validator()
    required = _load(SCHEMA).get("required") or []
    for claim in REQUIRED_CLAIMS:
        assert claim in required, f"the ticket schema does not require {claim!r}"
        candidate = copy.deepcopy(VALID_CLAIMS)
        candidate.pop(claim)
        assert not validator.is_valid(candidate), f"a ticket without {claim!r} validated"


def test_a_bad_digest_is_rejected() -> None:
    validator = _validator()
    for field in DIGEST_FIELDS:
        for bad in ("not-a-digest", "a" * 63, "a" * 65, "A" * 64, 123):
            candidate = copy.deepcopy(VALID_CLAIMS)
            candidate[field] = bad
            assert not validator.is_valid(candidate), (
                f"{field}={bad!r} validated; the field must be 64 lower-case hex or null"
            )


def test_assignment_is_null_only_in_v1() -> None:
    validator = _validator()
    for bad in ("host-1", {"worker": "host-1"}, ["host-1"]):
        candidate = copy.deepcopy(VALID_CLAIMS)
        candidate["assignment"] = bad
        assert not validator.is_valid(candidate), (
            f"assignment={bad!r} validated; v1 keeps the worker binding null-only"
        )
    assert validator.is_valid(VALID_CLAIMS), "assignment: null must validate"


def test_risk_tier_is_one_of_low_medium_high() -> None:
    validator = _validator()
    for tier in ("low", "medium", "high"):
        candidate = copy.deepcopy(VALID_CLAIMS)
        candidate["risk_tier"] = tier
        problems = _problems(validator, candidate)
        assert not problems, f"risk_tier={tier!r} does not validate: {problems}"
    for bad in ("critical", "HIGH", "", None):
        candidate = copy.deepcopy(VALID_CLAIMS)
        candidate["risk_tier"] = bad
        assert not validator.is_valid(candidate), f"risk_tier={bad!r} validated"


def test_iat_and_exp_are_integers() -> None:
    validator = _validator()
    for field in ("iat", "exp"):
        for bad in ("1764000000", 1764000000.5, None):
            candidate = copy.deepcopy(VALID_CLAIMS)
            candidate[field] = bad
            assert not validator.is_valid(candidate), (
                f"{field}={bad!r} validated; it must be integer seconds"
            )
    assert VALID_CLAIMS["exp"] > VALID_CLAIMS["iat"], "the control fixture must expire after it is issued"


def test_contract_sha256_is_nullable() -> None:
    validator = _validator()
    candidate = copy.deepcopy(VALID_CLAIMS)
    candidate["contract_sha256"] = "d" * 64
    problems = _problems(validator, candidate)
    assert not problems, f"a 64-hex contract_sha256 does not validate: {problems}"
    assert validator.is_valid(VALID_CLAIMS), "contract_sha256: null must validate for legacy slices"
