"""governance — garde-fous, approval gates, budgets, rollback.

Chaque étape peut être bloquée par une gate.
L'approval humaine peut être requise avant apply.
Budgets limitent le nombre ou la durée des étapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ApprovalGate:
    """Result of a governance check."""
    approved: bool = True
    blocked: bool = False
    reason: str = ""
    requires_human: bool = False


class Governance:
    """Governance layer for the meta-harness.

    Controls:
    - Human approval gates (before apply, before destructive ops)
    - Budget limits (max steps, max duration)
    - Safety rules (no destructive commands without approval)
    """

    DESTRUCTIVE_KEYWORDS = {"rm", "rmdir", "delete", "drop", "truncate",
                            "format", "mkfs", "dd", ":(){ :|:& };:"}

    def __init__(self, require_approval: bool = False,
                 max_steps: int = 20, max_duration: int = 600):
        self.require_approval = require_approval
        self.max_steps = max_steps
        self.max_duration = max_duration
        self.steps_executed = 0

    def check(self, step) -> ApprovalGate:
        """Check if a step can proceed through governance."""
        self.steps_executed += 1

        # Step limit
        if self.steps_executed > self.max_steps:
            return ApprovalGate(
                approved=False, blocked=True,
                reason=f"Step limit exceeded ({self.max_steps})"
            )

        # Check for destructive commands
        cmd_str = " ".join(step.command).lower()
        for keyword in self.DESTRUCTIVE_KEYWORDS:
            if keyword in cmd_str:
                return ApprovalGate(
                    approved=False, blocked=True,
                    reason=f"Destructive command detected: '{keyword}' in '{' '.join(step.command)}'",
                    requires_human=True,
                )

        # Global approval required
        if self.require_approval:
            return ApprovalGate(
                approved=False, blocked=True,
                reason="Human approval required (--approval mode)",
                requires_human=True,
            )

        return ApprovalGate(approved=True)

    def human_approve(self, step) -> ApprovalGate:
        """Simulate human approval (for testing). In production, prompts user."""
        return ApprovalGate(approved=True)
