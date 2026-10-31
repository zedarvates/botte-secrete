"""conductor — route a goal to an ordered, local-first plan of capabilities.

    from skills.conductor.conductor import plan
    plan("test my desktop app and report crashes")
"""

from skills.conductor.conductor import plan, Step, CAP_COMMAND
from skills.conductor.executor import execute, run_goal, classify, SAFE_CAPS
from skills.conductor.verified import execute_verified, validate_plan

__all__ = ["plan", "Step", "CAP_COMMAND",
           "execute", "run_goal", "classify", "SAFE_CAPS", "execute_verified", "validate_plan"]
