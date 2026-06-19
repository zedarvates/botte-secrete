#!/usr/bin/env python3
"""Tests for preflight (policy + hook).

    python -m skills.preflight.test_preflight
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.preflight import policy
from skills.preflight.hook import build_context


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== preflight tests ==")

    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        # no policy → load returns the default
        _ok("load() returns default when none committed",
            "prefer" in policy.load(proj).lower() or "LOCAL" in policy.load(proj), state)
        # write_default creates it, idempotent
        p1 = policy.write_default(proj)
        _ok("write_default creates .botte/policy.md",
            p1 is not None and (proj / ".botte" / "policy.md").exists(), state)
        _ok("write_default is idempotent (no overwrite)",
            policy.write_default(proj) is None, state)
        # AGENTS pointer
        (proj / "AGENTS.md").write_text("# A\nstuff\n", encoding="utf-8")
        _ok("ensure_agents_pointer adds a pointer",
            policy.ensure_agents_pointer(proj) and
            ".botte/policy.md" in (proj / "AGENTS.md").read_text(encoding="utf-8"), state)
        _ok("ensure_agents_pointer idempotent",
            policy.ensure_agents_pointer(proj) is False, state)

    # hook context: always carries the prefer-local rule
    ctx = build_context("classify these tickets", Path("."))
    _ok("hook injects prefer-local policy",
        "LOCAL" in ctx and "0 cloud tokens" in ctx, state)
    # big/ambiguous request → nudges improve_prompt
    big = build_context("please design and refactor the whole audit subsystem " * 5, Path("."))
    _ok("hook nudges improve_prompt on big requests", "improve_prompt" in big, state)
    # crash-proof: build_context never raises on odd input
    try:
        build_context("", Path("/nonexistent/xyz"))
        _ok("hook is crash-proof on bad input", True, state)
    except Exception:
        _ok("hook is crash-proof on bad input", False, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
