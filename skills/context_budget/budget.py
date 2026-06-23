"""Context budget — pick the optimal set of context to load under a token budget.

The OR-Tools principle, applied to the agent's always-on cost: choosing *which*
skills/docs to load is a **0/1 knapsack** — maximize total relevance while the
summed token cost stays under a budget. That's an exact deterministic solver
(stdlib DP), not an LLM "decide what's relevant" call, so it costs **0 tokens**
and beats the greedy "take the top matches until full" heuristic.

  knapsack(items, budget)        exact 0/1 knapsack over token cost
  select_skills(query, budget)   rank skills (skill_finder) → knapsack → load set
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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


def knapsack(items: list, budget: int, *, unit: int = 20):
    """Exact 0/1 knapsack: maximize summed relevance s.t. summed tokens ≤ budget.

    Token costs are scaled by ``unit`` to bound the DP table (a budget of a few
    thousand tokens → a few hundred cells). Deterministic. Returns
    (chosen_indices, total_tokens, total_relevance).
    """
    n = len(items)
    cap = max(0, budget // unit)
    if n == 0 or cap == 0:
        return [], 0, 0.0

    w = [max(1, -(-it.tokens // unit)) for it in items]  # ceil(tokens/unit)
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
    """Choose the best skills to load for a task within a token budget. 0 tokens.

    Ranks the catalog lexically ([[skill_finder]]), then knapsacks the top ``pool``
    candidates so the loaded set maximizes relevance under the budget — instead of
    loading the whole catalog every turn.
    """
    query = (query or "").strip()
    if not query:
        return {"error": "empty query"}
    try:
        from skills.skill_finder import rank, load_catalog
    except ImportError:
        return {"error": "skill_finder unavailable"}

    catalog = load_catalog(roots)
    matches = rank(query, catalog)[:pool]
    items = [Item(name=m.skill.name, kind="skill", tokens=m.skill.tokens_est,
                  relevance=m.score, ref=m.skill.path) for m in matches]

    idx, toks, rel = knapsack(items, budget)
    chosen = [items[i] for i in idx]
    chosen_names = {it.name for it in chosen}
    dropped = [it for it in items if it.name not in chosen_names]
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
