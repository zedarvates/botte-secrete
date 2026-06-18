"""metrics — cost-focused project metrics, broken down per component.

    from skills.metrics import collect
    m = collect("/path/to/project")
    m.cost           # token/cost framing (analysis = 0 LLM tokens)
    m.by_component   # LOC per top-level component
"""

from skills.metrics.metrics import collect, Metrics

__all__ = ["collect", "Metrics"]
