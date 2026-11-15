"""Read-only CLI/MCP contracts for declared multi-project sharing alternatives."""

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
    return json.loads((ROOT / "examples/parcimonia_plan_synergies.json").read_text(encoding="utf-8"))


class SynergyBoundaryTests(unittest.TestCase):
    def test_tool_is_lazy_discoverable_read_only_and_closed_world(self):
        definition = next(item for item in TOOLS if item["name"] == "analyse_plan_synergies")
        self.assertEqual(definition["annotations"], {
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        })
        self.assertFalse(definition["inputSchema"]["additionalProperties"])
        self.assertEqual(definition["inputSchema"]["required"], ["request_json"])
        found = call({"query": "analyse_plan_synergies"}, "find_tool")
        self.assertIn("analyse_plan_synergies", found["content"][0]["text"])

    def test_mcp_matches_helper_without_effects_or_changing_input(self):
        from skills.conductor.synergies import analyse_plan_synergies
        request = example()
        expected = analyse_plan_synergies(request)
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), \
                patch("socket.socket", side_effect=AssertionError("network")), \
                patch("pathlib.Path.write_text", side_effect=AssertionError("storage")), \
                patch("skills.llm_mcp.server.LocalLLMClient", side_effect=AssertionError("model")), \
                patch("skills.events.log_event", side_effect=AssertionError("telemetry")), \
                patch("skills.conductor.verified.execute_verified", side_effect=AssertionError("executor")):
            response = call({"request_json": json.dumps(request)}, "analyse_plan_synergies")
        self.assertFalse(response.get("isError", False), response)
        result = json.loads(response["content"][0]["text"])
        self.assertEqual(result, expected)
        self.assertEqual(request, example())
        self.assertIsNone(result["selected_candidate_id"])
        self.assertFalse(result["boundaries"]["execution"])

    def test_mcp_rejects_ambiguous_nonfinite_deep_oversized_or_extra_arguments(self):
        cases = [{}, {"request_json": {}}, {"request_json": "{}", "execute": True},
                 {"request_json": "{}", "checkpoint_path": "run.json"},
                 {"request_json": '{"schema":"a","schema":"b"}'},
                 {"request_json": '{"value":NaN}'}, {"request_json": '{"value":1e999}'},
                 {"request_json": "x" * (1048576 + 1)},
                 {"request_json": "[" * 1500 + "]" * 1500}]
        for args in cases:
            with self.subTest(fields=list(args)):
                self.assertTrue(call(args, "analyse_plan_synergies")["isError"])

    def run_cli(self, request):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "request.json"
            source.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            before = source.read_bytes()
            result = subprocess.run([
                sys.executable, "-m", "skills.conductor.cli", "--analyse-plan-synergies", str(source), "--json",
            ], cwd=directory, env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["request.json"])
            return result

    def test_actual_cli_from_outside_checkout_matches_helper_without_saving(self):
        from skills.conductor.synergies import analyse_plan_synergies
        result = self.run_cli(example())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), analyse_plan_synergies(example()))

    def test_actual_cli_invalid_envelope_reports_error_without_dispatch(self):
        request = example()
        request["opportunities"][0]["shared_action_id"] = "missing-action"
        result = self.run_cli(request)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("error", json.loads(result.stdout))

    def test_cli_empty_paths_execution_and_other_mode_flags_cannot_reach_executor(self):
        from skills.conductor.cli import main
        invalid = [
            ["goal", "--analyse-plan-synergies", "", "--execute", "--confirm"],
            ["--analyse-plan-synergies", "", "--execute", "--confirm"],
            ["--analyse-plan-synergies", "file.json", "--checkpoint", "run.json"],
            ["--analyse-plan-synergies", "file.json", "--project", "elsewhere"],
            ["--analyse-plan-synergies", "file.json", "--resume"],
            ["--analyse-plan-synergies", "file.json", "--save"],
            ["--analyse-plan-synergies", "file.json", "--selection", "receipt.json"],
            ["--analyse-plan-synergies", "file.json", "--max-questions", "1"],
            ["--analyse-plan-synergies", "file.json", "--compare-plans", "other.json"],
        ]
        for args in invalid:
            with self.subTest(args=args), patch("skills.conductor.cli._run_execute") as execute, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
                execute.assert_not_called()

    def test_actual_stdio_initialization_discovery_and_analysis(self):
        from skills.conductor.synergies import analyse_plan_synergies
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "find_tool", "arguments": {"query": "analyse_plan_synergies"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "analyse_plan_synergies", "arguments": {"request_json": json.dumps(example())}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-m", "skills.llm_mcp.server"],
                input="\n".join(json.dumps(item) for item in requests) + "\n", cwd=directory,
                env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            messages = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([message["id"] for message in messages], [1, 2, 3])
            self.assertFalse(messages[-1]["result"].get("isError", False))
            self.assertEqual(json.loads(messages[-1]["result"]["content"][0]["text"]), analyse_plan_synergies(example()))
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
