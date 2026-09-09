"""Select a lexical shortlist within a conservatively quantized token budget.

  knapsack(items, budget)        exact 0/1 knapsack over rounded-up token costs
  select_skills(query, budget)   rank skills (skill_finder) → knapsack → proposal

Quantization can exclude combinations that fit the original budget. Relevance
and token costs are estimates; callers still need to read selected instructions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Optional


@dataclass
class Item:
    name: str
    kind: str        # "skill" | "doc"
    tokens: int      # token cost to load it
    relevance: float # how relevant to the query (higher = better)
    ref: str = ""    # path or identifier

    def to_dict(self) -> dict:
        return asdict(self)


def _require_int(value, name: str, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def knapsack(items: list, budget: int, *, unit: int = 20):
    """Exact 0/1 knapsack for rounded-up costs, not for the original token costs.

    Token costs are scaled by ``unit`` to bound the DP table (a budget of a few
    thousand tokens → a few hundred cells). Deterministic. Returns
    (chosen_indices, total_tokens, total_relevance).
    """
    _require_int(budget, "budget")
    _require_int(unit, "unit", 1)
    for it in items:
        _require_int(it.tokens, "item tokens")
        if (isinstance(it.relevance, bool) or not isinstance(it.relevance, (int, float))
                or not math.isfinite(it.relevance)):
            raise ValueError("item relevance must be a finite number")

    n = len(items)
    w = [max(1, -(-it.tokens // unit)) for it in items]  # ceil(tokens/unit), at least one unit
    cap = min(budget // unit, sum(w))
    if n == 0 or cap == 0:
        return [], 0, 0.0

    v = [it.relevance for it in items]

    dp = [[0.0] * (cap + 1) for _ in range(n + 1)]
    keep = [[False] * (cap + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        wi, vi, prev, row, krow = w[i - 1], v[i - 1], dp[i - 1], dp[i], keep[i]
        for c in range(cap + 1):
            best, take = prev[c], False
            if wi <= c:
                cand = prev[c - wi] + vi
                if cand > best:
                    best, take = cand, True
            row[c], krow[c] = best, take

    chosen: list = []
    c = cap
    for i in range(n, 0, -1):
        if keep[i][c]:
            chosen.append(i - 1)
            c -= w[i - 1]
    chosen.reverse()
    total_tokens = sum(items[i].tokens for i in chosen)
    total_rel = sum(items[i].relevance for i in chosen)
    return chosen, total_tokens, round(total_rel, 4)


def select_skills(query: str, *, budget: int = 4000, roots: Optional[list] = None,
                  pool: int = 40) -> dict:
    """Propose skills using a lexical shortlist and a rounded token budget.

    Ranks the catalog lexically ([[skill_finder]]), then knapsacks the top ``pool``
    candidates. This returns references; it does not load instructions into an
    agent, verify applicability, or resolve dependencies between skills.
    """
    query = (query or "").strip()
    if not query:
        return {"error": "empty query"}
    try:
        _require_int(budget, "budget")
        _require_int(pool, "pool")
    except ValueError as exc:
        return {"error": str(exc)}
    try:
        from skills.skill_finder import rank, load_catalog
    except ImportError:
        return {"error": "skill_finder unavailable"}

    catalog = load_catalog(roots)
    matches = rank(query, catalog, top_k=pool)
    items = [Item(name=m.skill.name, kind="skill", tokens=m.skill.tokens_est,
                  relevance=m.score, ref=m.skill.path) for m in matches]

    idx, toks, rel = knapsack(items, budget)
    chosen = [items[i] for i in idx]
    chosen_indices = set(idx)
    dropped = [it for i, it in enumerate(items) if i not in chosen_indices]
    catalog_tokens = sum(s.tokens_est for s in catalog)

    return {
        "query": query, "budget": budget,
        "chosen": [it.to_dict() for it in chosen],
        "dropped": [it.to_dict() for it in dropped],
        "tokens_used": toks, "relevance_captured": rel,
        "catalog_size": len(catalog), "catalog_tokens": catalog_tokens,
        "savings_note": (
            f"Load {len(chosen)} skill(s) (~{toks} tok) for this task instead of "
            f"the whole {len(catalog)}-skill catalog (~{catalog_tokens} tok)."),
        "cloud_tokens": 0,
    }
