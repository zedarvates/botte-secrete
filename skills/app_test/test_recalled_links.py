"""Exact documentary matching from actual SQLite receipt retrievals."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skills.app_test.flaky import triage_failures
from skills.app_test.memory_bridge import prepare_verification_memory, persist_to_quarantine
from skills.app_test.memory_retrieval import retrieve_verification_memory
from skills.app_test.recalled_links import review_recalled_documents
from skills.memory_hub.store import MemoryStore


def inventory(nodes=(), links=(), completeness="complete"):
    return {"schema": "parcimonia.knowledge-inventory/v1", "completeness": completeness,
            "nodes": list(nodes), "links": list(links)}


def node(identity="doc", uri="repo:docs/spec", version="v3", kind="document"):
    return {"id": identity, "kind": kind, "source_uri": uri, "source_version": version}


class RecalledLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "memory"
        self.seed()
        self.report = retrieve_verification_memory(self.directory, "demo", "intermittency")
        self.assertEqual(self.report["status"], "completed")

    def seed(self, refs=None, run="run-one"):
        raw = json.dumps(triage_failures(lambda index, *_: {
            "status": "failed" if index == 0 else "passed",
            "failure_signature": "fixture.failure" if index == 0 else None}, max_attempts=2))
        proposal = prepare_verification_memory(raw, "demo", run, "urn:receipt:run", "source-v1",
            documentary_refs=refs if refs is not None else [{"uri": "repo:docs/spec", "version": "v3"}],
            observed_at=1700000000)
        with MemoryStore(base_dir=self.directory) as store:
            self.assertEqual(persist_to_quarantine(proposal, store)["status"], "stored")

    def match(self, data=None, report=None, **kwargs):
        return review_recalled_documents(self.report if report is None else report,
            inventory([node()]) if data is None else data, **kwargs)

    def test_unique_exact_document_resolves_declaration_and_preserves_failure_citations(self):
        result = self.match()
        self.assertEqual(result["status"], "completed")
        row = result["results"][0]
        self.assertEqual(row["documentary_review"][0]["status"], "declared_reference_resolved")
        for field in self.report["results"][0]:
            self.assertEqual(row[field], self.report["results"][0][field])
        self.assertTrue(row["summary"]["details"]["failure_ever_reported"])
        self.assertEqual(row["summary"]["reported_status"], "intermittent_observed")
        self.assertFalse(row["documentary_review"][0]["verified"])
        self.assertEqual(result["retrieval"], {key: value for key, value in self.report.items() if key != "results"})

    def test_recipe_is_a_documentary_target(self):
        self.assertEqual(self.match(inventory([node(kind="recipe")]))["status"], "completed")

    def test_unique_wrong_version_is_a_finding_without_rewriting_reference(self):
        result = self.match(inventory([node(version="v4")]))
        self.assertEqual(result["status"], "findings")
        self.assertEqual(result["reference_counts"]["version_mismatch"], 1)
        row = result["results"][0]
        self.assertEqual(row["documentary_refs"][0]["version"], "v3")
        self.assertEqual(row["documentary_review"][0]["candidate_nodes"][0]["source_version"], "v4")

    def test_missing_is_relative_to_declared_inventory_completeness(self):
        for completeness, status, outcome in (("complete", "findings", "missing_in_declared_inventory"),
                ("partial", "incomplete", "unknown_reference"), ("unknown", "incomplete", "unknown_reference")):
            with self.subTest(completeness=completeness):
                result = self.match(inventory(completeness=completeness))
                self.assertEqual(result["status"], status)
                self.assertEqual(result["reference_counts"][outcome], 1)
                self.assertEqual(result["coverage"]["global_knowledge_coverage"], "unknown")

    def test_duplicate_exact_targets_are_ambiguous_and_never_arbitrarily_chosen(self):
        result = self.match(inventory([node("z"), node("a")]))
        self.assertEqual(result["status"], "incomplete")
        match = result["results"][0]["documentary_review"][0]
        self.assertEqual(match["status"], "ambiguous_reference")
        self.assertEqual([item["id"] for item in match["candidate_nodes"]], ["a", "z"])

    def test_multiple_wrong_versions_are_ambiguous_but_unique_exact_version_wins(self):
        data = inventory([node("old", version="v1"), node("new", version="v4")])
        self.assertEqual(self.match(data)["reference_counts"]["ambiguous_reference"], 1)
        data["nodes"].append(node("exact"))
        result = self.match(data)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"][0]["documentary_review"][0]["candidate_nodes"],
            [{"id": "exact", "kind": "document", "source_version": "v3"}])

    def test_wrong_kind_cannot_resolve_a_documentary_reference(self):
        result = self.match(inventory([node(kind="capability")]))
        self.assertEqual(result["status"], "findings")
        self.assertEqual(result["reference_counts"]["kind_mismatch"], 1)
        self.assertEqual(result["reference_counts"]["declared_reference_resolved"], 0)

    def test_existing_dependency_cycle_stays_separate_from_receipt_matching(self):
        nodes = [node("a"), node("b", uri="repo:docs/other")]
        links = [{"source": source, "target": target, "kind": "depends_on",
                  "source_version": "v3", "target_version": "v3"} for source, target in (("a", "b"), ("b", "a"))]
        result = self.match(inventory(nodes, links))
        self.assertEqual(result["status"], "findings")
        self.assertEqual(result["reference_counts"]["declared_reference_resolved"], 1)
        self.assertEqual(result["inventory_review"]["counts"]["links"], 2)
        self.assertGreater(result["inventory_review"]["dependencies"]["back_edges_observed"], 0)
        self.assertFalse(result["boundaries"]["receipt_matches_added_to_inventory_graph"])

    def test_unresolved_existing_graph_link_is_not_repaired_by_receipt_or_similarity(self):
        result = self.match(inventory([node()], [{"source": "doc", "target": "spec-missing",
            "kind": "documents", "source_version": "v3", "target_version": "v3"}], "partial"))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reference_counts"]["declared_reference_resolved"], 1)
        self.assertEqual(result["inventory_review"]["counts"]["unknown_reference"], 1)
        self.assertEqual(result["inventory_review"]["lexical_suggestions"]["candidates"], [])

    def test_original_incomplete_and_unavailable_retrievals_cannot_complete(self):
        self.seed(run="run-two")
        limited = retrieve_verification_memory(self.directory, "demo", "intermittency", max_results=1)
        result = self.match(report=limited)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["retrieval"]["status"], "incomplete")
        self.assertEqual(result["retrieval"]["coverage"]["omitted_matches"], 1)
        absent = retrieve_verification_memory(self.directory / "absent", "demo", "intermittency")
        result = self.match(report=absent)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["results"], [])

    def test_completed_empty_read_remains_a_scoped_empty_read(self):
        empty = retrieve_verification_memory(self.directory, "demo", "noSuchWord")
        result = self.match(report=empty)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["coverage"]["references_reviewed"], 0)
        self.assertEqual(result["results"], [])

    def test_current_source_disagreement_stays_a_finding_even_if_inventory_matches(self):
        report = retrieve_verification_memory(self.directory, "demo", "intermittency",
            current_sources=[{"uri": "repo:docs/spec", "version": "v4"},
                             {"uri": "urn:receipt:run", "version": "source-v2"}])
        result = self.match(report=report)
        self.assertEqual(result["status"], "findings")
        self.assertEqual(result["reference_counts"]["declared_reference_resolved"], 1)
        self.assertEqual(result["current_source_comparison_findings"]["documentary_refs"]["version_mismatch"], 1)
        self.assertEqual(result["current_source_comparison_findings"]["report_sources"]["version_mismatch"], 1)
        self.assertEqual(result["results"][0]["source"]["comparison"], "version_mismatch")

    def test_digest_bases_and_unknown_authenticity_are_never_conflated(self):
        self.seed(refs=[{"uri": "repo:docs/hashed", "version": "v3", "sha256": "a"*64}], run="hashed")
        report = retrieve_verification_memory(self.directory, "demo", "hashed", current_sources=[
            {"uri": "repo:docs/hashed", "version": "v3", "sha256": "b"*64}])
        result = self.match(inventory([node(uri="repo:docs/hashed")]), report=report)
        self.assertEqual(result["status"], "findings")
        self.assertEqual(result["current_source_comparison_findings"]["documentary_refs"]["digest_mismatch"], 1)
        self.assertEqual(result["results"][0]["source"]["digest_basis"], "raw_report_utf8_bytes")
        self.assertEqual(result["results"][0]["documentary_refs"][0]["digest_basis"], "caller_declared_document_bytes")
        self.assertFalse(result["coverage"]["reference_digests_compared_to_inventory"])
        self.assertEqual(result["retrieval"]["boundaries"]["report_authenticity"], "unknown")

    def test_inputs_are_immutable_and_review_performs_no_sqlite_access(self):
        data = inventory([node()])
        before = copy.deepcopy((self.report, data))
        with patch("sqlite3.connect", side_effect=AssertionError("unexpected IO")):
            self.match(data)
        self.assertEqual((self.report, data), before)

    def test_ascii_budget_trims_unicode_graph_details_explicitly(self):
        nodes = [node(str(index)+"界"*35, uri="urn:doc:"+str(index), version="v1") for index in range(32)]
        result = self.match(inventory(nodes), max_output_bytes=8192)
        raw = json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode()
        self.assertLessEqual(len(raw), 8192)
        self.assertEqual(result["status"], "incomplete")
        self.assertGreater(result["coverage"]["inventory_graph_details_omitted_by_wrapper_budget"], 0)
        self.assertGreater(result["inventory_review"]["unlinked_node_ids_omitted"], 0)
        self.assertEqual(result["inventory_review"]["counts"]["nodes"], 32)

    def test_result_budget_omission_keeps_reference_counts_and_retrieval_identity(self):
        refs = [{"uri": "repo:"+str(index)+"é"*200, "version": "v3"} for index in range(32)]
        self.seed(refs=refs, run="long")
        report = retrieve_verification_memory(self.directory, "demo", "long")
        data = inventory([node(str(index), uri=ref["uri"]) for index, ref in enumerate(refs)])
        result = self.match(data, report=report, max_output_bytes=8192)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["reference_counts"]["declared_reference_resolved"], 32)
        self.assertEqual(result["coverage"]["reference_details_omitted_by_output_budget"], 32)
        self.assertEqual(result["retrieval"]["query_sha256"], report["query_sha256"])
        self.assertEqual(len(result["source"]["retrieval_sha256"]), 64)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode()), 8192)

    def test_candidate_detail_omission_is_explicit_and_incomplete(self):
        result = self.match(inventory([node(str(index), kind="task") for index in range(10)]))
        match = result["results"][0]["documentary_review"][0]
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(match["candidate_count"], 10)
        self.assertEqual(match["candidates_omitted"], 2)
        self.assertEqual(result["coverage"]["reference_candidates_omitted"], 2)

    def test_uris_are_exact_strings_not_normalized_or_lexically_repaired(self):
        result = self.match(inventory([node(uri="repo:docs/SPEC")]))
        self.assertEqual(result["reference_counts"]["missing_in_declared_inventory"], 1)

    def test_malformed_snapshots_and_boundaries_raise_value_error(self):
        variants = [None, [], {**self.report, "schema": []}, {**self.report, "status": {}},
                    {**self.report, "results": [{}]}, {**self.report, "coverage": []}]
        for report in variants:
            with self.subTest(report=report), self.assertRaises(ValueError):
                review_recalled_documents(report, inventory([node()]))
        for key, value in (("quarantined", False), ("report_schema", []), ("source", {}),
                ("memory_key", "verification:bogus"), ("summary", {"payload": "never emit"})):
            report = copy.deepcopy(self.report)
            report["results"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.match(report=report)

    def test_duplicate_refs_unknown_inventory_schema_and_invalid_budgets_are_rejected(self):
        report = copy.deepcopy(self.report)
        report["results"][0]["documentary_refs"] *= 2
        with self.assertRaises(ValueError):
            self.match(report=report)
        for data in ({"schema": "future"}, {**inventory(), "completeness": []}, []):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.match(data)
        for cap in (8191, True, 262145, 8192.0):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.match(max_output_bytes=cap)


if __name__ == "__main__":
    unittest.main()
