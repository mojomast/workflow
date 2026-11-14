"""Semantic validation for the machine-readable RETURN manifest.

A return manifest is the companion to templates/RETURN.md: it records what a
producer claims about one feature job, binds those claims to the immutable
feature packet and protocol revision, and carries an integrity digest. It is
evidence, never authority. It never carries a human decision: receiver_decision
must stay pending, and a filled decision is refused.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import jsonschema

BASE = Path(__file__).resolve().parents[1]
SCHEMA_PATH = BASE / "schemas" / "return-manifest.schema.json"
SUPPORTED = ("rizzstack.return/1",)
PENDING_DECISION: dict[str, Any] = {
    "status": "pending",
    "decided_by": None,
    "decided_at": None,
    "note": None,
}


class ReturnError(Exception):
    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message, "fix": self.fix}


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, compact separators, ASCII (same as packet_digest)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _without_generated_at(value: Any) -> Any:
    """Drop every generated_at field, at any depth, before digesting.

    generated_at is the only volatile timestamp this protocol allows, and a
    volatile value must never change the digest of an otherwise identical
    manifest.
    """
    if isinstance(value, Mapping):
        return {key: _without_generated_at(item) for key, item in value.items() if key != "generated_at"}
    if isinstance(value, list):
        return [_without_generated_at(item) for item in value]
    return value


def digest_body(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The manifest body evidence_digest covers: no evidence_digest, no generated_at."""
    body = {key: value for key, value in manifest.items() if key != "evidence_digest"}
    return _without_generated_at(body)


def evidence_digest(manifest: Mapping[str, Any]) -> str:
    """sha256 of the canonical manifest body; the value evidence_digest must equal."""
    return hashlib.sha256(canonical_json(digest_body(manifest)).encode("utf-8")).hexdigest()


def seal(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with evidence_digest recomputed. It does not validate."""
    sealed = copy.deepcopy(dict(manifest))
    sealed.pop("evidence_digest", None)
    sealed["evidence_digest"] = evidence_digest(sealed)
    return sealed


def pending_receiver_decision() -> dict[str, Any]:
    """The only receiver_decision a generated manifest may carry."""
    return copy.deepcopy(PENDING_DECISION)


def validate(manifest: Mapping[str, Any]) -> dict[str, Any]:
    try:
        jsonschema.validate(manifest, _schema())
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        if path == "receiver_decision" or path.startswith("receiver_decision."):
            # A filled decision is not a shape accident; name the rule it breaks.
            raise ReturnError(
                "receiver_decision_not_pending",
                f"receiver_decision must stay pending ({path}: {exc.message})",
                "Record the human decision in the RETURN document; never edit this slot.",
            ) from exc
        raise ReturnError("return_schema", f"{path or '<root>'}: {exc.message}",
                          "Fix the manifest shape.") from exc

    if manifest.get("schema") not in SUPPORTED:
        raise ReturnError("return_version_unsupported", f"{manifest.get('schema')!r} is not implemented",
                          "Upgrade the validator or emit rizzstack.return/1.")

    # Integrity first: a manifest edited after sealing is refused before any of
    # its claims are interpreted.
    expected = evidence_digest(manifest)
    if manifest.get("evidence_digest") != expected:
        raise ReturnError(
            "evidence_digest_mismatch",
            f"evidence_digest is {manifest.get('evidence_digest')!r}, canonical body hashes to {expected}",
            "Recompute it with tools/return_manifest.py --seal, or refuse the manifest.",
        )

    decision = manifest.get("receiver_decision") or {}
    for key, value in PENDING_DECISION.items():
        if decision.get(key) != value:
            raise ReturnError("receiver_decision_not_pending",
                              f"receiver_decision.{key} must be {value!r} in a generated manifest",
                              "Record the human decision in the RETURN document; never edit this slot.")

    seen: set[str] = set()
    for index, entry in enumerate(manifest.get("acceptance") or []):
        criterion = str(entry.get("id"))
        if criterion in seen:
            raise ReturnError("acceptance_duplicate", f"acceptance id {criterion} appears more than once",
                              "Report each criterion exactly once.")
        seen.add(criterion)
        if entry.get("status") == "PASS" and not entry.get("evidence"):
            raise ReturnError("pass_without_evidence",
                              f"{criterion} is PASS with no evidence",
                              "Attach the recorded check or report FAIL, UNVERIFIED, NOT RUN or BLOCKED.")

    red_green = manifest.get("red_green") or {}
    if red_green.get("test_first") and red_green.get("red") is None:
        raise ReturnError("red_green_inconsistent", "test_first is true but no RED record is named",
                          "Name the RED record or set test_first false.")
    if not red_green.get("test_first") and red_green.get("red") is not None:
        raise ReturnError("red_green_inconsistent", "a RED record is named but test_first is false",
                          "Set test_first true or drop the invented RED record.")

    descendant = manifest.get("descendant")
    authority = (manifest.get("authorization") or {}).get("authority")
    if descendant is None:
        if authority != "m1-authorization":
            raise ReturnError("descendant_authority_mismatch",
                              f"an exact feature needs authority m1-authorization, not {authority!r}",
                              "Keep the authority and the descendant block consistent.")
    else:
        if authority != "descendant-policy":
            raise ReturnError("descendant_authority_mismatch",
                              f"a dependent feature needs authority descendant-policy, not {authority!r}",
                              "Keep the authority and the descendant block consistent.")
        if descendant.get("accepted_commit") != (manifest.get("repository") or {}).get("source_rev"):
            raise ReturnError(
                "descendant_revision_mismatch",
                "descendant.accepted_commit is not repository.source_rev",
                "A dependent feature runs at the derived accepted commit; fix one of them.",
            )

    integration = manifest.get("integration") or {}
    present = [integration.get(field) is not None for field in ("commit", "wave", "evidence", "accepted_wave_digest")]
    if any(present) and not all(present):
        raise ReturnError("integration_incomplete",
                          "integration is partially populated",
                          "Record commit, wave, evidence and accepted_wave_digest together, or leave all four null.")

    return dict(manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a rizzstack.return/1 manifest, or seal one.")
    parser.add_argument("files", nargs="+", help="manifest JSON files")
    parser.add_argument("--seal", action="store_true",
                        help="print each manifest with a recomputed evidence_digest (does not validate)")
    args = parser.parse_args(argv)
    status = 0
    for name in args.files:
        try:
            manifest = json.loads(Path(name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{name}: error: {exc}", file=sys.stderr)
            status = 1
            continue
        if args.seal:
            print(json.dumps(seal(manifest), indent=2, sort_keys=True))
            continue
        try:
            validate(manifest)
        except ReturnError as exc:
            print(f"{name}: {exc.code}: {exc.message}", file=sys.stderr)
            status = 1
        else:
            print(f"{name}: ok {manifest['evidence_digest']}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
