"""RED for the frozen ``rizzstack.brief/1`` and ``rizzstack.attempt/1`` schemas.

Wave B, slice B2. Both schemas landed as drafts in workflow #141 with
``"x-status": "draft"`` and no examples. Freezing them means:

* both stay JSON Schema draft 2020-12 documents;
* at least one example of each shape lives under ``schemas/examples/`` and
  validates against its schema;
* a minimal brief still fails when a required field is missing;
* a high-tier brief without ``contract`` is refused;
* an unknown field is refused (``additionalProperties: false``);
* neither schema is marked draft any more;
* ``tools/check_brief_schemas.py`` exists, validates the files it is given
  (``python tools/check_brief_schemas.py FILE [FILE ...]``), exits 0 when every
  file validates and non-zero when one does not.

This module is the RED half: it is committed before the examples, the checker
and the ``x-status`` removal exist, so it fails now. It is also the acceptance
suite for the GREEN: no network, no secrets, stdlib plus ``jsonschema`` only.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
BRIEF_SCHEMA = ROOT / "schemas" / "rizzstack-brief.schema.json"
ATTEMPT_SCHEMA = ROOT / "schemas" / "rizzstack-attempt.schema.json"
EXAMPLES = ROOT / "schemas" / "examples"
CHECKER = ROOT / "tools" / "check_brief_schemas.py"

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

SCHEMAS = {"brief": BRIEF_SCHEMA, "attempt": ATTEMPT_SCHEMA}

#: The fields the brief cannot do without. Kept explicit: the test is the
#: frozen contract, so it must not read the answer back out of the schema.
REQUIRED_BRIEF_FIELDS = (
    "schema",
    "objective",
    "project",
    "source_rev",
    "assigned_files",
    "acceptance",
    "risk",
)

MINIMAL_BRIEF = {
    "schema": "rizzstack.brief/1",
    "objective": "Freeze rizzstack.brief/1 and rizzstack.attempt/1.",
    "project": "workflow",
    "source_rev": "0123456789abcdef0123456789abcdef01234567",
    "assigned_files": ["schemas/rizzstack-brief.schema.json"],
    "acceptance": {
        "criteria": ["every example validates"],
        "tests": ["tests/test_brief_schemas.py"],
    },
    "risk": {"tier": "medium", "reasons": ["schemas are referenced by dispatch clients"]},
}

MINIMAL_ATTEMPT = {
    "schema": "rizzstack.attempt/1",
    "attempt_id": "att_0123456789abcdef",
    "project": "workflow",
    "state": "queued",
    "created_at": "2026-11-24T00:00:00Z",
    "updated_at": "2026-11-24T00:00:00Z",
}


def _load(path: Path) -> dict:
    assert path.is_file(), f"{path.relative_to(ROOT)} is missing"
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(path: Path) -> jsonschema.Draft202012Validator:
    schema = _load(path)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _problems(validator: jsonschema.Draft202012Validator, instance: object) -> list[str]:
    return [f"{list(error.path)}: {error.message}" for error in validator.iter_errors(instance)]


def _example_paths(kind: str) -> list[Path]:
    return sorted(EXAMPLES.glob(f"rizzstack-{kind}-*.json"))


def test_both_schemas_are_draft_2020_12() -> None:
    for name, path in SCHEMAS.items():
        schema = _load(path)
        assert schema.get("$schema") == DRAFT_2020_12, (
            f"{name}: $schema is {schema.get('$schema')!r}, not {DRAFT_2020_12}"
        )
        validator_class = jsonschema.validators.validator_for(schema)
        assert validator_class is jsonschema.Draft202012Validator, (
            f"{name}: the document resolves to {validator_class.__name__}"
        )
        # Raises jsonschema.SchemaError if the document is not a valid 2020-12 schema.
        jsonschema.Draft202012Validator.check_schema(schema)


def test_brief_examples_validate() -> None:
    paths = _example_paths("brief")
    assert paths, "no schemas/examples/rizzstack-brief-*.json example exists"
    validator = _validator(BRIEF_SCHEMA)
    for path in paths:
        instance = json.loads(path.read_text(encoding="utf-8"))
        problems = _problems(validator, instance)
        assert not problems, f"{path.name} does not validate: {problems}"


def test_attempt_examples_validate() -> None:
    paths = _example_paths("attempt")
    assert paths, "no schemas/examples/rizzstack-attempt-*.json example exists"
    validator = _validator(ATTEMPT_SCHEMA)
    for path in paths:
        instance = json.loads(path.read_text(encoding="utf-8"))
        problems = _problems(validator, instance)
        assert not problems, f"{path.name} does not validate: {problems}"


def test_a_minimal_brief_missing_a_required_field_fails() -> None:
    validator = _validator(BRIEF_SCHEMA)
    problems = _problems(validator, MINIMAL_BRIEF)
    assert not problems, f"the control brief does not validate: {problems}"
    required = _load(BRIEF_SCHEMA).get("required") or []
    for field in REQUIRED_BRIEF_FIELDS:
        assert field in required, f"the brief schema does not require {field!r}"
        candidate = copy.deepcopy(MINIMAL_BRIEF)
        candidate.pop(field)
        assert not validator.is_valid(candidate), (
            f"a brief without {field!r} validated"
        )


def test_a_high_tier_brief_without_contract_fails() -> None:
    validator = _validator(BRIEF_SCHEMA)
    high = copy.deepcopy(MINIMAL_BRIEF)
    high["risk"] = {"tier": "high", "reasons": ["touches a protocol schema"]}
    assert not validator.is_valid(high), "a high-tier brief without contract validated"
    with_contract = copy.deepcopy(high)
    with_contract["contract"] = {"contract_version": "acdd/1", "id": "wave-b-b2"}
    problems = _problems(validator, with_contract)
    assert not problems, f"a high-tier brief with contract does not validate: {problems}"


def test_an_unknown_field_is_refused() -> None:
    brief_schema = _load(BRIEF_SCHEMA)
    assert brief_schema.get("additionalProperties") is False, (
        "the brief schema does not set additionalProperties: false"
    )
    unknown_brief = copy.deepcopy(MINIMAL_BRIEF)
    unknown_brief["wave_b_unknown_field"] = True
    assert not _validator(BRIEF_SCHEMA).is_valid(unknown_brief), (
        "a brief with an unknown field validated"
    )

    attempt_schema = _load(ATTEMPT_SCHEMA)
    assert attempt_schema.get("additionalProperties") is False, (
        "the attempt schema does not set additionalProperties: false"
    )
    unknown_attempt = copy.deepcopy(MINIMAL_ATTEMPT)
    unknown_attempt["wave_b_unknown_field"] = True
    assert not jsonschema.Draft202012Validator(attempt_schema).is_valid(unknown_attempt), (
        "an attempt with an unknown field validated"
    )


def test_neither_schema_is_marked_draft() -> None:
    for name, path in SCHEMAS.items():
        schema = _load(path)
        assert "x-status" not in schema, (
            f"{name}: still carries x-status={schema.get('x-status')!r}"
        )


def test_the_checker_accepts_the_examples_and_refuses_a_mutated_copy(tmp_path: Path) -> None:
    assert CHECKER.is_file(), "tools/check_brief_schemas.py is missing"
    examples = _example_paths("brief") + _example_paths("attempt")
    assert examples, "no brief or attempt example exists to hand the checker"

    accepted = subprocess.run(
        [sys.executable, str(CHECKER), *[str(path) for path in examples]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert accepted.returncode == 0, (
        f"the checker exited {accepted.returncode} on the examples\n"
        f"stdout:\n{accepted.stdout}\nstderr:\n{accepted.stderr}"
    )

    briefs = _example_paths("brief")
    seed = (
        json.loads(briefs[0].read_text(encoding="utf-8"))
        if briefs
        else copy.deepcopy(MINIMAL_BRIEF)
    )
    seed["checker_mutation"] = "an unknown field"
    mutated = tmp_path / "rizzstack-brief-mutated.json"
    mutated.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")

    refused = subprocess.run(
        [sys.executable, str(CHECKER), str(mutated)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0, (
        "the checker accepted a brief with an unknown field\n"
        f"stdout:\n{refused.stdout}\nstderr:\n{refused.stderr}"
    )
