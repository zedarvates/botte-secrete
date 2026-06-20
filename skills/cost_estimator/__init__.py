"""cost_estimator — tokens · model · money · time for a task or a fix.

    from skills.cost_estimator import estimate, estimate_fix
    estimate("code_review", 4000).human()      # "… tok · model · $ · ~Ns"
    estimate_fix("dead_code", count=11)
"""

from skills.cost_estimator.cost_estimator import estimate, estimate_fix, CostEstimate

__all__ = ["estimate", "estimate_fix", "CostEstimate"]
