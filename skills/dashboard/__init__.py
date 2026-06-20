"""dashboard — one timestamped HTML view of cost, savings, trends and fixes.

    from skills.dashboard.dashboard import generate, collect
    generate(".")    # → .botte/reports/dashboard_<stamp>.html
"""

from skills.dashboard.dashboard import generate, collect

__all__ = ["generate", "collect"]
