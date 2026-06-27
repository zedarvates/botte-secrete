"""Audit DAG — one canonical, machine-first audit artifact.

An audit is a *graph*, not a flat list: nodes are findings, edges are relations
(duplicate / same-file / blocks). Two renderings are derived from this single
source (see render.py): an ultra-compact form for LLMs and HTML for humans.

Why a DAG instead of a list: an LLM summarizing a flat list silently drops items.
Here every finding is an addressable node and the traversal order is deterministic
(severity, then file, then line), so nothing is forgotten and duplicates become
explicit edges instead of repeated text. Composes fallow_like findings.

Pure stdlib (no pydantic needed at this layer — findings come in as plain dicts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

_SEV_RANK = {"critical": 3, "error": 2, "warning": 1, "info": 0}


@dataclass
class Node:
    id: str
    rule: str
    severity: str
    file: str
    line: int
    message: str
    fix: str = ""
    confidence: float = 1.0
    count: int = 1          # how many identical findings collapsed into this node


@dataclass
class Edge:
    src: str
    dst: str
    kind: str               # dup | same_file | blocks


@dataclass
class AuditDAG:
    nodes: list[Node]
    edges: list[Edge]
    order: list[str]        # node ids in deterministic visit order
    counts: dict            # severity -> count
    grade: str

    def to_dict(self) -> dict:
        return {
            "grade": self.grade, "counts": self.counts, "order": self.order,
            "nodes": [vars(n) for n in self.nodes],
            "edges": [vars(e) for e in self.edges],
        }


def _norm(f: Any) -> dict:
    """Accept a fallow_like Finding, a pydantic model, or a plain dict."""
    if hasattr(f, "model_dump"):
        f = f.model_dump()
    elif hasattr(f, "__dict__") and not isinstance(f, dict):
        f = dict(vars(f))
    sev = str(f.get("severity", "info"))
    sev = sev.split(".")[-1].lower()        # Severity.ERROR / "error" → "error"
    return {
        "rule": f.get("rule_id") or f.get("rule") or "finding",
        "severity": sev if sev in _SEV_RANK else "info",
        "file": f.get("file", ""), "line": int(f.get("line", 0) or 0),
        "message": (f.get("message") or "").strip(),
        "fix": (f.get("fix_hint") or f.get("fix") or "").strip(),
        "confidence": float(f.get("confidence", 1.0) or 1.0),
    }


def _grade(counts: dict) -> str:
    if counts.get("critical"):
        return "F"
    if counts.get("error", 0) > 2:
        return "D"
    if counts.get("error"):
        return "C"
    if counts.get("warning", 0) > 3:
        return "C"
    if counts.get("warning"):
        return "B"
    return "A"


def build_dag(findings: Iterable[Any]) -> AuditDAG:
    """Build the canonical DAG: dedup → deterministic order → addressable ids → edges."""
    norm = [_norm(f) for f in findings]

    # 1. Dedup exact repeats (same rule+file+line+message), keeping a count.
    dedup: dict[tuple, dict] = {}
    for f in norm:
        key = (f["rule"], f["file"], f["line"], f["message"])
        if key in dedup:
            dedup[key]["count"] += 1
        else:
            dedup[key] = {**f, "count": 1}
    items = list(dedup.values())

    # 2. Deterministic order: severity desc, then file, then line, then rule.
    items.sort(key=lambda f: (-_SEV_RANK[f["severity"]], f["file"], f["line"], f["rule"]))

    # 3. Addressable ids in visit order (n1 = most severe).
    nodes = [Node(id=f"n{i+1}", rule=f["rule"], severity=f["severity"], file=f["file"],
                  line=f["line"], message=f["message"], fix=f["fix"],
                  confidence=f["confidence"], count=f["count"]) for i, f in enumerate(items)]

    # 4. Edges: duplicate-rule instances and same-file locality.
    edges: list[Edge] = []
    by_rule_msg: dict[tuple, list[str]] = {}
    by_file: dict[str, list[str]] = {}
    for n in nodes:
        by_rule_msg.setdefault((n.rule, n.message), []).append(n.id)
        if n.file:
            by_file.setdefault(n.file, []).append(n.id)
    for ids in by_rule_msg.values():
        for a, b in zip(ids, ids[1:]):
            edges.append(Edge(a, b, "dup"))          # same rule+message, different place
    for ids in by_file.values():
        for a, b in zip(ids, ids[1:]):
            edges.append(Edge(a, b, "same_file"))    # locality chain within a file

    counts: dict = {}
    for n in nodes:
        counts[n.severity] = counts.get(n.severity, 0) + 1
    return AuditDAG(nodes=nodes, edges=edges, order=[n.id for n in nodes],
                    counts=counts, grade=_grade(counts))
