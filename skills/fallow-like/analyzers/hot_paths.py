"""Hot path analysis combining graph topology and runtime data."""

from __future__ import annotations
from skills.fallow_like.graph_builder import DependencyGraph
from skills.fallow_like.runtime.ingestion import RuntimeData
from skills.fallow_like.models import HotPathFinding, Severity


class HotPathAnalyzer:
    def __init__(self, min_calls: int = 100):
        self.min_calls = min_calls

    def analyze(self, graph: DependencyGraph, runtime: RuntimeData | None = None) -> list:
        findings = []
        hot_paths = graph.hot_paths(call_counts=runtime.call_counts if runtime else None)

        for hp in hot_paths:
            if hp["call_count"] >= self.min_calls or hp["importance"] > 0.1:
                severity = Severity.CRITICAL if hp["call_count"] > 10000 else Severity.WARNING
                findings.append(HotPathFinding(
                    rule_id="HOT001",
                    severity=severity,
                    message=(
                        f"Hot path: {hp['file']} — importance={hp['importance']:.3f}, "
                        f"call_count={hp['call_count']}, dependents={hp['dependents']}"
                    ),
                    file=hp["file"],
                    path=hp["file"],
                    call_count=hp["call_count"],
                    avg_latency_ms=runtime.latencies.get(hp["file"], 0) if runtime else 0,
                    p99_latency_ms=runtime.p99_latencies.get(hp["file"], 0) if runtime else 0,
                    importance_score=hp["importance"],
                    confidence=0.8,
                    fix_hint="Optimize this file — many dependents and/or high call volume",
                ))

        return findings
