"""control_loop — measure routing outcomes, adapt the routing thresholds.

    from skills.control_loop.control_loop import record, analyze, adapt, apply
    record(effort_score=0.4, tier="LOCAL", mode="local", tokens_saved=500)
    a = adapt(analyze())
    if a["changed"]: apply(a["thresholds"])   # the router behaves differently next time
"""

from skills.control_loop.control_loop import (
    record, load, analyze, adapt, apply, reset_thresholds,
)

__all__ = ["record", "load", "analyze", "adapt", "apply", "reset_thresholds"]
