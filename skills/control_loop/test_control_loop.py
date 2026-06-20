#!/usr/bin/env python3
"""Tests for the control loop — temp ledger/config, deterministic.

    python -m skills.control_loop.test_control_loop
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.control_loop import control_loop as cl
from skills.auto_router import effort
from skills.auto_router.effort import DEFAULT_THRESHOLDS


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== control_loop tests ==")

    with tempfile.TemporaryDirectory() as d:
        ledger = Path(d) / "ledger.jsonl"
        for _ in range(12):  # local, reliable, no escalation
            cl.record(task="classify", effort_score=0.25, tier="LOCAL",
                      mode="local", tokens_saved=400, escalated=False,
                      success=True, path=ledger)
        recs = cl.load(ledger)
        st = cl.analyze(recs)
        _ok("analyze aggregates the ledger",
            st["samples"] == 12 and st["local_pct"] == 100 and st["tokens_saved_total"] == 4800, state)

        a = cl.adapt(st, thresholds=list(DEFAULT_THRESHOLDS))
        _ok("reliable-local → raises the LOCAL boundary (keep more local)",
            a["changed"] and a["thresholds"][1] > DEFAULT_THRESHOLDS[1], state)

        # escalation-heavy → lowers the LOCAL boundary
        bad = [{"mode": "cloud", "escalated": True, "success": True, "tier": "STANDARD",
                "tokens_saved": 0} for _ in range(12)]
        a2 = cl.adapt(cl.analyze(bad), thresholds=list(DEFAULT_THRESHOLDS))
        _ok("escalation-heavy → lowers the LOCAL boundary (escalate sooner)",
            a2["changed"] and a2["thresholds"][1] < DEFAULT_THRESHOLDS[1], state)

        # too few samples → no change
        a3 = cl.adapt(cl.analyze([{"mode": "local", "success": True, "tier": "LOCAL"}]),
                      thresholds=list(DEFAULT_THRESHOLDS))
        _ok("insufficient data → no change", a3["changed"] is False, state)

        # apply → effort reads the new thresholds live
        cfg = Path(d) / "thresholds.json"
        cl.apply([0.08, 0.40, 0.55, 0.80], path=cfg)
        _orig = effort._THRESHOLDS_PATH
        effort._THRESHOLDS_PATH = cfg
        try:
            _ok("effort.load_thresholds picks up the applied config",
                effort.load_thresholds()[1] == 0.40, state)
            # a score of 0.35 is now LOCAL (was CHEAP under default 0.30 boundary)
            _ok("applied threshold changes the routing tier",
                effort._tier_for(0.35).name == "LOCAL", state)
        finally:
            effort._THRESHOLDS_PATH = _orig

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
