#!/usr/bin/env python3
"""Tests for the Conductor.

    python -m skills.conductor.test_conductor
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.conductor import plan, execute, classify
from skills.conductor.executor import SAFE, GATED, NEEDS_ARGS
from skills.capabilities.registry import LAYERS


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _step(cap, command, local=True, order=1):
    return {"order": order, "layer": "ACT", "capability": cap,
            "local": local, "command": command, "why": "test"}


def _executor_tests(state):
    print("\n== conductor executor tests ==")

    # classification
    _ok("read-only cap, no placeholder → SAFE",
        classify(_step("metrics", "python -m skills.metrics.cli .")) == SAFE, state)
    _ok("command with <placeholder> → NEEDS_ARGS",
        classify(_step("skill_finder", "python -m skills.skill_finder.cli '<task>'"))
        == NEEDS_ARGS, state)
    _ok("cloud step (local=False) → GATED",
        classify(_step("auto_router", "python -m skills.auto_router.cli run x",
                       local=False)) == GATED, state)
    _ok("unknown/mutating cap → GATED",
        classify(_step("bootstrap", "python -m skills.bootstrap.cli proj")) == GATED, state)
    _ok("'see SKILL.md' pointer (no concrete command) → NEEDS_ARGS",
        classify(_step("report", "see skills/report/SKILL.md")) == NEEDS_ARGS, state)

    # a plan with one safe, one gated (mutating, local), one needs-args step
    fake_plan = {"goal": "g", "steps": [
        _step("metrics", "python -m skills.metrics.cli .", order=1),
        _step("bootstrap", "python -m skills.bootstrap.cli proj", order=2),
        _step("skill_finder", "python -m skills.skill_finder.cli '<task>'", order=3),
    ]}

    calls = []
    def rec_runner(cmd, cwd, timeout):
        calls.append(cmd)
        return 0, "ok"

    # safe_only: runs only the safe step, blocks gated, skips needs_args
    calls.clear()
    r = execute(fake_plan, runner=rec_runner)
    _ok("safe_only runs exactly the safe step", len(calls) == 1, state)
    _ok("safe_only mode label", r["mode"] == "safe_only", state)
    _ok("safe_only summary: 1 ran, 1 blocked, 1 skipped",
        r["summary"] == {"ran": 1, "blocked": 1, "skipped": 1, "failed": 0}, state)

    # confirm: also runs the gated step (but never the needs_args one)
    calls.clear()
    r = execute(fake_plan, confirm=True, runner=rec_runner)
    _ok("confirm runs safe + gated (2 steps)", len(calls) == 2, state)
    _ok("confirm never runs needs_args step",
        all("<task>" not in c for c in calls), state)

    # dry_run: runs nothing at all
    calls.clear()
    r = execute(fake_plan, dry_run=True, runner=rec_runner)
    _ok("dry_run runs nothing", len(calls) == 0, state)
    _ok("dry_run mode label", r["mode"] == "dry_run", state)

    # a failing command is reported as failed (non-zero exit)
    def fail_runner(cmd, cwd, timeout):
        return 2, "boom"
    r = execute({"goal": "g", "steps": [
        _step("metrics", "python -m skills.metrics.cli .")]}, runner=fail_runner)
    _ok("non-zero exit → status failed", r["summary"]["failed"] == 1, state)

    # always 0 cloud tokens + JSON-serialisable + error passthrough
    _ok("executor report is 0 cloud tokens", r["cloud_tokens"] == 0, state)
    _ok("executor report is JSON-serialisable", isinstance(json.dumps(r), str), state)
    _ok("plan error passes through", "error" in execute({"error": "x"}), state)


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

    _executor_tests(state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
