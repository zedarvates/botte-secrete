"""Adapters between Factory Assurance and capability/effect contracts.

The adapter accepts the effect sidecar shape introduced by PR #108 without
importing that draft branch. If the sidecar is absent, callers keep using the
plain Factory Assurance record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _load_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object")
    return value


def declaration_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def effect_manifest_to_assurance(path: str | Path) -> dict[str, Any]:
    """Return the deterministic effect subset needed by Factory Assurance."""
    value = _load_object(path)
    if value.get("schema") != "botte.capability-effects/v1":
        raise ValueError("unsupported capability effect schema")

    declared: list[str] = []
    for group in ("expected_effects", "downstream_effects"):
        items = value.get(group, [])
        if not isinstance(items, list):
            raise ValueError(f"{group} must be a list")
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not str(item.get("effect") or "").strip():
                raise ValueError(f"invalid {group}[{index}]")
            declared.append(f"/{group}/{index}")

    return {
        "capability_id": value.get("capability_id"),
        "contract_version": value.get("contract_version"),
        "declaration_digest": declaration_digest(value),
        "declared": declared,
        "preconditions": list(value.get("preconditions") or []),
        "required_scope": value.get("required_scope"),
        "reversibility": value.get("reversibility"),
        "retry": value.get("retry"),
    }


def observation_to_effects(path: str | Path) -> dict[str, Any]:
    """Reduce PR #108 observation v1/v2 evidence to observed/unresolved refs."""
    value = _load_object(path)
    if value.get("schema") not in {"botte.effect-observations/v1", "botte.effect-observations/v2"}:
        raise ValueError("unsupported effect observation schema")

    observed: set[str] = set()
    unresolved: list[str] = []
    for item in value.get("observations", []):
        if not isinstance(item, dict):
            unresolved.append("malformed observation")
            continue
        ref = item.get("effect_ref")
        comparison = item.get("comparison")
        if ref and comparison == "supported":
            observed.add(str(ref))
        elif comparison in {"deviation", "unknown"}:
            unresolved.append(str(ref or item.get("id") or "unknown observation"))

    for item in value.get("network", []):
        if not isinstance(item, dict):
            unresolved.append("malformed network observation")
            continue
        ref = item.get("effect_ref")
        if ref and item.get("comparison") == "supported":
            observed.add(str(ref))
        if item.get("remote_effects") == "unknown":
            unresolved.append(str(ref or item.get("id") or "unknown remote effect"))

    unresolved.extend(str(x) for x in value.get("problems", []) if str(x).strip())
    return {"observed": sorted(observed), "unresolved": sorted(set(unresolved))}


def holdout_attestation(*, set_id: str, digest: str, candidate_sha: str,
                        passed: bool, case_count: int) -> dict[str, Any]:
    """Create a public-safe holdout attestation without exposing test cases."""
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        raise ValueError("holdout digest must be a SHA-256 hex digest")
    if len(candidate_sha) != 40 or any(ch not in "0123456789abcdef" for ch in candidate_sha.lower()):
        raise ValueError("candidate_sha must be a 40-character git SHA")
    if not set_id.strip() or case_count < 1:
        raise ValueError("holdout set_id and positive case_count are required")
    return {
        "schema": "botte.factory-holdout-attestation/v1",
        "set_id": set_id,
        "set_digest_sha256": digest.lower(),
        "candidate_sha": candidate_sha.lower(),
        "case_count": int(case_count),
        "status": "pass" if passed else "fail",
        "contains_cases": False,
    }
