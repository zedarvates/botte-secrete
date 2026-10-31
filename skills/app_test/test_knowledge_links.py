"""Declared documentary identities, omissions and advisory similarity boundaries."""
import copy
import json
import unittest

from skills.app_test.knowledge_links import review_knowledge_links


def node(identity, kind="document", version="v1", title=""):
    return {"id": identity, "kind": kind, "source_uri": "urn:example:" + identity,
            "source_version": version, "title": title}


def inventory(nodes=None, links=None, completeness="complete"):
    return {"schema": "parcimonia.knowledge-inventory/v1", "completeness": completeness,
            "nodes": nodes or [], "links": links or []}


class KnowledgeLinkTests(unittest.TestCase):
    def test_exact_receipt_document_link_retains_declared_versions(self):
        value = inventory([node("receipt-42", "receipt"), node("recipe-login", "recipe", "v7")],
            [{"source":"receipt-42", "target":"recipe-login", "kind":"documents",
              "source_version":"v1", "target_version":"v7"}])
        original = copy.deepcopy(value)
        report = review_knowledge_links(value)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["counts"]["resolved"], 1)
        self.assertEqual(report["links"][0]["target_ref"]["source_version"], "v7")
        self.assertEqual(report["links"][0]["unconstrained_endpoints"], [])
        self.assertEqual(value, original)
        self.assertFalse(report["source"]["verified"])

    def test_complete_inventory_missing_reference_is_scoped_finding(self):
        report = review_knowledge_links(inventory([node("receipt", "receipt")],
            [{"source":"receipt", "target":"absent", "kind":"documents"}]))
        self.assertEqual(report["status"], "findings")
        self.assertEqual(report["links"][0]["status"], "missing_in_declared_inventory")
        self.assertEqual(report["links"][0]["missing_endpoints"], ["target"])
        self.assertEqual(report["coverage"]["global_knowledge_coverage"], "unknown")

    def test_partial_and_unknown_inventory_do_not_prove_document_absence(self):
        for completeness in ("partial", "unknown"):
            with self.subTest(completeness=completeness):
                report = review_knowledge_links(inventory([node("receipt")],
                    [{"source":"receipt", "target":"absent", "kind":"documents"}], completeness))
                self.assertEqual(report["status"], "incomplete")
                self.assertEqual(report["counts"]["missing_in_declared_inventory"], 0)
                self.assertEqual(report["counts"]["unknown_reference"], 1)

    def test_partial_inventory_can_complete_only_its_explicit_reference_review(self):
        report = review_knowledge_links(inventory([node("a"), node("b")],
            [{"source":"a", "target":"b", "kind":"documents"}], "partial"))
        self.assertEqual(report["status"], "completed")
        self.assertTrue(report["coverage"]["reference_review_complete"])
        self.assertFalse(report["coverage"]["inventory_declared_complete"])
        self.assertEqual(report["coverage"]["global_knowledge_coverage"], "unknown")

    def test_stale_constraint_does_not_resolve_current_version(self):
        report = review_knowledge_links(inventory([node("task", "task"), node("recipe", "recipe", "new")],
            [{"source":"task", "target":"recipe", "kind":"depends_on", "target_version":"old"}]))
        self.assertEqual(report["status"], "findings")
        self.assertEqual(report["counts"]["version_mismatch"], 1)
        self.assertEqual(report["links"][0]["version_mismatches"],
                         [{"endpoint":"target", "expected":"old", "observed":"new"}])
        self.assertEqual(report["dependencies"]["excluded_unresolved_or_stale_links"], 1)

    def test_constraint_mismatch_is_retained_even_with_other_endpoint_missing(self):
        report = review_knowledge_links(inventory([node("a", version="new")],
            [{"source":"a", "target":"missing", "kind":"depends_on", "source_version":"old"}]))
        self.assertEqual(report["counts"]["version_constraint_mismatches"], 1)
        self.assertEqual(report["counts"]["unresolved_endpoints"], 1)
        self.assertEqual(report["links"][0]["version_mismatches"][0]["endpoint"], "source")

    def test_cycles_only_apply_to_declared_dependencies(self):
        nodes = [node("a", "task"), node("b", "recipe")]
        links = [{"source":"a", "target":"b", "kind":"related_to"},
                 {"source":"b", "target":"a", "kind":"related_to"}]
        related = review_knowledge_links(inventory(nodes, links))
        self.assertEqual(related["status"], "completed")
        for link in links:
            link["kind"] = "depends_on"
        dependency = review_knowledge_links(inventory(nodes, links))
        self.assertEqual(dependency["status"], "findings")
        self.assertEqual(dependency["dependencies"]["cycle_witnesses"], [["a", "b", "a"]])
        self.assertFalse(dependency["dependencies"]["all_cycles_enumerated"])

    def test_long_dependency_chain_is_unknown_when_depth_budget_is_reached(self):
        nodes = [node(str(i), "task") for i in range(10)]
        links = [{"source":str(i), "target":str(i+1), "kind":"depends_on"} for i in range(9)]
        report = review_knowledge_links(inventory(nodes, links), max_depth=3)
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["dependencies"]["analysis_complete"])
        self.assertEqual(report["dependencies"]["cycle_status"], "unknown_depth_limit")

    def test_self_dependency_is_a_real_cycle_witness(self):
        report = review_knowledge_links(inventory([node("a")],
            [{"source":"a", "target":"a", "kind":"depends_on"}]))
        self.assertEqual(report["dependencies"]["cycle_witnesses"], [["a", "a"]])

    def test_lexical_candidate_never_becomes_resolved_evidence(self):
        report = review_knowledge_links(inventory([node("receipt"),
            node("recipe-login", "recipe", title="Login reconnect")],
            [{"source":"receipt", "target":"recipe-login-missing", "kind":"documents"}], "partial"))
        suggestions = report["lexical_suggestions"]
        self.assertEqual(suggestions["candidates"][0]["candidate_id"], "recipe-login")
        self.assertFalse(suggestions["candidates"][0]["verified"])
        self.assertFalse(suggestions["added_to_declared_links"])
        self.assertEqual(report["counts"]["resolved"], 0)

    def test_node_duplicates_conflicts_unknown_fields_and_bad_uris_rejected(self):
        for value in (inventory([node("a"), node("a")]),
                      inventory([node("a"), node("a", version="v2")]),
                      inventory([{**node("a"), "promote":True}]),
                      inventory([{**node("a"), "source_uri":"javascript:alert(1)"}]),
                      inventory([{**node("a"), "source_uri":"https://user:secret@example.test/doc"}])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                review_knowledge_links(value)

    def test_malformed_enum_types_are_deliberate_validation_errors(self):
        for value in ({**inventory(), "completeness":[]},
                      inventory([{**node("a"), "kind":[]}]),
                      inventory([], [{"source":"a", "target":"b", "kind":{}}])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                review_knowledge_links(value)
        for uri in ("urn:", "repo:", "wiki:", "file:"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                review_knowledge_links(inventory([{**node("a"), "source_uri":uri}]))

    def test_lexical_candidate_caps_have_explicit_omission_counts(self):
        report = review_knowledge_links(inventory([node("r", "receipt"), node("alpha-a"),
            node("alpha-b"), node("alpha-c")],
            [{"source":"r", "target":"alpha-missing", "kind":"documents"}], "partial"),
            max_suggestions=1)
        suggestions = report["lexical_suggestions"]
        self.assertEqual(len(suggestions["candidates"]), 1)
        self.assertEqual(suggestions["candidates_with_shared_tokens_observed"], 3)
        self.assertEqual(suggestions["candidates_excluded_by_per_query_policy"], 1)
        self.assertEqual(suggestions["candidates_omitted_by_limit"], 1)

    def test_input_and_utf8_limits_are_explicit(self):
        with self.assertRaises(ValueError):
            review_knowledge_links(inventory([node("a"), node("b")]), max_nodes=1)
        with self.assertRaises(ValueError):
            review_knowledge_links(inventory([node("a" * 129)]))
        with self.assertRaises(ValueError):
            review_knowledge_links(inventory([node("雪" * 44)]))
        for bad in (True, -1, 10**1000):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                review_knowledge_links(inventory(), max_nodes=bad)

    def test_output_omissions_preserve_counts_and_hashes(self):
        nodes = [node("receipt", "receipt"), node("doc", version="v2")]
        links = [{"source":"receipt", "target":"doc", "kind":"documents", "target_version":"old"}
                 for _ in range(100)]
        report = review_knowledge_links(inventory(nodes, links), max_output_bytes=2048)
        raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(raw), 2048)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["counts"]["version_mismatch"], 100)
        self.assertEqual(report["counts"]["duplicate_link_declarations"], 99)
        self.assertEqual(report["links_omitted"] + len(report["links"]), 100)
        self.assertEqual(len(report["source"]["inventory_sha256"]), 64)

    def test_hash_basis_identifies_normalized_snapshot(self):
        one = inventory([{key:value for key,value in node("a").items() if key != "title"}])
        two = inventory([node("a")])
        first, second = review_knowledge_links(one), review_knowledge_links(two)
        self.assertEqual(first["source"]["inventory_sha256"], second["source"]["inventory_sha256"])
        self.assertEqual(first["source"]["digest_basis"], "canonical_normalized_inventory_json_utf8")

    def test_maximum_supported_graph_has_bounded_summary(self):
        nodes = [node(f"n{i}", "task") for i in range(512)]
        links = [{"source":f"n{i % 512}", "target":f"n{(i + 1) % 512}", "kind":"depends_on"}
                 for i in range(2048)]
        report = review_knowledge_links(inventory(nodes, links), max_nodes=512,
                                        max_links=2048, max_depth=512, max_output_bytes=2048)
        self.assertEqual(report["status"], "incomplete")
        self.assertGreater(report["dependencies"]["back_edges_observed"], 0)
        self.assertEqual(report["counts"]["links"], 2048)
        self.assertLessEqual(len(json.dumps(report, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")), 2048)

    def test_exact_output_boundary_allows_another_omission(self):
        nodes = [node("a"), node("b")] + [node(str(i) + "x" * 80) for i in range(30)]
        links = [{"source":"a", "target":"b", "kind":"documents"}]
        for maximum in (2100, 2185, 2270, 2355):
            with self.subTest(maximum=maximum):
                report = review_knowledge_links(inventory(nodes, links), max_output_bytes=maximum)
                self.assertEqual(report["status"], "incomplete")
                self.assertLessEqual(len(json.dumps(report, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")), maximum)

    def test_same_input_has_deterministic_review_and_no_runtime_effects(self):
        value = inventory([node("a", title="café 雪")])
        first = review_knowledge_links(value)
        self.assertEqual(first, review_knowledge_links(value))
        self.assertEqual(first["unlinked_node_ids"], ["a"])
        self.assertEqual(first["boundaries"]["storage_writes"], 0)
        self.assertEqual(first["boundaries"]["network_calls"], 0)


if __name__ == "__main__":
    unittest.main()
