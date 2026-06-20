#!/usr/bin/env python3
"""Tests for cost_estimator + fix.

    python -m skills.cost_estimator.test_cost_estimator
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.cost_estimator import estimate, estimate_fix
from skills.fix import find_fixes


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== cost_estimator + fix tests ==")

    e = estimate("code_review", 4000)
    _ok("estimate yields tokens/model/usd/time",
        e.tokens_in > 0 and e.tokens_out > 0 and e.seconds > 0 and e.usd >= 0, state)
    _ok("human() has all four dimensions",
        all(k in e.human() for k in ("tok", "·", "s")), state)

    prem = estimate("security_audit", 8000)
    _ok("premium (cloud) costs money", prem.usd > 0 and not prem.local, state)

    df = estimate_fix("dead_code", count=11)
    _ok("dead_code fix is local + free", df.local and df.usd == 0, state)
    sf = estimate_fix("secret")
    _ok("secret fix routed to a careful (premium) tier", sf.tier == "PREMIUM", state)

    # fix plan on a synthetic project
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "AGENTS.md").write_text("See `src/gone.py`.", encoding="utf-8")
        r = find_fixes(proj)
        _ok("find_fixes is plan-only (no edits)",
            "dry-run" in r["mode"], state)
        _ok("stale ref surfaced as a fix with cost",
            any(f["kind"] == "stale_ref" for f in r["fixes"])
            and "stale_ref" in r["cost_by_kind"], state)
        _ok("totals carry tokens + usd + seconds",
            all(k in r["totals"] for k in ("tokens", "usd", "seconds")), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
