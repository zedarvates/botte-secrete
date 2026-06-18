#!/usr/bin/env python3
"""Tests for metrics — tempfile project, deterministic.

    python -m skills.metrics.test_metrics
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.metrics import collect


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== metrics tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "web").mkdir()
        (root / "web" / "app.ts").write_text("const a=1\nconst b=2\nconst c=3\n", encoding="utf-8")
        (root / "server").mkdir()
        (root / "server" / "main.zig").write_text("pub fn main() void {}\n" * 5, encoding="utf-8")
        (root / "tools").mkdir()
        (root / "tools" / "x.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "junk.js").write_text("x\n" * 999, encoding="utf-8")
        (root / "CLAUDE.md").write_text("word " * 1200, encoding="utf-8")  # ~1500 tok

        m = collect(root)
        _ok("counts LOC across languages", m.loc_total > 0, state)
        _ok("detects TypeScript + Zig + Python",
            {"TypeScript", "Zig", "Python"} <= set(m.by_language), state)
        _ok("breaks down by component (web/server/tools)",
            {"web", "server", "tools"} <= set(m.by_component), state)
        _ok("ignores node_modules",
            "node_modules" not in m.by_component and "JavaScript" not in m.by_language, state)
        _ok("directive score computed", m.directive_score > 0, state)
        _ok("always-on tokens reflect CLAUDE.md", m.always_on_tokens > 500, state)

        c = m.cost
        _ok("analysis cost is 0 LLM tokens", c["analysis_llm_tokens"] == 0, state)
        _ok("always-on per-session = per-turn × turns",
            c["always_on_tokens_per_session"] == c["always_on_tokens_per_turn"] * 30, state)
        _ok("skill-search avoided is reported", "skill_search_tokens_avoided" in c, state)

        # JSON round-trips
        _ok("to_dict is JSON-serialisable",
            isinstance(json.dumps(m.to_dict()), str), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
