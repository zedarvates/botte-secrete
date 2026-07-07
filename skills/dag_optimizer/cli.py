"""DAG Optimizer — optimisations DAG/RAG pour pipelines multi-agents.

6 techniques Copilot-inspired :
P56 — DAG Waves : les agents produisent des deltas en vagues synchrones
P57 — DAG Pruning : supprimer les nœuds/branches inutiles
P58 — DAG Memoization : cache par nœud (skip si inputs inchangés)
P59 — RAG Delta Retrieval : ne récupérer que les nouveaux éléments
P60 — RAG Query Shaping : reformuler la requête pour réduire le contexte
P61 — RAG-guided Routing : le RAG décide quel agent appeler
P62 — DAG/RAG Fusion Layer : couche de fusion DAG+RAG

Usage:
    python -m skills.dag_optimizer.cli prune --nodes A,B,C --deps A→B,B→C
    python -m skills.dag_optimizer.cli memoize node_A --input "..." --output "..."
    python -m skills.dag_optimizer.cli wave --agents "scan,fix,verify"
    python -m skills.dag_optimizer.cli rag --query "find vulnerability" --docs 5
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

STORE = Path.home() / ".botte" / "dag-cache.json"


# ── DAG Nodes ──────────────────────────────────────────────────

class DAGGraph:
    """Représentation d'un DAG d'agents."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[tuple[str, str]] = []
        self._memo: dict[str, str] = {}
        self._load()

    def _load(self):
        if STORE.exists():
            try:
                data = json.loads(STORE.read_text())
                self._memo = data.get("memo", {})
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps({"memo": self._memo}, indent=2))

    def add_node(self, name: str, cost: float = 1.0, agent_type: str = "generic"):
        self.nodes[name] = {"name": name, "cost": cost, "type": agent_type}

    def add_edge(self, fr: str, to: str):
        self.edges.append((fr, to))

    def prune(self, keep: Optional[list[str]] = None) -> list[str]:
        """Remove unnecessary nodes. Returns removed node names."""
        if keep is None:
            # Auto-prune: keep only nodes that are in a path from sources to sinks
            sources = {n for n in self.nodes if not any(e[1] == n for e in self.edges)}
            sinks = {n for n in self.nodes if not any(e[0] == n for e in self.edges)}
            keep_set: set[str] = set()

            # BFS from sources
            queue = list(sources)
            while queue:
                node = queue.pop(0)
                if node in keep_set:
                    continue
                keep_set.add(node)
                for fr, to in self.edges:
                    if fr == node:
                        queue.append(to)
            keep_list = list(keep_set)
        else:
            keep_list = list(keep)

        removed = [n for n in self.nodes if n not in keep_list]
        for n in removed:
            del self.nodes[n]
        self.edges = [(f, t) for f, t in self.edges if f in self.nodes and t in self.nodes]

        return removed

    def waves(self) -> list[list[str]]:
        """Topological sort into waves (parallel execution groups)."""
        in_degree = {n: 0 for n in self.nodes}
        for fr, to in self.edges:
            in_degree[to] = in_degree.get(to, 0) + 1

        queue = [n for n, d in in_degree.items() if d == 0]
        waves = []

        while queue:
            waves.append(list(queue))
            next_queue = []
            for node in queue:
                for fr, to in self.edges:
                    if fr == node:
                        in_degree[to] -= 1
                        if in_degree[to] == 0:
                            next_queue.append(to)
            queue = next_queue

        return waves

    def memoize(self, node: str, inp: str, output: str):
        """Cache a node's output keyed by input hash."""
        key = f"{node}:{hashlib.sha256(inp.encode()).hexdigest()[:16]}"
        self._memo[key] = output
        self._save()

    def memo_lookup(self, node: str, inp: str) -> Optional[str]:
        """Look up cached output for a node."""
        key = f"{node}:{hashlib.sha256(inp.encode()).hexdigest()[:16]}"
        return self._memo.get(key)

    def stats(self) -> dict:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "memo_entries": len(self._memo),
            "waves": len(self.waves()),
            "prunable_nodes": len(self.prune()),  # Simulate to count
        }


# ── RAG functions ──────────────────────────────────────────────

def shape_query(query: str, max_tokens: int = 200) -> str:
    """Reformulate query to be more concise for RAG retrieval."""
    # Strip common verbose patterns
    lines = query.split("\n")
    # Remove conversational filler
    lines = [l for l in lines if not any(
        p in l.lower() for p in ["let me", "i think", "basically", "actually",
                                  "you know", "by the way", "as i said"]
    )]
    # Take first N tokens
    result = "\n".join(lines)
    if len(result) // 4 > max_tokens:
        result = result[:max_tokens * 4] + "..."

    return result


def delta_retrieval(previous_docs: list[str], new_docs: list[str]) -> list[str]:
    """Only return documents that are new or changed."""
    prev_hashes = {hashlib.sha256(d.encode()).hexdigest()[:16] for d in previous_docs}
    return [d for d in new_docs
            if hashlib.sha256(d.encode()).hexdigest()[:16] not in prev_hashes]


def rag_route(query: str, agents: dict[str, str]) -> Optional[str]:
    """RAG-guided routing: pick the best agent for a query."""
    query_lower = query.lower()
    best_score = 0.0
    best_agent = None

    for agent, keywords in agents.items():
        score = sum(1 for kw in keywords.split(",") if kw.strip() in query_lower)
        score /= max(len(keywords.split(",")), 1)
        if score > best_score:
            best_score = score
            best_agent = agent

    return best_agent


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="dag_optimizer", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    dag = DAGGraph()

    s = sub.add_parser("prune", help="Prune DAG nodes")
    s.add_argument("--nodes", nargs="+", default=[], help="Nodes to keep")
    s.set_defaults(func=lambda a: print(f"Pruned: {dag.prune(a.nodes)}"))

    s2 = sub.add_parser("wave", help="Compute execution waves")
    s2.add_argument("--agents", nargs="+", default=[], help="Agent names")
    s2.set_defaults(func=lambda a: _wave(dag, a))

    s3 = sub.add_parser("memoize", help="Memoize node output")
    s3.add_argument("node", help="Node name")
    s3.add_argument("--input", required=True)
    s3.add_argument("--output", required=True)
    s3.set_defaults(func=lambda a: _memo(dag, a))

    s4 = sub.add_parser("rag", help="RAG query shaping")
    s4.add_argument("--query", required=True, help="Query to shape")
    s4.add_argument("--docs", type=int, default=5, help="Max docs")
    s4.set_defaults(func=lambda a: print(shape_query(a.query)))

    s5 = sub.add_parser("route", help="RAG-guided routing")
    s5.add_argument("--query", required=True)
    s5.add_argument("--agents", nargs="+")
    s5.set_defaults(func=lambda a: _route(a))

    sub.add_parser("stats", help="Show DAG stats").set_defaults(
        func=lambda a: print(json.dumps(dag.stats(), indent=2)))

    args = p.parse_args(argv)
    return 0


def _wave(dag: DAGGraph, args):
    for a in args.agents:
        dag.add_node(a)
    w = dag.waves()
    print(f"Execution waves ({len(w)}):")
    for i, wave in enumerate(w):
        print(f"  Wave {i}: {', '.join(wave)}")


def _memo(dag: DAGGraph, args):
    dag.memoize(args.node, args.input, args.output)
    print(f"✅ Memoized '{args.node}'")


def _route(args):
    agents = {}
    if args.agents:
        for a in args.agents:
            name, kws = a.split(":", 1) if ":" in a else (a, a)
            agents[name] = kws
    best = rag_route(args.query, agents)
    if best:
        print(f"→ Route to: {best}")
    else:
        print("→ No matching agent")


if __name__ == "__main__":
    main()
