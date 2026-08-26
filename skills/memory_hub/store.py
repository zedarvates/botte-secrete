"""Memory Store - governed memory with SQLite backend."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional
from skills.memory_hub.schema import (
    EXTERNAL_SOURCE_TYPES, FULL_DDL, SCHEMA_VERSION, MemoryEntry,
    MemorySourceType, MemoryStatus, MemoryTrustClass, MemoryVisibility,
)

class MemoryAccessError(PermissionError):
    def __init__(self, entry_key, agent_id, action):
        super().__init__(f"agent={agent_id} cannot {action} key={entry_key}")


_PROJECT_ID_RE = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9._-]{0,127}\Z")
_TABLES = ("memory_entries", "memory_quarantine")
_PROVENANCE_COLUMNS = {
    "source_type": "TEXT NOT NULL DEFAULT 'generated'",
    "source_uri": "TEXT NOT NULL DEFAULT ''",
    "source_id": "TEXT NOT NULL DEFAULT ''",
    "run_id": "TEXT NOT NULL DEFAULT 'legacy'",
    "observed_at": "REAL NOT NULL DEFAULT 0",
    "trust_class": "TEXT NOT NULL DEFAULT 'generated_untrusted'",
    "executable_instruction": "INTEGER NOT NULL DEFAULT 0",
    "quarantined": "INTEGER NOT NULL DEFAULT 1",
}


class MemoryStore:
    def __init__(self, base_dir=None):
        self.base = Path(base_dir) if base_dir else Path.home() / ".botte" / "memory_hub"
        self.base.mkdir(parents=True, exist_ok=True)
        self._connections = {}
        self._conn("__global__")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()

    @staticmethod
    def _validate_project_id(project_id):
        if not isinstance(project_id, str) or not _PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError(
                "project_id must be 1-128 characters using letters, digits, '.', '_', or '-'"
            )
        return project_id

    def _db_path(self, project_id):
        self._validate_project_id(project_id)
        return self.base / f"{project_id}.sqlite"

    def _conn(self, project_id):
        if project_id not in self._connections:
            path = self._db_path(project_id)
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            has = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_schema'").fetchone()
            if not has:
                conn.executescript(FULL_DDL)
                now = time.time()
                conn.execute(f"INSERT INTO _schema (version, applied_at) VALUES (?, ?)", (SCHEMA_VERSION, now))
            else:
                self._migrate(conn)
            conn.commit()
            self._connections[project_id] = conn
        return self._connections[project_id]

    @staticmethod
    def _migrate(conn):
        """Upgrade v1 safely; legacy rows remain non-executable and quarantined."""
        conn.executescript(FULL_DDL)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_entries)")}
        changed = False
        for name, ddl in _PROVENANCE_COLUMNS.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE memory_entries ADD COLUMN {name} {ddl}")
                changed = True
        quarantine_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(memory_quarantine)")
        ]
        names = ",".join(quarantine_columns)
        conn.execute(
            f"INSERT OR IGNORE INTO memory_quarantine ({names}) "
            f"SELECT {names} FROM memory_entries WHERE quarantined = 1"
        )
        conn.execute("DELETE FROM memory_entries WHERE quarantined = 1")
        current = conn.execute("SELECT MAX(version) FROM _schema").fetchone()[0] or 0
        if changed or current < SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO _schema (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, time.time()),
            )

    def close(self, project_id=None):
        if project_id:
            conn = self._connections.pop(project_id, None)
            if conn: conn.close()
        else:
            for conn in self._connections.values(): conn.close()
            self._connections.clear()

    def store(self, entry):
        self._normalize_provenance(entry)
        conn = self._conn(entry.project_id)
        now = time.time()
        tags_json = json.dumps(entry.tags, ensure_ascii=False)
        val_json = json.dumps(entry.value, ensure_ascii=False)
        existing, existing_table = self._get_raw(conn, entry.project_id, entry.key)
        version = entry.version
        created_at = now
        if existing:
            existing_entry = self._row_to_entry(existing)
            if existing_entry.agent_id and existing_entry.agent_id != entry.agent_id:
                raise MemoryAccessError(entry.key, entry.agent_id, "overwrite")
            created_at = existing["created_at"]
            version = existing["version"] + 1
            target = self._table_for(entry)
            if existing_table == "memory_quarantine" and target == "memory_entries":
                raise MemoryAccessError(entry.key, entry.agent_id, "dequarantine")
            if existing_table != target:
                conn.execute(
                    f"DELETE FROM {existing_table} WHERE project_id = ? AND key = ?",
                    (entry.project_id, entry.key),
                )
        table = self._table_for(entry)
        conn.execute(
            f"INSERT INTO {table} (key, value_json, asset_type, category, confidence, status, visibility, sensitivity, project_id, agent_id, source_ref, source_digest, source_type, source_uri, source_id, run_id, observed_at, trust_class, executable_instruction, quarantined, created_by, expires_at, created_at, updated_at, access_count, version, tags_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id, key) DO UPDATE SET value_json=excluded.value_json, asset_type=excluded.asset_type, category=excluded.category, confidence=excluded.confidence, status=excluded.status, visibility=excluded.visibility, sensitivity=excluded.sensitivity, source_ref=excluded.source_ref, source_digest=excluded.source_digest, source_type=excluded.source_type, source_uri=excluded.source_uri, source_id=excluded.source_id, run_id=excluded.run_id, observed_at=excluded.observed_at, trust_class=excluded.trust_class, executable_instruction=0, quarantined=excluded.quarantined, expires_at=excluded.expires_at, updated_at=excluded.updated_at, version=excluded.version, tags_json=excluded.tags_json",
            (entry.key, val_json, entry.asset_type, entry.category, entry.confidence, entry.status, entry.visibility, entry.sensitivity, entry.project_id, entry.agent_id, entry.source_ref, entry.source_digest, entry.source_type, entry.source_uri, entry.source_id, entry.run_id, entry.observed_at, entry.trust_class, 0, int(entry.quarantined), entry.created_by, entry.expires_at, created_at, now, 0, version, tags_json)
        )
        conn.commit()

    @staticmethod
    def _table_for(entry):
        return "memory_quarantine" if entry.quarantined else "memory_entries"

    @staticmethod
    def _normalize_provenance(entry):
        if entry.source_type not in {item.value for item in MemorySourceType}:
            raise ValueError("invalid memory source_type")
        if entry.trust_class not in {item.value for item in MemoryTrustClass}:
            raise ValueError("invalid memory trust_class")
        if not isinstance(entry.run_id, str) or not entry.run_id.strip() or len(entry.run_id) > 128:
            raise ValueError("run_id must be 1-128 characters")
        if (isinstance(entry.confidence, bool)
                or not isinstance(entry.confidence, (int, float))
                or not math.isfinite(entry.confidence)
                or not 0 <= entry.confidence <= 1):
            raise ValueError("confidence must be between 0 and 1")
        if (isinstance(entry.observed_at, bool)
                or not isinstance(entry.observed_at, (int, float))
                or not math.isfinite(entry.observed_at)
                or entry.observed_at <= 0):
            raise ValueError("timestamp must be a positive finite number")
        if entry.executable_instruction:
            raise ValueError("memory cannot contain executable instructions")
        for value, label in ((entry.source_uri, "source_uri"), (entry.source_id, "source_id")):
            if not isinstance(value, str) or len(value) > 512:
                raise ValueError(f"{label} must be a string of at most 512 characters")
        if entry.source_type in EXTERNAL_SOURCE_TYPES:
            entry.quarantined = True
            entry.trust_class = (
                MemoryTrustClass.GENERATED_UNTRUSTED.value
                if entry.source_type == MemorySourceType.GENERATED.value
                else MemoryTrustClass.EXTERNAL_OBSERVATION.value
            )
        elif entry.trust_class != MemoryTrustClass.TRUSTED_USER.value:
            entry.quarantined = True
        entry.executable_instruction = False

    def recall(self, project_id, key, agent_id=None):
        entry = self.get(project_id, key, agent_id)
        return entry.value if entry else None

    def get(self, project_id, key, agent_id=None):
        conn = self._conn(project_id)
        row, table = self._get_raw(conn, project_id, key)
        if not row: return None
        entry = self._row_to_entry(row)
        if agent_id and not self._can_access(entry, agent_id): return None
        conn.execute(f"UPDATE {table} SET access_count = access_count + 1 WHERE project_id = ? AND key = ?", (project_id, key))
        conn.commit()
        return entry

    def delete(self, project_id, key, actor_id=None):
        conn = self._conn(project_id)
        row, table = self._get_raw(conn, project_id, key)
        if not row:
            return False
        entry = self._row_to_entry(row)
        if actor_id is not None and entry.agent_id and entry.agent_id != actor_id:
            raise MemoryAccessError(key, actor_id, "delete")
        cur = conn.execute(f"DELETE FROM {table} WHERE project_id = ? AND key = ?", (project_id, key))
        conn.commit()
        return cur.rowcount > 0

    def search(self, project_id, query="", asset_type=None, status=None, visibility=None,
               agent_id=None, limit=50, storage_area="all"):
        conn = self._conn(project_id)
        limit = max(1, min(int(limit), 100))
        if storage_area not in {"all", "trusted", "quarantine"}:
            raise ValueError("storage_area must be all, trusted, or quarantine")
        tables = _TABLES if storage_area == "all" else (
            ("memory_entries",) if storage_area == "trusted" else ("memory_quarantine",)
        )
        rows = []
        for table in tables:
            sql = f"SELECT * FROM {table} WHERE project_id = ?"
            params = [project_id]
            if asset_type: sql += " AND asset_type = ?"; params.append(asset_type)
            if status: sql += " AND status = ?"; params.append(status)
            if visibility: sql += " AND visibility = ?"; params.append(visibility)
            if query:
                sql += " AND (key LIKE ? OR category LIKE ? OR tags_json LIKE ?)"
                like = f"%{query}%"; params.extend([like, like, like])
            rows.extend(conn.execute(sql, params).fetchall())
        entries = [self._row_to_entry(r) for r in rows]
        if agent_id: entries = [e for e in entries if self._can_access(e, agent_id)]
        entries.sort(key=lambda item: item.confidence * item.access_count, reverse=True)
        return entries[:limit]

    def list_projects(self):
        rows = []
        for p in self.base.glob("*.sqlite"):
            pid = p.stem
            conn = self._conn(pid)
            total = sum(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in _TABLES)
            if total > 0: rows.append(pid)
        return sorted(rows)

    def transition(self, project_id, key, new_status, actor_id=""):
        if not actor_id:
            return False
        entry = self.get(project_id, key)
        if not entry: return False
        current = MemoryStatus(entry.status)
        target = MemoryStatus(new_status)
        if current.frozen(): return False
        if target not in current.allowed_transitions(): return False
        if entry.quarantined and target is MemoryStatus.PROMOTED:
            return False
        conn = self._conn(project_id)
        table = self._table_for(entry)
        conn.execute(f"UPDATE {table} SET status = ?, updated_at = ? WHERE project_id = ? AND key = ?", (new_status, time.time(), project_id, key))
        conn.commit()
        return True

    def prune_expired(self, project_id):
        conn = self._conn(project_id)
        removed = 0
        for table in _TABLES:
            cur = conn.execute(f"DELETE FROM {table} WHERE project_id = ? AND expires_at IS NOT NULL AND expires_at < ?", (project_id, time.time()))
            removed += cur.rowcount
        conn.commit()
        return removed

    def stats(self, project_id):
        conn = self._conn(project_id)
        expired_count = self.prune_expired(project_id)
        total = quarantined = 0
        by_status = {}; by_asset = {}
        for table in _TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id = ?", (project_id,)).fetchone()[0]
            total += count
            if table == "memory_quarantine": quarantined = count
            for key, value in conn.execute(f"SELECT status, COUNT(*) FROM {table} WHERE project_id = ? GROUP BY status", (project_id,)):
                by_status[key] = by_status.get(key, 0) + value
            for key, value in conn.execute(f"SELECT asset_type, COUNT(*) FROM {table} WHERE project_id = ? GROUP BY asset_type", (project_id,)):
                by_asset[key] = by_asset.get(key, 0) + value
        return {"project_id": project_id, "total": total, "quarantined": quarantined,
                "by_status": by_status, "by_asset": by_asset,
                "expired_pruned": expired_count, "db_path": str(self._db_path(project_id))}

    def _get_raw(self, conn, project_id, key):
        for table in _TABLES:
            row = conn.execute(f"SELECT * FROM {table} WHERE project_id = ? AND key = ?", (project_id, key)).fetchone()
            if row:
                return row, table
        return None, None

    def _row_to_entry(self, row):
        tags = json.loads(row["tags_json"]) if isinstance(row["tags_json"], str) else row["tags_json"]
        return MemoryEntry(key=row["key"], value=json.loads(row["value_json"]), asset_type=row["asset_type"], category=row["category"], confidence=row["confidence"], status=row["status"], visibility=row["visibility"], sensitivity=row["sensitivity"], project_id=row["project_id"], agent_id=row["agent_id"], source_ref=row["source_ref"], source_digest=row["source_digest"], source_type=row["source_type"], source_uri=row["source_uri"], source_id=row["source_id"], run_id=row["run_id"], observed_at=row["observed_at"], trust_class=row["trust_class"], executable_instruction=bool(row["executable_instruction"]), quarantined=bool(row["quarantined"]), created_by=row["created_by"], expires_at=row["expires_at"], created_at=row["created_at"], updated_at=row["updated_at"], access_count=row["access_count"], version=row["version"], tags=tags)

    def _can_access(self, entry, agent_id):
        if entry.visibility == MemoryVisibility.PRIVATE.value:
            return entry.agent_id == agent_id
        return True

    def context_bundle(self, project_id, agent_id, max_entries=10):
        max_entries = max(1, min(int(max_entries), 100))
        entries = self.search(project_id=project_id, status="promoted", agent_id=agent_id,
                              limit=max_entries, storage_area="trusted")
        return [{"key": e.key, "value": e.value, "type": e.asset_type,
                 "confidence": e.confidence, "tags": e.tags,
                 "provenance": {"source_type": e.source_type,
                                "source_uri": e.source_uri, "source_id": e.source_id,
                                "run_id": e.run_id, "timestamp": e.observed_at,
                                "trust_class": e.trust_class,
                                "executable_instruction": False}}
                for e in entries[:max_entries]]

    def review_quarantine(self, project_id, agent_id, query="", limit=20):
        entries = self.search(project_id=project_id, query=query, agent_id=agent_id,
                              limit=limit, storage_area="quarantine")
        return [{"key": e.key, "content": e.value, "type": e.asset_type,
                 "handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE",
                 "provenance": {"source_type": e.source_type,
                                "source_uri": e.source_uri, "source_id": e.source_id,
                                "run_id": e.run_id, "timestamp": e.observed_at,
                                "confidence": e.confidence, "trust_class": e.trust_class,
                                "executable_instruction": False}}
                for e in entries]

__all__ = ["MemoryStore", "MemoryAccessError"]
