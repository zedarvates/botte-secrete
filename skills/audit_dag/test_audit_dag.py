#!/usr/bin/env python3
"""Tests for audit_dag — one canonical DAG, two faithful renderings.

    python -m skills.audit_dag.test_audit_dag
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.console_utf8 import force_utf8

force_utf8()

from skills.audit_dag import build_dag, to_compact, to_html


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


FINDINGS = [
    {"rule_id": "secret", "severity": "critical", "message": "hardcoded key",
     "file": "a.py", "line": 10, "fix_hint": "use env var"},
    {"rule_id": "taint", "severity": "error", "message": "untrusted → sink",
     "file": "b.py", "line": 20},
    {"rule_id": "dup_code", "severity": "warning", "message": "duplicate block",
     "file": "a.py", "line": 30},
    {"rule_id": "dup_code", "severity": "warning", "message": "duplicate block",
     "file": "c.py", "line": 5},                       # same rule+msg, other file → dup edge
    {"rule_id": "secret", "severity": "critical", "message": "hardcoded key",
     "file": "a.py", "line": 10, "fix_hint": "use env var"},  # exact repeat → collapses
]


def main() -> int:
    state = [0, 0]
    print("== audit_dag tests ==")

    dag = build_dag(FINDINGS)

    # dedup: the exact repeat collapses into one node with count 2.
    _ok("exact duplicate collapses (5 findings → 4 nodes)", len(dag.nodes) == 4, state)
    secret = next(n for n in dag.nodes if n.rule == "secret")
    _ok("collapsed node keeps a count", secret.count == 2, state)

    # determinism + ordering: most severe first, and stable across runs.
    _ok("severity-first order (n1 = critical)", dag.nodes[0].severity == "critical", state)
    _ok("ids are assigned in visit order", dag.order == ["n1", "n2", "n3", "n4"], state)
    _ok("build is deterministic", build_dag(FINDINGS).to_dict() == dag.to_dict(), state)

    # edges: dup (same rule+msg) and same_file locality.
    kinds = {e.kind for e in dag.edges}
    _ok("dup edge links the two duplicate-rule instances", "dup" in kinds, state)
    _ok("same_file edge links findings in a.py", "same_file" in kinds, state)

    # grade: a critical → F.
    _ok("grade is F when a critical exists", dag.grade == "F", state)

    # compact view: addressable + lossless (every node id appears).
    compact = to_compact(dag)
    _ok("compact lists ORDER for traversal", "ORDER n1 n2 n3 n4" in compact, state)
    _ok("compact contains every node (no omission)",
        all(n.id in compact for n in dag.nodes), state)
    _ok("compact carries the fix hint", "use env var" in compact, state)

    # html view: same data, human form.
    page = to_html(dag)
    _ok("html is a full document", page.startswith("<!doctype html"), state)
    _ok("html shows the grade", ">F</div>" in page, state)
    _ok("html contains every finding's rule",
        all(n.rule in page for n in dag.nodes), state)

    # clean repo → grade A, no findings.
    clean = build_dag([])
    _ok("empty findings → grade A", clean.grade == "A" and not clean.nodes, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
