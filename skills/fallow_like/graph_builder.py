"""Dependency graph builder using networkx."""

from __future__ import annotations
import networkx as nx
from skills.fallow_like.scanner import ScanResult
from pathlib import Path


class DependencyGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        self._built = False

# DEAD CODE (Porthos):     def build(self, scan: ScanResult) -> nx.DiGraph:
        for file_ast in scan.files:
            self.graph.add_node(
                file_ast.path,
                language=file_ast.language,
                symbols=[s.name for s in file_ast.symbols],
                imports=file_ast.imports,
                exports=file_ast.exports,
            )

        file_stems: dict[str, list[str]] = {}
        for file_ast in scan.files:
            stem = Path(file_ast.path).stem
            file_stems.setdefault(stem, []).append(file_ast.path)

        for file_ast in scan.files:
            for imp in file_ast.imports:
                for stem, paths in file_stems.items():
                    if stem and stem in imp.replace("/", ".").replace("\\", "."):
                        for target in paths:
                            if target != file_ast.path:
                                self.graph.add_edge(file_ast.path, target, type="import")

        self._built = True
        return self.graph

    def blast_radius(self, changed_file: str, max_depth: int = 5) -> dict:
        if not self._built:
            raise RuntimeError("Graph not built")
        if changed_file not in self.graph:
            return {"direct": 0, "transitive": 0, "files": []}

        direct = list(self.graph.predecessors(changed_file))
        all_affected: set[str] = set()
        queue = [(f, 1) for f in direct]

        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth or current in all_affected:
                continue
            all_affected.add(current)
            for pred in self.graph.predecessors(current):
                queue.append((pred, depth + 1))

        return {
            "direct": len(direct),
            "transitive": len(all_affected),
            "files": sorted(all_affected),
        }

    def hot_paths(self, call_counts: dict[str, int] | None = None) -> list[dict]:
        if not self._built:
            raise RuntimeError("Graph not built")

        pagerank = nx.pagerank(self.graph) if len(self.graph) > 0 else {}
        betweenness = nx.betweenness_centrality(self.graph) if len(self.graph) > 2 else {n: 0.0 for n in self.graph}

        paths = []
        for node in self.graph:
            importance = pagerank.get(node, 0) + betweenness.get(node, 0)
            paths.append({
                "file": node,
                "pagerank": pagerank.get(node, 0),
                "betweenness": betweenness.get(node, 0),
                "importance": importance,
                "call_count": call_counts.get(node, 0) if call_counts else 0,
                "dependents": len(list(self.graph.predecessors(node))),
                "dependencies": len(list(self.graph.successors(node))),
            })

        paths.sort(key=lambda x: x["importance"], reverse=True)
        return paths

    def cycles(self) -> list[list[str]]:
        return list(nx.simple_cycles(self.graph))

    def layers(self) -> dict[str, list[str]]:
        if not self._built:
            return {}
        try:
            layers: dict[str, int] = {}
            for node in nx.topological_sort(self.graph):
                preds = list(self.graph.predecessors(node))
                layer = max((layers.get(p, 0) for p in preds), default=-1) + 1
                layers[node] = layer
            result: dict[str, list[str]] = {}
            for node, layer in layers.items():
                result.setdefault(f"layer_{layer}", []).append(node)
            return result
        except nx.NetworkXUnfeasible:
            return {"layer_0": list(self.graph.nodes)}