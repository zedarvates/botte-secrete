"""Feature modes for safe, reversible loop-optimizer rollout."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class FeatureMode(str, Enum):
    OFF = "0"
    SHADOW = "shadow"
    ENABLED = "1"


def _mode(name: str, default: FeatureMode) -> FeatureMode:
    value = os.getenv(name, default.value).strip().lower()
    try:
        return FeatureMode(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class LoopRuntimeConfig:
    """Environment-only switches; invalid values always fail to the safe mode."""

    loop_optimizer: FeatureMode = FeatureMode.SHADOW
    needle_router: FeatureMode = FeatureMode.OFF

    @classmethod
    def from_environment(cls) -> "LoopRuntimeConfig":
        return cls(_mode("BOTTE_LOOP_OPTIMIZER", FeatureMode.SHADOW),
                   _mode("BOTTE_NEEDLE_ROUTER", FeatureMode.OFF))

    @property
    def applies_decisions(self) -> bool:
        return self.loop_optimizer is FeatureMode.ENABLED

    @property
    def records_shadow(self) -> bool:
        return self.loop_optimizer is FeatureMode.SHADOW


@dataclass(frozen=True)
class RolloutGate:
    """Deterministic staged-rollout gate for 10%, 50% and 100% activation."""

    scenarios: int = 0
    regressions: int = 0
    stage: int = 0

    def can_advance(self) -> bool:
        return self.scenarios >= 100 and self.regressions == 0 and self.stage < 3

    def advance(self) -> "RolloutGate":
        if not self.can_advance():
            raise ValueError("rollout requires 100 scenarios and zero regressions")
        return RolloutGate(self.scenarios, self.regressions, self.stage + 1)

    @property
    def percentage(self) -> int:
        return (0, 10, 50, 100)[self.stage]
