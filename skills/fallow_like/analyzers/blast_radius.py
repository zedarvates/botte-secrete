"""Blast radius analysis for change impact."""

from __future__ import annotations
from skills.fallow_like.graph_builder import DependencyGraph
from skills.fallow_like.models import BlastRadiusFinding, Severity


class BlastRadiusAnalyzer:
    def __init__(self, max_depth: int = 5):
        self.max_depth = max_depth

# DEAD CODE (Porthos):     def analyze(self, graph: DependencyGraph, changed_files: list[str] | None = None) -> list:
        findings = []

        if not changed_files:
            changed_files = [
                n for n in graph.graph
                if len(list(graph.graph.predecessors(n))) > 3
            ]

        for fpath in changed_files:
            radius = graph.blast_radius(fpath, self.max_depth)
            if radius["direct"] == 0 and radius["transitive"] == 0:
                continue

            total = radius["direct"] + radius["transitive"]
            if total > 20:
                risk = "critical"
            elif total > 10:
                risk = "high"
            elif total > 3:
                risk = "medium"
            else:
                risk = "low"

            findings.append(BlastRadiusFinding(
                rule_id="BLAST001",
                severity=Severity.CRITICAL if risk == "critical" else Severity.WARNING,
                message=(
                    f"Change to {fpath} affects {radius['direct']} direct "
                    f"and {radius['transitive']} transitive dependents"
                ),
                file=fpath,
                changed_symbol=fpath,
                direct_dependents=radius["direct"],
                transitive_dependents=radius["transitive"],
                risk_level=risk,
                confidence=0.9,
                fix_hint=f"Review all {total} affected files before merging",
            ))

        return findings