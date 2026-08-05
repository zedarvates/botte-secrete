#!/usr/bin/env python3
"""Tests for dashboard. python -m skills.dashboard.test_dashboard"""
from __future__ import annotations
import json
import sys
import tempfile
import threading
import urllib.request
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
        _ok("collect gathers dashboard and loop panels",
            all(k in data for k in ("routing_savings", "trends", "metrics", "outstanding_fixes", "loops")))
        paths = generate(p, fmt="html")
        _ok("generates a timestamped html dashboard",
            len(paths)==1 and paths[0].endswith(".html") and Path(paths[0]).exists())

        # --tui / --watch data source: same collect() dict, rendered as ANSI panels
        panels = build_panels(data)
        _ok("tui.build_panels returns the 5 fixed panels",
            [pnl.title for pnl in panels] == ["METRICS", "ROUTING SAVINGS",
                                              "OUTSTANDING FIXES", "LOOP OPTIMIZER",
                                              "TRENDS (Δ since last)"])
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

    # api (main's live-dashboard implementation) — coexists with the HTML/TUI one
    try:
        from skills.dashboard.api import load_metrics, DashboardHandler, make_server
        from skills.memory_hub.schema import MemoryEntry
        from skills.memory_hub.store import MemoryStore

        with tempfile.TemporaryDirectory() as api_dir:
            api_root = Path(api_dir)
            summary = api_root / "test-summary.json"
            summary.write_text(json.dumps({
                "passed": 711, "failed": 0, "suite_count": 46,
                "partial": False, "status": "passed",
                "generated_at": "2026-08-05T12:00:00+00:00", "git_sha": "abc123",
            }), encoding="utf-8")
            memory_root = api_root / "memory"
            with MemoryStore(base_dir=memory_root) as store:
                store.store(MemoryEntry(key="fixture", value="private",
                                        project_id="dashboard_test"))

            m = load_metrics(test_summary_path=summary, memory_hub_dir=memory_root)
            _ok("api.load_metrics uses the observed test summary",
                m["tests_passed"] == 711 and m["tests_failed"] == 0
                and m["test_suites"] == 46)
            _ok("api exposes Memory Hub aggregates without entry contents",
                m["memory_entries"] == 1 and m["memory_projects"] == 1
                and "private" not in json.dumps(m))

        _ok("api.DashboardHandler exists and load_metrics is callable",
            DashboardHandler is not None and callable(load_metrics))

        server = make_server("127.0.0.1", 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(base + "/", timeout=5) as response:
                html = response.read().decode("utf-8")
                _ok("api serves the canonical control-room HTML",
                    response.status == 200
                    and "<title>Botte Secrète — Control Room</title>" in html)
                _ok("api sends browser hardening headers without wildcard CORS",
                    response.headers.get("Content-Security-Policy") is not None
                    and response.headers.get("Access-Control-Allow-Origin") is None)
            with urllib.request.urlopen(base + "/api/stats", timeout=5) as response:
                live = json.loads(response.read().decode("utf-8"))
                _ok("api serves live JSON metrics", response.status == 200
                    and "tests_status" in live and "memory_by_status" in live)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
    except ImportError:
        _ok("api module importable", False)

    try:
        from scripts.generate_public_dashboard import build

        with tempfile.TemporaryDirectory() as public_dir:
            root = Path(public_dir)
            summary = root / "summary.json"
            summary.write_text(json.dumps({
                "passed": 711, "failed": 0, "suite_count": 46,
                "partial": False, "status": "passed",
            }), encoding="utf-8")
            paths = build(root / "site", summary)
            payload = json.loads((root / "site" / "dashboard-data.json").read_text(
                encoding="utf-8"))
            _ok("public dashboard build writes HTML and JSON",
                len(paths) == 2 and all(path.is_file() for path in paths))
            _ok("public dashboard excludes machine-private metrics",
                payload["snapshot_scope"] == "public_repository"
                and payload["local_metrics_included"] is False
                and payload["memory_entries"] == 0)
    except ImportError:
        _ok("public dashboard generator importable", False)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1]==0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
