"""Stdlib regression tests for deterministic spatial propositions."""

import unittest

from skills.approx_spatial.benchmark import run
from skills.approx_spatial.oracle import Interval, SpatialEvidence, Verdict, evaluate_less_than


def evidence(admissible, *, guards=(), excluded=()):
    return SpatialEvidence(
        None if admissible is None else tuple(Interval(*bounds) for bounds in admissible),
        tuple(Interval(*bounds) for bounds in excluded),
        tuple(guards),
    )


class ApproxSpatialTests(unittest.TestCase):
    def test_clear_yes_no_and_unknown_are_distinct(self):
        self.assertIs(evaluate_less_than(evidence([(1.7, 2.2)]), 3.0), Verdict.YES)
        self.assertIs(evaluate_less_than(evidence([(2.0, 2.4)]), 2.0), Verdict.NO)
        self.assertIs(evaluate_less_than(evidence([(1.7, 2.2)]), 2.0), Verdict.UNKNOWN)

    def test_unknown_is_not_coerced_to_no_when_hypotheses_span_threshold(self):
        value = evaluate_less_than(evidence([(1.0, 1.4), (3.2, 3.8)]), 2.0)
        self.assertIs(value, Verdict.UNKNOWN)

    def test_guard_failure_and_missing_measurement_abstain(self):
        self.assertIs(evaluate_less_than(
            evidence([(1.0, 1.2)], guards=("baseline_too_small",)), 2.0), Verdict.UNKNOWN)
        self.assertIs(evaluate_less_than(
            evidence(None, guards=("missing_measurement",)), 2.0), Verdict.UNKNOWN)

    def test_empty_admissible_set_is_conflict(self):
        self.assertIs(evaluate_less_than(evidence([]), 2.0), Verdict.CONFLICT)

    def test_no_midpoint_is_invented_and_exclusions_are_preserved(self):
        item = SpatialEvidence.from_mapping({
            "admissible_m": [[1.1, 1.9]],
            "excluded_m": [[0.2, 1.1], [1.9, 10.0]],
            "guard_failures": [],
        }).to_dict()
        self.assertNotIn("value_m", item)
        self.assertEqual(item["admissible_m"], [[1.1, 1.9]])
        self.assertEqual(item["excluded_m"], [[0.2, 1.1], [1.9, 10.0]])

    def test_invalid_interval_and_threshold_fail_closed(self):
        with self.assertRaises(ValueError):
            Interval(2.0, 1.0)
        invalid = ("2", True, False, None, [], {}, float("nan"),
                   float("inf"), -float("inf"), 10 ** 1000)
        for value in invalid:
            with self.subTest(value=value, field="low"), self.assertRaises(ValueError):
                Interval(value, 3.0)
            with self.subTest(value=value, field="high"), self.assertRaises(ValueError):
                Interval(1.0, value)
            with self.subTest(value=value, field="threshold"), self.assertRaises(ValueError):
                evaluate_less_than(evidence([(1.0, 2.0)]), value)

    def test_numeric_strings_cannot_produce_lexicographic_verdicts(self):
        # Formerly accepted as an inverted interval, and 10..20 < 3 returned YES.
        with self.assertRaises(ValueError):
            Interval("10", "2")
        with self.assertRaises(ValueError):
            evaluate_less_than(SpatialEvidence.from_mapping({
                "admissible_m": [["10", "20"]],
            }), "3")
        self.assertIs(evaluate_less_than(evidence([(10, 20)]), 3), Verdict.NO)

    def test_integer_bounds_keep_exact_order(self):
        value = 2 ** 53
        with self.assertRaises(ValueError):
            Interval(value + 1, value)
        self.assertIs(evaluate_less_than(evidence([(value, value)]), value + 1), Verdict.YES)

    def test_fixture_report_is_reproducible_and_all_cases_pass(self):
        first = run()
        second = run()
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["failed"], 0)
        self.assertGreaterEqual(first["summary"]["total"], 9)
        self.assertEqual(len(first["fixture_sha256"]), 64)
        self.assertEqual(len(first["results_sha256"]), 64)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ApproxSpatialTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
