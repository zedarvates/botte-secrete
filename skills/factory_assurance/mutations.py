"""Small deterministic mutation operators used to prove gates can fail."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def mutate_assurance_record(run: dict[str, Any], operator: str) -> dict[str, Any]:
    value = deepcopy(run)
    if operator == "identity-drift":
        tested = str(value.get("identity", {}).get("tested_sha") or "")
        value.setdefault("identity", {})["tested_sha"] = ("b" * 40 if tested != "b" * 40 else "c" * 40)
    elif operator == "undeclared-effect":
        value.setdefault("effects", {}).setdefault("observed", []).append("/__mutation__/unexpected")
    elif operator == "self-judge":
        builder = value.setdefault("actors", {}).get("builder") or "builder"
        value["actors"]["judge"] = builder
    elif operator == "missing-evidence":
        evidence = value.get("evidence") or []
        if evidence:
            evidence[0]["status"] = "missing"
        else:
            value["evidence"] = [{"name": "mutation-missing", "status": "missing", "required": True}]
    else:
        raise ValueError(f"unknown mutation operator: {operator}")
    return value


MUTATION_OPERATORS = ("identity-drift", "undeclared-effect", "self-judge", "missing-evidence")
