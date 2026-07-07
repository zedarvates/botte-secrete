#!/usr/bin/env python3
"""Tests for the event log — temp project dir, deterministic.

    python -m skills.events.test_events
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.events import events as ev


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== events tests ==")

    with tempfile.TemporaryDirectory() as d:
        ev.log_event("route", project_root=d, filter=1, out="local", tokens_saved=210)
        ev.log_event("cache", project_root=d, hit=True, tokens_saved=850)
        recs = ev.read_events(d)
        _ok("log_event appends, read_events reads back in order",
            len(recs) == 2 and recs[0]["kind"] == "route" and recs[1]["kind"] == "cache", state)

        p = ev._events_path(d)
        _ok("writes under .botte/events.jsonl", p.parent.name == ".botte" and p.name == "events.jsonl", state)

        for i in range(5):
            ev.log_event("nn_out", project_root=d, i=i)
        _ok("tail_events returns only the newest N",
            [r["i"] for r in ev.tail_events(d, n=3)] == [2, 3, 4], state)

        ev.clear_events(d)
        _ok("clear_events empties the log", ev.read_events(d) == [], state)

        # rotation: force a tiny MAX_BYTES and verify it keeps only the newest half
        orig_max = ev.MAX_BYTES
        ev.MAX_BYTES = 200
        try:
            for i in range(30):
                ev.log_event("route", project_root=d, i=i, pad="x" * 20)
            recs = ev.read_events(d)
            _ok("rotation keeps the file bounded and newest-last",
                len(recs) < 30 and recs[-1]["i"] == 29, state)
        finally:
            ev.MAX_BYTES = orig_max

        # a malformed line doesn't blow up read_events
        p.write_text(p.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
        try:
            ev.read_events(d)
            _ok("read_events tolerates a malformed line", True, state)
        except Exception:
            _ok("read_events tolerates a malformed line", False, state)

    # logging to an unwritable-ish path never raises
    try:
        ev.log_event("route", project_root="\0invalid")
        _ok("log_event never raises on a bad path", True, state)
    except Exception:
        _ok("log_event never raises on a bad path", False, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
