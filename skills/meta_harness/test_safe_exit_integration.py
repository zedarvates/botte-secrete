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


import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from skills.meta_harness.session import Session


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)
        def session_factory(name):
            return Session(name=name, storage_dir=str(self.tmp_path / "sessions"))
        mocked = patch("skills.meta_harness.orchestrator.Session", side_effect=session_factory)
        mocked.start()
        self.addCleanup(mocked.stop)

    def test_zero_and_exact_tool_budget_bound_actual_dispatch(self):
        from skills.meta_harness.runner import SandboxResult
        for limit in (0, 1):
            with self.subTest(limit=limit):
                h = MetaHarness(workdir=str(self.tmp_path), safe_exit_config=SafeExitConfig(max_tool_calls=limit))
                p = PipelinePlan(name="tools", steps=[
                    _python_step("probe", "print('ok')", str(self.tmp_path)) for _ in range(3)
                ])
                with patch("skills.meta_harness.orchestrator.Sandbox.run",
                           return_value=SandboxResult(True, "ok", "", 0, 0)) as run:
                    session = h.execute(p)
                self.assertEqual(run.call_count, limit)
                self.assertEqual(session.termination_reason, "tool_budget_exhausted")
                saved = json.loads((session.storage_dir / f"{session.name}.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["termination_decision"], "UNCERTAIN")
                self.assertEqual([r["status"] for r in saved["results"]],
                                 ["passed"] * limit + ["skipped"] * (3 - limit))

    def test_wall_budget_limits_real_subprocess(self):
        h = MetaHarness(workdir=str(self.tmp_path), safe_exit_config=SafeExitConfig(max_wall_seconds=0.15))
        p = PipelinePlan(name="timeout", steps=[
            _python_step("slow", "import time; time.sleep(5); print('must not finish')", str(self.tmp_path)),
            _python_step("later", "print('must not execute')", str(self.tmp_path)),
        ])
        session = h.execute(p)
        self.assertEqual(session.termination_reason, "wall_time_budget_exhausted")
        self.assertEqual([r.status for r in session.results], ["failed", "skipped"])
        self.assertEqual(session.results[0].exit_code, 124)
        self.assertNotIn("must not finish", session.results[0].output)

    def test_uncertain_session_and_consumed_plan_cannot_reexecute(self):
        h = MetaHarness(workdir=str(self.tmp_path), safe_exit_config=SafeExitConfig(max_iterations=1))
        p = PipelinePlan(name="once", steps=[_python_step("one", "print('ok')", str(self.tmp_path))])
        h.execute(p)
        with patch("skills.meta_harness.orchestrator.Sandbox.run") as run:
            with self.assertRaises(RuntimeError):
                h.execute(p)
            with self.assertRaises(RuntimeError):
                MetaHarness(workdir=str(self.tmp_path)).execute(p)
            run.assert_not_called()

    def test_cli_uncertain_exit_is_nonzero_without_failed_step(self):
        import contextlib
        import io
        from skills.meta_harness.cli import main
        h = MetaHarness(workdir=str(self.tmp_path), safe_exit_config=SafeExitConfig(max_tool_calls=0))
        p = PipelinePlan(name="held", steps=[_python_step("probe", "print('no')", str(self.tmp_path))])
        session = h.execute(p)
        self.assertFalse(p.has_failed)
        with patch("skills.meta_harness.cli.MetaHarness") as factory, contextlib.redirect_stdout(io.StringIO()):
            factory.return_value.plan.return_value = p
            factory.return_value.list_plans.return_value = {}
            factory.return_value.execute.return_value = session
            self.assertEqual(main(["run", str(self.tmp_path), "probe"]), 2)

    def test_meta_harness_stops_after_repeated_equivalent_failure(self):
        tmp_path = self.tmp_path
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


    def test_meta_harness_iteration_budget_stops_before_next_step(self):
        tmp_path = self.tmp_path
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


    def test_default_meta_harness_keeps_short_successful_pipeline_running(self):
        tmp_path = self.tmp_path
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


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationTests))
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
