#!/usr/bin/env python3
"""Budget hardware recommender — suggest what to buy for a given budget.

    python -m skills.infra_advisor.budget_recommender <budget_eur>
"""

from __future__ import annotations

import sys

RECOMMENDATIONS = [
    (300, "Used RTX 3060 12GB — run 7B models at Q4 locally"),
    (600, "RTX 4060 Ti 16GB — run 13B models at Q4, Hailo-8 for vision"),
    (1000, "Used RTX 3090 24GB — run 32B models at Q4"),
    (2000, "RTX 4090 24GB + Hailo-8 — full local AI stack"),
    (5000, "Dual RTX 4090 or Mac Studio M2 Ultra — run 70B models at Q4"),
]


def recommend(budget_eur: float) -> list[str]:
    return [desc for price, desc in RECOMMENDATIONS if price <= budget_eur]


def main():
    budget = float(sys.argv[1])
    recs = recommend(budget)
    print(f"💰 Budget: {budget:,.0f}€")
    if not recs:
        print("   Use free cloud tiers (GitHub Models, Cloudflare, Cerebras) until you can afford a GPU.")
        return
    for r in recs:
        print(f"   → {r}")


if __name__ == "__main__":
    main()
