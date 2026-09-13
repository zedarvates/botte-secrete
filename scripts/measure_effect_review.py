"""Compare serialized planning context. No workflow execution or model calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skills.capabilities.review import METHOD
from skills.conductor import plan

GOALS = (
    "audit my project and report metrics",
    "inspect verified outcome history",
    "reduce token cost and route local models",
)


def size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def measure() -> dict:
    method_bytes = len((ROOT / METHOD).read_bytes())
    rows = []
    for goal in GOALS:
        ordinary = plan(goal)
        full = plan(goal, include_effects=True)
        compact = plan(goal, review_effects=True)
        selected = lambda report: [(s["capability"], s["command"]) for s in report["steps"]]
        if not selected(ordinary) == selected(full) == selected(compact):
            raise ValueError("catalog changed during comparison")
        plain_bytes, full_bytes, compact_bytes = map(size, (ordinary, full, compact))
        total = compact_bytes + method_bytes
        rows.append({"goal": goal, "steps": len(compact["steps"]),
                     "ordinary_bytes": plain_bytes, "full_effects_bytes": full_bytes,
                     "compact_bytes": compact_bytes, "compact_with_method_bytes": total,
                     "reduction_vs_full_percent": round(100 * (1 - total / full_bytes), 1),
                     "overhead_vs_ordinary_bytes": total - plain_bytes})
    return {"measurement": "UTF-8 bytes of compact JSON plus shared instructions once per workflow",
            "limits": "Planning examples only; no model tokens, downstream task quality or execution costs measured. Deferred detail reads add context.",
            "method_bytes": method_bytes, "workflows": rows}


if __name__ == "__main__":
    print(json.dumps(measure(), ensure_ascii=False, indent=2))
