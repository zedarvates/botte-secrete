"""Health score calculation."""

from __future__ import annotations
from skills.fallow_like.models import HealthScore


def calculate_health(
    scan_result,
    dead_code: list = None,
    duplication: list = None,
    complexity: list = None,
    secrets: list = None,
    boundaries: list = None,
    feature_flags: list = None,
) -> HealthScore:
    """Calculate health score from scan result + analyzer outputs."""
    deductions = 0
    breakdown: dict[str, int] = {}

    secrets = secrets or []
    d = min(len(secrets) * 15, 40)
    deductions += d
    breakdown["secrets"] = d

    boundaries = boundaries or []
    d = min(len(boundaries) * 10, 30)
    deductions += d
    breakdown["boundaries"] = d

    complexity = complexity or []
    d = min(len(complexity) * 5, 25)
    deductions += d
    breakdown["complexity"] = d

    dead_code = dead_code or []
    d = min(len(dead_code) * 3, 20)
    deductions += d
    breakdown["dead_code"] = d

    duplication = duplication or []
    d = min(len(duplication) * 5, 20)
    deductions += d
    breakdown["duplication"] = d

    feature_flags = feature_flags or []
    d = min(len(feature_flags) * 1, 10)
    deductions += d
    breakdown["feature_flags"] = d

    score = max(0, 100 - deductions)
    if score >= 90:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 30:
        grade = "D"
    else:
        grade = "F"

    return HealthScore(score=score, grade=grade, deductions=deductions, breakdown=breakdown)
