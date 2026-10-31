"""Statistics discovery, task assessment and execution through real boundaries."""

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from skills.llm_mcp.lazy import CORE_TOOL_NAMES, find_tool
from skills.llm_mcp.server import TOOLS, handle
from skills.preflight.assessment import assess_task
from skills.solvers import compute_statistics


class StatisticsIntegrationTests(unittest.TestCase):
    def call(self, arguments):
        return handle({"jsonrpc": "2.0", "id": 17, "method": "tools/call",
                       "params": {"name": "compute_statistics", "arguments": arguments}})["result"]

    def test_discovery_returns_schema_without_expanding_core(self):
        self.assertNotIn("compute_statistics", CORE_TOOL_NAMES)
        matches = find_tool("compute_statistics", TOOLS)["matches"]
        tool = next(item for item in matches if item["name"] == "compute_statistics")
        self.assertIn("values", tool["inputSchema"]["required"])
        self.assertFalse(tool["inputSchema"]["additionalProperties"])

    def test_mcp_executes_supplied_data_without_model_or_network(self):
        # Import the engine before these guards so imports are not the subject
        # of the check. Exercise the actual MCP handler, not a mock calculator.
        expected = compute_statistics([10, 20, 30, 40], percentiles=[95])
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                patch("skills.llm_mcp.server.LocalLLMClient", side_effect=AssertionError("model")):
            result = self.call({"values": [10, 20, 30, 40], "percentiles": [95]})
        self.assertNotIn("isError", result)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload, expected)
        self.assertEqual(payload["results"]["mean"], 25)
        self.assertEqual(payload["percentiles"][0]["value"], 38.5)

    def test_mcp_refuses_invalid_and_unknown_arguments(self):
        for args in ({}, {"values": [True]}, {"values": [float("nan")]},
                     {"values": [1], "path": "data.csv"},
                     {"values": [1], "operations": ["variance_sample"]}):
            with self.subTest(args=args):
                self.assertTrue(self.call(args)["isError"])

    def test_french_and_english_requests_offer_the_actual_tool(self):
        offered = [{"name": tool["name"], "description": tool["description"]}
                   for tool in TOOLS if tool["name"] in {"compute_statistics", "plan_github_research"}]
        for task in ("Calcule la moyenne des temps de réponse", "Compute statistics for these values",
                     "Calculer les statistiques des tests terminés", "Mean of 1, 2 and 3",
                     "Compute standard deviation", "Compute the average", "Compute stats",
                     "Calculer l'écart-type", "Calculer la somme"):
            with self.subTest(task=task):
                result = assess_task(task, offered)
                self.assertEqual(result["intent"], "statistics")
                self.assertEqual(result["candidate_tools"][0]["name"], "compute_statistics")
                self.assertFalse(result["boundaries"]["execution"])

    def test_reading_quotes_negation_and_mixed_work_do_not_force_calculation(self):
        self.assertEqual(assess_task("Lire les statistiques")["intent"], "read_analysis")
        self.assertEqual(assess_task('Lire ce texte: "Compute statistics"')["intent"], "read_analysis")
        for task in ("Ne calcule pas les statistiques", "Explain statistics",
                     "Compute statistics and run tests", "Fix code and calculate the mean"):
            with self.subTest(task=task):
                self.assertEqual(assess_task(task)["status"], "abstained")

    def test_cli_reads_the_same_contract_on_stdin(self):
        root = Path(__file__).resolve().parents[2]
        request = {"values": [10, 20, 30, 40], "percentiles": [95]}
        result = subprocess.run([sys.executable, "-m", "skills.solvers.cli", "stats"],
                                input=json.dumps(request), cwd=root, capture_output=True,
                                text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), compute_statistics(**request))

    def test_cli_bad_input_returns_json_and_failure_exit(self):
        root = Path(__file__).resolve().parents[2]
        for request in ('{"values":[true]}', '{"values":[NaN]}', '{"values":[1],"unknown":true}', '[]'):
            with self.subTest(request=request):
                result = subprocess.run([sys.executable, "-m", "skills.solvers.cli", "stats"],
                                        input=request, cwd=root, capture_output=True,
                                        text=True, encoding="utf-8", timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("error", json.loads(result.stdout))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StatisticsIntegrationTests)
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
