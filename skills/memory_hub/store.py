"""Memory Store - governed memory with SQLite backend."""
from __future__ import annotations
import json, sqlite3, time
from pathlib import Path
from typing import Any, Optional
from skills.memory_hub.schema import FULL_DDL, SCHEMA_VERSION, MemoryEntry, MemoryStatus, MemoryVisibility

class MemoryAccessError(PermissionError):
    def __init__(self, entry_key, agent_id, action):
        super().__init__(f"agent={agent_id} cannot {action} key={entry_key}")

class MemoryStore:
    def __init__(self, base_dir=None):
        self.base = Path(base_dir) if base_dir else Path.home() / ".botte" / "memory_hub"
        self.base.mkdir(parents=True, exist_ok=True)
        self._connections = {}
        self._conn("__global__")

    def _db_path(self, project_id):
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
            conn.commit()
            self._connections[project_id] = conn
        return self._connections[project_id]

    def close(self, project_id=None):
        if project_id:
            conn = self._connections.pop(project_id, None)
            if conn: conn.close()
        else:
            for conn in self._connections.values(): conn.close()
            self._connections.clear()

    def store(self, entry):
        conn = self._conn(entry.project_id)
        now = time.time()
        tags_json = json.dumps(entry.tags, ensure_ascii=False)
        val_json = json.dumps(entry.value, ensure_ascii=False)
        existing = self._get_raw(conn, entry.project_id, entry.key)
        version = entry.version
        created_at = now
        if existing:
            created_at = existing["created_at"]
            version = existing["version"] + 1
        conn.execute(
            "INSERT INTO memory_entries (key, value_json, asset_type, category, confidence, status, visibility, sensitivity, project_id, agent_id, source_ref, source_digest, created_by, expires_at, created_at, updated_at, access_count, version, tags_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id, key) DO UPDATE SET value_json=excluded.value_json, asset_type=excluded.asset_type, category=excluded.category, confidence=excluded.confidence, status=excluded.status, visibility=excluded.visibility, sensitivity=excluded.sensitivity, updated_at=excluded.updated_at, version=excluded.version, tags_json=excluded.tags_json",
            (entry.key, val_json, entry.asset_type, entry.category, entry.confidence, entry.status, entry.visibility, entry.sensitivity, entry.project_id, entry.agent_id, entry.source_ref, entry.source_digest, entry.created_by, entry.expires_at, created_at, now, 0, version, tags_json)
        )
        conn.commit()

    def recall(self, project_id, key, agent_id=None):
        entry = self.get(project_id, key, agent_id)
        return entry.value if entry else None

    def get(self, project_id, key, agent_id=None):
        conn = self._conn(project_id)
        row = self._get_raw(conn, project_id, key)
        if not row: return None
        entry = self._row_to_entry(row)
        if agent_id and not self._can_access(entry, agent_id): return None
        conn.execute("UPDATE memory_entries SET access_count = access_count + 1 WHERE project_id = ? AND key = ?", (project_id, key))
        conn.commit()
        return entry

    def delete(self, project_id, key):
        conn = self._conn(project_id)
        cur = conn.execute("DELETE FROM memory_entries WHERE project_id = ? AND key = ?", (project_id, key))
        conn.commit()
        return cur.rowcount > 0

    def search(self, project_id, query="", asset_type=None, status=None, visibility=None, agent_id=None, limit=50):
        conn = self._conn(project_id)
        sql = "SELECT * FROM memory_entries WHERE project_id = ?"
        params = [project_id]
        if asset_type: sql += " AND asset_type = ?"; params.append(asset_type)
        if status: sql += " AND status = ?"; params.append(status)
        if visibility: sql += " AND visibility = ?"; params.append(visibility)
        if query:
            sql += " AND (key LIKE ? OR category LIKE ? OR tags_json LIKE ?)"
            like = f"%{query}%"; params.extend([like, like, like])
        sql += " ORDER BY confidence * access_count DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        entries = [self._row_to_entry(r) for r in rows]
        if agent_id: entries = [e for e in entries if self._can_access(e, agent_id)]
        return entries

    def list_projects(self):
        rows = []
        for p in self.base.glob("*.sqlite"):
            pid = p.stem
            conn = self._conn(pid)
            r = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()
            if r[0] > 0: rows.append(pid)
        return sorted(rows)

    def transition(self, project_id, key, new_status, actor_id=""):
        entry = self.get(project_id, key)
        if not entry: return False
        current = MemoryStatus(entry.status)
        target = MemoryStatus(new_status)
        if current.frozen(): return False
        if target not in current.allowed_transitions(): return False
        conn = self._conn(project_id)
        conn.execute("UPDATE memory_entries SET status = ?, updated_at = ?, created_by = ? WHERE project_id = ? AND key = ?", (new_status, time.time(), actor_id, project_id, key))
        conn.commit()
        return True

    def prune_expired(self, project_id):
        conn = self._conn(project_id)
        cur = conn.execute("DELETE FROM memory_entries WHERE project_id = ? AND expires_at IS NOT NULL AND expires_at < ?", (project_id, time.time()))
        conn.commit()
        return cur.rowcount

    def stats(self, project_id):
        conn = self._conn(project_id)
        total = conn.execute("SELECT COUNT(*) FROM memory_entries WHERE project_id = ?", (project_id,)).fetchone()[0]
        by_status = dict(conn.execute("SELECT status, COUNT(*) FROM memory_entries WHERE project_id = ? GROUP BY status", (project_id,)).fetchall())
        by_asset = dict(conn.execute("SELECT asset_type, COUNT(*) FROM memory_entries WHERE project_id = ? GROUP BY asset_type", (project_id,)).fetchall())
        expired_count = self.prune_expired(project_id)
        return {"project_id": project_id, "total": total, "by_status": by_status, "by_asset": by_asset, "expired_pruned": expired_count, "db_path": str(self._db_path(project_id))}

    def _get_raw(self, conn, project_id, key):
        return conn.execute("SELECT * FROM memory_entries WHERE project_id = ? AND key = ?", (project_id, key)).fetchone()

    def _row_to_entry(self, row):
        tags = json.loads(row["tags_json"]) if isinstance(row["tags_json"], str) else row["tags_json"]
        return MemoryEntry(key=row["key"], value=json.loads(row["value_json"]), asset_type=row["asset_type"], category=row["category"], confidence=row["confidence"], status=row["status"], visibility=row["visibility"], sensitivity=row["sensitivity"], project_id=row["project_id"], agent_id=row["agent_id"], source_ref=row["source_ref"], source_digest=row["source_digest"], created_by=row["created_by"], expires_at=row["expires_at"], created_at=row["created_at"], updated_at=row["updated_at"], access_count=row["access_count"], version=row["version"], tags=tags)

    def _can_access(self, entry, agent_id):
        if entry.visibility == MemoryVisibility.PRIVATE.value:
            return entry.agent_id == agent_id
        return True

    def context_bundle(self, project_id, agent_id, max_entries=10):
        entries = self.search(project_id=project_id, status="promoted", agent_id=agent_id, limit=max_entries)
        private_entries = self.search(project_id=project_id, visibility="private", agent_id=agent_id, limit=max_entries)
        seen = {e.key for e in entries}
        for pe in private_entries:
            if pe.key not in seen: entries.append(pe); seen.add(pe.key)
        return [{"key": e.key, "value": e.value, "type": e.asset_type, "confidence": e.confidence, "tags": e.tags} for e in entries[:max_entries]]

__all__ = ["MemoryStore", "MemoryAccessError"]