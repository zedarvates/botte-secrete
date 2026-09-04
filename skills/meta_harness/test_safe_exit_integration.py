from __future__ import annotations

import json
import sys

from skills.meta_harness.orchestrator import MetaHarness, PipelinePlan, Step
from skills.safe_exit import SafeExitConfig


def _python_step(agent: str, script: str, workdir: str) -> Step:
    return Step(
        agent=agent,
        command=[sys.executable, "-c", script],
        workdir=workdir,
    )


def test_meta_harness_stops_after_repeated_equivalent_failure(tmp_path):
    harness = MetaHarness(
        workdir=str(tmp_path),
        safe_exit_config=SafeExitConfig(
            max_iterations=10,
            max_tool_calls=10,
            max_wall_seconds=60,
            repeated_failure_limit=2,
            max_no_progress=10,
        ),
    )
    fail_script = "import sys; print('same failure', file=sys.stderr); sys.exit(7)"
    plan = PipelinePlan(
        name="loop-fixture",
        steps=[
            _python_step("loop", fail_script, str(tmp_path)),
            _python_step("loop", fail_script, str(tmp_path)),
            _python_step("should-not-run", "print('unexpected')", str(tmp_path)),
        ],
    )

    session = harness.execute(plan)

    assert session.termination_decision == "UNCERTAIN"
    assert session.termination_reason == "repeated_equivalent_failure"
    assert [result.status for result in session.results] == ["failed", "failed", "skipped"]
    assert "SAFE-EXIT" in session.results[-1].output
    payload = json.loads(session.to_json())
    assert payload["termination_decision"] == "UNCERTAIN"
    assert payload["termination_reason"] == "repeated_equivalent_failure"


def test_meta_harness_iteration_budget_stops_before_next_step(tmp_path):
    harness = MetaHarness(
        workdir=str(tmp_path),
        safe_exit_config=SafeExitConfig(
            max_iterations=1,
            max_tool_calls=10,
            max_wall_seconds=60,
            repeated_failure_limit=3,
            max_no_progress=10,
        ),
    )
    plan = PipelinePlan(
        name="bounded-fixture",
        steps=[
            _python_step("first", "print('ok')", str(tmp_path)),
            _python_step("second", "print('must not execute')", str(tmp_path)),
        ],
    )

    session = harness.execute(plan)

    assert session.termination_decision == "UNCERTAIN"
    assert session.termination_reason == "iteration_budget_exhausted"
    assert [result.status for result in session.results] == ["passed", "skipped"]


def test_default_meta_harness_keeps_short_successful_pipeline_running(tmp_path):
    harness = MetaHarness(workdir=str(tmp_path))
    plan = PipelinePlan(
        name="normal-short-run",
        steps=[
            _python_step("one", "print('one')", str(tmp_path)),
            _python_step("two", "print('two')", str(tmp_path)),
        ],
    )

    session = harness.execute(plan)

    assert session.termination_decision == "CONTINUE"
    assert session.termination_reason is None
    assert [result.status for result in session.results] == ["passed", "passed"]
