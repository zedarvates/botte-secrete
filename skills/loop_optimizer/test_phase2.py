"""Regression tests for progress, failure memory and deterministic guards."""

from skills.loop_optimizer.failures import FailureMemory, failure_signature
from skills.loop_optimizer.guards import remaining_budget, stop_decision
from skills.loop_optimizer.models import LoopRequest, LoopState, ProgressState
from skills.loop_optimizer.progress import ProgressSnapshot, evaluate


def test_progress_classifies_solved_progress_stalled_and_regressed():
    first = ProgressSnapshot(5, 2, {"a.py": "one"}, "info-1")
    improved = ProgressSnapshot(6, 1, {"a.py": "two"}, "info-2")
    same = ProgressSnapshot(6, 1, {"a.py": "two"}, "info-2")
    regressed = ProgressSnapshot(5, 3, {"a.py": "three"}, "info-3")

    assert evaluate(None, first).state is ProgressState.PROGRESS
    assert evaluate(first, improved).state is ProgressState.PROGRESS
    assert evaluate(improved, same).state is ProgressState.STALLED
    assert evaluate(same, regressed).state is ProgressState.REGRESSED
    assert evaluate(regressed, ProgressSnapshot(5, 3, verified_success=True)).state is ProgressState.SOLVED


def test_failure_memory_persists_bounds_and_distinguishes_changes(tmp_path):
    path = tmp_path / "failures.json"
    memory = FailureMemory(path, max_entries=2)
    signature = memory.record(error_type="AssertionError", message="  Expected 1\n got 2 ",
                              fingerprints={"a.py": "one"}, action="retry", loop_id="a")
    memory.record(error_type="AssertionError", message="expected 1 got 2",
                  fingerprints={"a.py": "one"}, action="retry", loop_id="a")

    restored = FailureMemory(path, max_entries=2)
    assert restored.repeated(signature, loop_id="a") is True
    changed = failure_signature("AssertionError", "expected 1 got 2",
                                {"a.py": "two"}, "retry")
    assert changed != signature


def test_guards_require_two_stalls_but_stop_exact_repeated_failure():
    request = LoopRequest("loop", "fix", max_iterations=3, max_total_tokens=100,
                          max_cloud_tokens=20)
    stalled = LoopState("loop", iteration=1, progress=ProgressState.STALLED)

    assert stop_decision(request, stalled, consecutive_stalled=1) is None
    assert stop_decision(request, stalled, consecutive_stalled=2).stop_reason.value == "no_change"
    assert stop_decision(request, stalled, repeated_failure=True,
                         fingerprints_unchanged=True).stop_reason.value == "repeated_failure"


def test_every_loop_reaches_iteration_terminal_and_budget_never_negative():
    request = LoopRequest("loop", "fix", max_iterations=4, max_total_tokens=10,
                          max_cloud_tokens=2)
    decision = None
    for iteration in range(10):
        state = LoopState("loop", iteration=iteration, context_tokens=min(iteration, 10))
        budget = remaining_budget(request, state)
        assert all(value >= 0 for value in budget.values())
        decision = stop_decision(request, state)
        if decision:
            break

    assert decision is not None
    assert decision.stop_reason.value in {"iteration_limit", "budget_exhausted"}
