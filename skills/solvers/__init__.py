"""solvers — deterministic assignment, bin-packing, and precedence scheduling.

    from skills.solvers import assign_balanced, bin_pack, schedule
    assign_balanced([("a", 5), ("b", 3)], ["w1", "w2"])   # balance load, 0 tokens
    schedule(["build", "test", "deploy"], {"test": ["build"], "deploy": ["test"]})
"""

from skills.solvers.solvers import assign_balanced, bin_pack, schedule

__all__ = ["assign_balanced", "bin_pack", "schedule"]
