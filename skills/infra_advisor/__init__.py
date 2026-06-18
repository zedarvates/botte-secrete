"""infra_advisor — hardware/software/MCP tips + auto audit to cut token cost.

    from skills.infra_advisor import advise, auto_audit
    advise()                 # cluster tips + ASCII diagram
    auto_audit(".")          # directives + infra + duplication + skills, one pass
"""

from skills.infra_advisor.advisor import advise, recommend, gather, ascii_diagram, Tip, Snapshot
from skills.infra_advisor.auto_audit import auto_audit, duplication_scan

__all__ = ["advise", "recommend", "gather", "ascii_diagram", "Tip", "Snapshot",
           "auto_audit", "duplication_scan"]
