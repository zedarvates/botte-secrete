"""Adapters between Factory Assurance and capability/effect contracts.

The adapters validate the shared capability/effect schemas. Their reduction
does not authenticate a producer or verify that bound sources are current.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


def _strict_json(raw: str) -> Any:
    """Reject ambiguous verdicts and values outside the JSON data model."""
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def constant(_value):
        raise ValueError("non-finite JSON number")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def _hex_digest(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length or any(
        ch not in "0123456789abcdef" for ch in value.lower()
    ):
        raise ValueError(f"{label} must be a {length}-character hex digest")
    return value.lower()


def _load_object(path: str | Path) -> dict[str, Any]:
    value = _strict_json(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object")
    return value


def declaration_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _effect_reference(digest: str, pointer: str) -> str:
    """A pointer is local to one immutable declaration, not a global effect ID."""
    return f"sha256:{digest}#{pointer}"


def effect_manifest_to_assurance(path: str | Path) -> dict[str, Any]:
    """Return the deterministic effect subset needed by Factory Assurance."""
    value = _load_object(path)
    from skills.capabilities.effects import validate_contract

    if validate_contract(value):
        raise ValueError("invalid capability effect contract")

    fingerprint = declaration_digest(value)
    declared: list[str] = []
    for group in ("expected_effects", "downstream_effects"):
        items = value.get(group, [])
        if not isinstance(items, list):
            raise ValueError(f"{group} must be a list")
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not str(item.get("effect") or "").strip():
                raise ValueError(f"invalid {group}[{index}]")
            declared.append(_effect_reference(fingerprint, f"/{group}/{index}"))

    return {
        "capability_id": value.get("capability_id"),
        "contract_version": value.get("contract_version"),
        "declaration_digest": fingerprint,
        "declared": declared,
        "preconditions": list(value.get("preconditions") or []),
        "required_scope": value.get("required_scope"),
        "reversibility": value.get("reversibility"),
        "retry": value.get("retry"),
    }


def observation_to_effects(path: str | Path) -> dict[str, Any]:
    """Reduce validated observation v1/v2 evidence without losing failures."""
    value = _load_object(path)
    from skills.capabilities.observations import validate_report

    if validate_report(value):
        raise ValueError("invalid effect observation report")

    observed: set[str] = set()
    unresolved: list[str] = []
    calls = {call["id"]: call for call in value["calls"]}
    process = value["process"]
    if process["status"] != "exited" or type(process["exit_code"]) is not int or process["exit_code"] != 0:
        unresolved.append("process did not complete successfully")
    for call in value["calls"]:
        if call["status"] != "returned":
            unresolved.append("call failed or is unfinished")
        if call["declaration_status"] != "declared":
            unresolved.append("call declaration is missing, invalid or stale")
    for item in value.get("observations", []):
        if not isinstance(item, dict):
            unresolved.append("malformed observation")
            continue
        ref = item.get("effect_ref")
        if ref:
            ref = _effect_reference(calls[item["call_id"]]["declaration_ref"], ref)
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
        if ref:
            ref = _effect_reference(calls[item["call_id"]]["declaration_ref"], ref)
        if ref and item.get("comparison") == "supported":
            observed.add(str(ref))
        if item.get("remote_effects") == "unknown":
            unresolved.append(str(ref or item.get("id") or "unknown remote effect"))

    unresolved.extend(str(x) for x in value.get("problems", []) if str(x).strip())
    return {"observed": sorted(observed), "unresolved": sorted(set(unresolved))}


def holdout_attestation(*, set_id: str, digest: str, candidate_sha: str,
                        passed: bool, case_count: int) -> dict[str, Any]:
    """Create a public-safe holdout attestation without exposing test cases."""
    digest = _hex_digest(digest, 64, "holdout digest")
    candidate_sha = _hex_digest(candidate_sha, 40, "candidate_sha")
    if type(passed) is not bool:
        raise ValueError("passed must be a boolean")
    if not isinstance(set_id, str) or not set_id.strip() or type(case_count) is not int or case_count < 1:
        raise ValueError("holdout set_id and positive case_count are required")
    return {
        "schema": "botte.factory-holdout-attestation/v1",
        "set_id": set_id,
        "set_digest_sha256": digest,
        "candidate_sha": candidate_sha,
        "case_count": case_count,
        "status": "pass" if passed else "fail",
        "contains_cases": False,
    }
