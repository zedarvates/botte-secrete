"""Tests for the cost-ordered loop controller."""

from skills.loop_optimizer.controller import LoopController
from skills.loop_optimizer.ledger import LoopLedger
from skills.loop_optimizer.models import LoopRequest, LoopState, ProgressState
from skills.response_cache import ResponseCache
from skills.events.events import read_events
from skills.loop_optimizer.runtime import FeatureMode, LoopRuntimeConfig, RolloutGate


def _controller(tmp_path):
    return LoopController(cache=ResponseCache(str(tmp_path / "cache")),
                          ledger=LoopLedger(tmp_path / "ledger.jsonl"))


def test_guards_precede_cache_and_lexical_routing(tmp_path):
    controller = _controller(tmp_path)
    request = LoopRequest("loop", "run tests", max_iterations=1,
                          allowed_tools=("run_tests",))
    state = LoopState("loop", iteration=1)

    decision = controller.decide(request, state,
                                 tool_catalog={"run_tests": "run targeted tests"})

    assert decision.action.value == "stop"
    assert decision.stop_reason.value == "iteration_limit"


def test_exact_cache_and_lexical_single_tool_are_deterministic(tmp_path):
    controller = _controller(tmp_path)
    request = LoopRequest("loop", "run targeted tests", allowed_tools=("run_tests",))
    state = LoopState("loop")
    catalog = {"run_tests": "run targeted tests", "inspect": "inspect source files"}

    first = controller.decide(request, state, tool_catalog=catalog)
    second = controller.decide(request, state, tool_catalog=catalog)

    assert first.tool == "run_tests"
    assert first.decided_by == "lexical"
    assert second.decided_by == "exact_cache"


def test_agent_selection_never_uses_learned_skip_for_critical_loops(tmp_path):
    controller = _controller(tmp_path)

    selected = controller.select_agents(("audit", "verify"), criticality=0.9)
    domain = controller.select_agents(("audit", "verify"), domain_matches=("verify",))

    assert selected.run == ("audit", "verify")
    assert domain.run == ("verify",)
    assert domain.skipped == ("audit",)


def test_decisions_are_observable_without_exposing_the_goal(tmp_path):
    controller = LoopController(cache=ResponseCache(str(tmp_path / "cache")),
                                ledger=LoopLedger(tmp_path / "ledger.jsonl"), project_root=tmp_path)
    controller.decide(LoopRequest("loop", "secret goal", allowed_tools=("inspect",)),
                      LoopState("loop"), tool_catalog={"inspect": "inspect"})
    events = read_events(tmp_path)
    assert {event["kind"] for event in events} >= {"loop_start", "loop_decision"}
    assert all("secret goal" not in str(event) for event in events)


def test_runtime_defaults_to_shadow_and_invalid_values_fail_safe(monkeypatch):
    monkeypatch.delenv("BOTTE_LOOP_OPTIMIZER", raising=False)
    monkeypatch.setenv("BOTTE_NEEDLE_ROUTER", "invalid")
    config = LoopRuntimeConfig.from_environment()
    assert config.loop_optimizer is FeatureMode.SHADOW
    assert config.needle_router is FeatureMode.OFF
    assert not config.applies_decisions and config.records_shadow


def test_rollout_gate_requires_clean_hundred_scenario_stages():
    assert RolloutGate().percentage == 0
    assert not RolloutGate(99, 0).can_advance()
    assert not RolloutGate(100, 1).can_advance()
    gate = RolloutGate(100, 0).advance()
    assert gate.percentage == 10
    assert gate.advance().advance().percentage == 100
