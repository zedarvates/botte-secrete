#!/usr/bin/env python3
"""Tests for /checkup.

    python -m skills.checkup.test_checkup
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.checkup.cli import run


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== checkup tests ==")

    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        r = run(proj)
        _ok("returns the canonical sections",
            all(k in r for k in ("directives", "infra_tips", "duplication",
                                 "cost", "by_component", "drift", "headline")), state)
        _ok("analysis cost is 0 LLM tokens", r["cost"]["analysis_llm_tokens"] == 0, state)
        _ok("flags missing policy as drift",
            any("policy" in x.lower() for x in r["drift"]), state)
        _ok("flags MCP-not-wired as drift",
            any("MCP" in x for x in r["drift"]), state)
        _ok("result is JSON-serialisable", isinstance(json.dumps(r), str), state)

        # after committing a policy, that particular drift item goes away
        from skills.preflight import policy
        policy.write_default(proj)
        r2 = run(proj)
        _ok("policy drift clears once committed",
            r2["policy_committed"] and not any("No .botte/policy" in x for x in r2["drift"]),
            state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
