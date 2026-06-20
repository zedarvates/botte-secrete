"""conductor — route a goal to an ordered, local-first plan of capabilities.

    from skills.conductor.conductor import plan
    plan("test my desktop app and report crashes")
"""

from skills.conductor.conductor import plan, Step, CAP_COMMAND

__all__ = ["plan", "Step", "CAP_COMMAND"]
