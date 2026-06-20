"""Trends — track audit metrics over time and show the delta.

Each snapshot records the headline numbers (directive score, duplicate groups,
LOC, always-on cost, fix count) to `.botte/trends.jsonl`; `show()` returns the
series and the change since the previous run, so the system sees its own progress.
Pure stdlib.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

_KEYS = ("directive_score", "duplicate_groups", "loc", "always_on_tokens", "fixes")


def _trends_path(project: Path) -> Path:
    return Path(project) / ".botte" / "trends.jsonl"


def snapshot(project: str | Path, *, from_checkup: Optional[dict] = None) -> dict:
    """Capture a metrics snapshot. Pulls from a checkup dict if given, else collects."""
    project = Path(project).resolve()
    snap = {"ts": time.strftime("%Y-%m-%d %H:%M:%S")}

    if from_checkup:
        d = from_checkup.get("directives", {})
        snap["directive_score"] = d.get("score") if isinstance(d, dict) else None
        snap["duplicate_groups"] = from_checkup.get("duplication", {}).get("duplicate_groups")
        snap["loc"] = from_checkup.get("loc_total")
        snap["always_on_tokens"] = (from_checkup.get("cost", {}) or {}).get("always_on_tokens_per_turn")
    else:
        try:
            from skills.metrics import collect
            m = collect(project)
            snap["directive_score"] = m.directive_score
            snap["duplicate_groups"] = m.duplicate_groups
            snap["loc"] = m.loc_total
            snap["always_on_tokens"] = m.always_on_tokens
        except Exception:
            pass
    try:
        from skills.fix import find_fixes
        snap["fixes"] = find_fixes(project)["total_fixes"]
    except Exception:
        snap["fixes"] = None

    p = _trends_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap) + "\n")
    return snap


def load(project: str | Path) -> list[dict]:
    p = _trends_path(Path(project))
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def show(project: str | Path) -> dict:
    series = load(project)
    delta = {}
    if len(series) >= 2:
        a, b = series[-2], series[-1]
        for k in _KEYS:
            va, vb = a.get(k), b.get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                delta[k] = {"from": va, "to": vb, "change": round(vb - va, 2)}
    return {"snapshots": len(series), "latest": series[-1] if series else None,
            "delta_since_previous": delta, "series": series[-10:]}
