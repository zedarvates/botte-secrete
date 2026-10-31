"""Behavioral tests for deterministic descriptive statistics."""

from __future__ import annotations

import copy
import json
import math
import unittest

from skills.solvers.statistics import MAX_VALUES, compute_statistics


class StatisticsTests(unittest.TestCase):
    def test_default_known_values(self):
        result = compute_statistics([10, 20, 30])
        self.assertEqual(result["results"], {
            "count": 3, "sum": 60, "min": 10, "max": 30,
            "mean": 20, "median": 20,
        })
        self.assertEqual(result["schema"], "botte.statistics/v1")
        self.assertEqual(result["execution"], {"model_calls": 0, "network_calls": 0})

    def test_even_median_and_negative_values(self):
        result = compute_statistics([-5, 4, -1, 2])["results"]
        self.assertEqual(result["median"], 0.5)
        self.assertEqual(result["mean"], 0)
        self.assertEqual(result["min"], -5)

    def test_population_and_sample_variance_are_explicit(self):
        result = compute_statistics([2, 4, 4, 4, 5, 5, 7, 9], [
            "variance_population", "variance_sample", "stdev_population", "stdev_sample",
        ])
        self.assertEqual(result["results"]["variance_population"], 4)
        self.assertAlmostEqual(result["results"]["variance_sample"], 32 / 7)
        self.assertEqual(result["results"]["stdev_population"], 2)
        self.assertAlmostEqual(result["results"]["stdev_sample"], math.sqrt(32 / 7))
        self.assertEqual(result["methods"]["variance_sample"], "ddof=1")

    def test_percentile_type7_boundaries_and_interpolation(self):
        result = compute_statistics([40, 10, 30, 20], ["count"], [0, 25, 50, 95, 100])
        self.assertEqual([entry["value"] for entry in result["percentiles"]],
                         [10, 17.5, 25, 38.5, 40])
        self.assertEqual(result["methods"]["percentiles"], "linear_type7")

    def test_singleton_population_and_percentiles(self):
        result = compute_statistics([7], ["variance_population", "stdev_population"], [0, 50, 100])
        self.assertEqual(list(result["results"].values()), [0, 0])
        self.assertEqual([entry["value"] for entry in result["percentiles"]], [7, 7, 7])

    def test_singleton_sample_rejected(self):
        for operation in ("variance_sample", "stdev_sample"):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                compute_statistics([7], [operation])

    def test_missing_rejected_by_default(self):
        with self.assertRaises(ValueError):
            compute_statistics([1, None, 3])

    def test_explicit_missing_omission_is_reported(self):
        result = compute_statistics([1, None, 3, None], missing="omit")
        self.assertEqual(result["input"], {
            "count": 4, "used": 2, "omitted": 2, "missing_policy": "omit",
        })
        self.assertEqual(result["results"]["mean"], 2)

    def test_omission_never_hides_other_invalid_values(self):
        for value in (True, False, "", "2", {}, [], float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compute_statistics([None, value], missing="omit")

    def test_empty_and_all_missing_rejected(self):
        for values in ([], [None], [None, None]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                compute_statistics(values, missing="omit")

    def test_collection_types_rejected(self):
        for values in (None, (1, 2), "1,2", {"value": 1}, 1):
            with self.subTest(values=values), self.assertRaises(ValueError):
                compute_statistics(values)

    def test_input_bound(self):
        self.assertEqual(compute_statistics([0] * MAX_VALUES, ["count"])["results"]["count"], MAX_VALUES)
        with self.assertRaises(ValueError):
            compute_statistics([0] * (MAX_VALUES + 1), ["count"])

    def test_operation_validation(self):
        for operations in ([], "mean", ["unknown"], ["mean", "mean"], [True], [None], list(range(17))):
            with self.subTest(operations=operations), self.assertRaises(ValueError):
                compute_statistics([1, 2], operations)

    def test_percentile_validation(self):
        for points in ("50", [True], [None], ["50"], [-1], [101], [float("nan")],
                       [float("inf")], [50, 50.0], [0] * 17):
            with self.subTest(points=points), self.assertRaises(ValueError):
                compute_statistics([1, 2], percentiles=points)

    def test_unknown_missing_policy(self):
        for policy in (None, "ignore", True, [], {}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                compute_statistics([1, 2], missing=policy)

    def test_large_integer_precision_is_not_silently_lost(self):
        self.assertEqual(compute_statistics([2**53], ["max"])["results"]["max"], 2**53)
        for value in (2**53 + 1, -(2**53 + 1), 10**500):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compute_statistics([value], ["count"])

    def test_finite_binary64_extremes(self):
        result = compute_statistics([1e308, 1e308], ["mean", "median"], [50])
        self.assertEqual(result["results"], {"mean": 1e308, "median": 1e308})
        self.assertEqual(result["percentiles"][0]["value"], 1e308)

    def test_balanced_extreme_sum_is_order_independent(self):
        for values in ([1e308, 1e308, -1e308], [-1e308, 1e308, 1e308]):
            self.assertEqual(compute_statistics(values, ["sum"])["results"]["sum"], 1e308)

    def test_subnormal_median_is_not_lost_to_intermediate_underflow(self):
        tiny = float.fromhex("0x0.0000000000001p-1022")
        result = compute_statistics([tiny, tiny], ["median"], [50])
        self.assertEqual(result["results"]["median"], tiny)
        self.assertEqual(result["percentiles"][0]["value"], tiny)

    def test_unrepresentable_requested_results_rejected(self):
        for values, operations in [([1e308, 1e308], ["sum"]),
                                   ([-1e308, 1e308], ["variance_population"]),
                                   ([-1e308, 1e308], ["variance_sample"])]:
            with self.subTest(operations=operations), self.assertRaises(ValueError):
                compute_statistics(values, operations)

    def test_representable_stdev_does_not_require_representable_variance(self):
        result = compute_statistics([-1e308, 1e308], ["stdev_population"])
        self.assertEqual(result["results"]["stdev_population"], 1e308)

    def test_subnormal_stdev_does_not_require_representable_variance(self):
        tiny = float.fromhex("0x0.0000000000001p-1022")
        result = compute_statistics([0, tiny * 2], ["stdev_population"])
        self.assertEqual(result["results"]["stdev_population"], tiny)

    def test_constant_stdev_is_zero(self):
        result = compute_statistics([1e308, 1e308], ["stdev_population", "stdev_sample"])
        self.assertEqual(list(result["results"].values()), [0, 0])

    def test_strict_json_and_repeatability(self):
        values = [1, 2.5, -3, None]
        first = compute_statistics(values, missing="omit", percentiles=[10, 95])
        second = compute_statistics(values, missing="omit", percentiles=[10, 95])
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first, allow_nan=False)), first)

    def test_inputs_not_mutated(self):
        values, operations, points = [3, None, 1, 2], ["mean", "median"], [95, 0]
        before = copy.deepcopy((values, operations, points))
        compute_statistics(values, operations, points, "omit")
        self.assertEqual((values, operations, points), before)

    def test_shift_and_scale_relationships(self):
        values = [1, 4, 8, 11]
        ops = ["mean", "median", "variance_population", "stdev_population"]
        base = compute_statistics(values, ops)["results"]
        transformed = compute_statistics([3 * value + 7 for value in values], ops)["results"]
        self.assertEqual(transformed["mean"], 3 * base["mean"] + 7)
        self.assertEqual(transformed["median"], 3 * base["median"] + 7)
        self.assertEqual(transformed["variance_population"], 9 * base["variance_population"])
        self.assertAlmostEqual(transformed["stdev_population"], 3 * base["stdev_population"])


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StatisticsTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
