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

__all__ = [
    "MetaHarness", "PipelinePlan", "Step",
    "Sandbox", "Governance", "ApprovalGate", "Session",
]
