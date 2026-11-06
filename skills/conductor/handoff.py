"""Bind a selected serial candidate to a supplied Conductor execution plan.

Pure stdlib: preparation does not execute, classify, observe files or persist
anything. Matching identifiers bind documents, not command semantics, safety,
cost estimates, caller identity or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from skills.conductor.preferences import _check_python_json
from skills.conductor.selection import validate_selection
from skills.conductor.verified import MAX_DOCUMENT, validate_plan

HANDOFF_SCHEMA = "parcimonia.plan-handoff/v1"
MAX_HANDOFF_BYTES = 2 * MAX_DOCUMENT
LIMITATIONS = (
    "Step identifiers and dependencies do not verify command semantics or goals.",
    "Declared costs are not verified execution costs or guarantees.",
    "Caller identity, user choice authority and execution authority are not verified.",
    "Sources, prerequisites, results and current project files are not checked.",
    "Command safety and effects are not verified; existing execution gates apply.",
)


def _canonical_json(value: Any, label: str, limit: int) -> bytes:
    """Require bounded finite JSON and retain boolean/number distinctions."""
    try:
        _check_python_json(value)
        payload = json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError(f"{label}: expected bounded finite JSON data") from exc
    if len(payload) > limit:
        raise ValueError(f"{label}: exceeds {limit} UTF-8 bytes")
    return payload


def prepare_plan_handoff(request: dict, receipt: dict, execution_plan: dict) -> dict:
    """Validate a current declared choice and bind an intact supplied plan.

    V1 supports exactly one execution step per selected action, in the same
    order, with the same dependency set. Commands and verification contracts
    must come from the trusted task controller; none are inferred here.
    """
    selection = validate_selection(request, receipt)
    _canonical_json(execution_plan, "execution plan", MAX_DOCUMENT)
    plan = deepcopy(execution_plan)
    try:
        validate_plan(plan)
    except (TypeError, ValueError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("execution plan: invalid botte.skill-plan/v1 document") from exc
    candidate_steps = selection["selected_plan"]["steps"]
    if [step["id"] for step in plan["steps"]] != candidate_steps:
        raise ValueError("execution plan: step IDs and order must match the selected candidate")
    actions = {action["id"]: action for action in request["actions"]}
    for step in plan["steps"]:
        if set(step["needs"]) != set(actions[step["id"]]["needs"]):
            raise ValueError("execution plan: dependencies must match the selected actions")
    plan_payload = _canonical_json(plan, "execution plan", MAX_DOCUMENT)
    handoff = {
        "schema": HANDOFF_SCHEMA,
        "status": "prepared_unverified",
        "input_digest": selection["input_digest"],
        "selected_candidate_id": selection["selected_candidate_id"],
        "selection_receipt": selection,
        "execution_plan": plan,
        "execution_plan_sha256": hashlib.sha256(plan_payload).hexdigest(),
        "execution_authorized": False,
        "limitations": list(LIMITATIONS),
    }
    handoff["handoff_id"] = hashlib.sha256(
        _canonical_json(handoff, "plan handoff", MAX_HANDOFF_BYTES)
    ).hexdigest()
    _canonical_json(handoff, "plan handoff", MAX_HANDOFF_BYTES)
    return handoff


def validate_plan_handoff(request: dict, handoff: dict) -> dict:
    """Rebuild a packet and reject changes, stale selections and extra fields.

    Hashes establish content consistency only. A caller can construct another
    consistent packet; this is not authentication or permission to execute.
    """
    if type(handoff) is not dict:
        raise ValueError("plan handoff: expected an object")
    supplied = _canonical_json(handoff, "plan handoff", MAX_HANDOFF_BYTES)
    rebuilt = prepare_plan_handoff(
        request, handoff.get("selection_receipt"), handoff.get("execution_plan"),
    )
    if supplied != _canonical_json(rebuilt, "plan handoff", MAX_HANDOFF_BYTES):
        raise ValueError("plan handoff does not match the current selection and execution plan")
    return rebuilt
