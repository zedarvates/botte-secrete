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
    """Compare two reports without inventing savings for a failed run."""
    base_tokens = max(0, int(baseline.get("tokens_total", 0)))
    optimized_tokens = max(0, int(optimized.get("tokens_total", 0)))
    comparable = bool(baseline.get("success")) == bool(optimized.get("success"))
    saved = base_tokens - optimized_tokens if comparable else 0
    return {
        "comparable": comparable,
        "tokens_saved": saved,
        "savings_pct": round(saved * 100 / base_tokens, 1) if base_tokens else 0.0,
        "iterations_saved": max(0, int(baseline.get("iterations", 0))
                                - int(optimized.get("iterations", 0))),
    }
