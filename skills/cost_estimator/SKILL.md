---
name: cost_estimator
layer: DECIDE
description: Estimate what a task or a fix will cost — tokens, model/tier, money ($), and wall-time — using the tiered cost model. Use whenever the user wants to know the cost of a correction, audit, or task before running it, or to compare local vs cloud cost.
---

# cost_estimator — tokens · model · money · time

```python
from skills.cost_estimator import estimate, estimate_fix
estimate("code_review", 4000).human()    # "2000 tok · Haiku/Flash (cloud) · $0.0001 · ~16s"
estimate_fix("dead_code", count=11)       # local · free · ~34s
```

Reuses `tiered_router`'s token+$ model and adds a throughput model for time.
Local tiers are free (slower/token); cloud tiers are billed (faster). Powers the
`fix` plan and any "what will this cost?" question. Exposed via [[llm_mcp]] as
`estimate_cost`. Related: [[fix]], [[auto_router]], [[metrics]].
