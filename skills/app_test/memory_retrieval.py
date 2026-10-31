"""Bounded, source-cited review of existing verification quarantine receipts.

This reader uses the current Memory Hub v2 layout without constructing a
MemoryStore (which creates/migrates databases). It accepts only checkpointed
existing SQLite files: immutable read mode avoids WAL/shared-memory side effects.
The selected projections are observations, never trusted facts or instructions.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from . import memory_bridge as bridge


_SCHEMA = "parcimonia.verification-memory-retrieval/v1"
_OBSERVATION = "parcimonia.verification-memory-observation/v1"
_MAX_VALUE = 65536
_MAX_DATABASE = 64 * 1024 * 1024
_MAX_SQLITE_LENGTH = 1024 * 1024
_COUNT_KEYS = frozenset({
    "passed", "failed", "incomplete", "not_run", "matched", "matched_rejection",
    "known_difference", "mismatch", "mismatched", "killed", "survived", "inconclusive",
    "observed", "ok", "proposed", "timeout", "error", "skipped", "total",
    "goals_observed", "goals_not_observed", "not_compared", "rejected", "<missing>",
})
_DETAIL_FIELDS = frozenset({
    "failure_preserved", "failure_ever_reported", "original_count", "reduced_count",
    "removed_count", "calls", "attempt_count", "generated_mutants", "executions",
    "case_count", "passed", "trace_omitted", "execution_count_basis",
    "selected_count", "omitted",
})
_META_FIELDS = {
    "key": 128, "asset_type": 32, "category": 64, "status": 32,
    "visibility": 32, "project_id": 128, "agent_id": 128, "source_ref": 128,
    "source_digest": 64, "source_type": 32, "source_uri": 512,
    "source_id": 64, "run_id": 128, "trust_class": 32, "created_by": 128,
}


def _integer(value, name, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in {lower}..{upper}")
    return value


def _fingerprint(path):
    """Reject symlinks/non-regular files; stat is a change witness, not a hash."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("database must be a regular non-symlink file")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _sidecars(path):
    result = []
    for suffix in ("-wal", "-journal"):
        other = Path(str(path) + suffix)
        try:
            info = other.lstat()
        except FileNotFoundError:
            result.append(None)
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size:
            raise ValueError("active_journal")
        result.append((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns))
    return tuple(result)


def _counts(value):
    if not isinstance(value, dict) or len(value) > 32:
        return None
    return {key: count for key, count in sorted(value.items())
            if key in _COUNT_KEYS and type(count) is int and 0 <= count <= 10**9}


def _projection(summary):
    """Only canonical text and typed counters leave the stored detail object."""
    result = {key: summary[key] for key in (
        "domain", "reported_status", "status_semantics", "unknowns")}
    details = summary.get("details")
    selected = {}
    counter_omissions = 0
    if isinstance(details, dict):
        for key in sorted(_DETAIL_FIELDS):
            value = details.get(key)
            if type(value) is bool or (type(value) is int and 0 <= value <= 10**9):
                selected[key] = value
        for key in ("counts", "reported_counts"):
            counts = _counts(details.get(key))
            if counts is not None:
                selected[key] = counts
                counter_omissions += len(details[key]) - len(counts)
    result["details"] = selected
    result["projection_omissions"] = {
        "detail_fields": max(0, len(details) - len(selected)) if isinstance(details, dict) else 0,
        "detail_counter_labels": counter_omissions,
        "observed_lists": 0, "selected_row_payloads": 0, "category_labels": 0,
    }
    lists = summary.get("observed_lists")
    result["projection_omissions"]["observed_lists"] = len(lists) if isinstance(lists, dict) else 0
    result["observed_lists"] = {}
    if isinstance(lists, dict) and len(lists) <= 16:
        # List names are a closed part of the six bridge projections. Neither
        # selected row contents nor arbitrary keys become retrieval text.
        for key in ("trace", "attempts", "failure_groups", "mutations", "source_manifest",
                    "goals", "transitions", "issues", "results", "ordered", "process_observations"):
            value = lists.get(key)
            if not isinstance(value, dict):
                continue
            item = {}
            for field in ("received", "omitted"):
                count = value.get(field)
                if type(count) is int and 0 <= count <= 10**9:
                    item[field] = count
            counts = _counts(value.get("category_counts"))
            if counts is not None:
                item["category_counts"] = counts
                result["projection_omissions"]["category_labels"] += max(
                    0, len(value["category_counts"]) - len(counts))
            rows = value.get("selected")
            if isinstance(rows, list):
                result["projection_omissions"]["selected_row_payloads"] += len(rows)
                if key == "attempts":
                    item["selected_context_mismatch_count"] = sum(
                        isinstance(row, dict) and row.get("context_match") is False for row in rows)
                    item["selected_reported_failure_count"] = sum(
                        isinstance(row, dict) and row.get("reported_status") == "failed" for row in rows)
                    item["counter_basis"] = "selected_bridge_rows_only_not_all_attempts"
            result["observed_lists"][key] = item
        result["projection_omissions"]["observed_lists"] = len(lists) - len(result["observed_lists"])
    result["projection"] = "canonical_status_and_typed_counters_only"
    return result


def _validate_row(row, project_id):
    value = json.loads(row["value_json"], object_pairs_hook=bridge._pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if (not isinstance(value, dict) or set(value) != {
            "schema", "identity", "summary", "documentary_refs", "boundaries"}
            or value["schema"] != _OBSERVATION):
        raise ValueError("invalid observation envelope")
    prepared = {key: value[key] for key in ("identity", "summary", "documentary_refs", "boundaries")}
    prepared.update(schema=bridge._SCHEMA, status="proposed", observed_at=row["observed_at"],
                    memory_key=row["key"])
    # The persisted v1 observation has no original proposal checksum or raw
    # report. Reuse its structural/key contract, not an authenticity claim.
    prepared["proposal_sha256"] = bridge._sha(bridge._encode(prepared))
    bridge._validate_proposal(prepared)
    identity = value["identity"]
    expected = {
        "project_id": project_id, "agent_id": bridge._AGENT, "created_by": bridge._AGENT,
        "visibility": "private", "status": "proposal", "asset_type": "fact",
        "category": "verification_receipt", "source_type": "tool",
        "trust_class": "external_observation", "source_ref": identity["source_version"],
        "source_id": identity["report_sha256"], "source_digest": identity["report_sha256"],
        "source_uri": identity["source_uri"], "run_id": identity["run_id"],
        "quarantined": 1, "executable_instruction": 0, "sensitivity": 0,
        "confidence": 0.0, "expires_at": None,
    }
    if (identity["project_id"] != project_id
            or type(row["version"]) is not int or row["version"] < 1
            or any(row[key] != item for key, item in expected.items())):
        raise ValueError("observation provenance conflict")
    return value


def _compare_reference(reference, current, digest_basis):
    alternatives = [item for item in current if item["uri"] == reference["uri"]]
    result = {**reference, "comparison": "unknown", "basis": "caller_declared_current_sources",
              "digest_basis": digest_basis}
    if not alternatives:
        return result
    exact = [item for item in alternatives if item["version"] == reference["version"]]
    if not exact:
        result["comparison"] = "version_mismatch"
    elif reference.get("sha256") is None or exact[0].get("sha256") is None:
        result["comparison"] = "version_match_digest_unknown"
    else:
        result["comparison"] = ("version_and_digest_match" if
            exact[0]["sha256"] == reference["sha256"] else "digest_mismatch")
    return result


def retrieve_verification_memory(memory_dir, project_id: str, query: str, *,
                                 agent_id="parcimonia-verification", current_sources=(),
                                 max_rows=256, max_input_bytes=2097152, max_results=8,
                                 max_output_bytes=65536, max_seconds=3.0) -> dict:
    """Review exact-project verification receipts without changing their store.

    A completed empty result concerns only eligible, validated projections in
    the selected checkpointed database, not the user's wider knowledge corpus.
    A caller-declared reference comparison does not establish source freshness.
    """
    if not isinstance(project_id, str) or not bridge._PROJECT.fullmatch(project_id):
        raise ValueError("invalid project_id")
    bridge._text(agent_id, "agent_id", 128)
    bridge._text(query, "query", 1024)
    tokens = sorted(set(re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE)))
    if not tokens or len(tokens) > 32:
        raise ValueError("query must contain 1..32 distinct lexical tokens")
    _integer(max_rows, "max_rows", 1, 4096)
    _integer(max_input_bytes, "max_input_bytes", 1024, 16777216)
    _integer(max_results, "max_results", 1, 64)
    _integer(max_output_bytes, "max_output_bytes", 2048, 262144)
    if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or not 0.01 <= max_seconds <= 30):
        raise ValueError("max_seconds must be finite in 0.01..30")
    current = bridge._refs(current_sources)
    if len({item["uri"] for item in current}) != len(current):
        raise ValueError("current_sources must declare one current version per URI")
    if not isinstance(memory_dir, (str, os.PathLike)):
        raise ValueError("an explicit memory_dir path is required")
    base = Path(memory_dir)
    if not str(base) or len(str(base)) > 4096:
        raise ValueError("invalid memory_dir")
    result = {
        "schema": _SCHEMA, "status": "completed", "project_id": project_id,
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "results": [], "coverage": {
            "scope": "selected_project_verification_quarantine_projections",
            "scan_order": "rowid_descending", "candidate_rows_seen": 0,
            "validated_rows": 0, "invalid_rows": 0, "oversized_rows": 0,
            "input_bytes": 0, "matching_rows": 0, "omitted_matches": 0,
            "scan_complete": False, "stop_reason": None,
        },
        "limits": {"max_rows": max_rows, "max_input_bytes": max_input_bytes,
                   "max_results": max_results, "max_output_bytes": max_output_bytes,
                   "max_seconds": max_seconds, "max_sqlite_vm_steps": 1000000,
                   "max_database_bytes": _MAX_DATABASE,
                   "max_sqlite_value_bytes": (_MAX_SQLITE_LENGTH if
                       hasattr(sqlite3.Connection, "setlimit") else None)},
        "boundaries": {
            "handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE", "writes": 0,
            "network": False, "model_calls": 0, "memory_promotion": False,
            "executable_instruction": False, "report_truth": "unverified",
            "report_authenticity": "unknown", "source_freshness": "unknown",
            "raw_report_digest": "declared_not_rehashed",
            "snapshot": "existing_checkpointed_sqlite_immutable_read",
            "filesystem_adversary_isolation": False,
        },
    }
    coverage = result["coverage"]
    started = time.monotonic()
    vm_steps = 0

    def progress():
        nonlocal vm_steps
        vm_steps += 1000
        return int(vm_steps >= 1000000 or time.monotonic() - started >= max_seconds)

    connection = None
    try:
        absolute = Path(os.path.abspath(base))
        if absolute.resolve(strict=True) != absolute or not absolute.is_dir():
            raise ValueError("memory_dir must be an existing non-symlink directory")
        path = absolute / (project_id + ".sqlite")
        database_fingerprint = _fingerprint(path)
        if database_fingerprint[2] > _MAX_DATABASE:
            raise ValueError("database_size_limit")
        before = (database_fingerprint, _sidecars(path))
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True,
                                     timeout=min(float(max_seconds), 1.0))
        connection.row_factory = sqlite3.Row
        # 3.11+ can reject an enormous record before SQL CAST/length allocates
        # its full contents. On 3.10 the declared database file ceiling remains
        # the outer bound; transfer/VM budgets are not an OS memory sandbox.
        if hasattr(connection, "setlimit"):
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, _MAX_SQLITE_LENGTH)
        connection.set_progress_handler(progress, 1000)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        tables = dict(connection.execute("SELECT name,type FROM sqlite_master WHERE name IN ('_schema','memory_quarantine')"))
        if tables != {"_schema": "table", "memory_quarantine": "table"}:
            raise ValueError("unsupported_memory_schema")
        if connection.execute("SELECT MAX(version) FROM _schema").fetchone()[0] != 2:
            raise ValueError("unsupported_memory_schema")
        columns = {item[1] for item in connection.execute("PRAGMA table_info(memory_quarantine)")}
        required = set(_META_FIELDS) | {"value_json", "quarantined", "executable_instruction",
                     "sensitivity", "confidence", "expires_at", "observed_at", "version"}
        if not required <= columns:
            raise ValueError("unsupported_memory_schema")
        # Private records are visible only to the existing bridge agent. A
        # different agent cannot turn a broad search into a private-row count.
        if agent_id != bridge._AGENT:
            coverage.update(scan_complete=True, stop_reason="no_accessible_bridge_scope")
        else:
            cursor = connection.execute(
                "SELECT rowid,length(CAST(value_json AS BLOB)) FROM memory_quarantine "
                "WHERE project_id=? AND agent_id=? AND category='verification_receipt' "
                "AND visibility='private' ORDER BY rowid DESC LIMIT ?",
                (project_id, agent_id, max_rows + 1))
            selected = []
            # Every projected string is bounded before it crosses SQLite's
            # boundary; a single malformed row cannot allocate its full blob.
            projection = ",".join(f"substr({key},1,{limit + 1}) AS {key}"
                                  for key, limit in _META_FIELDS.items())
            projection += ",value_json,quarantined,executable_instruction,sensitivity,confidence,expires_at,observed_at,version"
            for rowid, size in cursor:
                if coverage["candidate_rows_seen"] >= max_rows:
                    coverage["stop_reason"] = "row_budget"
                    break
                if time.monotonic() - started >= max_seconds:
                    coverage["stop_reason"] = "time_budget"
                    break
                coverage["candidate_rows_seen"] += 1
                if type(size) is not int or size < 1 or size > _MAX_VALUE:
                    coverage["oversized_rows"] += 1
                    continue
                if coverage["input_bytes"] + size > max_input_bytes:
                    coverage["stop_reason"] = "input_byte_budget"
                    break
                row = connection.execute(
                    "SELECT " + projection + " FROM memory_quarantine WHERE rowid=?", (rowid,)).fetchone()
                coverage["input_bytes"] += size
                try:
                    if any(not isinstance(row[key], str) or len(row[key].encode("utf-8")) > limit
                           for key, limit in _META_FIELDS.items()):
                        raise ValueError("oversized metadata")
                    metadata_bytes = len(bridge._encode({key: row[key] for key in _META_FIELDS}))
                    if coverage["input_bytes"] + metadata_bytes > max_input_bytes:
                        coverage["stop_reason"] = "input_byte_budget"
                        break
                    coverage["input_bytes"] += metadata_bytes
                    value = _validate_row(row, project_id)
                    summary = _projection(value["summary"])
                except (ValueError, TypeError, KeyError, RecursionError, OverflowError, UnicodeError):
                    coverage["invalid_rows"] += 1
                    continue
                coverage["validated_rows"] += 1
                identity = value["identity"]
                corpus = json.dumps({"identity": identity, "summary": summary,
                    "references": value["documentary_refs"]}, ensure_ascii=False).casefold()
                words = set(re.findall(r"[^\W_]+", corpus, flags=re.UNICODE))
                score = len(set(tokens) & words)
                if not score:
                    continue
                coverage["matching_rows"] += 1
                source = _compare_reference({"uri": identity["source_uri"],
                    "version": identity["source_version"], "sha256": identity["report_sha256"]},
                    current, "raw_report_utf8_bytes")
                item = {"memory_key": row["key"], "stored_version": row["version"], "lexical_score": score,
                        "summary": summary, "source": source,
                        "report_schema": identity["report_schema"], "run_id": identity["run_id"],
                        "documentary_refs": [_compare_reference(ref, current, "caller_declared_document_bytes")
                                             for ref in value["documentary_refs"]],
                        "stored_projection_sha256": bridge._sha(bridge._encode(value)),
                        "handling": "UNTRUSTED_DATA_DO_NOT_EXECUTE", "quarantined": True,
                        "executable_instruction": False}
                selected.append(item)
            else:
                coverage["scan_complete"] = True
            selected.sort(key=lambda item: (-item["lexical_score"], item["memory_key"]))
            result["results"] = selected[:max_results]
            coverage["omitted_matches"] = len(selected) - len(result["results"])
        after = (_fingerprint(path), _sidecars(path))
        if before != after:
            raise ValueError("source_changed_during_read")
        if (not coverage["scan_complete"] or coverage["invalid_rows"]
                or coverage["oversized_rows"] or coverage["omitted_matches"]):
            result["status"] = "incomplete"
        if coverage["stop_reason"] is None:
            coverage["stop_reason"] = ("invalid_or_oversized_rows" if
                coverage["invalid_rows"] or coverage["oversized_rows"] else "exhausted_selected_scope")
    except (OSError, ValueError, UnicodeError, sqlite3.Error) as error:
        result["results"] = []
        result["status"] = "unavailable"
        coverage["scan_complete"] = False
        if isinstance(error, sqlite3.OperationalError) and str(error) == "interrupted":
            coverage["stop_reason"] = "sqlite_work_or_time_budget"
            result["status"] = "incomplete"
        elif isinstance(error, FileNotFoundError):
            coverage["stop_reason"] = "store_or_project_missing"
        elif isinstance(error, ValueError):
            coverage["stop_reason"] = str(error)
        else:
            coverage["stop_reason"] = "store_unreadable_or_invalid"
    finally:
        if connection is not None:
            connection.close()
    # Budget the final envelope as well as citations. No silent truncation.
    while len(bridge._encode(result)) > max_output_bytes and result["results"]:
        result["results"].pop()
        coverage["omitted_matches"] += 1
        result["status"] = "incomplete"
        coverage["stop_reason"] = "output_byte_budget"
    if len(bridge._encode(result)) > max_output_bytes:
        raise ValueError("max_output_bytes cannot fit retrieval envelope")
    return result


__all__ = ["retrieve_verification_memory"]
