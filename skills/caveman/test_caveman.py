"""Standalone, offline regression tests for Caveman's measurement contract."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from skills.caveman.cli import compress_file, compress_text, main
from skills.caveman.prompts import list_levels


class TestCaveman(unittest.TestCase):
    def test_unchanged_text_cannot_claim_savings_at_any_level(self):
        for text in ("", "é", "Ne pas activer ce candidat.", "é漢🙂" * 400):
            for level in list_levels():
                result = compress_text(text, level)
                self.assertEqual(result["compressed"], text, level)
                self.assertEqual(result["saved_tokens"], 0, level)
                self.assertEqual(result["savings_pct"], 0, level)
                self.assertEqual(result["original_tokens"], result["estimated_tokens"], level)

    def test_file_analysis_is_read_only_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "instructions.md"
            original = "Do not merge.\n" * 200 + "Proof remains pending.\n"
            path.write_text(original, encoding="utf-8")
            for dry_run in (False, True):
                result = compress_file(str(path), "ultra", dry_run)
                self.assertEqual(result["compressed"], original)
                self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_missing_file_fails_in_both_cli_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            for output_format in ("compact", "json"):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main(["compress", str(Path(tmp) / "missing.md"), "--format", output_format])
                self.assertEqual(code, 1)

    def test_json_cli_labels_token_counts_as_estimates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.md"
            path.write_text("é漢🙂", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["compress", str(path), "--format", "json"]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["token_count_method"], "estimated_chars_div_4")
            self.assertFalse(result["applied"])
            self.assertIsNone(result["style_savings_pct"])
            self.assertEqual(result["original_bytes"], len("é漢🙂".encode("utf-8")))


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
