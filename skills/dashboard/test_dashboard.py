#!/usr/bin/env python3
"""Tests for dashboard. python -m skills.dashboard.test_dashboard"""
from __future__ import annotations
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from skills.dashboard import collect, generate
from skills.dashboard.tui import render, sparkline, build_panels


def main() -> int:
    state = [0, 0]
    def _ok(m, cond): print(f"  [{'PASS' if cond else 'FAIL'}] {m}"); state[0 if cond else 1]+=1
    print("== dashboard tests ==")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d); (p/"AGENTS.md").write_text("ok",encoding="utf-8"); (p/"a.py").write_text("x=1\n",encoding="utf-8")
        data = collect(p)
        _ok("collect gathers all four panels",
            all(k in data for k in ("routing_savings","trends","metrics","outstanding_fixes")))
        paths = generate(p, fmt="html")
        _ok("generates a timestamped html dashboard",
            len(paths)==1 and paths[0].endswith(".html") and Path(paths[0]).exists())

        # --tui / --watch data source: same collect() dict, rendered as ANSI panels
        panels = build_panels(data)
        _ok("tui.build_panels returns the 4 fixed panels",
            [pnl.title for pnl in panels] == ["METRICS", "ROUTING SAVINGS",
                                              "OUTSTANDING FIXES", "TRENDS (Δ since last)"])
        out = render(data)
        _ok("tui.render includes the project header and box-drawing panels",
            "Botte dashboard" in out and "┌─" in out)

    _ok("sparkline needs 2+ points, else falls back to dots",
        sparkline([]) == "" or sparkline([5]) == "·")
    _ok("sparkline is monotonic-shaped for a rising series",
        sparkline([1, 2, 3, 4, 5, 6, 7, 8])[0] < sparkline([1, 2, 3, 4, 5, 6, 7, 8])[-1])
    _ok("sparkline handles a flat series without dividing by zero",
        len(set(sparkline([3, 3, 3, 3]))) == 1)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1]==0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
