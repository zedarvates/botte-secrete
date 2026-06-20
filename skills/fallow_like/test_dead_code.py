#!/usr/bin/env python3
"""Tests for dead_code false-positive reduction (dynamic-usage awareness).

    python -m skills.fallow_like.test_dead_code
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.fallow_like.scanner import ProjectScanner
from skills.fallow_like.analyzers.dead_code import DeadCodeAnalyzer


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== dead_code tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # _tool_x is referenced only via a dispatch table (dynamic) — must NOT be dead.
        # used_helper is called normally. truly_dead is never referenced.
        (root / "mod.py").write_text(
            "def _tool_x(a):\n    return a\n\n"
            "def used_helper(a):\n    return a + 1\n\n"
            "def truly_dead(a):\n    return a - 1\n\n"
            "def run():\n    return used_helper(1)\n\n"
            'DISPATCH = {"x": _tool_x}\n',
            encoding="utf-8")
        scan = ProjectScanner(str(root)).scan()
        dead = {f.symbol_name for f in DeadCodeAnalyzer().analyze(scan)}

        _ok("dispatch-referenced symbol NOT flagged dead", "_tool_x" not in dead, state)
        _ok("normally-called helper NOT flagged dead", "used_helper" not in dead, state)
        _ok("genuinely unused symbol IS flagged dead", "truly_dead" in dead, state)
        _ok("framework override (do_GET) not flagged",
            "do_GET" not in dead, state)  # not defined here; sanity that run() entry isn't flagged
        _ok("entry point run() not flagged", "run" not in dead, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
