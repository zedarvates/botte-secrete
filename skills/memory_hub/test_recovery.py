"""Recovery acceptance: WAL, deletion reconciliation, ACLs and incomplete work."""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
from contextlib import closing

import pytest

from skills.memory_hub import recovery
from skills.memory_hub.shared_service import MemoryService, ServiceError
from skills.memory_hub.test_shared_service import (
    OPERATOR, OTHER, WORKER, capture, promote, recall, record,
)


@pytest.fixture
def current(tmp_path):
    service = MemoryService(tmp_path / "service" / "data")
    capture(service, key="retained")
    return service


def forget(service, key, version=1):
    return service.call("forget", {"project_id": "pilot", "key": key,
                        "request_id": "forget-" + key, "expected_version": version}, OPERATOR)


def snapshot(service, output):
    return recovery.backup_project(service.base_dir.parent, "pilot", output)


def restore(service, backup, output):
    return recovery.restore_project(backup, service.base_dir.parent, output)


def test_roundtrip_preserves_versions_privacy_provenance_receipts_and_forgetting(current, tmp_path):
    promote(current, key="retained")
    private = record("private worker observation", "agent", visibility="private")
    capture(current, key="private", principal=WORKER, data=private)
    erased = record("content-that-must-be-absent-after-restore",
                    embedding={"model": "fixture@1", "vector": [1.0, 0.0]})
    capture(current, key="forgotten", data=erased)
    corrected = record("corrected-content-that-must-also-be-absent",
                       embedding={"model": "fixture@1", "vector": [0.0, 1.0]})
    current.call("correct", {"project_id": "pilot", "key": "forgotten",
                 "request_id": "correction", "expected_version": 1, "record": corrected}, OPERATOR)
    capture(current, key="earlier-deletion")
    forget(current, "earlier-deletion")
    backup = tmp_path / "backup"
    snapshot(current, backup)
    original_backup = (backup / "snapshot.sqlite").read_bytes()
    forget(current, "forgotten", version=2)
    capture(current, key="created-and-forgotten-after-backup")
    forget(current, "created-and-forgotten-after-backup")
    capture(current, key="post-backup")
    output = tmp_path / "restored"
    result = restore(current, backup, output)
    resumed = MemoryService(output)
    assert result["removed_keys"] == 1 and result["tombstones"] == 3
    assert result["service_activated"] is False and result["ledger_freshness_attested"] is False
    assert result["post_backup_updates_recovered"] is False
    assert [e["key"] for e in recall(resumed, OTHER)["entries"]] == ["retained"]
    history = resumed.call("history", {"project_id": "pilot", "key": "retained"}, OPERATOR)
    assert history["revisions"][0]["version"] == 3
    assert len(history["revisions"]) == 3
    assert not recall(resumed, OTHER, area="observations")["entries"]
    visible = recall(resumed, WORKER, area="observations")["entries"]
    assert [e["key"] for e in visible] == ["private"]
    assert visible[0]["provenance"]["trust_class"] == "external_observation"
    assert capture(resumed, "private", WORKER, private)["replayed"] is True
    for key in ("earlier-deletion", "forgotten", "created-and-forgotten-after-backup"):
        with pytest.raises(ServiceError) as error:
            capture(resumed, key, data=erased)
        assert error.value.code == "forgotten"
    with closing(sqlite3.connect(output / "pilot.sqlite")) as conn:
        for table in recovery.KEY_TABLES:
            assert not conn.execute(f"SELECT 1 FROM {table} WHERE key = 'forgotten'").fetchall()
        assert not conn.execute("SELECT 1 FROM memory_entries WHERE key = 'post-backup'").fetchall()
    assert (backup / "snapshot.sqlite").read_bytes() == original_backup
    for path in output.iterdir():
        assert erased["text"].encode() not in path.read_bytes()
        assert corrected["text"].encode() not in path.read_bytes()
    assert "post-backup" in str(current.call("history", {"project_id": "pilot", "key": "post-backup"}, OPERATOR))


def test_backup_reads_committed_wal_and_excludes_credentials(current, tmp_path):
    token = "fixture-credential-never-exported"
    (current.base_dir.parent / "worker.secret").write_text(token, encoding="utf-8")
    database = current.base_dir / "pilot.sqlite"
    with closing(sqlite3.connect(database)) as keeper:
        keeper.execute("PRAGMA journal_mode = WAL")
        keeper.execute("PRAGMA wal_autocheckpoint = 0")
        capture(current, key="in-wal")
        assert (current.base_dir / "pilot.sqlite-wal").stat().st_size > 0
        result = snapshot(current, tmp_path / "backup")
    assert result["complete"] and not result["credentials_included"]
    assert not result["encrypted"] and not result["remote_copy_verified"]
    assert {p.name for p in (tmp_path / "backup").iterdir()} == {"manifest.json", "snapshot.sqlite"}
    with closing(sqlite3.connect(tmp_path / "backup" / "snapshot.sqlite")) as conn:
        assert conn.execute("SELECT 1 FROM memory_entries WHERE key='in-wal'").fetchone()
    for path in (tmp_path / "backup").iterdir():
        assert token.encode() not in path.read_bytes()
        if os.name != "nt":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    if os.name != "nt":
        assert stat.S_IMODE((tmp_path / "backup").stat().st_mode) == 0o700


@pytest.mark.parametrize("change", ["checksum", "manifest", "missing_manifest", "journal", "symlink"])
def test_incomplete_or_changed_backup_is_refused(current, tmp_path, change):
    backup = tmp_path / "backup"
    snapshot(current, backup)
    if change == "checksum":
        with (backup / "snapshot.sqlite").open("ab") as stream:
            stream.write(b"corruption")
    elif change == "manifest":
        (backup / "manifest.json").write_text('{"schema": "other"}', encoding="utf-8")
    elif change == "missing_manifest":
        (backup / "manifest.json").unlink()
    elif change == "journal":
        (backup / "snapshot.sqlite-wal").write_bytes(b"incomplete journal")
    else:
        real = tmp_path / "real.sqlite"
        (backup / "snapshot.sqlite").rename(real)
        (backup / "snapshot.sqlite").symlink_to(real)
    with pytest.raises(ValueError):
        restore(current, backup, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize("change", ["missing", "other_project", "schema", "ledger", "regressed"])
def test_invalid_current_deletion_source_is_refused(current, tmp_path, change):
    capture(current, "deleted-before-backup")
    forget(current, "deleted-before-backup")
    snapshot(current, tmp_path / "backup")
    database = current.base_dir / "pilot.sqlite"
    if change == "missing":
        database.unlink()
    else:
        with closing(sqlite3.connect(database)) as conn, conn:
            if change == "other_project":
                conn.execute("UPDATE memory_entries SET project_id='other'")
            elif change == "schema":
                conn.execute("CREATE TRIGGER extra AFTER DELETE ON memory_entries BEGIN SELECT 1; END")
            elif change == "ledger":
                conn.execute("UPDATE shared_tombstones SET key_digest='invalid'")
            else:
                conn.execute("DELETE FROM shared_tombstones")
    with pytest.raises(ValueError):
        restore(current, tmp_path / "backup", tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    if change == "missing":
        assert not database.exists()


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_existing_destination_is_never_overwritten(current, tmp_path, operation):
    snapshot(current, tmp_path / "backup")
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep unrelated contents", encoding="utf-8")
    with pytest.raises(FileExistsError):
        if operation == "backup":
            snapshot(current, output)
        else:
            restore(current, tmp_path / "backup", output)
    assert marker.read_text(encoding="utf-8") == "keep unrelated contents"


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_interruption_cleans_only_the_new_destination(current, tmp_path, monkeypatch, operation):
    snapshot(current, tmp_path / "backup")

    def interrupted(_conn):
        raise KeyboardInterrupt()

    monkeypatch.setattr(recovery, "_compact", interrupted)
    with pytest.raises(KeyboardInterrupt):
        if operation == "backup":
            snapshot(current, tmp_path / "incomplete")
        else:
            restore(current, tmp_path / "backup", tmp_path / "incomplete")
    assert not (tmp_path / "incomplete").exists()
    assert (tmp_path / "backup" / "manifest.json").is_file()
    assert current.call("history", {"project_id": "pilot", "key": "retained"}, OPERATOR)


def test_cli_roundtrip_and_corruption_error_are_machine_readable(current, tmp_path):
    def cli(*args):
        return subprocess.run([sys.executable, "-m", "skills.memory_hub.cli", *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", timeout=15)

    saved = cli("backup", "--directory", current.base_dir.parent, "--project", "pilot",
                "--output", tmp_path / "backup")
    assert saved.returncode == 0, saved.stderr
    assert json.loads(saved.stdout)["complete"]
    forget(current, "retained")
    restored = cli("restore", "--backup", tmp_path / "backup",
                   "--current-directory", current.base_dir.parent, "--output-data", tmp_path / "restored")
    assert restored.returncode == 0, restored.stderr
    assert json.loads(restored.stdout)["removed_keys"] == 1
    (current.base_dir / "pilot.sqlite").write_bytes(b"not a database")
    failed = cli("backup", "--directory", current.base_dir.parent, "--project", "pilot",
                 "--output", tmp_path / "failed")
    assert failed.returncode == 1 and not failed.stdout
    assert json.loads(failed.stderr)["error"] == "storage"
    assert not (tmp_path / "failed").exists()


def test_cli_interrupt_cannot_report_success(current, tmp_path, monkeypatch, capsys):
    from skills.memory_hub.cli import main

    def interrupted(_conn):
        raise KeyboardInterrupt()

    monkeypatch.setattr(recovery, "_compact", interrupted)
    code = main(["backup", "--directory", str(current.base_dir.parent), "--project", "pilot",
                 "--output", str(tmp_path / "interrupted")])
    result = capsys.readouterr()
    assert code == 130 and not result.out
    assert json.loads(result.err)["error"] == "interrupted"
    assert not (tmp_path / "interrupted").exists()
