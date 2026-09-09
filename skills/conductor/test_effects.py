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

from skills.capabilities import Capability, curate, load
from skills.capabilities.effects import contract_template
from skills.conductor import execute, plan, run_goal
from skills.conductor.cli import main as cli


class PlanningEffectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skill = self.root / "skills" / "different_folder"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text(
            "---\nname: selected\ndescription: fixture\n---\n", encoding="utf-8")
        self.contract = contract_template(self.skill, "zedarvates/botte-secrete:skills/different_folder")
        (self.skill / "effects.json").write_text(json.dumps(self.contract), encoding="utf-8")
        self.caps = [
            Capability("selected", "ACT", "fixture", str(self.skill / "SKILL.md"), True),
            Capability("unselected", "ACT", "fixture", str(self.root / "other" / "SKILL.md"), True),
        ]
        self.addCleanup(patch.stopall)
        patch("skills.capabilities.registry.REPO_ROOT", self.root).start()
        patch("skills.conductor.conductor.REPO_ROOT", self.root).start()
        patch("skills.conductor.conductor.load_caps", return_value=self.caps).start()
        patch("skills.conductor.conductor.curate", return_value=[
            {"name": "selected", "score": 1.0, "why": "fixture",
             "path": str(self.skill / "SKILL.md")}
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

    def test_duplicate_names_keep_their_layer_command_and_effects(self):
        expected = []
        for folder, layer in (("one/metrics", "SENSE"), ("two/metrics", "GOVERN"),
                              ("three/alias", "DEPLOY")):
            skill = self.root / "skills" / folder
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                f"---\nname: metrics\nlayer: {layer}\ndescription: metrics\n---\n",
                encoding="utf-8")
            contract = contract_template(skill, f"zedarvates/botte-secrete:skills/{folder}")
            (skill / "effects.json").write_text(json.dumps(contract), encoding="utf-8")
            expected.append((layer, f"see skills/{folder}/SKILL.md", contract["capability_id"]))
        caps = load(self.root, preserve_paths=True)
        # Exercise real discovery and curation, bypassing the single-step fixture.
        with patch("skills.conductor.conductor.load_caps", return_value=caps), \
             patch("skills.conductor.conductor.curate", wraps=curate):
            result = plan("metrics", include_effects=True)
        self.assertEqual([
            (s["layer"], s["command"], s["effects"]["contract"]["capability_id"])
            for s in result["steps"]], expected)
        with patch("skills.conductor.executor._default_runner") as runner:
            report = execute(result, confirm=True)
        runner.assert_not_called()
        self.assertEqual(report["summary"]["skipped"], 3)

    def test_same_name_candidates_keep_local_flags_and_canonical_command(self):
        caps = [
            Capability("metrics", "SENSE", "metrics", "skills/metrics/SKILL.md", True),
            Capability("metrics", "ACT", "metrics", "skills/vendor/metrics/SKILL.md", False),
        ]
        with patch("skills.conductor.conductor.load_caps", return_value=caps), \
             patch("skills.conductor.conductor.curate", wraps=curate):
            steps = plan("metrics")["steps"]
        self.assertEqual([s["local"] for s in steps], [True, False])
        self.assertEqual(steps[0]["command"], "python -m skills.metrics.cli .")
        self.assertEqual(steps[1]["command"], "see skills/vendor/metrics/SKILL.md")

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

    def test_selected_name_collision_inspects_only_the_curated_path(self):
        self.caps.append(Capability("selected", "ACT", "second fixture",
                                    str(self.root / "other" / "SKILL.md"), True))
        from skills.capabilities.effects import inspect_effects
        with patch("skills.capabilities.effects.inspect_effects", wraps=inspect_effects) as inspect:
            with patch("skills.conductor.executor._default_runner") as runner:
                result = run_goal("fixture", include_effects=True, confirm=True)
        self.assertEqual(result["results"][0]["effects_before"]["contract"], self.contract)
        self.assertEqual(result["summary"]["skipped"], 1)
        inspect.assert_called_once_with(self.skill)
        runner.assert_not_called()

    def test_unselected_name_collision_does_not_block_selected_capability(self):
        self.caps.append(Capability("unselected", "ACT", "second fixture",
                                    str(self.root / "other2" / "SKILL.md"), True))
        self.assertEqual(plan("fixture", include_effects=True)["steps"][0]["effects"]["status"],
                         "declared")

    def test_mcp_round_trip_preserves_effects_only_when_requested(self):
        from skills.llm_mcp.server import handle, TOOLS
        for tool_name in ("conduct", "execute_plan"):
            definition = next(t for t in TOOLS if t["name"] == tool_name)
            self.assertEqual(definition["inputSchema"]["properties"]["include_effects"]["type"],
                             "boolean")
            for include in (None, False, True):
                with self.subTest(tool=tool_name, include_effects=include):
                    arguments = {"goal": "fixture"}
                    if tool_name == "execute_plan":
                        arguments["dry_run"] = True
                    if include is not None:
                        arguments["include_effects"] = include
                    with patch("skills.conductor.executor._default_runner") as runner:
                        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                           "params": {"name": tool_name, "arguments": arguments}})
                    runner.assert_not_called()
                    payload = json.loads(response["result"]["content"][0]["text"])
                    steps_key, effects_key = (("steps", "effects") if tool_name == "conduct"
                                              else ("results", "effects_before"))
                    step = payload[steps_key][0]
                    self.assertEqual(effects_key in step, include is True)
                    if include:
                        self.assertEqual(step[effects_key]["contract"], self.contract)


    def test_mcp_observation_opt_in_implies_declarations_and_respects_dry_run(self):
        from skills.llm_mcp.server import TOOLS, handle
        definition = next(t for t in TOOLS if t["name"] == "execute_plan")
        self.assertFalse(definition["inputSchema"]["properties"]["observe_effects"]["default"])
        with patch("skills.conductor.observed_run.run_observed") as runner:
            response = handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
                "name": "execute_plan", "arguments": {"goal": "fixture", "dry_run": True,
                                                        "observe_effects": True}}})
        runner.assert_not_called()
        payload = json.loads(response["result"]["content"][0]["text"])
        result = payload["results"][0]
        self.assertEqual(result["effects_before"]["contract"], self.contract)
        self.assertEqual(result["effects_observed"]["process"]["status"], "not_run")

    def test_saved_execution_contains_complete_observation_companion(self):
        before = Path.cwd()
        try:
            os.chdir(self.root)
            reports = []
            with patch("skills.report.timestamped_name", side_effect=lambda name, ext: f"fixed.{ext}"):
                for _ in range(2):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        code = cli(["fixture", "--observe-effects", "--execute", "--dry-run",
                                    "--json", "--save", "both"])
                    self.assertEqual(code, 0)
                    reports.append(json.loads(output.getvalue()))
            self.assertNotEqual(reports[0]["effects_json"], reports[1]["effects_json"])
            for result in reports:
                complete = json.loads(Path(result["effects_json"]).read_text(encoding="utf-8"))
                self.assertEqual(complete, result)
                self.assertEqual(complete["results"][0]["effects_observed"]["schema"],
                                 "botte.effect-observations/v2")
        finally:
            os.chdir(before)


def main() -> int:
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(PlanningEffectsTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
