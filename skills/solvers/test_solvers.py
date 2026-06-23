#!/usr/bin/env python3
"""Tests for solvers — assignment / bin-packing / scheduling (deterministic).

    python -m skills.solvers.test_solvers
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.solvers import assign_balanced, bin_pack, schedule


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== solvers tests ==")

    # ── assignment (LPT) ──
    r = assign_balanced([("a", 5), ("b", 4), ("c", 3), ("d", 2), ("e", 2)], ["w1", "w2"])
    assigned = [it["task"] for w in r["assignment"].values() for it in w]
    _ok("every task is assigned exactly once",
        sorted(assigned) == ["a", "b", "c", "d", "e"], state)
    _ok("makespan >= largest task and <= total",
        5 <= r["makespan"] <= r["total"], state)
    _ok("load is reasonably balanced (LPT within 4/3 of ideal)",
        r["makespan"] <= (r["total"] / 2) * 4 / 3 + 1e-9, state)
    _ok("assignment is deterministic",
        assign_balanced([("a", 5), ("b", 4)], ["w1", "w2"]) ==
        assign_balanced([("a", 5), ("b", 4)], ["w1", "w2"]), state)
    _ok("no workers → error", "error" in assign_balanced([("a", 1)], []), state)
    _ok("assignment is 0 cloud tokens", r["cloud_tokens"] == 0, state)

    # ── bin packing (FFD) ──
    b = bin_pack([("a", 4), ("b", 7), ("c", 3), ("d", 6), ("e", 1)], capacity=10)
    _ok("every bin respects capacity",
        all(bn["used"] <= 10 + 1e-9 for bn in b["bins"]), state)
    placed = sorted(it["task"] for bn in b["bins"] for it in bn["items"])
    _ok("all items packed", placed == ["a", "b", "c", "d", "e"], state)
    _ok("FFD packs 21 units into 3 bins of 10", b["bin_count"] == 3, state)
    bo = bin_pack([("big", 15), ("a", 4)], capacity=10)
    _ok("oversized items are flagged, not force-packed",
        any(o["task"] == "big" for o in bo["oversize"]), state)
    _ok("zero capacity → error", "error" in bin_pack([("a", 1)], 0), state)

    # ── scheduling (DAG → order + waves) ──
    s = schedule(["build", "test", "lint", "deploy"],
                 {"test": ["build"], "lint": ["build"], "deploy": ["test", "lint"]})
    order = s["order"]
    _ok("order respects every dependency",
        order.index("build") < order.index("test")
        and order.index("test") < order.index("deploy")
        and order.index("lint") < order.index("deploy"), state)
    _ok("parallel waves are grouped (test+lint together)",
        ["build"] in s["waves"] and sorted(s["waves"][1]) == ["lint", "test"], state)
    _ok("max_parallel reflects the widest wave", s["max_parallel"] == 2, state)
    _ok("independent steps form a single wave",
        schedule(["x", "y", "z"])["wave_count"] == 1, state)

    cyc = schedule(["a", "b"], {"a": ["b"], "b": ["a"]})
    _ok("cycle is detected", "error" in cyc and set(cyc["cyclic"]) == {"a", "b"}, state)

    _ok("schedule is JSON-serialisable", isinstance(json.dumps(s), str), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
