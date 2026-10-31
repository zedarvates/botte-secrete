"""Real command-to-SQLite recall, including absent and active stores."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skills.app_test.flaky import triage_failures
from skills.app_test.memory_bridge import prepare_verification_memory, persist_to_quarantine
from skills.memory_hub.store import MemoryStore


ROOT = Path(__file__).resolve().parents[2]


class RecallCliTests(unittest.TestCase):
    def call(self, directory, *args):
        result = subprocess.run([sys.executable, "-m", "skills.app_test.workbench",
            "recall", "--memory-dir", str(directory), "--project", "demo",
            "--query", "intermittency", *map(str, args)], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertTrue(result.stdout, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def seed(self, directory, *, run="run-alpha", store=None):
        report = triage_failures(lambda index, seed, context: {
            "status": "failed" if index == 0 else "passed",
            "failure_signature": "fixture.failure" if index == 0 else None},
            max_attempts=2)
        proposal = prepare_verification_memory(json.dumps(report), "demo", run,
            "urn:verification:alpha", "source-v1", documentary_refs=[
                {"uri": "repo:docs/example", "version": "docs-v3"}])
        if store is None:
            with MemoryStore(base_dir=directory) as opened:
                result = persist_to_quarantine(proposal, opened)
        else:
            result = persist_to_quarantine(proposal, store)
        self.assertEqual(result["status"], "stored")
        return proposal

    def snapshot(self, directory):
        return {str(p.relative_to(directory)): (p.stat().st_size,
            hashlib.sha256(p.read_bytes()).hexdigest())
            for p in directory.rglob("*") if p.is_file()}

    def test_recall_cites_failed_observation_without_any_file_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            proposal = self.seed(directory)
            before = self.snapshot(directory)
            code, report = self.call(directory)
            self.assertEqual(code, 0, report)
            self.assertEqual(report["status"], "completed")
            text = json.dumps(report)
            for value in ("source-v1", "docs-v3", "intermittent_observed",
                          proposal["identity"]["report_sha256"],
                          "UNTRUSTED_DATA_DO_NOT_EXECUTE"):
                self.assertIn(value, text)
            self.assertEqual(before, self.snapshot(directory))

    def test_missing_store_is_unavailable_and_does_not_create_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "absent"
            code, report = self.call(directory)
            self.assertEqual(code, 2, report)
            self.assertEqual(report["status"], "unavailable")
            self.assertFalse(directory.exists())

    def test_empty_scoped_read_and_capped_read_have_different_exit_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            with MemoryStore(base_dir=directory) as store:
                store._conn("demo")
            code, report = self.call(directory)
            self.assertEqual(code, 0, report)
            self.assertEqual(report["status"], "completed")
            self.seed(directory)
            self.seed(directory, run="run-beta")
            code, report = self.call(directory, "--max-rows", 1)
            self.assertEqual(code, 2, report)
            self.assertEqual(report["status"], "incomplete")

    def test_explicit_current_source_mismatch_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            self.seed(directory)
            declaration = Path(temporary) / "current.json"
            declaration.write_text(json.dumps([
                {"uri": "urn:verification:alpha", "version": "source-v2"}]), encoding="utf-8")
            code, report = self.call(directory, "--current-sources", declaration)
            self.assertEqual(code, 0, report)
            text = json.dumps(report)
            self.assertIn("source-v1", text)
            self.assertTrue("mismatch" in text or "stale" in text, text)

    def test_live_wal_is_unavailable_without_file_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            with MemoryStore(base_dir=directory) as store:
                self.seed(directory, store=store)
                self.assertGreater((directory / "demo.sqlite-wal").stat().st_size, 0)
                before = self.snapshot(directory)
                code, report = self.call(directory)
                self.assertEqual(code, 2, report)
                self.assertEqual(report["status"], "unavailable")
                self.assertEqual(before, self.snapshot(directory))

    def inventory_file(self, temporary, *, completeness="complete", version="docs-v3",
                       absent=False, ambiguous=False, kind="document"):
        nodes = [] if absent else [{"id": "doc/example", "kind": kind,
            "source_uri": "repo:docs/example", "source_version": version}]
        if ambiguous:
            nodes.append({**nodes[0], "id": "doc/duplicate"})
        inventory = {"schema": "parcimonia.knowledge-inventory/v1",
            "completeness": completeness, "nodes": nodes, "links": []}
        path = Path(temporary) / "inventory.json"
        path.write_text(json.dumps(inventory), encoding="utf-8")
        return path

    def test_inventory_match_retains_failure_citations_and_unchanged_sqlite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            proposal = self.seed(directory)
            path = self.inventory_file(temporary)
            before = self.snapshot(directory)
            code, report = self.call(directory, "--inventory", path)
            self.assertEqual(code, 0, report)
            self.assertEqual(report["schema"], "parcimonia.verification-memory-linked-retrieval/v1")
            self.assertEqual(report["status"], "completed")
            text = json.dumps(report)
            for value in ("declared_reference_resolved", "source-v1", "docs-v3",
                          "intermittent_observed", proposal["identity"]["report_sha256"],
                          "UNTRUSTED_DATA_DO_NOT_EXECUTE"):
                self.assertIn(value, text)
            self.assertEqual(before, self.snapshot(directory))

    def test_inventory_missing_vs_unknown_and_version_mismatch_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            self.seed(directory)
            for kwargs, code_expected, label in (
                ({"absent": True}, 1, "missing_in_declared_inventory"),
                ({"absent": True, "completeness": "partial"}, 2, "unknown_reference"),
                ({"version": "docs-v4"}, 1, "version_mismatch"),
                ({"ambiguous": True}, 2, "ambiguous_reference"),
                ({"kind": "task"}, 1, "kind_mismatch")):
                with self.subTest(kwargs=kwargs):
                    path = self.inventory_file(temporary, **kwargs)
                    code, report = self.call(directory, "--inventory", path)
                    self.assertEqual(code, code_expected, report)
                    self.assertIn(label, json.dumps(report))

    def test_inventory_does_not_upgrade_partial_or_missing_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            path = self.inventory_file(temporary)
            code, report = self.call(directory, "--inventory", path)
            self.assertEqual(code, 2, report)
            self.assertEqual(report["status"], "unavailable")
            self.assertFalse(directory.exists())
            self.seed(directory)
            self.seed(directory, run="run-beta")
            code, report = self.call(directory, "--inventory", path, "--max-rows", 1)
            self.assertEqual(code, 2, report)
            self.assertEqual(report["status"], "incomplete")

    def test_explicit_null_inventory_cannot_silently_fall_back_to_plain_recall(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            self.seed(directory)
            path = Path(temporary) / "inventory.json"
            path.write_text("null", encoding="utf-8")
            code, report = self.call(directory, "--inventory", path)
            self.assertEqual(code, 2, report)
            self.assertEqual(report["status"], "invalid")

    def test_inventory_wrapper_rejects_too_small_output_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "memory"
            self.seed(directory)
            path = self.inventory_file(temporary)
            code, report = self.call(directory, "--inventory", path, "--max-output-bytes", 2048)
            self.assertEqual(code, 2, report)
            self.assertEqual(report["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
