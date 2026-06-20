"""cluster — the homelab as one schedulable resource (idle-aware routing).

    from skills.cluster.cluster import machines, pick, status, delegate
    pick("lru")        # least-recently-used backend → spread work to idle boxes
    status(scan_subnet=True)
"""

from skills.cluster.cluster import machines, pick, status, delegate, Machine

__all__ = ["machines", "pick", "status", "delegate", "Machine"]
