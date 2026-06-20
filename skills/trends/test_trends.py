#!/usr/bin/env python3
"""Tests for trends. python -m skills.trends.test_trends"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.trends import snapshot, show, load


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== trends tests ==")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "AGENTS.md").write_text("ok", encoding="utf-8")
        (p / "a.py").write_text("x=1\n", encoding="utf-8")
        s1 = snapshot(p)
        _ok("snapshot returns a timestamped record", "ts" in s1 and "loc" in s1, state)
        (p / "b.py").write_text("y=2\nz=3\n", encoding="utf-8")
        snapshot(p)
        _ok("two snapshots persisted", len(load(p)) == 2, state)
        r = show(p)
        _ok("show computes a delta vs previous",
            "loc" in r["delta_since_previous"] and r["delta_since_previous"]["loc"]["change"] >= 1,
            state)
        _ok("show with one project, latest present", r["latest"] is not None, state)
    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
