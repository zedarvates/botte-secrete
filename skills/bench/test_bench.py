#!/usr/bin/env python3
"""Tests for botte bench — deterministic, no network, no LLM required.

    python -m skills.bench.test_bench
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.bench.bench import run, BASELINE_TIER
from skills.bench.tasks import BENCH_TASKS
from skills.tiered_router import Tier


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== bench tests ==")

    r = run()
    _ok("runs the full built-in corpus", r["corpus_size"] == len(BENCH_TASKS), state)
    _ok("every task produces a row", len(r["rows"]) == len(BENCH_TASKS), state)
    _ok("baseline uses a fixed, documented tier",
        BASELINE_TIER == Tier.STANDARD and "STANDARD" in r["baseline"], state)

    t = r["totals"]
    _ok("with-belt tokens never exceed the baseline (routing can't cost more)",
        t["with_belt_tokens"] <= t["baseline_tokens"], state)
    _ok("token savings percentage is non-negative",
        t["token_savings_pct"] >= 0, state)
    _ok("usd savings percentage is non-negative",
        t["usd_savings_pct"] >= 0, state)
    _ok("local_pct is a valid percentage", 0 <= r["local_pct"] <= 100, state)

    _ok("local decisions cost exactly 0 tokens (0 cloud tokens claim)",
        all(row["actual_tokens"] == 0 for row in r["rows"] if row["decision"] == "local"),
        state)
    _ok("every row's baseline tokens > 0 (baseline always assumes a real cloud call)",
        all(row["baseline_tokens"] > 0 for row in r["rows"]), state)

    # a trivial task and a hard task should not get the same tier
    trivial_row = next(row for row in r["rows"] if "rename variable" in row["task"])
    hard_row = next(row for row in r["rows"] if "distributed consensus" in row["task"])
    _ok("a trivial task and a hard reasoning task are routed differently",
        trivial_row["tier"] != hard_row["tier"] or trivial_row["decision"] != hard_row["decision"],
        state)

    # run() accepts a custom corpus (reproducibility on a subset / CI smoke test)
    small = run(tasks=BENCH_TASKS[:3])
    _ok("run() accepts a custom task list", small["corpus_size"] == 3, state)

    # deterministic: same corpus, same result shape twice (decide() has no randomness)
    r2 = run(tasks=BENCH_TASKS[:3])
    _ok("running the same corpus twice gives the same decisions",
        [row["decision"] for row in small["rows"]] == [row["decision"] for row in r2["rows"]],
        state)

    _ok("result is JSON-serialisable", isinstance(r, dict) and "totals" in r, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
