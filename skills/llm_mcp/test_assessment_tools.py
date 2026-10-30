"""MCP boundary checks for the advisory Parcimonia tools."""

import json
import unittest

from skills.llm_mcp.server import handle


class AssessmentToolTests(unittest.TestCase):
    def call(self, name, arguments):
        return handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}})["result"]

    def test_assessment_is_discoverable_and_dispatches_without_model(self):
        listed = handle({"id": 1, "method": "tools/list"})["result"]["tools"]
        self.assertIn("assess_task", [tool["name"] for tool in listed])
        result = json.loads(self.call("assess_task", {"task": "Tester le jeu vidéo"})["content"][0]["text"])
        self.assertEqual(result["intent"], "game_playtest")
        self.assertFalse(result["boundaries"]["execution"])
        self.assertIsNone(result["measured_usage"]["cloud_tokens"])

    def test_plan_is_discoverable_on_demand_and_uses_explicit_scope(self):
        result = self.call("find_tool", {"query": "plan_github_research"})
        self.assertIn("plan_github_research", result["content"][0]["text"])
        plan = json.loads(self.call("plan_github_research", {
            "repository": "zedarvates/botte-secrete", "pr_number": 145
        })["content"][0]["text"])
        self.assertEqual(plan["mode"], "pull_request")
        self.assertEqual(plan["execution"]["network_calls"], 0)

    def test_invalid_inputs_surface_as_tool_errors(self):
        for name, args in [
            ("assess_task", {"task": "Read", "execute": True}),
            ("assess_task", {"task": "Read", "context_budget": True}),
            ("plan_github_research", {"repository": "../outside"}),
            ("plan_github_research", {"repository": "a/b", "pr_number": True}),
        ]:
            with self.subTest(name=name, args=args):
                self.assertTrue(self.call(name, args)["isError"])


if __name__ == "__main__":
    unittest.main()
