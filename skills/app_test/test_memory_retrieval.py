"""Actual SQLite contracts for source-cited, non-mutating receipt recall."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from skills.app_test import memory_retrieval as reader
from skills.app_test.memory_bridge import prepare_verification_memory, persist_to_quarantine
from skills.memory_hub.store import MemoryStore


class MemoryRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "memory"
        self.prepared = self.make_receipt()
        with MemoryStore(self.base) as store:
            persist_to_quarantine(self.prepared, store)

    def make_receipt(self, *, run="run-1", uri="urn:report:reproduction", version="commit-a",
                     refs=(), report=None):
        if report is None:
            report = {"schema": "parcimonia.reproduction-reduction/v1", "status": "reduced",
                      "failure_preserved": True, "original_count": 3, "reduced_count": 1}
        return prepare_verification_memory(json.dumps(report), "demo", run, uri, version,
                                           documentary_refs=refs, observed_at=1000.0)

    def recall(self, query="reproduction", **kwargs):
        return reader.retrieve_verification_memory(self.base, "demo", query, **kwargs)

    def mutate(self, sql, parameters=()):
        with closing(sqlite3.connect(self.base / "demo.sqlite")) as connection:
            connection.execute(sql, parameters)
            connection.commit()

    def snapshot(self):
        return {str(path.relative_to(self.base)): (path.stat().st_size,
                hashlib.sha256(path.read_bytes()).hexdigest()) for path in self.base.rglob("*") if path.is_file()}

    def test_existing_receipt_preserves_source_failure_and_untrusted_handling(self):
        result = self.recall()
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["coverage"]["scan_complete"])
        self.assertEqual(result["coverage"]["validated_rows"], 1)
        row = result["results"][0]
        self.assertEqual(row["source"]["uri"], "urn:report:reproduction")
        self.assertEqual(row["source"]["version"], "commit-a")
        self.assertEqual(row["source"]["sha256"], self.prepared["identity"]["report_sha256"])
        self.assertEqual(row["source"]["comparison"], "unknown")
        self.assertTrue(row["summary"]["details"]["failure_preserved"])
        self.assertIn("not fixed", row["summary"]["status_semantics"])
        self.assertTrue(row["quarantined"])
        self.assertFalse(row["executable_instruction"])
        self.assertEqual(result["boundaries"]["raw_report_digest"], "declared_not_rehashed")
        self.assertEqual(result["boundaries"]["source_freshness"], "unknown")

    def test_read_leaves_all_files_counters_versions_and_lifecycle_unchanged(self):
        before = self.snapshot()
        for _ in range(2):
            self.assertEqual(self.recall()["status"], "completed")
        self.assertEqual(self.snapshot(), before)
        with closing(sqlite3.connect(self.base / "demo.sqlite")) as connection:
            row = connection.execute("SELECT version,access_count,status,quarantined FROM memory_quarantine").fetchone()
        self.assertEqual(row, (1, 0, "proposal", 1))

    def test_missing_directory_or_project_is_unavailable_and_creates_nothing(self):
        missing = Path(self.temp.name) / "missing"
        result = reader.retrieve_verification_memory(missing, "demo", "reproduction")
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(missing.exists())
        before = self.snapshot()
        result = reader.retrieve_verification_memory(self.base, "absent", "reproduction")
        self.assertEqual(result["coverage"]["stop_reason"], "store_or_project_missing")
        self.assertEqual(self.snapshot(), before)

    def test_empty_match_is_completed_only_for_exhausted_eligible_scope(self):
        result = self.recall("notpresentanywhere")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"], [])
        self.assertTrue(result["coverage"]["scan_complete"])

    def test_wrong_agent_never_reads_or_counts_private_rows(self):
        result = self.recall(agent_id="other-agent")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["coverage"]["candidate_rows_seen"], 0)
        self.assertEqual(result["results"], [])

    def test_explicit_current_references_compare_exact_versions_and_digests(self):
        cases = [
            ({"uri": "urn:report:reproduction", "version": "commit-b"}, "version_mismatch"),
            ({"uri": "urn:report:reproduction", "version": "commit-a"}, "version_match_digest_unknown"),
            ({"uri": "urn:report:reproduction", "version": "commit-a", "sha256": "f" * 64}, "digest_mismatch"),
            ({"uri": "urn:report:reproduction", "version": "commit-a", "sha256": self.prepared["identity"]["report_sha256"]},
             "version_and_digest_match"),
        ]
        for reference, expected in cases:
            with self.subTest(expected=expected):
                result = self.recall(current_sources=[reference])
                self.assertEqual(result["results"][0]["source"]["comparison"], expected)
                self.assertEqual(result["boundaries"]["source_freshness"], "unknown")

    def test_document_citations_remain_distinct_from_report_source(self):
        receipt = self.make_receipt(run="run-2", refs=[{"uri": "https://example.test/guide", "version": "v1"}])
        with MemoryStore(self.base) as store:
            persist_to_quarantine(receipt, store)
        row = self.recall("guide", current_sources=[{"uri": "https://example.test/guide", "version": "v2"}])["results"][0]
        self.assertEqual(row["source"]["comparison"], "unknown")
        self.assertEqual(row["documentary_refs"][0]["comparison"], "version_mismatch")

    def test_lexical_order_is_deterministic_and_uses_literal_words(self):
        with MemoryStore(self.base) as store:
            persist_to_quarantine(self.make_receipt(run="run-2"), store)
        result = self.recall("reproduction")
        self.assertEqual(result, self.recall("reproduction"))
        keys = [row["memory_key"] for row in result["results"]]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(self.recall("produ")["results"], [])

    def test_unicode_reference_words_are_searchable(self):
        receipt = self.make_receipt(run="unicode", uri="urn:rapport:épreuve")
        with MemoryStore(self.base) as store:
            persist_to_quarantine(receipt, store)
        self.assertEqual(len(self.recall("ÉPREUVE")["results"]), 1)

    def test_row_result_and_output_budgets_are_explicit(self):
        with MemoryStore(self.base) as store:
            for index in range(4):
                persist_to_quarantine(self.make_receipt(run=f"extra-{index}"), store)
        limited = self.recall(max_rows=2)
        self.assertEqual(limited["status"], "incomplete")
        self.assertFalse(limited["coverage"]["scan_complete"])
        self.assertEqual(limited["coverage"]["stop_reason"], "row_budget")
        one = self.recall(max_results=1)
        self.assertEqual(one["coverage"]["matching_rows"], 5)
        self.assertEqual(one["coverage"]["omitted_matches"], 4)
        output = self.recall(max_output_bytes=2048)
        self.assertLessEqual(len(json.dumps(output, ensure_ascii=True, sort_keys=True,
                                separators=(",", ":")).encode("utf-8")), 2048)
        self.assertEqual(output["status"], "incomplete")
        self.assertEqual(output["coverage"]["stop_reason"], "output_byte_budget")

    def test_input_bytes_stop_without_claiming_no_matching_receipts(self):
        result = self.recall(max_input_bytes=1024)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["coverage"]["stop_reason"], "input_byte_budget")
        self.assertFalse(result["coverage"]["scan_complete"])

    def test_time_budget_is_an_incomplete_read(self):
        ticks = iter([0.0, 0.02, 0.04, 0.06, 0.08])
        with mock.patch.object(reader.time, "monotonic", side_effect=lambda: next(ticks, 1.0)):
            result = self.recall(max_seconds=0.01)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["coverage"]["stop_reason"], "time_budget")

    def test_tampered_key_and_provenance_are_not_cited(self):
        for sql in ("UPDATE memory_quarantine SET source_digest='bad'",
                    "UPDATE memory_quarantine SET executable_instruction=1",
                    "UPDATE memory_quarantine SET confidence=1",
                    "UPDATE memory_quarantine SET status='promoted'",
                    "UPDATE memory_quarantine SET key='verification:bad'"):
            with self.subTest(sql=sql):
                original = (self.base / "demo.sqlite").read_bytes()
                self.mutate(sql)
                result = self.recall()
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["coverage"]["invalid_rows"], 1)
                self.assertEqual(result["results"], [])
                (self.base / "demo.sqlite").write_bytes(original)

    def test_malformed_json_and_unhashable_schema_do_not_abort_reader(self):
        with closing(sqlite3.connect(self.base / "demo.sqlite")) as connection:
            original = connection.execute("SELECT value_json FROM memory_quarantine").fetchone()[0]
        bad = json.loads(original)
        bad["identity"]["report_schema"] = []
        for raw in ("{", '{"schema":"x","schema":"x"}', json.dumps(bad)):
            self.mutate("UPDATE memory_quarantine SET value_json=?", (raw,))
            result = self.recall()
            self.assertEqual(result["coverage"]["invalid_rows"], 1)
            self.assertEqual(result["results"], [])

    def test_oversized_value_and_blob_metadata_are_bounded_invalid_observations(self):
        self.mutate("UPDATE memory_quarantine SET value_json=?", ("x" * 65537,))
        result = self.recall()
        self.assertEqual(result["coverage"]["oversized_rows"], 1)
        self.assertEqual(result["coverage"]["input_bytes"], 0)
        self.mutate("UPDATE memory_quarantine SET value_json=?,source_uri=?", ("{}", b"bad"))
        result = self.recall()
        self.assertEqual(result["coverage"]["invalid_rows"], 1)

    def test_arbitrary_detail_payload_is_neither_indexed_nor_emitted(self):
        with closing(sqlite3.connect(self.base / "demo.sqlite")) as connection:
            value = json.loads(connection.execute("SELECT value_json FROM memory_quarantine").fetchone()[0])
        value["summary"]["details"]["instruction"] = "SENTINEL_EXECUTE_DELETE_FILES"
        value["summary"]["observed_lists"]["trace"]["selected"] = [{"reason": "SECRET_RAW_SENTINEL"}]
        self.mutate("UPDATE memory_quarantine SET value_json=?", (json.dumps(value),))
        result = self.recall()
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("SENTINEL", json.dumps(result))
        self.assertEqual(self.recall("SENTINEL_EXECUTE_DELETE_FILES")["results"], [])

    def test_flaky_reported_failure_and_mutation_survivors_remain_visible(self):
        reports = [
            {"schema": "parcimonia.flaky-triage/v1", "classification": "insufficient_evidence",
             "reported_counts": {"failed": 1}, "counts": {"incomplete": 1}, "failure_ever_reported": True},
            {"schema": "parcimonia.mutation-checks/v1", "status": "completed", "counts": {"survived": 1}},
        ]
        with MemoryStore(self.base) as store:
            for index, report in enumerate(reports):
                persist_to_quarantine(self.make_receipt(run=f"failure-{index}", report=report), store)
        flaky = self.recall("intermittency")["results"][0]["summary"]
        self.assertTrue(flaky["details"]["failure_ever_reported"])
        self.assertEqual(flaky["details"]["reported_counts"], {"failed": 1})
        mutation = self.recall("mutation")["results"][0]["summary"]
        self.assertEqual(mutation["details"]["counts"], {"survived": 1})

    def test_projection_retains_mismatch_and_selected_context_drift_with_omissions(self):
        reports = [
            {"schema": "parcimonia.conformance/v1", "status": "failed",
             "counts": {"mismatch": 2, "unexpected_label": 3}},
            {"schema": "parcimonia.flaky-triage/v1", "classification": "insufficient_evidence",
             "attempts": [{"status": "incomplete", "reported_status": "failed", "context_match": False}]},
            {"schema": "parcimonia.test-order/v1", "status": "proposed", "selected_count": 1,
             "ordered": [{"label": "test-a", "observations": 2}]},
        ]
        with MemoryStore(self.base) as store:
            for index, report in enumerate(reports):
                persist_to_quarantine(self.make_receipt(run=f"projection-{index}", report=report), store)
        conform = self.recall("conformance")["results"][0]["summary"]
        self.assertEqual(conform["details"]["counts"], {"mismatch": 2})
        self.assertEqual(conform["projection_omissions"]["detail_counter_labels"], 1)
        flaky = self.recall("intermittency")["results"][0]["summary"]["observed_lists"]["attempts"]
        self.assertEqual(flaky["selected_context_mismatch_count"], 1)
        self.assertEqual(flaky["selected_reported_failure_count"], 1)
        self.assertEqual(flaky["counter_basis"], "selected_bridge_rows_only_not_all_attempts")
        order = self.recall("ordering")["results"][0]["summary"]
        self.assertEqual(order["details"]["selected_count"], 1)
        self.assertEqual(order["observed_lists"]["ordered"]["category_counts"], {"<missing>": 1})
        self.assertEqual(order["projection_omissions"]["selected_row_payloads"], 1)

    def test_nonempty_wal_or_journal_is_unavailable_without_touching_files(self):
        for suffix in ("-wal", "-journal"):
            other = Path(str(self.base / "demo.sqlite") + suffix)
            other.write_bytes(b"active or potentially active data")
            before = self.snapshot()
            result = self.recall()
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["coverage"]["stop_reason"], "active_journal")
            self.assertEqual(self.snapshot(), before)
            other.unlink()

    def test_live_wal_is_refused_instead_of_returning_stale_checkpoint(self):
        connection = sqlite3.connect(self.base / "demo.sqlite")
        self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("UPDATE memory_quarantine SET access_count=10")
        connection.commit()
        before = self.snapshot()
        result = self.recall()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["coverage"]["stop_reason"], "active_journal")
        self.assertEqual(self.snapshot(), before)

    def test_symlink_database_or_directory_is_refused(self):
        alias = Path(self.temp.name) / "alias"
        try:
            alias.symlink_to(self.base, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        result = reader.retrieve_verification_memory(alias, "demo", "reproduction")
        self.assertEqual(result["status"], "unavailable")
        path = self.base / "demo.sqlite"
        original = self.base / "actual.sqlite"
        path.rename(original)
        path.symlink_to(original)
        self.assertEqual(self.recall()["status"], "unavailable")

    def test_old_schema_is_unavailable_and_is_not_migrated(self):
        self.mutate("UPDATE _schema SET version=1")
        before = self.snapshot()
        result = self.recall()
        self.assertEqual(result["coverage"]["stop_reason"], "unsupported_memory_schema")
        self.assertEqual(self.snapshot(), before)

    def test_non_database_is_unavailable_and_not_replaced(self):
        path = self.base / "demo.sqlite"
        path.write_bytes(b"not SQLite")
        before = self.snapshot()
        self.assertEqual(self.recall()["status"], "unavailable")
        self.assertEqual(self.snapshot(), before)

    def test_oversized_database_is_refused_before_sqlite_open(self):
        path = self.base / "demo.sqlite"
        with path.open("r+b") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        before = (path.stat().st_size, path.stat().st_mtime_ns)
        with mock.patch.object(reader.sqlite3, "connect", side_effect=AssertionError("must not open oversized DB")):
            result = self.recall()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["coverage"]["stop_reason"], "database_size_limit")
        self.assertEqual(result["coverage"]["input_bytes"], 0)
        self.assertEqual(result["limits"]["max_database_bytes"], 64 * 1024 * 1024)
        self.assertEqual((path.stat().st_size, path.stat().st_mtime_ns), before)

    def test_invalid_scope_query_budgets_or_current_source_ambiguity_raise(self):
        for kwargs in ({"project_id": "../escape"}, {"query": ""}, {"query": "%"},
                       {"max_rows": True}, {"max_rows": 0}, {"max_results": 65},
                       {"max_seconds": float("inf")}, {"max_output_bytes": 1},
                       {"current_sources": [{"uri": "urn:report:x", "version": "a"},
                                            {"uri": "urn:report:x", "version": "b"}]}):
            args = {"memory_dir": self.base, "project_id": "demo", "query": "reproduction"}
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reader.retrieve_verification_memory(**args)


if __name__ == "__main__":
    unittest.main()
