"""Stdlib regression tests for calibrated parallax and its validity guards."""

import unittest

from skills.approx_spatial.oracle import Verdict, evaluate_less_than
from skills.approx_spatial.parallax import ParallaxObservation, estimate_range


class ParallaxTests(unittest.TestCase):
    def test_exact_calibrated_parallax_recovers_range(self):
        result = estimate_range(ParallaxObservation(0.10, 800.0, 40.0))
        self.assertEqual(result.guard_failures, ())
        self.assertIsNotNone(result.admissible)
        self.assertEqual(result.admissible[0].low, 2.0)
        self.assertEqual(result.admissible[0].high, 2.0)

    def test_uncertainty_is_propagated_as_interval_not_midpoint(self):
        result = estimate_range(ParallaxObservation(
            0.10, 800.0, 40.0,
            disparity_uncertainty_px=2.0,
            baseline_uncertainty_m=0.002,
            focal_uncertainty_px=4.0,
        ))
        interval = result.admissible[0]
        self.assertLess(interval.low, 2.0)
        self.assertGreater(interval.high, 2.0)
        self.assertIs(evaluate_less_than(result, 3.0), Verdict.YES)

    def test_small_baseline_and_small_parallax_abstain(self):
        self.assertIn("baseline_too_small", estimate_range(
            ParallaxObservation(0.005, 800.0, 40.0)).guard_failures)
        self.assertIn("parallax_too_small", estimate_range(
            ParallaxObservation(0.10, 800.0, 0.2)).guard_failures)

    def test_ambiguity_motion_occlusion_and_calibration_fail_closed(self):
        cases = [
            (ParallaxObservation(0.1, 800, 40, correspondence_ambiguous=True), "ambiguous_correspondence"),
            (ParallaxObservation(0.1, 800, 40, target_moving=True), "target_moving"),
            (ParallaxObservation(0.1, 800, 40, occluded=True), "occluded"),
            (ParallaxObservation(0.1, 800, 40, calibration_valid=False), "calibration_invalid"),
        ]
        for observation, reason in cases:
            with self.subTest(reason=reason):
                result = estimate_range(observation)
                self.assertIsNone(result.admissible)
                self.assertIn(reason, result.guard_failures)

    def test_large_uncertainty_that_crosses_zero_abstains(self):
        result = estimate_range(ParallaxObservation(
            0.1, 800, 1.0, disparity_uncertainty_px=1.0))
        self.assertIsNone(result.admissible)
        self.assertIn("parallax_too_small", result.guard_failures)

    def test_invalid_measurements_are_rejected(self):
        fields = ("baseline_m", "focal_px", "disparity_px",
                  "disparity_uncertainty_px", "baseline_uncertainty_m", "focal_uncertainty_px")
        invalid = ("0.1", True, False, None, [], {}, float("nan"),
                   float("inf"), -float("inf"), -0.1, 10 ** 1000)
        for field in fields:
            for value in invalid:
                params = {"baseline_m": 0.1, "focal_px": 800, "disparity_px": 40, field: value}
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    estimate_range(ParallaxObservation(**params))

    def test_invalid_guard_thresholds_cannot_disable_abstention(self):
        invalid = (float("nan"), float("inf"), -float("inf"), -0.1,
                   "0.01", True, False, None, [], {}, 10 ** 1000)
        for field in ("min_baseline_m", "min_disparity_px"):
            for value in invalid:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    estimate_range(ParallaxObservation(0.005, 800, 0.2), **{field: value})

    def test_zero_guard_thresholds_still_require_positive_geometry(self):
        result = estimate_range(ParallaxObservation(0, 800, 0),
                                min_baseline_m=0, min_disparity_px=0)
        self.assertIsNone(result.admissible)
        self.assertIn("baseline_too_small", result.guard_failures)
        self.assertIn("parallax_too_small", result.guard_failures)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ParallaxTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = len(result.failures) + len(result.errors)
    print(f"{result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
