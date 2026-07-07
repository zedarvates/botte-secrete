#!/usr/bin/env python3
"""Demo replay — replay events from a JSONL file.

    python -m skills.demo.replay <events.jsonl>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def replay(path: str, delay: float = 0.1) -> None:
    events = []
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not events:
        print("No events found")
        return

    from collections import Counter

    kinds = Counter(e.get("kind") for e in events)
    modes = Counter(e.get("mode") or e.get("decision", {}).get("mode") for e in events)
    print(f"▶️  Replaying {len(events)} events")
    print(f"   kinds: {dict(kinds)}")
    print(f"   modes: {dict(modes)}")
    print()

    for e in events:
        kind = e.get("kind", "?")
        mode = e.get("mode") or e.get("decision", {}).get("mode", "?")
        reason = (e.get("reason") or e.get("decision", {}).get("reason", ""))[:80]
        print(f"   [{kind:8}] {mode:6} — {reason}")
        if delay:
            time.sleep(delay)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "events.jsonl"
    replay(path)
