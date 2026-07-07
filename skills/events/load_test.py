#!/usr/bin/env python3
"""Events load test — simulate high-volume event writing to test rotation.

    python -m skills.events.load_test [--count 10000]
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def generate_events(count: int = 10000) -> list[dict]:
    import random
    kinds = ["route", "route", "route", "escalate", "learn"]  # weighted
    modes = ["local", "local", "local", "cloud"]
    tiers = ["LOCAL", "CHEAP", "STANDARD", "PREMIUM"]
    events = []
    for i in range(count):
        events.append({
            "ts": f"2026-07-04T12:{i%60:02d}:00",
            "kind": random.choice(kinds),
            "mode": random.choice(modes),
            "tier": random.choice(tiers),
            "reason": f"test event {i}",
        })
    return events


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    events = generate_events(count)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
        tmp = f.name

    size = Path(tmp).stat().st_size
    print(f"📊 Load test: {count} events → {size:,} bytes ({size/count:.1f} B/event)")
    print(f"   Rotation at 5 MB would trigger after ~{5_000_000//(size//count):,} events")
    Path(tmp).unlink()


if __name__ == "__main__":
    main()
