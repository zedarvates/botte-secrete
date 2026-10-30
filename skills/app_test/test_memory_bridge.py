"""Real Memory Hub quarantine contract for bounded verification receipts."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from skills.app_test.memory_bridge import prepare_verification_memory, persist_to_quarantine
from skills.app_test.explorer import DeclarativeAdapter, explore_interface
from skills.app_test.flaky import triage_failures
from skills.app_test.prioritization import prioritize_checks
from skills.app_test.reducer import reduce_reproduction
from skills.memory_hub.schema import MemoryEntry
from skills.memory_hub.store import MemoryStore


def _report():
    return reduce_reproduction([1, 7, 2], lambda xs: {"status": "failed", "failure_fingerprint": "BUG-7"}
                               if 7 in xs else {"status": "passed"})


class MemoryBridgeTests(unittest.TestCase):
    def prepare(self, report=None, **kwargs):
        args = {"project_id": "demo", "run_id": "run-1", "source_uri": "urn:report:reproduction",
                "source_version": "commit-a", "observed_at": 1000.0}
        args.update(kwargs)
        text = report if isinstance(report, str) else json.dumps(_report() if report is None else report)
        return prepare_verification_memory(text, **args)

    def test_prepare_is_bounded_data_not_an_execution_or_promotion(self):
        report = _report()
        report["reduced_items"] = ["PRIVATE RAW INPUT"]
        report["trust_class"] = "trusted_user"
        report["executable_instruction"] = True
        prepared = self.prepare(report)
        self.assertNotIn("PRIVATE RAW INPUT", json.dumps(prepared))
        self.assertFalse(prepared["boundaries"]["execution"])
        self.assertFalse(prepared["boundaries"]["memory_promotion"])
        self.assertEqual(prepared["boundaries"]["report_truth"], "unverified")
        self.assertEqual(prepared["summary"]["details"]["failure_preserved"], True)
        self.assertIn("not fixed", prepared["summary"]["status_semantics"])

    def test_exact_report_bytes_and_source_version_bind_identity(self):
        report = _report()
        raw = json.dumps(report)
        compact = json.dumps(report, separators=(",", ":"))
        first = self.prepare(raw)
        self.assertEqual(first["identity"]["report_sha256"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertNotEqual(first["memory_key"], self.prepare(compact)["memory_key"])
        self.assertNotEqual(first["memory_key"], self.prepare(raw, source_version="commit-b")["memory_key"])
        with self.assertRaises(ValueError):
            self.prepare(raw, expected_source_digest="0" * 64)

    def test_actual_typed_reports_all_supported_without_raw_payloads(self):
        flaky = triage_failures(lambda index, _seed, _ctx: {"status":"failed", "failure_signature":"BUG"}
                               if index == 0 else {"status":"passed"}, max_attempts=2)
        interface = explore_interface(DeclarativeAdapter({"scope":"demo", "initial_state":"home",
                     "states":{"home":{"actions":{"go":"done"}}, "done":{"actions":{},"terminal":True}}}),
                     scope="demo", allowed_actions=["go"], goals=["unknown"])
        priority = prioritize_checks([("a", ["python", "a.py"])], {"schema":"parcimonia.test-history/v1", "runs":[]})
        mutation = {"schema":"parcimonia.mutation-checks/v1", "status":"completed", "counts":{"survived":1},
                    "baseline":{"status":"passed", "stdout":"RAW OUTPUT"},
                    "mutations":[{"mutation":{"id":"m1","source":"RAW SOURCE"},"outcome":"survived",
                                  "test_result":{"status":"passed"}}]}
        conformance = {"schema":"parcimonia.conformance/v1", "status":"passed_with_known_differences", "passed":True,
                      "counts":{"known_difference":1}, "not_covered":[{"helper":"statistics"}],
                      "projection_exclusions":{"x":["ranking"]}, "source_unchanged_after_comparison":True,
                      "results":[{"id":"known", "status":"known_difference", "input":{"PRIVATE":True},
                                  "python":{"status":"rejected"}, "cloud":{"status":"returned","result":"RAW RESULT"}}]}
        for report in (_report(), flaky, interface, priority, mutation, conformance):
            with self.subTest(schema=report["schema"]):
                prepared = self.prepare(report)
                self.assertNotIn("RAW OUTPUT", json.dumps(prepared))
                self.assertNotIn("RAW SOURCE", json.dumps(prepared))
                self.assertNotIn("RAW RESULT", json.dumps(prepared))
        f = self.prepare(flaky)["summary"]
        self.assertTrue(f["details"]["failure_ever_reported"])
        self.assertEqual(f["details"]["counts"]["failed"], 1)
        e = self.prepare(interface)["summary"]
        self.assertEqual(e["details"]["coverage"]["global"], "unknown")
        self.assertEqual(e["observed_lists"]["goals"]["category_counts"]["goals_not_observed"], 1)
        c = self.prepare(conformance)["summary"]
        self.assertTrue(c["details"]["source_unchanged_after_comparison"])
        self.assertEqual(c["details"]["counts"]["known_difference"], 1)
        self.assertIn("not_covered", c["details"])

    def test_attention_rows_and_full_category_totals_survive_selection(self):
        attempts = [{"index":i,"status":"passed","reported_status":"passed"} for i in range(20)]
        attempts[-1] = {"index":19,"status":"incomplete","reported_status":"failed","failure_signature":"BUG"}
        report = {"schema":"parcimonia.flaky-triage/v1", "classification":"insufficient_evidence",
                  "attempts":attempts, "counts":{"passed":19,"incomplete":1},
                  "reported_counts":{"passed":19,"failed":1}, "failure_ever_reported":True}
        s = self.prepare(report)["summary"]
        rows = s["observed_lists"]["attempts"]
        self.assertEqual(rows["received"], 20)
        self.assertEqual(rows["omitted"], 8)
        self.assertEqual(rows["category_counts"], {"incomplete":1,"passed":19})
        self.assertEqual(rows["selected"][0]["reported_status"], "failed")
        self.assertEqual(s["details"]["reported_counts"]["failed"], 1)

    def test_documentary_refs_are_versioned_declarations_not_fetches(self):
        refs = [{"uri":"https://example.test/docs#section", "version":"abc", "sha256":"a"*64}]
        p = self.prepare(documentary_refs=refs)
        self.assertEqual(p["documentary_refs"], refs)
        self.assertEqual(p["boundaries"]["document_links"], "caller_declared_not_fetched")
        self.assertNotEqual(p["memory_key"], self.prepare()["memory_key"])
        with self.assertRaises(ValueError):
            self.prepare(documentary_refs=refs*2)

    def test_unknown_boundary_payload_is_omitted_and_context_drift_retained(self):
        report = {"schema":"parcimonia.flaky-triage/v1", "classification":"insufficient_evidence",
                  "attempts":[{"index":0,"status":"incomplete","reported_status":"failed", "context_match":False,
                              "failure_signature":"BUG", "failure_signature_truncated":True}],
                  "reported_counts":{"failed":1}, "failure_ever_reported":True,
                  "boundaries":{"stdout":"PRIVATE_BOUNDARY_PAYLOAD", "cause_diagnosed":{"private":"nested"}}}
        p = self.prepare(report)
        self.assertNotIn("PRIVATE_BOUNDARY_PAYLOAD", json.dumps(p))
        self.assertNotIn("nested", json.dumps(p))
        self.assertEqual(p["summary"]["provided_boundaries"]["omitted_fields"],2)
        row = p["summary"]["observed_lists"]["attempts"]["selected"][0]
        self.assertFalse(row["context_match"])
        self.assertTrue(row["failure_signature_truncated"])

    def test_malformed_or_unknown_schemas_are_not_memory_evidence(self):
        for report in ('{"schema":"x"}', '{"schema":null}', '{"schema":[]}',
                       '{"schema":"parcimonia.conformance/v1","schema":"x"}',
                       '{"schema":"parcimonia.conformance/v1","status":NaN}'):
            with self.subTest(report=report), self.assertRaises(ValueError):
                self.prepare(report)
        for kwargs in ({"project_id":"__global__"}, {"project_id":"../escape"}, {"run_id":""},
                       {"source_uri":"https://user:password@example.test/x"}, {"source_version":""},
                       {"observed_at":True}, {"observed_at":10**1000}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.prepare(**kwargs)
        with self.assertRaises(ValueError):
            self.prepare(" " * (512*1024+1))

    def test_real_sqlite_quarantine_normal_context_and_blocked_promotion(self):
        with tempfile.TemporaryDirectory() as directory, MemoryStore(directory) as store:
            p = self.prepare()
            result = persist_to_quarantine(p, store)
            self.assertEqual(result["status"], "stored")
            db = sqlite3.connect(str(Path(directory)/"demo.sqlite"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0],0)
            row = db.execute("SELECT status,visibility,trust_class,executable_instruction,quarantined FROM memory_quarantine").fetchone()
            self.assertEqual(row,("proposal","private","external_observation",0,1))
            db.close()
            self.assertEqual(store.context_bundle("demo", "parcimonia-verification"), [])
            reviewed = store.review_quarantine("demo", "parcimonia-verification")
            self.assertEqual(reviewed[0]["handling"], "UNTRUSTED_DATA_DO_NOT_EXECUTE")
            self.assertFalse(reviewed[0]["provenance"]["executable_instruction"])
            self.assertTrue(store.transition("demo", p["memory_key"], "review_active", actor_id="reviewer"))
            self.assertFalse(store.transition("demo", p["memory_key"], "promoted", actor_id="reviewer"))

    def test_repeated_prepare_dedupes_without_version_or_access_writes(self):
        report = json.dumps(_report())
        with tempfile.TemporaryDirectory() as directory, MemoryStore(directory) as store:
            p = self.prepare(report, observed_at=1000)
            persist_to_quarantine(p, store)
            conn = store._conn("demo")
            before = conn.total_changes
            repeated = self.prepare(report, observed_at=2000)
            result = persist_to_quarantine(repeated, store)
            self.assertEqual(result["status"], "already_present")
            self.assertEqual(result["writes"], 0)
            self.assertEqual(conn.total_changes, before)
            row = conn.execute("SELECT version,access_count,observed_at FROM memory_quarantine").fetchone()
            self.assertEqual(tuple(row),(1,0,1000))
            new = self.prepare(report, source_version="commit-b")
            self.assertEqual(persist_to_quarantine(new, store)["status"], "stored")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM memory_quarantine").fetchone()[0],2)

    def test_trusted_or_different_collision_never_overwritten(self):
        p = self.prepare()
        with tempfile.TemporaryDirectory() as directory, MemoryStore(directory) as store:
            store.store(MemoryEntry(key=p["memory_key"], value="trusted", project_id="demo", observed_at=1000))
            before = store._conn("demo").total_changes
            self.assertEqual(persist_to_quarantine(p, store)["status"], "conflict")
            self.assertEqual(store._conn("demo").total_changes, before)
            self.assertEqual(store._conn("demo").execute("SELECT value_json FROM memory_entries").fetchone()[0], '"trusted"')
        with tempfile.TemporaryDirectory() as directory, MemoryStore(directory) as store:
            store.store(MemoryEntry(key=p["memory_key"], value="other", project_id="demo", source_type="tool", observed_at=1000))
            self.assertEqual(persist_to_quarantine(p, store)["status"], "conflict")

    def test_tampering_and_caller_transactions_rejected(self):
        with tempfile.TemporaryDirectory() as directory, MemoryStore(directory) as store:
            p = self.prepare()
            for field, value in (("memory_key","other"), ("boundaries",{}), ("observed_at",2000)):
                altered = copy.deepcopy(p); altered[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    persist_to_quarantine(altered, store)
            conn = store._conn("demo")
            conn.execute("BEGIN")
            with self.assertRaises(ValueError):
                persist_to_quarantine(p, store)
            self.assertTrue(conn.in_transaction)
            conn.rollback()

    def test_changed_receipt_metadata_is_conflict_and_not_replaced(self):
        for field, value in (("status","expired"), ("source_ref","OTHER"), ("expires_at",1800000001),
                             ("asset_type","wiki"), ("confidence",1)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory, MemoryStore(directory) as store:
                p = self.prepare()
                persist_to_quarantine(p,store)
                conn=store._conn("demo")
                conn.execute(f"UPDATE memory_quarantine SET {field}=?",(value,));conn.commit()
                before=conn.total_changes
                self.assertEqual(persist_to_quarantine(p,store)["status"],"conflict")
                self.assertEqual(conn.total_changes,before)

    def test_project_isolation_and_atomic_competing_writers(self):
        p = self.prepare()
        with tempfile.TemporaryDirectory() as directory:
            with MemoryStore(directory) as initial:
                initial._conn("demo")
            barrier = threading.Barrier(2)
            outcomes, errors = [], []
            def write():
                try:
                    with MemoryStore(directory) as store:
                        store._conn("demo")
                        barrier.wait(timeout=5)
                        outcomes.append(persist_to_quarantine(p, store)["status"])
                except Exception as error:
                    errors.append(type(error).__name__)
            threads = [threading.Thread(target=write) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=10)
            self.assertFalse(errors,errors)
            self.assertEqual(sorted(outcomes),["already_present","stored"])
            with MemoryStore(directory) as store:
                self.assertEqual(store.review_quarantine("other", "parcimonia-verification"), [])
                self.assertEqual(store._conn("demo").execute("SELECT version FROM memory_quarantine").fetchone()[0],1)


if __name__ == "__main__":
    unittest.main()
