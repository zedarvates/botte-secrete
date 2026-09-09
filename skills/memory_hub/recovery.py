"""Operator-only project snapshots and offline restore candidates; no activation."""
from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import sqlite3
import time
from contextlib import closing, contextmanager
from functools import lru_cache
from pathlib import Path

from skills.memory_hub.schema import FULL_DDL, SCHEMA_VERSION
from skills.memory_hub.shared_contract import PROJECT, decode, encode, validate
from skills.memory_hub.shared_service import _DDL, _digest

FORMAT = "botte.memory-backup/v1"
KEY_TABLES = ("memory_entries", "memory_quarantine", "shared_revisions",
              "shared_vectors", "shared_requests")


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_connection(path):
    # Never create a missing source; immutable=1 would ignore a live WAL.
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected an existing regular SQLite source file")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    conn.execute("PRAGMA trusted_schema = OFF")
    return conn


@contextmanager
def _destination(path):
    root = Path(path)
    root.mkdir(mode=0o700, exist_ok=False)  # No overwrite, including an empty directory.
    try:
        yield root
    except BaseException:
        # Only the fresh directory owned by this invocation can be removed.
        shutil.rmtree(root)
        raise


def _write_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(encode(value).decode("utf-8") + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _copy_database(source, destination):
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    deadline = time.monotonic() + 30

    def progress(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise ValueError("Snapshot exceeded its 30-second copy budget")

    with closing(_read_connection(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst, pages=128, progress=progress, sleep=0.01)
        dst.execute("PRAGMA journal_mode = DELETE")
        dst.execute("PRAGMA synchronous = FULL")


def _columns(conn, table):
    return {(row[1], row[2], row[3], row[5])
            for row in conn.execute(f'PRAGMA table_info("{table}")')}


@lru_cache(maxsize=1)
def _expected_columns():
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.executescript(FULL_DDL + _DDL)
        return {name: _columns(conn, name) for name, in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}


def _verify(conn, project):
    expected = _expected_columns()
    objects = set(conn.execute(
        "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'view', 'trigger')"))
    if objects != {("table", name) for name in expected}:
        raise ValueError("Unsupported memory database schema; no migration is performed")
    if any(_columns(conn, name) != columns for name, columns in expected.items()):
        raise ValueError("Unsupported memory database columns")
    if conn.execute("SELECT MAX(version) FROM _schema").fetchone()[0] != SCHEMA_VERSION:
        raise ValueError("Unsupported memory schema version")
    if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite integrity check failed")
    for table in KEY_TABLES[:2]:
        if conn.execute(f"SELECT 1 FROM {table} WHERE project_id != ? LIMIT 1", (project,)).fetchone():
            raise ValueError("Database contains a different project")


def _ledger(conn):
    rows = dict(conn.execute("SELECT key_digest, forgotten_at FROM shared_tombstones"))
    for digest, timestamp in rows.items():
        if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or not isinstance(timestamp, (float, int))
                or not math.isfinite(timestamp) or timestamp <= 0):
            raise ValueError("Invalid deletion ledger")
    return rows


def _compact(conn):
    # Remove deleted cells/free pages from the NEW file, never from the source.
    conn.commit()
    conn.execute("VACUUM")


def backup_project(directory, project, output):
    """Snapshot one existing service project, including committed WAL contents."""
    validate(PROJECT, project)
    source = Path(directory) / "data" / f"{project}.sqlite"
    with _destination(output) as root:
        database = root / "snapshot.sqlite"
        _copy_database(source, database)
        with closing(sqlite3.connect(database)) as conn:
            conn.execute("PRAGMA trusted_schema = OFF")
            _verify(conn, project)
            _ledger(conn)
            _compact(conn)
        manifest = {"schema": FORMAT, "project_id": project,
                    "created_at": time.time(), "database_sha256": _sha256(database)}
        # A missing final manifest identifies an incomplete/interrupted snapshot.
        _write_json(root / "manifest.json", manifest)
    return {**manifest, "complete": True, "credentials_included": False,
            "encrypted": False, "remote_copy_verified": False}


def _manifest(root):
    path = root / "manifest.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Missing or invalid backup manifest")
    manifest = decode(path.read_text(encoding="utf-8"))
    fields = {"schema", "project_id", "created_at", "database_sha256"}
    if not isinstance(manifest, dict) or set(manifest) != fields or manifest["schema"] != FORMAT:
        raise ValueError("Unsupported backup manifest")
    validate(PROJECT, manifest["project_id"])
    stamp = manifest["created_at"]
    digest = manifest["database_sha256"]
    if (isinstance(stamp, bool) or not isinstance(stamp, (int, float))
            or not math.isfinite(stamp) or stamp <= 0 or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        raise ValueError("Invalid backup metadata")
    return manifest


def restore_project(backup, current_directory, output_data):
    """Prepare a NEW data directory. The operator must keep current writers stopped.

    current_directory is the authoritative service directory, not an older copy.
    The CLI cannot attest its freshness, prevent a later write, or perform cutover.
    """
    root = Path(backup)
    manifest = _manifest(root)
    source = root / "snapshot.sqlite"
    if source.is_symlink() or not source.is_file() or _sha256(source) != manifest["database_sha256"]:
        raise ValueError("Backup checksum mismatch or missing database")
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Backup must be a closed standalone database")
    project = manifest["project_id"]
    current = Path(current_directory) / "data" / f"{project}.sqlite"
    with closing(_read_connection(current)) as conn:
        conn.execute("BEGIN")  # One consistent view of the current deletion ledger.
        _verify(conn, project)
        ledger = _ledger(conn)
        observed_at = time.time()
    with _destination(output_data) as destination:
        database = destination / f"{project}.sqlite"
        # Copy the exact bytes whose digest was checked; recheck the private copy.
        fd = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
            shutil.copyfileobj(src, dst)
        if _sha256(database) != manifest["database_sha256"]:
            raise ValueError("Backup changed during restore")
        with closing(sqlite3.connect(database)) as conn:
            conn.execute("PRAGMA trusted_schema = OFF")
            conn.execute("PRAGMA secure_delete = ON")
            _verify(conn, project)
            old_ledger = _ledger(conn)
            if any(ledger.get(key, 0) < stamp for key, stamp in old_ledger.items()):
                raise ValueError("Current deletion ledger has regressed from the backup")
            keys = conn.execute(" UNION ".join(f"SELECT key FROM {table}" for table in KEY_TABLES)).fetchall()
            removed = 0
            with conn:
                for key, in keys:
                    if _digest([project, key]) in ledger:
                        for table in KEY_TABLES:
                            conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
                        removed += 1
                conn.executemany("INSERT OR REPLACE INTO shared_tombstones VALUES (?, ?)", ledger.items())
            _compact(conn)
            _verify(conn, project)
        result = {"schema": "botte.memory-restore/v1", "complete": True,
                  "project_id": project, "backup_sha256": manifest["database_sha256"],
                  "database_sha256": _sha256(database), "removed_keys": removed,
                  "tombstones": len(ledger), "ledger_observed_at": observed_at,
                  "ledger_sha256": _digest(sorted(ledger.items())),
                  "ledger_freshness_attested": False, "service_activated": False,
                  "credentials_included": False, "post_backup_updates_recovered": False}
        _write_json(destination / "restore.json", result)
    return result
