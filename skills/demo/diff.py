#!/usr/bin/env python3
"""Demo diff — compare two session replays side by side.

    python -m skills.demo.diff <session1.jsonl> <session2.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load_events(path: str) -> list[dict]:
    events = []
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def diff(a: str, b: str) -> dict:
    ea, eb = load_events(a), load_events(b)
    ka = Counter(e.get("kind") for e in ea)
    kb = Counter(e.get("kind") for e in eb)
    return {
        "a": {"file": a, "events": len(ea), "by_kind": dict(ka)},
        "b": {"file": b, "events": len(eb), "by_kind": dict(kb)},
        "delta_events": len(eb) - len(ea),
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: demo_diff.py <session1.jsonl> <session2.jsonl>")
        return
    d = diff(sys.argv[1], sys.argv[2])
    print(f"📊 Diff: {d['a']['file']} → {d['b']['file']}")
    print(f"   events: {d['a']['events']} → {d['b']['events']} (Δ={d['delta_events']:+d})")
    print(f"   A: {d['a']['by_kind']}")
    print(f"   B: {d['b']['by_kind']}")


if __name__ == "__main__":
    main()
