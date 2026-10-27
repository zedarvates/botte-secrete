"""Fail-closed checks that distinguish a real migration from a compatibility shim."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any


SPEC_SCHEMA = "botte.migration-audit-spec/v1"
AUDIT_SCHEMA = "botte.migration-audit/v1"
_KINDS = {
    "text_absent", "text_present", "path_absent", "path_present",
    "paths_not_both",
}
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_MIGRATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}$")
_IGNORED_DIRS = {
    ".git", ".botte-cache", ".botte-sandbox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "__pycache__", "node_modules", "vendor",
}
_CHECK_KEYS = {"id", "kind", "pattern", "include", "path", "paths"}
_SPEC_KEYS = {"schema", "migration_id", "checks", "max_files", "max_file_bytes"}


def _relative(value: object, name: str, *, allow_glob: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or "\\" in value:
        raise ValueError(f"{name} must be a bounded POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"{name} must stay inside the project root")
    if not allow_glob and any(char in value for char in "*?["):
        raise ValueError(f"{name} must not contain glob characters")
    return value


def _validated(spec: object) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("migration audit spec must be a JSON object")
    unknown = set(spec) - _SPEC_KEYS
    if unknown:
        raise ValueError(f"unknown spec fields: {', '.join(sorted(unknown))}")
    if spec.get("schema") != SPEC_SCHEMA:
        raise ValueError(f"schema must be {SPEC_SCHEMA}")
    migration_id = spec.get("migration_id")
    if not isinstance(migration_id, str) or not _MIGRATION_ID.fullmatch(migration_id):
        raise ValueError("migration_id must be an opaque 1-128 character identifier")
    checks = spec.get("checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= 100:
        raise ValueError("checks must contain between 1 and 100 entries")
    seen: set[str] = set()
    clean_checks: list[dict[str, Any]] = []
    for index, raw in enumerate(checks):
        if not isinstance(raw, dict) or set(raw) - _CHECK_KEYS:
            raise ValueError(f"checks[{index}] contains unknown or invalid fields")
        check_id = raw.get("id")
        kind = raw.get("kind")
        if not isinstance(check_id, str) or not _ID.fullmatch(check_id) or check_id in seen:
            raise ValueError(f"checks[{index}].id must be unique and machine-safe")
        if kind not in _KINDS:
            raise ValueError(f"checks[{index}].kind is unsupported")
        allowed = (
            {"id", "kind", "pattern", "include"} if kind.startswith("text_")
            else {"id", "kind", "path"} if kind in ("path_absent", "path_present")
            else {"id", "kind", "paths"}
        )
        if set(raw) - allowed:
            raise ValueError(f"checks[{index}] contains fields invalid for {kind}")
        seen.add(check_id)
        check: dict[str, Any] = {"id": check_id, "kind": kind}
        if kind.startswith("text_"):
            pattern = raw.get("pattern")
            includes = raw.get("include", ["**/*"])
            if not isinstance(pattern, str) or not 1 <= len(pattern) <= 256:
                raise ValueError(f"checks[{index}].pattern must be a bounded literal")
            if not isinstance(includes, list) or not 1 <= len(includes) <= 20:
                raise ValueError(f"checks[{index}].include must be a bounded list")
            check["pattern"] = pattern
            check["include"] = [
                _relative(item, f"checks[{index}].include", allow_glob=True)
                for item in includes
            ]
        elif kind in ("path_absent", "path_present"):
            check["path"] = _relative(raw.get("path"), f"checks[{index}].path")
        else:
            paths = raw.get("paths")
            if not isinstance(paths, list) or len(paths) != 2:
                raise ValueError(f"checks[{index}].paths must contain exactly two paths")
            check["paths"] = [
                _relative(item, f"checks[{index}].paths") for item in paths
            ]
        clean_checks.append(check)
    max_files = spec.get("max_files", 5000)
    max_file_bytes = spec.get("max_file_bytes", 1_048_576)
    if not isinstance(max_files, int) or isinstance(max_files, bool) or not 1 <= max_files <= 10_000:
        raise ValueError("max_files must be an integer between 1 and 10000")
    if (not isinstance(max_file_bytes, int) or isinstance(max_file_bytes, bool)
            or not 128 <= max_file_bytes <= 2_097_152):
        raise ValueError("max_file_bytes must be between 128 and 2097152")
    return {
        "migration_id": migration_id,
        "checks": clean_checks,
        "max_files": max_files,
        "max_file_bytes": max_file_bytes,
    }


def _files(root: Path, limit: int) -> tuple[list[tuple[str, Path]], bool, list[str]]:
    rows: list[tuple[str, Path]] = []
    unsafe: list[str] = []
    root_real = root.resolve()
    for current, dirs, files in os.walk(root, followlinks=False):
        kept_dirs: list[str] = []
        for dirname in sorted(d for d in dirs if d not in _IGNORED_DIRS):
            directory = Path(current) / dirname
            if directory.is_symlink():
                unsafe.append(directory.relative_to(root).as_posix())
            else:
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for name in sorted(files):
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            try:
                path.resolve().relative_to(root_real)
            except (OSError, ValueError):
                unsafe.append(rel)
                continue
            if len(rows) >= limit:
                return rows, True, unsafe
            rows.append((rel, path))
    return rows, False, unsafe


def _matches(path: str, patterns: list[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(
        candidate.match(pattern)
        or (pattern.startswith("**/") and candidate.match(pattern[3:]))
        for pattern in patterns
    )


def _safe_exists(root: Path, rel: str) -> tuple[bool, bool]:
    path = root / rel
    if not path.exists() and not path.is_symlink():
        return False, True
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return True, False
    return True, True


def _text_check(check: dict[str, Any], files: list[tuple[str, Path]], *,
                max_file_bytes: int, truncated: bool, unsafe: list[str]) -> dict[str, Any]:
    candidates = [(rel, path) for rel, path in files if _matches(rel, check["include"])]
    found: list[str] = []
    unreadable: list[str] = []
    for rel, path in candidates:
        try:
            if path.stat().st_size > max_file_bytes:
                unreadable.append(rel)
                continue
            raw = path.read_bytes()
            if b"\x00" in raw:
                unreadable.append(rel)
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable.append(rel)
            continue
        if check["pattern"] in text:
            found.append(rel)
    uncertainty = bool(unreadable or unsafe or truncated)
    wants_absence = check["kind"] == "text_absent"
    if wants_absence and found:
        status, reason = "FAIL", "forbidden_text_present"
    elif not wants_absence and found:
        status, reason = "PASS", "required_text_present"
    elif uncertainty:
        status, reason = "UNCERTAIN", "scan_incomplete"
    elif wants_absence:
        status, reason = "PASS", "forbidden_text_absent"
    else:
        status, reason = "FAIL", "required_text_missing"
    evidence_paths = sorted(set(found + unreadable + unsafe))[:20]
    return {
        "id": check["id"], "kind": check["kind"], "status": status,
        "reason_code": reason, "matched_files": len(found),
        "candidate_files": len(candidates), "paths": evidence_paths,
    }


def _path_check(check: dict[str, Any], root: Path) -> dict[str, Any]:
    rels = [check["path"]] if check["kind"] in ("path_absent", "path_present") else check["paths"]
    observations = [_safe_exists(root, rel) for rel in rels]
    if not all(safe for _, safe in observations):
        status, reason = "UNCERTAIN", "path_escapes_root"
    elif check["kind"] == "path_absent":
        status = "FAIL" if observations[0][0] else "PASS"
        reason = "forbidden_path_present" if status == "FAIL" else "forbidden_path_absent"
    elif check["kind"] == "path_present":
        status = "PASS" if observations[0][0] else "FAIL"
        reason = "required_path_present" if status == "PASS" else "required_path_missing"
    else:
        both = all(exists for exists, _ in observations)
        status, reason = ("FAIL", "old_and_new_paths_coexist") if both else ("PASS", "paths_not_duplicated")
    return {
        "id": check["id"], "kind": check["kind"], "status": status,
        "reason_code": reason, "matched_files": sum(exists for exists, _ in observations),
        "candidate_files": len(rels), "paths": rels[:20] if status != "PASS" else [],
    }


def audit_migration(spec: object, project_root: str | Path = ".") -> dict[str, Any]:
    """Audit a project without executing its code or trusting its normal tests."""
    clean = _validated(spec)
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError("project_root must be an existing directory")
    files, truncated, unsafe = _files(root, clean["max_files"])
    results = []
    for check in clean["checks"]:
        if check["kind"].startswith("text_"):
            result = _text_check(
                check, files, max_file_bytes=clean["max_file_bytes"],
                truncated=truncated, unsafe=unsafe,
            )
        else:
            result = _path_check(check, root)
        results.append(result)
    statuses = {item["status"] for item in results}
    status = "FAIL" if "FAIL" in statuses else "UNCERTAIN" if "UNCERTAIN" in statuses else "PASS"
    return {
        "schema": AUDIT_SCHEMA,
        "migration_id": clean["migration_id"],
        "status": status,
        "reason_code": {
            "PASS": "migration_complete",
            "FAIL": "migration_incomplete",
            "UNCERTAIN": "evidence_incomplete",
        }[status],
        "checks": results,
        "summary": {
            "total": len(results),
            "passed": sum(item["status"] == "PASS" for item in results),
            "failed": sum(item["status"] == "FAIL" for item in results),
            "uncertain": sum(item["status"] == "UNCERTAIN" for item in results),
            "scanned_files": len(files),
            "truncated": truncated,
        },
        "evidence_count": sum(len(item["paths"]) for item in results),
        "authority": "SIMULATE",
        "shadow_only": True,
        "activation_allowed": False,
        "executed_project_code": False,
        "privacy": {"raw_source": False, "matched_text": False, "absolute_paths": False},
    }
