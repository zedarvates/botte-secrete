"""auto_router — auto-decide local vs cloud, multi-provider, with fusion.

    from skills.auto_router import auto_route, auto_run
    from skills.auto_router import fusion

    auto_route("classify: bug or feature?")        # decision only
    auto_run("design a rate limiter", max_tokens=800)
    fusion.draft_refine("explain CAP theorem")      # local drafts, cloud refines
    fusion.vote("capital of France in one word?")   # consensus across models

Effort is judged automatically (skills.auto_router.effort); cloud models live in
a data-driven catalog (skills.auto_router.providers) reached via OpenRouter or
native keys. Local backends come from skills.llm_backends.
"""

from skills.auto_router.effort import estimate, EffortEstimate
from skills.auto_router.router import AutoRouter, AutoDecision, auto_route, auto_run
from skills.auto_router import providers, fusion

__all__ = [
    "estimate", "EffortEstimate", "AutoRouter", "AutoDecision",
    "auto_route", "auto_run", "providers", "fusion",
]
