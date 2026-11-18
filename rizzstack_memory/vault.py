"""Disk-backed vault service for the ``rizzstack.memory/1`` contract.

The vault is a plain, Obsidian-compatible markdown directory: one file per
memory at ``<type-dir>/<id>.md`` with YAML frontmatter, plus the service-owned
rulebook (``VAULT.md``), the curated root files (``index.md``, ``hot.md``) and
the append-only receipt log (``log.md``).

This slice implements a local, dependency-free engine:

* ``write`` / ``write_envelope``  validate and persist one memory, appending an
  fsynced receipt to ``log.md`` and returning the durable sequence number;
* ``read``                        parses a memory and warns on ``expected_sha``
  drift;
* ``query``                       scans the markdown files locally and always
  reports ``mode_used: grep`` (no FTS5 index, no embeddings, no network);
* ``active_records``              evaluates the per-type retention policy.

``vault_rev`` is derived from the durable receipt counter as ``gen-<n>`` so it
survives restarts and never moves backwards.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

CONTRACT = "rizzstack.memory/1"

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

_SCALAR_SAFE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@+-]*$")
_SCALAR_RESERVED = frozenset({"null", "~", "true", "false", "yes", "no", "on", "off"})
_FRONTMATTER_KEYS = ("schema", "id", "type", "created", "modified")


class ContractError(Exception):
    """A read, query or write refused by one named contract rule."""

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
    """sha256 over canonical frontmatter (sans sha), a newline, then the body."""
    core = {key: value for key, value in record.items() if key != "sha"}
    payload = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n" + body
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Frontmatter: a deterministic YAML subset, parsed without PyYAML.
# ---------------------------------------------------------------------------


def _dump_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        refuse("schema_invalid", "frontmatter values must be strings, numbers, booleans or null")
    if _SCALAR_SAFE_RE.match(value) and value.lower() not in _SCALAR_RESERVED:
        return value
    return json.dumps(value, ensure_ascii=True)


def _parse_scalar(text: str):
    text = text.strip()
    if text in ("null", "~"):
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith('"'):
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            refuse("schema_invalid", "a quoted frontmatter value is not valid JSON")
    return text


def serialize_memory(record: dict, body: str) -> str:
    """Serialise one memory deterministically: fixed key order, no blank lines."""
    lines = ["---"]
    for key in _FRONTMATTER_KEYS:
        lines.append(f"{key}: {_dump_scalar(record[key])}")
    lines.append("retention:")
    for key in ("policy", "expires", "superseded_by"):
        lines.append(f"  {key}: {_dump_scalar(record['retention'][key])}")
    lines.append("sources:")
    for source in record["sources"]:
        first = True
        for key in ("kind", "ref", "note"):
            if key == "note" and "note" not in source:
                continue
            prefix = "  - " if first else "    "
            lines.append(prefix + key + ": " + _dump_scalar(source[key]))
            first = False
    lines.append("sha: " + _dump_scalar(record["sha"]))
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def _split_frontmatter(text: str):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        refuse("schema_invalid", "a memory file starts with a frontmatter fence")
    closing = None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == "---":
            closing = index
            break
    if closing is None:
        refuse("schema_invalid", "the frontmatter fence is not closed")
    return "".join(lines[1:closing]), "".join(lines[closing + 1 :])


def _parse_frontmatter_block(block: str) -> dict:
    record: dict = {}
    current = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            key, sep, value = line.partition(":")
            if not sep:
                refuse("schema_invalid", "malformed frontmatter line")
            key = key.strip()
            if value.strip():
                record[key] = _parse_scalar(value)
                current = None
            else:
                nested = {"retention": {}, "sources": []}
                if key not in nested:
                    refuse("schema_invalid", f"unknown nested frontmatter key: {key!r}")
                record[key] = nested[key]
                current = key
        elif current == "retention":
            key, sep, value = line.partition(":")
            if not sep:
                refuse("schema_invalid", "malformed retention entry")
            record["retention"][key.strip()] = _parse_scalar(value)
        elif current == "sources":
            if line.startswith("- "):
                key, sep, value = line[2:].partition(":")
                if not sep:
                    refuse("schema_invalid", "malformed source entry")
                record["sources"].append({key.strip(): _parse_scalar(value)})
            else:
                if not record["sources"]:
                    refuse("schema_invalid", "a source continuation has no source")
                key, sep, value = line.partition(":")
                if not sep:
                    refuse("schema_invalid", "malformed source entry")
                record["sources"][-1][key.strip()] = _parse_scalar(value)
        else:
            refuse("schema_invalid", "unexpected indented frontmatter line")
    return record


def parse_memory(text: str):
    """Parse a stored memory file into ``(record, body)``."""
    block, body = _split_frontmatter(text)
    return _parse_frontmatter_block(block), body


# ---------------------------------------------------------------------------
# Contract validation (mirrors the published schema's semantic half).
# ---------------------------------------------------------------------------


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
# Zones, retention and engine fallback.
# ---------------------------------------------------------------------------


def zone_of(path: str) -> str:
    if path in CURATED_FILES or path.startswith(CURATED_PREFIXES):
        return "curated"
    if path.startswith(REVIEWED_PREFIXES):
        return "reviewed"
    if path.startswith(QUARANTINE_ROOT + "/"):
        return "open"
    return "service-owned"


def quarantine_prefix(writer: str) -> str:
    return f"{QUARANTINE_ROOT}/{writer.replace(':', '-')}/"


def is_expired(record: dict, now: str) -> bool:
    ret = record["retention"]
    if ret.get("superseded_by"):
        return True
    expires = ret.get("expires")
    if expires and parse_time(expires) <= parse_time(now):
        return True
    return False


def resolve_mode(requested: str, has_fts5: bool, has_embeddings: bool) -> str:
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
    lines = [line for line in body.splitlines()[1:] if line.strip()]
    text = " ".join(lines)
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "\u2026"


# ---------------------------------------------------------------------------
# The vault.
# ---------------------------------------------------------------------------

RULEBOOK = """# rizzstack memory vault

This file is the vault rulebook. Read it before touching anything else here.

The vault is the semantic-memory layer of the rizzstack: plain, Obsidian-
compatible markdown that any agent can read, search and write through the
`rizzstack.memory/1` contract. Files plus search, not a bespoke store.

## Layout

- `concepts/`   reference memories: stable distilled knowledge with sources
- `entities/`   env-fact memories: checked facts about concrete environment things
- `decisions/`  decision memories: chosen directions and why
- `learnings/`  learning memories: durable insights about how work behaves
- `pitfalls/`   pitfall memories: confirmed traps and their fixes
- `projects/`   project-state memories: where a project stands and what is next
- `sessions/`   service-owned episodic session digests (source material only)
- `index.md`    curated hand-built index of entries and wikilinks
- `hot.md`      curated always-injected slice for every brief
- `log.md`      service-owned append-only JSON-lines receipt log
- `VAULT.md`    this service-owned rulebook

One file per memory, named `<id>.md`, in the directory its type maps to.
Writing a memory into a directory its type does not map to is refused.

## Zones and grants

Writes are quarantined by default: without an authority grant a writer may only
target its own `.quarantine/<writer-slug>/` subtree. Reviewed zones
(`entities/`, `learnings/`, `pitfalls/`, `projects/`) accept a grant approved by
`human`, `orbit` or `bundlebees`. Curated zones (`concepts/`, `decisions/`,
`hot.md`, `index.md`) require a human approver. Service-owned paths
(`sessions/`, `log.md`, `VAULT.md`) are never written through the operation
surface.

## Digests and the sha guard

`sha` is sha256 over the canonical frontmatter without the `sha` field, then a
newline, then the markdown body. Every write carries `expected_sha`: null on
create, the digest last read on update. A stale digest is refused with the
current digest and a re-read requirement; the loser merges, never overwrites.

## Retention

A memory expires when `superseded_by` is set or `expires` has passed. Queries
hide expired memories unless they opt in with `include_expired`.

- decision: decision-permanent; supersede, never auto-expire
- learning: learning-until-superseded; `expires` stays null
- pitfall: pitfall-until-fixed; the fixer sets `expires`
- env-fact: env-fact-until-fix; point `superseded_by` at the replacement
- project-state: project-state-until-done; set `expires` on completion
- reference: reference-refresh; always carries a re-verify deadline

## Receipts and scrubbing

Every accepted write appends one JSON receipt line to `log.md` with a
monotonically increasing `seq`. The vault generation is `gen-<seq>` and never
moves backwards.

Never store a credential, an environment file or a private endpoint here.
Scrub before writing; provenance belongs in `sources`, not in a transcript.
"""

INDEX_MD = """# Vault index

Hand-built index of entries and wikilinks. Maintained by humans; add one bullet
per entry and link related memories with wikilinks.
"""

HOT_MD = """# Hot memories

The always-injected slice: the small set of facts every brief should start from.
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DiskVault:
    """Read, query and write the markdown vault at ``root``."""

    def __init__(self, root) -> None:
        self.root = Path(root)
        if self.root.exists() and not self.root.is_dir():
            raise NotADirectoryError(f"{self.root} is not a directory")
        self._bootstrap()

    # -- bootstrap ---------------------------------------------------------

    def _bootstrap(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for name in VAULT_DIRS:
            (self.root / name).mkdir(exist_ok=True)
        for name, text in (("VAULT.md", RULEBOOK), ("index.md", INDEX_MD), ("hot.md", HOT_MD), ("log.md", "")):
            target = self.root / name
            if not target.exists():
                self._write_text(target, text)

    @staticmethod
    def _write_text(target: Path, text: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(target.parent), delete=False)
        try:
            with handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(handle.name, target)
        except BaseException:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise

    # -- paths -------------------------------------------------------------

    def _validate_path(self, path) -> str:
        if not isinstance(path, str) or not VAULT_PATH_RE.match(path):
            refuse("schema_invalid", "path must be a vault-relative markdown path")
        if any(segment in (".", "..") for segment in PurePosixPath(path).parts):
            refuse("schema_invalid", "path segments must not be dot segments")
        return path

    def _resolve(self, path: str) -> Path:
        self._validate_path(path)
        target = (self.root / path).resolve()
        root = self.root.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            refuse("schema_invalid", "path resolves outside the vault root")
        return target

    # -- receipts ----------------------------------------------------------

    @property
    def log_path(self) -> Path:
        return self.root / "log.md"

    def _last_log_seq(self) -> int:
        last = 0
        if not self.log_path.exists():
            return last
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except (ValueError, TypeError):
                continue
            seq = entry.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool) and seq > last:
                last = seq
        return last

    @property
    def vault_rev(self) -> str:
        return f"gen-{self._last_log_seq()}"

    def receipts(self) -> list:
        entries = []
        if not self.log_path.exists():
            return entries
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except (ValueError, TypeError):
                continue
        return entries

    def _append_receipt(self, entry: dict) -> None:
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    # -- scanning ----------------------------------------------------------

    def _candidate_paths(self) -> list:
        paths = []
        for name in sorted(set(TYPE_DIR.values())):
            directory = self.root / name
            if directory.is_dir():
                paths.extend(directory.rglob("*.md"))
        quarantine = self.root / QUARANTINE_ROOT
        if quarantine.is_dir():
            paths.extend(quarantine.rglob("*.md"))
        for name in CURATED_FILES:
            if (self.root / name).is_file():
                paths.append(self.root / name)
        unique = {}
        for path in paths:
            if path.is_file():
                unique[path.relative_to(self.root).as_posix()] = path
        return [unique[key] for key in sorted(unique)]

    def _load(self, target: Path):
        text = target.read_text(encoding="utf-8")
        record, body = parse_memory(text)
        validate_frontmatter(record)
        return record, body

    def _scan(self) -> list:
        entries = []
        for target in self._candidate_paths():
            rel = target.relative_to(self.root).as_posix()
            if zone_of(rel) == "service-owned":
                continue
            try:
                record, body = self._load(target)
            except (ContractError, OSError, UnicodeDecodeError):
                continue
            entries.append({"record": record, "body": body, "path": rel})
        return entries

    # -- write -------------------------------------------------------------

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

        target = self._resolve(path)
        existing = None
        if target.is_file():
            try:
                stored_record, _ = self._load(target)
            except (ContractError, OSError, UnicodeDecodeError):
                stored_record = None
            if stored_record is not None:
                existing = stored_record

        if existing is None:
            if op["expected_sha"] is not None:
                refuse("sha_conflict", "the target does not exist; re-read and create without a digest", reread=True)
            for entry in self._scan():
                if entry["path"] == path:
                    continue
                if entry["record"]["id"] == record["id"]:
                    refuse("duplicate_id", "this memory id already exists elsewhere in the vault")
        else:
            stored = existing["sha"]
            if op["expected_sha"] is None:
                refuse("sha_conflict", "an update needs the digest of the version you read", reread=True, current_sha=stored)
            elif op["expected_sha"] != stored:
                refuse("sha_conflict", "your digest is stale; the memory changed under you", reread=True, current_sha=stored)
            if existing["id"] != record["id"]:
                refuse("id_mismatch", "the path holds a different memory id")

        self._write_text(target, serialize_memory(record, body))
        seq = self._last_log_seq() + 1
        self._append_receipt(
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
        self._refresh_index(record["id"], path)
        return {"accepted": True, "id": record["id"], "sha": record["sha"], "path": path, "log_seq": seq}

    def _refresh_index(self, memory_id: str, path: str) -> None:
        """Refresh an existing index for one accepted write; never raise."""
        try:
            from .index import Index

            index = Index(self.root)
            if index.healthy():
                index.update_incremental(memory_id, path=path)
        except Exception:
            return

    def write_envelope(self, op: dict) -> dict:
        """A refusal envelope a coordinator can relay without catching."""
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

    # -- read --------------------------------------------------------------

    def read(self, path: str, expected_sha: str = None) -> dict:
        if expected_sha is not None and (not isinstance(expected_sha, str) or not SHA_RE.match(expected_sha)):
            refuse("schema_invalid", "expected_sha must be null or 64 lowercase hex characters")
        target = self._resolve(path)
        if not target.is_file():
            refuse("not_found", f"no memory at {path}")
        record, body = self._load(target)
        result = {
            "record": copy.deepcopy(record),
            "body": body,
            "path": path,
            "drift": False,
            "warning": None,
            "current_sha": record["sha"],
        }
        if expected_sha is not None and expected_sha != record["sha"]:
            result["drift"] = True
            result["warning"] = (
                f"{path} changed since it was read: expected digest {expected_sha}, current digest {record['sha']}"
            )
        return result

    # -- retention ---------------------------------------------------------

    def active_records(self, now: str, include_expired: bool = False) -> list:
        if not isinstance(now, str) or not TIME_RE.match(now):
            refuse("schema_invalid", "now must be an RFC 3339 timestamp")
        records = []
        for entry in self._scan():
            if include_expired or not is_expired(entry["record"], now):
                records.append(copy.deepcopy(entry["record"]))
        return records

    # -- query -------------------------------------------------------------

    def query(self, op: dict, now: str = None) -> dict:
        validate_query_op(op)
        if now is None:
            now = _utc_now()
        elif not isinstance(now, str) or not TIME_RE.match(now):
            refuse("schema_invalid", "now must be an RFC 3339 timestamp")
        include_expired = bool(op.get("include_expired"))
        types = set(op.get("types") or ())
        k = op.get("k", 8)
        requested = op.get("mode", "hybrid")
        terms = _query_terms(op["q"])

        index = self._open_index(requested)
        mode_used = resolve_mode(requested, has_fts5=index is not None, has_embeddings=False)
        ranked = None
        if mode_used == "keyword" and index is not None:
            try:
                ranked = self._keyword_ranked(index, terms, types, include_expired, now)
            except Exception:
                ranked = None
        if ranked is None:
            mode_used = "grep"
            ranked = self._grep_ranked(terms, types, include_expired, now)
        ranked.sort(key=lambda hit: (-hit["score"], hit["path"]))
        result = {
            "op": "query-result",
            "mode_used": mode_used,
            "hits": ranked[:k],
            "vault_rev": self.vault_rev,
        }
        return validate_query_result(result)

    def _open_index(self, requested: str):
        if requested == "grep":
            return None
        try:
            from .index import Index

            candidate = Index(self.root)
            if candidate.healthy():
                return candidate
        except Exception:
            return None
        return None

    def _keyword_ranked(self, index, terms: list, types: set, include_expired: bool, now: str) -> list:
        entries = []
        for memory_id in index.search(terms):
            stored = index.get(memory_id)
            if stored is None:
                continue
            try:
                target = self._resolve(stored["path"])
            except ContractError:
                continue
            if not target.is_file():
                continue
            try:
                record, body = self._load(target)
            except (ContractError, OSError, UnicodeDecodeError):
                continue
            entries.append({"record": record, "body": body, "path": stored["path"]})
        return self._rank_entries(entries, terms, types, include_expired, now)

    def _grep_ranked(self, terms: list, types: set, include_expired: bool, now: str) -> list:
        return self._rank_entries(self._scan(), terms, types, include_expired, now)

    @staticmethod
    def _rank_entries(entries: list, terms: list, types: set, include_expired: bool, now: str) -> list:
        ranked = []
        for entry in entries:
            record = entry["record"]
            if types and record["type"] not in types:
                continue
            if not include_expired and is_expired(record, now):
                continue
            body = entry["body"]
            title = _title_of(body, record)
            score = _score(terms, title, body)
            if score <= 0:
                continue
            ranked.append(
                {
                    "id": record["id"],
                    "type": record["type"],
                    "path": entry["path"],
                    "title": title,
                    "sha": record["sha"],
                    "score": score,
                    "snippet": _snippet(body, title, terms),
                }
            )
        return ranked


def _query_terms(q: str) -> list:
    seen = []
    for term in re.findall(r"[a-z0-9]+", q.lower()):
        if term not in seen:
            seen.append(term)
    return seen


def _title_of(body: str, record: dict) -> str:
    first = body.splitlines()[0] if body.splitlines() else ""
    title = first[2:] if first.startswith("# ") else first
    if not title:
        title = record["id"]
    return title[:200]


def _score(terms: list, title: str, body: str) -> float:
    if not terms:
        return 0.0
    title_low = title.lower()
    body_low = body.lower()
    score = 0.0
    for term in terms:
        score += 3.0 * title_low.count(term)
        score += float(body_low.count(term))
    return score


def _snippet(body: str, title: str, terms: list) -> str:
    lines = [line.strip() for line in body.splitlines()[1:] if line.strip()]
    if not lines:
        return title[:MAX_SNIPPET_CHARS]
    best = max(lines, key=lambda line: sum(line.lower().count(term) for term in terms))
    if len(best) <= MAX_SNIPPET_CHARS:
        return best
    return best[: MAX_SNIPPET_CHARS - 1] + "\u2026"


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
