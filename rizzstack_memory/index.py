"""SQLite FTS5 keyword index for the ``rizzstack.memory/1`` vault.

The index is a derived cache, never the source of truth: markdown files stay
authoritative, and every row here can be rebuilt from them. It exists so
``DiskVault.query`` can answer a keyword query from SQLite FTS5 instead of
scanning every file, while the same vault stays queryable through the grep
fallback when the index is missing, unreadable or corrupt.

Only the standard library is used (``sqlite3`` with the built-in FTS5 module).
Rebuilds and incremental refreshes read markdown and write only inside
``<root>/.index/``; they never touch frontmatter, ``index.md``, ``hot.md`` or
``log.md``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .vault import (
    CURATED_FILES,
    QUARANTINE_ROOT,
    TYPE_DIR,
    ContractError,
    _score,
    _title_of,
    parse_memory,
    validate_frontmatter,
    zone_of,
)

INDEX_DIR = ".index"
INDEX_NAME = "memory-fts5.sqlite3"
SCHEMA_VERSION = "1"


class Index:
    """A keyword index over the markdown memories of one vault root."""

    def __init__(self, root) -> None:
        self.root = Path(root)
        self.db_path = self.root / INDEX_DIR / INDEX_NAME

    # -- connection and schema --------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=1.0)

    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE memories ("
            "memory_id TEXT PRIMARY KEY, type TEXT NOT NULL, path TEXT NOT NULL UNIQUE, "
            "title TEXT NOT NULL, sha TEXT NOT NULL, body TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE memory_fts USING fts5("
            "memory_id UNINDEXED, type UNINDEXED, path UNINDEXED, title, sha UNINDEXED, body)"
        )
        conn.execute(
            "INSERT INTO meta (name, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )

    def healthy(self) -> bool:
        """True only for a readable database with this index's schema."""
        if not self.db_path.is_file():
            return False
        conn = None
        try:
            conn = self._connect()
            row = conn.execute("SELECT value FROM meta WHERE name = 'schema_version'").fetchone()
            if row is None or row[0] != SCHEMA_VERSION:
                return False
            conn.execute("SELECT memory_id, type, path, title, sha, body FROM memories LIMIT 1").fetchone()
            conn.execute("SELECT count(*) FROM memories").fetchone()
            conn.execute("SELECT count(*) FROM memory_fts").fetchone()
            conn.execute("SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ?", ('"healthcheck"',)).fetchall()
        except (sqlite3.Error, OSError, ValueError):
            return False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
        return True

    # -- markdown scan -----------------------------------------------------

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
            target = self.root / name
            if target.is_file():
                paths.append(target)
        unique = {}
        for target in paths:
            if target.is_file():
                rel = target.relative_to(self.root).as_posix()
                unique[rel] = target
        return [unique[rel] for rel in sorted(unique)]

    def _read_path(self, target: Path):
        try:
            rel = target.relative_to(self.root).as_posix()
        except ValueError:
            return None
        if zone_of(rel) == "service-owned":
            return None
        try:
            record, body = parse_memory(target.read_text(encoding="utf-8"))
            validate_frontmatter(record)
        except (ContractError, OSError, UnicodeDecodeError):
            return None
        return {
            "id": record["id"],
            "type": record["type"],
            "path": rel,
            "title": _title_of(body, record),
            "sha": record["sha"],
            "body": body,
        }

    @staticmethod
    def _insert(conn: sqlite3.Connection, row: dict) -> None:
        conn.execute(
            "INSERT INTO memories (memory_id, type, path, title, sha, body) VALUES (?, ?, ?, ?, ?, ?)",
            (row["id"], row["type"], row["path"], row["title"], row["sha"], row["body"]),
        )
        conn.execute(
            "INSERT INTO memory_fts (memory_id, type, path, title, sha, body) VALUES (?, ?, ?, ?, ?, ?)",
            (row["id"], row["type"], row["path"], row["title"], row["sha"], row["body"]),
        )

    @staticmethod
    def _delete(conn: sqlite3.Connection, memory_id: str) -> None:
        conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
        conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,))

    def _discard_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(self.db_path) + suffix).unlink()
            except FileNotFoundError:
                pass
            except OSError:
                raise

    # -- build and refresh -------------------------------------------------

    def create(self) -> "Index":
        """Create the index when it is absent or unusable; idempotent."""
        if not self.healthy():
            self.rebuild()
        return self

    def rebuild(self) -> "Index":
        """Rebuild every row from the markdown files, replacing any old file."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._discard_files()
        conn = self._connect()
        try:
            self._create_schema(conn)
            for target in self._candidate_paths():
                row = self._read_path(target)
                if row is not None:
                    self._insert(conn, row)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self

    def _locate(self, memory_id: str, path) -> Path:
        if path is not None:
            target = Path(path)
            if not target.is_absolute():
                target = self.root / target
            return target
        conn = self._connect()
        try:
            row = conn.execute("SELECT path FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
        finally:
            conn.close()
        if row is not None:
            return self.root / row[0]
        matches = [target for target in self._candidate_paths() if target.stem == memory_id]
        if len(matches) == 1:
            return matches[0]
        return None

    def update_incremental(self, memory_id: str, path=None) -> bool:
        """Re-read one memory file and refresh its row (or drop a stale row)."""
        if not isinstance(memory_id, str) or not memory_id:
            return False
        if not self.db_path.is_file():
            return False
        try:
            target = self._locate(memory_id, path)
        except (sqlite3.Error, OSError):
            return False
        if target is None:
            return False
        row = self._read_path(target)
        try:
            rel = target.relative_to(self.root).as_posix()
        except ValueError:
            rel = None
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT memory_id FROM memories WHERE memory_id = ? OR path = ?",
                (memory_id, rel if rel is not None else memory_id),
            ).fetchall()
            for (old_id,) in existing:
                self._delete(conn, old_id)
            if row is not None and row["id"] == memory_id:
                self._insert(conn, row)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        return row is not None and row["id"] == memory_id

    # -- reads -------------------------------------------------------------

    def get(self, memory_id: str):
        """Return one stored row, or None."""
        if not self.db_path.is_file():
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT memory_id, type, path, title, sha, body FROM memories WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "id": row[0],
            "type": row[1],
            "path": row[2],
            "title": row[3],
            "sha": row[4],
            "body": row[5],
        }

    def search(self, terms) -> list:
        """Return matching memory ids, ranked by the shared vault score."""
        cleaned = [term for term in terms if term]
        if not cleaned:
            return []
        if not self.db_path.is_file():
            return []
        match = " OR ".join('"' + term + '"*' for term in cleaned)
        conn = self._connect()
        try:
            ids = {
                row[0]
                for row in conn.execute(
                    "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ?", (match,)
                ).fetchall()
            }
            for term in cleaned:
                needle = "%" + term + "%"
                ids.update(
                    row[0]
                    for row in conn.execute(
                        "SELECT memory_id FROM memories WHERE lower(title) LIKE ? OR lower(body) LIKE ?",
                        (needle, needle),
                    ).fetchall()
                )
            ranked = []
            for memory_id in ids:
                row = conn.execute(
                    "SELECT memory_id, title, body, path FROM memories WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
                if row is None:
                    continue
                score = _score(cleaned, row[1], row[2])
                if score <= 0:
                    continue
                ranked.append((score, row[3], row[0]))
        finally:
            conn.close()
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked]


__all__ = ["INDEX_DIR", "INDEX_NAME", "Index"]
