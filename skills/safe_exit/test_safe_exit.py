from skills.safe_exit.core import (
    ActionIntent,
    AuthorizationTier,
    RunDecision,
    SafeExitConfig,
    SafeExitGuard,
    validate_action,
)


def test_iteration_budget_returns_uncertain():
    guard = SafeExitGuard(SafeExitConfig(max_iterations=2), started_at=0.0)
    first = guard.observe(now=1.0)
    second = guard.observe(now=2.0)
    assert first.decision == RunDecision.CONTINUE
    assert second.decision == RunDecision.UNCERTAIN
    assert second.reason == "iteration_budget_exhausted"


def test_tool_budget_returns_uncertain():
    guard = SafeExitGuard(SafeExitConfig(max_iterations=10, max_tool_calls=2), started_at=0.0)
    result = guard.observe(tool_calls_delta=3, now=1.0)
    assert result.decision == RunDecision.UNCERTAIN
    assert result.reason == "tool_budget_exhausted"


def test_wall_time_budget_returns_uncertain():
    guard = SafeExitGuard(SafeExitConfig(max_iterations=10, max_wall_seconds=5), started_at=10.0)
    result = guard.observe(now=15.0)
    assert result.decision == RunDecision.UNCERTAIN
    assert result.reason == "wall_time_budget_exhausted"


def test_repeated_failure_returns_uncertain():
    guard = SafeExitGuard(
        SafeExitConfig(max_iterations=10, repeated_failure_limit=3, max_no_progress=10),
        started_at=0.0,
    )
    assert guard.observe(failure_signature="same", now=1).decision == RunDecision.CONTINUE
    assert guard.observe(failure_signature="same", now=2).decision == RunDecision.CONTINUE
    result = guard.observe(failure_signature="same", now=3)
    assert result.decision == RunDecision.UNCERTAIN
    assert result.reason == "repeated_equivalent_failure"


def test_no_progress_returns_uncertain():
    guard = SafeExitGuard(
        SafeExitConfig(max_iterations=10, repeated_failure_limit=5, max_no_progress=2),
        started_at=0.0,
    )
    assert guard.observe(score=0.8, now=1).decision == RunDecision.CONTINUE
    assert guard.observe(score=0.8, now=2).decision == RunDecision.CONTINUE
    result = guard.observe(score=0.79, now=3)
    assert result.decision == RunDecision.UNCERTAIN
    assert result.reason == "no_score_progress"


def test_score_improvement_resets_no_progress():
    guard = SafeExitGuard(
        SafeExitConfig(max_iterations=10, repeated_failure_limit=5, max_no_progress=2),
        started_at=0.0,
    )
    guard.observe(score=0.5, now=1)
    guard.observe(score=0.5, now=2)
    result = guard.observe(score=0.7, now=3)
    assert result.decision == RunDecision.CONTINUE
    assert result.no_progress_count == 0
    assert result.best_score == 0.7


def test_implicit_privilege_escalation_is_blocked():
    decision = validate_action(
        ActionIntent("write", requested_tier=AuthorizationTier.ACT),
        current_tier=AuthorizationTier.SHADOW,
    )
    assert decision.allowed is False
    assert decision.reason == "implicit_privilege_escalation"


def test_destructive_action_requires_act():
    decision = validate_action(
        ActionIntent(
            "delete_fixture",
            requested_tier=AuthorizationTier.SHADOW,
            destructive=True,
            snapshot_id="snap-1",
        ),
        current_tier=AuthorizationTier.SHADOW,
    )
    assert decision.allowed is False
    assert decision.reason == "destructive_requires_act"


def test_destructive_action_requires_snapshot():
    decision = validate_action(
        ActionIntent(
            "delete_fixture",
            requested_tier=AuthorizationTier.ACT,
            destructive=True,
        ),
        current_tier=AuthorizationTier.ACT,
    )
    assert decision.allowed is False
    assert decision.reason == "destructive_requires_snapshot"


def test_destructive_action_with_act_and_snapshot_is_allowed():
    decision = validate_action(
        ActionIntent(
            "delete_fixture",
            requested_tier=AuthorizationTier.ACT,
            destructive=True,
            snapshot_id="git:abc123",
        ),
        current_tier=AuthorizationTier.ACT,
    )
    assert decision.allowed is True
    assert decision.reason is None


def test_non_destructive_shadow_action_is_allowed():
    decision = validate_action(
        ActionIntent("inspect", requested_tier=AuthorizationTier.SHADOW),
        current_tier=AuthorizationTier.SHADOW,
    )
    assert decision.allowed is True
