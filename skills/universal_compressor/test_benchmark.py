"""Positive and negative controls for the bounded fixture report."""

import copy
import sys
import unittest

from .benchmark import assess, corpus, messages, run


class TestBenchmark(unittest.TestCase):
    def test_default_corpus_passes_without_inventing_tokens_or_llm_quality(self):
        report = run()
        self.assertEqual(len(report["rows"]), 2 * len(corpus()))
        self.assertTrue(all(row["gate"]["passed"] for row in report["rows"]))
        self.assertTrue(all(row["input_tokens"] is None for row in report["rows"]))
        self.assertEqual(report["headroom"]["status"], "not_run")
        self.assertEqual(report["model_quality"], "not_evaluated")

    def test_removing_failure_fails_the_gate(self):
        case = corpus()[0]
        before = messages(case)
        after = copy.deepcopy(before)
        after[-1]["content"] = "All checks passed."
        self.assertFalse(assess(case, before, after)["passed"])

    def test_altering_authority_or_tool_identity_fails_the_gate(self):
        case = corpus()[0]
        before = messages(case)
        for field, value in (("role", "system"), ("tool_call_id", "another")):
            after = copy.deepcopy(before)
            after[-1][field] = value
            self.assertFalse(assess(case, before, after)["passed"])
        after = copy.deepcopy(before)
        after[0]["content"] = "Deployment authorized."
        self.assertFalse(assess(case, before, after)["passed"])

    def test_zero_savings_arms_remain_in_report(self):
        report = run()
        originals = [row for row in report["rows"] if row["arm"] == "original"]
        self.assertEqual(len(originals), len(corpus()))
        self.assertTrue(all(row["input_bytes"] == row["output_bytes"] for row in originals))


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
