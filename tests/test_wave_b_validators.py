"""RED for Wave B slice B3: one validator per language, frozen to the schemas.

Wave B (``docs/design/wave-b-worker-contract.md``, decision 3) freezes
``rizzstack.brief/1`` and ``rizzstack.attempt/1`` and then generates validators
from them: Python for bundlebees and hyvv, JavaScript for Orbit and the control
plane. Both are vendored into the consumer, so neither may add a runtime
dependency, and every consumer must reach the same verdict on the same
document.

The contract this module freezes
--------------------------------

``validators/python/rizzstack_validators.py`` (standard library only, loadable
by path with ``importlib``)::

    validate_brief(document, *, schema_dir=None) -> list[str]
    validate_attempt(document, *, schema_dir=None) -> list[str]

An empty list means the document is valid; every entry is one problem (a
JSON-pointer-ish path plus a message). ``schema_dir`` defaults to the
repository ``schemas/`` directory. Pointing it at a copy of the schemas that
was mutated must change the verdict, which is what proves the validator is
driven by the frozen document and not by a hand-copied checklist.

``validators/js/rizzstack-validators.mjs`` (ES module, no imports)::

    validateBrief(document) -> string[]
    validateAttempt(document) -> string[]

Both validators are exercised on one shared corpus, and the parity test
compares every verdict with ``jsonschema`` reading the frozen schemas, so
"generated from or checked against" is measured rather than asserted.

RED now: neither module exists.
"""

from __future__ import annotations

import ast
import copy
import functools
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
BRIEF_SCHEMA = SCHEMAS / "rizzstack-brief.schema.json"
ATTEMPT_SCHEMA = SCHEMAS / "rizzstack-attempt.schema.json"
EXAMPLES = SCHEMAS / "examples"
VALIDATORS = ROOT / "validators"
PY_VALIDATOR = VALIDATORS / "python" / "rizzstack_validators.py"
JS_VALIDATOR = VALIDATORS / "js" / "rizzstack-validators.mjs"

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

#: The brief fields the frozen schema requires. Listed explicitly so the test
#: is a contract, not a mirror of whatever the schema happens to say.
REQUIRED_BRIEF_FIELDS = (
    "schema",
    "objective",
    "project",
    "source_rev",
    "assigned_files",
    "acceptance",
    "risk",
)

MINIMAL_BRIEF: dict[str, Any] = {
    "schema": "rizzstack.brief/1",
    "objective": "Validate briefs with the vendored validator.",
    "project": "workflow",
    "source_rev": "0123456789abcdef0123456789abcdef01234567",
    "assigned_files": ["docs/README.md"],
    "acceptance": {"criteria": ["the brief validates"]},
    "risk": {"tier": "medium"},
}

MINIMAL_ATTEMPT: dict[str, Any] = {
    "schema": "rizzstack.attempt/1",
    "attempt_id": "att_0123456789abcdef",
    "project": "workflow",
    "state": "queued",
    "created_at": "2026-11-24T00:00:00Z",
    "updated_at": "2026-11-24T00:00:00Z",
}


# --------------------------------------------------------------------------
# module loading
# --------------------------------------------------------------------------


def _load_python_validator():
    assert PY_VALIDATOR.is_file(), (
        f"{PY_VALIDATOR.relative_to(ROOT)} is missing; B3 has not landed"
    )
    spec = importlib.util.spec_from_file_location("wave_b_python_validator", PY_VALIDATOR)
    assert spec is not None and spec.loader is not None, f"cannot load {PY_VALIDATOR}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _python_problems(kind: str, document: object, **kwargs: Any) -> list[str]:
    module = _load_python_validator()
    function = module.validate_brief if kind == "brief" else module.validate_attempt
    problems = function(copy.deepcopy(document), **kwargs)
    assert isinstance(problems, list), (
        f"validate_{kind} returned {type(problems).__name__}, not a list of problems"
    )
    for problem in problems:
        assert isinstance(problem, str) and problem, (
            f"validate_{kind} returned a non-string problem: {problem!r}"
        )
    return problems


# --------------------------------------------------------------------------
# the shared corpus: every case is (name, kind, document, expected verdict)
# --------------------------------------------------------------------------


def _brief_without(field: str) -> dict[str, Any]:
    document = copy.deepcopy(MINIMAL_BRIEF)
    document.pop(field)
    return document


def _shared_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def add(name: str, kind: str, document: object, valid: bool, why: str) -> None:
        cases.append({"name": name, "kind": kind, "document": document, "valid": valid, "why": why})

    add("brief-minimal", "brief", MINIMAL_BRIEF, True, "the control document")
    add(
        "brief-high-tier-with-contract",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "risk": {"tier": "high"}, "contract": {"contract_version": "acdd/1"}},
        True,
        "high risk is allowed when a contract is carried",
    )
    add(
        "brief-high-tier-without-contract",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "risk": {"tier": "high"}},
        False,
        "risk.tier high requires contract",
    )
    for field in ("schema", "objective", "project", "source_rev", "assigned_files", "acceptance", "risk"):
        add(f"brief-missing-{field}", "brief", _brief_without(field), False, f"{field} is required")
    add(
        "brief-unknown-field",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "wave_b_unknown_field": True},
        False,
        "additionalProperties is false",
    )
    add(
        "brief-short-source-rev",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "source_rev": "0123456"},
        False,
        "source_rev is a full 40- or 64-character hex id",
    )
    add(
        "brief-empty-assigned-files",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "assigned_files": []},
        False,
        "assigned_files has minItems 1",
    )
    add(
        "brief-duplicate-assigned-files",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "assigned_files": ["a.py", "a.py"]},
        False,
        "assigned_files is uniqueItems",
    )
    add(
        "brief-unknown-risk-tier",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "risk": {"tier": "critical"}},
        False,
        "risk.tier is low/medium/high",
    )
    add(
        "brief-acceptance-without-criteria",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "acceptance": {"tests": ["tests/test_x.py"]}},
        False,
        "acceptance requires criteria",
    )
    add(
        "brief-acceptance-as-array",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "acceptance": ["the brief validates"]},
        False,
        "rizzstack.brief/1 acceptance is the object form",
    )
    add(
        "brief-empty-objective",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "objective": ""},
        False,
        "objective has minLength 1",
    )
    add(
        "brief-ticket",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "ticket": "header.payload.signature"},
        True,
        "the optional Wave C ticket is a string",
    )
    add(
        "brief-contract-on-low-tier",
        "brief",
        {**copy.deepcopy(MINIMAL_BRIEF), "contract": {"contract_version": "acdd/1"}},
        True,
        "contract is optional below high risk",
    )
    add("attempt-minimal", "attempt", MINIMAL_ATTEMPT, True, "the control document")
    add(
        "attempt-backoff-rate-limited",
        "attempt",
        {**copy.deepcopy(MINIMAL_ATTEMPT), "state": "backoff", "reason": "rate_limited"},
        True,
        "backoff is a frozen state",
    )
    add(
        "attempt-usage-nulls",
        "attempt",
        {
            **copy.deepcopy(MINIMAL_ATTEMPT),
            "state": "succeeded",
            "usage": {"input_tokens": None, "output_tokens": None, "cost_usd": None},
        },
        True,
        "unknown usage is null, not absent",
    )
    add(
        "attempt-unknown-state",
        "attempt",
        {**copy.deepcopy(MINIMAL_ATTEMPT), "state": "expired"},
        False,
        "the state enum is frozen",
    )
    add(
        "attempt-missing-updated-at",
        "attempt",
        {key: value for key, value in MINIMAL_ATTEMPT.items() if key != "updated_at"},
        False,
        "updated_at is required",
    )
    add(
        "attempt-unknown-field",
        "attempt",
        {**copy.deepcopy(MINIMAL_ATTEMPT), "wave_b_unknown_field": True},
        False,
        "additionalProperties is false",
    )
    add(
        "attempt-unknown-nested-field",
        "attempt",
        {**copy.deepcopy(MINIMAL_ATTEMPT), "usage": {"wave_b_unknown_field": 1}},
        False,
        "additionalProperties is false inside usage",
    )
    return cases


def _corpus() -> list[dict[str, Any]]:
    """The shared cases plus every approved example under ``schemas/examples``."""
    cases = _shared_cases()
    for kind in ("brief", "attempt"):
        for path in sorted(EXAMPLES.glob(f"rizzstack-{kind}-*.json")):
            cases.append(
                {
                    "name": f"example-{path.stem}",
                    "kind": kind,
                    "document": json.loads(path.read_text(encoding="utf-8")),
                    "valid": True,
                    "why": f"{path.name} is an approved example",
                }
            )
    return cases


# --------------------------------------------------------------------------
# the oracle: the frozen schemas, read by jsonschema
# --------------------------------------------------------------------------


def _oracle(kind: str) -> jsonschema.Draft202012Validator:
    path = BRIEF_SCHEMA if kind == "brief" else ATTEMPT_SCHEMA
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema.get("$schema") == DRAFT_2020_12, f"{path.name} is not draft 2020-12"
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _oracle_verdict(kind: str, document: object) -> bool:
    # json-schema "format" is an annotation by default; the corpus stays away
    # from format-only cases so the oracle and the vendored validators compare
    # the structural keywords the consumers actually rely on.
    return _oracle(kind).is_valid(copy.deepcopy(document))


# --------------------------------------------------------------------------
# (a) the Python validator
# --------------------------------------------------------------------------


def test_python_validator_accepts_the_minimal_brief() -> None:
    problems = _python_problems("brief", MINIMAL_BRIEF)
    assert not problems, f"the minimal brief does not validate: {problems}"


def test_python_validator_accepts_the_minimal_attempt() -> None:
    problems = _python_problems("attempt", MINIMAL_ATTEMPT)
    assert not problems, f"the minimal attempt does not validate: {problems}"


@pytest.mark.parametrize("field", REQUIRED_BRIEF_FIELDS)
def test_python_validator_refuses_a_missing_required_field(field: str) -> None:
    problems = _python_problems("brief", _brief_without(field))
    assert problems, f"a brief without {field!r} validated"


def test_python_validator_refuses_a_high_tier_brief_without_contract() -> None:
    high = {**copy.deepcopy(MINIMAL_BRIEF), "risk": {"tier": "high"}}
    assert _python_problems("brief", high), "a high-tier brief without contract validated"

    with_contract = {**copy.deepcopy(high), "contract": {"contract_version": "acdd/1"}}
    problems = _python_problems("brief", with_contract)
    assert not problems, f"a high-tier brief with contract does not validate: {problems}"


# --------------------------------------------------------------------------
# (b) the JavaScript validator
# --------------------------------------------------------------------------

NODE = shutil.which("node")


def _js_verdicts() -> dict[str, bool]:
    assert JS_VALIDATOR.is_file(), f"{JS_VALIDATOR.relative_to(ROOT)} is missing; B3 has not landed"
    node = NODE or shutil.which("node")
    assert node, "node is required to run the JavaScript validator parity tests"

    with tempfile.TemporaryDirectory(prefix="wave-b-js-") as directory:
        work = Path(directory)
        cases_path = work / "cases.json"
        cases_path.write_text(json.dumps(_corpus()), encoding="utf-8")
        driver = work / "driver.mjs"
        driver.write_text(
            """
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const modulePath = process.argv[2];
const casesPath = process.argv[3];
const mod = await import(pathToFileURL(modulePath).href);
const cases = JSON.parse(await readFile(casesPath, 'utf8'));
const verdicts = {};
for (const entry of cases) {
  const validate = entry.kind === 'brief' ? mod.validateBrief : mod.validateAttempt;
  if (typeof validate !== 'function') {
    throw new Error(`missing ${entry.kind} validator export; exports: ${Object.keys(mod).join(', ')}`);
  }
  const problems = validate(entry.document);
  if (!Array.isArray(problems)) {
    throw new Error(`${entry.kind} validator returned ${typeof problems}, not an array`);
  }
  verdicts[entry.name] = problems.length === 0;
}
console.log(JSON.stringify(verdicts));
""",
            encoding="utf-8",
        )
        result = subprocess.run(
            [node, str(driver), str(JS_VALIDATOR), str(cases_path)],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    assert result.returncode == 0, (
        "the JavaScript validator driver failed\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    verdicts = json.loads(result.stdout.strip().splitlines()[-1])
    assert isinstance(verdicts, dict), f"driver printed {verdicts!r}"
    return verdicts


@functools.lru_cache(maxsize=1)
def _cached_js_verdicts() -> dict[str, bool]:
    return _js_verdicts()


def _js_verdict(name: str) -> bool:
    verdicts = _cached_js_verdicts()
    assert name in verdicts, f"the JavaScript validator driver did not report {name!r}"
    return verdicts[name]


def test_js_validator_accepts_the_minimal_brief() -> None:
    assert _js_verdict("brief-minimal") is True, "the JavaScript validator refused the minimal brief"


def test_js_validator_accepts_the_minimal_attempt() -> None:
    assert _js_verdict("attempt-minimal") is True, "the JavaScript validator refused the minimal attempt"


@pytest.mark.parametrize("field", REQUIRED_BRIEF_FIELDS)
def test_js_validator_refuses_a_missing_required_field(field: str) -> None:
    assert _js_verdict(f"brief-missing-{field}") is False, (
        f"the JavaScript validator accepted a brief without {field!r}"
    )


def test_js_validator_refuses_a_high_tier_brief_without_contract() -> None:
    assert _js_verdict("brief-high-tier-without-contract") is False, (
        "the JavaScript validator accepted a high-tier brief without contract"
    )
    assert _js_verdict("brief-high-tier-with-contract") is True, (
        "the JavaScript validator refused a high-tier brief with contract"
    )


# --------------------------------------------------------------------------
# (c) checked against the frozen schemas; same verdict on the shared corpus
# --------------------------------------------------------------------------


def test_python_validator_reads_the_frozen_schema_it_is_given(tmp_path: Path) -> None:
    assert not _python_problems("brief", MINIMAL_BRIEF), "the control brief does not validate"

    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    brief_schema = json.loads(BRIEF_SCHEMA.read_text(encoding="utf-8"))
    brief_schema["required"] = [*brief_schema["required"], "wave_b_probe"]
    (schema_dir / BRIEF_SCHEMA.name).write_text(json.dumps(brief_schema), encoding="utf-8")
    shutil.copyfile(ATTEMPT_SCHEMA, schema_dir / ATTEMPT_SCHEMA.name)

    mutated = _python_problems("brief", MINIMAL_BRIEF, schema_dir=schema_dir)
    assert mutated, (
        "the Python validator accepted a brief that the schema it was handed requires "
        "'wave_b_probe' on; it is not driven by schema_dir"
    )
    assert not _python_problems("attempt", MINIMAL_ATTEMPT, schema_dir=schema_dir), (
        "the Python validator cannot validate an attempt from an alternate schema_dir"
    )


def test_both_validators_match_the_frozen_schemas_on_the_shared_corpus() -> None:
    disagreements: list[str] = []
    for case in _corpus():
        oracle = _oracle_verdict(case["kind"], case["document"])
        python = not _python_problems(case["kind"], case["document"])
        javascript = _js_verdict(case["name"])
        expected = case["valid"]
        if not (oracle == python == javascript == expected):
            disagreements.append(
                f"{case['name']}: expected={expected} schema={oracle} "
                f"python={python} javascript={javascript} ({case['why']})"
            )
    assert not disagreements, "the validators disagree with the schemas:\n" + "\n".join(disagreements)


# --------------------------------------------------------------------------
# (d) no consumer adds a runtime dependency to enforce validation
# --------------------------------------------------------------------------


def test_the_validators_ship_no_dependency_manifest() -> None:
    if not VALIDATORS.exists():
        pytest.fail(f"{VALIDATORS.relative_to(ROOT)} is missing; B3 has not landed")
    forbidden = {"package.json", "package-lock.json", "requirements.txt", "pyproject.toml", "Pipfile"}
    found = sorted(
        str(path.relative_to(ROOT))
        for path in VALIDATORS.rglob("*")
        if path.is_file() and path.name in forbidden
    )
    assert not found, f"the vendored validators declare dependencies: {found}"


def test_the_python_validator_imports_only_the_standard_library() -> None:
    assert PY_VALIDATOR.is_file(), f"{PY_VALIDATOR.relative_to(ROOT)} is missing; B3 has not landed"
    tree = ast.parse(PY_VALIDATOR.read_text(encoding="utf-8"), filename=str(PY_VALIDATOR))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                imported.add(f"{'.' * node.level}{node.module or ''}")
            elif node.module:
                imported.add(node.module.split(".")[0])
    external = sorted(imported - sys.stdlib_module_names)
    assert not external, f"the Python validator imports third-party modules: {external}"


def test_the_javascript_validator_has_no_imports() -> None:
    assert JS_VALIDATOR.is_file(), f"{JS_VALIDATOR.relative_to(ROOT)} is missing; B3 has not landed"
    source = JS_VALIDATOR.read_text(encoding="utf-8")
    offenders = []
    if re.search(r"^\s*import\b", source, re.MULTILINE):
        offenders.append("import")
    if re.search(r"\brequire\s*\(", source):
        offenders.append("require()")
    if re.search(r"^\s*export\b[^\n]*\bfrom\b", source, re.MULTILINE):
        offenders.append("export ... from")
    assert not offenders, f"the JavaScript validator pulls in modules: {offenders}"


def test_the_python_validator_runs_without_site_packages(tmp_path: Path) -> None:
    assert PY_VALIDATOR.is_file(), f"{PY_VALIDATOR.relative_to(ROOT)} is missing; B3 has not landed"
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('v', {str(PY_VALIDATOR)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        f"minimal = json.loads({json.dumps(MINIMAL_BRIEF)!r})\n"
        f"high = json.loads({json.dumps({**MINIMAL_BRIEF, 'risk': {'tier': 'high'}})!r})\n"
        "print(json.dumps([module.validate_brief(minimal), module.validate_brief(high)]))\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        # -I isolates from the environment and user site, -S drops site-packages:
        # a validator that needs jsonschema or any other wheel cannot start.
        [sys.executable, "-I", "-S", str(driver)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, (
        "the Python validator needs a third-party runtime dependency\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload[0] == [], f"the minimal brief does not validate under -I -S: {payload[0]}"
    assert payload[1], "a high-tier brief without contract validated under -I -S"
