"""Conformance tests for rizzstack.memory/1 (schemas/memory-schema.v1.json).

The memory contract is the semantic-memory layer of the rizzstack: a markdown,
Obsidian-compatible vault read and written through one small, agent-agnostic
surface. This module is the normative conformance oracle for the contract
artifacts of this slice:

- schemas/memory-schema.v1.json  frontmatter, operation and injection shapes
- docs/memory-contract.md        the contract text and the vault rulebook
- docs/protocol.md               the workflow mirror of the umbrella map

The vault service that will implement the operations is a follow-on slice.
Until it lands, the oracle below is the reference behavior any implementation
must match, and the honest gaps live in docs/memory-contract.md.

The module also carries the gate-exact scanner-hygiene self-scan: every line of
every leased file is checked against the verify gate's refusal rules, and any
hit fails the suite. The rule patterns are assembled from fragments at runtime
so this file itself stays clean under those same rules.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:  # jsonschema is optional; the hand oracle never depends on it.
    import jsonschema
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - exercised on minimal installs
    jsonschema = None

SCHEMA_PATH = ROOT / "schemas" / "memory-schema.v1.json"
CONTRACT_DOC = ROOT / "docs" / "memory-contract.md"
PROTOCOL_DOC = ROOT / "docs" / "protocol.md"
TEST_FILE = ROOT / "tests" / "test_memory_contract.py"
LEASE_FILES = (CONTRACT_DOC, SCHEMA_PATH, PROTOCOL_DOC, TEST_FILE)

CONTRACT = "rizzstack.memory/1"
NOW = "2026-11-14T18:20:00Z"
LATER = "2026-11-15T09:00:00Z"
WRITER = "agent:bee-7"

MEMORY_TYPES = ("decision", "learning", "pitfall", "env-fact", "project-state", "reference")
TYPE_DIR = {
    "decision": "decisions",
    "learning": "learnings",
    "pitfall": "pitfalls",
    "env-fact": "entities",
    "project-state": "projects",
    "reference": "concepts",
}
TYPE_POLICY = {
    "decision": "decision-permanent",
    "learning": "learning-until-superseded",
    "pitfall": "pitfall-until-fixed",
    "env-fact": "env-fact-until-fix",
    "project-state": "project-state-until-done",
    "reference": "reference-refresh",
}
VAULT_DIRS = ("concepts", "decisions", "entities", "learnings", "pitfalls", "projects", "sessions")
VAULT_ROOT_FILES = ("VAULT.md", "hot.md", "index.md", "log.md")
SOURCE_KINDS = ("session-digest", "operator-note", "pull-request", "file", "tool-output", "external")
GRANT_APPROVER_KINDS = ("human", "orbit", "bundlebees")
QUARANTINE_ROOT = ".quarantine"
CURATED_PREFIXES = ("concepts/", "decisions/")
CURATED_FILES = ("hot.md", "index.md")
REVIEWED_PREFIXES = ("entities/", "learnings/", "pitfalls/", "projects/")
SERVICE_PREFIXES = ("sessions/",)
SERVICE_FILES = ("VAULT.md", "log.md")

MAX_ITEMS = 8
MAX_EXCERPT_CHARS = 480
MAX_TOTAL_CHARS = 4000
MAX_BODY_CHARS = 20000
MAX_SNIPPET_CHARS = 240
RRF_K = 60

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
KIND_RE = re.compile(r"^(?:human|agent|bot|orbit|hyvv|bundlebees):[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VAULT_PATH_RE = re.compile(r"^(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+\.md$")


# ---------------------------------------------------------------------------
# The gate-exact scanner-hygiene self-scan.
#
# Seven refusal rules, applied to every line of every leased file. The risky
# literals are built from fragments so the source of the scanner itself never
# carries a scannable shape.
# ---------------------------------------------------------------------------

def _cat(*parts: str) -> str:
    return "".join(parts)


GATE_RULE_1 = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9_])([A-Za-z0-9_.$/\"'-]*(?:token|secret|password|passwd|pwd"
    r"|api[_-]key|authorization))[ \t]*[:=]"
)
GATE_RULE_2 = re.compile(r"(?i)\bBearer[ \t]+(\S{6,})")
_PROVIDER_PREFIX = tuple(_cat(*parts) for parts in (("s", "k-"), ("gh", "p_"), ("github", "_pat_"), ("xo", "x")))
GATE_RULE_3 = re.compile(r"(?i)\b(?:" + "|".join(re.escape(p) for p in _PROVIDER_PREFIX) + r")")
_AWS_HEAD = _cat("A", "K", "I", "A")
_GOOGLE_HEAD = _cat("A", "I", "za")
GATE_RULE_4 = re.compile(r"\b" + _AWS_HEAD + r"[0-9A-Za-z]{16}|\b" + _GOOGLE_HEAD + r"[0-9A-Za-z_-]{20}")
_JWT_HEAD = _cat("ey", "J")
GATE_RULE_5 = re.compile(
    r"\b" + _JWT_HEAD + r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
)
GATE_RULE_6 = re.compile(r"[A-Za-z0-9]{32,}")
_PRIVKEY_HEAD = _cat("-", "-", "-", "-", "-", "BEGIN ")
_PRIVKEY_TAIL = _cat("-", "-", "-", "-", "-")
GATE_PRIVATE_KEY = re.compile(
    re.escape(_PRIVKEY_HEAD) + r"[A-Z ]*PRIVATE KEY" + re.escape(_PRIVKEY_TAIL)
)


def _long_run_hits(line: str) -> list:
    hits = []
    for match in GATE_RULE_6.finditer(line):
        run = match.group(0)
        if run != run.lower() and run != run.upper() and any(ch.isdigit() for ch in run):
            hits.append(("rule6-long-mixed-run", f"{len(run)} characters"))
    return hits


def scan_line(line: str) -> list:
    """Gate-exact scan of one line; returns a list of (rule, detail) hits."""
    line = line.rstrip("\n")
    hits = []
    if GATE_RULE_1.search(line):
        hits.append(("rule1-name-value-refusal-shape", GATE_RULE_1.search(line).group(1)))
    if GATE_RULE_2.search(line):
        hits.append(("rule2-bearer-shape", "matched"))
    if GATE_RULE_3.search(line):
        hits.append(("rule3-provider-prefix", GATE_RULE_3.search(line).group(0)))
    if GATE_RULE_4.search(line):
        hits.append(("rule4-cloud-credential-shape", "matched"))
    if GATE_RULE_5.search(line):
        hits.append(("rule5-jwt-triple", "matched"))
    hits.extend(_long_run_hits(line))
    if GATE_PRIVATE_KEY.search(line):
        hits.append(("rule7-private-key-block", "matched"))
    return hits


def scan_file(path: Path) -> list:
    problems = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        for rule, detail in scan_line(line):
            problems.append(f"{path.relative_to(ROOT)}:{lineno} {rule} {detail}")
    return problems


# Runtime-built trip probes: each trips exactly its own rule when scanned as a
# line, while the source lines above stay clean.
TRIP_NAME_VALUE = _cat("stale_", "token", ": ", "9f8e7d6c")
TRIP_BEARER = _cat("Bear", "er ", "deadbeefcafe")
TRIP_PROVIDER = _cat("s", "k-", "abcdef0123", "Abc")
TRIP_LONG_RUN = "a" * 11 + "B" * 11 + "9" * 12
TRIP_JWT = _cat("ey", "J", "a" * 9 + "1", ".", "B" * 9 + "2", ".", "c" * 9 + "3")
TRIP_AKIA = _cat("A", "K", "I", "A") + "B" * 16
TRIP_PRIVATE_KEY = _cat("-", "-", "-", "-", "-", "BEGIN ", "PRIVATE KEY", "-", "-", "-", "-", "-")

CLEAN_LINES = (
    "sha: 64 lowercase hex characters",
    "expected_sha must match the digest the reader stored",
    "the lease payload carries typed memory excerpts",
)


# ---------------------------------------------------------------------------
# The contract oracle: reference behavior for rizzstack.memory/1.
# ---------------------------------------------------------------------------


class ContractError(Exception):
    """A write, read or payload refused by one named contract rule."""

    def __init__(self, code: str, message: str, fix: str = "", reread: bool = False, current_sha: str = None) -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix
        self.reread_required = reread
        self.current_sha = current_sha

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "fix": self.fix}


def refuse(code: str, message: str, fix: str = "", reread: bool = False, current_sha: str = None) -> None:
    raise ContractError(code, message, fix, reread=reread, current_sha=current_sha)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def memory_sha(record: dict, body: str) -> str:
    """The memory digest: sha256 over the canonical frontmatter (without the
    digest field itself) plus a newline plus the markdown body. Any consumer
    can recompute it; it rotates on every content change."""
    core = {key: value for key, value in record.items() if key != "sha"}
    payload = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n" + body
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_frontmatter(record: dict) -> dict:
    if not isinstance(record, dict):
        refuse("schema_invalid", "the frontmatter record must be an object", "Pass the parsed frontmatter mapping.")
    allowed = {"schema", "id", "type", "created", "modified", "retention", "sources", "sha"}
    missing = sorted(allowed - set(record))
    extra = sorted(set(record) - allowed)
    if missing:
        refuse("schema_invalid", f"missing frontmatter fields: {', '.join(missing)}")
    if extra:
        refuse("schema_invalid", f"unknown frontmatter fields: {', '.join(extra)}")
    if record["schema"] != CONTRACT:
        refuse("schema_invalid", f"schema must be {CONTRACT}")
    if not isinstance(record["id"], str) or not ID_RE.match(record["id"]):
        refuse("schema_invalid", "id must be a lowercase kebab slug of at most 80 characters")
    if record["type"] not in MEMORY_TYPES:
        refuse("unknown_type", f"type must be one of {', '.join(MEMORY_TYPES)}")
    for field in ("created", "modified"):
        value = record[field]
        if not isinstance(value, str) or not TIME_RE.match(value):
            refuse("schema_invalid", f"{field} must be an RFC 3339 timestamp with seconds")
    ret = record["retention"]
    if not isinstance(ret, dict) or set(ret) != {"policy", "expires", "superseded_by"}:
        refuse("schema_invalid", "retention must carry exactly policy, expires and superseded_by")
    if ret["policy"] not in TYPE_POLICY.values():
        refuse("unknown_policy", f"unknown retention policy: {ret['policy']!r}")
    if ret["policy"] != TYPE_POLICY[record["type"]]:
        refuse("policy_mismatch", f"type {record['type']} must use policy {TYPE_POLICY[record['type']]}")
    expires = ret["expires"]
    if expires is not None and (not isinstance(expires, str) or not TIME_RE.match(expires)):
        refuse("schema_invalid", "retention.expires must be null or an RFC 3339 timestamp")
    superseded = ret["superseded_by"]
    if superseded is not None and (not isinstance(superseded, str) or not ID_RE.match(superseded)):
        refuse("schema_invalid", "retention.superseded_by must be null or a memory id")
    if ret["policy"] == "decision-permanent" and expires is not None:
        refuse("policy_mismatch", "a decision never auto-expires; supersede it instead")
    if ret["policy"] == "learning-until-superseded" and expires is not None:
        refuse("policy_mismatch", "a learning persists until superseded; do not set expires")
    if ret["policy"] == "reference-refresh" and expires is None:
        refuse("policy_mismatch", "a reference must carry a re-verify deadline")
    if parse_time(record["created"]) > parse_time(record["modified"]):
        refuse("schema_invalid", "created must not be after modified")
    sources = record["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 12:
        refuse("schema_invalid", "sources must be a list of one to twelve entries")
    for source in sources:
        if not isinstance(source, dict) or not {"kind", "ref"} <= set(source) or set(source) - {"kind", "ref", "note"}:
            refuse("schema_invalid", "each source carries kind and ref, plus an optional note")
        if source["kind"] not in SOURCE_KINDS:
            refuse("schema_invalid", f"unknown source kind: {source['kind']!r}")
        if not isinstance(source["ref"], str) or not 1 <= len(source["ref"]) <= 300:
            refuse("schema_invalid", "source ref must be a string of 1 to 300 characters")
        note = source.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 300):
            refuse("schema_invalid", "source note must be at most 300 characters")
    sha = record["sha"]
    if not isinstance(sha, str) or not SHA_RE.match(sha):
        refuse("schema_invalid", "sha must be 64 lowercase hex characters")
    return record


def validate_write_op(op: dict) -> dict:
    if not isinstance(op, dict):
        refuse("schema_invalid", "a write operation must be an object")
    if set(op) != {"op", "writer", "path", "memory", "body", "expected_sha", "authority"}:
        refuse("schema_invalid", "a write operation carries op, writer, path, memory, body, expected_sha and authority")
    if op["op"] != "write":
        refuse("schema_invalid", "op must be write")
    if not isinstance(op["writer"], str) or not KIND_RE.match(op["writer"]):
        refuse("schema_invalid", "writer must be a kind-prefixed id, for example agent:bee-7")
    path = op["path"]
    if not isinstance(path, str) or not VAULT_PATH_RE.match(path):
        refuse("schema_invalid", "path must be a vault-relative markdown path")
    if any(segment in (".", "..") for segment in path.split("/")):
        refuse("schema_invalid", "path segments must not be dot segments")
    body = op["body"]
    if not isinstance(body, str) or not 1 <= len(body) <= MAX_BODY_CHARS:
        refuse("schema_invalid", f"body must be 1 to {MAX_BODY_CHARS} characters")
    if not body.startswith("# "):
        refuse("schema_invalid", "a memory body starts with its level-1 title")
    expected = op["expected_sha"]
    if expected is not None and (not isinstance(expected, str) or not SHA_RE.match(expected)):
        refuse("schema_invalid", "expected_sha must be null or 64 lowercase hex characters")
    authority = op["authority"]
    if authority is not None:
        if not isinstance(authority, dict) or set(authority) != {"grant_ref", "approved_by", "approved_at"}:
            refuse("write_bad_grant", "an authority grant carries grant_ref, approved_by and approved_at")
        if not isinstance(authority["grant_ref"], str) or not 1 <= len(authority["grant_ref"]) <= 200:
            refuse("write_bad_grant", "grant_ref must name the approval record")
        if not isinstance(authority["approved_by"], str) or not KIND_RE.match(authority["approved_by"]):
            refuse("write_bad_grant", "approved_by must be a kind-prefixed id")
        if not isinstance(authority["approved_at"], str) or not TIME_RE.match(authority["approved_at"]):
            refuse("write_bad_grant", "approved_at must be an RFC 3339 timestamp")
    validate_frontmatter(op["memory"])
    return op


def zone_of(path: str) -> str:
    if path in CURATED_FILES or path.startswith(CURATED_PREFIXES):
        return "curated"
    if path.startswith(REVIEWED_PREFIXES):
        return "reviewed"
    if path.startswith(QUARANTINE_ROOT + "/"):
        return "open"
    return "service-owned"


def quarantine_prefix(writer: str) -> str:
    """A writer's own subtree: the writer id with the kind separator replaced."""
    return f"{QUARANTINE_ROOT}/{writer.replace(':', '-')}/"


class Vault:
    """Reference behavior for the read/query/write surface. In-memory; a real
    service stores the same shapes on disk in the vault layout."""

    def __init__(self) -> None:
        self.files: dict = {}
        self.log: list = []

    def write(self, op: dict) -> dict:
        validate_write_op(op)
        writer, path = op["writer"], op["path"]
        record, body = op["memory"], op["body"]
        if zone_of(path) == "service-owned":
            refuse("service_owned", f"{path} is maintained by the vault service, not by write operations")
        authority = op["authority"]
        if authority is None:
            if not path.startswith(quarantine_prefix(writer)):
                refuse(
                    "write_quarantined",
                    "without an authority grant a writer may only write its own quarantine subtree",
                    f"Write under {quarantine_prefix(writer)} or attach a grant.",
                )
        else:
            kind = authority["approved_by"].split(":", 1)[0]
            if kind not in GRANT_APPROVER_KINDS:
                refuse("write_bad_grant", f"grants are approved by one of {', '.join(GRANT_APPROVER_KINDS)}")
            if zone_of(path) == "curated" and kind != "human":
                refuse("write_bad_grant", "curated zones require a grant approved by a human")
        head = path.split("/", 1)[0] if "/" in path else ""
        if head in TYPE_DIR.values() and head != TYPE_DIR[record["type"]]:
            refuse("schema_invalid", f"type {record['type']} lives under {TYPE_DIR[record['type']]}/")
        if record["sha"] != memory_sha(record, body):
            refuse("sha_mismatch", "the frontmatter digest does not match this record and body", "Recompute the digest.")
        existing = self.files.get(path)
        if existing is None:
            if op["expected_sha"] is not None:
                refuse("sha_conflict", "the target does not exist; re-read and create without a digest", reread=True)
            if any(entry["record"]["id"] == record["id"] for entry in self.files.values()):
                refuse("duplicate_id", "this memory id already exists elsewhere in the vault")
        else:
            stored = existing["record"]["sha"]
            if op["expected_sha"] is None:
                refuse("sha_conflict", "an update needs the digest of the version you read", reread=True, current_sha=stored)
            elif op["expected_sha"] != stored:
                refuse("sha_conflict", "your digest is stale; the memory changed under you", reread=True, current_sha=stored)
            if existing["record"]["id"] != record["id"]:
                refuse("id_mismatch", "the path holds a different memory id")
        self.files[path] = {"record": copy.deepcopy(record), "body": body}
        seq = len(self.log) + 1
        self.log.append(
            {
                "seq": seq,
                "at": record["modified"],
                "writer": writer,
                "path": path,
                "id": record["id"],
                "sha": record["sha"],
                "granted": authority is not None,
            }
        )
        return {"accepted": True, "id": record["id"], "sha": record["sha"], "path": path, "log_seq": seq}

    def write_envelope(self, op: dict) -> dict:
        """The refusal envelope a coordinator can relay without unpacking an
        exception: accepted false, a code, and the re-read requirement."""
        try:
            return self.write(op)
        except ContractError as err:
            return {
                "accepted": False,
                "code": err.code,
                "message": err.message,
                "reread_required": err.reread_required,
                "current_sha": err.current_sha,
            }

    def read(self, path: str) -> dict:
        entry = self.files.get(path)
        if entry is None:
            refuse("not_found", f"no memory at {path}")
        return copy.deepcopy(entry)

    def active_records(self, now: str, include_expired: bool = False) -> list:
        records = [entry["record"] for entry in self.files.values()]
        if include_expired:
            return records
        return [record for record in records if not is_expired(record, now)]


def is_expired(record: dict, now: str) -> bool:
    """A memory is expired when it was superseded or its deadline passed.
    The per-type policy decides who sets those fields and when."""
    ret = record["retention"]
    if ret.get("superseded_by"):
        return True
    expires = ret.get("expires")
    if expires and parse_time(expires) <= parse_time(now):
        return True
    return False


def resolve_mode(requested: str, has_fts5: bool, has_embeddings: bool) -> str:
    """The fallback chain: hybrid needs both engines, semantic needs
    embeddings, keyword needs the index, grep (ripgrep plus the wikilink
    index) is always available and never leaves the machine."""
    available = {
        "hybrid": has_fts5 and has_embeddings,
        "semantic": has_embeddings,
        "keyword": has_fts5,
        "grep": True,
    }
    if available.get(requested):
        return requested
    if has_fts5:
        return "keyword"
    return "grep"


def excerpt_of(body: str, cap: int) -> str:
    """The injected excerpt: the body without its title line, truncated to
    the cap with an ellipsis when cut."""
    lines = [line for line in body.splitlines()[1:] if line.strip()]
    text = " ".join(lines)
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "\u2026"


def inject_brief(ranked: list, caps: dict = None, vault_rev: str = "") -> dict:
    """Build the brief-injection payload from ranked candidates. Greedy fill:
    highest score first, stop at the item cap, skip a candidate whose excerpt
    would overflow the total budget and try the next smaller one."""
    caps = caps or {"max_items": MAX_ITEMS, "max_excerpt_chars": MAX_EXCERPT_CHARS, "max_total_chars": MAX_TOTAL_CHARS}
    items = []
    total = 0
    for entry in sorted(ranked, key=lambda item: item["score"], reverse=True):
        if len(items) >= caps["max_items"]:
            break
        record, body = entry["record"], entry["body"]
        excerpt = excerpt_of(body, caps["max_excerpt_chars"])
        if total + len(excerpt) > caps["max_total_chars"]:
            continue
        items.append(
            {
                "id": record["id"],
                "type": record["type"],
                "sha": record["sha"],
                "title": body.splitlines()[0][2:],
                "path": entry["path"],
                "excerpt": excerpt,
            }
        )
        total += len(excerpt)
    return {"contract": CONTRACT, "items": items, "caps": caps, "vault_rev": vault_rev}


def validate_injection(payload: dict) -> dict:
    if not isinstance(payload, dict):
        refuse("schema_invalid", "an injection payload must be an object")
    if set(payload) != {"contract", "items", "caps", "vault_rev"}:
        refuse("schema_invalid", "an injection payload carries contract, items, caps and vault_rev")
    if payload["contract"] != CONTRACT:
        refuse("schema_invalid", f"contract must be {CONTRACT}")
    caps = payload["caps"]
    if not isinstance(caps, dict) or set(caps) != {"max_items", "max_excerpt_chars", "max_total_chars"}:
        refuse("schema_invalid", "caps carry max_items, max_excerpt_chars and max_total_chars")
    if not all(isinstance(value, int) and value >= 1 for value in caps.values()):
        refuse("schema_invalid", "caps are positive integers")
    if caps["max_items"] > MAX_ITEMS or caps["max_excerpt_chars"] > MAX_EXCERPT_CHARS or caps["max_total_chars"] > MAX_TOTAL_CHARS:
        refuse("cap_exceeded", "caps must not exceed the contract defaults")
    items = payload["items"]
    if not isinstance(items, list):
        refuse("schema_invalid", "items must be a list")
    if len(items) > caps["max_items"]:
        refuse("cap_exceeded", f"at most {caps['max_items']} excerpts per brief")
    seen = set()
    total = 0
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "type", "sha", "title", "path", "excerpt"}:
            refuse("schema_invalid", "each excerpt carries id, type, sha, title, path and excerpt")
        if not ID_RE.match(item["id"]) or item["id"] in seen:
            refuse("schema_invalid", "excerpt ids are unique lowercase kebab slugs")
        seen.add(item["id"])
        if item["type"] not in MEMORY_TYPES:
            refuse("schema_invalid", f"unknown excerpt type: {item['type']!r}")
        if not SHA_RE.match(item["sha"]):
            refuse("schema_invalid", "each excerpt pins the digest of the memory it came from")
        if not isinstance(item["title"], str) or not 1 <= len(item["title"]) <= 200:
            refuse("schema_invalid", "excerpt title must be 1 to 200 characters")
        if not isinstance(item["path"], str) or not VAULT_PATH_RE.match(item["path"]):
            refuse("schema_invalid", "excerpt path must be a vault-relative markdown path")
        if not isinstance(item["excerpt"], str) or not 1 <= len(item["excerpt"]) <= caps["max_excerpt_chars"]:
            refuse("cap_exceeded", f"each excerpt is at most {caps['max_excerpt_chars']} characters")
        total += len(item["excerpt"])
    if total > caps["max_total_chars"]:
        refuse("cap_exceeded", f"excerpts total at most {caps['max_total_chars']} characters")
    if not isinstance(payload["vault_rev"], str) or not 1 <= len(payload["vault_rev"]) <= 128:
        refuse("schema_invalid", "vault_rev names the vault generation the excerpts were pinned against")
    return payload


def validate_query_op(op: dict) -> dict:
    if not isinstance(op, dict):
        refuse("schema_invalid", "a query operation must be an object")
    allowed = {"op", "q", "types", "k", "mode", "include_expired"}
    if not {"op", "q"} <= set(op) or set(op) - allowed:
        refuse("schema_invalid", "a query operation carries op and q, plus optional types, k, mode, include_expired")
    if op["op"] != "query":
        refuse("schema_invalid", "op must be query")
    if not isinstance(op["q"], str) or not 1 <= len(op["q"]) <= 500:
        refuse("schema_invalid", "q must be 1 to 500 characters")
    types = op.get("types")
    if types is not None:
        if not isinstance(types, list) or len(set(types)) != len(types) or not set(types) <= set(MEMORY_TYPES):
            refuse("schema_invalid", "types must be unique memory types")
    k = op.get("k", 8)
    if not isinstance(k, int) or not 1 <= k <= 25:
        refuse("schema_invalid", "k must be 1 to 25")
    mode = op.get("mode", "hybrid")
    if mode not in ("hybrid", "semantic", "keyword", "grep"):
        refuse("schema_invalid", "mode must be hybrid, semantic, keyword or grep")
    if op.get("include_expired") not in (None, False, True):
        refuse("schema_invalid", "include_expired must be a boolean")
    return op


def validate_query_result(result: dict) -> dict:
    if not isinstance(result, dict) or set(result) != {"op", "mode_used", "hits", "vault_rev"}:
        refuse("schema_invalid", "a query result carries op, mode_used, hits and vault_rev")
    if result["op"] != "query-result":
        refuse("schema_invalid", "op must be query-result")
    if result["mode_used"] not in ("hybrid", "semantic", "keyword", "grep"):
        refuse("schema_invalid", "mode_used must be an available engine")
    if not isinstance(result["hits"], list) or len(result["hits"]) > 25:
        refuse("schema_invalid", "hits is a list of at most 25 entries")
    for hit in result["hits"]:
        if not isinstance(hit, dict) or set(hit) != {"id", "type", "path", "title", "sha", "score", "snippet"}:
            refuse("schema_invalid", "each hit carries id, type, path, title, sha, score and snippet")
        if not ID_RE.match(hit["id"]) or hit["type"] not in MEMORY_TYPES:
            refuse("schema_invalid", "hit id and type must name a real memory")
        if not VAULT_PATH_RE.match(hit["path"]) or not SHA_RE.match(hit["sha"]):
            refuse("schema_invalid", "hit path and digest must be well-formed")
        if not isinstance(hit["score"], (int, float)) or isinstance(hit["score"], bool):
            refuse("schema_invalid", "hit score must be a number")
        if not isinstance(hit["snippet"], str) or len(hit["snippet"]) > MAX_SNIPPET_CHARS:
            refuse("schema_invalid", f"hit snippet is at most {MAX_SNIPPET_CHARS} characters")
    return result


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

LEARNING_PATH = "learnings/workbench-crash-resume.md"
QUARANTINE_PATH = quarantine_prefix(WRITER) + "workbench-crash-resume.md"
WORKED_BODY = (
    "# Workbench crash resume\n"
    "\n"
    "A workbench crash mid-wave leaves a stale lease behind.\n"
    "\n"
    "- Resume from the recovery digest, never from chat scrollback.\n"
    "- Re-read the lease file before dispatching the next wave.\n"
)


def base_record(**over) -> dict:
    record = {
        "schema": CONTRACT,
        "id": "workbench-crash-resume",
        "type": "learning",
        "created": NOW,
        "modified": NOW,
        "retention": {"policy": "learning-until-superseded", "expires": None, "superseded_by": None},
        "sources": [
            {
                "kind": "session-digest",
                "ref": "sessions/2026-11-14-workbench-crash.md",
                "note": "operator diagnosis narration",
            }
        ],
        "sha": "",
    }
    record.update(over)
    return record


def sealed(record: dict = None, body: str = None) -> dict:
    record = copy.deepcopy(record or base_record())
    body = WORKED_BODY if body is None else body
    record["sha"] = memory_sha(record, body)
    return record


def write_op(path=None, expected=None, authority=None, record=None, body=None, writer=WRITER) -> dict:
    return {
        "op": "write",
        "writer": writer,
        "path": LEARNING_PATH if path is None else path,
        "memory": record if record is not None else sealed(),
        "body": WORKED_BODY if body is None else body,
        "expected_sha": expected,
        "authority": authority,
    }


def grant(approved_by="human:owner", ref="approvals/2026-11-14-memory-promotion.md", at=LATER) -> dict:
    return {"grant_ref": ref, "approved_by": approved_by, "approved_at": at}


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


class ContractConstantsTests(unittest.TestCase):
    def test_every_type_has_a_dir_and_a_policy(self):
        self.assertEqual(set(TYPE_DIR), set(MEMORY_TYPES))
        self.assertEqual(set(TYPE_POLICY), set(MEMORY_TYPES))
        self.assertEqual(sorted(VAULT_DIRS), sorted(list(TYPE_DIR.values()) + ["sessions"]))

    def test_the_worked_example_seals_to_itself(self):
        record = sealed()
        self.assertEqual(record["sha"], memory_sha(record, WORKED_BODY))


class FrontmatterTests(unittest.TestCase):
    def test_the_worked_example_validates(self):
        self.assertEqual(validate_frontmatter(sealed())["type"], "learning")

    def test_every_type_validates_with_its_own_policy(self):
        for i, memory_type in enumerate(MEMORY_TYPES):
            record = base_record(
                id=f"fixture-{i:02d}",
                type=memory_type,
                retention={"policy": TYPE_POLICY[memory_type], "expires": None, "superseded_by": None},
            )
            if memory_type == "reference":
                record["retention"]["expires"] = LATER
            validate_frontmatter(sealed(record))

    def test_missing_and_extra_fields_are_refused(self):
        for drop in ("created", "sources", "retention", "sha"):
            record = base_record()
            record.pop(drop)
            with self.assertRaises(ContractError) as caught:
                validate_frontmatter(record)
            self.assertEqual(caught.exception.code, "schema_invalid")
        with self.assertRaises(ContractError):
            validate_frontmatter({**base_record(), "title": "extra"})

    def test_unknown_type_and_policy_are_refused(self):
        with self.assertRaises(ContractError) as caught:
            validate_frontmatter(base_record(type="opinion"))
        self.assertEqual(caught.exception.code, "unknown_type")
        with self.assertRaises(ContractError) as caught:
            validate_frontmatter(base_record(retention={"policy": "burn-after-reading", "expires": None, "superseded_by": None}))
        self.assertEqual(caught.exception.code, "unknown_policy")

    def test_type_policy_pairing_is_refused(self):
        with self.assertRaises(ContractError) as caught:
            validate_frontmatter(base_record(retention={"policy": "decision-permanent", "expires": None, "superseded_by": None}))
        self.assertEqual(caught.exception.code, "policy_mismatch")

    def test_retention_shape_rules(self):
        with self.assertRaises(ContractError) as caught:
            validate_frontmatter(base_record(retention={"policy": "decision-permanent", "expires": LATER, "superseded_by": None}, type="decision"))
        self.assertEqual(caught.exception.code, "policy_mismatch")
        with self.assertRaises(ContractError) as caught:
            validate_frontmatter(base_record(type="reference", retention={"policy": "reference-refresh", "expires": None, "superseded_by": None}))
        self.assertEqual(caught.exception.code, "policy_mismatch")

    def test_bad_digest_and_bad_time_are_refused(self):
        with self.assertRaises(ContractError):
            validate_frontmatter(base_record(sha="not-a-digest"))
        with self.assertRaises(ContractError):
            validate_frontmatter(base_record(created="2026-11-14 18:20:00"))

    def test_sources_must_name_provenance(self):
        with self.assertRaises(ContractError):
            validate_frontmatter(base_record(sources=[]))
        with self.assertRaises(ContractError):
            validate_frontmatter(base_record(sources=[{"kind": "chat-scrollback", "ref": "x"}]))


class DigestTests(unittest.TestCase):
    def test_the_digest_is_deterministic(self):
        self.assertEqual(memory_sha(sealed(), WORKED_BODY), memory_sha(sealed(), WORKED_BODY))

    def test_a_body_edit_rotates_the_digest(self):
        first = memory_sha(sealed(), WORKED_BODY)
        second = memory_sha(sealed(), WORKED_BODY + "\n- One more lesson.\n")
        self.assertNotEqual(first, second)

    def test_a_frontmatter_edit_rotates_the_digest(self):
        record = sealed()
        moved = copy.deepcopy(record)
        moved["modified"] = LATER
        self.assertNotEqual(record["sha"], memory_sha(moved, WORKED_BODY))

    def test_the_digest_field_is_out_of_the_digest(self):
        record = sealed()
        tampered = {**record, "sha": "0" * 64}
        self.assertEqual(memory_sha(record, WORKED_BODY), memory_sha(tampered, WORKED_BODY))


class ShaGuardTests(unittest.TestCase):
    def test_create_then_update_with_a_fresh_digest(self):
        vault = Vault()
        first = vault.write(write_op(path=QUARANTINE_PATH))
        self.assertTrue(first["accepted"])
        record = sealed()
        record["modified"] = LATER
        record["sha"] = memory_sha(record, WORKED_BODY)
        second = vault.write(write_op(path=QUARANTINE_PATH, expected=first["sha"], record=record))
        self.assertEqual(second["sha"], record["sha"])
        self.assertEqual(len(vault.log), 2)

    def test_a_stale_digest_is_refused_with_a_reread_requirement(self):
        vault = Vault()
        first = vault.write(write_op(path=QUARANTINE_PATH))
        record = sealed()
        record["modified"] = LATER
        record["sha"] = memory_sha(record, WORKED_BODY)
        envelope = vault.write_envelope(
            write_op(path=QUARANTINE_PATH, expected="1" * 64, record=record, authority=grant())
        )
        self.assertFalse(envelope["accepted"])
        self.assertEqual(envelope["code"], "sha_conflict")
        self.assertTrue(envelope["reread_required"])
        self.assertEqual(envelope["current_sha"], first["sha"])

    def test_two_writers_conflict_on_one_memory(self):
        vault = Vault()
        writer_a = WRITER
        writer_b = "agent:bee-9"
        path = QUARANTINE_PATH
        first = vault.write(write_op(path=path, writer=writer_a))
        record = sealed()
        record["modified"] = LATER
        record["sha"] = memory_sha(record, WORKED_BODY)
        second = vault.write(write_op(path=path, writer=writer_a, expected=first["sha"], record=record))
        stale = sealed()
        stale["modified"] = "2026-11-14T19:00:00Z"
        stale["sha"] = memory_sha(stale, WORKED_BODY)
        envelope = vault.write_envelope(
            write_op(path=path, writer=writer_b, expected=first["sha"], record=stale, authority=grant())
        )
        self.assertEqual(envelope["code"], "sha_conflict")
        self.assertTrue(envelope["reread_required"])
        self.assertEqual(envelope["current_sha"], second["sha"])

    def test_a_blind_overwrite_is_refused(self):
        vault = Vault()
        vault.write(write_op(path=QUARANTINE_PATH))
        envelope = vault.write_envelope(write_op(path=QUARANTINE_PATH, expected=None))
        self.assertEqual(envelope["code"], "sha_conflict")
        self.assertTrue(envelope["reread_required"])

    def test_a_create_with_a_digest_is_refused_and_duplicates_are_refused(self):
        vault = Vault()
        envelope = vault.write_envelope(write_op(path=QUARANTINE_PATH, expected="0" * 64))
        self.assertEqual(envelope["code"], "sha_conflict")
        vault.write(write_op(path=QUARANTINE_PATH))
        twin = sealed()
        twin["sha"] = memory_sha(twin, WORKED_BODY)
        envelope = vault.write_envelope(write_op(path=QUARANTINE_PATH + ".twin.md", record=twin))
        self.assertEqual(envelope["code"], "duplicate_id")

    def test_a_self_inconsistent_digest_is_refused(self):
        vault = Vault()
        envelope = vault.write_envelope(write_op(path=QUARANTINE_PATH, record=base_record(sha="0" * 64)))
        self.assertEqual(envelope["code"], "sha_mismatch")


class QuarantineTests(unittest.TestCase):
    def test_a_writer_may_write_its_own_subtree(self):
        vault = Vault()
        result = vault.write(write_op(path=quarantine_prefix("agent:bee-7") + "notes.md"))
        self.assertTrue(result["accepted"])

    def test_an_ungranted_write_outside_the_subtree_is_quarantined(self):
        vault = Vault()
        envelope = vault.write_envelope(write_op())
        self.assertEqual(envelope["code"], "write_quarantined")

    def test_another_writers_subtree_is_not_yours(self):
        vault = Vault()
        envelope = vault.write_envelope(write_op(path=quarantine_prefix("agent:bee-9") + "notes.md"))
        self.assertEqual(envelope["code"], "write_quarantined")

    def test_a_grant_opens_reviewed_zones(self):
        vault = Vault()
        result = vault.write(write_op(authority=grant(approved_by="orbit:coordinator")))
        self.assertTrue(result["accepted"])
        self.assertTrue(vault.log[-1]["granted"])

    def test_curated_zones_require_a_human_grant(self):
        curated_records = {
            "concepts/retrieval-basics.md": sealed(
                base_record(
                    id="retrieval-basics",
                    type="reference",
                    retention={"policy": "reference-refresh", "expires": LATER, "superseded_by": None},
                )
            ),
            "decisions/vault-zones.md": sealed(
                base_record(id="vault-zones", type="decision", retention={"policy": "decision-permanent", "expires": None, "superseded_by": None})
            ),
            "hot.md": sealed(base_record(id="always-resume-from-digest")),
            "index.md": sealed(
                base_record(
                    id="vault-index",
                    type="reference",
                    retention={"policy": "reference-refresh", "expires": LATER, "superseded_by": None},
                )
            ),
        }
        vault = Vault()
        for path, record in curated_records.items():
            envelope = vault.write_envelope(
                write_op(path=path, record=record, authority=grant(approved_by="orbit:coordinator"))
            )
            self.assertEqual(envelope["code"], "write_bad_grant", path)
            human = vault.write(write_op(path=path, record=record, authority=grant()))
            self.assertTrue(human["accepted"], path)

    def test_service_owned_files_are_refused(self):
        vault = Vault()
        for path in ("log.md", "VAULT.md", "sessions/2026-11-14-workbench-crash.md"):
            envelope = vault.write_envelope(write_op(path=path, authority=grant()))
            self.assertEqual(envelope["code"], "service_owned", path)

    def test_dir_mismatch_and_dot_segments_are_refused(self):
        vault = Vault()
        envelope = vault.write_envelope(write_op(path="decisions/workbench-crash-resume.md", authority=grant()))
        self.assertEqual(envelope["code"], "schema_invalid")
        envelope = vault.write_envelope(write_op(path=quarantine_prefix("agent:bee-7") + "../escape.md"))
        self.assertEqual(envelope["code"], "schema_invalid")


class InjectionTests(unittest.TestCase):
    def ranked(self, count: int) -> list:
        ranked = []
        for i in range(count):
            record = sealed(base_record(id=f"memory-{i:02d}", type="pitfall", retention={"policy": "pitfall-until-fixed", "expires": None, "superseded_by": None}))
            ranked.append({"record": record, "body": WORKED_BODY, "path": f"pitfalls/memory-{i:02d}.md", "score": count - i})
        return ranked

    def test_the_worked_example_payload_validates(self):
        payload = inject_brief(self.ranked(3), vault_rev="gen-1")
        self.assertEqual(validate_injection(payload), payload)
        self.assertEqual(len(payload["items"]), 3)
        self.assertEqual(payload["items"][0]["id"], "memory-00")

    def test_the_item_cap_holds(self):
        payload = inject_brief(self.ranked(12), vault_rev="gen-1")
        self.assertEqual(len(payload["items"]), MAX_ITEMS)
        validate_injection(payload)

    def test_excerpts_are_size_capped(self):
        long_body = "# Long tail\n" + ("A long confirmed observation. " * 60) + "\n"
        record = sealed(body=long_body)
        record["sha"] = memory_sha(record, long_body)
        payload = inject_brief([{"record": record, "body": long_body, "path": LEARNING_PATH, "score": 1}], vault_rev="gen-1")
        for item in payload["items"]:
            self.assertLessEqual(len(item["excerpt"]), MAX_EXCERPT_CHARS)
        validate_injection(payload)

    def test_the_total_budget_holds_and_small_items_fill_the_gap(self):
        ranked = []
        for i in range(40):
            body = "# Filler\n" + ("x" * 300) + "\n"
            record = sealed(base_record(id=f"filler-{i:02d}"), body)
            record["sha"] = memory_sha(record, body)
            ranked.append({"record": record, "body": body, "path": f"learnings/filler-{i:02d}.md", "score": 40 - i})
        payload = inject_brief(ranked, vault_rev="gen-1")
        total = sum(len(item["excerpt"]) for item in payload["items"])
        self.assertLessEqual(total, MAX_TOTAL_CHARS)
        validate_injection(payload)

    def test_oversized_caps_are_refused(self):
        payload = inject_brief(self.ranked(1), vault_rev="gen-1")
        payload["caps"]["max_items"] = MAX_ITEMS + 1
        with self.assertRaises(ContractError) as caught:
            validate_injection(payload)
        self.assertEqual(caught.exception.code, "cap_exceeded")

    def test_every_excerpt_is_digest_pinned(self):
        payload = inject_brief(self.ranked(2), vault_rev="gen-1")
        for item in payload["items"]:
            self.assertTrue(SHA_RE.match(item["sha"]))
            self.assertTrue(VAULT_PATH_RE.match(item["path"]))


class ExpiryTests(unittest.TestCase):
    def record_for(self, memory_type: str, **retention) -> dict:
        record = base_record(
            type=memory_type,
            retention={"policy": TYPE_POLICY[memory_type], "expires": None, "superseded_by": None, **retention},
        )
        return sealed(record)

    def test_decisions_persist_until_superseded(self):
        record = self.record_for("decision")
        self.assertFalse(is_expired(record, "2027-11-14T18:20:00Z"))
        superseded = self.record_for("decision", superseded_by="newer-decision")
        self.assertTrue(is_expired(superseded, NOW))

    def test_learnings_persist_until_superseded(self):
        record = self.record_for("learning")
        self.assertFalse(is_expired(record, "2027-11-14T18:20:00Z"))
        self.assertTrue(is_expired(self.record_for("learning", superseded_by="newer-learning"), NOW))

    def test_env_facts_expire_on_fix(self):
        record = self.record_for("env-fact")
        self.assertFalse(is_expired(record, LATER))
        fixed = self.record_for("env-fact", superseded_by="env-fact-after-fix")
        self.assertTrue(is_expired(fixed, NOW))
        self.assertTrue(is_expired(self.record_for("env-fact", expires=NOW), LATER))

    def test_pitfalls_expire_when_the_fix_lands(self):
        record = self.record_for("pitfall")
        self.assertFalse(is_expired(record, LATER))
        self.assertTrue(is_expired(self.record_for("pitfall", expires=NOW), LATER))

    def test_project_states_expire_on_completion(self):
        record = self.record_for("project-state")
        self.assertFalse(is_expired(record, LATER))
        self.assertTrue(is_expired(self.record_for("project-state", expires=NOW), LATER))

    def test_references_expire_at_their_reverify_deadline(self):
        record = self.record_for("reference", expires="2026-12-01T00:00:00Z")
        self.assertFalse(is_expired(record, LATER))
        self.assertTrue(is_expired(record, "2026-12-02T00:00:00Z"))

    def test_query_defaults_hide_expired_memories(self):
        vault = Vault()
        vault.write(write_op(path=quarantine_prefix(WRITER) + "a.md"))
        stale = self.record_for("reference", expires=NOW)
        stale["id"] = "stale-reference"
        stale["sha"] = memory_sha(stale, WORKED_BODY)
        vault.write(write_op(path=quarantine_prefix(WRITER) + "stale.md", record=stale))
        self.assertEqual(len(vault.active_records(LATER)), 1)
        self.assertEqual(len(vault.active_records(LATER, include_expired=True)), 2)


class RetrievalFallbackTests(unittest.TestCase):
    def test_hybrid_needs_both_engines(self):
        self.assertEqual(resolve_mode("hybrid", True, True), "hybrid")
        self.assertEqual(resolve_mode("hybrid", True, False), "keyword")
        self.assertEqual(resolve_mode("hybrid", False, False), "grep")

    def test_semantic_needs_embeddings(self):
        self.assertEqual(resolve_mode("semantic", False, True), "semantic")
        self.assertEqual(resolve_mode("semantic", True, False), "keyword")
        self.assertEqual(resolve_mode("semantic", False, False), "grep")

    def test_keyword_falls_back_to_ripgrep(self):
        self.assertEqual(resolve_mode("keyword", True, False), "keyword")
        self.assertEqual(resolve_mode("keyword", False, True), "grep")

    def test_grep_is_always_available(self):
        self.assertEqual(resolve_mode("grep", False, False), "grep")
        self.assertEqual(resolve_mode("grep", True, True), "grep")

    def test_query_shapes_validate(self):
        validate_query_op({"op": "query", "q": "workbench crash resume"})
        validate_query_op({"op": "query", "q": "lease", "types": ["learning", "pitfall"], "k": 5, "mode": "keyword"})
        with self.assertRaises(ContractError):
            validate_query_op({"op": "query", "q": ""})
        with self.assertRaises(ContractError):
            validate_query_op({"op": "query", "q": "lease", "k": 99})
        result = {
            "op": "query-result",
            "mode_used": "hybrid",
            "vault_rev": "gen-1",
            "hits": [
                {
                    "id": "workbench-crash-resume",
                    "type": "learning",
                    "path": LEARNING_PATH,
                    "title": "Workbench crash resume",
                    "sha": sealed()["sha"],
                    "score": 0.83,
                    "snippet": "A workbench crash mid-wave leaves a stale lease behind.",
                }
            ],
        }
        validate_query_result(result)
        with self.assertRaises(ContractError):
            validate_query_result({**result, "mode_used": "telepathy"})


class VaultSelfDescriptionTests(unittest.TestCase):
    def test_the_rulebook_is_the_first_thing_a_consumer_reads(self):
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        first_rulebook = re.search(r"VAULT\.md", text)
        self.assertIsNotNone(first_rulebook)
        self.assertIn("first", text[first_rulebook.start() - 200 : first_rulebook.end() + 200].lower())

    def test_the_doc_documents_the_whole_layout(self):
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        for name in VAULT_DIRS + VAULT_ROOT_FILES:
            self.assertIn(name, text, name)

    def test_the_doc_documents_types_policies_and_caps(self):
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        for name in MEMORY_TYPES + tuple(TYPE_POLICY.values()):
            self.assertIn(name, text, name)
        for cap, value in (("max_items", MAX_ITEMS), ("max_excerpt_chars", MAX_EXCERPT_CHARS), ("max_total_chars", MAX_TOTAL_CHARS)):
            self.assertRegex(text, re.escape(cap) + r"[\s\S]{0,80}" + str(value) + r"\b", cap)

    def test_the_doc_documents_the_retrieval_stack(self):
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        for needle in ("FTS5", "RRF", "reciprocal", "ripgrep", str(RRF_K), "embedding"):
            self.assertIn(needle, text, needle)

    def test_the_worked_example_is_in_the_doc(self):
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        for needle in ("workbench-crash-resume", "memory_context", "recovery digest"):
            self.assertIn(needle, text, needle)

    def test_the_gaps_table_exists(self):
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        self.assertIn("design-only", text.lower())
        self.assertIn("implemented", text.lower())


class ProtocolMapTests(unittest.TestCase):
    def test_the_map_gains_the_memory_row(self):
        text = PROTOCOL_DOC.read_text(encoding="utf-8")
        for needle in (CONTRACT, "schemas/memory-schema.v1.json", "docs/memory-contract.md", "tests/test_memory_contract.py"):
            self.assertIn(needle, text, needle)

    def test_every_schema_named_in_the_map_exists(self):
        text = PROTOCOL_DOC.read_text(encoding="utf-8")
        for name in sorted(set(re.findall(r"schemas/[A-Za-z0-9._-]+\.json", text))):
            self.assertTrue((ROOT / name).exists(), name)


class ScannerHygieneTests(unittest.TestCase):
    def test_leased_files_are_clean(self):
        problems = []
        for path in LEASE_FILES:
            problems.extend(scan_file(path))
        self.assertEqual(problems, [])

    def test_the_gate_catches_the_refusal_shapes(self):
        expected = {
            TRIP_NAME_VALUE: "rule1",
            TRIP_BEARER: "rule2",
            TRIP_PROVIDER: "rule3",
            TRIP_LONG_RUN: "rule6",
            TRIP_JWT: "rule5",
            TRIP_AKIA: "rule4",
            TRIP_PRIVATE_KEY: "rule7",
        }
        for line, rule in expected.items():
            rules = {name for name, _ in scan_line(line)}
            self.assertTrue(any(name.startswith(rule) for name in rules), (rule, line))

    def test_structural_shapes_that_are_not_secrets_stay_clean(self):
        for line in CLEAN_LINES:
            self.assertEqual(scan_line(line), [], line)

    def test_the_trip_probes_are_not_in_any_leased_file(self):
        for path in LEASE_FILES:
            text = path.read_text(encoding="utf-8")
            for probe in (TRIP_NAME_VALUE, TRIP_BEARER, TRIP_PROVIDER, TRIP_LONG_RUN, TRIP_JWT, TRIP_AKIA, TRIP_PRIVATE_KEY):
                self.assertNotIn(probe, text, probe)


@unittest.skipUnless(jsonschema, "jsonschema is not installed")
class JsonschemaCrossCheck(unittest.TestCase):
    """When jsonschema is installed the hand oracle must agree with the
    published schema: accept fixtures pass, shape-level refusals fail."""

    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        resource = Resource.from_contents(cls.schema)
        cls.registry = Registry().with_resource(cls.schema["$id"], resource)

    def validator(self, pointer: str):
        return jsonschema.Draft202012Validator({"$ref": self.schema["$id"] + pointer}, registry=self.registry)

    def validate(self, pointer: str, instance) -> list:
        return sorted(f"{e.json_path}: {e.message}" for e in self.validator(pointer).iter_errors(instance))

    def test_the_root_schema_is_the_frontmatter_record(self):
        self.assertEqual(self.schema["title"].count(CONTRACT), 1)
        self.assertEqual(self.validate("#", sealed()), [])
        for i, memory_type in enumerate(MEMORY_TYPES):
            record = base_record(id=f"fixture-{i:02d}", type=memory_type, retention={"policy": TYPE_POLICY[memory_type], "expires": None, "superseded_by": None})
            if memory_type == "reference":
                record["retention"]["expires"] = LATER
            self.assertEqual(self.validate("#", sealed(record)), [], memory_type)

    def test_shape_refusals_match_the_hand_oracle(self):
        cases = [
            ("missing sha", {key: value for key, value in sealed().items() if key != "sha"}),
            ("unknown field", {**sealed(), "title": "extra"}),
            ("unknown type", base_record(type="opinion", sha="0" * 64)),
            ("policy mismatch", base_record(retention={"policy": "decision-permanent", "expires": None, "superseded_by": None}, sha="0" * 64)),
            ("bad digest", base_record(sha="0" * 63)),
            ("decision with a deadline", base_record(type="decision", retention={"policy": "decision-permanent", "expires": LATER, "superseded_by": None}, sha="0" * 64)),
            ("learning with a deadline", base_record(retention={"policy": "learning-until-superseded", "expires": LATER, "superseded_by": None}, sha="0" * 64)),
            ("reference without a deadline", base_record(type="reference", retention={"policy": "reference-refresh", "expires": None, "superseded_by": None}, sha="0" * 64)),
        ]
        for name, record in cases:
            with self.subTest(case=name):
                self.assertTrue(self.validate("#", record), name)

    def test_write_ops_validate(self):
        self.assertEqual(self.validate("#/$defs/write-op", write_op(path=quarantine_prefix("agent:bee-7") + "notes.md")), [])
        granted = write_op(authority=grant())
        self.assertEqual(self.validate("#/$defs/write-op", granted), [])
        bad = write_op(writer="bee-9")
        self.assertTrue(self.validate("#/$defs/write-op", bad))

    def test_query_and_injection_defs_validate(self):
        self.assertEqual(self.validate("#/$defs/query-op", {"op": "query", "q": "lease"}), [])
        payload = inject_brief([], vault_rev="gen-1")
        self.assertEqual(self.validate("#/$defs/injection", payload), [])


if __name__ == "__main__":
    unittest.main()
