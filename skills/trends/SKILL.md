---
name: trends
layer: GOVERN
description: Track a project's audit metrics over time (directive score, duplication, LOC, always-on cost, fix count) and show the change since the previous run. Use to see whether the project is getting healthier/cheaper across audits.
---

# trends — the project's metrics over time

```bash
python -m skills.trends.cli snapshot .   # record current metrics
python -m skills.trends.cli show .        # series + Δ since previous run
```

Each `snapshot` appends to `.botte/trends.jsonl`; `show` reports the series and
the delta (e.g. "duplicate_groups 35 ▼ 12"). Run it after each `checkup` to watch
the project improve. Exposed via [[llm_mcp]] as `trends_show`. Related:
[[checkup]], [[metrics]], [[report]].
