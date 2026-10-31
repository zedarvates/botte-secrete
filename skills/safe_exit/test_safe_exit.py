import unittest

from skills.safe_exit.core import (
    ActionIntent,
    AuthorizationTier,
    RunDecision,
    SafeExitConfig,
    SafeExitGuard,
    validate_action,
)


class GuardTests(unittest.TestCase):
    def test_zero_tools_blocks_before_dispatch(self):
        guard = SafeExitGuard(SafeExitConfig(max_tool_calls=0), started_at=0)
        result = guard.check(now=1)
        self.assertEqual(result.reason, "tool_budget_exhausted")
        self.assertEqual((result.iterations, result.tool_calls), (0, 0))

    def test_exact_tool_limit_stops_without_extra_call(self):
        guard = SafeExitGuard(SafeExitConfig(max_tool_calls=1), started_at=0)
        self.assertEqual(guard.check(now=1).decision, RunDecision.CONTINUE)
        self.assertEqual(guard.observe(tool_calls_delta=1, now=2).reason, "tool_budget_exhausted")

    def test_uncertain_is_terminal_even_after_score_improvement(self):
        guard = SafeExitGuard(SafeExitConfig(max_no_progress=1), started_at=0)
        guard.observe(score=1, now=1)
        stopped = guard.observe(score=1, now=2)
        self.assertEqual(stopped.reason, "no_score_progress")
        self.assertEqual(guard.observe(score=2, now=3), stopped)

    def test_nonfinite_and_wrongly_typed_config_is_rejected(self):
        for kwargs in ({"max_wall_seconds": float("nan")}, {"max_wall_seconds": float("inf")},
                       {"min_score_delta": float("nan")}, {"max_iterations": True},
                       {"max_tool_calls": 1.5}, {"max_no_progress": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SafeExitConfig(**kwargs)

    def test_invalid_observation_does_not_consume_budget(self):
        for kwargs in ({"score": float("nan")}, {"now": float("inf")},
                       {"tool_calls_delta": True}, {"tool_calls_delta": -1}):
            guard = SafeExitGuard(started_at=0)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                guard.observe(**kwargs)
            self.assertEqual((guard.iterations, guard.tool_calls), (0, 0))

    def test_invalid_authorization_cannot_pass_gate(self):
        for tier in (float("nan"), 2, True, "ACT"):
            decision = validate_action(ActionIntent("write", AuthorizationTier.ACT), current_tier=tier)
            self.assertFalse(decision.allowed)
        decision = validate_action(ActionIntent("delete", AuthorizationTier.ACT, True, 123),
                                   current_tier=AuthorizationTier.ACT)
        self.assertFalse(decision.allowed)

    def test_iteration_budget_returns_uncertain(self):
        guard = SafeExitGuard(SafeExitConfig(max_iterations=2), started_at=0.0)
        first = guard.observe(now=1.0)
        second = guard.observe(now=2.0)
        assert first.decision == RunDecision.CONTINUE
        assert second.decision == RunDecision.UNCERTAIN
        assert second.reason == "iteration_budget_exhausted"


    def test_tool_budget_returns_uncertain(self):
        guard = SafeExitGuard(SafeExitConfig(max_iterations=10, max_tool_calls=2), started_at=0.0)
        result = guard.observe(tool_calls_delta=3, now=1.0)
        assert result.decision == RunDecision.UNCERTAIN
        assert result.reason == "tool_budget_exhausted"


    def test_wall_time_budget_returns_uncertain(self):
        guard = SafeExitGuard(SafeExitConfig(max_iterations=10, max_wall_seconds=5), started_at=10.0)
        result = guard.observe(now=15.0)
        assert result.decision == RunDecision.UNCERTAIN
        assert result.reason == "wall_time_budget_exhausted"


    def test_repeated_failure_returns_uncertain(self):
        guard = SafeExitGuard(
            SafeExitConfig(max_iterations=10, repeated_failure_limit=3, max_no_progress=10),
            started_at=0.0,
        )
        assert guard.observe(failure_signature="same", now=1).decision == RunDecision.CONTINUE
        assert guard.observe(failure_signature="same", now=2).decision == RunDecision.CONTINUE
        result = guard.observe(failure_signature="same", now=3)
        assert result.decision == RunDecision.UNCERTAIN
        assert result.reason == "repeated_equivalent_failure"


    def test_no_progress_returns_uncertain(self):
        guard = SafeExitGuard(
            SafeExitConfig(max_iterations=10, repeated_failure_limit=5, max_no_progress=2),
            started_at=0.0,
        )
        assert guard.observe(score=0.8, now=1).decision == RunDecision.CONTINUE
        assert guard.observe(score=0.8, now=2).decision == RunDecision.CONTINUE
        result = guard.observe(score=0.79, now=3)
        assert result.decision == RunDecision.UNCERTAIN
        assert result.reason == "no_score_progress"


    def test_score_improvement_resets_no_progress(self):
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


    def test_implicit_privilege_escalation_is_blocked(self):
        decision = validate_action(
            ActionIntent("write", requested_tier=AuthorizationTier.ACT),
            current_tier=AuthorizationTier.SHADOW,
        )
        assert decision.allowed is False
        assert decision.reason == "implicit_privilege_escalation"


    def test_destructive_action_requires_act(self):
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


    def test_destructive_action_requires_snapshot(self):
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


    def test_destructive_action_with_act_and_snapshot_is_allowed(self):
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


    def test_non_destructive_shadow_action_is_allowed(self):
        decision = validate_action(
            ActionIntent("inspect", requested_tier=AuthorizationTier.SHADOW),
            current_tier=AuthorizationTier.SHADOW,
        )
        assert decision.allowed is True


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
