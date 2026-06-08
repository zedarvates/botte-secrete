"""Health score calculation."""

from __future__ import annotations
from skills.fallow_like.models import AnalysisResult, HealthScore


def calculate_health(result: AnalysisResult) -> HealthScore:
    deductions = 0
    breakdown: dict[str, int] = {}

    d = min(len(result.secrets) * 15, 40)
    deductions += d
    breakdown["secrets"] = d

    d = min(len(result.boundaries) * 10, 30)
    deductions += d
    breakdown["boundaries"] = d

    d = min(len(result.complexity) * 5, 25)
    deductions += d
    breakdown["complexity"] = d

    d = min(len(result.dead_code) * 3, 20)
    deductions += d
    breakdown["dead_code"] = d

    d = min(len(result.duplication) * 5, 20)
    deductions += d
    breakdown["duplication"] = d

    d = min(len(result.feature_flags) * 1, 10)
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
