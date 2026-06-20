#!/usr/bin/env python3
"""Tests for the Conductor.

    python -m skills.conductor.test_conductor
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.conductor import plan
from skills.capabilities.registry import LAYERS


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== conductor tests ==")

    _ok("empty goal → error", "error" in plan(""), state)

    r = plan("test my desktop app and capture crashes")
    steps = r["steps"]
    _ok("produces a non-empty ordered plan", len(steps) >= 2, state)
    _ok("plan cost is 0 cloud tokens", r["cloud_tokens"] == 0, state)
    _ok("steps ordered by layer (SENSE→…→DEPLOY)",
        [LAYERS.index(s["layer"]) for s in steps] ==
        sorted(LAYERS.index(s["layer"]) for s in steps), state)
    _ok("app_test is in the plan for a GUI-test goal",
        any(s["capability"] == "app_test" for s in steps), state)
    _ok("each step carries a concrete command",
        all(s["command"] for s in steps), state)
    _ok("effort tier is reported", r["effort"]["tier"] in
        ("FREE", "LOCAL", "CHEAP", "STANDARD", "PREMIUM", "UNKNOWN"), state)

    r2 = plan("scrape a web page and ingest it into the knowledge base")
    _ok("ingest is in the plan for a scrape/ingest goal",
        any(s["capability"] == "ingest" for s in r2["steps"]), state)

    _ok("plan is JSON-serialisable", isinstance(json.dumps(r), str), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
