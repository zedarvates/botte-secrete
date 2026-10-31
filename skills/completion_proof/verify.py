"""Read-only verification against a receipt digest supplied by a trusted caller.

No commands are executed. A receipt is not an independent attestation: its digest
must come from the test executor, outside the report being checked.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

MAX_JSON = 1_000_000
MAX_FILE = 8_000_000
MAX_TOTAL = 32_000_000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceError(ValueError):
    def __init__(self, code: str, status: str = "invalid_evidence"):
        self.code = code
        self.status = status
        super().__init__(code)


def _digest(value):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise EvidenceError("invalid_sha256")
    return value


def _read(path: Path, limit: int) -> bytes:
    try:
        if not path.is_file():
            raise EvidenceError("missing_file", "missing_evidence")
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
        if len(content) > limit:
            raise EvidenceError("file_too_large")
        return content
    except OSError as exc:
        raise EvidenceError("unreadable_file") from exc


def _scoped(root: Path, reference) -> Path:
    if (not isinstance(reference, str) or not reference
            or "\\" in reference or ":" in reference
            or any(ord(c) < 32 for c in reference)):
        raise EvidenceError("unsafe_reference")
    parts = reference.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise EvidenceError("unsafe_reference")
    if PurePosixPath(reference).is_absolute():
        raise EvidenceError("unsafe_reference")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise EvidenceError("linked_reference")
    try:
        path.resolve().relative_to(root)
    except (ValueError, RuntimeError, OSError) as exc:
        raise EvidenceError("reference_outside_root") from exc
    return path


def _json(data: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise EvidenceError("duplicate_json_key")
            result[key] = value
        return result

    def constant(_value):
        raise EvidenceError("nonfinite_json")

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("invalid_json") from exc
    if not isinstance(value, dict):
        raise EvidenceError("expected_object")
    return value


def verify_report(report: str | Path, *, evidence_root: str | Path,
                  source_root: str | Path, trusted_receipt_sha256: str) -> dict:
    """Verify v1 receipt integrity and its declared source scope, never run code.

    Both roots are explicit caller inputs. Roots/files must stay quiescent during
    verification. Missing trust input cannot be inferred from the report.
    """
    result = {"schema_version": 1, "status": "invalid_evidence", "verified": False,
              "errors": [], "source_files_checked": [], "cloud_tokens": 0,
              "scope": "recorded tests and listed files only"}
    try:
        pin = _digest(trusted_receipt_sha256)
        evidence = Path(evidence_root).resolve(strict=True)
        sources_root = Path(source_root).resolve(strict=True)
        if not evidence.is_dir() or not sources_root.is_dir():
            raise EvidenceError("invalid_root")
        claim = _json(_read(Path(report), MAX_JSON))
        if claim.get("status") != "complete":
            raise EvidenceError("not_a_completion_claim", "announced")
        proof = claim.get("proof")
        if not isinstance(proof, dict) or not proof.get("receipt_ref"):
            raise EvidenceError("missing_receipt_reference", "missing_evidence")
        data = _read(_scoped(evidence, proof["receipt_ref"]), MAX_JSON)
        if hashlib.sha256(data).hexdigest() != pin:
            raise EvidenceError("receipt_hash_mismatch")
        receipt = _json(data)
        if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1:
            raise EvidenceError("unsupported_schema")
        run_id = receipt.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 128:
            raise EvidenceError("invalid_run_id")
        if claim.get("run_id") != run_id:
            raise EvidenceError("run_id_mismatch")
        outcome = receipt.get("result")
        if not isinstance(outcome, dict):
            raise EvidenceError("missing_test_result")
        for key in ("exit_code", "tests_run", "failures", "errors"):
            if type(outcome.get(key)) is not int:
                raise EvidenceError("invalid_test_result")
        skipped = outcome.get("skipped", 0)  # legacy v1 producers did not emit this field
        if type(skipped) is not int or skipped < 0:
            raise EvidenceError("invalid_test_counts")
        if (outcome["tests_run"] <= 0 or outcome["failures"] < 0
                or outcome["errors"] < 0
                or outcome["failures"] + outcome["errors"] + skipped > outcome["tests_run"]):
            raise EvidenceError("invalid_test_counts")
        if skipped == outcome["tests_run"]:
            raise EvidenceError("no_tests_executed")
        log = receipt.get("log")
        if not isinstance(log, dict):
            raise EvidenceError("missing_log")
        log_data = _read(_scoped(evidence, log.get("path")), MAX_FILE)
        if hashlib.sha256(log_data).hexdigest() != _digest(log.get("sha256")):
            raise EvidenceError("log_hash_mismatch")
        source_files = receipt.get("sources")
        if not isinstance(source_files, list) or not 1 <= len(source_files) <= 128:
            raise EvidenceError("invalid_source_scope")
        seen = set()
        total = len(log_data)
        for entry in source_files:
            if not isinstance(entry, dict):
                raise EvidenceError("invalid_source_entry")
            path = _scoped(sources_root, entry.get("path"))
            identity = path.resolve()
            if identity in seen:
                raise EvidenceError("duplicate_source")
            seen.add(identity)
            content = _read(path, min(MAX_FILE, MAX_TOTAL - total))
            total += len(content)
            if hashlib.sha256(content).hexdigest() != _digest(entry.get("sha256")):
                raise EvidenceError("source_hash_mismatch")
            result["source_files_checked"].append(entry["path"])
        result["tests_run"] = outcome["tests_run"]
        result["tests_skipped"] = skipped
        result["tests_executed"] = outcome["tests_run"] - skipped
        result["receipt_sha256"] = pin
        if outcome["exit_code"] != 0 or outcome["failures"] or outcome["errors"]:
            result["status"] = "test_failed"
        else:
            result["status"] = "verified_on_recorded_tests"
            result["verified"] = True
    except EvidenceError as exc:
        result["status"] = exc.status
        result["errors"].append(exc.code)
    except (OSError, RuntimeError, ValueError) as exc:
        result["errors"].append("root_or_io_error")
    return result
