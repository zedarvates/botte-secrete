"""Behavioral contracts for consultative GitHub research planning."""

from __future__ import annotations

import json
import unittest
from urllib.parse import parse_qs, urlsplit

from skills.preflight.github_plan import plan_github_research


class GitHubPlanTests(unittest.TestCase):
    def test_search_is_scoped_and_query_cannot_inject_qualifiers(self):
        result = plan_github_research("zedarvates/botte-secrete", 'repo:other/secret OR is:issue "merge"')
        query = parse_qs(urlsplit(result["search"]["url"]).query)["q"][0]
        self.assertTrue(query.startswith("repo:zedarvates/botte-secrete is:pr "))
        self.assertNotIn("repo:other", query)
        self.assertNotIn("is:issue", query)
        self.assertIn('"OR"', query)
        self.assertEqual(result["evidence"]["completeness"], "not_observed")
        self.assertNotIn("url", result["steps"][0])
        self.assertEqual(result["steps"][0]["url_ref"], "search.url")

    def test_pr_reads_filenames_before_patches_and_checks_exact_head(self):
        result = plan_github_research("zedarvates/botte-secrete", "security tests", pr_number=145)
        steps = {step["id"]: step for step in result["steps"]}
        self.assertEqual(steps["patches"]["requires"], ["files"])
        self.assertEqual(steps["patches"]["focus_terms"], ["security", "tests"])
        self.assertEqual(steps["checks"]["bind"], {"head_sha": "metadata.head.sha"})
        self.assertIn("{head_sha}", steps["checks"]["url_template"])
        self.assertIn("merged_at", steps["metadata"]["select"])
        self.assertIn("statuses", steps["refresh"]["requires"])
        self.assertEqual(result["source_url"], "https://github.com/zedarvates/botte-secrete/pull/145")

    def test_base_retarget_invalidates_diff_without_invalidating_same_head_checks(self):
        result = plan_github_research("owner/repo", pr_number=1)
        steps = {step["id"]: step for step in result["steps"]}
        self.assertIn("base.ref", steps["metadata"]["select"])
        self.assertIn("base.repo.full_name", steps["metadata"]["select"])
        self.assertEqual(steps["refresh"]["compare"], ["head.sha", "base.sha", "base.ref", "base.repo.full_name"])
        self.assertEqual(steps["refresh"]["invalidate"]["base_changed"], ["files", "patches"])
        self.assertIn("checks", steps["refresh"]["invalidate"]["head_changed"])

    def test_partial_and_missing_results_stay_unknown(self):
        result = plan_github_research("owner/repo", "security")
        self.assertIn("incomplete_results", result["steps"][0]["select"])
        self.assertIn("partial", result["steps"][0]["pagination"])
        self.assertEqual(result["evidence"]["merge_state"], "not_observed")
        rules = " ".join(result["evidence"]["rules"])
        self.assertIn("do not prove absence", rules)
        self.assertIn("closed PR is not evidence", rules)

    def test_plan_is_bounded_and_deterministic(self):
        query = " ".join(f"term{i}" for i in range(100))
        result = plan_github_research("owner/repo", query)
        self.assertLessEqual(len(result["search"]["terms"]), 12)
        self.assertTrue(result["search"]["terms_limited"])
        self.assertEqual(result, plan_github_research("owner/repo", query))
        self.assertLess(len(json.dumps(result)), 6000)

    def test_worst_case_unicode_plan_is_bounded_in_utf8(self):
        repository = "a" * 39 + "/" + "r" * 100
        query = " ".join(chr(0x1D400 + i) * 48 for i in range(12))
        for pr_number in (None, 2_147_483_647):
            with self.subTest(pr_number=pr_number):
                result = plan_github_research(repository, query, pr_number)
                self.assertLess(len(json.dumps(result, ensure_ascii=False).encode("utf-8")), 6000)
                self.assertLess(len(json.dumps(result).encode("utf-8")), 6000)
        search = plan_github_research(repository, query)["search"]
        self.assertLessEqual(sum(len(term.encode("utf-8")) for term in search["terms"]), 384)
        self.assertTrue(search["terms_limited"])

    def test_plan_never_claims_execution_or_savings(self):
        result = plan_github_research("owner/repo", pr_number=1)
        self.assertEqual(result["authority"], "consultative")
        self.assertEqual(result["execution"], {"performed": False, "network_calls": 0, "model_calls": 0})
        self.assertIsNone(result["measurements"]["host_tokens"])
        self.assertIsNone(result["measurements"]["latency_ms"])

    def test_invalid_inputs_are_rejected(self):
        for value in (None, "owner/repo/extra", "https://github.com/owner/repo", "a/..", "owner/repo?x=1", "owner/repo\n"):
            with self.subTest(repository=value), self.assertRaises(ValueError):
                plan_github_research(value)
        for value in (False, True, 0, -1, 1.5, "12", 2_147_483_648):
            with self.subTest(pr_number=value), self.assertRaises(ValueError):
                plan_github_research("owner/repo", pr_number=value)
        for value in (None, [], "x" * 1001):
            with self.subTest(query=value), self.assertRaises(ValueError):
                plan_github_research("owner/repo", value)


if __name__ == "__main__":
    unittest.main()
