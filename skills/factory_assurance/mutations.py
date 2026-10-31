"""Small deterministic mutation operators used to prove gates can fail."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def mutate_assurance_record(run: dict[str, Any], operator: str) -> dict[str, Any]:
    value = deepcopy(run)
    if operator == "identity-drift":
        identity = value.setdefault("identity", {})
        commits = [identity.get(key) for key in ("source_sha", "build_sha", "tested_sha")]
        identity["tested_sha"] = next(ch * 40 for ch in "abcdef" if ch * 40 not in commits)
        if "tested_tree" in identity:
            trees = [identity.get(key) for key in ("source_tree", "build_tree", "tested_tree")]
            identity["tested_tree"] = next(ch * 40 for ch in "abcdef" if ch * 40 not in trees)
    elif operator == "undeclared-effect":
        value.setdefault("effects", {}).setdefault("observed", []).append("/__mutation__/unexpected")
    elif operator == "self-judge":
        builder = value.setdefault("actors", {}).get("builder") or "builder"
        value["actors"]["judge"] = builder
    elif operator == "missing-evidence":
        evidence = value.setdefault("evidence", [])
        required = next((item for item in evidence if item.get("required", True) is True), None)
        if required is not None:
            required["status"] = "missing"
        else:
            evidence.append({"name": "mutation-missing", "status": "missing", "required": True})
    else:
        raise ValueError(f"unknown mutation operator: {operator}")
    return value


MUTATION_OPERATORS = ("identity-drift", "undeclared-effect", "self-judge", "missing-evidence")
