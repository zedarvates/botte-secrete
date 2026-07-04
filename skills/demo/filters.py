#!/usr/bin/env python3
"""Demo filters — replay events with kind/type filters.

    python -m skills.demo.filters <events.jsonl> --only route,escalate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def filter_events(path: str | Path, only_kinds: list[str] | None = None) -> list[dict]:
    path = Path(path)
    events = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if only_kinds and evt.get("kind") not in only_kinds:
            continue
        events.append(evt)
    return events


def main():
    p = argparse.ArgumentParser()
    p.add_argument("events_file")
    p.add_argument("--only", help="Comma-separated kinds: route,escalate,learn")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    only = args.only.split(",") if args.only else None
    events = filter_events(args.events_file, only)

    if args.json:
        print(json.dumps(events, indent=2, default=str))
        return

    print(f"📊 {len(events)} filtered events")
    for e in events[:20]:
        print(f"   [{e.get('kind','?')}] {e.get('reason','')[:80]}")


if __name__ == "__main__":
    main()
