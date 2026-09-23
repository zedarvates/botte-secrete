"""Deterministic, read-only portfolio registry helpers."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Iterator, Mapping

SCHEMA_VERSION = 1
PROJECT_FIELDS = (
    "id",
    "source",
    "visibility",
    "status",
    "priority",
    "confidentiality",
)
DEFAULT_STATUS_VALUES = {
    "active",
    "maintenance",
    "incubation",
    "publication",
    "needs-review",
    "archived",
}
DEFAULT_PRIORITY_VALUES = {
    "critical",
    "high",
    "medium",
    "low",
    "unclassified",
}
VISIBILITY_VALUES = {"public", "private", "restricted"}
CONFIDENTIALITY_VALUES = {"public", "confidential", "restricted"}
SENSITIVE_KEYS = {
    "token",
    "access_token",
    "auth_token",
    "bearer_token",
    "refresh_token",
    "github_token",
    "api_key",
    "apikey",
    "password",
    "passwd",
    "private_key",
    "secret",
    "secrets",
    "secret_key",
    "secret_access_key",
    "client_secret",
    "credentials",
    "ssh_key",
}
SAFE_SENSITIVE_SENTINELS = {
    "",
    "none",
    "null",
    "redacted",
    "never-store",
    "not-stored",
    "env-only",
}
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
GITHUB_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
GITHUB_SOURCE_RE = re.compile(
    r"^github:(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9_.-]+)$"
)


class PortfolioError(ValueError):
    """Raised when a portfolio registry or observed inventory is invalid."""


def _read_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PortfolioError(f"cannot read {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PortfolioError(
            f"invalid JSON in {source} at line {exc.lineno}, column {exc.colno}"
        ) from exc


def _looks_absolute_local_path(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith("file://"):
        return True
    if value.startswith(("~/", "~\\", "\\\\")):
        return True
    if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", value))


def _scan_for_sensitive_values(value: Any, location: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.strip().lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS and child is not None:
                rendered = str(child).strip().lower()
                if rendered not in SAFE_SENSITIVE_SENTINELS:
                    raise PortfolioError(
                        f"sensitive value is forbidden at {location}.{key}"
                    )
            _scan_for_sensitive_values(child, f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _scan_for_sensitive_values(child, f"{location}[{index}]")
        return
    if isinstance(value, str) and _looks_absolute_local_path(value):
        raise PortfolioError(f"absolute local path is forbidden at {location}")


def _string_set(value: Any, fallback: set[str], field: str) -> set[str]:
    if value is None:
        return set(fallback)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise PortfolioError(f"{field} must be a list of non-empty strings")
    values = {item.strip() for item in value}
    if len(values) != len(value):
        raise PortfolioError(f"{field} contains duplicate values")
    return values


def iter_projects(registry: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """Yield ``(program, project)`` pairs in registry order."""
    programs = registry.get("programs")
    if not isinstance(programs, Mapping):
        return
    for program, entries in programs.items():
        if not isinstance(entries, list):
            continue
        for project in entries:
            if isinstance(project, Mapping):
                yield str(program), project


def _is_valid_github_full_name(full_name: str) -> bool:
    if full_name.count("/") != 1:
        return False
    owner, repo = full_name.split("/", 1)
    if not GITHUB_OWNER_RE.fullmatch(owner):
        return False
    if not GITHUB_REPO_RE.fullmatch(repo) or repo in {".", ".."}:
        return False
    return True


def _github_full_name(source: str) -> str | None:
    match = GITHUB_SOURCE_RE.fullmatch(source)
    if not match:
        return None
    full_name = f"{match.group('owner')}/{match.group('repo')}"
    return full_name if _is_valid_github_full_name(full_name) else None


def validate_registry(registry: Any) -> dict[str, Any]:
    """Validate a v1 registry and return a compact, JSON-ready report."""
    if not isinstance(registry, Mapping):
        raise PortfolioError("registry root must be a JSON object")
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise PortfolioError(
            f"schema_version must be {SCHEMA_VERSION}, got "
            f"{registry.get('schema_version')!r}"
        )

    _scan_for_sensitive_values(registry)

    programs = registry.get("programs")
    if not isinstance(programs, Mapping) or not programs:
        raise PortfolioError("programs must be a non-empty object")

    statuses = _string_set(
        registry.get("status_values"),
        DEFAULT_STATUS_VALUES,
        "status_values",
    )
    priorities = _string_set(
        registry.get("priority_values"),
        DEFAULT_PRIORITY_VALUES,
        "priority_values",
    )

    project_ids: set[str] = set()
    github_sources: set[str] = set()
    project_count = 0
    github_count = 0

    for raw_program, entries in programs.items():
        program = str(raw_program).strip()
        if not program:
            raise PortfolioError("program names must be non-empty")
        if not isinstance(entries, list):
            raise PortfolioError(f"program {program!r} must contain a list")

        for index, project in enumerate(entries):
            location = f"programs.{program}[{index}]"
            if not isinstance(project, Mapping):
                raise PortfolioError(f"{location} must be an object")
            missing = [field for field in PROJECT_FIELDS if field not in project]
            if missing:
                raise PortfolioError(
                    f"{location} is missing required fields: {', '.join(missing)}"
                )

            for field in PROJECT_FIELDS:
                if not isinstance(project[field], str) or not project[field].strip():
                    raise PortfolioError(f"{location}.{field} must be a non-empty string")

            project_id = project["id"].strip()
            if not PROJECT_ID_RE.fullmatch(project_id):
                raise PortfolioError(f"{location}.id has an invalid format")
            if project_id in project_ids:
                raise PortfolioError(f"duplicate project id: {project_id}")
            project_ids.add(project_id)

            status = project["status"].strip()
            priority = project["priority"].strip()
            visibility = project["visibility"].strip()
            confidentiality = project["confidentiality"].strip()
            if status not in statuses:
                raise PortfolioError(f"{location}.status is not declared: {status}")
            if priority not in priorities:
                raise PortfolioError(f"{location}.priority is not declared: {priority}")
            if visibility not in VISIBILITY_VALUES:
                raise PortfolioError(f"{location}.visibility is invalid: {visibility}")
            if confidentiality not in CONFIDENTIALITY_VALUES:
                raise PortfolioError(
                    f"{location}.confidentiality is invalid: {confidentiality}"
                )

            source = project["source"].strip()
            github_name = _github_full_name(source)
            if source.startswith("github:") and github_name is None:
                raise PortfolioError(f"{location}.source has an invalid GitHub form")
            if github_name is not None:
                canonical = github_name.casefold()
                if canonical in github_sources:
                    raise PortfolioError(f"duplicate GitHub source: {github_name}")
                github_sources.add(canonical)
                github_count += 1

            project_count += 1

    return {
        "valid": True,
        "schema_version": SCHEMA_VERSION,
        "programs": len(programs),
        "projects": project_count,
        "github_projects": github_count,
        "non_github_projects": project_count - github_count,
    }


def load_registry(path: str | Path) -> dict[str, Any]:
    """Load and validate a portfolio registry without modifying it."""
    value = _read_json(path)
    validate_registry(value)
    return dict(value)


def summarize_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic counts for a validated registry."""
    validation = validate_registry(registry)
    by_status: Counter[str] = Counter()
    by_priority: Counter[str] = Counter()
    by_visibility: Counter[str] = Counter()
    by_confidentiality: Counter[str] = Counter()
    by_program: Counter[str] = Counter()
    by_source_type: Counter[str] = Counter()

    for program, project in iter_projects(registry):
        by_program[program] += 1
        by_status[project["status"]] += 1
        by_priority[project["priority"]] += 1
        by_visibility[project["visibility"]] += 1
        by_confidentiality[project["confidentiality"]] += 1
        source = project["source"]
        by_source_type[
            "github" if source.startswith("github:") else source
        ] += 1

    def ordered(counter: Counter[str]) -> dict[str, int]:
        return dict(sorted(counter.items()))

    return {
        **validation,
        "by_program": ordered(by_program),
        "by_status": ordered(by_status),
        "by_priority": ordered(by_priority),
        "by_visibility": ordered(by_visibility),
        "by_confidentiality": ordered(by_confidentiality),
        "by_source_type": ordered(by_source_type),
    }


def _inventory_entries(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        for key in ("repositories", "items", "repos"):
            entries = value.get(key)
            if isinstance(entries, list):
                return entries
    raise PortfolioError(
        "observed inventory must be a list or an object containing "
        "repositories/items/repos"
    )


def _normalize_observed_entry(entry: Any, owner: str | None) -> dict[str, Any]:
    if isinstance(entry, str):
        full_name = entry.strip()
        if "/" not in full_name and owner:
            full_name = f"{owner}/{full_name}"
        if not _is_valid_github_full_name(full_name):
            raise PortfolioError(f"invalid observed repository name: {entry!r}")
        return {"full_name": full_name, "visibility": None, "archived": None}

    if not isinstance(entry, Mapping):
        raise PortfolioError("observed repository entries must be strings or objects")

    full_name = str(entry.get("full_name") or "").strip()
    if not full_name:
        name = str(entry.get("name") or "").strip()
        observed_owner = entry.get("owner")
        if isinstance(observed_owner, Mapping):
            observed_owner = observed_owner.get("login")
        observed_owner = str(observed_owner or owner or "").strip()
        if name and observed_owner:
            full_name = f"{observed_owner}/{name}"
    if not _is_valid_github_full_name(full_name):
        raise PortfolioError(f"observed repository lacks a valid full_name: {entry!r}")

    visibility = entry.get("visibility")
    if visibility is None and isinstance(entry.get("private"), bool):
        visibility = "private" if entry["private"] else "public"
    if visibility is not None:
        visibility = str(visibility).strip().lower()
        if visibility not in {"public", "private", "internal"}:
            raise PortfolioError(
                f"invalid observed visibility for {full_name}: {visibility}"
            )

    archived = entry.get("archived")
    if archived is not None and not isinstance(archived, bool):
        raise PortfolioError(f"archived must be boolean for {full_name}")

    return {
        "full_name": full_name,
        "visibility": visibility,
        "archived": archived,
    }


def load_observed_inventory(
    path: str | Path,
    owner: str | None = None,
) -> list[dict[str, Any]]:
    """Load a sanitized GitHub inventory snapshot from disk."""
    value = _read_json(path)
    entries = [
        _normalize_observed_entry(entry, owner)
        for entry in _inventory_entries(value)
    ]
    names = [entry["full_name"].casefold() for entry in entries]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise PortfolioError(
            f"observed inventory contains duplicate repositories: {', '.join(duplicates)}"
        )
    return entries


def compare_github_inventory(
    registry: Mapping[str, Any],
    observed: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare a registry with a pre-fetched GitHub inventory.

    This function performs no network request and no write. The caller is
    responsible for producing the observed inventory snapshot.
    """
    validate_registry(registry)

    registered: dict[str, dict[str, Any]] = {}
    for program, project in iter_projects(registry):
        full_name = _github_full_name(project["source"])
        if full_name is None:
            continue
        registered[full_name.casefold()] = {
            "full_name": full_name,
            "project_id": project["id"],
            "program": program,
            "visibility": project["visibility"],
            "status": project["status"],
        }

    normalized_observed: dict[str, dict[str, Any]] = {}
    owner = str(registry.get("owner") or "").strip() or None
    for raw_entry in observed:
        entry = _normalize_observed_entry(raw_entry, owner)
        key = entry["full_name"].casefold()
        if key in normalized_observed:
            raise PortfolioError(f"duplicate observed repository: {entry['full_name']}")
        normalized_observed[key] = entry

    missing_in_registry = [
        normalized_observed[key]["full_name"]
        for key in sorted(set(normalized_observed) - set(registered))
    ]
    registered_not_observed = [
        registered[key]["full_name"]
        for key in sorted(set(registered) - set(normalized_observed))
    ]

    visibility_mismatches: list[dict[str, str]] = []
    archive_mismatches: list[dict[str, Any]] = []
    for key in sorted(set(registered) & set(normalized_observed)):
        expected = registered[key]
        actual = normalized_observed[key]
        observed_visibility = actual.get("visibility")
        if (
            observed_visibility in {"public", "private"}
            and expected["visibility"] in {"public", "private"}
            and observed_visibility != expected["visibility"]
        ):
            visibility_mismatches.append(
                {
                    "full_name": expected["full_name"],
                    "project_id": expected["project_id"],
                    "registry": expected["visibility"],
                    "observed": observed_visibility,
                }
            )

        observed_archived = actual.get("archived")
        registry_archived = expected["status"] == "archived"
        if observed_archived is not None and observed_archived != registry_archived:
            archive_mismatches.append(
                {
                    "full_name": expected["full_name"],
                    "project_id": expected["project_id"],
                    "registry_status": expected["status"],
                    "observed_archived": observed_archived,
                }
            )

    matched = len(set(registered) & set(normalized_observed))
    drift_count = (
        len(missing_in_registry)
        + len(registered_not_observed)
        + len(visibility_mismatches)
        + len(archive_mismatches)
    )
    return {
        "read_only": True,
        "matched": matched,
        "registered_github": len(registered),
        "observed_github": len(normalized_observed),
        "drift_count": drift_count,
        "clean": drift_count == 0,
        "missing_in_registry": missing_in_registry,
        "registered_not_observed": registered_not_observed,
        "visibility_mismatches": visibility_mismatches,
        "archive_mismatches": archive_mismatches,
    }
