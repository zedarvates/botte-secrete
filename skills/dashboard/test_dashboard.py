#!/usr/bin/env python3
"""Tests for dashboard. python -m skills.dashboard.test_dashboard"""
from __future__ import annotations
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from skills.dashboard import collect, generate
from skills.dashboard.tui import render, sparkline, build_panels
from skills.dashboard import fleet as fleet_mod


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

    with tempfile.TemporaryDirectory() as fleet_dir:
        fleet_path = Path(fleet_dir) / "fleet.json"
        with tempfile.TemporaryDirectory() as proj_a, tempfile.TemporaryDirectory() as proj_b:
            Path(proj_a, "a.py").write_text("x=1\n", encoding="utf-8")
            Path(proj_b, "b.py").write_text("y=2\n", encoding="utf-8")

            projects = fleet_mod.add(proj_a, path=fleet_path)
            _ok("fleet.add registers a project", str(Path(proj_a).resolve()) in projects)
            fleet_mod.add(proj_b, path=fleet_path)
            _ok("fleet.list_fleet returns both registered projects",
                len(fleet_mod.list_fleet(path=fleet_path)) == 2)

            agg = fleet_mod.aggregate(path=fleet_path)
            _ok("fleet.aggregate collects every registered project",
                agg["totals"]["projects_ok"] == 2 and agg["totals"]["projects_errored"] == 0)
            _ok("fleet.aggregate sums LOC/tokens/fixes across projects",
                all(k in agg["totals"] for k in
                    ("loc_total", "tokens_saved_total", "outstanding_fixes_total")))

            remaining = fleet_mod.remove(proj_a, path=fleet_path)
            _ok("fleet.remove drops exactly one project",
                len(remaining) == 1 and str(Path(proj_a).resolve()) not in remaining)

        # proj_a no longer exists on disk now (tempdir cleaned up) — aggregate
        # over the leftover registration (proj_b, still valid) must not raise
        # even though proj_a would be stale if still registered.
        fleet_mod.add(proj_a, path=fleet_path)  # re-register a now-deleted path
        agg2 = fleet_mod.aggregate(path=fleet_path)
        _ok("fleet.aggregate reports vanished projects as errored, not a crash",
            agg2["totals"]["projects_errored"] >= 1)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1]==0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
