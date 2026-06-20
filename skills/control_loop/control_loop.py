"""Control loop — measure routing outcomes, adapt the routing thresholds.

Closes the system into a self-improving loop: every routing decision + its
outcome is recorded; periodically we analyse the ledger and nudge the effort→tier
thresholds (read live by skills.auto_router.effort) so the router gets better at
keeping work local without failing.

  record(...)   append one decision+outcome to the ledger
  analyze()     aggregate the ledger (local %, savings, escalation/success rates)
  adapt()       compute adjusted thresholds from the stats (+ rationale)
  apply()       write the thresholds the router reads next time

Conservative by design: needs enough data, moves boundaries in small steps,
clamps to a sane range, and keeps ordering. Pure stdlib.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from skills.auto_router.effort import (
    DEFAULT_THRESHOLDS, load_thresholds, _THRESHOLDS_PATH,
)

LEDGER_PATH = Path.home() / ".botte" / "control-ledger.jsonl"

MIN_SAMPLES = 10          # don't adapt on noise
STEP = 0.03               # small boundary nudges
LOCAL_MIN, LOCAL_MAX = 0.18, 0.45   # clamp the LOCAL→CHEAP boundary


def record(*, task: str = "", effort_score: float = 0.0, tier: str = "",
           mode: str = "local", tokens_saved: int = 0, escalated: bool = False,
           success: bool = True, path: Optional[Path] = None) -> None:
    """Append one routing decision + outcome to the ledger (best-effort)."""
    p = path or LEDGER_PATH
    rec = {"ts": time.time(), "task": task[:80], "effort": round(float(effort_score), 3),
           "tier": tier, "mode": mode, "tokens_saved": int(tokens_saved),
           "escalated": bool(escalated), "success": bool(success)}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def load(path: Optional[Path] = None) -> list[dict]:
    p = path or LEDGER_PATH
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def analyze(records: Optional[list[dict]] = None) -> dict:
    recs = records if records is not None else load()
    n = len(recs)
    if not n:
        return {"samples": 0}
    local = sum(1 for r in recs if r.get("mode") == "local")
    esc = sum(1 for r in recs if r.get("escalated"))
    ok = sum(1 for r in recs if r.get("success", True))
    saved = sum(int(r.get("tokens_saved", 0)) for r in recs)
    by_tier: dict[str, int] = {}
    for r in recs:
        by_tier[r.get("tier", "?")] = by_tier.get(r.get("tier", "?"), 0) + 1
    return {
        "samples": n,
        "local_pct": round(local * 100 / n),
        "escalation_rate": round(esc / n, 3),
        "success_rate": round(ok / n, 3),
        "tokens_saved_total": saved,
        "by_tier": by_tier,
    }


def adapt(stats: Optional[dict] = None, thresholds: Optional[list] = None) -> dict:
    """Compute adjusted thresholds from outcomes. Returns {thresholds, changed, why}."""
    stats = stats if stats is not None else analyze()
    cur = list(thresholds or load_thresholds())
    free, local, cheap, standard = cur
    n = stats.get("samples", 0)
    if n < MIN_SAMPLES:
        return {"thresholds": cur, "changed": False,
                "why": f"insufficient data ({n}/{MIN_SAMPLES} samples) — no change"}

    esc = stats.get("escalation_rate", 0.0)
    succ = stats.get("success_rate", 1.0)
    why = []
    if succ >= 0.85 and esc < 0.15:
        new_local = min(round(local + STEP, 3), LOCAL_MAX)
        if new_local != local:
            why.append(f"local reliable (success {succ:.0%}, escalation {esc:.0%}) "
                       f"→ keep more local ({local}→{new_local})")
            local = new_local
    elif esc > 0.30:
        new_local = max(round(local - STEP, 3), LOCAL_MIN)
        if new_local != local:
            why.append(f"local insufficient (escalation {esc:.0%}) "
                       f"→ escalate borderline sooner ({cur[1]}→{new_local})")
            local = new_local

    # keep strict ordering free < local < cheap < standard
    local = min(max(local, free + 0.02), cheap - 0.02)
    new = [free, round(local, 3), cheap, standard]
    return {"thresholds": new, "changed": new != cur,
            "why": "; ".join(why) or "within target band — no change"}


def apply(thresholds: list, path: Optional[Path] = None) -> Path:
    p = path or _THRESHOLDS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"thresholds": thresholds,
                             "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                 encoding="utf-8")
    return p


def reset_thresholds(path: Optional[Path] = None) -> None:
    apply(list(DEFAULT_THRESHOLDS), path=path)
