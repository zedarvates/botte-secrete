"""Fail-closed validation for Monte Cristo strategic reports.

The validator deliberately does not execute evidence references or infer missing
fields. Reports are untrusted data and remain proposals until separately approved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_ID = "monte-cristo/v1"
VERDICTS = frozenset({"KEEP", "REPAIR", "REPLACE", "RETIRE", "INVESTIGATE"})
DECISIONS = VERDICTS
PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
PREMISE_STATES = frozenset({"CONFIRMED", "CHALLENGED", "UNKNOWN", "BLOCKED"})
EVIDENCE_KINDS = frozenset({"OBSERVED", "INFERRED", "PROPOSED", "BLOCKED"})
MUTATING_DECISIONS = frozenset({"REPAIR", "REPLACE", "RETIRE"})
MAX_MOVES = 12

_REPORT_KEYS = frozenset({
    "schema", "scope", "verdict", "confidence", "thesis", "preserve",
    "premises", "moves", "unknowns", "counter_case", "next_gate",
})
_PREMISE_KEYS = frozenset({"id", "claim", "status", "evidence"})
_MOVE_KEYS = frozenset({
    "id", "priority", "decision", "target", "rationale", "evidence",
    "blast_radius", "validation", "approval_required",
})
_EVIDENCE_KEYS = frozenset({"kind", "ref", "note"})


class ReportValidationError(ValueError):
    """Raised when a report violates the Monte Cristo contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_keys(value: dict[str, Any], expected: frozenset[str], path: str,
                errors: list[str]) -> None:
    missing = sorted(expected - value.keys())
    unexpected = sorted(value.keys() - expected)
    for key in missing:
        errors.append(f"{path}.{key}: missing")
    for key in unexpected:
        errors.append(f"{path}.{key}: unexpected")


def _validate_evidence(value: Any, path: str, errors: list[str]) -> list[str]:
    observed_refs: list[str] = []
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return observed_refs

    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path}: expected object")
            continue
        _check_keys(item, _EVIDENCE_KEYS, item_path, errors)
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            errors.append(f"{item_path}.kind: invalid evidence kind")
        ref = item.get("ref")
        if not _non_empty_string(ref):
            errors.append(f"{item_path}.ref: expected non-empty string")
        elif kind == "OBSERVED":
            observed_refs.append(ref.strip())
        if not _non_empty_string(item.get("note")):
            errors.append(f"{item_path}.note: expected non-empty string")
    return observed_refs


def _validate_string_list(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return
    for index, item in enumerate(value):
        if not _non_empty_string(item):
            errors.append(f"{path}[{index}]: expected non-empty string")


def validate_report(report: Any) -> list[str]:
    """Return deterministic validation errors; an empty list means valid."""
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["$: expected object"]

    _check_keys(report, _REPORT_KEYS, "$", errors)
    if report.get("schema") != SCHEMA_ID:
        errors.append(f"$.schema: expected {SCHEMA_ID!r}")
    for field in ("scope", "thesis", "counter_case", "next_gate"):
        if not _non_empty_string(report.get(field)):
            errors.append(f"$.{field}: expected non-empty string")

    verdict = report.get("verdict")
    if verdict not in VERDICTS:
        errors.append("$.verdict: invalid verdict")
    confidence = report.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, int):
        errors.append("$.confidence: expected integer")
    elif not 0 <= confidence <= 100:
        errors.append("$.confidence: expected value from 0 to 100")

    _validate_string_list(report.get("preserve"), "$.preserve", errors)
    _validate_string_list(report.get("unknowns"), "$.unknowns", errors)

    observed_refs: list[str] = []
    premises = report.get("premises")
    if not isinstance(premises, list):
        errors.append("$.premises: expected array")
    else:
        seen_ids: set[str] = set()
        for index, premise in enumerate(premises):
            path = f"$.premises[{index}]"
            if not isinstance(premise, dict):
                errors.append(f"{path}: expected object")
                continue
            _check_keys(premise, _PREMISE_KEYS, path, errors)
            premise_id = premise.get("id")
            if not _non_empty_string(premise_id):
                errors.append(f"{path}.id: expected non-empty string")
            elif premise_id in seen_ids:
                errors.append(f"{path}.id: duplicate id")
            else:
                seen_ids.add(premise_id)
            if not _non_empty_string(premise.get("claim")):
                errors.append(f"{path}.claim: expected non-empty string")
            status = premise.get("status")
            if status not in PREMISE_STATES:
                errors.append(f"{path}.status: invalid premise status")
            evidence = premise.get("evidence")
            premise_observed = _validate_evidence(evidence, f"{path}.evidence", errors)
            observed_refs.extend(premise_observed)
            if status in {"CONFIRMED", "CHALLENGED"} and not evidence:
                errors.append(f"{path}.evidence: required for {status}")

    moves = report.get("moves")
    if not isinstance(moves, list):
        errors.append("$.moves: expected array")
    else:
        if len(moves) > MAX_MOVES:
            errors.append(f"$.moves: maximum {MAX_MOVES} items")
        seen_ids: set[str] = set()
        for index, move in enumerate(moves):
            path = f"$.moves[{index}]"
            if not isinstance(move, dict):
                errors.append(f"{path}: expected object")
                continue
            _check_keys(move, _MOVE_KEYS, path, errors)
            move_id = move.get("id")
            if not _non_empty_string(move_id):
                errors.append(f"{path}.id: expected non-empty string")
            elif move_id in seen_ids:
                errors.append(f"{path}.id: duplicate id")
            else:
                seen_ids.add(move_id)
            for field in ("target", "rationale", "blast_radius", "validation"):
                if not _non_empty_string(move.get(field)):
                    errors.append(f"{path}.{field}: expected non-empty string")
            priority = move.get("priority")
            if priority not in PRIORITIES:
                errors.append(f"{path}.priority: invalid priority")
            decision = move.get("decision")
            if decision not in DECISIONS:
                errors.append(f"{path}.decision: invalid decision")
            approval_required = move.get("approval_required")
            if not isinstance(approval_required, bool):
                errors.append(f"{path}.approval_required: expected boolean")
            elif decision in MUTATING_DECISIONS and not approval_required:
                errors.append(
                    f"{path}.approval_required: must be true for {decision}"
                )
            move_observed = _validate_evidence(
                move.get("evidence"), f"{path}.evidence", errors
            )
            observed_refs.extend(move_observed)
            if not move.get("evidence"):
                errors.append(f"{path}.evidence: at least one item required")
            if priority == "P0" and not move_observed:
                errors.append(f"{path}.evidence: P0 requires OBSERVED evidence")

    if verdict != "INVESTIGATE" and isinstance(moves, list) and not moves:
        errors.append("$.moves: decisive verdict requires at least one move")
    if verdict != "INVESTIGATE" and not observed_refs:
        errors.append("$: decisive verdict requires OBSERVED evidence")
    if isinstance(confidence, int) and confidence > 40 and not observed_refs:
        errors.append("$.confidence: without OBSERVED evidence maximum is 40")

    return sorted(set(errors))


def assert_valid_report(report: Any) -> None:
    """Raise :class:`ReportValidationError` when ``report`` is invalid."""
    errors = validate_report(report)
    if errors:
        raise ReportValidationError(errors)


def new_report(scope: str) -> dict[str, Any]:
    """Return a valid, evidence-empty investigation report template."""
    if not _non_empty_string(scope):
        raise ValueError("scope must be a non-empty string")
    return {
        "schema": SCHEMA_ID,
        "scope": scope.strip(),
        "verdict": "INVESTIGATE",
        "confidence": 0,
        "thesis": "No strategic decision before the evidence pass.",
        "preserve": [],
        "premises": [{
            "id": "PR-1",
            "claim": "The current objective and system boundary are correct.",
            "status": "BLOCKED",
            "evidence": [{
                "kind": "BLOCKED",
                "ref": "uncollected",
                "note": "The blind evidence pass has not run yet.",
            }],
        }],
        "moves": [],
        "unknowns": ["Primary evidence has not been collected."],
        "counter_case": "No preferred move exists yet.",
        "next_gate": "Collect at least one OBSERVED item from a primary source.",
    }


def load_report(path: str | Path) -> dict[str, Any]:
    """Load a UTF-8 JSON report without following evidence references."""
    report_path = Path(path)
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportValidationError([f"$: cannot load report: {exc}"]) from exc
    if not isinstance(data, dict):
        raise ReportValidationError(["$: expected object"])
    return data
