"""Exact-file inspection through CLI, MCP and the advisory task assessor."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.llm_mcp.lazy import CORE_TOOL_NAMES, find_tool
from skills.llm_mcp.server import TOOLS, handle
from skills.preflight.assessment import assess_task


class FileDuplicateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name, data in {"a.bin": b"same", "b.bin": b"same", "c.bin": b"diff"}.items():
            (self.root / name).write_bytes(data)

    def call(self, arguments):
        return handle({"jsonrpc": "2.0", "id": 27, "method": "tools/call",
                       "params": {"name": "find_file_duplicates", "arguments": arguments}})["result"]

    def test_discovery_is_lazy_and_requires_an_explicit_root(self):
        self.assertNotIn("find_file_duplicates", CORE_TOOL_NAMES)
        match = next(item for item in find_tool("find_file_duplicates", TOOLS)["matches"]
                     if item["name"] == "find_file_duplicates")
        self.assertEqual(match["inputSchema"]["required"], ["root"])
        self.assertFalse(match["inputSchema"]["additionalProperties"])

    def test_mcp_returns_verified_groups_without_mutating_content(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                patch("skills.llm_mcp.server.LocalLLMClient", side_effect=AssertionError("model")):
            result = self.call({"root": str(self.root)})
        self.assertNotIn("isError", result)
        report = json.loads(result["content"][0]["text"])
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["group_count"], 1)
        self.assertEqual(report["groups"][0]["match"], "exact_bytes")
        self.assertEqual(report["groups"][0]["file_count"], 2)
        self.assertFalse(report["atomic_snapshot"])
        self.assertGreater(report["summary"]["comparison_bytes_read"], 0)
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()})

    def test_partial_scan_remains_a_report_with_explicit_limits(self):
        result = self.call({"root": str(self.root), "max_total_bytes": 1})
        self.assertNotIn("isError", result)
        report = json.loads(result["content"][0]["text"])
        self.assertEqual(report["status"], "partial")
        self.assertTrue(report["scan_partial"])
        self.assertTrue(report["partial_reasons"])
        self.assertLessEqual(report["summary"]["bytes_read"], 1)

    def test_mcp_rejects_missing_scope_bad_limits_and_destructive_arguments(self):
        for arguments in ({}, {"root": str(self.root), "delete": True},
                          {"root": str(self.root), "max_files": True},
                          {"root": str(self.root), "max_depth": -1},
                          {"root": str(self.root), "exclude_dirs": ["../outside"]}):
            with self.subTest(arguments=arguments):
                self.assertTrue(self.call(arguments)["isError"])

    def test_assessment_only_proposes_exact_file_inspection_for_matching_requests(self):
        offered = [{"name": "find_file_duplicates", "description": "Find exact file duplicates using bytes SHA256 hash; read only local files"}]
        for task in ("Find duplicate files", "Recherche les doublons de fichiers",
                     "Cherche les doublons de fichiers de code", "Détecte les doublons de fichiers"):
            with self.subTest(task=task):
                result = assess_task(task, offered)
                self.assertEqual(result["intent"], "file_duplicates")
                self.assertEqual(result["candidate_tools"][0]["name"], "find_file_duplicates")
                self.assertFalse(result["boundaries"]["execution"])
        for task in ("Find duplicate images", "Find duplicate features", "Search similar duplicate files",
                     "Explain duplicate files", "Ne recherche pas les doublons de fichiers"):
            with self.subTest(task=task):
                self.assertNotEqual(assess_task(task, offered)["intent"], "file_duplicates")
        self.assertEqual(assess_task("Find duplicate files and fix code")["status"], "abstained")

    def test_cli_has_distinct_complete_partial_and_invalid_exit_codes(self):
        checkout = Path(__file__).resolve().parents[2]
        base = [sys.executable, "-m", "skills.fallow_like.duplicates_cli", str(self.root)]
        for extra, expected_exit, expected_status in (
                ([], 0, "complete"), (["--max-total-bytes", "1"], 3, "partial"),
                (["--max-files", "0"], 2, None)):
            with self.subTest(extra=extra):
                result = subprocess.run(base + extra, cwd=checkout, capture_output=True,
                                        text=True, encoding="utf-8", timeout=10)
                self.assertEqual(result.returncode, expected_exit, result.stderr)
                report = json.loads(result.stdout)
                if expected_status:
                    self.assertEqual(report["status"], expected_status)
                else:
                    self.assertIn("error", report)


    @unittest.skipUnless(os.name == "posix", "surrogateescaped filenames are a Unix boundary")
    def test_cli_and_stdio_mcp_preserve_non_utf8_filename_bytes(self):
        raw_name = b"raw-\xff.bin"
        descriptor = os.open(os.fsencode(self.root) + b"/" + raw_name,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, b"same")
        finally:
            os.close(descriptor)
        checkout = Path(__file__).resolve().parents[2]
        cli = subprocess.run([sys.executable, "-m", "skills.fallow_like.duplicates_cli", str(self.root)],
                             cwd=checkout, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        report = json.loads(cli.stdout)
        self.assertIn(raw_name, [os.fsencode(path) for path in report["groups"][0]["paths"]])
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "find_file_duplicates", "arguments": {"root": str(self.root)}}}
        mcp = subprocess.run([sys.executable, "-m", "skills.llm_mcp.server"],
                             input=json.dumps(request) + "\n", cwd=checkout,
                             capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(mcp.returncode, 0, mcp.stderr)
        report = json.loads(json.loads(mcp.stdout)["result"]["content"][0]["text"])
        self.assertIn(raw_name, [os.fsencode(path) for path in report["groups"][0]["paths"]])


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FileDuplicateIntegrationTests)
    result = unittest.TextTestRunner().run(suite)
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"{result.testsRun - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
