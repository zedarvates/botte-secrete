"""Verified trajectory contracts and conservative policy activation gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from skills.atomic_json import write_json
from skills.loop_optimizer.features import FEATURE_NAMES
from skills.loop_optimizer.models import LoopAction

MIN_TRAJECTORIES = 2_000
HOLDOUT_RATIO = 0.20


@dataclass(frozen=True)
class Trajectory:
    features: dict[str, float]
    action: LoopAction
    success: bool
    verified: bool = False

    def __post_init__(self) -> None:
        if tuple(self.features) != FEATURE_NAMES:
            raise ValueError("trajectory features must match FEATURE_NAMES exactly")
        if not self.verified:
            raise ValueError("only verified trajectories may enter the policy dataset")

    def to_dict(self) -> dict[str, Any]:
        return {"features": self.features, "action": self.action.value,
                "success": self.success, "verified": self.verified}


def split_temporal(items: Iterable[Trajectory], holdout_ratio: float = HOLDOUT_RATIO) -> tuple[list[Trajectory], list[Trajectory]]:
    """Keep the newest time-ordered fraction exclusively for holdout evaluation."""
    values = list(items)
    if not values:
        raise ValueError("at least one trajectory is required")
    if not 0.0 < holdout_ratio < 1.0:
        raise ValueError("holdout_ratio must be between 0 and 1")
    cut = max(1, min(len(values) - 1, int(len(values) * (1.0 - holdout_ratio)))) if len(values) > 1 else 1
    return values[:cut], values[cut:]


def save_verified(path: str | Path, trajectories: Iterable[Trajectory]) -> int:
    values = list(trajectories)
    if any(not item.verified for item in values):
        raise ValueError("unverified trajectory cannot be persisted")
    write_json(path, {"version": 1, "count": len(values), "trajectories": [item.to_dict() for item in values]})
    return len(values)


def policy_activation_allowed(
    trajectory_count: int, *, baseline_success: float, policy_success: float,
    baseline_tokens: float, policy_tokens: float,
) -> bool:
    """Require data volume, no success loss, and a measured 10% token reduction."""
    if trajectory_count < MIN_TRAJECTORIES or baseline_tokens <= 0:
        return False
    return policy_success >= baseline_success and policy_tokens <= baseline_tokens * 0.90


def deterministic_fallback(_features: dict[str, float]) -> LoopAction:
    """Safe action when a learned policy abstains or is unavailable."""
    return LoopAction.RETRY_LOCAL
