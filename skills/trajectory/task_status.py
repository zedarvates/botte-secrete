"""Passive task-plane status packets derived from private QA outcomes."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from skills.trajectory.outcome import load_outcomes

SCHEMA = "botte.task-quality-status/v1"
_TASK_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}$")
_OUTCOME_ID = re.compile(r"^qo_[0-9a-f]{16}$")


def _select(project_root: str | Path, outcome_id: str | None) -> dict | None:
    rows = load_outcomes(project_root)
    if outcome_id is None:
        return max(rows, key=lambda row: float(row.get("timestamp", 0))) if rows else None
    if not isinstance(outcome_id, str) or not _OUTCOME_ID.fullmatch(outcome_id):
        raise ValueError("outcome_id must match qo_<16 lowercase hex characters>")
    selected = next((row for row in rows if row.get("id") == outcome_id), None)
    if selected is None:
        raise ValueError("outcome_id was not found in the private outcome ledger")
    return selected


def _classification(row: dict | None) -> tuple[str, str, str, str]:
    if row is None:
        return (
            "empty", "no_outcome", "review",
            "Collect an independently verified outcome before changing task state.",
        )
    status = str(row.get("status", "PARTIAL"))
    verified = row.get("verified") is True
    if status == "APPROVAL_REQUIRED":
        return (
            "approval_required", "human_approval_required", "review",
            "Obtain explicit human approval; do not execute or close the task.",
        )
    if status == "ESCALATED":
        return (
            "escalated", "human_review_required", "review",
            "Review the escalation and its evidence before choosing a next step.",
        )
    if status == "ABSTAINED":
        return (
            "abstained", "route_abstained", "review",
            "Keep deterministic control and inspect why the route abstained.",
        )
    if not verified:
        return (
            "collecting", "unverified_observation", "review",
            "Obtain independent evidence; do not treat this observation as a label.",
        )
    if status in ("PASS", "PASS_ROBUST"):
        return (
            "grounded", "verified_pass", "review",
            "Review the verified evidence before a human closes the task.",
        )
    if status == "FAIL":
        return (
            "failing", "verified_failure", "review",
            "Inspect the verified failure evidence and define a safe retry.",
        )
    if status == "UNCERTAIN":
        return (
            "uncertain", "verified_uncertainty", "review",
            "Run an independent replay before accepting or rejecting the result.",
        )
    return (
        "collecting", "incomplete_observation", "review",
        "Collect the missing independent evidence before changing task state.",
    )


def task_quality_status(*, task_ref: str, project_root: str | Path = ".",
                        outcome_id: str | None = None) -> dict:
    """Return a bounded task-plane observation without authorizing a transition.

    ``task_ref`` is an external opaque identifier such as ``kanboard:task:76``.
    It is never interpreted as task text. Evidence references are exported only
    for independently verified outcomes; untrusted observations carry none.
    """
    if not isinstance(task_ref, str) or not _TASK_REF.fullmatch(task_ref):
        raise ValueError(
            "task_ref must be a 1-128 character opaque identifier using "
            "letters, digits, dot, underscore, colon, slash, hash, or hyphen"
        )
    row = _select(project_root, outcome_id)
    state, reason_code, suggested_state, next_action = _classification(row)
    verified = bool(row and row.get("verified") is True)
    refs = row.get("evidence_refs", []) if verified and row else []
    evidence_refs = [str(ref) for ref in refs[:20]] if isinstance(refs, list) else []
    selected_id = str(row.get("id")) if row else None
    identity = f"{task_ref}\n{selected_id or 'empty'}\n{state}"
    status_id = "tqs_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return {
        "schema": SCHEMA,
        "id": status_id,
        "task_ref": task_ref,
        "outcome_id": selected_id,
        "source": str(row.get("source", "")) if row else "",
        "state": state,
        "reason_code": reason_code,
        "next_safe_action": next_action,
        "quality_status": str(row.get("status", "NO_OUTCOME")) if row else "NO_OUTCOME",
        "verification_state": str(row.get("verification_state", "unverified")) if row else "unverified",
        "verified": verified,
        "evidence_refs": evidence_refs,
        "evidence_count": len(evidence_refs),
        "requires_human_review": True,
        "suggested_task_state": suggested_state,
        "task_transition_allowed": False,
        "terminal": False,
        "shadow_only": True,
        "activation_allowed": False,
        "privacy": {
            "raw_task": False,
            "task_fingerprint": False,
            "execution_fingerprint": False,
            "evidence_body": False,
        },
    }


__all__ = ["SCHEMA", "task_quality_status"]
