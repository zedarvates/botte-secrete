"""
Metrics for the decision ladder — track how much code was avoided.

Usage:
    from skills.decision_ladder.metrics import LadderMetrics
    metrics = LadderMetrics.load()
    metrics.record(task="extract function names", rung="stdlib", saved=15)
    metrics.save()
    print(metrics.summary())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

METRICS_PATH = Path.home() / ".botte" / "decision-ladder-metrics.json"


@dataclass
class LadderMetrics:
    """Persistent metrics for decision ladder usage."""
    total_checks: int = 0
    by_rung: dict[str, int] = field(default_factory=dict)
    total_lines_saved: int = 0
    tasks_avoided: int = 0
    history: list[dict] = field(default_factory=list)

    def record(self, *, task: str, rung: str, saved: int, confidence: float = 0.0):
        """Record one decision ladder check."""
        self.total_checks += 1
        self.by_rung[rung] = self.by_rung.get(rung, 0) + 1
        self.total_lines_saved += saved
        if rung != "new_code":
            self.tasks_avoided += 1
        self.history.append({
            "ts": time.time(),
            "task": task[:120],
            "rung": rung,
            "saved": saved,
            "confidence": round(confidence, 3),
        })
        # Keep only last 1000 entries
        if len(self.history) > 1000:
            self.history = self.history[-500:]

    @property
    def avoidable_pct(self) -> float:
        if not self.total_checks:
            return 0.0
        return round(self.tasks_avoided * 100 / self.total_checks, 1)

    @property
    def avg_lines_saved(self) -> float:
        if not self.tasks_avoided:
            return 0.0
        return round(self.total_lines_saved / self.tasks_avoided, 1)

    def summary(self) -> str:
        lines = [
            f"Decision Ladder Metrics",
            f"  Checks: {self.total_checks}",
            f"  Avoided: {self.tasks_avoided} ({self.avoidable_pct}%)",
            f"  Lines saved: {self.total_lines_saved} (avg {self.avg_lines_saved}/task)",
            f"  By rung: {self.by_rung}",
        ]
        return "\n".join(lines)

    def save(self, path: Path | None = None):
        p = path or METRICS_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_checks": self.total_checks,
            "by_rung": self.by_rung,
            "total_lines_saved": self.total_lines_saved,
            "tasks_avoided": self.tasks_avoided,
            "history": self.history[-100:],  # last 100 only in save
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> LadderMetrics:
        p = path or METRICS_PATH
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(
                total_checks=data.get("total_checks", 0),
                by_rung=data.get("by_rung", {}),
                total_lines_saved=data.get("total_lines_saved", 0),
                tasks_avoided=data.get("tasks_avoided", 0),
                history=data.get("history", []),
            )
        except (json.JSONDecodeError, OSError):
            return cls()
