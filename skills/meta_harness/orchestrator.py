"""orchestrator — orchestre le pipeline d'agents Botte.

Pipeline = liste ordonnée d'étapes.
Chaque étape = {agent, commande, workdir, args}.
L'orchestrateur dispatche vers le runner, collecte les résultats.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from skills.meta_harness.runner import Sandbox
from skills.meta_harness.governance import Governance
from skills.meta_harness.session import Session
from skills.safe_exit import RunDecision, SafeExitConfig, SafeExitGuard


# ── Agents catalogue ──
_AGENT_CATALOG: dict[str, dict] = {
    "porthos": {
        "name": "porthos",
        "skill": "directives_audit",
        "command": [sys.executable, "-m", "skills.directives_audit.cli", "audit"],
        "description": "Audit des directives (AGENTS.md, CLAUDE.md)",
        "requires": [],
    },
    "rochefort": {
        "name": "rochefort",
        "skill": "cardinal",
        "command": [sys.executable, "-m", "skills.cardinal.cli", "audit"],
        "description": "Contre-audit red team",
        "requires": ["porthos"],
    },
    "dartagnan": {
        "name": "d'artagnan",
        "skill": "fix",
        "command": [sys.executable, "-m", "skills.fix.cli", "fix"],
        "description": "Correction automatique",
        "requires": ["porthos"],
    },
    "aramis": {
        "name": "aramis",
        "skill": "optimize",
        "command": [sys.executable, "-m", "skills.skill_project_optimizer.cli", "optimize"],
        "description": "Optimisation token",
        "requires": [],
    },
    "security": {
        "name": "security",
        "skill": "security_scanner",
        "command": [sys.executable, "-m", "skills.security_scanner.cli", "scan"],
        "description": "Scan sécurité",
        "requires": [],
    },
    "fast_context": {
        "name": "fast_context",
        "skill": "fast_context",
        "command": [sys.executable, "-m", "skills.fast_context.cli", "explore"],
        "description": "Exploration repo",
        "requires": [],
    },
    "migration_audit": {
        "name": "migration_audit",
        "skill": "migration_audit",
        "command": [sys.executable, "-m", "skills.migration_audit.cli"],
        "description": "Gate deterministic entre BUILDER et VALIDATOR",
        "requires": [],
    },
    "test": {
        "name": "test",
        "skill": None,  # shell command
        "command": [sys.executable, "-m", "pytest"],
        "description": "Lance les tests",
        "requires": ["dartagnan"],
    },
}


@dataclass
class Step:
    """A single step in the pipeline."""
    agent: str
    command: list[str]
    args: list[str] = field(default_factory=list)
    workdir: str = ""
    requires: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, passed, failed, skipped
    output: str = ""
    exit_code: int = -1
    duration: float = 0.0
    sandbox_path: str = ""


@dataclass
class PipelinePlan:
    """A plan = ordered list of steps with metadata."""
    name: str
    steps: list[Step] = field(default_factory=list)
    created_at: float = 0.0
    approval_required: bool = False

    def add_step(self, step: Step):
        self.steps.append(step)

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("passed", "skipped") for s in self.steps)

    @property
    def has_failed(self) -> bool:
        return any(s.status == "failed" for s in self.steps)


# ── Built-in plans ──
_BUILTIN_PLANS: dict[str, list[str]] = {
    "audit": ["fast_context", "porthos", "rochefort"],
    "quick-fix": ["porthos", "dartagnan", "test"],
    "full": ["fast_context", "porthos", "rochefort", "dartagnan", "security", "test"],
    "security": ["fast_context", "security"],
    "test-only": ["test"],
    "migration-gate": ["migration_audit"],
}


class MetaHarness:
    """The meta-harness orchestrator."""

    def __init__(
        self,
        workdir: str = ".",
        approval: bool = False,
        *,
        safe_exit_config: SafeExitConfig | None = None,
    ):
        self.workdir = str(Path(workdir).resolve())
        self.governance = Governance(require_approval=approval)
        self.session = Session(name=f"pipeline_{int(time.time())}")
        self.safe_exit_config = safe_exit_config or SafeExitConfig()

    def list_agents(self) -> list[dict]:
        """List available agents with metadata."""
        return [
            {"name": a["name"], "skill": a["skill"],
             "description": a["description"], "requires": a["requires"]}
            for a in _AGENT_CATALOG.values()
        ]

    def list_plans(self) -> dict[str, list[str]]:
        """List available built-in plans."""
        return dict(_BUILTIN_PLANS)

    def plan(self, agents: list[str], approval: bool = False) -> PipelinePlan:
        """Create a plan from a list of agent names.

        Validates dependencies and orders steps correctly.
        Falls back to command execution if a Botte skill is not found.
        """
        normalized = {
            name.lower().replace("-", "_").replace(" ", "_") for name in agents
        }
        if {"builder", "validator"} <= normalized:
            from skills.migration_audit.stage import insert_migration_audit_stage
            agents = insert_migration_audit_stage(agents)

        plan = PipelinePlan(
            name="-".join(agents),
            created_at=time.time(),
            approval_required=approval or self.governance.require_approval,
        )

        resolved: list[Step] = []
        seen: set[str] = set()

        for name in agents:
            agent_info = self._resolve_agent(name)
            if agent_info is None:
                resolved.append(Step(
                    agent=name,
                    command=[sys.executable, "-m", name] if name == "test" else [name],
                    args=[],
                    workdir=self.workdir,
                    requires=[],
                ))
                continue

            for dep in agent_info.get("requires", []):
                if dep not in seen:
                    dep_info = self._resolve_agent(dep)
                    if dep_info:
                        dep_step = Step(
                            agent=dep_info["name"],
                            command=list(dep_info["command"]),
                            args=[],
                            workdir=self.workdir,
                            requires=dep_info.get("requires", []),
                        )
                        resolved.append(dep_step)
                        seen.add(dep)
                    else:
                        resolved.append(Step(
                            agent=dep,
                            command=[dep],
                            workdir=self.workdir,
                        ))
                        seen.add(dep)

            step = Step(
                agent=agent_info["name"],
                command=list(agent_info["command"]),
                args=[],
                workdir=self.workdir,
                requires=agent_info.get("requires", []),
            )
            resolved.append(step)
            seen.add(name)

        plan.steps = resolved
        return plan

    def execute(self, plan: PipelinePlan) -> Session:
        """Execute a plan step by step, respecting governance and SAFE-EXIT."""
        self.session.plan = plan
        guard = SafeExitGuard(self.safe_exit_config)

        for i, step in enumerate(plan.steps):
            deps_met = all(
                any(s.agent == dep and s.status == "passed" for s in plan.steps[:i])
                for dep in step.requires
            )
            if not deps_met:
                step.status = "skipped"
                step.output = "Dependencies not met"
                self.session.add_result(step)
                continue

            if plan.approval_required:
                gate = self.governance.check(step)
                if gate.blocked:
                    step.status = "skipped"
                    step.output = f"Blocked by governance: {gate.reason}"
                    self.session.add_result(step)
                    continue

            step.status = "running"
            sandbox = Sandbox(workdir=step.workdir, sandbox_dir=f".botte-sandbox/{step.agent}")

            t0 = time.time()
            result = sandbox.run(step.command, args=step.args)
            t1 = time.time()

            step.status = "passed" if result.success else "failed"
            step.output = result.stdout[:2000] if result.success else result.stderr[:2000]
            step.exit_code = result.exit_code
            step.duration = round(t1 - t0, 2)
            step.sandbox_path = sandbox.sandbox_dir
            self.session.add_result(step)

            failure_signature = None
            if not result.success:
                # Stable, bounded signature: enough to identify repeating failures
                # without persisting the full stderr in the guard state.
                first_line = (result.stderr or "").strip().splitlines()[:1]
                failure_signature = f"{step.agent}:{result.exit_code}:{first_line[0] if first_line else ''}"[:512]

            guard_result = guard.observe(
                failure_signature=failure_signature,
                tool_calls_delta=1,
            )
            if guard_result.decision == RunDecision.UNCERTAIN:
                self.session.terminate_uncertain(guard_result.reason or "safe_exit")
                self._skip_remaining_after_safe_exit(plan, i + 1, guard_result.reason or "safe_exit")
                break

        self.session.completed_at = time.time()
        self.session._save()
        return self.session

    def _skip_remaining_after_safe_exit(self, plan: PipelinePlan, start: int, reason: str) -> None:
        """Record unexecuted steps after a bounded-run stop."""
        for step in plan.steps[start:]:
            if step.status != "pending":
                continue
            step.status = "skipped"
            step.output = f"SAFE-EXIT: {reason}"
            self.session.add_result(step)

    def _resolve_agent(self, name: str) -> Optional[dict]:
        """Resolve an agent name to its catalog entry."""
        name_lower = name.lower().replace("'", "").replace(" ", "_")
        for key, info in _AGENT_CATALOG.items():
            if key == name_lower or info["name"] == name:
                return info
        return None
