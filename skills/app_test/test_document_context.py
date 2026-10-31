"""Actual local files and CLI: content pins, cited lines and bounded reads."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.app_test import document_context as module


ROOT = Path(__file__).resolve().parents[2]


class DocumentContextTests(unittest.TestCase):
    def fixture(self, root, raw=b"# Guide\r\nUnrelated line\r\nFailure context stays visible.\r\n"):
        path = root / "guide.md"
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        refs = [{"uri": "wiki:guide", "version": "v1", "sha256": digest}]
        catalog = {"schema": "parcimonia.local-document-catalog/v1", "documents": [
            {**refs[0], "file": path.name}]}
        return path, refs, catalog

    def test_actual_crlf_document_cites_original_bytes_and_correct_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, refs, catalog = self.fixture(root)
            original = copy.deepcopy((refs, catalog))
            before = path.read_bytes(), path.stat().st_mtime_ns
            result = module.prepare_document_context(refs, catalog, root, "failure context")
            row = result["documents"][0]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(row["source_sha256"], refs[0]["sha256"])
            self.assertEqual(row["citation"]["line"], 3)
            self.assertEqual(row["excerpt"], "Failure context stays visible.")
            self.assertEqual(row["excerpt_sha256"], hashlib.sha256(row["excerpt"].encode()).hexdigest())
            self.assertEqual(original, (refs, catalog))
            self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
            self.assertFalse(result["boundaries"]["source_truth_verified"])
            self.assertEqual(result["boundaries"]["model_calls"], 0)

    def test_changed_bytes_are_findings_without_stale_excerpts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, refs, catalog = self.fixture(root)
            path.write_text("Failure replacement", encoding="utf-8")
            result = module.prepare_document_context(refs, catalog, root, "failure")
            self.assertEqual(result["status"], "findings")
            self.assertEqual(result["documents"][0]["status"], "content_digest_mismatch")
            self.assertNotIn("excerpt", result["documents"][0])

    def test_reference_pin_mismatch_and_uncatalogued_version_open_no_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, refs, catalog = self.fixture(root)
            for change, expected in (({"sha256": "0"*64}, "reference_digest_mismatch"),
                                     ({"version": "v2"}, "version_not_catalogued"),
                                     ({"uri": "wiki:elsewhere"}, "not_catalogued")):
                with self.subTest(expected=expected), patch.object(module, "_read", side_effect=AssertionError("must not read")):
                    result = module.prepare_document_context([{**refs[0], **change}], catalog, root, "failure")
                    self.assertEqual(result["status"], "findings")
                    self.assertEqual(result["documents"][0]["status"], expected)

    def test_absent_document_is_incomplete_not_empty_knowledge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, refs, catalog = self.fixture(root)
            path.unlink()
            result = module.prepare_document_context(refs, catalog, root, "failure")
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["documents"][0]["status"], "unavailable")
            self.assertFalse(path.exists())

    def test_no_lexical_match_has_explicit_selected_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, refs, catalog = self.fixture(root)
            result = module.prepare_document_context(refs, catalog, root, "absenttoken")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["counts"], {"no_match": 1})
            self.assertEqual(result["coverage"]["corpus_coverage"], "explicit_selected_references_only")

    def test_symlink_and_nonregular_sources_never_produce_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, refs, catalog = self.fixture(root)
            target = root / "target.txt"
            path.rename(target)
            try:
                path.symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation unavailable")
            self.assertEqual(module.prepare_document_context(refs, catalog, root, "failure")["status"], "incomplete")
            path.unlink()
            path.mkdir()
            self.assertEqual(module.prepare_document_context(refs, catalog, root, "failure")["status"], "incomplete")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_fifo_does_not_wait_for_a_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, refs, catalog = self.fixture(root)
            path.unlink()
            os.mkfifo(path)
            result = module.prepare_document_context(refs, catalog, root, "failure")
            self.assertEqual(result["documents"][0]["status"], "unavailable")

    def test_catalog_validation_precedes_every_source_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, refs, catalog = self.fixture(root)
            for unsafe in ("../outside.md", "/absolute.md", "folder/../guide.md", "./guide.md",
                           "a\\b.md", "file.py", "C:guide.md", "a//guide.md"):
                bad = copy.deepcopy(catalog)
                bad["documents"][0]["file"] = unsafe
                with self.subTest(path=unsafe), patch.object(module, "_read", side_effect=AssertionError("must not read")):
                    with self.assertRaises(ValueError):
                        module.prepare_document_context(refs, bad, root, "failure")

    def test_invalid_duplicate_and_ambiguous_catalogs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, refs, catalog = self.fixture(root)
            duplicate = copy.deepcopy(catalog)
            duplicate["documents"].append({**duplicate["documents"][0], "file": "other.md"})
            for bad in (None, {}, {**catalog, "schema": []}, duplicate):
                with self.subTest(value=bad), self.assertRaises(ValueError):
                    module.prepare_document_context(refs, bad, root, "failure")
            with self.assertRaises(ValueError):
                module.prepare_document_context(refs*2, catalog, root, "failure")

    def test_file_and_total_byte_budgets_are_not_claimed_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, refs, catalog = self.fixture(root, b"failure "*300)
            for budgets in ({"max_file_bytes": 1024}, {"max_input_bytes": 1024}):
                result = module.prepare_document_context(refs, catalog, root, "failure", **budgets)
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["documents"][0]["status"], "file_byte_budget")
                self.assertEqual(result["coverage"]["input_bytes"], 0)

    def test_document_count_and_escaped_unicode_output_budgets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, refs, catalog = self.fixture(root, ("mot " + "界"*3000).encode())
            entry = catalog["documents"][0]
            catalog["documents"] = [{**entry, "uri": f"wiki:doc{i}"} for i in range(8)]
            refs = [{"uri": e["uri"], "version": e["version"]} for e in catalog["documents"]]
            result = module.prepare_document_context(refs, catalog, root, "mot", max_documents=1)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["counts"]["input_budget"], 7)
            result = module.prepare_document_context(refs, catalog, root, "mot", max_output_bytes=4096)
            self.assertLessEqual(len(module._encode(result)), 4096)
            self.assertEqual(result["status"], "incomplete")
            self.assertGreater(result["coverage"]["documents_omitted_by_output_budget"], 0)

    def test_non_utf8_and_binary_documents_are_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for raw in (b"failure\x00binary", b"failure\xffinvalid"):
                _, refs, catalog = self.fixture(root, raw)
                result = module.prepare_document_context(refs, catalog, root, "failure")
                self.assertEqual(result["status"], "incomplete")
                self.assertNotIn("excerpt", result["documents"][0])

    def test_source_changed_during_read_discards_excerpt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, refs, catalog = self.fixture(root)
            actual = module.os.fstat
            calls = 0
            def concurrent_change(fd):
                nonlocal calls
                calls += 1
                if calls == 2:
                    path.write_bytes(b"new bytes")
                return actual(fd)
            with patch.object(module.os, "fstat", side_effect=concurrent_change):
                result = module.prepare_document_context(refs, catalog, root, "failure")
            self.assertEqual(result["documents"][0]["status"], "source_changed")
            self.assertNotIn("excerpt", result["documents"][0])

    def test_long_line_citation_window_contains_late_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            line = "prefix "*1000 + "failure " + "suffix "*1000
            _, refs, catalog = self.fixture(root, line.encode())
            row = module.prepare_document_context(refs, catalog, root, "failure", max_excerpt_chars=256)["documents"][0]
            self.assertIn("failure", row["excerpt"])
            self.assertFalse(row["full_line_included"])
            start, end = row["citation"]["start_column"], row["citation"]["end_column_exclusive"]
            self.assertEqual(row["excerpt"], line[start-1:end-1])

    def test_cli_real_files_and_changed_digest_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, refs, catalog = self.fixture(root)
            ref_file, catalog_file = root / "refs.json", root / "catalog.json"
            ref_file.write_text(json.dumps(refs), encoding="utf-8")
            catalog_file.write_text(json.dumps(catalog), encoding="utf-8")
            command = [sys.executable, "-m", "skills.app_test.workbench", "document-context",
                "--references", str(ref_file), "--catalog", str(catalog_file), "--root", str(root), "--query", "failure"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["documents"][0]["citation"]["line"], 3)
            path.write_text("changed failure", encoding="utf-8")
            result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "findings")

    def recalled_fixture(self, root, *, linked=False, capped=False):
        from skills.app_test.flaky import triage_failures
        from skills.app_test.memory_bridge import prepare_verification_memory, persist_to_quarantine
        from skills.app_test.memory_retrieval import retrieve_verification_memory
        from skills.app_test.recalled_links import review_recalled_documents
        from skills.memory_hub.store import MemoryStore
        _, refs, catalog = self.fixture(root)
        refs[0]["uri"] = catalog["documents"][0]["uri"] = "repo:guide"
        report = triage_failures(lambda i, seed, context: {"status": "failed",
            "failure_signature": "authored.failure"}, max_attempts=2)
        memory = root / "memory"
        with MemoryStore(base_dir=memory) as store:
            for i in range(2 if capped else 1):
                proposal = prepare_verification_memory(json.dumps(report), "docs-demo", "run-"+str(i),
                    "urn:run", "v1", documentary_refs=refs)
                persist_to_quarantine(proposal, store)
        recalled = retrieve_verification_memory(memory, "docs-demo", "intermittency",
                                                 max_rows=1 if capped else 256)
        if linked:
            inventory = {"schema": "parcimonia.knowledge-inventory/v1", "completeness": "complete",
                "nodes": [{"id": "doc/guide", "kind": "document", "source_uri": "repo:guide", "source_version": "v1"}], "links": []}
            recalled = review_recalled_documents(recalled, inventory)
        return recalled, catalog

    def test_real_recall_to_document_context_retains_failure_and_upstream_partiality(self):
        for linked, capped in ((False, False), (True, False), (True, True)):
            with self.subTest(linked=linked, capped=capped), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                report, catalog = self.recalled_fixture(root, linked=linked, capped=capped)
                result = module.prepare_recalled_document_context(report, catalog, root, "failure")
                self.assertEqual(result["status"], "incomplete" if capped else "completed")
                self.assertEqual(result["documents"][0]["status"], "matched")
                self.assertIn("intermittency:reproduced_failure", result["upstream"]["reported_outcomes"])
                self.assertEqual(result["upstream"]["status"], report["status"])
                self.assertEqual(result["schema"], "parcimonia.recalled-document-context/v1")

    def test_recall_current_source_contradictions_are_not_erased(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, catalog = self.recalled_fixture(root)
            report["results"][0]["documentary_refs"][0]["comparison"] = "version_mismatch"
            result = module.prepare_recalled_document_context(report, catalog, root, "failure")
            self.assertEqual(result["status"], "findings")
            self.assertEqual(result["upstream"]["comparison_findings"], {"version_mismatch": 1})

    def test_unknown_recall_schema_and_unavailable_scope(self):
        from skills.app_test.memory_retrieval import retrieve_verification_memory
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, catalog = self.fixture(root)
            report = retrieve_verification_memory(root / "absent", "demo", "failure")
            result = module.prepare_recalled_document_context(report, catalog, root, "failure")
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["documents"], [])
            self.assertFalse((root / "absent").exists())
            with self.assertRaises(ValueError):
                module.prepare_recalled_document_context({"schema": "unknown"}, catalog, root, "failure")

    def test_cli_reads_actual_linked_recall_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recalled, catalog = self.recalled_fixture(root, linked=True)
            source, mapping = root / "recall.json", root / "catalog.json"
            source.write_text(json.dumps(recalled), encoding="utf-8")
            mapping.write_text(json.dumps(catalog), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "skills.app_test.workbench", "document-context",
                "--recall", str(source), "--catalog", str(mapping), "--root", str(root), "--query", "failure"],
                cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["documents"][0]["citation"]["line"], 3)
            self.assertEqual(report["upstream"]["selected_receipts"], 1)


if __name__ == "__main__":
    unittest.main()
