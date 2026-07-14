"""Typed contracts shared by every loop-optimizer component."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ProgressState(str, Enum):
    PROGRESS = "progress"
    STALLED = "stalled"
    REGRESSED = "regressed"
    SOLVED = "solved"


class LoopAction(str, Enum):
    STOP = "stop"
    RETRY_LOCAL = "retry_local"
    CHANGE_TOOL = "change_tool"
    VERIFY = "verify"
    ASK_LOCAL = "ask_local"
    ESCALATE = "escalate"
    ROLLBACK = "rollback"


class StopReason(str, Enum):
    SOLVED = "solved"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CLOUD_BUDGET_EXHAUSTED = "cloud_budget_exhausted"
    ITERATION_LIMIT = "iteration_limit"
    NO_CHANGE = "no_change"
    REPEATED_FAILURE = "repeated_failure"
    REGRESSION = "regression"
    CANCELLED = "cancelled"


def _non_negative(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


@dataclass(slots=True)
class LoopRequest:
    """Immutable limits and permissions for one retroactive loop."""

    loop_id: str
    goal: str
    max_iterations: int = 5
    max_total_tokens: int = 8_000
    max_cloud_tokens: int = 2_000
    criticality: float = 0.5
    allowed_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.loop_id = self.loop_id.strip()
        self.goal = self.goal.strip()
        if not self.loop_id:
            raise ValueError("loop_id must not be empty")
        if not self.goal:
            raise ValueError("goal must not be empty")
        if isinstance(self.max_iterations, bool) or self.max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")
        _non_negative("max_total_tokens", self.max_total_tokens)
        _non_negative("max_cloud_tokens", self.max_cloud_tokens)
        if not 0.0 <= float(self.criticality) <= 1.0:
            raise ValueError("criticality must be between 0 and 1")
        normalized = tuple(tool.strip() for tool in self.allowed_tools if tool.strip())
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_tools must not contain duplicates")
        self.allowed_tools = normalized

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LoopState:
    """Mutable accounting and observations for the current iteration."""

    loop_id: str
    iteration: int = 0
    context_tokens: int = 0
    execution_tokens: int = 0
    verification_tokens: int = 0
    cloud_tokens: int = 0
    progress: ProgressState = ProgressState.PROGRESS
    fingerprints: dict[str, str] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    agents_run: tuple[str, ...] = ()
    agents_skipped: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.loop_id = self.loop_id.strip()
        if not self.loop_id:
            raise ValueError("loop_id must not be empty")
        for name in ("iteration", "context_tokens", "execution_tokens",
                     "verification_tokens", "cloud_tokens"):
            _non_negative(name, getattr(self, name))
        if not isinstance(self.progress, ProgressState):
            self.progress = ProgressState(self.progress)

    @property
    def total_tokens(self) -> int:
        return self.context_tokens + self.execution_tokens + self.verification_tokens

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["progress"] = self.progress.value
        data["total_tokens"] = self.total_tokens
        return data


@dataclass(slots=True)
class LoopDecision:
    """One proposed action and the layer that selected it."""

    action: LoopAction
    reason: str
    decided_by: str = "deterministic"
    tool: str = ""
    confidence: float = 1.0
    stop_reason: StopReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, LoopAction):
            self.action = LoopAction(self.action)
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("decision reason must not be empty")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.stop_reason is not None and not isinstance(self.stop_reason, StopReason):
            self.stop_reason = StopReason(self.stop_reason)
        if self.action is LoopAction.STOP and self.stop_reason is None:
            raise ValueError("stop decisions require stop_reason")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        data["stop_reason"] = self.stop_reason.value if self.stop_reason else None
        return data


@dataclass(slots=True)
class LoopOutcome:
    """Verified result and measured cost of one completed iteration."""

    loop_id: str
    iteration: int
    action: LoopAction
    progress: ProgressState
    context_tokens: int = 0
    execution_tokens: int = 0
    verification_tokens: int = 0
    cloud_tokens: int = 0
    success: bool = False
    cache_hit: bool = False
    error_signature: str = ""

    def __post_init__(self) -> None:
        self.loop_id = self.loop_id.strip()
        if not self.loop_id:
            raise ValueError("loop_id must not be empty")
        if not isinstance(self.action, LoopAction):
            self.action = LoopAction(self.action)
        if not isinstance(self.progress, ProgressState):
            self.progress = ProgressState(self.progress)
        for name in ("iteration", "context_tokens", "execution_tokens",
                     "verification_tokens", "cloud_tokens"):
            _non_negative(name, getattr(self, name))

    @property
    def total_tokens(self) -> int:
        return self.context_tokens + self.execution_tokens + self.verification_tokens

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        data["progress"] = self.progress.value
        data["total_tokens"] = self.total_tokens
        return data
