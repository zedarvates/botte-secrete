"""Deterministic reference cost for an unoptimized full-loop execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class BaselineStep:
    context_tokens: int
    execution_tokens: int
    verification_tokens: int
    cloud_tokens: int = 0
    agents_run: int = 1
    success: bool = False

    def __post_init__(self) -> None:
        for name in ("context_tokens", "execution_tokens", "verification_tokens",
                     "cloud_tokens", "agents_run"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


def simulate_full_loop(steps: Iterable[BaselineStep]) -> dict[str, int | bool]:
    """Aggregate the cost paid when every supplied iteration runs in full."""
    items = list(steps)
    return {
        "iterations": len(items),
        "tokens_total": sum(
            step.context_tokens + step.execution_tokens + step.verification_tokens
            for step in items
        ),
        "cloud_tokens": sum(step.cloud_tokens for step in items),
        "agents_run": sum(step.agents_run for step in items),
        "success": bool(items and items[-1].success),
    }


def compare(baseline: dict, optimized: dict) -> dict[str, int | float | bool]:
    """Compare supplied counts only when both runs explicitly report success.

    The caller must establish the same task and acceptance checks. These counts
    alone do not prove agent quality, actual model usage or provider billing.
    """
    counts_complete = all(
        type(report.get(name)) is int and report[name] >= 0
        for report in (baseline, optimized)
        for name in ("tokens_total", "iterations")
    )
    comparable = (counts_complete and baseline.get("success") is True
                  and optimized.get("success") is True)
    base_tokens = baseline["tokens_total"] if counts_complete else 0
    optimized_tokens = optimized["tokens_total"] if counts_complete else 0
    saved = base_tokens - optimized_tokens if comparable else 0
    return {
        "comparable": comparable,
        "tokens_saved": saved,
        "savings_pct": round(saved * 100 / base_tokens, 1) if base_tokens else 0.0,
        "iterations_saved": (baseline["iterations"] - optimized["iterations"]
                             if comparable else 0),
    }
