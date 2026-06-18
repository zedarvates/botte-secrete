#!/usr/bin/env python3
"""Tests for the fallow scanner's scaling fixes (prune + cap).

    python -m skills.fallow_like.test_scanner
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.fallow_like.scanner import ProjectScanner, DEFAULT_IGNORE_DIRS


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== fallow scanner tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src").mkdir()
        (root / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        # vendored / worktree dirs that must be pruned
        for skip in ("node_modules", ".venv", ".kilo"):
            (root / skip).mkdir()
            (root / skip / "junk.py").write_text("def g():\n    return 2\n", encoding="utf-8")

        res = ProjectScanner(str(root)).scan()
        scanned = {f.path.replace("\\", "/") for f in res.files}
        _ok("scans real source file", "src/a.py" in scanned, state)
        _ok("prunes node_modules/.venv/.kilo",
            not any(p.startswith(("node_modules", ".venv", ".kilo")) for p in scanned), state)
        _ok("default ignore set covers the usual cruft",
            {"node_modules", ".venv", ".git", "dist"} <= DEFAULT_IGNORE_DIRS, state)

    # file cap stops a pathological tree
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for i in range(20):
            (root / f"m{i}.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        res = ProjectScanner(str(root), max_files=5).scan()
        _ok("respects max_files cap", len(res.files) == 5 and res.stats["capped"], state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
