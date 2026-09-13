"""Hermetic integrity, version-binding and real unittest-receipt checks."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.completion_proof.verify import verify_report
from skills.completion_proof.cli import main as cli


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "app.py").write_text("VALUE = 42\n", encoding="utf-8")
        (self.root / "log.txt").write_text("recorded test output\n", encoding="utf-8")
        self.report = {"status": "complete", "run_id": "run-1",
                       "proof": {"receipt_ref": "receipt.json"}}
        self.receipt = {"schema_version": 1, "run_id": "run-1",
                        "result": {"exit_code": 0, "tests_run": 1, "failures": 0, "errors": 0},
                        "log": {"path": "log.txt", "sha256": sha(self.root / "log.txt")},
                        "sources": [{"path": "app.py", "sha256": sha(self.source / "app.py")}]}
        self.save()

    def save(self):
        (self.root / "report.json").write_text(json.dumps(self.report), encoding="utf-8")
        (self.root / "receipt.json").write_text(json.dumps(self.receipt), encoding="utf-8")
        self.pin = sha(self.root / "receipt.json")

    def verify(self, **kwargs):
        return verify_report(self.root / "report.json", evidence_root=self.root,
                             source_root=self.source,
                             trusted_receipt_sha256=kwargs.get("pin", self.pin))

    def rejected(self, code):
        result = self.verify()
        self.assertFalse(result["verified"])
        self.assertIn(code, result["errors"])

    def test_valid_receipt(self):
        result = self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], "verified_on_recorded_tests")
        self.assertEqual(result["source_files_checked"], ["app.py"])

    def test_absent_reference(self):
        self.report["proof"] = {"cmd_output_ref": "made-up.txt"}
        self.save()
        self.rejected("missing_receipt_reference")

    def test_missing_files(self):
        for name in ("receipt.json", "log.txt", "source/app.py"):
            with self.subTest(name=name):
                path = self.root / name
                data = path.read_bytes()
                path.unlink()
                self.rejected("missing_file")
                path.write_bytes(data)

    def test_modified_receipt_cannot_supply_its_own_pin(self):
        original = self.pin
        self.receipt["result"]["tests_run"] = 12
        self.save()
        self.report["proof"]["receipt_sha256"] = self.pin
        self.save()
        self.pin = original
        self.rejected("receipt_hash_mismatch")

    def test_modified_log(self):
        (self.root / "log.txt").write_text("all passed", encoding="utf-8")
        self.rejected("log_hash_mismatch")

    def test_old_code_version(self):
        (self.source / "app.py").write_text("VALUE = 43\n", encoding="utf-8")
        self.rejected("source_hash_mismatch")

    def test_different_run(self):
        self.report["run_id"] = "run-2"
        self.save()
        self.rejected("run_id_mismatch")

    def test_test_failure_is_not_success(self):
        self.receipt["result"].update(exit_code=1, failures=1)
        self.save()
        result = self.verify()
        self.assertEqual(result["status"], "test_failed")
        self.assertFalse(result["verified"])

    def test_inconsistent_pass_counts_are_not_success(self):
        self.receipt["result"]["errors"] = 1
        self.save()
        self.assertEqual(self.verify()["status"], "test_failed")

    def test_invalid_results(self):
        original = self.receipt["result"].copy()
        for field, value in (("tests_run", 0), ("tests_run", True), ("exit_code", False),
                             ("errors", -1), ("failures", 2), ("exit_code", "0")):
            with self.subTest(field=field, value=value):
                self.receipt["result"] = dict(original, **{field: value})
                self.save()
                self.assertFalse(self.verify()["verified"])

    def test_paths_are_scoped(self):
        for reference in ("../outside", "/tmp/outside", "C:/outside", "//host/share",
                          "source/../log.txt", "source\\app.py", "a:stream", "a\x00b"):
            with self.subTest(reference=reference):
                self.receipt["log"]["path"] = reference
                self.save()
                self.rejected("unsafe_reference")

    def test_link_is_rejected(self):
        link = self.source / "linked.py"
        try:
            link.symlink_to(self.source / "app.py")
        except OSError:
            self.skipTest("symlink creation unavailable on this host")
        self.receipt["sources"][0]["path"] = "linked.py"
        self.save()
        self.rejected("linked_reference")

    def test_receipt_reference_is_scoped(self):
        self.report["proof"]["receipt_ref"] = "../receipt.json"
        self.save()
        self.rejected("unsafe_reference")

    def test_duplicate_and_empty_source_scope(self):
        entry = self.receipt["sources"][0]
        for entries in ([], [entry, entry], [entry] * 129):
            self.receipt["sources"] = entries
            self.save()
            self.assertFalse(self.verify()["verified"])

    def test_json_duplicate_keys_and_malformed_input(self):
        for data in (b'{"status":"complete","status":"complete"}', b'[]', b'{', b'{"x":NaN}'):
            (self.root / "report.json").write_bytes(data)
            self.assertFalse(self.verify()["verified"])

    def test_missing_trust_anchor(self):
        for pin in (None, "", "abc", "F" * 64):
            self.assertFalse(self.verify(pin=pin)["verified"])

    def test_oversized_input(self):
        with patch("skills.completion_proof.verify.MAX_JSON", 8):
            self.rejected("file_too_large")

    def test_unsupported_schema(self):
        for version in (True, 2, "1"):
            self.receipt["schema_version"] = version
            self.save()
            self.rejected("unsupported_schema")

    def test_no_commands_executed(self):
        self.receipt["command"] = ["untrusted-command", "do-not-run"]
        self.save()
        with patch("subprocess.run", side_effect=AssertionError("must not execute")):
            self.assertTrue(self.verify()["verified"])

    def test_cli_requires_explicit_context(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli([str(self.root / "report.json"), "--verify"])

    def test_cli_json_and_report_only_compatibility(self):
        args = [str(self.root / "report.json"), "--verify", "--json",
                "--evidence-root", str(self.root), "--source-root", str(self.source),
                "--receipt-sha256", self.pin]
        (self.source / "app.py").write_text("changed", encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(cli(args), 0)
        self.assertFalse(json.loads(output.getvalue())["verified"])

    def test_actual_execution_then_source_change(self):
        test_file = self.source / "test_app.py"
        test_file.write_text("import unittest\nfrom app import VALUE\nclass T(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(VALUE, 42)\n", encoding="utf-8")
        before = {p.name: sha(p) for p in (test_file, self.source / "app.py")}
        result = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_app"],
                                cwd=self.source, capture_output=True, text=True,
                                encoding="utf-8", timeout=30,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(result.returncode, 0)
        self.assertIn("Ran 1 test", result.stderr)
        self.assertEqual(before, {name: sha(self.source / name) for name in before})
        (self.root / "log.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        self.receipt["result"]["exit_code"] = result.returncode
        self.receipt["log"]["sha256"] = sha(self.root / "log.txt")
        self.receipt["sources"] = [{"path": name, "sha256": value} for name, value in before.items()]
        self.save()  # caller captures pin separately, after the real execution
        self.assertTrue(self.verify()["verified"])
        test_file.write_text("# tests removed\n", encoding="utf-8")
        self.rejected("source_hash_mismatch")

    def test_strict_subprocess_gate(self):
        cases = (("valid", 0), ("missing", 3), ("invalid", 4),
                 ("failed", 5), ("announced", 6), ("io", 7))
        for case, expected in cases:
            with self.subTest(case=case):
                self.report["status"] = "pending" if case == "announced" else "complete"
                self.report["proof"]["receipt_ref"] = "absent.json" if case == "missing" else "receipt.json"
                self.receipt["result"]["exit_code"] = 1 if case == "failed" else 0
                self.save()
                argv = [sys.executable, "-m", "skills.completion_proof.cli",
                        str(self.root / "report.json"), "--verify", "--strict", "--json",
                        "--evidence-root", str(self.root),
                        "--source-root", str(self.source if case != "io" else self.root / "absent"),
                        "--receipt-sha256", "0" * 64 if case == "invalid" else self.pin]
                result = subprocess.run(argv, capture_output=True, text=True,
                                        encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(json.loads(result.stdout)["verified"], case == "valid")
                marker = self.root / (case + "-closed.txt")
                if result.returncode == 0:
                    marker.write_text("closed", encoding="utf-8")
                self.assertEqual(marker.exists(), case == "valid")

    def test_strict_requires_verification(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            cli([str(self.root / "report.json"), "--strict"])
        self.assertEqual(caught.exception.code, 2)

    def test_strict_unknown_or_inconsistent_result_blocks(self):
        argv = [str(self.root / "report.json"), "--verify", "--strict", "--json",
                "--evidence-root", str(self.root), "--source-root", str(self.source),
                "--receipt-sha256", self.pin]
        for result in ({"status": "new_status", "verified": True, "errors": []},
                       {"status": "verified_on_recorded_tests", "verified": False, "errors": []},
                       {"status": "verified_on_recorded_tests", "verified": True, "errors": ["error"]}):
            with patch("skills.completion_proof.verify.verify_report", return_value=result), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli(argv), 4)

    def test_presentation_does_not_promote_unverified_result(self):
        from skills.completion_proof.presentation import format_result
        for result in ({"status": "verified_on_recorded_tests", "verified": False, "errors": []},
                       {"status": "verified_on_recorded_tests", "verified": True, "errors": ["bad"]},
                       {"status": "unknown", "verified": True, "errors": []}):
            self.assertTrue(format_result(result).startswith("Preuve invalide"))

    def test_presentation_explains_source_change_without_echoing_payload(self):
        from skills.completion_proof.presentation import format_result
        result = {"status": "invalid_evidence", "verified": False,
                  "errors": ["source_hash_mismatch", "UNTRUSTED_PAYLOAD"]}
        text = format_result(result)
        self.assertIn("ont changé", text)
        self.assertIn("Relancer les tests", text)
        self.assertNotIn("UNTRUSTED_PAYLOAD", text)

    def test_cli_language_preserves_json_and_strict_exit(self):
        args = [str(self.root / "report.json"), "--verify", "--strict",
                "--evidence-root", str(self.root), "--source-root", str(self.source),
                "--receipt-sha256", self.pin]
        results = []
        for language in ("fr", "en"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli(args + ["--lang", language, "--json"]), 0)
            results.append(json.loads(output.getvalue()))
        self.assertEqual(results[0], results[1])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(cli(args + ["--lang", "fr"]), 0)
        self.assertIn("Vérifié sur ces tests", output.getvalue())
        self.assertIn("1 test(s)", output.getvalue())

    def test_all_skipped_tests_are_not_verified(self):
        self.receipt["result"]["skipped"] = 1
        self.save()
        self.rejected("no_tests_executed")

    def test_skipped_counts_are_validated(self):
        for skipped in (True, -1, 2, "1"):
            with self.subTest(skipped=skipped):
                self.receipt["result"]["skipped"] = skipped
                self.save()
                self.rejected("invalid_test_counts")

    def test_mixed_skipped_and_passed_tests(self):
        self.receipt["result"].update(tests_run=2, skipped=1)
        self.save()
        result = self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual(result["tests_executed"], 1)
        self.assertEqual(result["tests_skipped"], 1)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(VerificationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed - len(result.skipped)} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
