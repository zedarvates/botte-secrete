#!/usr/bin/env python3
"""Tests for dashboard. python -m skills.dashboard.test_dashboard"""
from __future__ import annotations
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from skills.dashboard import collect, generate


def main() -> int:
    state = [0, 0]
    def _ok(m, c): print(f"  [{'PASS' if c else 'FAIL'}] {m}"); state[0 if c else 1]+=1
    print("== dashboard tests ==")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d); (p/"AGENTS.md").write_text("ok",encoding="utf-8"); (p/"a.py").write_text("x=1\n",encoding="utf-8")
        data = collect(p)
        _ok("collect gathers all four panels",
            all(k in data for k in ("routing_savings","trends","metrics","outstanding_fixes")))
        paths = generate(p, fmt="html")
        _ok("generates a timestamped html dashboard",
            len(paths)==1 and paths[0].endswith(".html") and Path(paths[0]).exists())
    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1]==0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
