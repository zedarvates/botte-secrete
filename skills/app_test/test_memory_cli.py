"""Command integration against real proposal bytes, SQLite and declared links."""

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing

from skills.app_test.prioritization import prioritize_checks

ROOT = Path(__file__).resolve().parents[2]


class MemoryCliTests(unittest.TestCase):
    def call(self, *args):
        result = subprocess.run([sys.executable, "-m", "skills.app_test.workbench", *map(str, args)],
                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
        return result.returncode, json.loads(result.stdout)

    def make_report(self, root):
        report = prioritize_checks([("check", ["check"])], {
            "schema":"parcimonia.test-history/v1", "runs":[]})
        path = root / "report.json"
        raw = json.dumps(report, indent=2).replace("\n", "\r\n").encode("utf-8")
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def args(self, path, digest):
        return ["memory", "--input", path, "--project", "demo", "--run-id", "run-one",
                "--source-uri", "urn:verification:fixture", "--source-version", "source-v1",
                "--source-digest", digest, "--observed-at", "1700000000"]

    def test_preview_preserves_raw_digest_and_does_not_create_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest = self.make_report(root)
            code, report = self.call(*self.args(path, digest))
            self.assertEqual(code, 0, report)
            self.assertEqual(report["identity"]["report_sha256"], digest)
            self.assertEqual(list(root.iterdir()), [path])

    def test_explicit_write_is_quarantined_and_repeat_does_not_update_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest = self.make_report(root)
            args = [*self.args(path, digest), "--write-quarantine", "--memory-dir", root/"memory"]
            first, result = self.call(*args)
            self.assertEqual(first, 0, result)
            self.assertEqual(result["persistence"]["status"], "stored")
            second, result = self.call(*args)
            self.assertEqual(second, 0, result)
            self.assertEqual(result["persistence"]["status"], "already_present")
            with closing(sqlite3.connect(root/"memory"/"demo.sqlite")) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0], 0)
                rows = conn.execute("SELECT version,access_count,quarantined,executable_instruction FROM memory_quarantine").fetchall()
                self.assertEqual(rows, [(1,0,1,0)])

    def test_write_needs_explicit_pair_and_wrong_digest_fails_before_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest = self.make_report(root)
            self.assertEqual(self.call(*self.args(path, digest), "--write-quarantine")[0], 2)
            args = self.args(path, "0"*64)
            code, result = self.call(*args, "--write-quarantine", "--memory-dir", root/"memory")
            self.assertEqual(code, 2)
            self.assertFalse((root/"memory").exists())

    def test_actual_knowledge_link_findings_do_not_exit_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "inventory.json"
            document = {"schema":"parcimonia.knowledge-inventory/v1", "completeness":"complete",
                "nodes":[{"id":"r", "kind":"receipt", "source_uri":"urn:r", "source_version":"v1"}],
                "links":[{"source":"r", "target":"missing", "kind":"documents", "source_version":"v1", "target_version":"v1"}]}
            path.write_text(json.dumps(document), encoding="utf-8")
            code, result = self.call("knowledge-links", "--input", path)
            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "findings")
            document["completeness"] = "partial"
            path.write_text(json.dumps(document), encoding="utf-8")
            code, result = self.call("knowledge-links", "--input", path)
            self.assertEqual(code, 2, result)


if __name__ == "__main__":
    unittest.main()
