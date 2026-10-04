"""Minimal calibrated parallax baseline for ApproxRange R&D."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .oracle import Interval, SpatialEvidence


@dataclass(frozen=True)
class ParallaxObservation:
    baseline_m: float
    focal_px: float
    disparity_px: float
    disparity_uncertainty_px: float = 0.0
    baseline_uncertainty_m: float = 0.0
    focal_uncertainty_px: float = 0.0
    correspondence_ambiguous: bool = False
    target_moving: bool = False
    occluded: bool = False
    calibration_valid: bool = True


def _finite_nonnegative(value: float, name: str) -> float:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return float(value)


def estimate_range(
    observation: ParallaxObservation,
    *,
    min_baseline_m: float = 0.01,
    min_disparity_px: float = 0.5,
) -> SpatialEvidence:
    """Return a conservative range interval from z = f*b/d.

    The implementation is intentionally calibrated/simple. It does not perform
    feature matching and never guesses when a validity guard fails.
    """
    b = _finite_nonnegative(observation.baseline_m, "baseline_m")
    f = _finite_nonnegative(observation.focal_px, "focal_px")
    d = _finite_nonnegative(observation.disparity_px, "disparity_px")
    du = _finite_nonnegative(observation.disparity_uncertainty_px, "disparity_uncertainty_px")
    bu = _finite_nonnegative(observation.baseline_uncertainty_m, "baseline_uncertainty_m")
    fu = _finite_nonnegative(observation.focal_uncertainty_px, "focal_uncertainty_px")
    guards = []
    if b < min_baseline_m or b - bu <= 0:
        guards.append("baseline_too_small")
    if d < min_disparity_px or d - du <= 0:
        guards.append("parallax_too_small")
    if f <= 0 or f - fu <= 0 or not observation.calibration_valid:
        guards.append("calibration_invalid")
    if observation.correspondence_ambiguous:
        guards.append("ambiguous_correspondence")
    if observation.target_moving:
        guards.append("target_moving")
    if observation.occluded:
        guards.append("occluded")
    if guards:
        return SpatialEvidence(None, guard_failures=tuple(guards), method="calibrated_parallax")

    low = (f - fu) * (b - bu) / (d + du)
    high = (f + fu) * (b + bu) / (d - du)
    if not (math.isfinite(low) and math.isfinite(high) and 0 <= low <= high):
        return SpatialEvidence(None, guard_failures=("degenerate_geometry",), method="calibrated_parallax")
    return SpatialEvidence((Interval(low, high),), method="calibrated_parallax")
