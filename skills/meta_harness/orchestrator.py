"""orchestrator — orchestre le pipeline d'agents Botte.

Pipeline = liste ordonnée d'étapes.
Chaque étape = {agent, commande, workdir, args}.
L'orchestrateur dispatche vers le runner, collecte les résultats.
"""

from __future__ import annotations

import sys
import time
import uuid
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from skills.meta_harness.runner import Sandbox
from skills.meta_harness.governance import Governance
from skills.meta_harness.session import Session
from skills.safe_exit import (
    AuthorizationTier,
    RunDecision,
    SafeExitConfig,
    SafeExitGuard,
)


# ── Agents catalogue ──
_AGENT_CATALOG: dict[str, dict] = {
    "porthos": {
        "name": "porthos",
        "skill": "directives_audit",
        "command": [sys.executable, "-m", "skills.directives_audit.cli", "audit"],
        "description": "Audit des directives (AGENTS.md, CLAUDE.md)",
        "requires": [],
        "mutating": False,
        "evidence_ref": "audit:directives",
    },
    "rochefort": {
        "name": "rochefort",
        "skill": "cardinal",
        "command": [sys.executable, "-m", "skills.cardinal.cli", "audit"],
        "description": "Contre-audit red team",
        "requires": ["porthos"],
        "mutating": False,
        "evidence_ref": "audit:counter",
    },
    "dartagnan": {
        "name": "d'artagnan",
        "skill": "fix",
        "command": [sys.executable, "-m", "skills.fix.cli", "fix"],
        "description": "Correction automatique",
        "requires": ["porthos"],
        "mutating": True,
        "evidence_ref": "change:fix",
    },
    "aramis": {
        "name": "aramis",
        "skill": "optimize",
        "command": [sys.executable, "-m", "skills.skill_project_optimizer.cli", "optimize"],
        "description": "Optimisation token",
        "requires": [],
        "mutating": True,
        "evidence_ref": "change:optimize",
    },
    "security": {
        "name": "security",
        "skill": "security_scanner",
        "command": [sys.executable, "-m", "skills.security_scanner.cli", "scan"],
        "description": "Scan sécurité",
        "requires": [],
        "mutating": False,
        "evidence_ref": "audit:security",
    },
    "fast_context": {
        "name": "fast_context",
        "skill": "fast_context",
        "command": [sys.executable, "-m", "skills.fast_context.cli", "explore"],
        "description": "Exploration repo",
        "requires": [],
        "mutating": False,
        "evidence_ref": "",
    },
    "migration_audit": {
        "name": "migration_audit",
        "skill": "migration_audit",
        "command": [sys.executable, "-m", "skills.migration_audit.cli"],
        "description": "Gate deterministic entre BUILDER et VALIDATOR",
        "requires": [],
        "mutating": False,
        "evidence_ref": "audit:migration",
    },
    "test": {
        "name": "test",
        "skill": None,  # shell command
        "command": [sys.executable, "-m", "pytest"],
        "description": "Lance les tests",
        "requires": [],
        "mutating": False,
        "evidence_ref": "tests:project",
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
    mutating: bool = False
    evidence_ref: str = ""


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
        mission: Mapping | None = None,
        context_manifest: Mapping | None = None,
        worker_id: str = "meta-harness",
        attempt_id: str | None = None,
        base_ref: str = "HEAD",
        workspace_root: str | Path | None = None,
        addressed_failure_refs: list[str] | None = None,
    ):
        self.workdir = str(Path(workdir).resolve())
        self.governance = Governance(require_approval=approval)
        self.mission = None
        self.context_manifest = dict(context_manifest or {})
        self.worker_id = worker_id
        self.attempt_id = attempt_id or f"attempt-{uuid.uuid4().hex[:12]}"
        self.base_ref = base_ref
        self.workspace_root = workspace_root
        self.addressed_failure_refs = list(addressed_failure_refs or [])
        self.lease_manager = None
        self.workspace_lease = None
        if mission is not None:
            from skills.run_contract import validate_mission

            self.mission = validate_mission(mission)
            budgets = self.mission["budgets"]
            if safe_exit_config is None:
                safe_exit_config = SafeExitConfig(
                    max_iterations=budgets["max_iterations"],
                    max_tool_calls=budgets["max_tool_calls"],
                    max_wall_seconds=budgets["max_wall_seconds"],
                )
        self.session = Session(
            name=f"pipeline_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            storage_dir=Path(self.workdir) / ".botte-cache" / "sessions",
        )
        self.safe_exit_config = safe_exit_config or SafeExitConfig()

    def list_agents(self) -> list[dict]:
        """List available agents with metadata."""
        return [
            {"name": a["name"], "skill": a["skill"],
             "description": a["description"], "requires": a["requires"],
             "mutating": a["mutating"]}
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
                if self.mission is not None:
                    raise ValueError(
                        f"mission runs reject unknown agent/command: {name}"
                    )
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
                            mutating=dep_info.get("mutating", False),
                            evidence_ref=dep_info.get("evidence_ref", ""),
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
                mutating=agent_info.get("mutating", False),
                evidence_ref=agent_info.get("evidence_ref", ""),
            )
            self._validate_step_authority(step)
            resolved.append(step)
            seen.add(name)

        plan.steps = resolved
        return plan

    def execute(self, plan: PipelinePlan) -> Session:
        """Execute a plan step by step, respecting governance and SAFE-EXIT."""
        self.session.plan = plan
        run_root = self.workdir
        if self.mission is not None:
            from skills.meta_harness.lease import WorktreeLeaseManager
            from skills.meta_harness.review import CheckpointRegistry

            self.lease_manager = WorktreeLeaseManager(
                self.workdir, workspace_root=self.workspace_root
            )
            ttl = self.mission["budgets"]["max_wall_seconds"] + 300
            self.workspace_lease = self.lease_manager.create(
                self.worker_id, base_ref=self.base_ref, ttl_seconds=ttl
            )
            run_root = self.workspace_lease.workspace_path
            try:
                CheckpointRegistry(self.workdir).register_attempt(
                    self.mission,
                    attempt_id=self.attempt_id,
                    addressed_failure_refs=self.addressed_failure_refs,
                )
            except Exception:
                # The lease is brand-new and clean here. Release it rather than
                # consuming a workspace for a rejected revision contract.
                self.lease_manager.release(self.workspace_lease)
                raise
            self.session.bind_contract(
                mission_id=self.mission["mission_id"],
                attempt_id=self.attempt_id,
                worker_id=self.worker_id,
                workspace_lease=self.workspace_lease.contract_view(),
                context_manifest_sha256=self.context_manifest.get(
                    "manifest_sha256", ""
                ),
            )
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
            sandbox = Sandbox(workdir=run_root, sandbox_dir=f".botte-sandbox/{step.agent}")

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
        if self.mission is not None and self.workspace_lease is not None:
            self.workspace_lease = self.lease_manager.refresh(self.workspace_lease)
            self.session.workspace_lease = self.workspace_lease.contract_view()
            self.session.set_handoff(self._build_handoff(plan))
            self._emit_bound_outcome(plan)
        self.session._save()
        return self.session

    def _validate_step_authority(self, step: Step) -> None:
        if self.mission is None or not step.mutating:
            return
        tiers = {
            "SIMULATE": AuthorizationTier.SIMULATE,
            "SHADOW": AuthorizationTier.SHADOW,
            "ACT": AuthorizationTier.ACT,
        }
        if tiers[self.mission["authority"]] < AuthorizationTier.ACT:
            raise ValueError(
                f"agent {step.agent} mutates the workspace and requires ACT"
            )

    def _build_handoff(self, plan: PipelinePlan) -> dict:
        from skills.run_contract import build_handoff

        checks = []
        evidence_refs = []
        for result, step in zip(self.session.results, plan.steps):
            status = {
                "passed": "PASS",
                "failed": "FAIL",
                "skipped": "SKIPPED",
            }.get(result.status, "UNCERTAIN")
            evidence_ref = (
                step.evidence_ref
                if status == "PASS"
                else f"harness:{self.session.name}:{step.agent}:{result.exit_code}"
            )
            checks.append(
                {
                    "name": step.agent,
                    "status": status,
                    "evidence_ref": evidence_ref,
                }
            )
            if evidence_ref:
                evidence_refs.append(evidence_ref)

        required = set(self.mission["required_evidence"])
        produced = set(evidence_refs)
        approval_required = (
            self.mission["risk"] in ("R3", "R4")
            and not self.mission.get("owner_approval_ref")
        )
        if self.session.termination_decision == "UNCERTAIN":
            status = "UNCERTAIN"
            next_action = "Revise the plan; do not reset SAFE-EXIT inside this attempt."
        elif plan.has_failed:
            status = "FAIL"
            next_action = "Name the failing proof before creating a bounded revision."
        elif approval_required:
            status = "APPROVAL_REQUIRED"
            next_action = "Obtain the owner-review approval before any ACT transition."
        elif required <= produced and checks and all(
            item["status"] == "PASS" for item in checks
        ):
            status = "READY_FOR_REVIEW"
            next_action = "Run a fresh Gauntlet review in a distinct workspace."
        else:
            status = "PARTIAL"
            next_action = "Collect the mission's missing required evidence."

        return build_handoff(
            self.mission,
            attempt_id=self.attempt_id,
            worker_id=self.worker_id,
            status=status,
            workspace_lease=self.workspace_lease.contract_view(),
            checks=checks,
            evidence_refs=sorted(produced),
            uncertainties=(
                [self.session.termination_reason]
                if self.session.termination_reason
                else []
            ),
            approval_required=approval_required,
            next_safe_action=next_action,
        )

    def _repository_ref(self) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", self.workdir, "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        remote = result.stdout.strip().removesuffix(".git")
        if remote.startswith("git@github.com:"):
            return remote.split(":", 1)[1]
        marker = "github.com/"
        if marker in remote:
            return remote.split(marker, 1)[1]
        return ""

    def _emit_bound_outcome(self, plan: PipelinePlan) -> None:
        from skills.trajectory.outcome import emit_outcome

        handoff = self.session.handoff or {}
        status = handoff.get("status", "PARTIAL")
        outcome_status = {
            "FAIL": "FAIL",
            "UNCERTAIN": "UNCERTAIN",
            "APPROVAL_REQUIRED": "APPROVAL_REQUIRED",
        }.get(status, "PARTIAL")
        checks = handoff.get("checks", [])
        evidence = list(handoff.get("evidence_refs", []))
        if outcome_status in ("FAIL", "UNCERTAIN"):
            evidence.extend(
                check["evidence_ref"]
                for check in checks
                if check.get("evidence_ref")
            )
        command_basis = json.dumps(
            [step.command + step.args for step in plan.steps],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        risk = {
            "R0": "low", "R1": "low", "R2": "standard",
            "R3": "high", "R4": "critical",
        }[self.mission["risk"]]
        verified_by = (
            "harness:meta-harness"
            if outcome_status in ("FAIL", "UNCERTAIN") and evidence
            else ""
        )
        emitted = emit_outcome(
            self.mission["objective"],
            project_root=self.workdir,
            execution_id=f"{self.mission['mission_id']}/{self.attempt_id}",
            source="meta_harness",
            route="deterministic",
            status=outcome_status,
            verified_by=verified_by,
            evidence_refs=sorted(set(evidence)),
            risk=risk,
            permission_profile=self.mission["authority"].casefold(),
            harness="meta-harness/run-contract-v1",
            acted=any(step.mutating and step.status == "passed" for step in plan.steps),
            approval_required=handoff.get("approval_required", False),
            mission_id=self.mission["mission_id"],
            attempt_id=self.attempt_id,
            worker_id=self.worker_id,
            workspace_lease=self.workspace_lease.contract_view(),
            repository_ref=self._repository_ref(),
            base_sha=self.workspace_lease.base_sha,
            head_sha=self.workspace_lease.head_sha,
            dirty_tree_sha256=self.workspace_lease.dirty_tree_sha256,
            check_command_sha256=hashlib.sha256(
                command_basis.encode("utf-8")
            ).hexdigest(),
            checks=checks,
            uncertainties=handoff.get("uncertainties", []),
            next_safe_action=handoff.get("next_safe_action", ""),
        )
        self.session.outcome_id = emitted["envelope"]["id"]

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
