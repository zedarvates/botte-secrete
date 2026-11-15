"""CLI/MCP contracts for declared cost ranges and measurement suggestions."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.llm_mcp.server import TOOLS
from skills.llm_mcp.test_plan_preferences import ROOT, call


def example():
    return json.loads((ROOT / "examples/parcimonia_plan_uncertainty.json").read_text(encoding="utf-8"))


class UncertaintyBoundaryTests(unittest.TestCase):
    def test_tools_are_lazy_discoverable_read_only_and_closed_world(self):
        for name in ("analyse_plan_uncertainty", "suggest_plan_measurements"):
            definition = next(item for item in TOOLS if item["name"] == name)
            self.assertEqual(definition["annotations"], {
                "readOnlyHint": True, "destructiveHint": False,
                "idempotentHint": True, "openWorldHint": False,
            })
            self.assertFalse(definition["inputSchema"]["additionalProperties"])
            self.assertIn(name, call({"query": name}, "find_tool")["content"][0]["text"])

    def test_mcp_analysis_and_measurements_match_pure_helpers_without_effects(self):
        from skills.conductor.uncertainty import analyse_plan_uncertainty
        from skills.conductor.measurement import suggest_plan_measurements
        request = example()
        for name, operation in (("analyse_plan_uncertainty", analyse_plan_uncertainty),
                                ("suggest_plan_measurements", suggest_plan_measurements)):
            expected = operation(request)
            with patch("subprocess.Popen", side_effect=AssertionError("execution")), \
                    patch("socket.socket", side_effect=AssertionError("network")), \
                    patch("pathlib.Path.write_text", side_effect=AssertionError("storage")), \
                    patch("skills.events.log_event", side_effect=AssertionError("telemetry")), \
                    patch("skills.conductor.verified.execute_verified", side_effect=AssertionError("executor")):
                response = call({"request_json": json.dumps(request)}, name)
            self.assertFalse(response.get("isError", False))
            result = json.loads(response["content"][0]["text"])
            self.assertEqual(result, expected)
            self.assertIsNone(result["selected_candidate_id"])
            self.assertEqual(result["selection_status"], "not_selected")
        self.assertEqual(request, example())

    def test_mcp_rejects_ambiguous_json_and_unsupported_arguments(self):
        for name in ("analyse_plan_uncertainty", "suggest_plan_measurements"):
            for args in ({}, {"request_json": {}}, {"request_json": "{}", "execute": True},
                         {"request_json": '{"schema":"a","schema":"b"}'},
                         {"request_json": '{"value":NaN}'},
                         {"request_json": "x" * (1048576 + 1)},
                         {"request_json": "[" * 1500 + "]" * 1500}):
                with self.subTest(name=name, fields=list(args)):
                    self.assertTrue(call(args, name)["isError"])

    def test_mcp_measurement_bounds_are_checked_at_runtime(self):
        request = json.dumps(example())
        for changes in ({"max_checks": True}, {"max_checks": 0}, {"max_checks": 129},
                        {"max_questions": False}, {"max_questions": 17}, {"max_questions": "1"}):
            with self.subTest(changes=changes):
                self.assertTrue(call({"request_json": request, **changes}, "suggest_plan_measurements")["isError"])
        valid = call({"request_json": request, "max_checks": 1, "max_questions": 1},
                     "suggest_plan_measurements")
        self.assertFalse(valid.get("isError", False))
        report = json.loads(valid["content"][0]["text"])
        self.assertLessEqual(report["analysis"]["variables_checked"], 1)
        self.assertLessEqual(len(report["questions"]), 1)

    def run_cli(self, mode, flags=()):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ranges.json"
            source.write_text(json.dumps(example()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "skills.conductor.cli", mode, str(source), *flags, "--json"],
                cwd=directory, env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["ranges.json"])
            return result

    def test_cli_analysis_and_bounded_measurements_print_results_without_saving(self):
        from skills.conductor.uncertainty import analyse_plan_uncertainty
        from skills.conductor.measurement import suggest_plan_measurements
        analysis = self.run_cli("--analyse-plan-uncertainty")
        self.assertEqual(analysis.returncode, 0, analysis.stderr)
        self.assertEqual(json.loads(analysis.stdout), analyse_plan_uncertainty(example()))
        measured = self.run_cli("--suggest-plan-measurements", ["--max-checks", "1", "--max-questions", "1"])
        self.assertEqual(measured.returncode, 0, measured.stderr)
        self.assertEqual(json.loads(measured.stdout), suggest_plan_measurements(example(), max_checks=1, max_questions=1))

    def test_cli_empty_paths_and_out_of_mode_knobs_cannot_reach_executor(self):
        from skills.conductor.cli import main
        invalid = [
            ["goal", "--analyse-plan-uncertainty", "", "--execute", "--confirm"],
            ["goal", "--suggest-plan-measurements", "", "--execute", "--confirm"],
            ["--analyse-plan-uncertainty", "file.json", "--max-checks", "2"],
            ["--compare-plans", "file.json", "--max-questions", "1"],
            ["goal", "--execute", "--confirm", "--max-checks", "2"],
            ["--suggest-plan-measurements", "file.json", "--selection", "receipt.json"],
            ["--analyse-plan-uncertainty", "file.json", "--propose-plans", "other.json"],
        ]
        for args in invalid:
            with self.subTest(args=args), patch("skills.conductor.cli._run_execute") as execute, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
                execute.assert_not_called()

    def test_actual_stdio_analysis_then_measurement_hints(self):
        request = json.dumps(example())
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "analyse_plan_uncertainty", "arguments": {"request_json": request}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "suggest_plan_measurements", "arguments": {
                    "request_json": request, "max_checks": 1, "max_questions": 1}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-m", "skills.llm_mcp.server"],
                input="\n".join(json.dumps(item) for item in requests) + "\n", cwd=directory,
                env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            messages = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([item["id"] for item in messages], [1, 2, 3])
            for message in messages[1:]:
                self.assertFalse(message["result"].get("isError", False))
                self.assertIsNone(json.loads(message["result"]["content"][0]["text"])["selected_candidate_id"])
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
