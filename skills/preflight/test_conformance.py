"""Conformance verifier regressions, including actual bounded Node processes.

Set BOTTE_CONFORMANCE_CLOUD_ROOT to include the real separate cloud checkout.
Absent source checkouts are not replaced by a fabricated successful comparison.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from skills.preflight import conformance as con
from skills.preflight.assessment import assess_task
from skills.preflight.github_evidence import summarize_github_evidence
from skills.preflight.github_plan import plan_github_research


class ConformanceTests(unittest.TestCase):
    def make_cloud(self, root, helper, output=None, body=None):
        root = Path(root)
        (root / "src").mkdir(exist_ok=True)
        (root / "package.json").write_text('{"type":"module","version":"fixture"}', encoding="utf-8")
        for name, (_, filename, export, _) in con._HELPERS.items():
            code = body if name == helper and body is not None else (
                "return " + json.dumps(output, ensure_ascii=True) + ";" if name == helper else "return {};")
            (root / "src" / filename).write_text(f"export function {export}(input){{{code}}}", encoding="utf-8")
        return root

    def case(self, helper="assess_task", arguments=None, **extra):
        return {"id": "fixture", "helper": helper, "arguments": arguments or {"task": "Lire le document"}, **extra}

    def run_fixture(self, helper, arguments, output=None, body=None, **kwargs):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_cloud(temporary, helper, output, body)
            return con.run_conformance(root, [self.case(helper, arguments)], **kwargs)

    def test_typed_differences_preserve_missing_null_and_boolean(self):
        difference = con._differences({"null": None, "boolean": False}, {"boolean": 0})
        self.assertEqual({x["kind"] for x in difference}, {"missing", "type"})
        self.assertEqual(len(con._differences({"x": [0]}, {"x": []})), 1)
        self.assertEqual(con._differences({"x": None}, {"x": None}), [])

    def test_difference_list_is_bounded(self):
        self.assertEqual(len(con._differences({str(i): i for i in range(100)}, {})), 32)

    def test_ranking_exclusion_does_not_accept_invalid_shortlist_schema(self):
        arguments = {"task": "Rechercher les PR GitHub", "available_tools": [
            {"name": "github_search_prs", "description": "Search GitHub pull requests"}]}
        reference = assess_task(**arguments)
        self.assertFalse(con._assessment_invariants(reference, arguments))
        for change in ("score", "duplicate", "estimate", "status"):
            result = copy.deepcopy(reference)
            if change == "score":
                result["candidate_tools"][0]["lexical_score"] = None
            elif change == "duplicate":
                result["candidate_tools"].append(copy.deepcopy(result["candidate_tools"][0]))
            elif change == "estimate":
                result["context"]["shortlist_estimated_tokens"] = 0
            else:
                result["tool_selection_status"] = "abstained"
            self.assertTrue(con._assessment_invariants(result, arguments), change)

    def test_cases_are_bounded_finite_json_with_unique_ids(self):
        case = self.case()
        for cases in ([], [case, case], [dict(case, surprise=True)],
                      [dict(case, helper="execute_code")],
                      [dict(case, arguments={"x": float("nan")})],
                      [dict(case, arguments={"task": "x" * 524288})]):
            with self.subTest(cases=str(cases)[:80]), self.assertRaises(ValueError):
                con.run_conformance(".", cases)
        for value in (True, 0, 65):
            with self.assertRaises(ValueError):
                con.run_conformance(".", [case], max_cases=value)

    def test_known_difference_policy_cannot_ignore_arbitrary_cases(self):
        for arguments in ({"pr_number": 1}, {"pr_number": 1.5}, {"pr_number": True}):
            with self.assertRaises(ValueError):
                con.run_conformance(".", [self.case("plan_github_research", arguments,
                    expected_difference="integral_number_representation")])

    def test_missing_sources_do_not_pass(self):
        with tempfile.TemporaryDirectory() as root:
            report = con.run_conformance(root)
        self.assertEqual(report["status"], "not_run")
        self.assertFalse(report["passed"])

    def test_missing_node_does_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_cloud(temporary, "assess_task", {})
            report = con.run_conformance(root, node_command="botte-missing-node-9a47")
        self.assertEqual(report["reason"], "node_unavailable")
        self.assertFalse(report["passed"])

    def test_runtime_argument_validation(self):
        for seconds in (True, 0, -1, 121, float("inf")):
            with self.assertRaises(ValueError):
                con.run_conformance(".", timeout_seconds=seconds)
        with self.assertRaises(ValueError):
            con.run_conformance(".", node_command="node\x00")

    @unittest.skipUnless(shutil.which("node"), "Node is required for actual cross-runtime tests")
    def test_actual_node_mirror_matches(self):
        arguments = {"task": "Lire le document"}
        report = self.run_fixture("assess_task", arguments, assess_task(**arguments))
        self.assertTrue(report["passed"])
        self.assertEqual(report["counts"]["matched"], 1)
        self.assertTrue(report["source_unchanged_after_comparison"])
        self.assertEqual(report["cloud_package_version"], "fixture")
        self.assertEqual(len(report["source_files"]), 3)

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_ranking_difference_is_declared_but_safety_still_checked(self):
        arguments = {"task": "Rechercher les PR GitHub", "available_tools": [
            {"name": "github_search_prs", "description": "Search GitHub pull requests"}]}
        result = assess_task(**arguments)
        result["candidate_tools"] = []
        result["tool_selection_status"] = "abstained"
        result["context"]["shortlist_estimated_tokens"] = 0
        result["missing_prerequisites"].append("matching_tool_metadata_within_budget")
        report = self.run_fixture("assess_task", arguments, result)
        self.assertTrue(report["passed"])
        result["candidate_tools"] = [{"name": "unoffered_tool", "capability_verified": False}]
        report = self.run_fixture("assess_task", arguments, result)
        self.assertFalse(report["passed"])
        self.assertTrue(report["results"][0]["invariant_failures"]["cloud"])

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_null_missing_or_boolean_number_are_never_equal(self):
        arguments = {"report_json": json.dumps({"repository": "owner/repo", "pull_request": {"number": 1}})}
        reference = summarize_github_evidence(**arguments)
        for kind in ("missing", "boolean"):
            result = copy.deepcopy(reference)
            if kind == "missing":
                del result["pull_request"]["merged"]
            else:
                result["source"]["verified"] = 0
            report = self.run_fixture("summarize_github_evidence", arguments, result)
            self.assertFalse(report["passed"])
            self.assertTrue(report["results"][0]["differences"])

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_serialized_output_size_can_differ_but_is_retained(self):
        arguments = {"report_json": json.dumps({"repository": "owner/repo", "pull_request": {"number": 1}})}
        reference = summarize_github_evidence(**arguments)
        reference["measurements"]["output_utf8_bytes"] += 1
        report = self.run_fixture("summarize_github_evidence", arguments, reference)
        self.assertTrue(report["passed"])
        self.assertNotEqual(report["results"][0]["python"]["result"]["measurements"]["output_utf8_bytes"],
                            report["results"][0]["cloud"]["result"]["measurements"]["output_utf8_bytes"])

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_undefined_cloud_result_or_import_failure_is_incomplete(self):
        for body in ("return undefined;", "throw new Error('runtime failure');"):
            report = self.run_fixture("assess_task", {"task": "Read"}, body=body)
            self.assertFalse(report["passed"])
            self.assertIn(report["status"], {"failed", "incomplete"})
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_cloud(temporary, "assess_task", {})
            (root / "src" / "assessment.js").write_text("throw new Error('import failed');", encoding="utf-8")
            report = con.run_conformance(root, [self.case()])
        self.assertEqual(report["status"], "incomplete")

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_timeout_and_output_overflow_cannot_pass(self):
        for body, reason, timeout in (("while(true){}", "timeout", 0.2),
                                      ("console.log('x'.repeat(3000000)); return {};", "output_limit", 3)):
            report = self.run_fixture("assess_task", {"task": "Read"}, body=body, timeout_seconds=timeout)
            self.assertFalse(report["passed"])
            self.assertEqual(report["reason"], reason)

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_expected_integral_float_requires_correct_normalized_result(self):
        arguments = {"repository": "owner/repo", "pr_number": 1.0}
        case = self.case("plan_github_research", arguments,
                         expected_difference="integral_number_representation")
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_cloud(temporary, "plan_github_research", plan_github_research("owner/repo", pr_number=1))
            report = con.run_conformance(root, [case])
            self.assertTrue(report["passed"])
            self.assertEqual(report["counts"]["known_difference"], 1)
            self.make_cloud(temporary, "plan_github_research", {"unrelated": "result"})
            report = con.run_conformance(root, [case])
            self.assertFalse(report["passed"])

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_python_unexpected_error_is_not_a_matching_rejection(self):
        def broken(**kwargs):
            raise RuntimeError("internal failure")
        with patch.dict(con._HELPERS, {"assess_task": (broken, "assessment.js", "assessTask", "assessment.py")}):
            report = self.run_fixture("assess_task", {"task": "Read"}, body="throw new Error('rejected');")
        self.assertFalse(report["passed"])
        self.assertEqual(report["status"], "incomplete")

    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_cloud_source_change_invalidates_comparison(self):
        arguments = {"task": "Read"}
        result = assess_task(**arguments)
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_cloud(temporary, "assess_task", result)
            original = con._node_cases

            def mutate_after(*args, **kwargs):
                response = original(*args, **kwargs)
                (root / "src" / "assessment.js").write_text("// changed", encoding="utf-8")
                return response
            with patch.object(con, "_node_cases", side_effect=mutate_after):
                report = con.run_conformance(root, [self.case(arguments=arguments)])
        self.assertEqual(report["reason"], "source_changed_during_comparison")
        self.assertFalse(report["passed"])

    def test_python_source_changed_since_import_is_not_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_cloud(temporary, "assess_task", {})
            with patch.dict(con._PYTHON_IMPORT_HASHES, {"assessment.py": "changed"}):
                report = con.run_conformance(root, [self.case()])
        self.assertEqual(report["reason"], "python_source_changed_since_import")

    @unittest.skipUnless(os.environ.get("BOTTE_CONFORMANCE_CLOUD_ROOT"), "Separate real cloud checkout not supplied")
    def test_real_cloud_sources(self):
        report = con.run_conformance(os.environ["BOTTE_CONFORMANCE_CLOUD_ROOT"])
        self.assertTrue(report["passed"], [(x["id"], x["status"]) for x in report["results"]])
        self.assertEqual(report["counts"]["known_difference"], 1)
        self.assertTrue(report["source_unchanged_after_comparison"])


if __name__ == "__main__":
    unittest.main()
