"""Cost estimator — tokens · model · money · time for a task or a fix.

The cross-cutting answer to "what will this correction cost?". Reuses the
tiered_router cost model (tokens + $) and adds a throughput model for wall-time.
Everything is an estimate, with the assumptions made explicit. Pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from skills.tiered_router import (
    Tier, TIER_INFO, TASK_TIER, estimate_tokens, estimate_cost,
)

# Rough output throughput per tier (tokens/sec) + fixed overhead (s).
# Local is free but slower per token; cloud is faster but billed.
_THROUGHPUT = {
    Tier.FREE:     (9999.0, 0.1),   # static/NPU — effectively instant
    Tier.LOCAL:    (35.0, 1.0),     # local LLM
    Tier.CHEAP:    (80.0, 0.6),     # cloud small
    Tier.STANDARD: (60.0, 0.8),     # cloud standard
    Tier.PREMIUM:  (45.0, 1.2),     # cloud best
}


@dataclass
class CostEstimate:
    tier: str
    model_class: str
    local: bool
    tokens_in: int
    tokens_out: int
    usd: float
    seconds: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["usd"] = round(self.usd, 6)
        d["seconds"] = round(self.seconds, 1)
        return d

    def human(self) -> str:
        money = "free" if self.usd == 0 else f"${self.usd:.4f}"
        where = "local" if self.local else "cloud"
        return (f"{self.tokens_in + self.tokens_out} tok · {self.model_class} "
                f"({where}) · {money} · ~{self.seconds:.0f}s")


def estimate(task_type: str, input_chars: int, *, complexity: float = 1.0,
             tier: Optional[Tier] = None) -> CostEstimate:
    """Estimate tokens, model, $ and wall-time for a task."""
    tier = tier or TASK_TIER.get(task_type, Tier.STANDARD)
    t_in, t_out = estimate_tokens(task_type, input_chars, complexity)
    usd = estimate_cost(tier, t_in, t_out)
    rate, overhead = _THROUGHPUT[tier]
    seconds = overhead + t_out / rate + t_in / (rate * 4)  # prefill cheaper than decode
    _, _, desc = TIER_INFO[tier]
    return CostEstimate(
        tier=tier.name, model_class=desc.split("—")[-1].strip() if "—" in desc else desc,
        local=tier <= Tier.LOCAL, tokens_in=t_in, tokens_out=t_out,
        usd=usd, seconds=seconds,
    )


# Map a fix kind to a representative task tier + per-fix input size (chars).
_FIX_PROFILE = {
    "dead_code":   ("refactor_suggest", Tier.LOCAL, 400),   # remove a symbol — easy/local
    "duplication": ("refactor_suggest", Tier.CHEAP, 1200),  # dedup across files — review
    "stale_ref":   ("simple_qa", Tier.LOCAL, 120),          # fix a path — trivial/local
    "complexity":  ("refactor_suggest", Tier.STANDARD, 2000),
    "secret":      ("critical_fix", Tier.PREMIUM, 600),     # rotate/remove — careful
    "directive":   ("doc_generate", Tier.LOCAL, 300),
}


def estimate_fix(kind: str, *, count: int = 1, complexity: float = 1.0) -> CostEstimate:
    """Estimate the cost to apply `count` fixes of a given kind."""
    task, tier, chars = _FIX_PROFILE.get(kind, ("refactor_suggest", Tier.CHEAP, 800))
    est = estimate(task, chars * max(count, 1), complexity=complexity, tier=tier)
    return est
