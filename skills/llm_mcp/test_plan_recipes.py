"""Goal-recipe construction through CLI/MCP and the existing choice pipeline."""

from __future__ import annotations

import copy
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


def recipe_example():
    return json.loads((ROOT / "examples/parcimonia_recipe_planning.json").read_text(encoding="utf-8"))


class RecipeBoundaryTests(unittest.TestCase):
    def test_tool_is_lazy_discoverable_read_only_and_closed_world(self):
        definition = next(item for item in TOOLS if item["name"] == "build_plan_candidates")
        self.assertEqual(definition["annotations"], {
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        })
        self.assertFalse(definition["inputSchema"]["additionalProperties"])
        discovery = call({"query": "build_plan_candidates"}, "find_tool")
        self.assertIn("build_plan_candidates", discovery["content"][0]["text"])

    def test_mcp_construction_matches_library_without_effects(self):
        from skills.conductor.recipes import build_plan_candidates
        request = recipe_example()
        expected = build_plan_candidates(request)
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), \
                patch("socket.socket", side_effect=AssertionError("network")), \
                patch("pathlib.Path.write_text", side_effect=AssertionError("storage")), \
                patch("skills.events.log_event", side_effect=AssertionError("telemetry")):
            response = call({"request_json": json.dumps(request)}, "build_plan_candidates")
        self.assertFalse(response.get("isError", False))
        self.assertEqual(json.loads(response["content"][0]["text"]), expected)
        self.assertEqual(request, recipe_example())

    def test_built_candidates_enter_existing_proposal_and_selection_contracts(self):
        from skills.conductor.recipes import build_plan_candidates
        from skills.conductor.preferences import propose_plans
        from skills.conductor.selection import select_plan, validate_selection
        built = build_plan_candidates(recipe_example())
        self.assertEqual(built["status"], "candidates_built")
        request = built["comparison_request"]
        proposal = propose_plans(request)
        self.assertGreaterEqual(len(proposal["options"]), 2)
        self.assertIsNone(proposal["selected_candidate_id"])
        chosen = proposal["options"][-1]["candidate_id"]
        receipt = select_plan(request, chosen, proposal["input_digest"])
        self.assertEqual(receipt["selected_candidate_id"], chosen)
        self.assertEqual(validate_selection(request, receipt), receipt)
        self.assertFalse(receipt["execution_authorized"])

    def test_mcp_rejects_bad_envelopes_and_ambiguous_json(self):
        for arguments in ({}, {"request_json": {}}, {"request_json": "{}", "execute": True},
                          {"request_json": '{"schema":"a","schema":"b"}'},
                          {"request_json": '{"value":NaN}'},
                          {"request_json": "x" * (1048576 + 1)}):
            with self.subTest(fields=list(arguments)):
                self.assertTrue(call(arguments, "build_plan_candidates")["isError"])

    def run_cli(self, request):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "recipes.json"
            source.write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "skills.conductor.cli", "--build-plan-candidates", str(source), "--json"],
                cwd=directory, env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["recipes.json"])
            return result

    def test_cli_construction_matches_library_and_does_not_save(self):
        from skills.conductor.recipes import build_plan_candidates
        request = recipe_example()
        result = self.run_cli(request)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), build_plan_candidates(request))

    def test_cli_missing_recipe_returns_no_candidates_not_execution(self):
        request = copy.deepcopy(recipe_example())
        request["recipes"] = []
        result = self.run_cli(request)
        self.assertEqual(result.returncode, 2, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "no_candidates")
        self.assertIsNone(data["comparison_request"])

    def test_cli_build_mode_rejects_execution_and_other_document_modes(self):
        from skills.conductor.cli import main
        for args in (["goal", "--build-plan-candidates", "", "--execute", "--confirm"],
                     ["--build-plan-candidates", "request.json", "--candidate", "candidate"],
                     ["--build-plan-candidates", "request.json", "--selection", "receipt.json"],
                     ["--build-plan-candidates", "request.json", "--compare-plans", "other.json"]):
            with self.subTest(args=args), patch("skills.conductor.cli._run_execute") as execute, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
                execute.assert_not_called()

    def test_actual_stdio_build_then_propose(self):
        from skills.conductor.recipes import build_plan_candidates
        request = recipe_example()
        comparison = build_plan_candidates(request)["comparison_request"]
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "build_plan_candidates", "arguments": {"request_json": json.dumps(request)}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "propose_plans", "arguments": {"request_json": json.dumps(comparison)}}},
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
            built = json.loads(messages[1]["result"]["content"][0]["text"])
            proposal = json.loads(messages[2]["result"]["content"][0]["text"])
            self.assertEqual(built["comparison_request"], comparison)
            self.assertEqual(proposal["status"], "proposed")
            self.assertIsNone(proposal["selected_candidate_id"])
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
