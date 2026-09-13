"""Conservative bridge from assurance decisions to the routing control loop.

It emits telemetry-shaped data only. It never calls control_loop.apply(), never
changes thresholds, and never promotes a change.
"""

from __future__ import annotations

from typing import Any


def control_loop_signal(decision: dict[str, Any]) -> dict[str, Any]:
    status = decision.get("status")
    if status not in {"review_ready", "hold"}:
        raise ValueError("unsupported assurance decision status")
    return {
        "task": f"factory-assurance:{decision.get('action_id') or 'unknown'}",
        "mode": "assurance",
        "success": status == "review_ready",
        "escalated": status == "hold",
        "tokens_saved": 0,
        "tier": "GATED",
        "apply_policy_change": False,
        "may_merge_automatically": False,
        "may_deploy_automatically": False,
    }
