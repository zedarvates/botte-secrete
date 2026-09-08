"""meta_harness — orchestration multi-agent type Omnigent pour Botte.

    from skills.meta_harness import MetaHarness, PipelinePlan

    h = MetaHarness(workdir="/path/to/project")
    plan = h.plan(["audit", "fix", "test"])
    session = h.execute(plan)
    print(session.report())
"""

from skills.meta_harness.orchestrator import MetaHarness, PipelinePlan, Step
from skills.meta_harness.runner import Sandbox
from skills.meta_harness.governance import Governance, ApprovalGate
from skills.meta_harness.session import Session
from skills.meta_harness.lease import (
    WorkspaceLease,
    WorkspaceLeaseError,
    WorktreeLeaseManager,
)
from skills.meta_harness.review import CheckpointRegistry, ReviewError, review_handoff

__all__ = [
    "MetaHarness", "PipelinePlan", "Step",
    "Sandbox", "Governance", "ApprovalGate", "Session",
    "WorkspaceLease", "WorkspaceLeaseError", "WorktreeLeaseManager",
    "CheckpointRegistry", "ReviewError", "review_handoff",
]
