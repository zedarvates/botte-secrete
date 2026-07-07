#!/usr/bin/env python3
"""Events export — Parquet format for offline analysis (pandas optional).

    python -m skills.events.export <events.jsonl> [--parquet|--csv]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def export_csv(path: str, output: str) -> str:
    import csv
    events = []
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not events:
        return "No events"

    with open(output, "w", newline="") as f:
        keys = ["kind", "mode", "tier", "reason", "escalated"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for e in events:
            d = e.get("decision", e)
            w.writerow({
                "kind": e.get("kind", ""),
                "mode": d.get("mode", ""),
                "tier": d.get("tier", ""),
                "reason": d.get("reason", "")[:100],
                "escalated": e.get("escalated", False),
            })
    return output


def export_parquet(path: str, output: str) -> str:
    try:
        import pandas as pd
        events = []
        for line in Path(path).read_text(errors="replace").splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        df = pd.DataFrame(events)
        df.to_parquet(output)
        return output
    except ImportError:
        return "pandas not installed — use --csv instead"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ".botte/events.jsonl"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "--csv"

    out = path.replace(".jsonl", ".csv" if fmt == "--csv" else ".parquet")
    if fmt == "--parquet":
        result = export_parquet(path, out)
    else:
        result = export_csv(path, out)
    print(f"📊 Exported → {result}")


if __name__ == "__main__":
    main()
