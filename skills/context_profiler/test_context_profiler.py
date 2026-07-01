#!/usr/bin/env python3
"""Tests for context_profiler — prefix accounting + reduction plan (deterministic).

    python -m skills.context_profiler.test_context_profiler
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.context_profiler import summarize, profile, DEFAULT_WINDOWS


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== context_profiler tests ==")

    # summarize: pure accounting + reduction plan
    comp = {"directives": 500, "core_agent": 500, "tool_schemas": 4000,
            "skill_catalog": 3000, "_n_tools": 40, "_n_skills": 46}
    r = summarize(comp)
    _ok("total is the sum of real components",
        r["total_prefix_tokens"] == 8000, state)
    _ok("window_pct computed for 64k/128k/256k",
        set(r["window_pct"]) == set(DEFAULT_WINDOWS), state)
    _ok("64k pct is total/window",
        r["window_pct"]["64k"] == round(100 * 8000 / 65536, 1), state)
    _ok("internal _n_* keys are hidden from components output",
        "_n_tools" not in r["components"], state)

    levers = {p["lever"] for p in r["reduction_plan"]}
    _ok("plan proposes lazy tool loading", "lazy tool loading" in levers, state)
    _ok("plan proposes on-demand skill search", "on-demand skill search" in levers, state)
    _ok("skill catalog is fully reducible (inject 0)",
        any(p["applies_to"] == "skill_catalog" and p["saves_tokens"] == 3000
            for p in r["reduction_plan"]), state)
    _ok("lazy tools keep only ~5 cores (big cut, not all)",
        0 < next(p["saves_tokens"] for p in r["reduction_plan"]
                 if p["lever"] == "lazy tool loading") < 4000, state)
    _ok("minimal prefix < total", r["minimal_prefix_tokens"] < r["total_prefix_tokens"], state)
    _ok("reducible = total − minimal",
        r["reducible_tokens"] == r["total_prefix_tokens"] - r["minimal_prefix_tokens"], state)
    _ok("summarize is JSON-serialisable", isinstance(json.dumps(r), str), state)

    # tiny catalog (fewer tools than the core floor) → no lazy-tools lever
    r2 = summarize({"tool_schemas": 100, "_n_tools": 3, "skill_catalog": 0})
    _ok("no lazy-tools lever when tools <= core floor",
        all(p["lever"] != "lazy tool loading" for p in r2["reduction_plan"]), state)

    # profile() on the real repo: structure + measures the tool-schema cost
    pr = profile(".")
    _ok("profile returns totals + window_pct + counts",
        pr["total_prefix_tokens"] >= 0 and "window_pct" in pr and "counts" in pr, state)
    _ok("tool schemas are actually accounted (the hidden cost)",
        pr["components"]["tool_schemas"] > 0, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
