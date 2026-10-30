"""Real JSON child-process behavior, including unavailable and incomplete runs."""
import sys
import unittest

from skills.app_test.process_oracle import invoke_json


class ProcessOracleTests(unittest.TestCase):
    def test_huge_integer_deadline_is_invalid_without_launch(self):
        with self.assertRaises(ValueError):
            invoke_json([sys.executable], {}, timeout_seconds=10**1000)

    def invoke(self, code, **kwargs):
        return invoke_json([sys.executable, "-c", code], ["é", 2], **kwargs)

    def test_actual_json_process_and_input_roundtrip(self):
        r = self.invoke('import json,sys; x=json.load(sys.stdin); print(json.dumps({"status":"failed","failure_fingerprint":"BUG","seen":x}))')
        self.assertEqual(r["status"], "failed")
        self.assertEqual(r["seen"], ["é", 2])
        self.assertEqual(r["exit"], 0)

    def test_nonzero_exit_overrides_forged_success(self):
        r = self.invoke('print(\'{"status":"passed"}\'); raise SystemExit(7)')
        self.assertEqual(r["status"], "error")

    def test_incomplete_and_duplicate_json_do_not_pass(self):
        for text in ('not JSON', '{"status":"failed","status":"passed"}', '{"status":NaN}'):
            with self.subTest(text=text):
                self.assertEqual(self.invoke(f'print({text!r})')["status"], "incomplete")

    def test_timeout_and_missing_command_are_explicit(self):
        self.assertEqual(self.invoke('import time; time.sleep(1)', timeout_seconds=0.05)["status"], "timeout")
        self.assertEqual(invoke_json(["/definitely-missing-parcimonia-oracle"], {})["status"], "not_run")

    def test_output_cap_and_own_provenance(self):
        self.assertEqual(self.invoke('print("x"*1000)', max_output_bytes=256)["status"], "incomplete")
        r = self.invoke('print(\'{"status":"passed","exit":9,"command_sha256":"forged"}\')')
        self.assertEqual(r["exit"], 0)
        self.assertNotEqual(r["command_sha256"], "forged")


if __name__ == "__main__":
    unittest.main()
