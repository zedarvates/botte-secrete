from skills.approx_spatial.oracle import Verdict, evaluate_less_than
from skills.approx_spatial.parallax import ParallaxObservation, estimate_range


def test_exact_calibrated_parallax_recovers_range():
    result = estimate_range(ParallaxObservation(0.10, 800.0, 40.0))
    assert result.guard_failures == ()
    assert result.admissible is not None
    assert result.admissible[0].low == 2.0
    assert result.admissible[0].high == 2.0


def test_uncertainty_is_propagated_as_interval_not_midpoint():
    result = estimate_range(ParallaxObservation(
        0.10, 800.0, 40.0,
        disparity_uncertainty_px=2.0,
        baseline_uncertainty_m=0.002,
        focal_uncertainty_px=4.0,
    ))
    interval = result.admissible[0]
    assert interval.low < 2.0 < interval.high
    assert evaluate_less_than(result, 3.0) is Verdict.YES


def test_small_baseline_and_small_parallax_abstain():
    assert "baseline_too_small" in estimate_range(
        ParallaxObservation(0.005, 800.0, 40.0)
    ).guard_failures
    assert "parallax_too_small" in estimate_range(
        ParallaxObservation(0.10, 800.0, 0.2)
    ).guard_failures


def test_ambiguity_motion_occlusion_and_calibration_fail_closed():
    cases = [
        (ParallaxObservation(0.1, 800, 40, correspondence_ambiguous=True), "ambiguous_correspondence"),
        (ParallaxObservation(0.1, 800, 40, target_moving=True), "target_moving"),
        (ParallaxObservation(0.1, 800, 40, occluded=True), "occluded"),
        (ParallaxObservation(0.1, 800, 40, calibration_valid=False), "calibration_invalid"),
    ]
    for observation, reason in cases:
        result = estimate_range(observation)
        assert result.admissible is None
        assert reason in result.guard_failures


def test_large_uncertainty_that_crosses_zero_abstains():
    result = estimate_range(ParallaxObservation(
        0.1, 800, 1.0, disparity_uncertainty_px=1.0
    ))
    assert result.admissible is None
    assert "parallax_too_small" in result.guard_failures
