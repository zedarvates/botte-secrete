#!/usr/bin/env python3
"""Tests for context_budget — exact knapsack + skill selection.

    python -m skills.context_budget.test_context_budget
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.context_budget import select_skills, knapsack, Item


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== context_budget tests ==")

    # knapsack picks the optimal value combo, not the greedy one.
    # Greedy by relevance would grab A (rel 6, 100 tok) first, leaving room for
    # only one of B/C → 6+5=11. Optimal is B+C = 5+5=10... so craft so optimal
    # differs from greedy-by-ratio. Budget 100:
    #   A: rel 6, 60 tok ; B: rel 5, 50 tok ; C: rel 5, 50 tok
    # greedy-by-relevance: A then nothing fits (40 left) → 6.
    # optimal: B+C = 10.
    items = [Item("A", "skill", 60, 6.0), Item("B", "skill", 50, 5.0),
             Item("C", "skill", 50, 5.0)]
    idx, toks, rel = knapsack(items, budget=100, unit=10)
    chosen = {items[i].name for i in idx}
    _ok("knapsack finds the optimal combo (B+C), not greedy A",
        chosen == {"B", "C"} and rel == 10.0, state)
    _ok("knapsack respects the budget", toks <= 100, state)

    # budget 0 or no items → empty
    _ok("zero budget → nothing chosen", knapsack(items, 0)[0] == [], state)
    _ok("no items → nothing chosen", knapsack([], 1000)[0] == [], state)

    # a generous budget takes everything
    idx2, toks2, rel2 = knapsack(items, budget=1000, unit=10)
    _ok("generous budget takes all items", len(idx2) == 3 and rel2 == 16.0, state)

    # determinism: identical inputs → identical output
    _ok("knapsack is deterministic",
        knapsack(items, 100, unit=10) == knapsack(items, 100, unit=10), state)

    # select_skills over the real catalog (deterministic, offline, 0 cloud tokens)
    r = select_skills("optimize slow postgres queries and add tests", budget=3000)
    _ok("select_skills returns chosen skills", len(r["chosen"]) >= 1, state)
    _ok("selection stays within budget", r["tokens_used"] <= 3000, state)
    _ok("selection costs 0 cloud tokens", r["cloud_tokens"] == 0, state)
    _ok("selection is cheaper than the whole catalog",
        r["tokens_used"] <= r["catalog_tokens"], state)
    _ok("result is JSON-serialisable", isinstance(json.dumps(r), str), state)
    _ok("empty query → error", "error" in select_skills("  "), state)

    # a tiny budget forces a strict subset (or nothing), never over budget
    rt = select_skills("postgres", budget=200)
    _ok("tiny budget never exceeds the budget", rt["tokens_used"] <= 200, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
