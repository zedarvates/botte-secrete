"""Bind a caller-declared choice to current eligible plan proposals.

Pure stdlib: no persistence, execution, collection, network or model calls.
Hashes detect changed content; they do not authenticate the caller or prove
that a human instructed the choice.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from skills.conductor.preferences import (
    MAX_INPUT_BYTES, REQUEST_SCHEMA, _check_python_json, propose_plans,
)

SELECTION_SCHEMA = "parcimonia.plan-selection/v1"
MAX_RECEIPT_BYTES = MAX_INPUT_BYTES
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _canonical_json(value: Any) -> bytes:
    """Bound JSON data and preserve type differences during exact comparison."""
    _check_python_json(value)
    try:
        payload = json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("selection receipt must be finite JSON data") from exc
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ValueError("selection receipt exceeds 1 MiB UTF-8")
    return payload


def _identifier(value: Any) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("candidate_id: expected a short ASCII identifier")
    return value


def _digest(value: Any) -> str:
    if type(value) is not str or not _DIGEST.fullmatch(value):
        raise ValueError("input_digest: expected a lowercase SHA256 digest")
    return value


def select_plan(request: dict, candidate_id: str, expected_input_digest: str) -> dict:
    """Record one explicit eligible candidate against an exact current digest.

    Dominated and non-recommended options remain selectable. A stale digest,
    absent choice or unavailable candidate fails without choosing a fallback.
    The receipt only records a caller declaration and grants no execution.
    """
    candidate_id = _identifier(candidate_id)
    expected_input_digest = _digest(expected_input_digest)
    proposals = propose_plans(request)
    if proposals["input_digest"] != expected_input_digest:
        raise ValueError("input_digest: stale plan proposals")
    option = next((item for item in proposals["options"]
                   if item["candidate_id"] == candidate_id), None)
    if option is None:
        raise ValueError("candidate_id: candidate is absent or not currently eligible")
    candidate = next(item for item in request["candidates"] if item["id"] == candidate_id)
    selected_plan = {
        "candidate_id": candidate_id,
        "steps": option["steps"],
        "goals": {pid: sorted(goals) for pid, goals in candidate["goals"].items()},
        "projects": [{"id": project["id"], "goals": sorted(project["goals"])}
                     for project in sorted(request["projects"], key=lambda item: item["id"])],
        **{key: option[key] for key in (
            "totals", "project_totals", "unknown_metrics", "shared_actions",
            "goal_coverage",
        )},
    }
    receipt = {
        "schema": SELECTION_SCHEMA,
        "request_schema": REQUEST_SCHEMA,
        "input_digest": proposals["input_digest"],
        "selected_candidate_id": candidate_id,
        "recommended_candidate_id": proposals["recommended_candidate_id"],
        "selected_plan": deepcopy(selected_plan),
        "currency": proposals["currency"],
        "planning_model": proposals["planning_model"],
        "project_cost_allocation": proposals["project_cost_allocation"],
        "project_elapsed_minutes": proposals["project_elapsed_minutes"],
        "choice_origin": "caller_declared",
        "selection_status": "selected",
        "execution_authorized": False,
        "claim": {**proposals["claim"], "choice_authority_verified": False},
        "boundaries": dict(proposals["boundaries"]),
    }
    receipt["selection_id"] = hashlib.sha256(_canonical_json(receipt)).hexdigest()
    _canonical_json(receipt)
    return receipt


def validate_selection(request: dict, receipt: dict) -> dict:
    """Rebuild the current selection and reject altered or additional fields.

    Validation checks content consistency, not authorship or human approval.
    A newly fabricated consistent receipt is still only a caller declaration.
    """
    if type(receipt) is not dict:
        raise ValueError("selection receipt: expected an object")
    supplied = _canonical_json(receipt)
    rebuilt = select_plan(
        request, receipt.get("selected_candidate_id"), receipt.get("input_digest"),
    )
    if supplied != _canonical_json(rebuilt):
        raise ValueError("selection receipt does not match the current declared choice")
    return rebuilt
