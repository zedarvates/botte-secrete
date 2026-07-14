"""Compact, deterministic features for future loop-policy evaluation."""

from __future__ import annotations

from typing import Any, Mapping


FEATURE_NAMES = (
    "iteration_ratio", "budget_ratio", "fingerprint_match", "failure_repeat",
    "progress_score", "cache_history", "verification_state", "criticality",
    "local_fail_rate",
)


def _ratio(value: int | float, limit: int | float) -> float:
    if limit <= 0:
        return 1.0 if value > 0 else 0.0
    return max(0.0, min(1.0, float(value) / float(limit)))


def extract_features(
    request: Any,
    state: Any,
    *,
    fingerprint_match: bool = False,
    failure_repeat: bool = False,
    cache_history: float = 0.0,
    verification_state: float = 0.0,
    local_fail_rate: float = 0.0,
) -> dict[str, float]:
    """Build the nine planned features and clamp all values to ``[0, 1]``.

    This function only describes a trajectory; it never recommends an action.
    """
    progress = getattr(getattr(state, "progress", ""), "value", getattr(state, "progress", ""))
    progress_score = {"solved": 1.0, "progress": 0.75, "stalled": 0.25, "regressed": 0.0}.get(progress, 0.0)
    max_tokens = max(0, int(getattr(request, "max_total_tokens", 0)))
    used_tokens = max(0, int(getattr(state, "total_tokens", 0)))
    result = {
        "iteration_ratio": _ratio(getattr(state, "iteration", 0), getattr(request, "max_iterations", 0)),
        "budget_ratio": _ratio(used_tokens, max_tokens),
        "fingerprint_match": float(bool(fingerprint_match)),
        "failure_repeat": float(bool(failure_repeat)),
        "progress_score": progress_score,
        "cache_history": max(0.0, min(1.0, float(cache_history))),
        "verification_state": max(0.0, min(1.0, float(verification_state))),
        "criticality": max(0.0, min(1.0, float(getattr(request, "criticality", 0.0)))),
        "local_fail_rate": max(0.0, min(1.0, float(local_fail_rate))),
    }
    return {name: result[name] for name in FEATURE_NAMES}
