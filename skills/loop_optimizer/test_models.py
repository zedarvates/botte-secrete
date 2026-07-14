"""Tests for Phase 1 loop contracts and deterministic baseline."""

import pytest

from skills.loop_optimizer.baseline import BaselineStep, compare, simulate_full_loop
from skills.loop_optimizer.models import (
    LoopAction,
    LoopDecision,
    LoopOutcome,
    LoopRequest,
    LoopState,
    ProgressState,
    StopReason,
)


def test_request_and_state_validate_limits():
    request = LoopRequest("loop-1", "corriger le routeur", allowed_tools=("test", "verify"))
    state = LoopState("loop-1", context_tokens=10, execution_tokens=20,
                      verification_tokens=5)

    assert request.allowed_tools == ("test", "verify")
    assert state.total_tokens == 35
    with pytest.raises(ValueError):
        LoopRequest("", "goal")
    with pytest.raises(ValueError):
        LoopRequest("id", "goal", max_total_tokens=-1)
    with pytest.raises(ValueError):
        LoopRequest("id", "goal", allowed_tools=("test", "test"))


def test_stop_decision_requires_reason():
    with pytest.raises(ValueError):
        LoopDecision(LoopAction.STOP, "done")
    decision = LoopDecision(LoopAction.STOP, "verified", stop_reason=StopReason.SOLVED)
    assert decision.to_dict()["stop_reason"] == "solved"


def test_baseline_is_measured_and_success_comparable():
    report = simulate_full_loop([
        BaselineStep(100, 200, 50),
        BaselineStep(100, 150, 50, cloud_tokens=150, success=True),
    ])
    optimized = {"iterations": 1, "tokens_total": 300, "success": True}

    assert report == {
        "iterations": 2, "tokens_total": 650, "cloud_tokens": 150,
        "agents_run": 2, "success": True,
    }
    assert compare(report, optimized)["tokens_saved"] == 350
    failed = dict(optimized, success=False)
    assert compare(report, failed)["comparable"] is False
    assert compare(report, failed)["tokens_saved"] == 0


def test_outcome_serializes_enums_and_unicode():
    outcome = LoopOutcome("boucle-é", 1, LoopAction.VERIFY, ProgressState.PROGRESS,
                          context_tokens=4, success=True)
    assert outcome.to_dict()["action"] == "verify"
    assert outcome.to_dict()["total_tokens"] == 4
