#!/usr/bin/env python3
"""Tests for the statusline — deterministic, offline.

    python -m skills.statusline.test_statusline
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.statusline.statusline import render, summarize
from skills.events import log_event


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== statusline tests ==")

    with tempfile.TemporaryDirectory() as d:
        _ok("render on an empty project never raises",
            "botte" in render(d), state)

        log_event("route", project_root=d, out="local", tokens_saved=500)
        log_event("route", project_root=d, out="cloud", tokens_saved=0)
        log_event("cache", project_root=d, hit=True, tokens_saved=200)
        log_event("cache", project_root=d, hit=False)
        log_event("escalate", project_root=d, **{"from": "local", "to": "cloud"})

        s = summarize(d)
        _ok("summarize aggregates tokens saved across route + cache events",
            s["tokens_saved"] == 700, state)
        _ok("summarize counts only real cache hits, not misses",
            s["cache_hits"] == 1, state)
        _ok("summarize splits local vs cloud routes",
            s["local_routes"] == 1 and s["cloud_routes"] == 1, state)
        _ok("summarize counts escalations", s["escalations"] == 1, state)

        line = render(d)
        _ok("render produces a single non-empty line with the token count",
            "\n" not in line and "700" in line, state)
        _ok("render mentions cache hits when present", "cache hits" in line, state)

    _ok("render on a project with no .botte dir at all never raises",
        isinstance(render("/nonexistent/path/xyz"), str), state)

    # CLI entry point: positional arg, no stdin JSON needed
    with tempfile.TemporaryDirectory() as d:
        log_event("route", project_root=d, out="local", tokens_saved=42)
        result = subprocess.run(
            [sys.executable, "-m", "skills.statusline.cli", d],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=15,
        )
        _ok("CLI prints a rendered line and exits 0",
            result.returncode == 0 and "42" in result.stdout, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
