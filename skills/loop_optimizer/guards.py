"""Zero-token stop and retry guards for retroactive loops."""

from __future__ import annotations

from skills.loop_optimizer.models import (
    LoopAction,
    LoopDecision,
    LoopRequest,
    LoopState,
    ProgressState,
    StopReason,
)


def stop_decision(request: LoopRequest, state: LoopState, *,
                  consecutive_stalled: int = 0,
                  repeated_failure: bool = False,
                  fingerprints_unchanged: bool = False) -> LoopDecision | None:
    """Return a deterministic stop decision, or ``None`` to continue."""
    if state.progress is ProgressState.SOLVED:
        return LoopDecision(LoopAction.STOP, "final verification succeeded",
                            stop_reason=StopReason.SOLVED)
    if state.iteration >= request.max_iterations:
        return LoopDecision(LoopAction.STOP, "maximum iteration count reached",
                            stop_reason=StopReason.ITERATION_LIMIT)
    if state.total_tokens >= request.max_total_tokens:
        return LoopDecision(LoopAction.STOP, "total token budget exhausted",
                            stop_reason=StopReason.BUDGET_EXHAUSTED)
    if state.cloud_tokens >= request.max_cloud_tokens and state.cloud_tokens > 0:
        return LoopDecision(LoopAction.STOP, "cloud token budget exhausted",
                            stop_reason=StopReason.CLOUD_BUDGET_EXHAUSTED)
    if repeated_failure and fingerprints_unchanged:
        return LoopDecision(LoopAction.STOP,
                            "same action failed again with identical inputs",
                            stop_reason=StopReason.REPEATED_FAILURE)
    if state.progress is ProgressState.REGRESSED:
        return LoopDecision(LoopAction.STOP, "measured state regressed",
                            stop_reason=StopReason.REGRESSION)
    if state.progress is ProgressState.STALLED and consecutive_stalled >= 2:
        return LoopDecision(LoopAction.STOP, "two consecutive iterations made no progress",
                            stop_reason=StopReason.NO_CHANGE)
    return None


def remaining_budget(request: LoopRequest, state: LoopState) -> dict[str, int]:
    return {
        "iterations": max(0, request.max_iterations - state.iteration),
        "tokens": max(0, request.max_total_tokens - state.total_tokens),
        "cloud_tokens": max(0, request.max_cloud_tokens - state.cloud_tokens),
    }
