#!/usr/bin/env python3
"""Tests for local_harness.bench — the harness drives returned-hallucinations to 0.

    python -m skills.local_harness.test_bench
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.console_utf8 import force_utf8

force_utf8()

from skills.local_harness import bench


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== local_harness.bench tests ==")

    rep = bench.run_bench(bench._mock_output)
    raw, h = rep["raw"], rep["harnessed"]

    _ok("the flawed model DOES hallucinate without the harness (>30%)",
        rep["raw_hallucination_rate"] > 0.3, state)
    _ok("the harness returns ZERO hallucinations",
        h["hallucinated_returned"] == 0 and rep["harnessed_hallucination_rate"] == 0.0, state)
    _ok("grounded-correct answers are still trusted locally",
        h["trusted_correct"] == raw["correct"] and raw["correct"] >= 4, state)
    _ok("ungrounded answers + traps are escalated, not returned",
        h["escalated"] == raw["hallucinated"], state)
    _ok("counts are conserved (n = trusted + escalated + abstained + leaked)",
        h["trusted_correct"] + h["escalated"] + h["abstained"]
        + h["hallucinated_returned"] == rep["n"], state)
    _ok("report renders the headline", "Headline" in bench.format_report(rep), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
