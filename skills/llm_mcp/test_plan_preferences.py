"""Behavioral CLI and MCP boundaries for supplied plan comparisons."""

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

from skills.llm_mcp.server import TOOLS, handle

ROOT = Path(__file__).resolve().parents[2]


def example():
    return json.loads((ROOT / "examples/parcimonia_plan_preferences.json").read_text(encoding="utf-8"))


def call(arguments, name="compare_plans"):
    return handle({"id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}})["result"]


class PlanPreferenceBoundaryTests(unittest.TestCase):
    def test_tool_discovery_is_lazy_read_only_and_closed_world(self):
        definition = next(item for item in TOOLS if item["name"] == "compare_plans")
        self.assertEqual(definition["annotations"], {
            "readOnlyHint": True, "destructiveHint": False,
            "idempotentHint": True, "openWorldHint": False,
        })
        self.assertFalse(definition["inputSchema"]["additionalProperties"])
        found = call({"query": "compare_plans"}, "find_tool")
        self.assertIn("compare_plans", found["content"][0]["text"])

    def test_mcp_dispatch_matches_library_and_has_no_external_effect(self):
        from skills.conductor.preferences import rank_plans
        request = example()
        expected = rank_plans(request)
        with patch("socket.socket", side_effect=AssertionError("network")), \
                patch("subprocess.Popen", side_effect=AssertionError("execution")), \
                patch("skills.llm_mcp.server.LocalLLMClient", side_effect=AssertionError("model")), \
                patch("pathlib.Path.write_text", side_effect=AssertionError("write")), \
                patch("skills.events.log_event", side_effect=AssertionError("telemetry")):
            response = call({"request_json": json.dumps(request)})
        self.assertFalse(response.get("isError", False))
        self.assertEqual(json.loads(response["content"][0]["text"]), expected)
        self.assertEqual(request, example())

    def test_mcp_rejects_extra_fields_wrong_types_ambiguous_json_and_nonfinite(self):
        for args in ({}, {"request_json": {}}, {"request_json": "{}", "execute": True},
                     {"request_json": '{"schema":"a","schema":"b"}'},
                     {"request_json": '{"n":NaN}'}, {"request_json": '{"n":1e999}'},
                     {"request_json": "x" * (1048576 + 1)},
                     {"request_json": "[" * 1500 + "]" * 1500}):
            with self.subTest(args=str(args)[:100]):
                self.assertTrue(call(args)["isError"])

    def test_stdio_handshake_discovery_and_comparison(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "find_tool", "arguments": {"query": "compare_plans"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "compare_plans", "arguments": {"request_json": json.dumps(example())}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-m", "skills.llm_mcp.server"],
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                cwd=directory, env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            messages = [json.loads(line) for line in process.stdout.splitlines()]
            self.assertEqual([message["id"] for message in messages], [1, 2, 3])
            self.assertIn("serverInfo", messages[0]["result"])
            self.assertIn("compare_plans", messages[1]["result"]["content"][0]["text"])
            ranking = json.loads(messages[2]["result"]["content"][0]["text"])
            self.assertEqual(ranking["status"], "ranked")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def run_cli(self, request, flags=()):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "request.json"
            source.write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "skills.conductor.cli", "--compare-plans", str(source), *flags],
                cwd=directory, env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"},
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["request.json"])
            return result

    def test_cli_reads_requested_file_and_returns_same_result_without_saving(self):
        from skills.conductor.preferences import rank_plans
        request = example()
        result = self.run_cli(request, ["--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), rank_plans(request))

    def test_cli_rejects_execution_and_checkpoint_flags(self):
        for flags in (["--execute"], ["--confirm"], ["--dry-run"], ["--save"],
                      ["--checkpoint", "run.json"], ["--project", "other"],
                      ["--plan", "other.json"], ["--timeout", "5"]):
            with self.subTest(flags=flags):
                result = self.run_cli(example(), flags)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("separate read-only operation", result.stderr)

    def test_empty_comparison_path_cannot_fall_through_to_execution(self):
        from skills.conductor.cli import main
        with patch("skills.conductor.cli._run_execute", return_value=77) as execute, \
                patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:
                main(["test goal", "--compare-plans", "", "--execute", "--confirm"])
        self.assertEqual(error.exception.code, 2)
        execute.assert_not_called()

    def test_cli_nonranking_and_invalid_requests_have_distinct_exits(self):
        data = copy.deepcopy(example())
        data["preferences"]["limits"] = {"peak_ram_gib": 0}
        result = self.run_cli(data)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "no_eligible_plan")
        result = self.run_cli({"schema": "unknown"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
