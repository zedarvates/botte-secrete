"""orchestrator — orchestre le pipeline d'agents Botte.

Pipeline = liste ordonnée d'étapes.
Chaque étape = {agent, commande, workdir, args}.
L'orchestrateur dispatche vers le runner, collecte les résultats.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from skills.meta_harness.runner import Sandbox, SandboxResult
from skills.meta_harness.governance import Governance
from skills.meta_harness.session import Session


# ── Agents catalogue ──
_AGENT_CATALOG: dict[str, dict] = {
    "porthos": {
        "name": "porthos",
        "skill": "directives_audit",
        "command": ["python3", "-m", "skills.directives_audit.cli", "audit"],
        "description": "Audit des directives (AGENTS.md, CLAUDE.md)",
        "requires": [],
    },
    "rochefort": {
        "name": "rochefort",
        "skill": "cardinal",
        "command": ["python3", "-m", "skills.cardinal.cli", "audit"],
        "description": "Contre-audit red team",
        "requires": ["porthos"],
    },
    "dartagnan": {
        "name": "d'artagnan",
        "skill": "fix",
        "command": ["python3", "-m", "skills.fix.cli", "fix"],
        "description": "Correction automatique",
        "requires": ["porthos"],
    },
    "aramis": {
        "name": "aramis",
        "skill": "optimize",
        "command": ["python3", "-m", "skills.skill_project_optimizer.cli", "optimize"],
        "description": "Optimisation token",
        "requires": [],
    },
    "security": {
        "name": "security",
        "skill": "security_scanner",
        "command": ["python3", "-m", "skills.security_scanner.cli", "scan"],
        "description": "Scan sécurité",
        "requires": [],
    },
    "fast_context": {
        "name": "fast_context",
        "skill": "fast_context",
        "command": ["python3", "-m", "skills.fast_context.cli", "explore"],
        "description": "Exploration repo",
        "requires": [],
    },
    "test": {
        "name": "test",
        "skill": None,  # shell command
        "command": ["python3", "-m", "pytest"],
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
}


class MetaHarness:
    """The meta-harness orchestrator."""

    def __init__(self, workdir: str = ".", approval: bool = False):
        self.workdir = str(Path(workdir).resolve())
        self.governance = Governance(require_approval=approval)
        self.session = Session(name=f"pipeline_{int(time.time())}")

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
                # Fallback: try as a raw CLI command
                resolved.append(Step(
                    agent=name,
                    command=["python3", "-m", name] if name == "test" else [name],
                    args=[],
                    workdir=self.workdir,
                    requires=[],
                ))
                continue

            # Add dependencies recursively
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
        """Execute a plan step by step, respecting governance."""
        self.session.plan = plan

        for i, step in enumerate(plan.steps):
            # Check dependencies
            deps_met = all(
                any(s.agent == dep and s.status == "passed" for s in plan.steps[:i])
                for dep in step.requires
            )
            if not deps_met:
                step.status = "skipped"
                step.output = "Dependencies not met"
                self.session.add_result(step)
                continue

            # Governance check
            if plan.approval_required:
                gate = self.governance.check(step)
                if gate.blocked:
                    step.status = "skipped"
                    step.output = f"Blocked by governance: {gate.reason}"
                    self.session.add_result(step)
                    continue

            # Execute in sandbox
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

        self.session.completed_at = time.time()
        return self.session

    def _resolve_agent(self, name: str) -> Optional[dict]:
        """Resolve an agent name to its catalog entry."""
        name_lower = name.lower().replace("'", "").replace(" ", "_")
        for key, info in _AGENT_CATALOG.items():
            if key == name_lower or info["name"] == name:
                return info
        return None
