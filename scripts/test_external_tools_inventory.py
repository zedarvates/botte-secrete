"""Regression tests for truthful external-tool version observations."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import inventory_external_tools as inventory


class ExternalToolsInventoryTests(unittest.TestCase):
    def test_stable_version_comparison_and_prerelease_uncertainty(self):
        for version, expected in [("0.9.0", "older_than_reference"),
                                  ("0.49.0", "matches_reference"),
                                  ("0.100.0", "newer_than_reference"),
                                  ("0.49.0-rc1", "unrecognized_version"),
                                  ("0.49.0+local", "unrecognized_version")]:
            with self.subTest(version=version):
                self.assertEqual(inventory.version_status(version, "0.49.0"), expected)

    def test_missing_rtk_does_not_invoke_a_process(self):
        with patch.object(inventory.shutil, "which", return_value=None), \
                patch.object(inventory.subprocess, "run") as run:
            self.assertEqual(inventory.inspect_rtk("0.49.0")["version_status"], "not_found_on_path")
            run.assert_not_called()

    def test_rtk_version_probe_never_installs_or_initializes(self):
        completed = subprocess.CompletedProcess([], 0, "rtk 0.49.0\n", "")
        with patch.object(inventory.subprocess, "run", return_value=completed) as run:
            result = inventory.inspect_rtk("0.49.0", "C:/Tools with spaces/rtk.exe")
            run.assert_called_once_with(
                ["C:/Tools with spaces/rtk.exe", "--version"], stdin=subprocess.DEVNULL,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=5, shell=False,
            )
        self.assertEqual(result["version_status"], "matches_reference")
        self.assertEqual(result["compatibility"], "not_tested")

    def test_rtk_errors_remain_unknown(self):
        for error in [OSError("unavailable"), subprocess.TimeoutExpired("rtk", 5)]:
            with self.subTest(error=type(error).__name__), \
                    patch.object(inventory.subprocess, "run", side_effect=error):
                result = inventory.inspect_rtk("0.49.0", "rtk")
                self.assertEqual(result["version_status"], "probe_failed")
                self.assertIsNone(result["observed_version"])

    def test_failed_or_wrong_binary_cannot_match(self):
        for code, output in [(1, "rtk 0.49.0"), (0, "other-tool 0.49.0")]:
            with self.subTest(code=code), patch.object(inventory.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], code, output, "")):
                result = inventory.inspect_rtk("0.49.0", "rtk")
                self.assertIsNone(result["observed_version"])

    def test_ponytail_metadata_fingerprint_does_not_claim_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'{"name":"@dietrichgebert/ponytail","version":"4.9.0"}'
            (root / "package.json").write_bytes(raw)
            # Reading metadata must not execute plugin scripts, even if present.
            (root / "index.js").write_text("throw new Error('must not execute');", encoding="utf-8")
            with patch.object(inventory.subprocess, "run") as run:
                result = inventory.inspect_ponytail(root, "4.9.0")
                run.assert_not_called()
            self.assertEqual(result["version_status"], "matches_reference")
            self.assertEqual(result["active_in_agent"], "not_checked")
            self.assertEqual(result["compatibility"], "not_tested")
            self.assertEqual(result["manifests"][0]["sha256"], hashlib.sha256(raw).hexdigest())

    def test_codex_and_claude_manifests_with_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in [".codex-plugin/plugin.json", ".claude-plugin/plugin.json"]:
                file = root / relative
                file.parent.mkdir()
                file.write_text('{"name":"ponytail","version":"4.9.0"}', encoding="utf-8-sig")
            result = inventory.inspect_ponytail(root, "4.9.0")
            self.assertEqual(result["version_status"], "matches_reference")
            self.assertEqual(len(result["manifests"]), 2)

    def test_conflicting_ponytail_versions_are_not_silently_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                '{"name":"@dietrichgebert/ponytail","version":"4.9.0"}', encoding="utf-8")
            (root / ".codex-plugin").mkdir()
            (root / ".codex-plugin/plugin.json").write_text(
                '{"name":"ponytail","version":"4.8.4"}', encoding="utf-8")
            result = inventory.inspect_ponytail(root, "4.9.0")
            self.assertEqual(result["version_status"], "conflicting_metadata")
            self.assertIsNone(result["observed_version"])

    def test_bad_metadata_never_counts_as_current(self):
        for raw in [b'not json', b'[]', b'{"name":"other","version":"4.9.0"}',
                    b'{"name":"@dietrichgebert/ponytail","version":490}', b'x' * 65537]:
            with self.subTest(raw=raw[:30]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "package.json").write_bytes(raw)
                result = inventory.inspect_ponytail(root, "4.9.0")
                self.assertEqual(result["version_status"], "metadata_error")
                self.assertIsNone(result["observed_version"])

    def test_empty_root_is_not_evidence_of_machine_wide_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inventory.inspect_ponytail(Path(directory), "4.9.0")
            self.assertEqual(result["version_status"], "metadata_not_found")

    def test_unspecified_plugin_root_is_not_checked(self):
        output = io.StringIO()
        with patch.object(inventory.shutil, "which", return_value=None), \
                contextlib.redirect_stdout(output):
            self.assertEqual(inventory.main([]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["ponytail"][0]["version_status"], "not_checked")
        self.assertEqual(report["rtk"]["version_status"], "not_found_on_path")

    def test_separate_installations_keep_separate_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            args = []
            for i, version in enumerate(["4.8.4", "4.9.0"]):
                root = Path(directory) / str(i)
                root.mkdir()
                (root / "package.json").write_text(json.dumps(
                    {"name": "@dietrichgebert/ponytail", "version": version}), encoding="utf-8")
                args.extend(["--ponytail-root", str(root)])
            output = io.StringIO()
            with patch.object(inventory.shutil, "which", return_value=None), \
                    contextlib.redirect_stdout(output):
                inventory.main(args)
            report = json.loads(output.getvalue())
            self.assertEqual([x["version_status"] for x in report["ponytail"]],
                             ["older_than_reference", "matches_reference"])


if __name__ == "__main__":
    unittest.main()
