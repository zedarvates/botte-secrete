"""Regression checks for failed-run savings and incomplete cost reports."""

import unittest

from skills.loop_optimizer.baseline import compare


class TestCostReporting(unittest.TestCase):
    def test_failed_or_unverified_runs_never_receive_savings(self):
        for left, right in ((False, False), (True, False), (False, True),
                            ("true", True), (True, 1), (None, None)):
            result = compare({"tokens_total": 1000, "iterations": 4, "success": left},
                             {"tokens_total": 100, "iterations": 1, "success": right})
            self.assertFalse(result["comparable"])
            self.assertEqual(result["tokens_saved"], 0)
            self.assertEqual(result["iterations_saved"], 0)
            self.assertEqual(result["savings_pct"], 0.0)

    def test_missing_or_invalid_counts_are_not_free_work(self):
        baseline = {"tokens_total": 1000, "iterations": 4, "success": True}
        for name in ("tokens_total", "iterations"):
            for value in (None, True, -1, 1.5, "1"):
                candidate = {"tokens_total": 100, "iterations": 1, "success": True}
                candidate[name] = value
                for left, right in ((baseline, candidate), (candidate, baseline)):
                    result = compare(left, right)
                    self.assertFalse(result["comparable"])
                    self.assertEqual(result["tokens_saved"], 0)
                    self.assertEqual(result["iterations_saved"], 0)
            missing = dict(baseline)
            del missing[name]
            self.assertFalse(compare(baseline, missing)["comparable"])

    def test_successful_runs_keep_both_savings_and_regressions_visible(self):
        baseline = {"tokens_total": 1000, "iterations": 4, "success": True}
        candidate = {"tokens_total": 700, "iterations": 2, "success": True}
        gain = compare(baseline, candidate)
        self.assertTrue(gain["comparable"])
        self.assertEqual(gain["tokens_saved"], 300)
        self.assertEqual(gain["iterations_saved"], 2)
        self.assertEqual(gain["savings_pct"], 30.0)
        regression = compare(candidate, baseline)
        self.assertEqual(regression["tokens_saved"], -300)
        self.assertEqual(regression["iterations_saved"], -2)

    def test_zero_reported_cost_is_distinct_from_missing_cost(self):
        baseline = {"tokens_total": 100, "iterations": 2, "success": True}
        candidate = {"tokens_total": 0, "iterations": 0, "success": True}
        self.assertEqual(compare(baseline, candidate)["tokens_saved"], 100)
        self.assertFalse(compare(baseline, {"success": True})["comparable"])


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(TestCostReporting))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
