"""Strict Codex/Hermes run manifests mapped to private QA outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from skills.trajectory.outcome import emit_outcome

SCHEMA = "botte.agent-run/v1"
AGENTS = ("codex", "hermes")
_REQUIRED = {"schema", "agent", "execution_id", "task", "route", "status"}
_ALLOWED = _REQUIRED | {
    "task_type", "tags", "verdict", "verified_by", "evidence_refs",
    "quality_score", "risk", "permission_profile", "model", "harness",
    "tool_versions", "duration_ms", "cost_usd", "tokens", "memory_mb",
    "energy_wh", "acted", "abstained", "escalated", "approval_required",
}
_BOOL_FIELDS = {"acted", "abstained", "escalated", "approval_required"}


def emit_agent_run(manifest: Mapping[str, object], *,
                   project_root: str | Path = ".") -> dict:
    """Validate one bounded agent manifest and emit its QA envelope.

    The raw task exists only long enough to derive the privacy-safe fingerprint.
    Unknown fields are rejected so responses, stdout, paths, and other accidental
    payloads cannot silently enter the private outcome contract.
    """
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be an object")
    keys = set(manifest)
    missing = sorted(_REQUIRED - keys)
    unknown = sorted(keys - _ALLOWED)
    if missing:
        raise ValueError(f"manifest missing required fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"manifest contains unsupported fields: {', '.join(unknown)}")
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")
    agent = manifest.get("agent")
    if agent not in AGENTS:
        raise ValueError(f"agent must be one of: {', '.join(AGENTS)}")
    execution_id = manifest.get("execution_id")
    task = manifest.get("task")
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise ValueError("execution_id must be a non-empty string")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    for field in _BOOL_FIELDS & keys:
        if not isinstance(manifest[field], bool):
            raise ValueError(f"{field} must be a boolean")

    result = emit_outcome(
        task,
        project_root=project_root,
        execution_id=execution_id,
        source=agent,
        route=manifest["route"],
        status=manifest["status"],
        task_type=manifest.get("task_type", ""),
        tags=manifest.get("tags", ()),
        verdict=manifest.get("verdict"),
        verified_by=manifest.get("verified_by", ""),
        evidence_refs=manifest.get("evidence_refs", ()),
        quality_score=manifest.get("quality_score"),
        risk=manifest.get("risk", "standard"),
        permission_profile=manifest.get("permission_profile", ""),
        model=manifest.get("model", ""),
        harness=manifest.get("harness", f"{agent}-run-manifest"),
        tool_versions=manifest.get("tool_versions"),
        duration_ms=manifest.get("duration_ms"),
        cost_usd=manifest.get("cost_usd"),
        tokens=manifest.get("tokens"),
        memory_mb=manifest.get("memory_mb"),
        energy_wh=manifest.get("energy_wh"),
        acted=manifest.get("acted", False),
        abstained=manifest.get("abstained", False),
        escalated=manifest.get("escalated", False),
        approval_required=manifest.get("approval_required", False),
    )
    return {"schema": SCHEMA, "agent": agent, **result}


__all__ = ["AGENTS", "SCHEMA", "emit_agent_run"]
