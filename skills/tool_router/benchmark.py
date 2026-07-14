"""Dependency-free evaluation for optional tool routers."""

from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass
from typing import Sequence

from .base import ToolRouter, ToolSpec


@dataclass(frozen=True)
class EvaluationCase:
    query: str
    tools: Sequence[ToolSpec]
    expected_tool: str | None
    expected_arguments: dict[str, object]


@dataclass(frozen=True)
class BenchmarkResult:
    total: int
    tool_accuracy: float
    arguments_accuracy: float
    abstention_accuracy: float
    dangerous_false_routes: int
    p95_latency_ms: float
    peak_memory_bytes: int

    def meets_needle_gate(self, local_llm_p95_ms: float) -> bool:
        return (self.tool_accuracy >= 0.95 and self.arguments_accuracy >= 0.98
                and self.dangerous_false_routes == 0 and self.p95_latency_ms < local_llm_p95_ms)


def needle_activation_allowed(needle: BenchmarkResult, local_llm: BenchmarkResult | None) -> bool:
    """Return true only for a fully measured, strictly safer Needle result.

    Missing comparison data fails closed.  This function deliberately does not
    mutate configuration: a deployment layer must opt in after this gate passes.
    """
    return local_llm is not None and needle.meets_needle_gate(local_llm.p95_latency_ms)


def benchmark(router: ToolRouter, cases: Sequence[EvaluationCase]) -> BenchmarkResult:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    latencies: list[float] = []
    correct_tools = correct_arguments = correct_abstentions = dangerous = 0
    tracemalloc.start()
    try:
        for case in cases:
            started = time.perf_counter()
            result = router.route(case.query, case.tools)
            latencies.append((time.perf_counter() - started) * 1000)
            correct_tools += result.tool_name == case.expected_tool
            correct_arguments += result.arguments == case.expected_arguments
            correct_abstentions += result.abstained == (case.expected_tool is None)
            dangerous += int(case.expected_tool is None and not result.abstained)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    ordered = sorted(latencies)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * .95 + .999999) - 1))]
    total = len(cases)
    return BenchmarkResult(total, correct_tools / total, correct_arguments / total, correct_abstentions / total, dangerous, p95, peak)
