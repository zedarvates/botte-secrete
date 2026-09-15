"""session — persistance d'une session pipeline.

Stocke l'historique des étapes, les résultats, et permet le rollback.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class StepResult:
    """Result of a single pipeline step."""
    agent: str
    status: str  # pending, running, passed, failed, skipped
    output: str = ""
    exit_code: int = -1
    duration: float = 0.0
    sandbox_path: str = ""
    timestamp: float = 0.0


class Session:
    """A pipeline execution session with history and bounded-run termination."""

    def __init__(self, name: str = "", storage_dir: str = ".botte-cache/sessions/"):
        self.name = name or f"pipeline_{int(time.time())}"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()
        self.completed_at: float = 0.0
        self.plan = None  # PipelinePlan
        self.results: list[StepResult] = []
        self.termination_decision: str = "CONTINUE"
        self.termination_reason: str | None = None

    def add_result(self, step) -> None:
        """Record a step result."""
        self.results.append(StepResult(
            agent=step.agent,
            status=step.status,
            output=step.output,
            exit_code=step.exit_code,
            duration=step.duration,
            sandbox_path=step.sandbox_path,
            timestamp=time.time(),
        ))
        self._save()

    def terminate_uncertain(self, reason: str) -> None:
        """Persist a SAFE-EXIT termination without granting retry authority."""
        self.termination_decision = "UNCERTAIN"
        self.termination_reason = reason
        self._save()

    def report(self) -> str:
        """Generate a pipeline report."""
        lines = [f"📋 Pipeline: {self.name}"]
        lines.append(f"   Started: {time.ctime(self.started_at)}")
        if self.completed_at:
            total = round(self.completed_at - self.started_at, 1)
            lines.append(f"   Duration: {total}s")
        if self.termination_decision == "UNCERTAIN":
            lines.append(f"   SAFE-EXIT: UNCERTAIN ({self.termination_reason})")
        lines.append("")

        status_emoji = {
            "passed": "✅", "failed": "❌", "running": "🔄",
            "skipped": "⏭️", "pending": "⏳",
        }

        for r in self.results:
            emoji = status_emoji.get(r.status, "❓")
            lines.append(f"  {emoji} {r.agent:<15} {r.status:<8} "
                         f"({r.duration:.1f}s)")

        lines.append("")
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "passed")
        failed = sum(1 for r in self.results if r.status == "failed")
        skipped = sum(1 for r in self.results if r.status == "skipped")
        lines.append(f"   {passed}/{total} passed, {failed} failed, {skipped} skipped")

        failed_steps = [r for r in self.results if r.status == "failed"]
        if failed_steps:
            lines.append("\n❌ Failed step details:")
            for r in failed_steps:
                lines.append(f"   {r.agent}:")
                lines.append(f"     exit_code={r.exit_code}")
                if r.output:
                    lines.append(f"     {r.output[:200]}")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Export session as JSON."""
        data = {
            "name": self.name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "termination_decision": self.termination_decision,
            "termination_reason": self.termination_reason,
            "results": [asdict(r) for r in self.results],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _save(self) -> None:
        """Persist session to disk."""
        path = self.storage_dir / f"{self.name}.json"
        path.write_text(self.to_json(), encoding="utf-8")
