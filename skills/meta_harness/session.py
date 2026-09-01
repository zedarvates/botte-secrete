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
        self.mission_id: str = ""
        self.attempt_id: str = ""
        self.worker_id: str = ""
        self.workspace_lease: dict = {}
        self.context_manifest_sha256: str = ""
        self.handoff: dict | None = None
        self.outcome_id: str = ""

    def bind_contract(
        self,
        *,
        mission_id: str,
        attempt_id: str,
        worker_id: str,
        workspace_lease: dict,
        context_manifest_sha256: str,
    ) -> None:
        """Bind privacy-safe contract metadata to this session."""
        self.mission_id = mission_id
        self.attempt_id = attempt_id
        self.worker_id = worker_id
        self.workspace_lease = dict(workspace_lease)
        self.context_manifest_sha256 = context_manifest_sha256
        self._save()

    def set_handoff(self, handoff: dict) -> None:
        self.handoff = dict(handoff)
        self._save()

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
        if self.mission_id:
            lines.append(f"   Mission: {self.mission_id} / {self.attempt_id}")
        if self.workspace_lease:
            lines.append(
                f"   Lease: {self.workspace_lease.get('lease_id', '')} "
                f"[{self.workspace_lease.get('state', '')}]"
            )
        if self.handoff:
            lines.append(f"   Handoff: {self.handoff.get('status', '')}")
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
            "mission_id": self.mission_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "workspace_lease": self.workspace_lease,
            "context_manifest_sha256": self.context_manifest_sha256,
            "handoff": self.handoff,
            "outcome_id": self.outcome_id,
            "results": [asdict(r) for r in self.results],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _save(self) -> None:
        """Persist session to disk."""
        path = self.storage_dir / f"{self.name}.json"
        path.write_text(self.to_json(), encoding="utf-8")
