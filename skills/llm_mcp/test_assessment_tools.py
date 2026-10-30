"""MCP boundary checks for the advisory Parcimonia tools."""

import json
import unittest

from skills.llm_mcp.server import handle, TOOLS


class AssessmentToolTests(unittest.TestCase):
    def test_knowledge_link_review_is_discoverable_read_only_and_scoped(self):
        tool = next(tool for tool in TOOLS if tool['name']=='review_knowledge_links')
        self.assertEqual(tool['annotations'], {'readOnlyHint':True,'destructiveHint':False,
                                              'idempotentHint':True,'openWorldHint':False})
        found = self.call("find_tool", {"query":"review_knowledge_links"})
        self.assertIn("review_knowledge_links", found["content"][0]["text"])
        inventory = {"schema":"parcimonia.knowledge-inventory/v1", "completeness":"complete",
            "nodes":[{"id":"receipt", "kind":"receipt", "source_uri":"urn:receipt", "source_version":"v1"}],
            "links":[{"source":"receipt", "target":"missing", "kind":"documents", "target_version":"v1"}]}
        raw = self.call("review_knowledge_links", {"inventory_json":json.dumps(inventory)})
        report = json.loads(raw["content"][0]["text"])
        self.assertEqual(report["status"], "findings")
        self.assertEqual(report["counts"]["missing_in_declared_inventory"], 1)

    def test_knowledge_link_tool_rejects_bad_envelopes(self):
        for args in ({"inventory_json":"{}", "execute":True},
                     {"inventory_json":[]},
                     {"inventory_json":'{"schema":"x","schema":"y"}'},
                     {"inventory_json":'{"value":NaN}'}):
            with self.subTest(args=args):
                self.assertTrue(self.call("review_knowledge_links", args)["isError"])

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

    def test_github_summary_preserves_unknowns_and_rejects_extra_arguments(self):
        report = {"repository": "owner/repo", "pull_request": {"number": 7, "state": "closed"}}
        result = self.call("summarize_github_evidence", {"report_json": json.dumps(report)})
        summary = json.loads(result["content"][0]["text"])
        self.assertIsNone(summary["pull_request"]["merged"])
        self.assertFalse(summary["source"]["verified"])
        self.assertIsNone(summary["measurements"]["host_tokens"])
        self.assertTrue(self.call("summarize_github_evidence", {
            "report_json": json.dumps(report), "fetch": True})["isError"])


if __name__ == "__main__":
    unittest.main()
