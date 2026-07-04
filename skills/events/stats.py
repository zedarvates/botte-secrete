#!/usr/bin/env python3
"""events stats — summarise events.jsonl without printing everything.

    python -m skills.events.stats [<project>]

Reads events.jsonl and prints a compact summary: total events, by kind,
escalation rate, and top task types. 0 cloud tokens.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def stats(project: str | Path = ".") -> dict:
    project = Path(project).resolve()
    events_file = project / ".botte" / "events.jsonl"
    if not events_file.exists():
        return {"error": "no events file", "project": str(project)}

    kinds = Counter()
    modes = Counter()
    tiers = Counter()
    escalated = 0
    total = 0

    for line in events_file.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        kinds[evt.get("kind", "unknown")] += 1
        if evt.get("escalated"):
            escalated += 1
        mode = evt.get("mode") or evt.get("decision", {}).get("mode", "")
        if mode:
            modes[mode] += 1
        tier = evt.get("tier") or evt.get("decision", {}).get("tier", "")
        if tier:
            tiers[tier] += 1

    return {
        "project": str(project),
        "total": total,
        "by_kind": dict(kinds.most_common()),
        "by_mode": dict(modes.most_common()),
        "by_tier": dict(tiers.most_common()),
        "escalated": escalated,
        "escalation_rate": round(100 * escalated / total, 1) if total else 0,
        "cloud_tokens": 0,
    }


def main():
    project = sys.argv[1] if len(sys.argv) > 1 else "."
    s = stats(project)
    print(f"📊 Events — {s['project']}  ({s['total']} events)")
    print(f"   by kind: {s['by_kind']}")
    print(f"   by mode: {s['by_mode']}")
    if s["escalated"]:
        print(f"   escalated: {s['escalated']}/{s['total']} ({s['escalation_rate']}%)")
    else:
        print("   no escalations")


if __name__ == "__main__":
    main()
