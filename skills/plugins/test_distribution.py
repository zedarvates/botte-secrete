"""Offline contracts for the native Codex package and its MCP runtime."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

from skills import __version__


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "botte-secrete"


class DistributionTests(unittest.TestCase):
    def test_marketplace_resolves_the_installable_plugin(self):
        catalog = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        entry = next(item for item in catalog["plugins"] if item["name"] == "botte-secrete")
        self.assertEqual(entry["source"]["source"], "local")
        self.assertEqual((ROOT / entry["source"]["path"]).resolve(), PLUGIN)
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], __version__)
        version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), __version__)
        self.assertTrue((PLUGIN / manifest["mcpServers"]).is_file())
        self.assertTrue((PLUGIN / manifest["skills"] / "botte-secrete/SKILL.md").is_file())

    def test_installed_subset_preserves_the_license(self):
        self.assertEqual((PLUGIN / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())

    def test_mcp_configuration_uses_the_installed_console_entry_point(self):
        config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"]["botte-llm"], {"type": "stdio", "command": "botte-mcp"})
        self.assertIn('botte-mcp = "skills.llm_mcp.server:main"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_runtime_initialize_reports_the_package_version(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "distribution-test", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        result = subprocess.run([sys.executable, "-m", "skills.llm_mcp.server"], cwd=ROOT,
                                input="".join(json.dumps(item) + "\n" for item in requests),
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = {item["id"]: item for item in map(json.loads, result.stdout.splitlines())}
        self.assertEqual(responses[1]["result"]["serverInfo"]["version"], __version__)
        self.assertTrue(responses[2]["result"]["tools"])


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(DistributionTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    sys.exit(0 if result.wasSuccessful() else 1)
