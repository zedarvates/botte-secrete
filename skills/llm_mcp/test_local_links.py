"""Supplied local-link checking across CLI, MCP and advisory routing."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.llm_mcp.lazy import CORE_TOOL_NAMES, find_tool
from skills.llm_mcp.server import TOOLS, handle
from skills.preflight.assessment import assess_task


class LocalLinkIntegrationTests(unittest.TestCase):
    def payload(self, text="[existing](docs/guide.md)", **extra):
        return {"documents": [{"path": "README.md", "text": text}],
                "available_paths": ["README.md", "docs/guide.md"],
                "inventory_complete": True, **extra}

    def call(self, arguments):
        return handle({"jsonrpc": "2.0", "id": 29, "method": "tools/call",
                       "params": {"name": "check_local_links", "arguments": arguments}})["result"]

    def cli(self, payload, *args):
        return subprocess.run([sys.executable, "-m", "skills.fallow_like.links_cli", *args],
                              input=json.dumps(payload), cwd=Path(__file__).resolve().parents[2],
                              capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_lazy_discovery_advertises_supplied_data_boundary(self):
        self.assertNotIn("check_local_links", CORE_TOOL_NAMES)
        tool = next(t for t in find_tool("check_local_links", TOOLS)["matches"]
                    if t["name"] == "check_local_links")
        self.assertEqual(tool["inputSchema"]["required"], ["documents", "available_paths"])
        self.assertFalse(tool["inputSchema"]["additionalProperties"])
        self.assertIn("No filesystem access", tool["description"])

    def test_mcp_is_pure_and_reports_actual_source_line(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                patch("skills.llm_mcp.server.LocalLLMClient", side_effect=AssertionError("model")), \
                patch("pathlib.Path.exists", side_effect=AssertionError("filesystem")):
            result = self.call(self.payload("Title\n[missing](docs/lost.md)"))
        self.assertNotIn("isError", result)
        report = json.loads(result["content"][0]["text"])
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["counts"]["missing"], 1)
        self.assertEqual(report["findings"][0]["line"], 2)
        self.assertEqual(report["findings"][0]["path"], "README.md")

    def test_partial_inventory_never_declares_a_target_missing(self):
        report = json.loads(self.call(self.payload("[x](absent.md)", inventory_complete=False))["content"][0]["text"])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["counts"]["missing"], 0)
        self.assertEqual(report["counts"]["unresolved"], 1)

    def test_mcp_rejects_unknown_fields_bad_types_and_hidden_document_fields(self):
        for payload in ({}, self.payload(root="/tmp"), self.payload(max_links=True),
                        self.payload(inventory_complete="true"),
                        self.payload(documents=[{"path": "README.md", "text": "", "extra": 1}]),
                        self.payload(documents=[{"path": "../README.md", "text": ""}])):
            with self.subTest(payload=payload):
                self.assertTrue(self.call(payload)["isError"])

    def test_cli_distinguishes_clean_missing_partial_and_invalid(self):
        for payload, expected in ((self.payload(), 0), (self.payload("[x](missing.md)"), 1),
                                  (self.payload(inventory_complete=False), 3),
                                  (self.payload("[x](one.md) [y](two.md)", max_links=1), 3),
                                  (self.payload(max_links=0), 2)):
            with self.subTest(expected=expected, payload=payload):
                result = self.cli(payload)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertIsInstance(json.loads(result.stdout), dict)

    def test_cli_reads_named_json_file_and_rejects_duplicate_keys(self):
        checkout = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(self.payload()), encoding="utf-8")
            result = self.cli({}, str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, "-m", "skills.fallow_like.links_cli"],
                                input='{"inventory_complete":false,"inventory_complete":true}',
                                cwd=checkout, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("duplicate", json.loads(result.stdout)["error"])

    def test_stdio_mcp_and_cli_preserve_unicode_and_have_equal_reports(self):
        payload = self.payload("[é](docs/été.md)")
        cli = self.cli(payload)
        self.assertEqual(cli.returncode, 1, cli.stderr)
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "check_local_links", "arguments": payload}}
        mcp = subprocess.run([sys.executable, "-m", "skills.llm_mcp.server"],
                             input=json.dumps(request) + "\n", cwd=Path(__file__).resolve().parents[2],
                             capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(mcp.returncode, 0, mcp.stderr)
        report = json.loads(json.loads(mcp.stdout)["result"]["content"][0]["text"])
        self.assertEqual(json.loads(cli.stdout), report)
        self.assertEqual(report["findings"][0]["target"], "docs/été.md")

    def test_legacy_script_remains_callable_directly(self):
        checkout = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "yes.md").write_text("", encoding="utf-8")
            source = root / "source.md"
            source.write_text("[yes](yes.md)\n`[code](missing.md)`\n~~~\n[x](missing.md)\n~~~", encoding="utf-8")
            result = subprocess.run([sys.executable, "scripts/check_docs_links.py", str(source)],
                                    cwd=checkout, capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0 broken local links", result.stdout)

    def test_advisory_routing_requires_explicit_local_markdown_scope(self):
        offered = [{"name": "check_local_links", "description": "Check local Markdown links against supplied repository inventory paths"}]
        for task in ("Check local Markdown links", "Vérifie les liens locaux Markdown manquants",
                     "Détecter les références relatives dans README.md"):
            with self.subTest(task=task):
                report = assess_task(task, offered)
                self.assertEqual(report["intent"], "local_links")
                self.assertEqual(report["candidate_tools"][0]["name"], "check_local_links")
                self.assertFalse(report["boundaries"]["execution"])
        for task in ("Vérifie mes références professionnelles", "Check remote Markdown links",
                     "Ne vérifie pas les liens locaux Markdown", "Explain local Markdown links"):
            with self.subTest(task=task):
                self.assertNotEqual(assess_task(task, offered)["intent"], "local_links")
        self.assertEqual(assess_task("Check local Markdown links and fix code")["status"], "abstained")


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"{result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
