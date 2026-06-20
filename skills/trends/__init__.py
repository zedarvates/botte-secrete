"""trends — track audit metrics over time and show the delta.

    from skills.trends import snapshot, show
    snapshot(".")        # record current metrics
    show(".")            # series + change since last run
"""

from skills.trends.trends import snapshot, show, load

__all__ = ["snapshot", "show", "load"]
