#!/usr/bin/env python3
"""Tests for demo mode — deterministic, no sleep, no TTY assumptions.

    python -m skills.demo.test_demo
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ["NO_COLOR"] = "1"

from skills.demo import scenario as sc
from skills.demo.demo import build_panels, run_scripted, run_replay, load_events_file
from skills.demo.render import Panel, render_grid


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== demo tests ==")

    panels = build_panels(sc.STEPS)
    _ok("build_panels returns the 4 fixed panels",
        [p.title for p in panels] == ["ROUTING", "SAVINGS (session)", "MICRO-NN", "ESCALATIONS"], state)

    grid = render_grid(panels)
    _ok("render_grid produces multi-line box-drawing output",
        "┌─" in grid and "└" in grid and grid.count("\n") > 4, state)

    tot = sc.totals(sc.STEPS)
    _ok("scenario totals aggregate tokens saved across steps",
        tot["tokens_saved"] == sum(int(s.get("tokens_saved", 0)) for s in sc.STEPS) and tot["tokens_saved"] > 0,
        state)

    frames = list(run_scripted(delay=0, clear=False))
    _ok("run_scripted yields one frame per scenario step",
        len(frames) == len(sc.STEPS), state)
    _ok("later frames accumulate more content than earlier ones",
        len(frames[-1]) >= len(frames[0]), state)

    long_panel = Panel("X" * 5, ["a very very very very long line that should be trimmed"], width=20)
    rendered = long_panel.render()
    _ok("Panel.render trims long lines to fit width",
        all(len(line) <= 25 for line in rendered), state)

    empty = Panel("EMPTY", [])
    _ok("Panel.render shows a placeholder for no data",
        any("none yet" in line for line in empty.render()), state)

    replayed = list(run_replay(sc.STEPS, delay=0, clear=False))
    _ok("run_replay replays an arbitrary captured event list",
        len(replayed) == len(sc.STEPS), state)

    # live mode wiring: read_events/follow_events exist and cooperate with a
    # real project dir without raising (no network, no blocking here).
    with tempfile.TemporaryDirectory() as d:
        from skills.events import log_event, read_events
        log_event("route", project_root=d, out="local", tokens_saved=100)
        panels2 = build_panels(read_events(d))
        _ok("build_panels works on real events.jsonl records too",
            len(panels2) == 4, state)

    # P5b — session replay must accept the exact file `events` actually writes
    # (JSONL), not just a JSON array, since that's the roadmap's documented usage.
    with tempfile.TemporaryDirectory() as d:
        from skills.events import log_event
        log_event("route", project_root=d, out="local", tokens_saved=10)
        log_event("cache", project_root=d, hit=True, tokens_saved=20)
        jsonl_path = Path(d) / ".botte" / "events.jsonl"
        loaded = load_events_file(jsonl_path)
        _ok("load_events_file reads a raw .botte/events.jsonl (JSONL, not an array)",
            len(loaded) == 2 and loaded[0]["kind"] == "route", state)

        array_path = Path(d) / "captured.json"
        array_path.write_text(json.dumps(loaded), encoding="utf-8")
        loaded2 = load_events_file(array_path)
        _ok("load_events_file also reads a JSON array (e.g. `events tail --json`)",
            loaded2 == loaded, state)

        frames = list(run_replay(load_events_file(jsonl_path), delay=0, clear=False))
        _ok("a replayed real events.jsonl produces one frame per event",
            len(frames) == 2, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
