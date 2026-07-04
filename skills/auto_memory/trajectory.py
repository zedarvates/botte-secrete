"""
Trajectory Memory Layer — captures agent execution paths.

Inspired by arXiv:2606.09498 (Self-Harness paradigm).
Records: goal → actions → observations → outcomes → refinements.

Usage:
    from skills.auto_memory.trajectory import TrajectoryRecorder
    rec = TrajectoryRecorder("task_id")
    rec.step("plan", {"steps": ["a", "b"]})
    rec.step("execute", {"result": "done"})
    rec.save()
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skills.auto_memory.memory_bank import MEMORY_DIR


@dataclass
class TrajectoryStep:
    """One step in an agent trajectory."""
    ts: float
    phase: str  # "observe", "hypothesize", "plan", "execute", "verify", "refine"
    data: dict[str, Any]
    outcome: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {"ts": self.ts, "phase": self.phase, "data": self.data,
                "outcome": self.outcome, "confidence": self.confidence}


class TrajectoryRecorder:
    """Records and persists agent trajectories."""

    def __init__(self, task_id: str, base_dir: Path | None = None):
        self.task_id = task_id
        self.base = Path(base_dir) if base_dir else MEMORY_DIR / "trajectories"
        self.base.mkdir(parents=True, exist_ok=True)
        self.steps: list[TrajectoryStep] = []

    def step(self, phase: str, data: dict[str, Any], outcome: str | None = None,
             confidence: float = 1.0):
        """Record a trajectory step."""
        self.steps.append(TrajectoryStep(
            ts=time.time(), phase=phase, data=data, outcome=outcome, confidence=confidence
        ))

    def save(self):
        """Persist trajectory to disk."""
        path = self.base / f"{self.task_id}.jsonl"
        with path.open("a") as f:
            for step in self.steps:
                f.write(json.dumps(step.to_dict()) + "\n")
        self.steps.clear()

    def load(self) -> list[dict]:
        """Load trajectory from disk."""
        path = self.base / f"{self.task_id}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().strip().split("\n") if line]

    def summary(self) -> dict:
        """Return a summary of the trajectory."""
        phases = [s.phase for s in self.steps]
        return {
            "task_id": self.task_id,
            "phases": phases,
            "step_count": len(self.steps),
            "duration": (max(s.ts for s in self.steps) - min(s.ts for s in self.steps)) if self.steps else 0,
        }