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
    taint: list = None,
) -> HealthScore:
    """Confidence-weighted health score from scan result + analyzer outputs.

    Each finding contributes by its own ``confidence`` (default 1.0) rather than a
    flat count, so a pile of low-confidence/heuristic findings can't tank a clean
    codebase. Hard signals (secrets, boundary violations, complexity) keep their
    weight; heuristic categories (dead code, duplication) are weighted down — dead
    code over-reports on dynamically-imported code (MCP dispatch, `-m`, plugin
    loaders), so it is review-grade, not a hard penalty.
    """
    def _eff(items) -> float:
        return sum(min(float(getattr(i, "confidence", 1.0) or 1.0), 1.0)
                   for i in (items or []))

    # category: (per-effective-finding deduction, cap)
    weights = {
        "secrets":       (15, 40),
        "taint":         (12, 40),   # data-flow security — a hard signal
        "boundaries":    (10, 30),
        "complexity":    (4, 25),
        "duplication":   (3, 15),
        "dead_code":     (1, 10),   # heuristic, false-positive prone → low weight
        "feature_flags": (1, 8),
    }
    items = {
        "secrets": secrets, "taint": taint, "boundaries": boundaries,
        "complexity": complexity, "duplication": duplication,
        "dead_code": dead_code, "feature_flags": feature_flags,
    }
    deductions = 0
    breakdown: dict[str, int] = {}
    for cat, (per, cap) in weights.items():
        d = int(min(round(_eff(items[cat]) * per), cap))
        deductions += d
        breakdown[cat] = d

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
