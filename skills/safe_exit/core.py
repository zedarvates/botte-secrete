from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Deque


class RunDecision(str, Enum):
    CONTINUE = "CONTINUE"
    UNCERTAIN = "UNCERTAIN"


class AuthorizationTier(IntEnum):
    SIMULATE = 0
    SHADOW = 1
    ACT = 2


@dataclass(frozen=True)
class SafeExitConfig:
    max_iterations: int = 12
    max_tool_calls: int = 48
    max_wall_seconds: float = 900.0
    repeated_failure_limit: int = 3
    max_no_progress: int = 4
    min_score_delta: float = 1e-6

    def __post_init__(self) -> None:
        for name in ("max_iterations", "max_tool_calls", "repeated_failure_limit", "max_no_progress"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        for name in ("max_wall_seconds", "min_score_delta"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls must be non-negative")
        if self.max_wall_seconds <= 0:
            raise ValueError("max_wall_seconds must be positive")
        if self.repeated_failure_limit <= 1:
            raise ValueError("repeated_failure_limit must be > 1")
        if self.max_no_progress <= 0:
            raise ValueError("max_no_progress must be positive")
        if self.min_score_delta < 0:
            raise ValueError("min_score_delta must be non-negative")


@dataclass(frozen=True)
class RunGuardResult:
    decision: RunDecision
    reason: str | None
    iterations: int
    tool_calls: int
    best_score: float | None
    no_progress_count: int


class SafeExitGuard:
    """Deterministic budget/stagnation guard for agent loops.

    The guard does not execute tools and does not retry work. It only records
    progress and returns ``UNCERTAIN`` when a configured safety budget is
    exhausted or the run is demonstrably stagnating.
    """

    def __init__(
        self,
        config: SafeExitConfig | None = None,
        *,
        started_at: float | None = None,
    ) -> None:
        self.config = config or SafeExitConfig()
        self.started_at = time.monotonic() if started_at is None else started_at
        self._validate_number(self.started_at, "started_at")
        self.iterations = 0
        self.tool_calls = 0
        self.best_score: float | None = None
        self.no_progress_count = 0
        self._failure_signatures: Deque[str] = deque(
            maxlen=self.config.repeated_failure_limit
        )
        self._stop_reason: str | None = None

    @staticmethod
    def _validate_number(value: float, name: str) -> None:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")

    def remaining_seconds(self, *, now: float | None = None) -> float:
        current = time.monotonic() if now is None else now
        self._validate_number(current, "now")
        return max(0.0, self.config.max_wall_seconds - max(0.0, current - self.started_at))

    def check(self, *, now: float | None = None) -> RunGuardResult:
        """Check before dispatch without consuming an iteration or tool call.

        An uncertain trajectory stays stopped; recovery requires a new guard.
        """
        remaining = self.remaining_seconds(now=now)
        reason = self._stop_reason
        if reason is None:
            if self.iterations >= self.config.max_iterations:
                reason = "iteration_budget_exhausted"
            elif self.tool_calls >= self.config.max_tool_calls:
                reason = "tool_budget_exhausted"
            elif remaining <= 0:
                reason = "wall_time_budget_exhausted"
            elif (
                len(self._failure_signatures) == self.config.repeated_failure_limit
                and len(set(self._failure_signatures)) == 1
            ):
                reason = "repeated_equivalent_failure"
            elif self.no_progress_count >= self.config.max_no_progress:
                reason = "no_score_progress"
        self._stop_reason = reason
        return RunGuardResult(
            decision=RunDecision.UNCERTAIN if reason else RunDecision.CONTINUE,
            reason=reason,
            iterations=self.iterations,
            tool_calls=self.tool_calls,
            best_score=self.best_score,
            no_progress_count=self.no_progress_count,
        )

    def observe(
        self,
        *,
        score: float | None = None,
        failure_signature: str | None = None,
        tool_calls_delta: int = 0,
        now: float | None = None,
    ) -> RunGuardResult:
        if type(tool_calls_delta) is not int or tool_calls_delta < 0:
            raise ValueError("tool_calls_delta must be non-negative")
        if score is not None:
            self._validate_number(score, "score")
        if failure_signature is not None and not isinstance(failure_signature, str):
            raise ValueError("failure_signature must be text")
        self.remaining_seconds(now=now)  # Validate the clock before changing state.
        if self._stop_reason is not None:
            return self.check(now=now)

        self.iterations += 1
        self.tool_calls += tool_calls_delta

        if score is not None:
            if self.best_score is None or score > self.best_score + self.config.min_score_delta:
                self.best_score = score
                self.no_progress_count = 0
            else:
                self.no_progress_count += 1
        elif failure_signature:
            self.no_progress_count += 1

        if failure_signature:
            self._failure_signatures.append(failure_signature)
        else:
            self._failure_signatures.clear()

        return self.check(now=now)


@dataclass(frozen=True)
class ActionIntent:
    name: str
    requested_tier: AuthorizationTier
    destructive: bool = False
    snapshot_id: str | None = None


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    reason: str | None = None


def validate_action(intent: ActionIntent, *, current_tier: AuthorizationTier) -> ActionDecision:
    """Fail closed on implicit privilege escalation and destructive mutations."""

    if (
        not isinstance(current_tier, AuthorizationTier)
        or not isinstance(intent.requested_tier, AuthorizationTier)
        or type(intent.destructive) is not bool
    ):
        return ActionDecision(False, "invalid_authorization")
    if intent.requested_tier > current_tier:
        return ActionDecision(False, "implicit_privilege_escalation")

    if intent.destructive and current_tier < AuthorizationTier.ACT:
        return ActionDecision(False, "destructive_requires_act")

    if intent.destructive and not (
        isinstance(intent.snapshot_id, str) and intent.snapshot_id.strip()
    ):
        return ActionDecision(False, "destructive_requires_snapshot")

    return ActionDecision(True, None)
