"""Effects-aware planning without changing execution authority."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.capabilities import Capability
from skills.capabilities.effects import contract_template
from skills.conductor import execute, plan, run_goal
from skills.conductor.cli import main as cli


class PlanningEffectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skill = self.root / "different_folder"
        self.skill.mkdir()
        (self.skill / "SKILL.md").write_text(
            "---\nname: selected\ndescription: fixture\n---\n", encoding="utf-8")
        self.contract = contract_template(self.skill, "example/repo:skills/different_folder")
        (self.skill / "effects.json").write_text(json.dumps(self.contract), encoding="utf-8")
        self.caps = [
            Capability("selected", "ACT", "fixture", str(self.skill / "SKILL.md"), True),
            Capability("unselected", "ACT", "fixture", str(self.root / "other" / "SKILL.md"), True),
        ]
        self.addCleanup(patch.stopall)
        patch("skills.conductor.conductor.load_caps", return_value=self.caps).start()
        patch("skills.conductor.conductor.curate", return_value=[
            {"name": "selected", "score": 1.0, "why": "fixture"}
        ]).start()

    def test_default_plan_does_not_inspect_sidecars_or_add_fields(self):
        with patch("skills.capabilities.effects.inspect_effects") as inspect:
            result = plan("fixture")
        inspect.assert_not_called()
        self.assertEqual(set(result["steps"][0]),
                         {"order", "layer", "capability", "local", "command", "why"})

    def test_selected_only_inspection_uses_actual_path_and_preserves_order(self):
        from skills.capabilities.effects import inspect_effects
        before = plan("fixture")
        with patch("skills.capabilities.effects.inspect_effects", wraps=inspect_effects) as inspect:
            after = plan("fixture", include_effects=True)
        inspect.assert_called_once_with(self.skill)
        details = after["steps"][0].pop("effects")
        self.assertEqual(details["status"], "declared")
        self.assertEqual(details["contract"], self.contract)
        self.assertEqual(after, before)

    def test_stale_missing_and_invalid_declarations_remain_explicit(self):
        (self.skill / "SKILL.md").write_text("changed", encoding="utf-8")
        self.assertEqual(plan("fixture", include_effects=True)["steps"][0]["effects"]["status"], "stale")
        sidecar = self.skill / "effects.json"
        sidecar.unlink()
        self.assertEqual(plan("fixture", include_effects=True)["steps"][0]["effects"]["status"], "missing")
        sidecar.write_text("{", encoding="utf-8")
        self.assertEqual(plan("fixture", include_effects=True)["steps"][0]["effects"]["status"], "invalid")

    def test_declaration_does_not_unlock_execution(self):
        step = {"order": 1, "capability": "unknown", "local": True,
                "command": "python worker.py", "why": "fixture",
                "effects": {"status": "declared", "contract": self.contract}}
        with patch("skills.conductor.executor._default_runner") as runner:
            result = execute({"goal": "fixture", "steps": [step]})
        runner.assert_not_called()
        self.assertEqual(result["results"][0]["status"], "blocked")
        self.assertEqual(result["results"][0]["effects_before"], step["effects"])

    def test_execution_retains_snapshot_taken_before_runner(self):
        step = {"order": 1, "capability": "metrics", "local": True,
                "command": "python -m skills.metrics.cli .", "why": "fixture",
                "effects": {"status": "missing", "errors": []}}
        def runner(command, cwd, timeout):
            step["effects"]["status"] = "changed during execution"
            return 2, "fixture failure"
        result = execute({"goal": "fixture", "steps": [step]}, runner=runner)
        self.assertEqual(result["results"][0]["effects_before"]["status"], "missing")
        self.assertEqual(result["results"][0]["status"], "failed")

    def test_run_goal_dry_run_carries_declarations_without_execution(self):
        with patch("skills.conductor.executor._default_runner") as runner:
            result = run_goal("fixture", include_effects=True, dry_run=True)
        runner.assert_not_called()
        self.assertEqual(result["results"][0]["effects_before"]["status"], "declared")
        self.assertEqual(result["summary"]["ran"], 0)

    def test_json_cli_returns_failure_for_failed_execution(self):
        result = {"goal": "fixture", "summary": {"failed": 1}, "results": []}
        with patch("skills.conductor.cli.run_goal", return_value=result):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli(["fixture", "--execute", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue()), result)

    def test_saved_effects_have_a_complete_json_companion(self):
        original = Path.cwd()
        try:
            os.chdir(self.root)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli(["fixture", "--effects", "--json", "--save", "both"])
            result = json.loads(output.getvalue())
            complete = json.loads(Path(result["effects_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(complete["steps"][0]["effects"]["contract"], self.contract)
            for path in (self.root / ".botte" / "reports").glob("plan_*"):
                self.assertIn(result["effects_json"], path.read_text(encoding="utf-8"))
        finally:
            os.chdir(original)

    def test_cli_effects_dry_run_reports_planning_snapshot(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli(["fixture", "--effects", "--execute", "--dry-run", "--json"])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["results"][0]["effects_before"]["status"], "declared")
        self.assertEqual(result["summary"]["ran"], 0)


def main() -> int:
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(PlanningEffectsTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
