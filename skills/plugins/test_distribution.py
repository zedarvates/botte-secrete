"""Offline contracts for the native Codex package and its MCP runtime."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import unicodedata
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

from skills import __version__


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "botte-secrete"


def _validate_listing_interface(interface):
    """Check this package's listing text against documented ingestion limits.

    This is a focused metadata gate, not a public-directory submission validator.
    https://developers.openai.com/plugins/deploy/submission-errors
    """
    def text(value, limit, single_line=True):
        if (not isinstance(value, str) or not value.strip() or len(value) > limit
                or any(unicodedata.category(char) in {"Cf", "Zl", "Zp"}
                       or (unicodedata.category(char) == "Cc" and (single_line or char not in "\r\n"))
                       for char in value)):
            raise ValueError("invalid listing text")

    text(interface.get("displayName"), 30)
    text(interface.get("shortDescription"), 30)
    text(interface.get("longDescription"), 4000, single_line=False)
    text(interface.get("developerName"), 80)
    categories = {"Productivity", "Creativity", "Developer Tools", "Business & Operations",
                  "Data & Analytics", "Communication", "Education & Research", "Security",
                  "Finance", "Healthcare", "Travel", "Entertainment", "Other"}
    if interface.get("category") not in categories:
        raise ValueError("unsupported listing category")
    for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL", "supportURL"):
        if field in interface:
            text(interface[field], 1024)
            parsed = urlsplit(interface[field])
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("listing URLs must use HTTPS without credentials")
    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 20:
        raise ValueError("capabilities must be a non-empty list of strings")
    for capability in capabilities:
        text(capability, 120)
    prompts = interface.get("defaultPrompt")
    if isinstance(prompts, str):
        prompts = [prompts]
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
        raise ValueError("defaultPrompt must contain one to three prompts")
    seen = set()
    for prompt in prompts:
        text(prompt, 128)
        normalized = unicodedata.normalize("NFKC", " ".join(prompt.split()))
        if "@" in prompt or normalized in seen:
            raise ValueError("starter prompts must be unique and omit app mentions")
        seen.add(normalized)


def _validate_branding_assets(interface, plugin_root=PLUGIN):
    """Validate the declared square SVG assets shipped by this package."""
    for field in ("composerIcon", "logo"):
        relative = interface.get(field)
        if (not isinstance(relative, str) or not relative.startswith("./")
                or relative.strip() != relative or ".." in Path(relative).parts):
            raise ValueError("branding paths must stay inside the plugin")
        path = (plugin_root / relative).resolve()
        if (not path.is_relative_to(plugin_root.resolve()) or not path.is_file()
                or path.suffix.lower() != ".svg"):
            raise ValueError("branding must reference a bundled SVG")
        data = path.read_bytes()
        if len(data) > 5 * 1024 * 1024:
            raise ValueError("branding image exceeds 5 MiB")
        svg = ET.fromstring(data.decode("utf-8"))
        if svg.tag.split("}")[-1] != "svg":
            raise ValueError("branding root must be SVG")
        if "width" in svg.attrib and "height" in svg.attrib:
            dimensions = [float(svg.attrib[key]) for key in ("width", "height")]
        else:
            box = [float(value) for value in svg.attrib.get("viewBox", "").split()]
            if len(box) != 4:
                raise ValueError("branding needs numeric dimensions")
            dimensions = box[2:]
        if (any(not math.isfinite(value) or value < 48 for value in dimensions)
                or dimensions[0] != dimensions[1]):
            raise ValueError("branding image must be square and at least 48 pixels")


class DistributionTests(unittest.TestCase):
    def listing_interface(self):
        return json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))["interface"]

    def test_listing_has_capabilities_and_starter_prompt(self):
        interface = self.listing_interface()
        _validate_listing_interface(interface)
        interface["defaultPrompt"] = interface["defaultPrompt"][0]
        _validate_listing_interface(interface)

    def test_listing_ships_square_branding_assets(self):
        _validate_branding_assets(self.listing_interface())

    def test_listing_rejects_missing_unsafe_or_invalid_branding(self):
        for relative in (None, "../outside.svg", "/absolute.svg", "./missing.svg"):
            with self.subTest(relative=relative):
                interface = self.listing_interface()
                interface["composerIcon"] = relative
                with self.assertRaises(ValueError):
                    _validate_branding_assets(interface)
        fixtures = ["<not-svg/>", '<svg width="16" height="16"/>',
                    '<svg width="128" height="64"/>', '<svg width="NaN" height="NaN"/>',
                    '<svg viewBox="0 0 128 64"/>', '<svg/>']
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory)
            for document in fixtures:
                with self.subTest(document=document):
                    (plugin / "bad.svg").write_text(document, encoding="utf-8")
                    interface = {"composerIcon": "./bad.svg", "logo": "./bad.svg"}
                    with self.assertRaises(ValueError):
                        _validate_branding_assets(interface, plugin)
    def test_listing_rejects_missing_or_invalid_capabilities(self):
        invalid = [None, "tools", [], [1], [" "], ["two\nlines"], ["x" * 121], ["x"] * 21]
        for value in invalid:
            with self.subTest(value=value):
                interface = self.listing_interface()
                interface["capabilities"] = value
                with self.assertRaises(ValueError):
                    _validate_listing_interface(interface)

    def test_listing_rejects_invalid_starter_prompts_and_description(self):
        invalid = [None, {}, [], [1], [" "], ["x" * 129], ["two\nlines"], ["run @botte"], ["x"] * 4,
                   ["Same", " Same "], ["Résumé", "Re\u0301sume\u0301"]]
        for value in invalid:
            with self.subTest(value=value):
                interface = self.listing_interface()
                interface["defaultPrompt"] = value
                with self.assertRaises(ValueError):
                    _validate_listing_interface(interface)
        interface = self.listing_interface()
        interface["shortDescription"] = "x" * 31
        with self.assertRaises(ValueError):
            _validate_listing_interface(interface)

    def test_listing_rejects_invalid_identity_category_and_urls(self):
        invalid = {"displayName": "x" * 31, "longDescription": "x" * 4001,
                   "developerName": None, "category": "unsupported",
                   "websiteURL": "http://example.com"}
        for field, value in invalid.items():
            with self.subTest(field=field):
                interface = self.listing_interface()
                interface[field] = value
                with self.assertRaises(ValueError):
                    _validate_listing_interface(interface)

    def test_marketplace_resolves_the_installable_plugin(self):
        catalog = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        entry = next(item for item in catalog["plugins"] if item["name"] == "botte-secrete")
        self.assertEqual(entry["source"]["source"], "local")
        self.assertEqual((ROOT / entry["source"]["path"]).resolve(), PLUGIN)
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        # Local Codex cachebusters retain the separately installed runtime version.
        self.assertEqual(manifest["version"].split("+", 1)[0], __version__)
        version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), __version__)
        self.assertTrue((PLUGIN / manifest["mcpServers"]).is_file())
        self.assertTrue((PLUGIN / manifest["skills"] / "botte-secrete/SKILL.md").is_file())

    def test_installed_subset_preserves_the_license(self):
        self.assertEqual((PLUGIN / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())

    def test_plugin_markdown_links_are_self_contained(self):
        from skills.fallow_like.local_links import extract_markdown_links

        for document in sorted(PLUGIN.rglob("*.md")):
            extracted = extract_markdown_links(document.read_text(encoding="utf-8"))
            self.assertFalse(extracted["truncated"], document)
            self.assertFalse(extracted["issues"], document)
            for link in extracted["links"]:
                parsed = urlsplit(link["target"])
                if parsed.scheme or not parsed.path or link["target"].startswith("//"):
                    continue
                target = (document.parent / unquote(parsed.path)).resolve()
                with self.subTest(document=str(document.relative_to(PLUGIN)),
                                  line=link["line"], target=link["target"]):
                    self.assertTrue(target.is_relative_to(PLUGIN.resolve()),
                                    "documentation must also work in the standalone plugin")
                    self.assertTrue(target.is_file(), "local link target must be bundled")

    def test_mcp_configuration_uses_the_installed_console_entry_point(self):
        config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"]["botte-llm"], {
            "type": "stdio", "command": "botte-mcp",
            "env": {"BOTTE_MCP_LAZY_TOOLS": "0"},
        })
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

    def test_codex_plugin_advertises_all_runtime_tools_before_calls(self):
        """Discovery text cannot register a method in Codex's native catalog."""
        from skills.llm_mcp.server import TOOLS

        launch = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["botte-llm"]
        environment = {**os.environ, "PYTHONUTF8": "1", "BOTTE_NN_AUTO_LABELS": "0"}
        environment.pop("BOTTE_MCP_LAZY_TOOLS", None)
        environment.update(launch.get("env", {}))
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "native-catalog-regression", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"cursor": None, "_meta": {}}},
        ]
        process = subprocess.run([sys.executable, "-m", "skills.llm_mcp.server"], cwd=ROOT,
            env=environment, input="".join(json.dumps(item) + "\n" for item in requests),
            capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = {item["id"]: item for item in map(json.loads, process.stdout.splitlines())}
        offered = responses[2]["result"]["tools"]
        self.assertEqual({item["name"] for item in offered}, {item["name"] for item in TOOLS})
        self.assertEqual(len(offered), len({item["name"] for item in offered}))
        self.assertTrue({"compute_statistics", "find_file_duplicates", "check_local_links"} <= {item["name"] for item in offered})
        self.assertTrue(all(isinstance(item.get("inputSchema"), dict) for item in offered))
        self.assertEqual(responses[1]["result"]["serverInfo"]["version"], __version__)


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(DistributionTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    sys.exit(0 if result.wasSuccessful() else 1)
